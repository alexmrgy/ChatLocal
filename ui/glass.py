"""Effet verre : fond flouté de la fenêtre + teinte sombre fidèle à la capture (#171717)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

TINT = QColor(23, 23, 23, 226)       # #171717 de la capture, très légèrement translucide
BORDER = QColor(255, 255, 255, 30)   # liseré ≈ #2c2c2c
RADIUS = 20


def blurred_backdrop(window: QWidget) -> QPixmap:
    """Capture de la fenêtre (calque verre masqué) puis flou par réductions/agrandissements lissés."""
    snap = window.grab()
    size = snap.size()
    small = snap.scaled(max(1, size.width() // 14), max(1, size.height() // 14),
                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    mid = small.scaled(max(1, size.width() // 5), max(1, size.height() // 5),
                       Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    blur = mid.scaled(size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    blur.setDevicePixelRatio(snap.devicePixelRatio())
    return blur


def paint_overlay(p: QPainter, widget_rect, card_rect, backdrop: QPixmap | None) -> None:
    """Voile léger sur l'app + carte en verre dépoli arrondie."""
    p.setRenderHint(QPainter.Antialiasing)
    p.fillRect(widget_rect, QColor(0, 0, 0, 80))
    r = QRectF(card_rect).adjusted(0.5, 0.5, -0.5, -0.5)
    path = QPainterPath()
    path.addRoundedRect(r, RADIUS, RADIUS)
    p.save()
    p.setClipPath(path)
    if backdrop is not None:
        p.drawPixmap(0, 0, backdrop)
    p.fillRect(r, TINT)
    p.restore()
    p.setPen(QPen(BORDER, 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r, RADIUS, RADIUS)
