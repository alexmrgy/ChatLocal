"""Vue de conversation : messages, blocs de code, indicateur d'attente."""
from __future__ import annotations

import math
import textwrap
import time

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

from . import theme
from .icons import icon_pixmap
from .markdown_render import CODE_CSS, DOC_CSS, code_to_html, md_to_html, replace_code_segment, split_segments
from .action_menu import ActionMenu, MenuItem
from .input_bar import PromptEdit
from .widgets import AutoText, IconButton

COLUMN_MAX = 740
# liaisons avec la fenêtre principale (panneau de code à droite)
CODE_HOOKS: dict = {"open": None, "update": None, "link": None}


def _copy(text: str) -> None:
    QApplication.clipboard().setText(text)


class ThinkingIndicator(QWidget):
    """Attente de réponse : icône cerveau qui pulse + « Réflexion… 12 s » (secondes comptées)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setMinimumWidth(150)
        f = QFont(self.font())
        f.setPixelSize(15)
        self.setFont(f)
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=60, timeout=self.update)
        self._timer.start()

    def seconds(self) -> int:
        return int(time.monotonic() - self._t0)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        elapsed = time.monotonic() - self._t0
        p.setOpacity(0.55 + 0.45 * (0.5 + 0.5 * math.sin(elapsed * 4.0)))   # pulsation douce
        p.drawPixmap(0, (self.height() - 20) // 2, icon_pixmap("brain", theme.TEXT_DIM, 20, self.devicePixelRatioF()))
        p.setOpacity(1.0)
        p.setPen(QColor(theme.TEXT_MUTE))
        p.drawText(30, 0, self.width() - 30, self.height(), Qt.AlignVCenter | Qt.AlignLeft,
                   f"Réflexion… {self.seconds()} s")


def show_text_menu(tb: QTextBrowser, pos) -> None:
    """Menu contextuel d'un texte de discussion : Copier, Demander à Ollama, Tout sélectionner."""
    view = tb.parentWidget()
    while view is not None and not isinstance(view, ChatView):
        view = view.parentWidget()
    has = tb.textCursor().hasSelection()
    items = [
        MenuItem("Copier", "copy", enabled=has, callback=tb.copy),
        MenuItem("Demander à Ollama", "chat", enabled=has and view is not None,
                 callback=lambda: view.ask_from(tb)),
        MenuItem("Tout sélectionner", "list", callback=tb.selectAll),
    ]
    tb._menu = ActionMenu(items, tb)
    tb._menu.popup(pos)


