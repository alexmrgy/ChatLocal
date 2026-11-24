"""Menu contextuel arrondi (icône, raccourci, action en rouge, sous-menu par glissement)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget

from . import theme
from .icons import icon_pixmap

DANGER = "#ff6b6b"


@dataclass
class MenuItem:
    text: str
    icon: str = ""
    shortcut: str = ""
    danger: bool = False
    callback: Callable[[], None] | None = None
    submenu: list | None = None          # liste de MenuItem / None (séparateur)
    enabled: bool = True
    dot: str = ""                      # pastille de couleur à la place de l'icône
    checked: bool = False


SEP = None


class _Row(QWidget):
    clicked = Signal()

    def __init__(self, item: MenuItem, back: bool = False, parent=None):
        super().__init__(parent)
        self.item, self._back, self._hover = item, back, False
        self.setFixedHeight(30)
        self.setEnabled(item.enabled)
        if item.enabled:
            self.setCursor(Qt.PointingHandCursor)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.Medium)
        self.setFont(f)
        w = QFontMetrics(f).horizontalAdvance(item.text) + 68
        if item.shortcut:
            w += QFontMetrics(f).horizontalAdvance(item.shortcut) + 28
        self.setMinimumWidth(w)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self.isEnabled() and e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        it = self.item
        if self._hover and self.isEnabled():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 107, 107, 34) if it.danger else QColor(255, 255, 255, 22))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        color = DANGER if it.danger else (theme.TEXT if self.isEnabled() else theme.TEXT_MUTE)
        x = 10
        icon = "chevron_left" if self._back else it.icon
        if it.dot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(it.dot))
            p.drawEllipse(QRectF(x + 3, (self.height() - 10) / 2, 10, 10))
        elif icon:
            p.drawPixmap(x, (self.height() - 16) // 2, icon_pixmap(icon, color, 16, self.devicePixelRatioF()))
        x = 34
        p.setPen(QColor(color))
        p.drawText(x, 0, self.width() - x - 10, self.height(), Qt.AlignVCenter | Qt.AlignLeft, it.text)
        if it.shortcut:
            f = QFont(self.font())
            f.setPixelSize(11)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(QColor(theme.TEXT_MUTE))
            p.drawText(0, 0, self.width() - 12, self.height(), Qt.AlignVCenter | Qt.AlignRight, it.shortcut)
        elif it.checked:
            p.drawPixmap(self.width() - 10 - 15, (self.height() - 15) // 2,
                         icon_pixmap("check", theme.TEXT, 15, self.devicePixelRatioF()))
        elif it.submenu is not None and not self._back:
            p.drawPixmap(self.width() - 10 - 15, (self.height() - 15) // 2,
                         icon_pixmap("chevron_right", theme.TEXT_MUTE, 15, self.devicePixelRatioF()))


class ActionMenu(QWidget):
    def __init__(self, items: list, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._root = items
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.body = QFrame(objectName="ActionMenuBody")
        outer.addWidget(self.body)
        self._lay = QVBoxLayout(self.body)
        self._lay.setContentsMargins(5, 5, 5, 5)
        self._lay.setSpacing(0)
        self._build(items)

    def _build(self, items: list, back_to: str = "") -> None:
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        if back_to:
            back = _Row(MenuItem(back_to), back=True)
            back.clicked.connect(lambda: (self._build(self._root), self._fit()))
            self._lay.addWidget(back)
            self._lay.addWidget(self._line())
        for it in items:
            if it is SEP:
                self._lay.addWidget(self._line())
                continue
            row = _Row(it)
            row.clicked.connect(lambda it=it: self._activate(it))
            self._lay.addWidget(row)

    def _line(self) -> QFrame:
        ln = QFrame(objectName="ActionMenuLine")
        ln.setFixedHeight(1)
        return ln

    def _fit(self) -> None:
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self._lay.activate()
        self.layout().activate()
        self.resize(self.sizeHint())        # se rétrécit aussi : adjustSize() gardait la hauteur du menu précédent
        self._keep_on_screen()

    def _keep_on_screen(self) -> None:
        if not self.isVisible():
            return
        screen = QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        g = screen.availableGeometry()
        y = min(self.y(), g.bottom() - self.height() - 8)
        x = min(self.x(), g.right() - self.width() - 8)
        self.move(max(g.left() + 8, x), max(g.top() + 8, y))

    def _activate(self, item: MenuItem) -> None:
        if item.submenu is not None:
            self._build(item.submenu, back_to=item.text)
            self._fit()
            return
        self.close()
        if item.callback:
            QTimer.singleShot(0, item.callback)   # après la fermeture du popup (les dialogues prennent le focus)

    def popup(self, pos: QPoint) -> None:
        self.resize(self.sizeHint())
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        g = screen.availableGeometry()
        x = min(max(g.left() + 8, pos.x()), g.right() - self.width() - 8)
        y = pos.y()
        if y + self.height() > g.bottom() - 8:
            y = max(g.top() + 8, g.bottom() - self.height() - 8)
        self.move(x, y)
        # apparition douce : fondu + léger glissement vers le bas
        self.setWindowOpacity(0.0)
        self.show()
        self._open_anim = QVariantAnimation(self)
        self._open_anim.setDuration(230)
        self._open_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._open_anim.setStartValue(0.0)
        self._open_anim.setEndValue(1.0)

        def step(t, x=x, y=y):
            self.setWindowOpacity(t)
            self.move(x, int(y - 8 * (1.0 - t)))
        self._open_anim.valueChanged.connect(step)
        self._open_anim.start()
