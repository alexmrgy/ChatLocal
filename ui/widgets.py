"""Widgets réutilisables : bouton-icône animé, texte auto-dimensionné."""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QTextBrowser

from . import theme
from .icons import icon_pixmap


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class IconButton(QAbstractButton):
    """Bouton à icône SVG avec transition douce au survol."""

    def __init__(self, icon: str, size=(36, 36), icon_size=20, fg=theme.TEXT_DIM, fg_hover=theme.TEXT,
                 bg="transparent", bg_hover=theme.BG_HOVER, bg_checked=None, radius=None,
                 hover_ms=140, tooltip="", parent=None):
        super().__init__(parent)
        self._icon = icon
        self._icon_size = icon_size
        self._fg, self._fg_hover = QColor(fg), QColor(fg_hover)
        self._bg = QColor(0, 0, 0, 0) if bg == "transparent" else QColor(bg)
        self._bg_hover = QColor(bg_hover)
        self._bg_checked = QColor(bg_checked) if bg_checked else None
        self._radius = radius
        self._t = 0.0
        self._anim = QVariantAnimation(self, duration=hover_ms, startValue=0.0, endValue=1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.setFixedSize(*size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon(self, name: str) -> None:
        self._icon = name
        self.update()

    def flash(self, icon: str, color: str, ms: int = 1500) -> None:
        """Change brièvement icône + couleur (retour visuel de « Copier »)."""
        if getattr(self, "_orig", None) is None:
            self._orig = (self._icon, self._fg, self._fg_hover)
        self._icon, self._fg, self._fg_hover = icon, QColor(color), QColor(color)
        self.update()
        QTimer.singleShot(ms, self._unflash)

    def _unflash(self) -> None:
        if getattr(self, "_orig", None) is not None:
            self._icon, self._fg, self._fg_hover = self._orig
            self._orig = None
            self.update()

    def set_colors(self, fg=None, bg=None) -> None:
        if fg:
            self._fg = QColor(fg)
        if bg:
            self._bg = QColor(bg)
        self.update()

    def _on_anim(self, v) -> None:
        self._t = float(v)
        self.update()

    def _animate_to(self, end: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(end)
        self._anim.start()

    def enterEvent(self, e) -> None:
        self._animate_to(1.0)

    def leaveEvent(self, e) -> None:
        self._animate_to(0.0)

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = self._bg
        if self.isChecked() and self._bg_checked is not None:
            bg = self._bg_checked
        bg = _mix(bg, self._bg_hover, self._t) if not (self.isChecked() and self._bg_checked) else bg
        if bg.alpha() > 0:
            r = self._radius if self._radius is not None else min(self.width(), self.height()) / 2
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(self.rect()), r, r)
        color = _mix(self._fg, self._fg_hover, self._t)
        if not self.isEnabled():
            p.setOpacity(0.4)
        dpr = self.devicePixelRatioF()
        pm = icon_pixmap(self._icon, color, self._icon_size, dpr)
        s = self._icon_size
        p.drawPixmap(QPointF((self.width() - s) / 2, (self.height() - s) / 2), pm)


class AutoText(QTextBrowser):
    """Texte riche sans cadre ni barres, dont la hauteur suit le contenu."""

    def __init__(self, parent=None, css: str = ""):
        super().__init__(parent)
        self.setFrameShape(QTextBrowser.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background: transparent;")
        self.viewport().setCursor(Qt.IBeamCursor)
        self.document().setDocumentMargin(0)
        if css:
            self.document().setDefaultStyleSheet(css)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.setFixedHeight(20)

    def _fit(self, size) -> None:
        h = math.ceil(size.height())
        if h != self.height():
            self.setFixedHeight(max(h, 1))

    def contextMenuEvent(self, e) -> None:
        from .messages import show_text_menu     # import tardif : évite l'import circulaire
        show_text_menu(self, e.globalPos())

    def ideal_width(self) -> int:
        d = self.document()
        d.setTextWidth(-1)
        w = math.ceil(d.idealWidth())
        d.setTextWidth(self.viewport().width())
        return w
