"""Génère assets/app.ico (icône de l'application et de l'exécutable) : bulle de chat blanche sur fond bleu.

Usage : python scripts/make_icon.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from ui.icons import icon_pixmap  # noqa: E402

app = QGuiApplication([])
SIZE = 256
img = QImage(SIZE, SIZE, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)
p.setBrush(QColor("#4867be"))
p.drawRoundedRect(QRectF(0, 0, SIZE, SIZE), 56, 56)
pm = icon_pixmap("chat", "#ffffff", 150, 1.0)
p.drawPixmap((SIZE - 150) // 2, (SIZE - 150) // 2, pm)
p.end()
out = ROOT / "assets" / "app.ico"
ok = img.save(str(out), "ICO")
img.save(str(ROOT / "assets" / "app.png"), "PNG")
print("Icône enregistrée :" if ok else "Échec de l'enregistrement :", out)
os._exit(0 if ok else 1)
