"""Génère le logo : assets/app.ico (icône de l'application et de l'exécutable) et assets/logo.png.

Logo simple : bulle de discussion blanche avec trois points, sur fond bleu arrondi.

Usage : python scripts/make_icon.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402

app = QGuiApplication([])
S = 256
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)

# fond : carré arrondi, dégradé bleu
grad = QLinearGradient(0, 0, S, S)
grad.setColorAt(0, QColor("#6f9bff"))
grad.setColorAt(1, QColor("#3a54c4"))
p.setBrush(grad)
p.drawRoundedRect(QRectF(0, 0, S, S), 58, 58)

# bulle blanche + queue en bas à gauche
bubble = QPainterPath()
bubble.addRoundedRect(QRectF(46, 56, 164, 116), 38, 38)
tail = QPainterPath()
tail.moveTo(QPointF(76, 160))
tail.lineTo(QPointF(70, 204))
tail.lineTo(QPointF(118, 168))
tail.closeSubpath()
p.setBrush(QColor("#ffffff"))
p.drawPath(bubble.united(tail))

# trois points
p.setBrush(QColor("#4a63c9"))
for cx in (88, 128, 168):
    p.drawEllipse(QPointF(cx, 114), 12, 12)
p.end()

assets = ROOT / "assets"
ok = img.save(str(assets / "app.ico"), "ICO")
img.save(str(assets / "logo.png"), "PNG")
(assets / "app.png").unlink(missing_ok=True)
print("Logo enregistré :" if ok else "Échec :", assets / "app.ico")
os._exit(0 if ok else 1)
