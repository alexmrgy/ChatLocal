"""Génère le logo : assets/app.ico (icône de l'application et de l'exécutable) et assets/logo.png.

Logo moderne : fond nuit avec halo lumineux, bulle de discussion en dégradé indigo → cyan,
et une étincelle (IA) en son centre.

Usage : python scripts/make_icon.py
"""
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath,  # noqa: E402
                           QPen, QRadialGradient)

app = QGuiApplication([])
S = 1024                      # dessiné en grand puis réduit : bords nets à toutes les tailles
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setRenderHint(QPainter.SmoothPixmapTransform)
p.setPen(Qt.NoPen)

# --- fond : carré arrondi nuit, halo violet en haut à gauche et cyan en bas à droite
base = QPainterPath()
base.addRoundedRect(QRectF(0, 0, S, S), 232, 232)
p.setClipPath(base)
bg = QLinearGradient(0, 0, S, S)
bg.setColorAt(0, QColor("#1d2147"))
bg.setColorAt(1, QColor("#0b0e22"))
p.fillRect(0, 0, S, S, bg)
for cx, cy, r, col in ((220, 160, 620, QColor(124, 92, 255, 120)), (860, 900, 640, QColor(34, 211, 238, 90))):
    g = QRadialGradient(cx, cy, r)
    g.setColorAt(0, col)
    g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
    p.fillRect(0, 0, S, S, QBrush(g))
p.setClipping(False)

# --- bulle : rectangle très arrondi + queue en bas à gauche
bubble = QPainterPath()
bubble.addRoundedRect(QRectF(176, 220, 672, 500), 190, 190)
tail = QPainterPath()
tail.moveTo(QPointF(300, 660))
tail.quadTo(QPointF(296, 790), QPointF(214, 836))
tail.quadTo(QPointF(386, 826), QPointF(480, 712))
tail.closeSubpath()
shape = bubble.united(tail)

# lueur derrière la bulle
glow = QRadialGradient(S / 2, 470, 520)
glow.setColorAt(0, QColor(110, 130, 255, 110))
glow.setColorAt(1, QColor(110, 130, 255, 0))
p.setBrush(QBrush(glow))
p.drawEllipse(QPointF(S / 2, 470), 520, 520)

fill = QLinearGradient(176, 220, 848, 836)
fill.setColorAt(0, QColor("#8b7bff"))
fill.setColorAt(0.55, QColor("#5b8cff"))
fill.setColorAt(1, QColor("#22d3ee"))
p.setBrush(QBrush(fill))
p.drawPath(shape)

# reflet léger en haut de la bulle
shine = QLinearGradient(0, 220, 0, 470)
shine.setColorAt(0, QColor(255, 255, 255, 80))
shine.setColorAt(1, QColor(255, 255, 255, 0))
p.setClipPath(shape)
p.setBrush(QBrush(shine))
p.drawRect(QRectF(176, 220, 672, 260))
p.setClipping(False)

# --- étincelle (étoile à 4 branches, côtés concaves) au centre de la bulle
def sparkle(cx: float, cy: float, r: float, pinch: float = 0.16) -> QPainterPath:
    path = QPainterPath()
    pts = [QPointF(cx + r * math.sin(a), cy - r * math.cos(a)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    path.moveTo(pts[0])
    for i in range(4):
        nxt = pts[(i + 1) % 4]
        mid = QPointF(cx + (pts[i].x() + nxt.x() - 2 * cx) * pinch, cy + (pts[i].y() + nxt.y() - 2 * cy) * pinch)
        path.quadTo(mid, nxt)
    path.closeSubpath()
    return path


p.setBrush(QColor("#ffffff"))
p.drawPath(sparkle(512, 470, 205))
p.drawPath(sparkle(668, 342, 62, 0.2))       # petite étincelle secondaire
p.setBrush(QColor(255, 255, 255, 215))
p.drawPath(sparkle(352, 578, 44, 0.2))
p.end()

assets = ROOT / "assets"
small = img.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
ok = small.save(str(assets / "app.ico"), "ICO")
small.save(str(assets / "logo.png"), "PNG")
img.scaled(512, 512, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(assets / "logo_512.png"), "PNG")
print("Logo enregistré :" if ok else "Échec :", assets / "app.ico")
os._exit(0 if ok else 1)