class CodeView(QTextBrowser):
    """Code sans retour à la ligne : barre de défilement horizontale fine, hauteur = contenu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodeView")
        self.setFrameShape(QFrame.NoFrame)
        self.setLineWrapMode(QTextBrowser.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet(CODE_CSS)
        self.document().documentLayout().documentSizeChanged.connect(lambda _: self._fit())
        self.setFixedHeight(40)

    def _fit(self) -> None:
        doc = self.document()
        h = math.ceil(doc.size().height())
        bar = self.horizontalScrollBar()
        need_bar = math.ceil(doc.idealWidth()) > self.viewport().width()
        extra = (bar.sizeHint().height() + 6) if need_bar else 0
        if h + extra != self.height():
            self.setFixedHeight(max(h + extra, 1))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._fit()

    def contextMenuEvent(self, e) -> None:
        show_text_menu(self, e.globalPos())


class CodeBlock(QFrame):
    """Bloc de code façon ChatGPT : carte grise #393939, icône </> + langue, copie à droite."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CodeBlock")
        self._code = ""
        self._lang = None
        self._closed = None
        self.owner = None           # AssistantMessage qui contient ce bloc
        lay = QVBoxLayout(self)
        m = self.SHADOW
        lay.setContentsMargins(22 + m, 14 + m, 14 + m, 4 + m)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        self.icon = QLabel(objectName="CodeIcon")
        self.icon.setFixedSize(20, 20)
        self.icon.setPixmap(icon_pixmap("code", theme.TEXT, 18, self.devicePixelRatioF()))
        self.lang_label = QLabel(objectName="CodeLang")
        self.copy_btn = IconButton("copy", size=(34, 34), icon_size=18, radius=10, fg=theme.TEXT,
                                   fg_hover="#ffffff", bg_hover="#4a4a4a", tooltip="Copier le code")
        self.copy_btn.clicked.connect(self._on_copy)
        self.open_btn = IconButton("panel_open", size=(34, 34), icon_size=18, radius=10, fg=theme.TEXT,
                                   fg_hover="#ffffff", bg_hover="#4a4a4a", tooltip="Ouvrir sur la droite")
        self.open_btn.clicked.connect(self._open_panel)
        head.addWidget(self.icon)
        head.addWidget(self.lang_label)
        head.addStretch(1)
        head.addWidget(self.open_btn)
        head.addWidget(self.copy_btn)
        lay.addLayout(head)
        self.body = CodeView()
        lay.addWidget(self.body)

    SHADOW = 5   # marge réservée à l'ombre fine autour de la carte

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        m = self.SHADOW
        card = QRectF(self.rect()).adjusted(m, m, -m, -m)
        for i, alpha in enumerate((8, 14, 22, 34)):      # halo doux, du plus large au plus serré
            grow = 4 - i
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(card.adjusted(-grow, -grow + 1, grow, grow + 1), 16 + grow, 16 + grow)
        p.setBrush(QColor("#393939"))
        p.drawRoundedRect(card, 16, 16)

    def update_code(self, code: str, lang: str, closed: bool) -> None:
        if (code, lang, closed) == (self._code, self._lang, self._closed):
            return
        self._code, self._lang, self._closed = code, lang, closed
        self.lang_label.setText(lang or "code")
        self.body.setHtml(code_to_html(code, lang))
        fmt = QTextBlockFormat()
        fmt.setLineHeight(165, QTextBlockFormat.ProportionalHeight.value)
        cur = QTextCursor(self.body.document())
        cur.select(QTextCursor.Document)
        cur.mergeBlockFormat(fmt)
        if CODE_HOOKS["link"] is self and CODE_HOOKS["update"]:      # affiché à droite : mise à jour en direct
            CODE_HOOKS["update"](code, lang, closed)

    def code(self) -> str:
        return self._code

    def apply_edit(self, code: str) -> None:
        """Code modifié dans le panneau de droite : met à jour ce bloc, le message et la base."""
        if self.owner is not None:
            self.owner.replace_code(self, code)

    def lang(self) -> str:
        return self._lang or ""

    def is_closed(self) -> bool:
        return bool(self._closed)

    def line_count(self) -> int:
        return self._code.count("\n") + 1 if self._code else 0

    def _open_panel(self) -> None:
        if CODE_HOOKS["open"]:
            CODE_HOOKS["open"](self)

    def _on_copy(self) -> None:
        _copy(self._code)
        self.copy_btn.flash("check", theme.SUCCESS)


class TextBlock(AutoText):
    def __init__(self, parent=None):
        super().__init__(parent, css=DOC_CSS)
        self._src = None

    def update_text(self, text: str) -> None:
        if text != self._src:
            self._src = text
            self.setHtml(md_to_html(text))
            fmt = QTextBlockFormat()
            fmt.setLineHeight(150, QTextBlockFormat.ProportionalHeight.value)
            cur = QTextCursor(self.document())
            cur.select(QTextCursor.Document)
            cur.mergeBlockFormat(fmt)


