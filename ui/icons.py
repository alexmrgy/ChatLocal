"""Chargement des icônes SVG, recolorées à la volée."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
_svg: dict[str, str] = {}
_px: dict[tuple, QPixmap] = {}


def icon_pixmap(name: str, color: str | QColor, size: int, dpr: float = 1.0) -> QPixmap:
    hexcolor = QColor(color).name()
    key = (name, hexcolor, size, round(dpr, 2))
    if key in _px:
        return _px[key]
    if name not in _svg:
        _svg[name] = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    data = QByteArray(_svg[name].replace("currentColor", hexcolor).encode("utf-8"))
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(data).render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    _px[key] = pm
    return pm
