"""Barre supérieure du panneau principal + page d'accueil (titre, saisie, raccourcis)."""
from __future__ import annotations

import random

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from . import theme
from .icons import icon_pixmap
from .widgets import IconButton

HOME_COLUMN = 640

GREETINGS = [
    "Comment puis-je vous aider ?",
    "Par quoi commençons-nous ?",
    "Que voulez-vous faire aujourd'hui ?",
    "Une question ? Je vous écoute.",
    "Sur quoi travaillons-nous ?",
    "Prêt quand vous l'êtes.",
    "Quoi de neuf ?",
    "Qu'avez-vous en tête ?",
    "Dites-moi tout.",
    "Un projet, une idée, un doute ?",
]

SHORTCUTS = [
    ("image_plus", "Créer une image ou un sticker", "Décris en détail l'image ou le sticker à créer : "),
    ("pencil", "Écrire ou modifier", "Aide-moi à écrire ou à modifier ce texte : "),
]


def centered_slot(max_w: int, margins=(24, 0, 24, 0)) -> tuple[QWidget, QVBoxLayout]:
    """Conteneur horizontal centré dont la colonne plafonne à max_w ; renvoie (widget, layout de la colonne)."""
    outer = QWidget()
    h = QHBoxLayout(outer)
    h.setContentsMargins(*margins)
    h.addStretch(1)
    col = QWidget()
    col.setMaximumWidth(max_w)
    v = QVBoxLayout(col)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    h.addWidget(col, 1000)
    h.addStretch(1)
    return outer, v


class TopBar(QWidget):
    ephemeralClicked = Signal()
    newChatClicked = Signal()
    titleClicked = Signal(QPoint)   # position globale sous le titre

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setFixedHeight(54)
        g = QGridLayout(self)
        g.setContentsMargins(16, 10, 16, 0)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(2, 1)
        g.setAlignment(Qt.AlignTop)

        left = QWidget()
        ll = QHBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        self.new_btn = IconButton("new_chat", size=(34, 34), icon_size=19, radius=11, fg=theme.TEXT_DIM,
                                  tooltip="Nouveau chat (Ctrl+N)")
        self.new_btn.clicked.connect(self.newChatClicked)
        self.title_btn = QPushButton(objectName="TitleBtn")
        self.title_btn.setCursor(Qt.PointingHandCursor)
        self.title_btn.setFocusPolicy(Qt.NoFocus)
        self.title_btn.setLayoutDirection(Qt.RightToLeft)
        self.title_btn.setFixedHeight(34)
        self.title_btn.setIcon(QIcon(icon_pixmap("chevron_down", theme.TEXT_DIM, 14, self.devicePixelRatioF())))
        self.title_btn.clicked.connect(lambda: self.titleClicked.emit(
            self.title_btn.mapToGlobal(QPoint(0, self.title_btn.height() + 6))))
        ll.addWidget(self.new_btn)
        ll.addWidget(self.title_btn)
        left.hide()
        self._left = left
        g.addWidget(left, 0, 0, Qt.AlignLeft)


        self.temp_btn = IconButton("tempchat", size=(34, 34), icon_size=20, radius=11, bg_checked=theme.BG_ACTIVE,
                                   fg=theme.TEXT_DIM, tooltip="Chat éphémère (Ctrl+Maj+N)")
        self.temp_btn.setCheckable(True)
        self.temp_btn.clicked.connect(self.ephemeralClicked)
        g.addWidget(self.temp_btn, 0, 2, Qt.AlignRight)


    def set_conversation(self, in_chat: bool, title: str | None) -> None:
        """Bouton « nouveau chat » dans une conversation ; titre cliquable si elle est enregistrée."""
        self._left.setVisible(in_chat)
        self.title_btn.setVisible(bool(title))
        if title:
            fm = QFontMetrics(self.title_btn.font())
            self.title_btn.setText(fm.elidedText(title, Qt.ElideRight, 420))
            self.title_btn.setToolTip(title)

    def set_ephemeral(self, on: bool) -> None:
        self.temp_btn.setChecked(on)
        self.temp_btn.update()



class HomePage(QWidget):
    shortcutClicked = Signal(str)

    def set_ephemeral(self, on: bool) -> None:
        self._ephemeral = on
        self.heading.setText("Chat éphémère" if on else self._greeting)
        self.subtitle.setText("Cette conversation n'apparaîtra pas dans ton historique et ne sera pas enregistrée."
                              if on else "")
        self.subtitle.setVisible(on)

    def _new_greeting(self) -> None:
        """Tire une nouvelle phrase d'accueil, différente de la précédente."""
        self._greeting = random.choice([g for g in GREETINGS if g != self._greeting] or GREETINGS)
        if not self._ephemeral:
            self.heading.setText(self._greeting)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._new_greeting()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ephemeral = False
        self._greeting = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addStretch(8)
        self.heading = QLabel(random.choice(GREETINGS), objectName="Heading")
        self.heading.setAlignment(Qt.AlignCenter)
        v.addWidget(self.heading)
        self.subtitle = QLabel(objectName="HeadingSub")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.setContentsMargins(40, 0, 40, 0)
        self.subtitle.hide()
        v.addSpacing(8)
        v.addWidget(self.subtitle)
        v.addSpacing(18)
        self.input_slot_widget, self.input_slot = centered_slot(HOME_COLUMN)
        v.addWidget(self.input_slot_widget)
        v.addSpacing(14)

        sc_outer, sc = centered_slot(HOME_COLUMN)
        for icon, label, prompt in SHORTCUTS:
            b = QPushButton(label, objectName="Shortcut")
            b.setIcon(QIcon(icon_pixmap(icon, theme.TEXT_MUTE, 18, self.devicePixelRatioF())))
            b.setIconSize(QSize(18, 18))
            b.setFixedHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, p=prompt: self.shortcutClicked.emit(p))
            sc.addWidget(b, 0, Qt.AlignLeft)
        v.addWidget(sc_outer)
        v.addStretch(12)
