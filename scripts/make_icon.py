"""Génère le logo : assets/app.ico (icône de l'application et de l'exécutable) et assets/logo.png.

Logo simple et plat : rectangle arrondi coupé en diagonale entre un orange chaud et un vert sauge,
avec un « C » blanc épais au centre.

Usage : python scripts/make_icon.py
"""
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

ORANGE = QColor("#D97757")
VERT = QColor("#10A37F")

app = QGuiApplication([])
S = 1024                      # dessiné en grand puis réduit : bords nets à toutes les tailles
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)

# rectangle arrondi
tile = QPainterPath()
tile.addRoundedRect(QRectF(0, 0, S, S), 200, 200)
p.setClipPath(tile)

# fond : moitié orange, moitié vert, coupure en diagonale
p.fillRect(0, 0, S, S, ORANGE)
green = QPainterPath()
green.moveTo(QPointF(S, 0))
green.lineTo(QPointF(S, S))
green.lineTo(QPointF(0, S))
green.closeSubpath()
p.setBrush(VERT)
p.drawPath(green)
p.setClipping(False)

# « C » blanc : gros arc ouvert à droite, bouts arrondis
pen = QPen(QColor("#FFFFFF"), 150)
pen.setCapStyle(Qt.RoundCap)
p.setPen(pen)
p.setBrush(Qt.NoBrush)
r = 236
p.drawArc(QRectF(S / 2 - r, S / 2 - r, 2 * r, 2 * r), 45 * 16, 270 * 16)
p.end()

assets = ROOT / "assets"
small = img.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
ok = small.save(str(assets / "app.ico"), "ICO")
small.save(str(assets / "logo.png"), "PNG")
img.scaled(512, 512, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(assets / "logo_512.png"), "PNG")
# change le paramètre ?v= du logo dans le README : GitHub et le navigateur rechargent la nouvelle image
readme = ROOT / "README.md"
if readme.exists():
    text = readme.read_text(encoding="utf-8")
    readme.write_text(re.sub(r"assets/logo_512\.png(\?v=\d+)?", f"assets/logo_512.png?v={int(time.time())}", text),
                      encoding="utf-8")
print("Logo enregistré :" if ok else "Échec :", assets / "app.ico")
os._exit(0 if ok else 1)
