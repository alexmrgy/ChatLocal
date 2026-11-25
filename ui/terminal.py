"""Terminal intégré : lance du code Python ou C (sans fichier choisi) et des commandes simples."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from . import theme
from .widgets import IconButton

def python_executable() -> str | None:
    """Python à utiliser pour lancer le code de l'IA. Dans l'exécutable (.exe), sys.executable est l'application
    elle-même : on cherche alors le Python installé sur le PC."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python") or shutil.which("py")


OUT, ERR, INFO, OK, BAD = "#e6e6e6", "#ff8a80", "#7aa7ff", "#4ade80", "#ff6b6b"

PY_LANGS = {"python", "py", "python3", "py3"}
C_LANGS = {"c"}
C_COMPILERS = ("gcc", "clang", "tcc", "cc")
# C : sortie non tamponnée, pour que les « printf » / invites s'affichent tout de suite dans le terminal
UNBUF_H = '#include <stdio.h>\n__attribute__((constructor)) static void __chatlocal_unbuf(void){ setvbuf(stdout, NULL, _IONBF, 0); }\n'


def run_kind(lang: str, code: str = "") -> str | None:
    """'python' | 'c' | None (langage non lançable). Devine le langage si l'IA ne l'a pas précisé."""
    l = (lang or "").lower().strip()
    if l in PY_LANGS:
        return "python"
    if l in C_LANGS:
        return "c"
    if not l:
        if "#include" in code and "main" in code:
            return "c"
        if any(k in code for k in ("def ", "import ", "print(")):
            return "python"
    return None


def find_c_compiler() -> str | None:
    for name in C_COMPILERS:
        path = shutil.which(name)
        if path:
            return path
    return None


