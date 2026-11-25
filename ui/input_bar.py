"""Barre de saisie : +, champ, sélecteur de modèle, bouton d'action."""
from __future__ import annotations

import textwrap

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QKeyEvent, QPainter
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QTextEdit, QVBoxLayout, QWidget)

import attachments
from claude_api.client import DISPLAY_NAMES as CLAUDE_NAMES
from claude_api.client import PREFIX as CLAUDE_PREFIX
from nvidia.client import PREFIX as NVIDIA_PREFIX

from . import theme
from .icons import icon_pixmap
from .widgets import IconButton


class PromptEdit(QTextEdit):
    submit = Signal()
    cancel = Signal()
    MAX_H = 170

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PromptEdit")
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().documentLayout().documentSizeChanged.connect(lambda _: self._fit())
        self._fit()

    ROW_H = 32   # même hauteur que les boutons de la barre

    def _fit(self) -> None:
        doc = self.document()
        lh = self.fontMetrics().lineSpacing()
        margin = doc.documentMargin()
        lines = max(1, round((doc.size().height() - 2 * margin) / lh))
        want = max(2.0, (self.ROW_H - lh) / 2) if lines == 1 else 6.0   # 1 ligne : texte centré verticalement
        if abs(want - margin) > 0.1:
            doc.setDocumentMargin(want)
            margin = want
        h = max(self.ROW_H, min(self.MAX_H, int(lines * lh + 2 * margin)))
        if h != self.height():
            self.setFixedHeight(h)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn if h >= self.MAX_H else Qt.ScrollBarAlwaysOff)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._fit()   # recalcul une fois la police finale appliquée

    def event(self, e) -> bool:
        if e.type() == QEvent.ShortcutOverride and e.key() == Qt.Key_Escape and self.receivers("2cancel()") > 0:
            e.accept()   # Échap annule l'édition au lieu de déclencher « arrêter la génération »
            return True
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key_Escape and self.receivers("2cancel()") > 0:
            self.cancel.emit()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(e)


class FileChip(QFrame):
    """Pastille d'un fichier joint : icône, nom (raccourci) et croix pour le retirer."""
    removed = Signal()

    def __init__(self, name: str, kind: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FileChip")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 4, 4)
        h.setSpacing(6)
        ic = QLabel()
        ic.setPixmap(icon_pixmap("images" if kind == "image" else "pencil", theme.TEXT_DIM, 16, self.devicePixelRatioF()))
        h.addWidget(ic)
        h.addWidget(QLabel(textwrap.shorten(name, width=26, placeholder="…"), objectName="FileChipName"))
        close = IconButton("win_close", size=(22, 22), icon_size=11, radius=7, fg=theme.TEXT_MUTE, fg_hover=theme.TEXT,
                           tooltip="Retirer le fichier")
        close.clicked.connect(self.removed)
        h.addWidget(close)


class QuoteChip(QFrame):
    """Carte « Sélection » au-dessus du champ de saisie : aperçu du texte sélectionné + croix pour le retirer."""
    removed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("QuoteChip")
        self.setFixedWidth(300)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 10, 8)
        v.setSpacing(8)
        self.preview = QLabel(objectName="QuoteText")
        self.preview.setWordWrap(True)
        self.preview.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.preview.setMinimumHeight(48)
        v.addWidget(self.preview)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icon_pixmap("chat", theme.TEXT, 17, self.devicePixelRatioF()))
        bottom.addWidget(icon)
        bottom.addWidget(QLabel("Sélection", objectName="QuoteHead"))
        bottom.addStretch(1)
        close = IconButton("win_close", size=(26, 26), icon_size=13, radius=8, fg=theme.TEXT_MUTE, fg_hover=theme.TEXT,
                           tooltip="Retirer la sélection")
        close.clicked.connect(self.removed)
        bottom.addWidget(close)
        v.addLayout(bottom)

    def set_text(self, text: str) -> None:
        self.preview.setText(textwrap.shorten(" ".join(text.split()), width=170, placeholder="…"))


