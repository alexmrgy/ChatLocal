"""Barre de titre personnalisée : navigation, menus, contrôles de fenêtre."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMenu, QPushButton, QWidget

from . import theme
from .widgets import IconButton

TITLE_H = 38


def make_menu(parent) -> QMenu:
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    m.setAttribute(Qt.WA_TranslucentBackground)
    return m


class TitleBar(QWidget):
    backClicked = Signal()
    forwardClicked = Signal()
    sidebarClicked = Signal()
    minimizeClicked = Signal()
    maximizeClicked = Signal()
    closeClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLE_H)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 0, 0)
        row.setSpacing(2)

        kw = dict(size=(30, 30), icon_size=18, radius=8)
        self.back = IconButton("arrow_left", tooltip="Précédent", **kw)
        self.forward = IconButton("arrow_right", tooltip="Suivant", **kw)
        self.toggle = IconButton("sidebar", tooltip="Historique des conversations", **kw)
        self.back.clicked.connect(self.backClicked)
        self.forward.clicked.connect(self.forwardClicked)
        self.toggle.clicked.connect(self.sidebarClicked)
        row.addWidget(self.back)
        row.addWidget(self.forward)
        row.addSpacing(6)
        row.addWidget(self.toggle)
        row.addSpacing(14)

        self._menus: dict[str, QMenu] = {}
        self._menu_buttons: dict[str, QPushButton] = {}
        self._menu_row = row

        row.addStretch(1)
        wk = dict(size=(46, TITLE_H), icon_size=16, radius=0, fg=theme.TEXT_DIM, fg_hover=theme.TEXT)
        self.btn_min = IconButton("win_min", tooltip="", **wk)
        self.btn_max = IconButton("win_max", **wk)
        self.btn_close = IconButton("win_close", bg_hover="#c42b1c", **wk)
        self.btn_close._fg_hover = self.btn_close._fg_hover.__class__("#ffffff")
        self.btn_min.clicked.connect(self.minimizeClicked)
        self.btn_max.clicked.connect(self.maximizeClicked)
        self.btn_close.clicked.connect(self.closeClicked)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            row.addWidget(b)

    def add_menu(self, title: str, menu: QMenu) -> None:
        btn = QPushButton(title, objectName="MenuBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.clicked.connect(lambda: self._open_menu(btn, menu))
        idx = self._menu_row.count() - 4  # avant le stretch et les 3 boutons
        self._menu_row.insertWidget(idx, btn)
        self._menus[title] = menu
        self._menu_buttons[title] = btn

    @staticmethod
    def _open_menu(btn: QPushButton, menu: QMenu) -> None:
        menu.exec(btn.mapToGlobal(QPoint(0, btn.height() + 2)))
        # après la fermeture du menu Qt garde le survol : on le retire si la souris est ailleurs
        if not btn.rect().contains(btn.mapFromGlobal(QCursor.pos())):
            QApplication.sendEvent(btn, QEvent(QEvent.Leave))
            btn.update()

    def set_maximized(self, maximized: bool) -> None:
        self.btn_max.set_icon("win_restore" if maximized else "win_max")
