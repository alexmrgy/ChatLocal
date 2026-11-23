"""Test : sélection multiple dans l'historique (Ctrl / Maj + clic), puis archivage ou suppression groupés."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_sel_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, Qt, QPoint  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.sidebar import NavRow  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
ids = [db.create_conversation(f"Discussion {i}", "m") for i in range(1, 7)]
win = mw.MainWindow(db)
win.show()
fails = 0


def pump(ms, until=None):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.01)
        if until and until():
            return True
    return until() if until else True


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


def rows():
    return [r for r in win.history_panel.findChildren(NavRow) if r._actions]


def click(title, mods=Qt.NoModifier):
    r = next(r for r in rows() if r._text == title)
    QTest.mouseClick(r, Qt.LeftButton, mods, QPoint(40, 17))
    pump(150)


pump(500)
win.history_panel.set_open(True)
pump(500)
hp = win.history_panel
check("6 conversations listées", len(rows()) == 6)

# Ctrl + clic : sélection multiple, rien n'est ouvert
click("Discussion 6", Qt.ControlModifier)
click("Discussion 4", Qt.ControlModifier)
check("Ctrl + clic sélectionne sans ouvrir", set(hp.selected_ids()) == {ids[5], ids[3]} and win.cid is None)
check("barre d'actions affichée", hp.sel_bar.isVisible() and "2 sélectionnées" in hp.sel_label.text())
win.grab().save(str(OUT / "shot_history_select.png"))

# Ctrl + clic de nouveau : retire
click("Discussion 4", Qt.ControlModifier)
check("Ctrl + clic retire de la sélection", hp.selected_ids() == [ids[5]])

# Maj + clic : plage
click("Discussion 6", Qt.ControlModifier)      # retire 6 -> sélection vide
check("sélection vidée : barre masquée", not hp.sel_bar.isVisible())
click("Discussion 5", Qt.ControlModifier)      # ancre sur la ligne 5
click("Discussion 3", Qt.ShiftModifier)
check("Maj + clic sélectionne la plage", set(hp.selected_ids()) == {ids[4], ids[3], ids[2]})

# Échap annule
QTest.keyClick(hp, Qt.Key_Escape)
pump(150)
check("Échap annule la sélection", hp.selected_ids() == [] and not hp.sel_bar.isVisible())

# clic simple avec sélection : annule puis ouvre
click("Discussion 2", Qt.ControlModifier)
click("Discussion 1")
check("clic simple annule la sélection et ouvre", hp.selected_ids() == [] and win.cid == ids[0])

# archivage groupé
click("Discussion 2", Qt.ControlModifier)
click("Discussion 3", Qt.ControlModifier)
QTest.mouseClick(hp.sel_archive, Qt.LeftButton)
pump(400)
arch = {r["id"] for r in db.list_conversations() if r["archived"]}
check("archivage groupé", arch == {ids[1], ids[2]})
check("sélection vidée après archivage", hp.selected_ids() == [] and not hp.sel_bar.isVisible())

# suppression groupée (avec confirmation)
click("Discussion 5", Qt.ControlModifier)
click("Discussion 6", Qt.ControlModifier)
QTest.mouseClick(hp.sel_delete, Qt.LeftButton)
pump(400)
check("confirmation demandée avant de supprimer", win.confirm_dialog.isVisible())
check("rien n'est supprimé avant confirmation", len(db.list_conversations()) == 6)
win.confirm_dialog.ok.click()
pump(600)
left = {r["id"] for r in db.list_conversations()}
check("suppression groupée après confirmation", left == {ids[0], ids[1], ids[2], ids[3]})
check("sélection vidée après suppression", hp.selected_ids() == [] and not hp.sel_bar.isVisible())

# Suppr au clavier
click("Discussion 4", Qt.ControlModifier)
QTest.keyClick(hp, Qt.Key_Delete)
pump(300)
check("la touche Suppr demande la confirmation", win.confirm_dialog.isVisible())
win.confirm_dialog.cancel.click() if hasattr(win.confirm_dialog, "cancel") else None

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
