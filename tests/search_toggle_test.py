"""Test : Ctrl+K ouvre la recherche, un 2e appui la referme."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_search_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
win = mw.MainWindow(Database())
win.show()
win.activateWindow()
fails = 0


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def press(key):
    QTest.keyClick(app.focusWidget() or win, key, Qt.ControlModifier)
    pump(600)


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


pump(500)
win.input.focus_input()
press(Qt.Key_K)
check("Ctrl+K ouvre la recherche", win.palette.isVisible())
press(Qt.Key_K)
check("2e Ctrl+K la referme", not win.palette.isVisible())
press(Qt.Key_K)
check("3e Ctrl+K la rouvre", win.palette.isVisible())
press(Qt.Key_F)
check("Ctrl+F la referme aussi", not win.palette.isVisible())

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
