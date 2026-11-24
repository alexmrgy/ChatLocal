"""Fenêtre de saisie en verre dépoli (création / renommage de dossier), ouverture en fondu."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (QEasingCurve, QEvent, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF, Qt,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme
from .glass import blurred_backdrop, paint_overlay
from .icons import icon_pixmap

CARD_W, CARD_H = 320, 222


class _Badge(QWidget):
    """Pastille arrondie avec icône (en-tête de la fenêtre)."""

    def __init__(self, icon: str, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._danger = False
        self.setFixedSize(38, 38)

    def set_icon(self, icon: str, danger: bool = False) -> None:
        self._icon, self._danger = icon, danger
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 107, 107, 44) if self._danger else QColor(42, 42, 42))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        pm = icon_pixmap(self._icon, "#ff6b6b" if self._danger else theme.TEXT, 20, self.devicePixelRatioF())
        p.drawPixmap((self.width() - 20) // 2, (self.height() - 20) // 2, pm)


class TextPrompt(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("PromptOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()
        self._backdrop = None
        self._closing = False
        self._callback: Callable[[str], None] | None = None

        self.card = QFrame(self, objectName="PromptCard")
        self.card.setFixedSize(CARD_W, CARD_H)
        v = QVBoxLayout(self.card)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(0)
        self.badge = _Badge("folder_open")
        v.addWidget(self.badge, 0, Qt.AlignHCenter)
        v.addSpacing(10)
        self.title = QLabel(objectName="PromptTitle")
        self.title.setAlignment(Qt.AlignCenter)
        v.addWidget(self.title)
        v.addSpacing(3)
        self.subtitle = QLabel(objectName="PromptSubtitle")
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setWordWrap(True)
        v.addWidget(self.subtitle)
        v.addSpacing(14)
        self.edit = QLineEdit(objectName="PromptEdit")
        self.edit.textChanged.connect(self._sync)
        self.edit.returnPressed.connect(self._submit)
        self.edit.installEventFilter(self)
        v.addWidget(self.edit)
        v.addStretch(1)
        v.addSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.cancel = QPushButton("Annuler", objectName="PromptCancel")
        self.ok = QPushButton(objectName="PromptOk")
        for b in (self.cancel, self.ok):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(32)
            row.addWidget(b, 1)
        self.cancel.clicked.connect(self.close_prompt)
        self.ok.clicked.connect(self._submit)
        v.addLayout(row)

        self._op = 0.0
        self._fx = QGraphicsOpacityEffect(self.card)
        self._fx.setOpacity(0.0)
        self.card.setGraphicsEffect(self._fx)
        self._anim = QParallelAnimationGroup(self)
        self._fade = QVariantAnimation(self)
        self._fade.valueChanged.connect(self._set_op)
        self._slide = QPropertyAnimation(self.card, b"pos", self)
        for a in (self._fade, self._slide):
            a.setDuration(240)
            a.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.addAnimation(a)
        self._anim.finished.connect(self._done)

    # ----- API -----
    def ask(self, title: str, subtitle: str, placeholder: str, initial: str, ok_label: str,
            callback: Callable[[str], None], icon: str = "folder_open", secret: bool = False) -> None:
        self._callback = callback
        self.edit.setEchoMode(QLineEdit.Password if secret else QLineEdit.Normal)
        self.edit.setMaxLength(300 if secret else 60)
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(initial)
        self.ok.setText(ok_label)
        self.badge.set_icon(icon)
        self._sync()
        self._closing = False
        if not self.isVisible():
            self._backdrop = blurred_backdrop(self.parentWidget())
        self.setGeometry(self.parentWidget().rect())
        self._place()
        self.show()
        self.raise_()
        self.edit.setFocus()
        self.edit.selectAll()
        self._run(True)

    def close_prompt(self) -> None:
        if self.isVisible() and not self._closing:
            self._closing = True
            self._run(False)

    # ----- interne -----
    def _sync(self) -> None:
        self.ok.setEnabled(bool(self.edit.text().strip()))

    def _submit(self) -> None:
        name = self.edit.text().strip()
        if not name or self._closing:
            return
        cb = self._callback
        self.close_prompt()
        if cb:
            cb(name)

    def _y(self) -> int:
        return max(20, (self.height() - self.card.height()) // 2)

    def _place(self) -> None:
        self.card.move((self.width() - self.card.width()) // 2, self._y())

    def _run(self, opening: bool) -> None:
        self._anim.stop()
        base = QPoint((self.width() - self.card.width()) // 2, self._y())
        self._fade.setStartValue(self._op)
        self._fade.setEndValue(1.0 if opening else 0.0)
        self._slide.setStartValue(base + QPoint(0, 14) if opening else self.card.pos())
        self._slide.setEndValue(base if opening else base + QPoint(0, 10))
        self._anim.start()

    def _done(self) -> None:
        if self._closing:
            self.hide()
            self._closing = False
            self.parentWidget().setFocus()

    def _set_op(self, v) -> None:
        self._op = float(v)
        self._fx.setOpacity(self._op)
        self.update()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setOpacity(self._op)
        paint_overlay(p, self.rect(), self.card.geometry(), self._backdrop)
        p.end()

    def mousePressEvent(self, e) -> None:
        if not self.card.geometry().contains(e.position().toPoint()):
            self.close_prompt()

    def eventFilter(self, obj, ev) -> bool:
        if obj is self.edit:
            if ev.type() == QEvent.ShortcutOverride and ev.key() == Qt.Key_Escape:
                ev.accept()
                return True
            if ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
                self.close_prompt()
                return True
        return super().eventFilter(obj, ev)


class _Check(QWidget):
    """Case à cocher arrondie avec libellé (« Ne plus me demander »)."""
    toggled = Signal(bool)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._text, self.checked, self._hover = text, False, False
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        f = QFont(self.font())
        f.setPixelSize(14)
        self.setFont(f)
        self.setFixedWidth(QFontMetrics(f).horizontalAdvance(text) + 40)

    def set_checked(self, on: bool) -> None:
        self.checked = on
        self.update()

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.set_checked(not self.checked)
            self.toggled.emit(self.checked)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, (self.height() - 20) / 2, 20, 20)
        if self.checked:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT))
            p.drawRoundedRect(box, 6, 6)
            p.drawPixmap(int(box.x() + 2), int(box.y() + 2), icon_pixmap("check", "#ffffff", 16, self.devicePixelRatioF()))
        else:
            p.setPen(QColor(120, 120, 120) if self._hover else QColor(85, 85, 85))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(30, 0, self.width() - 30, self.height(), Qt.AlignVCenter | Qt.AlignLeft, self._text)


class ConfirmDialog(TextPrompt):
    """Confirmation en verre dépoli (suppression…) avec « Ne plus me demander »."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.edit.hide()
        self.card.setFixedSize(330, 262)
        self.setFocusPolicy(Qt.StrongFocus)
        v = self.card.layout()
        self.check = _Check("Ne plus me demander")
        v.insertWidget(v.indexOf(self.edit), self.check, 0, Qt.AlignHCenter)
        self.ok.setProperty("danger", True)
        self._confirm_cb = None

    def ask_confirm(self, title: str, message: str, button: str, callback, icon: str = "trash",
                    danger: bool = True, skippable: bool = True) -> None:
        """callback(ne_plus_demander: bool) est appelé seulement si l'utilisateur confirme."""
        self._confirm_cb = callback
        self.title.setText(title)
        self.subtitle.setText(message)
        self.ok.setText(button)
        self.ok.setProperty("danger", danger)
        self.ok.style().unpolish(self.ok)
        self.ok.style().polish(self.ok)
        self.ok.setEnabled(True)
        self.badge.set_icon(icon, danger)
        self.check.set_checked(False)
        self.check.setVisible(skippable)   # suppression groupée : toujours confirmée
        self._closing = False
        if not self.isVisible():
            self._backdrop = blurred_backdrop(self.parentWidget())
        self.setGeometry(self.parentWidget().rect())
        self._place()
        self.show()
        self.raise_()
        self.setFocus()
        self._run(True)

    def _sync(self) -> None:
        pass

    def _submit(self) -> None:
        if self._closing:
            return
        cb, skip = self._confirm_cb, self.check.checked
        self.close_prompt()
        if cb:
            cb(skip)

    def event(self, e) -> bool:
        if e.type() == QEvent.ShortcutOverride and e.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            e.accept()          # Échap / Entrée appartiennent à la fenêtre (pas aux raccourcis de l'app)
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.close_prompt()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._submit()
        else:
            super().keyPressEvent(e)