class AssistantMessage(QWidget):
    contentEdited = Signal(str)          # texte Markdown complet après une modification de code

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(8)
        self._blocks: list[tuple[str, QWidget]] = []
        self._text = ""
        self._dots: ThinkingIndicator | None = ThinkingIndicator()
        self._lay.addWidget(self._dots)
        self._error: QLabel | None = None
        kw = dict(size=(34, 34), icon_size=18, radius=9, fg=theme.TEXT_DIM)
        self.copy_btn = IconButton("copy", tooltip="Copier la réponse", **kw)
        self.copy_btn.clicked.connect(self._on_copy)
        self._extra: list[IconButton] = []
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(2)
        for b in (self.copy_btn, *self._extra):
            b.hide()
            foot.addWidget(b)
        foot.addStretch(1)
        self._foot = foot
        self._lay.addLayout(foot)

    @property
    def text(self) -> str:
        return self._text

    def _drop_dots(self) -> None:
        if self._dots is not None:
            self._lay.removeWidget(self._dots)
            self._dots.hide()
            self._dots.deleteLater()
            self._dots = None

    def set_text(self, text: str) -> None:
        self._text = text
        if not text.strip():
            return
        self._drop_dots()
        segs = split_segments(text)
        for i, seg in enumerate(segs):
            if i < len(self._blocks) and self._blocks[i][0] != seg.kind:
                self._truncate(i)
            if i >= len(self._blocks):
                w: QWidget = TextBlock() if seg.kind == "text" else CodeBlock()
                if seg.kind == "code":
                    w.owner = self
                self._lay.insertWidget(self._lay.count() - 1, w)
                self._blocks.append((seg.kind, w))
            w = self._blocks[i][1]
            if seg.kind == "text":
                w.update_text(seg.content)
            else:
                w.update_code(seg.content, seg.lang, seg.closed)
        self._truncate(len(segs))

    def _truncate(self, n: int) -> None:
        while len(self._blocks) > n:
            _, w = self._blocks.pop()
            self._lay.removeWidget(w)
            w.hide()
            w.deleteLater()

    def replace_code(self, block, new_code: str) -> None:
        blocks = self.code_blocks()
        if block not in blocks:
            return
        new_text = replace_code_segment(self._text, blocks.index(block), new_code)
        if new_text is not None and new_text != self._text:
            self.set_text(new_text)
            self.contentEdited.emit(new_text)

    def code_blocks(self) -> list:
        return [w for kind, w in self._blocks if kind == "code"]

    def set_error(self, msg: str) -> None:
        self._drop_dots()
        if self._error is None:
            self._error = QLabel(wordWrap=True)
            self._error.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._lay.insertWidget(self._lay.count() - 1, self._error)
        self._error.setText(f'<span style="color:{theme.ERROR}">{msg}</span>')

    def finish(self) -> None:
        self._drop_dots()
        if self._text.strip():
            for b in (self.copy_btn, *self._extra):
                b.show()

    def _on_copy(self) -> None:
        _copy(self._text)
        self.copy_btn.flash("check", theme.SUCCESS)


