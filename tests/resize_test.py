"""Test : largeur de l'historique réglable à la souris (ouverture, réglage, fermeture, mémorisation)."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_resize_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
win = MainWindow(db)
win.show()
hp, handle = win.history_panel, win.history_handle
fails = 0


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


_BASE = {}


def _send(kind, dx, button=Qt.LeftButton, buttons=Qt.LeftButton):
    local = QPointF(2, 100)   # la poignée suit le panneau : la position globale de départ est figée
    glob = _BASE["g"] + QPointF(dx, 0)
    ev = QMouseEvent(kind, local, glob, button, buttons, Qt.NoModifier)
    QApplication.sendEvent(handle, ev)


def drag(dx):
    """Glisse la poignée de dx pixels (événements souris envoyés directement à la poignée)."""
    _BASE["g"] = QPointF(handle.mapToGlobal(QPoint(2, 100)))
    _send(QEvent.MouseButtonPress, 0)
    for step in range(1, 9):
        _send(QEvent.MouseMove, dx * step // 8, Qt.NoButton)
        QCoreApplication.processEvents()
    _send(QEvent.MouseButtonRelease, dx, Qt.LeftButton, Qt.NoButton)
    pump(400)


pump(600)
win.toggle_history()
pump(500)
check("ouvert à la largeur par défaut", hp.is_open() and hp.maximumWidth() == hp.WIDTH)

drag(100)
check("élargi à la souris (+100)", hp.maximumWidth() == hp.WIDTH + 100 and hp.panel_width() == hp.WIDTH + 100)
check("largeur mémorisée en base", db.get_setting("history_width") == str(hp.WIDTH + 100))
win.grab().save(str(OUT / "shot_resize_wide.png"))

drag(-1000)
check("tiré trop loin : se ferme", not hp.is_open() and hp.maximumWidth() == 0)
check("bouton horloge décoché", not win.sidebar.history.isChecked())
check("la largeur choisie est conservée", hp.panel_width() == hp.WIDTH + 100)

drag(260)
check("rouvert en glissant depuis fermé", hp.is_open() and hp.maximumWidth() == 260)
check("nouvelle largeur mémorisée", db.get_setting("history_width") == "260")

drag(-100)
check("rétréci (-100)", hp.maximumWidth() == 200 and hp.panel_width() == 200)   # plafonné au minimum

QTest.mouseDClick(handle, Qt.LeftButton, Qt.NoModifier, QPoint(2, 100))
pump(300)
check("double-clic : largeur par défaut", hp.panel_width() == hp.WIDTH and hp.maximumWidth() == hp.WIDTH)

win.close()
db2 = Database(db.path)
win2 = MainWindow(db2)
check("largeur retrouvée au redémarrage", win2.history_panel.panel_width() == hp.WIDTH)
db2.set_setting("history_width", "333")
win3 = MainWindow(Database(db.path))
check("largeur personnalisée retrouvée au redémarrage", win3.history_panel.panel_width() == 333)
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