class InputBar(QFrame):
    submitted = Signal(str)
    stopRequested = Signal()
    modelChosen = Signal(str)
    refreshRequested = Signal()
    nvidiaKeyAdd = Signal()
    nvidiaKeyRemove = Signal()
    claudeKeyAdd = Signal()
    claudeKeyRemove = Signal()
    modelRenameRequested = Signal(str)   # identifiant complet du modèle à renommer
    modelDeleteRequested = Signal(str)   # identifiant complet du modèle Ollama à supprimer
    filesRejected = Signal(str)          # message d'erreur : fichier illisible ou trop gros

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InputBar")
        self._nvidia: list[str] = []
        self._claude: list[str] = []
        self._has_claude = False
        self._aliases: dict[str, str] = {}
        self._has_key = False
        self._models: list[str] = []
        self._running = False
        self._model = ""
        self._generating = False
        self._files: list[dict] = []
        self.setAcceptDrops(True)

        col = QVBoxLayout(self)
        col.setContentsMargins(8, 7, 8, 7)
        col.setSpacing(8)
        self.files_row = QWidget()
        self.files_lay = QHBoxLayout(self.files_row)
        self.files_lay.setContentsMargins(4, 0, 0, 0)
        self.files_lay.setSpacing(6)
        self.files_row.hide()
        col.addWidget(self.files_row, 0, Qt.AlignLeft)
        self.quote_chip = QuoteChip()
        self.quote_chip.removed.connect(self.clear_quote)
        self.quote_chip.hide()
        col.addWidget(self.quote_chip, 0, Qt.AlignLeft)
        self._quote = ""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        col.addLayout(row)

        self.plus = IconButton("plus", size=(30, 30), icon_size=20, fg=theme.TEXT, fg_hover="#ffffff",
                               bg_hover="#444444", tooltip="Joindre des fichiers")
        self.plus.clicked.connect(self.pick_files)
        self.edit = PromptEdit()
        self.edit.setPlaceholderText("Demander à Ollama")
        self.edit.submit.connect(self._on_submit)
        self.edit.textChanged.connect(self._sync_action)

        self.model_btn = QPushButton(objectName="ModelBtn")
        self.model_btn.setCursor(Qt.PointingHandCursor)
        self.model_btn.setFocusPolicy(Qt.NoFocus)
        self.model_btn.setLayoutDirection(Qt.RightToLeft)
        self.model_btn.setFixedHeight(32)
        self.model_btn.setIcon(QIcon(icon_pixmap("chevron_down", theme.TEXT_DIM, 14, self.devicePixelRatioF())))
        self.model_btn.clicked.connect(self._open_menu)

        self.action = IconButton("arrow_up", size=(32, 32), icon_size=19, fg="#181818", fg_hover="#181818",
                                 bg="#5a5a5a", bg_hover="#5a5a5a", tooltip="Envoyer (Entrée)")
        self.action.clicked.connect(self._on_action)

        # les boutons restent alignés en bas quand le champ grandit
        row.addWidget(self.plus, 0, Qt.AlignBottom)
        row.addWidget(self.edit, 1, Qt.AlignVCenter)
        row.addWidget(self.model_btn, 0, Qt.AlignBottom)
        row.addWidget(self.action, 0, Qt.AlignBottom)
        self.setMinimumHeight(46)
        self._refresh_model_text()

    # ----- état -----
    def set_models(self, models: list[str], running: bool, nvidia: list[str] | None = None,
                   has_key: bool = False, claude: list[str] | None = None, has_claude: bool = False) -> None:
        self._models, self._running = models, running
        self._nvidia, self._has_key = list(nvidia or []), has_key
        self._claude, self._has_claude = list(claude or []), has_claude
        self._refresh_model_text()

    def set_aliases(self, aliases: dict) -> None:
        self._aliases = dict(aliases)
        self._refresh_model_text()

    @staticmethod
    def default_name(full: str) -> str:
        if full.startswith(CLAUDE_PREFIX):
            real = full[len(CLAUDE_PREFIX):]
            return CLAUDE_NAMES.get(real, real)          # « Claude Sonnet 4.5 » plutôt que l'identifiant daté
        return full[len(NVIDIA_PREFIX):] if full.startswith(NVIDIA_PREFIX) else full

    def display_name(self, full: str) -> str:
        """Nom affiché : l'alias choisi par l'utilisateur, sinon le nom réel du modèle."""
        return self._aliases.get(full) or self.default_name(full)

    def set_model(self, name: str) -> None:
        self._model = name
        self._refresh_model_text()

    def model(self) -> str:
        return self._model

    # ----- extrait sélectionné (joint au prochain message) -----
    def set_quote(self, text: str) -> None:
        self._quote = text.strip()
        self.quote_chip.set_text(self._quote)
        self.quote_chip.setVisible(bool(self._quote))
        self._sync_action()
        self.edit.setFocus()

    def quote(self) -> str:
        return self._quote

    def clear_quote(self) -> None:
        self._quote = ""
        self.quote_chip.hide()
        self._sync_action()

    # ----- fichiers joints -----
    def files(self) -> list[dict]:
        return list(self._files)

    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Joindre des fichiers", "",
            "Tous les fichiers (*);;Texte et code (*.txt *.md *.py *.json *.csv *.html *.css *.js *.c *.cpp *.java *.log);;"
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)")
        self.add_paths(paths)

    def add_paths(self, paths) -> None:
        for p in paths:
            if len(self._files) >= attachments.MAX_FILES:
                self.filesRejected.emit(f"Maximum {attachments.MAX_FILES} fichiers par message.")
                break
            try:
                self._files.append(attachments.read_file(p))
            except (attachments.AttachmentError, OSError) as e:
                self.filesRejected.emit(str(e))
        self._refresh_files()
        self.edit.setFocus()

    def clear_files(self) -> None:
        self._files = []
        self._refresh_files()

    def _remove_file(self, i: int) -> None:
        if 0 <= i < len(self._files):
            del self._files[i]
            self._refresh_files()

    def _refresh_files(self) -> None:
        while self.files_lay.count():
            w = self.files_lay.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i, f in enumerate(self._files):
            chip = FileChip(f["name"], f["kind"])
            chip.removed.connect(lambda i=i: self._remove_file(i))
            self.files_lay.addWidget(chip)
        self.files_row.setVisible(bool(self._files))
        self._sync_action()

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
        e.acceptProposedAction()

    def set_locked(self, locked: bool) -> None:
        self.edit.setReadOnly(locked)
        self.edit.setPlaceholderText("Chat verrouillé : déverrouille-le pour écrire" if locked else "Demander à Ollama")

    def set_generating(self, on: bool) -> None:
        self._generating = on
        self._sync_action()

    def set_text(self, text: str) -> None:
        self.edit.setPlainText(text)
        c = self.edit.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.edit.setTextCursor(c)
        self.edit.setFocus()

    def focus_input(self) -> None:
        self.edit.setFocus()

    def _refresh_model_text(self) -> None:
        if self._model.startswith(NVIDIA_PREFIX):
            label, tip = self.display_name(self._model), "Modèle NVIDIA (API en ligne) : " + self.default_name(self._model)
        elif self._model.startswith(CLAUDE_PREFIX):
            label, tip = self.display_name(self._model), "Modèle Claude (API Anthropic) : " + self._model[len(CLAUDE_PREFIX):]
        elif not self._running and not self._nvidia and not self._claude:
            label, tip = "Ollama hors ligne", "Ollama ne répond pas sur localhost:11434"
        elif not self._models and not self._nvidia and not self._claude:
            label, tip = "Aucun modèle", "Aucun modèle installé (ollama pull ...)"
        else:
            label = self.display_name(self._model) if self._model else "Choisir"
            tip = "Modèle utilisé pour cette conversation" + (f" : {self._model}" if self._aliases.get(self._model) else "")
        fm = QFontMetrics(self.model_btn.font())
        self.model_btn.setText(fm.elidedText(label, Qt.ElideMiddle, 210))
        self.model_btn.setToolTip(tip)
        self.model_btn.adjustSize()

    def _sync_action(self) -> None:
        if self._generating:
            self.action.set_icon("stop")
            self.action.set_colors(fg="#181818", bg="#ececec")
            self.action._fg_hover = self.action._fg
            self.action._bg_hover = self.action._bg
            self.action.setToolTip("Arrêter la génération")
        elif self.edit.toPlainText().strip() or self._quote or self._files:
            self.action.set_icon("arrow_up")
            self.action.set_colors(fg="#181818", bg="#ececec")
            self.action._fg_hover = self.action._fg
            self.action._bg_hover = self.action._bg
            self.action.setToolTip("Envoyer (Entrée)")
        else:
            self.action.set_icon("arrow_up")      # champ vide : bouton d'envoi grisé
            self.action.set_colors(fg="#181818", bg="#5a5a5a")
            self.action._fg_hover = self.action._fg
            self.action._bg_hover = self.action._bg
            self.action.setToolTip("Envoyer (Entrée)")
        self.action.update()

    # ----- actions -----
    def _on_submit(self) -> None:
        if self._generating:
            return
        text = self.edit.toPlainText().strip()
        if not text and self._quote:
            text = "Explique cet extrait."          # carte « Sélection » seule : question par défaut
        elif not text and self._files:
            text = "Analyse le fichier joint." if len(self._files) == 1 else "Analyse les fichiers joints."
        if text:
            self.edit.clear()
            self.submitted.emit(text)

    def _on_action(self) -> None:
        if self._generating:
            self.stopRequested.emit()
        else:
            self._on_submit()

    def _open_menu(self) -> None:
        note = ""
        if not self._running and not self._has_key and not self._has_claude:
            note = "Ollama n'est pas lancé"
        elif self._running and not self._models and not self._has_key and not self._has_claude:
            note = "Aucun modèle installé"
        shown = self._models if self._running else []
        names = {m: self.display_name(m) for m in shown}
        names.update({NVIDIA_PREFIX + m: self.display_name(NVIDIA_PREFIX + m) for m in self._nvidia})
        names.update({CLAUDE_PREFIX + m: self.display_name(CLAUDE_PREFIX + m) for m in self._claude})
        popup = ModelPopup(shown, self._nvidia, self._model, note, self._has_key, self, names,
                           claude=self._claude, has_claude=self._has_claude)
        popup.addClaudeKey.connect(self.claudeKeyAdd)
        popup.removeClaudeKey.connect(self.claudeKeyRemove)
        popup.renameRequested.connect(self.modelRenameRequested)
        popup.deleteRequested.connect(self.modelDeleteRequested)
        popup.chosen.connect(self.modelChosen)
        popup.addKey.connect(self.nvidiaKeyAdd)
        popup.removeKey.connect(self.nvidiaKeyRemove)
        popup.adjustSize()
        btn = self.model_btn
        screen = btn.screen().availableGeometry()
        top_left = btn.mapToGlobal(QPoint(0, 0))
        x = max(screen.left() + 8, top_left.x() + btn.width() - popup.width())
        below = top_left.y() + btn.height() + 8
        y = below if below + popup.height() <= screen.bottom() else max(screen.top() + 8, top_left.y() - popup.height() - 8)
        popup.move(x, y)
        popup.setWindowOpacity(0.0)
        popup.show()
        anim = QVariantAnimation(popup)       # apparition douce : fondu + léger glissement
        anim.setDuration(230)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def step(t, x=x, y=y):
            popup.setWindowOpacity(t)
            popup.move(x, int(y + (8 if y < top_left.y() else -8) * (1.0 - t)))
        anim.valueChanged.connect(step)
        anim.start()
        self._popup = popup