class UserMessage(QWidget):
    """Message de l'utilisateur : bulle bleue + boutons copier / modifier ; édition sur place ;
    navigation entre les versions du prompt (‹ 1/2 ›) quand il a été modifié."""
    editSubmitted = Signal(str)
    versionRequested = Signal(int)   # -1 : version précédente, +1 : suivante

    def __init__(self, text: str, ver: int = 1, total: int = 1, locked: bool = False, quote: str = "", files: list | None = None,
                 parent=None):
        super().__init__(parent)
        self._text = text
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)

        # --- affichage normal ---
        self.show_box = QWidget()
        sv = QVBoxLayout(self.show_box)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(4)
        if quote:                                   # extrait sélectionné joint à ce message
            qrow = QHBoxLayout()
            qrow.setContentsMargins(0, 0, 0, 0)
            qrow.addStretch(1)
            card = QFrame(objectName="UserQuote")
            card.setMaximumWidth(380)
            ql = QVBoxLayout(card)
            ql.setContentsMargins(14, 10, 14, 10)
            ql.setSpacing(6)
            body = QLabel(textwrap.shorten(" ".join(quote.split()), width=150, placeholder="…"),
                          objectName="UserQuoteText")
            body.setWordWrap(True)
            ql.addWidget(body)
            head = QHBoxLayout()
            head.setSpacing(6)
            ic = QLabel()
            ic.setPixmap(icon_pixmap("chat", theme.TEXT_DIM, 15, self.devicePixelRatioF()))
            head.addWidget(ic)
            head.addWidget(QLabel("Sélection", objectName="UserQuoteHead"))
            head.addStretch(1)
            ql.addLayout(head)
            qrow.addWidget(card)
            sv.addLayout(qrow)
        for f in files or []:                       # fichiers joints à ce message
            frow = QHBoxLayout()
            frow.setContentsMargins(0, 0, 0, 0)
            frow.addStretch(1)
            card = QFrame(objectName="UserQuote")
            fl = QHBoxLayout(card)
            fl.setContentsMargins(12, 8, 14, 8)
            fl.setSpacing(8)
            ic = QLabel()
            ic.setPixmap(icon_pixmap("images" if f["kind"] == "image" else "pencil", theme.TEXT_DIM, 16,
                                     self.devicePixelRatioF()))
            fl.addWidget(ic)
            fl.addWidget(QLabel(textwrap.shorten(f["name"], width=40, placeholder="…"), objectName="UserQuoteHead"))
            frow.addWidget(card)
            sv.addLayout(frow)
        brow = QHBoxLayout()
        brow.setContentsMargins(0, 0, 0, 0)
        brow.addStretch(1)
        self.bubble = QFrame(objectName="UserBubble")
        bl = QVBoxLayout(self.bubble)
        bl.setContentsMargins(20, 13, 20, 13)
        self.view = AutoText(css="body { white-space: pre-wrap; }")
        self.view.setPlainText(text)
        bl.addWidget(self.view)
        self.bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        brow.addWidget(self.bubble)
        sv.addLayout(brow)
        self.footer = QWidget()
        self.footer.setFixedHeight(32)
        frow = QHBoxLayout(self.footer)
        frow.setContentsMargins(0, 0, 0, 0)
        frow.setSpacing(2)
        frow.addStretch(1)
        kw = dict(size=(32, 32), icon_size=17, radius=9, fg=theme.TEXT_MUTE, fg_hover=theme.TEXT)
        self.copy_btn = IconButton("copy", tooltip="Copier le message", **kw)
        self.copy_btn.clicked.connect(self._on_copy)
        self.edit_btn = IconButton("pencil", tooltip="Modifier le message", **kw)
        self.edit_btn.clicked.connect(self.start_edit)
        frow.addWidget(self.copy_btn)
        frow.addWidget(self.edit_btn)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2)
        bar.addStretch(1)
        self.nav = QWidget()                       # toujours visible dès qu'il existe plusieurs versions
        nl = QHBoxLayout(self.nav)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(0)
        nkw = dict(size=(26, 32), icon_size=14, radius=8, fg=theme.TEXT_MUTE, fg_hover=theme.TEXT)
        self.prev_btn = IconButton("arrow_left", tooltip="Version précédente", **nkw)
        self.next_btn = IconButton("arrow_right", tooltip="Version suivante", **nkw)
        self.ver_label = QLabel(objectName="VerLabel")
        self.prev_btn.clicked.connect(lambda: self.versionRequested.emit(-1))
        self.next_btn.clicked.connect(lambda: self.versionRequested.emit(1))
        nl.addWidget(self.prev_btn)
        nl.addWidget(self.ver_label)
        nl.addWidget(self.next_btn)
        bar.addWidget(self.nav)
        bar.addWidget(self.footer)
        sv.addLayout(bar)
        self.set_versions(ver, total)
        self.edit_btn.setVisible(not locked)   # chat verrouillé : lecture seule
        self._fx = QGraphicsOpacityEffect(self.footer)
        self._fx.setOpacity(0.0)
        self.footer.setGraphicsEffect(self._fx)
        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._fade.setDuration(130)
        self._lay.addWidget(self.show_box)

        # --- édition sur place ---
        self.edit_box = QFrame(objectName="EditBox")
        ev = QVBoxLayout(self.edit_box)
        ev.setContentsMargins(14, 6, 10, 8)
        ev.setSpacing(4)
        self.editor = PromptEdit()
        self.editor.submit.connect(self._submit_edit)
        self.editor.cancel.connect(self.cancel_edit)
        ev.addWidget(self.editor)
        erow = QHBoxLayout()
        erow.setSpacing(8)
        erow.addStretch(1)
        self.cancel_btn = QPushButton("Annuler", objectName="EditCancel")
        self.send_btn = QPushButton("Envoyer", objectName="EditSend")
        for b in (self.cancel_btn, self.send_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(30)
            erow.addWidget(b)
        self.cancel_btn.clicked.connect(self.cancel_edit)
        self.send_btn.clicked.connect(self._submit_edit)
        ev.addLayout(erow)
        self.edit_box.hide()
        self._lay.addWidget(self.edit_box)
        self.set_max_width(560)

    @property
    def text(self) -> str:
        return self._text

    def set_versions(self, ver: int, total: int) -> None:
        self.nav.setVisible(total > 1)
        self.ver_label.setText(f"{ver}/{total}")
        self.prev_btn.setEnabled(ver > 1)
        self.next_btn.setEnabled(ver < total)

    def _fade_to(self, value: float) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._fx.opacity())
        self._fade.setEndValue(value)
        self._fade.start()

    def enterEvent(self, e) -> None:
        self._fade_to(1.0)

    def leaveEvent(self, e) -> None:
        self._fade_to(0.0)

    def set_max_width(self, maxw: int) -> None:
        self.view.document().setTextWidth(-1)
        ideal = int(self.view.document().idealWidth()) + 4
        self.bubble.setFixedWidth(max(40, min(maxw, ideal + 40)))

    def _on_copy(self) -> None:
        _copy(self._text)
        self.copy_btn.flash("check", theme.SUCCESS)

    # ----- édition -----
    def start_edit(self) -> None:
        self.editor.setPlainText(self._text)
        self.show_box.hide()
        self.edit_box.show()
        self.editor.setFocus()
        c = self.editor.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.editor.setTextCursor(c)

    def cancel_edit(self) -> None:
        self.edit_box.hide()
        self.show_box.show()

    def _submit_edit(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self.edit_box.hide()
        self.show_box.show()
        if text != self._text:
            self.editSubmitted.emit(text)   # texte identique : rien à renvoyer


def _row(widget: QWidget) -> QWidget:
    row = QWidget()
    outer = QHBoxLayout(row)
    outer.setContentsMargins(24, 12, 24, 12)
    outer.addStretch(1)
    col = QWidget()
    col.setMaximumWidth(COLUMN_MAX)
    cl = QHBoxLayout(col)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.addWidget(widget)
    outer.addWidget(col, 1000)
    outer.addStretch(1)
    return row


class ScrollDownButton(IconButton):
    """Bouton rond « descendre en bas » (anneau fin autour de la flèche)."""

    def __init__(self, parent=None):
        super().__init__("arrow_down", size=(38, 38), icon_size=20, fg=theme.TEXT, fg_hover="#ffffff",
                         bg="#1f1f1f", bg_hover="#2b2b2b", tooltip="Aller en bas", parent=parent)

    def paintEvent(self, e) -> None:
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(255, 255, 255, 45))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))


