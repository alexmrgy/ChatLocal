"""Régénère docs/screenshot.png (capture de l'accueil, base de données temporaire).

Usage : python scripts/update_screenshot.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_shot_")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

app = QApplication([])
main.load_fonts(app)
main.load_style(app)
win = MainWindow(Database())
win.resize(1100, 700)
win.show()
app.processEvents()
out = ROOT / "docs" / "screenshot.png"
out.parent.mkdir(exist_ok=True)
win.grab().save(str(out))
print("Capture enregistrée :", out)
os._exit(0)
