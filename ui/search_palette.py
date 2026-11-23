"""Fenêtre de recherche (palette) : actions rapides + conversations, ouverture en fondu."""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QEvent, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .glass import blurred_backdrop, paint_overlay
from .icons import icon_pixmap

CARD_W, CARD_H = 560, 440
ACTIONS = [
    ("new", "Nouveau chat", "new_chat", "Ctrl+N"),
    ("folder", "Nouveau dossier", "folder_open", "Ctrl+O"),
]


class PaletteRow(QWidget):
    hovered = Signal()
    activated = Signal()

    def __init__(self, text: str, icon: str, badge: str = "", parent=None):
        super().__init__(parent)
        self._text, self._icon, self._badge, self.selected = text, icon, badge, False
        self.setFixedHeight(38)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        f = QFont(self.font())
        f.setPixelSize(15)
        self.setFont(f)

    def set_selected(self, on: bool) -> None:
        if on != self.selected:
            self.selected = on
            self.update()

    def enterEvent(self, e) -> None:
        self.hovered.emit()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.activated.emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(42, 42, 42))
            p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        color = theme.TEXT if self.selected else "#d4d4d4"
        p.drawPixmap(14, (self.height() - 18) // 2, icon_pixmap(self._icon, color, 18, self.devicePixelRatioF()))
        p.setPen(QColor(color))
        fm = p.fontMetrics()
        right = 16
        if self._badge:
            bw = fm.horizontalAdvance(self._badge) + 16
            r = QRectF(self.width() - right - bw, (self.height() - 22) / 2, bw, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(46, 46, 46))
            p.drawRoundedRect(r, 11, 11)
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(r, Qt.AlignCenter, self._badge)
            right += bw + 12
            p.setPen(QColor(color))
        txt = fm.elidedText(self._text, Qt.ElideRight, self.width() - 50 - right)
        p.drawText(48, 0, self.width() - 48, self.height(), Qt.AlignVCenter | Qt.AlignLeft, txt)


class SearchPalette(QWidget):
    newChat = Signal()
    newFolder = Signal()
    openConversation = Signal(int)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("PaletteOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()
        self._convs: list = []
        self._tab = 0
        self._rows: list[tuple[PaletteRow, tuple]] = []
        self._sel = 0
        self._closing = False
        self._backdrop: QPixmap | None = None

        self.card = QFrame(self, objectName="PaletteCard")
        v = QVBoxLayout(self.card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.edit = QLineEdit(objectName="PaletteEdit")
        self.edit.setPlaceholderText("Rechercher dans ChatLocal")
        self.edit.textChanged.connect(lambda _: self._rebuild())
        self.edit.installEventFilter(self)
        v.addWidget(self.edit)
        v.addWidget(self._line())

        self.scroll = QScrollArea(objectName="PaletteScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget(objectName="PaletteContent")
        self.col = QVBoxLayout(self.content)
        self.col.setContentsMargins(8, 6, 8, 6)
        self.col.setSpacing(0)
        self.scroll.setWidget(self.content)
        v.addWidget(self.scroll, 1)

        v.addWidget(self._line())
        tabs = QHBoxLayout()
        tabs.setContentsMargins(8, 6, 8, 8)
        tabs.setSpacing(4)
        grp = QButtonGroup(self)
        for i, name in enumerate(("Tout", "Actions", "Chats")):
            b = QPushButton(name, objectName="PaletteTab")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, i=i: self._set_tab(i))
            grp.addButton(b)
            tabs.addWidget(b)
        tabs.addStretch(1)
        v.addLayout(tabs)

        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QParallelAnimationGroup(self)
        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._slide = QPropertyAnimation(self.card, b"pos", self)
        for a in (self._fade, self._slide):
            a.setDuration(190)
            a.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.addAnimation(a)
        self._anim.finished.connect(self._anim_done)

    def _line(self) -> QFrame:
        ln = QFrame(objectName="PaletteLine")
        ln.setFixedHeight(1)
        return ln

    # ----- ouverture / fermeture douces -----
    def paintEvent(self, e) -> None:
        paint_overlay(QPainter(self), self.rect(), self.card.geometry(), self._backdrop)

    def open(self, convs) -> None:
        self._backdrop = blurred_backdrop(self.parentWidget()) if not self.isVisible() else self._backdrop
        self._convs = list(convs)
        self._closing = False
        self.edit.clear()
        self._tab = 0
        self.setGeometry(self.parentWidget().rect())
        self._layout_card()
        self._rebuild()
        self.show()
        self.raise_()
        self.edit.setFocus()
        self._run(True)

    def close_palette(self) -> None:
        if self.isVisible() and not self._closing:
            self._closing = True
            self._run(False)

    def _run(self, opening: bool) -> None:
        self._anim.stop()
        end = self.card.pos() if not opening else QPoint(self.card.x(), self._card_y())
        base = QPoint(end.x(), self._card_y())
        self._fade.setStartValue(self._fx.opacity())
        self._fade.setEndValue(1.0 if opening else 0.0)
        self._slide.setStartValue(base + QPoint(0, 14) if opening else self.card.pos())
        self._slide.setEndValue(base if opening else base + QPoint(0, 10))
        self._anim.start()

    def _anim_done(self) -> None:
        if self._closing:
            self.hide()
            self._closing = False
            self.parentWidget().setFocus()

    def _card_y(self) -> int:
        return max(20, (self.height() - self.card.height()) // 2)

    def _layout_card(self) -> None:
        w = min(CARD_W, self.width() - 48)
        h = min(CARD_H, self.height() - 100)
        self.card.setFixedSize(max(w, 300), max(h, 240))
        self.card.move((self.width() - self.card.width()) // 2, self._card_y())

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.isVisible() and not self._anim.state():
            self._layout_card()

    def mousePressEvent(self, e) -> None:
        if not self.card.geometry().contains(e.position().toPoint()):
            self.close_palette()

    # ----- contenu -----
    def _set_tab(self, i: int) -> None:
        self._tab = i
        self._rebuild()
        self.edit.setFocus()

    def _section(self, text: str) -> None:
        lb = QLabel(text, objectName="PaletteSection")
        self.col.addWidget(lb)

    def _rebuild(self) -> None:
        while self.col.count():
            it = self.col.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        self._rows = []
        q = self.edit.text().strip().lower()
        if self._tab in (0, 1):
            acts = [a for a in ACTIONS if q in a[1].lower()]
            if acts:
                self._section("Actions rapides")
                for key, label, icon, badge in acts:
                    self._add(PaletteRow(label, icon, badge), ("action", key))
        if self._tab in (0, 2):
            chats = [c for c in self._convs if q in c["title"].lower()][:60]
            if chats:
                self._section("Chats")
                for c in chats:
                    self._add(PaletteRow(c["title"], "chat"), ("chat", c["id"]))
        if not self._rows:
            lb = QLabel("Aucun résultat", objectName="PaletteEmpty")
            lb.setAlignment(Qt.AlignCenter)
            self.col.addWidget(lb)
        self.col.addStretch(1)
        self._select(0)

    def _add(self, row: PaletteRow, payload: tuple) -> None:
        i = len(self._rows)
        row.hovered.connect(lambda i=i: self._select(i, scroll=False))
        row.activated.connect(lambda i=i: self._activate(i))
        self._rows.append((row, payload))
        self.col.addWidget(row)

    def _select(self, i: int, scroll: bool = True) -> None:
        if not self._rows:
            return
        self._sel = max(0, min(i, len(self._rows) - 1))
        for j, (r, _) in enumerate(self._rows):
            r.set_selected(j == self._sel)
        if scroll:
            self.scroll.ensureWidgetVisible(self._rows[self._sel][0], 0, 40)

    def _activate(self, i: int | None = None) -> None:
        if not self._rows:
            return
        kind, val = self._rows[self._sel if i is None else i][1]
        self.close_palette()
        if kind == "action":
            sig = self.newChat if val == "new" else self.newFolder
            QTimer.singleShot(230, sig.emit)  # après la fermeture en fondu (capture de fond propre)
        else:
            self.openConversation.emit(val)

    def eventFilter(self, obj, ev) -> bool:
        if obj is self.edit:
            t = ev.type()
            if t == QEvent.ShortcutOverride and ev.key() == Qt.Key_Escape:
                ev.accept()
                return True
            if t == QEvent.KeyPress:
                k = ev.key()
                if k == Qt.Key_Escape:
                    self.close_palette()
                    return True
                if k == Qt.Key_Down:
                    self._select(self._sel + 1)
                    return True
                if k == Qt.Key_Up:
                    self._select(self._sel - 1)
                    return True
                if k in (Qt.Key_Return, Qt.Key_Enter):
                    self._activate()
                    return True
        return super().eventFilter(obj, ev)
