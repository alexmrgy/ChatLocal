"""Panneau de code sur la droite : éditeur modifiable (enregistrement automatique), terminal et bouton lancer."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from . import theme
from .code_editor import CodeEditor
from .icons import icon_pixmap
from .terminal import Terminal, run_kind
from . import vscode
from .vscode import EXT, extension_for  # noqa: F401  (réexporté)
from .widgets import IconButton, Spinner

class CodePanel(QWidget):
    """Colonne de droite qui s'ouvre en glissant ; largeur réglable à la souris (poignée à gauche)."""
    openChanged = Signal(bool)
    widthChanged = Signal(int)
    codeEdited = Signal(str)       # code modifié par l'utilisateur (après 0,5 s sans frappe)
    roomNeeded = Signal()          # on tire plus large que la place disponible : libérer de la place (historique)

    WIDTH, MIN_W, MAX_W, COLLAPSE_W = 560, 340, 2000, 200
    CHAT_MIN = 340                 # largeur minimale gardée pour la discussion (le reste est à toi)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodePanel")
        self.setMaximumWidth(0)
        self._open = False
        self._width = self.WIDTH
        self._lang, self._closed = "", True
        self._loading = False
        self._last_text = ""
        self._editable = True
        self._drag_start = 0
        self.reserved_fn = None        # largeur déjà prise ailleurs (historique ouvert), fournie par la fenêtre
        self._anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._save_timer = QTimer(self, singleShot=True, interval=500)
        self._save_timer.timeout.connect(self._emit_save)       # 0,5 s sans frappe : enregistrement automatique

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame(objectName="CodeFrame")
        self.frame.setFixedWidth(self._width)
        outer.addWidget(self.frame, 1, Qt.AlignRight)
        v = QVBoxLayout(self.frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head_w = QFrame(objectName="PanelHead")
        head_w.setFixedHeight(46)
        head = QHBoxLayout(head_w)
        head.setContentsMargins(16, 0, 10, 0)
        head.setSpacing(8)
        self.lang_label = QLabel(objectName="PanelLang")
        head.addWidget(self.lang_label)
        self.count_label = QLabel(objectName="PanelCount")
        head.addWidget(self.count_label)
        self.save_label = QLabel(objectName="PanelSaved")
        head.addWidget(self.save_label)
        head.addStretch(1)
        self.vs_btn = QPushButton("Ouvrir l'éditeur de code", objectName="OpenEditorBtn")
        self.vs_btn.setCursor(Qt.PointingHandCursor)
        self.vs_btn.setFocusPolicy(Qt.NoFocus)
        self.vs_btn.setFixedHeight(26)
        self.vs_btn.clicked.connect(self._open_vscode)
        self._vs_path = None
        head.addWidget(self.vs_btn)
        self.spinner = Spinner(16, theme.TEXT_DIM)
        self.spinner.setToolTip("Le code s'écrit…")
        self.spinner.hide()
        head.addWidget(self.spinner)
        kw = dict(size=(30, 30), icon_size=16, radius=8, fg=theme.TEXT_DIM, fg_hover=theme.TEXT, bg_hover="#2a2d34")
        self.term_btn = IconButton("terminal", tooltip="Afficher / masquer le terminal", **kw)
        self.play_btn = IconButton("play", size=(30, 30), icon_size=15, radius=8, fg="#ffffff", fg_hover="#ffffff",
                                   bg="#2e8b57", bg_hover="#38a169", tooltip="Lancer (Ctrl+Entrée)")
        self.copy_btn = IconButton("copy", tooltip="Copier le code", **kw)
        self.save_btn = IconButton("download", tooltip="Enregistrer dans un fichier…", **kw)
        self.close_btn = IconButton("win_close", tooltip="Fermer", **kw)
        self.term_btn.clicked.connect(self.toggle_terminal)
        self.play_btn.clicked.connect(self._play)
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn.clicked.connect(self.save_as)
        self.close_btn.clicked.connect(self.close_panel)
        for b in (self.play_btn, self.term_btn, self.copy_btn, self.save_btn, self.close_btn):
            head.addWidget(b)
        v.addWidget(head_w)
        line = QFrame(objectName="PanelLine")
        line.setFixedHeight(1)
        v.addWidget(line)

        self.split = QSplitter(Qt.Vertical)
        self.split.setObjectName("CodeSplit")
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(7)
        self.editor = CodeEditor()
        self.view = self.editor          # alias (compatibilité)
        self.editor.textChanged.connect(self._on_text_changed)
        self.split.addWidget(self.editor)
        self.terminal = Terminal()
        self.terminal.runningChanged.connect(self._on_running)
        self.terminal.closeRequested.connect(self.hide_terminal)
        self.terminal.hide()
        self.split.addWidget(self.terminal)
        self.split.setStretchFactor(0, 3)
        self.split.setStretchFactor(1, 2)
        v.addWidget(self.split, 1)
        QShortcut(QKeySequence("Ctrl+Return"), self.editor, activated=self._play, context=Qt.WidgetShortcut)

    # ----- état -----
    def is_open(self) -> bool:
        return self._open

    def panel_width(self) -> int:
        return self._width

    def code(self) -> str:
        return self.editor.toPlainText()

    def _limit(self) -> int:
        """Largeur maximale : toujours laisser de la place à la discussion."""
        win = self.window()
        if win is None or win is self:
            return self.MAX_W
        reserved = self.reserved_fn() if self.reserved_fn else 0
        return max(self.MIN_W, min(self.MAX_W, win.width() - 52 - reserved - self.CHAT_MIN))

    def set_panel_width(self, w: int) -> None:
        self._width = max(self.MIN_W, min(self.MAX_W, int(w)))
        self.frame.setFixedWidth(self._width)
        if self._open:
            self.setMaximumWidth(self._width)

    def set_open(self, on: bool) -> None:
        if on == self._open and self.maximumWidth() == (self._width if on else 0):
            return
        self._open = on
        self._anim.stop()
        if on:
            self._width = min(self._width, self._limit())
            self.frame.setFixedWidth(self._width)
        else:
            self._flush_save()
            self.terminal.stop()
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(self._width if on else 0)
        self._anim.start()
        self.openChanged.emit(on)

    def close_panel(self) -> None:
        self.set_open(False)

    def cleanup(self) -> None:
        self._flush_save()
        self.terminal.cleanup()

    # ----- contenu -----
    def set_editable(self, on: bool) -> None:
        self._editable = on
        self._apply_readonly()

    def _apply_readonly(self) -> None:
        ro = not (self._editable and self._closed)       # pas de modification pendant que le code s'écrit
        self.editor.setReadOnly(ro)
        self.editor._highlight_line()
        self.spinner.setVisible(not self._closed)
        self.editor.setToolTip("Le code est en cours d'écriture…" if not self._closed else "")

    def open_code(self, code: str, lang: str, closed: bool = True, editable: bool = True) -> None:
        self._flush_save()
        self._editable = editable
        self._load(code, lang, closed)
        self.set_open(True)

    def update_code(self, code: str, lang: str, closed: bool) -> None:
        """Mise à jour venue de la discussion (code encore en cours d'écriture, ou modifié ailleurs)."""
        if code == self.code() and lang == self._lang and closed == self._closed:
            return
        if code == self.code():                     # même texte : on ne touche pas au curseur
            self._lang, self._closed = lang, closed
            self._apply_readonly()
            self._refresh_labels()
            return
        self._load(code, lang, closed)

    def _load(self, code: str, lang: str, closed: bool) -> None:
        sb = self.editor.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        value = sb.value()
        self._loading = True
        self._lang, self._closed = lang, closed
        if lang != self.editor._lang:
            self.editor.set_language(lang)
        self.editor.set_code(code)           # en direct : on ajoute seulement la fin, sans tout recharger
        self._last_text = self.editor.toPlainText()
        self._loading = False
        self._apply_readonly()
        self._refresh_labels()
        if not closed and at_bottom:
            sb.setValue(sb.maximum())
        else:
            sb.setValue(value)
        self.save_label.setText("")
        if self._vs_path is not None:
            vscode.write(self._vs_path, self.code())      # fichier VS Code suivi en direct

    def _refresh_labels(self) -> None:
        code = self.code()
        n = code.count("\n") + 1 if code else 0
        self.lang_label.setText(self._lang or "code")
        self.count_label.setText(f"{n} ligne{'s' if n > 1 else ''}" + ("" if self._closed else " · en cours…"))
        kind = run_kind(self._lang, code)
        self.play_btn.setEnabled(kind is not None or self.terminal.is_running())
        if not self.terminal.is_running():
            self.play_btn.setToolTip("Lancer (Ctrl+Entrée)" if kind else
                                     "Lancement disponible pour Python et C seulement")

    # ----- modification + enregistrement automatique -----
    def _on_text_changed(self) -> None:
        txt = self.code()
        if self._loading or txt == self._last_text:    # la coloration émet aussi « textChanged » : on l'ignore
            return
        self._last_text = txt
        self._refresh_labels()
        self.save_label.setText("· modification…")
        self._save_timer.start()

    def _flush_save(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._emit_save()

    def _emit_save(self) -> None:
        if self._vs_path is not None:
            vscode.write(self._vs_path, self.code())
        self.codeEdited.emit(self.code())
        self.save_label.setText("· enregistré ✓")

    # ----- terminal / lancement -----
    def hide_terminal(self) -> None:
        """Ferme le terminal (arrête le programme en cours) ; l'éditeur reprend toute la hauteur."""
        self.terminal.stop()
        self.terminal.hide()

    def toggle_terminal(self) -> None:
        if self.terminal.isVisible():
            self.hide_terminal()
            return
        self.terminal.show()
        if self.terminal.isVisible():
            self.split.setSizes([300, 220])
            self.terminal.input.setFocus()

    def _on_running(self, running: bool) -> None:
        self.play_btn.set_icon("stop" if running else "play")
        self.play_btn.set_colors(bg="#c0392b" if running else "#2e8b57")
        self.play_btn._bg_hover = self.play_btn._bg.lighter(115)
        self.play_btn.setToolTip("Arrêter" if running else "Lancer (Ctrl+Entrée)")
        self.play_btn.setEnabled(True if running else run_kind(self._lang, self.code()) is not None)

    def _play(self) -> None:
        if self.terminal.is_running():
            self.terminal.stop()
            return
        if run_kind(self._lang, self.code()) is None:
            return
        self._flush_save()                         # le code lancé = le code enregistré, sans fichier à choisir
        if not self.terminal.isVisible():
            self.toggle_terminal()
        self.terminal.run_code(self.code(), self._lang)

    # ----- actions -----
    def _open_vscode(self) -> None:
        self._flush_save()
        if self._vs_path is None:
            self._vs_path = vscode.new_path(self._lang)
        vscode.write(self._vs_path, self.code())
        vscode.open_in_vscode(self._vs_path)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.code())
        self.copy_btn.flash("check", theme.SUCCESS)

    def save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le code", f"code.{extension_for(self._lang)}",
                                              "Tous les fichiers (*)")
        if path:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.code())

    # ----- redimensionnement à la souris (poignée à gauche) -----
    def begin_drag(self) -> None:
        self._anim.stop()
        self._drag_start = self.maximumWidth()

    def drag_to(self, dx: int) -> None:
        """dx > 0 : élargit (la poignée est tirée vers la gauche)."""
        want = max(0, min(self.MAX_W, self._drag_start + dx))
        if want > self._limit():
            self.roomNeeded.emit()                 # ex. referme l'historique pour gagner de la place à gauche
        w = min(want, self._limit())
        self.setMaximumWidth(w)
        self.frame.setFixedWidth(max(w, self.MIN_W))

    def end_drag(self) -> None:
        w = self.maximumWidth()
        if w < self.COLLAPSE_W:
            self._open = False
            self._flush_save()
            self.terminal.stop()
            self._anim.setStartValue(w)
            self._anim.setEndValue(0)
            self._anim.start()
            self.openChanged.emit(False)
        else:
            self._width = max(self.MIN_W, min(self.MAX_W, w))
            self.setMaximumWidth(self._width)
            self.frame.setFixedWidth(self._width)
            self.widthChanged.emit(self._width)
