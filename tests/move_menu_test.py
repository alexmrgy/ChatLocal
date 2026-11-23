"""Test : menu « Déplacer vers un dossier » — taille correcte du sous-menu, dossier actuel coché, nouveau dossier."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_mv_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.action_menu import _Row  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
fa = db.create_folder("Travail")
fb = db.create_folder("Perso")
db.set_folder_color(fb, "vert")
cid = db.create_conversation("Ma discussion", "m")
db.move_conversation(cid, fa)
win = mw.MainWindow(db)
win.show()
fails = 0


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


def rows(menu):
    return [r for r in menu.findChildren(_Row) if r.isVisible()]


pump(400)
win.poller.models.disconnect()
win.poller.running.disconnect()
win.show_conversation_menu(cid, QPoint(300, 200))
pump(300)
menu = win._ctx_menu
main_h = menu.height()
check("menu principal affiché", menu.isVisible() and len(rows(menu)) >= 8)

# ouvre le sous-menu
move = next(r for r in rows(menu) if r.item.text == "Déplacer vers un dossier")
move.clicked.emit()
pump(300)
sub = rows(menu)
texts = [r.item.text for r in sub]
check("sous-menu : retour, dossiers, retirer, nouveau", texts == ["Déplacer vers un dossier", "Perso", "Travail", "Retirer du dossier", "Nouveau dossier…"]
      or sorted(texts[1:3]) == ["Perso", "Travail"] and "Nouveau dossier…" in texts and "Retirer du dossier" in texts)
check("le dossier actuel est coché", next(r for r in sub if r.item.text == "Travail").item.checked
      and not next(r for r in sub if r.item.text == "Perso").item.checked)
check("le dossier coloré a sa pastille", next(r for r in sub if r.item.text == "Perso").item.dot != "")
# la fenêtre épouse le contenu : pas de grand vide
expected = sum(r.height() for r in sub) + 8 * 2 + 2   # lignes + marges (+ séparateurs de 1 px)
check(f"le sous-menu se rétrécit ({menu.height()} px, menu principal {main_h} px)", menu.height() < main_h
      and menu.height() <= expected + 20)
gaps = [sub[i + 1].y() - (sub[i].y() + sub[i].height()) for i in range(len(sub) - 1)]
check("lignes serrées, sans grands espaces", max(gaps) <= 12)
win.grab().save(str(OUT / "shot_move_menu.png"))
menu.grab().save(str(OUT / "shot_move_menu_only.png"))

# déplacer vers l'autre dossier
next(r for r in sub if r.item.text == "Perso").clicked.emit()
pump(400)
check("déplacée dans « Perso »", db.get_conversation(cid)["folder_id"] == fb)

# retirer du dossier
win.show_conversation_menu(cid, QPoint(300, 200))
pump(300)
next(r for r in rows(win._ctx_menu) if r.item.text == "Déplacer vers un dossier").clicked.emit()
pump(200)
next(r for r in rows(win._ctx_menu) if r.item.text == "Retirer du dossier").clicked.emit()
pump(400)
check("retirée du dossier", db.get_conversation(cid)["folder_id"] is None)

# nouveau dossier : la discussion y est rangée
win.show_conversation_menu(cid, QPoint(300, 200))
pump(300)
next(r for r in rows(win._ctx_menu) if r.item.text == "Déplacer vers un dossier").clicked.emit()
pump(200)
check("« Retirer du dossier » absent hors dossier", "Retirer du dossier" not in [r.item.text for r in rows(win._ctx_menu)])
next(r for r in rows(win._ctx_menu) if r.item.text == "Nouveau dossier…").clicked.emit()
pump(500)
win.prompt.edit.setText("Projets")
win.prompt.ok.click()
pump(500)
fid = next(f["id"] for f in db.list_folders() if f["name"] == "Projets")
check("nouveau dossier créé et discussion rangée dedans", db.get_conversation(cid)["folder_id"] == fid)

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
