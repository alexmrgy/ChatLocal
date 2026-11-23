"""Test : le survol d'un bouton disparaît même si Qt n'envoie pas l'événement « leave »."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication, QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QEnterEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.widgets import IconButton  # noqa: E402

app = QApplication([])
b = IconButton("home")
b.move(5000, 5000)          # loin du curseur
b.show()


def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


QApplication.sendEvent(b, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
pump(120)
hovered = b._t > 0
pump(500)                    # aucun « leave » n'est envoyé : le filet de sécurité doit retirer le survol
ok = hovered and b._t == 0.0
print(("OK   " if ok else "FAIL ") + "survol retiré sans événement leave")
os._exit(0 if ok else 1)