class _Dots(QWidget):
    """Trois pastilles de couleur façon fenêtre de terminal (peintes : aucune police nécessaire)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(46, 12)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
            p.setBrush(QColor(c))
            p.drawEllipse(i * 17, 1, 10, 10)


class Terminal(QWidget):
    runningChanged = Signal(bool)
    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerminalBox")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._proc: QProcess | None = None
        self._stage = ""          # "compile" | "run" | "shell"
        self._workdir: str | None = None
        self._t0 = 0.0
        self._stopped = False
        self._exe = ""
        self._retries = 0
        self._blocked = False         # Windows a refusé d'exécuter le .exe compilé

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 2, 10, 10)          # le terminal est une carte arrondie dans le panneau
        root.setSpacing(0)
        card = QFrame(objectName="TermCard")
        root.addWidget(card)
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head_w = QFrame(objectName="TermHead")
        head_w.setFixedHeight(40)
        head = QHBoxLayout(head_w)
        head.setContentsMargins(14, 0, 8, 0)
        head.setSpacing(8)
        head.addWidget(_Dots())
        head.addSpacing(4)
        head.addWidget(QLabel("Terminal", objectName="TermTitle"))
        self.status = QLabel(objectName="TermStatus")
        head.addWidget(self.status)
        head.addStretch(1)
        self.clear_btn = IconButton("trash", size=(30, 30), icon_size=16, radius=9, fg=theme.TEXT_DIM,
                                    tooltip="Effacer le terminal")
        self.clear_btn.clicked.connect(self.clear)
        head.addWidget(self.clear_btn)
        self.close_btn = IconButton("win_close", size=(30, 30), icon_size=15, radius=9, fg=theme.TEXT_DIM,
                                    tooltip="Fermer le terminal")
        self.close_btn.clicked.connect(self.closeRequested)
        head.addWidget(self.close_btn)
        v.addWidget(head_w)

        self.out = QPlainTextEdit(objectName="TermOut")
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(5000)
        self.out.setFrameShape(QPlainTextEdit.NoFrame)
        self.out.document().setDocumentMargin(12)
        f = QFont()
        f.setFamilies(["Cascadia Mono", "Consolas", "monospace"])
        f.setPixelSize(13)
        self.out.setFont(f)
        v.addWidget(self.out, 1)

        row = QHBoxLayout()
        row.setContentsMargins(12, 4, 12, 12)
        row.setSpacing(8)
        self.prompt = QLabel(">", objectName="TermPrompt")
        row.addWidget(self.prompt)
        self.input = QLineEdit(objectName="TermInput")
        self.input.setPlaceholderText("Commande (PowerShell) ou réponse au programme en cours")
        self.input.returnPressed.connect(self._submit)
        row.addWidget(self.input, 1)
        v.addLayout(row)

    # ----- état -----
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def workdir(self) -> str:
        if self._workdir is None or not os.path.isdir(self._workdir):
            self._workdir = tempfile.mkdtemp(prefix="chatlocal_run_")
        return self._workdir

    def cleanup(self) -> None:
        self.stop()
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None

    def clear(self) -> None:
        self.out.clear()
        self.status.setText("")

    def _set_status(self, text: str, color: str = theme.TEXT_MUTE) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")

    # ----- affichage -----
    def append(self, text: str, color: str = OUT) -> None:
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "")
        bar = self.out.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 4
        cur = QTextCursor(self.out.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cur.insertText(text, fmt)
        if follow:
            bar.setValue(bar.maximum())

    def line(self, text: str, color: str = INFO) -> None:
        if self.out.toPlainText() and not self.out.toPlainText().endswith("\n"):
            self.append("\n")
        self.append(text + "\n", color)

    # ----- lancement -----
    def run_code(self, code: str, lang: str) -> None:
        kind = run_kind(lang, code)
        if kind is None:
            self.line("Ce langage ne peut pas encore être lancé ici (Python et C seulement).", BAD)
            return
        self.stop()
        wd = self.workdir()
        self._t0 = time.time()
        self._stopped = False
        self._blocked = False
        if kind == "python":
            path = os.path.join(wd, "main.py")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(code)
            self.line(f"$ python main.py", INFO)
            py = python_executable()
            if not py:
                self.line("Python est introuvable sur cet ordinateur : installe-le (python.org) pour lancer du code "
                          "Python.", BAD)
                return
            self._start(py, ["-u", path], "run", wd)
        else:
            cc = find_c_compiler()
            if not cc:
                self.line("Aucun compilateur C trouvé (gcc, clang ou tcc). Installe-en un, par exemple MSYS2/MinGW-w64, "
                          "puis relance l'application.", BAD)
                return
            path = os.path.join(wd, "main.c")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(code)
            self._exe = os.path.join(wd, "main.exe" if os.name == "nt" else "main")
            args = [path, "-o", self._exe, "-lm"]
            name = os.path.basename(cc).lower()
            if name.startswith(("gcc", "clang", "cc")):
                with open(os.path.join(wd, "unbuf.h"), "w", encoding="utf-8") as f:
                    f.write(UNBUF_H)
                args = ["-include", os.path.join(wd, "unbuf.h"), "-Wall"] + args
            self.line(f"$ {os.path.basename(cc)} main.c -o main", INFO)
            self._start(cc, args, "compile", wd)

    def run_shell(self, cmd: str) -> None:
        self.stop()
        self._t0 = time.time()
        self._stopped = False
        self.line(f"> {cmd}", INFO)
        full = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + cmd
        self._start("powershell", ["-NoProfile", "-NonInteractive", "-Command", full], "shell", self.workdir())

    def _start(self, program: str, args: list[str], stage: str, wd: str) -> None:
        p = QProcess(self)
        self._proc, self._stage = p, stage
        p.setWorkingDirectory(wd)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        p.setProcessEnvironment(env)
        p.readyReadStandardOutput.connect(lambda p=p: self._read(p, False))
        p.readyReadStandardError.connect(lambda p=p: self._read(p, True))
        p.finished.connect(lambda code, st, p=p: self._finished(p, code, st))
        p.errorOccurred.connect(lambda err, p=p: self._error(p, err))
        self._set_status("compilation…" if stage == "compile" else "en cours…", INFO)
        self.runningChanged.emit(True)
        p.start(program, args)

    def _read(self, p: QProcess, is_err: bool) -> None:
        try:
            data = p.readAllStandardError() if is_err else p.readAllStandardOutput()
        except RuntimeError:          # processus déjà détruit (fermeture de l'application)
            return
        self.append(bytes(data).decode("utf-8", "replace"), ERR if is_err else OUT)

    def _error(self, p: QProcess, err) -> None:
        if p is not self._proc or err != QProcess.FailedToStart:
            return
        reason = p.errorString()
        if any(k in reason.lower() for k in ("bloqu", "blocked", "stratégie", "strategie", "policy")):
            self.line("Windows a bloqué le lancement du programme compilé (stratégie de contrôle d'application / "
                      "Smart App Control). La compilation a réussi, mais ton PC refuse d'exécuter ce nouvel .exe.", BAD)
            self._proc = None
            self._blocked = True
            self._set_status("bloqué par Windows", BAD)
            self.runningChanged.emit(False)
            return
        if self._stage == "run" and self._exe and self._retries < 10 and not self._stopped:
            # l'exécutable vient d'être écrit : Windows (antivirus) peut le verrouiller un instant -> on réessaie
            self._retries += 1
            self._proc = None
            QTimer.singleShot(300, self._retry_exe)
            return
        self.line(f"Impossible de démarrer le programme ({p.errorString()}).", BAD)
        self._proc = None
        self._set_status("erreur", BAD)
        self.runningChanged.emit(False)

    def _retry_exe(self) -> None:
        if self._proc is None and not self._stopped:
            self._start(self._exe, [], "run", self.workdir())

    def _finished(self, p: QProcess, code: int, status) -> None:
        if p is not self._proc:
            return
        self._read(p, False)
        self._read(p, True)
        stage = self._stage
        dur = time.time() - self._t0
        if self._stopped:
            self.line("■ Arrêté", BAD)
            self._set_status("arrêté", BAD)
        elif stage == "compile":
            if code == 0:
                self.line("✓ Compilation réussie", OK)
                self._proc = None
                self._t0 = time.time()
                self._retries = 0
                self._start(self._exe, [], "run", self.workdir())
                return
            self.line(f"✗ Échec de la compilation (code {code})", BAD)
            self._set_status("échec compilation", BAD)
        else:
            ok = code == 0
            self.line(f"{'✓' if ok else '✗'} Terminé (code {code}) en {dur:.2f} s", OK if ok else BAD)
            self._set_status(f"terminé · code {code}", OK if ok else BAD)
        self._proc = None
        self.runningChanged.emit(False)

    def stop(self) -> None:
        p = self._proc
        if p is not None and p.state() != QProcess.NotRunning:
            self._stopped = True
            p.kill()
            p.waitForFinished(1500)

    # ----- saisie -----
    def _submit(self) -> None:
        text = self.input.text()
        self.input.clear()
        if self.is_running() and self._stage == "run":
            self.append(text + "\n", INFO)          # écho de ce qu'on envoie au programme
            self._proc.write((text + "\n").encode("utf-8"))
        elif text.strip():
            self.run_shell(text.strip())