class SelectionPill(QPushButton):
    """Pastille flottante affichée près d'un texte sélectionné : « Demander à … »."""

    def __init__(self, parent=None):
        super().__init__("Demander à Ollama", parent)
        self.setObjectName("AskPill")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(34)
        from PySide6.QtGui import QIcon
        self.setIcon(QIcon(icon_pixmap("chat", theme.TEXT_DIM, 16, self.devicePixelRatioF())))
        self.adjustSize()
        self.hide()


class ChatView(QScrollArea):
    quoteRequested = Signal(str)           # texte sélectionné à joindre au prochain message
    editSubmitted = Signal(int, str)       # (index dans l'historique, nouveau texte)
    versionRequested = Signal(int, int)    # (index dans l'historique, -1 / +1)
    assistantEdited = Signal(int, str)     # (index, nouveau texte) : code modifié dans le panneau de droite

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatView")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._inner = QWidget(objectName="ChatInner")
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 8, 0, 8)
        self._lay.setSpacing(0)
        self._lay.addStretch(1)
        self.setWidget(self._inner)
        self._rows: list[tuple[QWidget, int]] = []   # (ligne, index de l'historique)
        self.locked = False
        self._stick = True
        # sélection de texte -> pastille « Demander à … »
        self.pill = SelectionPill(self)
        self.pill.pressed.connect(self._ask_about_selection)   # dès l'appui : ne dépend pas du relâchement
        self._sel_tb = None
        self._sel_text = ""
        self._prog = False
        QApplication.instance().installEventFilter(self)
        sb = self.verticalScrollBar()
        sb.rangeChanged.connect(self._on_range)
        sb.valueChanged.connect(self._on_value)

        # bouton flottant « descendre » : visible dès qu'on est loin du bas de la discussion
        self._down_shown = False
        self.down_btn = ScrollDownButton(self)
        self.down_btn.clicked.connect(self.scroll_to_bottom)
        self._down_fx = QGraphicsOpacityEffect(self.down_btn)
        self._down_fx.setOpacity(0.0)
        self.down_btn.setGraphicsEffect(self._down_fx)
        self.down_btn.hide()
        self._down_anim = QPropertyAnimation(self._down_fx, b"opacity", self)
        self._down_anim.setDuration(160)
        self._down_anim.finished.connect(self._down_anim_done)
        self._scroll_anim = QPropertyAnimation(sb, b"value", self)
        self._scroll_anim.setDuration(280)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_anim.finished.connect(self._after_scroll)
        # défilement à la molette fluide : on accumule une cible et on glisse dessus
        self._wheel_target = None
        self._wheel_anim = QPropertyAnimation(sb, b"value", self)
        self._wheel_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._wheel_anim.setDuration(240)
        self._wheel_anim.finished.connect(lambda: setattr(self, "_wheel_target", None))

    DOWN_THRESHOLD = 120   # distance (px) au bas à partir de laquelle le bouton apparaît

    def _on_range(self, lo, hi) -> None:
        if self._stick:
            self._prog = True
            self.verticalScrollBar().setValue(hi)
            self._prog = False
        self._update_down()

    def _on_value(self, v) -> None:
        self._stick = v >= self.verticalScrollBar().maximum() - 30
        if not self._prog:           # seul un vrai défilement de l'utilisateur masque la pastille
            self.pill.hide()
        self._update_down()

    # ----- sélection de texte -----
    def eventFilter(self, obj, ev) -> bool:
        t = ev.type()
        if t == QEvent.MouseButtonPress:
            # on juge d'après le widget réellement sous le curseur (le filtre voit aussi la fenêtre mère)
            try:
                under = QApplication.widgetAt(ev.globalPosition().toPoint())
            except AttributeError:
                under = obj if isinstance(obj, QWidget) else None
            if under is not self.pill and not (under is not None and self.pill.isAncestorOf(under)):
                self.pill.hide()
        elif t == QEvent.MouseButtonRelease and isinstance(obj, QWidget) and ev.button() == Qt.LeftButton:
            tb = obj.parent()
            if isinstance(tb, QTextBrowser) and obj is tb.viewport() and self.isAncestorOf(tb) \
                    and tb.textCursor().hasSelection():
                gp = ev.globalPosition().toPoint()
                QTimer.singleShot(0, lambda tb=tb, gp=gp: self._show_pill(tb, gp))
        return False

    @staticmethod
    def selected_text(tb: QTextBrowser) -> str:
        return tb.textCursor().selectedText().replace("\u2029", "\n").replace("\u2028", "\n").strip()

    def _show_pill(self, tb: QTextBrowser, gp) -> None:
        try:
            ok = bool(self.selected_text(tb))
        except RuntimeError:           # widget supprimé entre-temps
            return
        if not ok:
            self.pill.hide()
            return
        self._sel_tb = tb
        self._sel_text = self.selected_text(tb)      # copie : l'appui sur la pastille ne doit pas la perdre
        pos = self.mapFromGlobal(gp)
        w, h = self.pill.width(), self.pill.height()
        x = max(8, min(pos.x() - w // 2, self.width() - w - 8))
        y = pos.y() - h - 14
        if y < 6:
            y = pos.y() + 20
        self.pill.move(x, y)
        self.pill.show()
        self.pill.raise_()

    def ask_from(self, tb: QTextBrowser) -> None:
        """Joint la sélection de `tb` au prochain message (clic droit ou pastille)."""
        self._sel_tb = tb
        self._ask_about_selection()

    def _ask_about_selection(self) -> None:
        tb, self._sel_tb = self._sel_tb, None
        saved, self._sel_text = self._sel_text, ""
        self.pill.hide()
        if tb is None:
            return
        text = ""
        try:
            text = self.selected_text(tb)
            c = tb.textCursor()
            c.clearSelection()
            tb.setTextCursor(c)
        except RuntimeError:
            pass
        text = text or saved
        if text:
            self.quoteRequested.emit(text)


    def _far_from_bottom(self) -> bool:
        sb = self.verticalScrollBar()
        return sb.maximum() - sb.value() > self.DOWN_THRESHOLD

    def _update_down(self) -> None:
        show = self._far_from_bottom() and self._scroll_anim.state() != QAbstractAnimation.Running
        if show == self._down_shown:
            return
        self._down_shown = show
        self._down_anim.stop()
        if show:
            self._place_down()
            self.down_btn.show()
            self.down_btn.raise_()
        self._down_anim.setStartValue(self._down_fx.opacity())
        self._down_anim.setEndValue(1.0 if show else 0.0)
        self._down_anim.start()

    def _down_anim_done(self) -> None:
        if self._down_fx.opacity() == 0.0:
            self.down_btn.hide()

    def _place_down(self) -> None:
        self.down_btn.move((self.width() - self.down_btn.width()) // 2, self.height() - self.down_btn.height() - 14)

    def wheelEvent(self, e) -> None:
        sb = self.verticalScrollBar()
        if e.modifiers() & Qt.ControlModifier:
            return super().wheelEvent(e)
        pix = e.pixelDelta().y()
        if pix:                      # pavé tactile : déjà fluide, on suit le doigt tel quel
            self._wheel_anim.stop()
            self._wheel_target = None
            sb.setValue(sb.value() - pix)
            e.accept()
            return
        dy = e.angleDelta().y()
        if not dy:
            return super().wheelEvent(e)
        self._scroll_anim.stop()
        base = self._wheel_target if self._wheel_target is not None else sb.value()
        target = max(sb.minimum(), min(sb.maximum(), base - dy * 1.1))
        self._wheel_target = target
        self._wheel_anim.stop()
        self._wheel_anim.setStartValue(sb.value())
        self._wheel_anim.setEndValue(int(target))
        self._wheel_anim.start()
        e.accept()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._place_down()

    def scroll_to_bottom(self) -> None:
        """Descend en douceur tout en bas, puis suit de nouveau le texte qui arrive."""
        sb = self.verticalScrollBar()
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(sb.value())
        self._scroll_anim.setEndValue(sb.maximum())
        self._scroll_anim.start()
        self._update_down()

    def _after_scroll(self) -> None:
        self._stick = True
        sb = self.verticalScrollBar()
        self._prog = True
        sb.setValue(sb.maximum())
        self._prog = False
        self._update_down()

    def clear(self) -> None:
        self.gen = getattr(self, "gen", 0) + 1
        while self._lay.count() > 1:
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        self._rows = []
        self._stick = True

    def truncate_from(self, index: int) -> None:
        """Retire les messages dont l'index d'historique est >= index (et tout ce qui suit)."""
        cut = next((i for i, (_, idx) in enumerate(self._rows) if idx >= index), len(self._rows))
        for row, _ in self._rows[cut:]:
            self._lay.removeWidget(row)
            row.hide()
            row.deleteLater()
        self._rows = self._rows[:cut]

    def begin_prepend(self) -> None:
        """Prépare l'ajout de messages plus anciens en tête : on retient la position d'une ligne visible."""
        self._anchor = None
        self.setUpdatesEnabled(False)
        vp = self.viewport()
        for row, _ in self._rows:
            y = row.mapTo(vp, QPoint(0, 0)).y()
            if y + row.height() > 0:
                self._anchor = (row, y)
                break
        self._front = True

    def end_prepend(self) -> None:
        """Termine l'ajout en tête et recale le défilement pour que rien ne bouge à l'écran."""
        self._front = False
        if self._anchor is not None:
            row, y0 = self._anchor
            self._lay.activate()
            y1 = row.mapTo(self.viewport(), QPoint(0, 0)).y()
            bar = self.verticalScrollBar()
            self._prog = True
            bar.setValue(bar.value() + (y1 - y0))
            self._prog = False
        self._anchor = None
        self.setUpdatesEnabled(True)

    def _add(self, row: QWidget, index: int, fade: bool = True) -> None:
        if getattr(self, "_front", False):          # message plus ancien : ajouté tout en haut
            self._lay.insertWidget(0, row)
            self._rows.insert(0, (row, index))
            return
        self._lay.insertWidget(self._lay.count() - 1, row)
        self._rows.append((row, index))
        if fade:
            eff = QGraphicsOpacityEffect(row)
            row.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", row)
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.finished.connect(lambda: row.setGraphicsEffect(None))
            anim.start()
        self._stick = True

    def add_user(self, text: str, index: int, ver: int = 1, total: int = 1, fade: bool = True,
                 quote: str = "", files: list | None = None) -> None:
        m = UserMessage(text, ver, total, self.locked, quote, files)
        m.editSubmitted.connect(lambda new, i=index: self.editSubmitted.emit(i, new))
        m.versionRequested.connect(lambda d, i=index: self.versionRequested.emit(i, d))
        self._add(_row(m), index, fade)

    def add_assistant(self, text: str = "", index: int = 0, fade: bool = True) -> AssistantMessage:
        m = AssistantMessage()
        m.contentEdited.connect(lambda txt, i=index: self.assistantEdited.emit(i, txt))
        if text:
            m.set_text(text)
            m.finish()
        self._add(_row(m), index, fade)
        return m