class _ModelRow(QWidget):
    """Ligne du menu : modèle (coche à droite, crayon « renommer » au survol), titre de section ou action."""
    clicked = Signal()
    renameClicked = Signal()
    deleteClicked = Signal()

    def __init__(self, text: str, checked: bool = False, enabled: bool = True, kind: str = "item",
                 icon: str = "", rename: bool = False, tip: str = "", can_delete: bool = False, parent=None):
        super().__init__(parent)
        self._text, self._checked, self._hover, self._kind, self._icon = text, checked, False, kind, icon
        self._rename = rename
        self._can_delete = can_delete
        if tip:
            self.setToolTip(tip)
        self.setFixedHeight(24 if kind == "header" else 30)
        self.setEnabled(enabled and kind != "header")
        if self.isEnabled():
            self.setCursor(Qt.PointingHandCursor)
        f = QFont(self.font())
        f.setPixelSize(11 if kind == "header" else 13)
        f.setWeight(QFont.DemiBold if kind == "header" else QFont.Medium)
        self.setFont(f)
        pad = {"item": 48 + (28 if rename else 0) + (24 if can_delete else 0), "action": 64}.get(kind, 36)
        self.setMinimumWidth(min(420, QFontMetrics(f).horizontalAdvance(text) + pad))

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self.isEnabled() and e.button() == Qt.LeftButton:
            x = e.position().x()
            if self._can_delete and x >= self.width() - 30:
                self.deleteClicked.emit()      # clic sur la corbeille
            elif self._rename and x >= self.width() - (54 if self._can_delete else 34):
                self.renameClicked.emit()      # clic sur le crayon
            else:
                self.clicked.emit()

    def contextMenuEvent(self, e) -> None:
        if self._rename and self.isEnabled():
            self.renameClicked.emit()          # clic droit : renommer

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._hover and self.isEnabled():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 22))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        x = 10
        if self._kind == "header":
            p.setPen(QColor(theme.TEXT_MUTE))
        elif self._kind == "action":
            p.setPen(QColor(theme.TEXT_DIM if self.isEnabled() else theme.TEXT_MUTE))
            if self._icon:
                pm = icon_pixmap(self._icon, theme.TEXT_DIM, 15, self.devicePixelRatioF())
                p.drawPixmap(x, (self.height() - 15) // 2, pm)
                x += 24
        else:
            p.setPen(QColor(theme.TEXT if self.isEnabled() else theme.TEXT_MUTE))
        fm = p.fontMetrics()
        txt = fm.elidedText(self._text, Qt.ElideMiddle, self.width() - x - (32 if self._kind == "item" else 12) - (28 if self._rename else 0)
                           - (24 if self._can_delete else 0))
        p.drawText(x, 0, self.width() - x, self.height(), Qt.AlignVCenter | Qt.AlignLeft, txt)
        shift = (28 if self._rename else 0) + (24 if self._can_delete else 0)
        if self._checked:
            pm = icon_pixmap("check", theme.TEXT, 15, self.devicePixelRatioF())
            p.drawPixmap(self.width() - 10 - 15 - shift, (self.height() - 15) // 2, pm)
        if self._rename and self._hover:
            pm = icon_pixmap("pencil", theme.TEXT_DIM, 14, self.devicePixelRatioF())
            p.drawPixmap(self.width() - 10 - 14 - (24 if self._can_delete else 0), (self.height() - 14) // 2, pm)
        if self._can_delete and self._hover:
            pm = icon_pixmap("trash", theme.TEXT_DIM, 14, self.devicePixelRatioF())
            p.drawPixmap(self.width() - 10 - 14, (self.height() - 14) // 2, pm)


class ModelPopup(QWidget):
    """Choix du modèle : Ollama, NVIDIA (si clé) et gestion de la clé API NVIDIA."""
    chosen = Signal(str)
    addKey = Signal()
    removeKey = Signal()
    addClaudeKey = Signal()
    removeClaudeKey = Signal()
    renameRequested = Signal(str)
    deleteRequested = Signal(str)

    MAX_LIST_H = 360

    def __init__(self, ollama, nvidia, current, note, has_key, parent=None, names=None, claude=(), has_claude=False):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._names = names or {}
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QFrame(objectName="ModelPopupBody")
        outer.addWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(5, 5, 5, 5)
        v.setSpacing(0)

        self._rows = []        # (ligne, texte filtrable)
        self._sections = []    # (titre, lignes)
        self.search = None
        if len(ollama) + len(nvidia) + len(claude) > 8:
            self.search = QLineEdit(objectName="ModelSearch")
            self.search.setPlaceholderText("Rechercher un modèle")
            self.search.textChanged.connect(self._filter)
            v.addWidget(self.search)
            v.addSpacing(3)

        content = QWidget(objectName="ModelContent")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        if note:
            cl.addWidget(_ModelRow(note, enabled=False))
        multi = sum(1 for x in (bool(ollama), has_key, has_claude) if x) > 1
        self._add_section(cl, "Claude" if has_claude else "", claude, current, CLAUDE_PREFIX)
        self._add_section(cl, "Ollama" if multi else "", ollama, current, "")
        if has_key:
            if nvidia:
                self._add_section(cl, "NVIDIA", nvidia, current, NVIDIA_PREFIX)
            else:
                cl.addWidget(_ModelRow("NVIDIA : aucun modèle chargé", enabled=False))
        scroll = QScrollArea(objectName="ModelScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        h = content.sizeHint().height()
        scroll.setFixedHeight(min(h, self.MAX_LIST_H))
        scroll.setMinimumWidth(max(200, content.sizeHint().width() + (12 if h > self.MAX_LIST_H else 0)))
        v.addWidget(scroll)

        line = QFrame(objectName="ModelLine")
        line.setFixedHeight(1)
        v.addSpacing(3)
        v.addWidget(line)
        v.addSpacing(3)
        if has_claude:
            for text, icon, sig in (("Modifier la clé API Claude", "key", self.addClaudeKey),
                                    ("Déconnecter Claude", "trash", self.removeClaudeKey)):
                r = _ModelRow(text, kind="action", icon=icon)
                r.clicked.connect(lambda s=sig: (s.emit(), self.close()))
                v.addWidget(r)
        else:
            r = _ModelRow("Connecter Claude (clé API)", kind="action", icon="key")
            r.clicked.connect(lambda: (self.addClaudeKey.emit(), self.close()))
            v.addWidget(r)
        if has_key:
            for text, icon, sig in (("Modifier la clé API NVIDIA", "key", self.addKey),
                                    ("Supprimer la clé API NVIDIA", "trash", self.removeKey)):
                r = _ModelRow(text, kind="action", icon=icon)
                r.clicked.connect(lambda s=sig: (s.emit(), self.close()))
                v.addWidget(r)
        else:
            r = _ModelRow("Ajouter une clé API NVIDIA", kind="action", icon="key")
            r.clicked.connect(lambda: (self.addKey.emit(), self.close()))
            v.addWidget(r)

    def _add_section(self, layout, title, names, current, prefix):
        if not names:
            return
        header = _ModelRow(title, kind="header") if title else None
        if header:
            layout.addWidget(header)
        rows = []
        for n in names:
            full = prefix + n
            shown = self._names.get(full, n)
            local = not prefix     # seuls les modèles Ollama (installés sur le PC) peuvent être supprimés
            hint = "Clic droit ou crayon : renommer" + (" · corbeille : supprimer" if local else "")
            r = _ModelRow(shown, checked=(full == current), rename=True, can_delete=local,
                          tip=(f"{n}\n{hint}" if shown != n else hint))
            r.clicked.connect(lambda f=full: (self.chosen.emit(f), self.close()))
            r.renameClicked.connect(lambda f=full: (self.renameRequested.emit(f), self.close()))
            r.deleteClicked.connect(lambda f=full: (self.deleteRequested.emit(f), self.close()))
            layout.addWidget(r)
            rows.append(r)
            self._rows.append((r, f"{n} {shown}".lower()))
        if header:
            self._sections.append((header, rows))

    def _filter(self, text):
        q = text.strip().lower()
        for r, name in self._rows:
            r.setVisible(q in name)
        for header, rows in self._sections:
            header.setVisible(any(r.isVisible() for r in rows))
