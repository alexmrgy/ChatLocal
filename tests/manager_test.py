"""Test : page « Toutes les discussions », actions groupées, couleurs de dossier, enregistrement local de l'état."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_mgr_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QPoint  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.manager import _Row  # noqa: E402
from ui.sidebar import NavRow  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
f1 = db.create_folder("Travail")
ids = []
for i in range(6):
    c = db.create_conversation(f"Discussion {i}", "m")
    db.add_message(c, "user", f"question {i}")
    db.add_message(c, "assistant", f"réponse {i}")
    ids.append(c)
db.set_flag(ids[0], "pinned", True)
db.set_flag(ids[1], "locked", True)
db.set_flag(ids[2], "archived", True)
db.move_conversation(ids[3], f1)
win = mw.MainWindow(db)
win.show()
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


def select_all():
    if win.manager.header.state != 2:
        win.manager.header.toggled.emit()
    pump(150)


def vis_rows():
    return [r for r in win.manager.findChildren(_Row) if r.isVisible()]


pump(500)
win.sidebar.manager.click()
pump(300)
check("page « Toutes les discussions » ouverte", win.stack.currentIndex() == mw.MANAGER)
check("onglet Toutes : 5 discussions (1 archivée masquée)", len(vis_rows()) == 5)
check("aucune sélection : boutons d'action désactivés", not win.manager.btns["delete"].isEnabled())
win.grab().save(str(OUT / "shot_manager.png"))

# tout sélectionner
win.manager.header.toggled.emit()
pump(200)
check("tout sélectionner", len(win.manager.selected_ids()) == 5 and win.manager.header.state == 2
      and win.manager.btns["delete"].isEnabled())
win.grab().save(str(OUT / "shot_manager_sel.png"))
win.manager.header.toggled.emit()
pump(200)
check("tout désélectionner", win.manager.selected_ids() == [])

# clic sur la case d'une ligne = sélection ; clic ailleurs = ouverture
r = vis_rows()[0]
QTest.mouseClick(r, Qt.LeftButton, Qt.NoModifier, QPoint(28, 20))
pump(200)
check("case d'une ligne : sélection", len(win.manager.selected_ids()) == 1)
win.manager.header.toggled.emit()  # complète la sélection
win.manager.header.toggled.emit()  # puis vide
pump(100)

# actions groupées : épingler
win.manager.header.toggled.emit()
pump(150)
win.manager.btns["pin"].click()
pump(200)
check("épingler la sélection", all(db.get_conversation(c)["pinned"] for c in ids if c != ids[2]))
win.manager.btns["pin"].click()
pump(200)
check("désépingler la sélection", not any(db.get_conversation(c)["pinned"] for c in ids if c != ids[2]))

# archiver
select_all()
win.manager.btns["archive"].click()
pump(200)
check("archiver la sélection", all(db.get_conversation(c)["archived"] for c in ids))
check("onglet Toutes vide après archivage", len(vis_rows()) == 0)
win.manager._set_tab(2)
pump(200)
check("onglet Archivées : 6 discussions", len(vis_rows()) == 6)
select_all()
win.manager.btns["archive"].click()   # texte « Désarchiver »
pump(200)
check("désarchiver", not any(db.get_conversation(c)["archived"] for c in ids))
win.manager._set_tab(0)
pump(200)

# déplacer dans un dossier
select_all()
win.manager.moveRequested.emit(win.manager.selected_ids(), f1)
pump(200)
check("déplacer la sélection dans un dossier", all(db.get_conversation(c)["folder_id"] == f1 for c in ids))

# exporter
dest = Path(tempfile.mkdtemp())
mw.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(dest))
win.manager.btns["export"].click()
pump(300)
check("exporter : un .md par discussion", len(list(dest.glob("*.md"))) == 6)

# supprimer : confirmation toujours demandée, verrouillée ignorée
select_all()
win.manager.btns["delete"].click()
pump(400)
dlg = win.confirm_dialog
check("suppression groupée : confirmation sans « Ne plus me demander »", dlg.isVisible() and dlg.check.isHidden())
check("texte : 5 supprimées, 1 verrouillée ignorée", "5 discussions" in dlg.subtitle.text() and "verrouillée" in dlg.subtitle.text())
win.grab().save(str(OUT / "shot_manager_confirm.png"))
dlg.cancel.click()
pump(400)
check("Annuler : rien supprimé", all(db.get_conversation(c) for c in ids))
win.manager.btns["delete"].click()
pump(400)
dlg.ok.click()
pump(500)
left = [c for c in ids if db.get_conversation(c)]
check("supprimées sauf la verrouillée", left == [ids[1]])
check("sélection : seule la verrouillée (conservée) reste cochée", win.manager.selected_ids() == [ids[1]])

# ---------- couleurs de dossier ----------
win.set_folder_color(f1, "bleu")
pump(300)
check("couleur de dossier enregistrée", db.list_folders()[0]["color"] == "bleu")
win.toggle_history()
pump(500)
frow = [r for r in win.history_panel.findChildren(NavRow) if r.isVisible() and r._text == "Travail"]
check("icône du dossier colorée", len(frow) == 1 and frow[0]._icon_color == "#5b8cff")
win.show_folder_menu(f1, QPoint(300, 300))
pump(200)
from ui.action_menu import _Row as MRow  # noqa: E402
labels = [w.item.text for w in win._ctx_menu.findChildren(MRow)]
check("menu du dossier : Renommer / Couleur / Supprimer", labels == ["Renommer", "Couleur", "Supprimer le dossier"])
win._ctx_menu.close()
pump(100)
win.grab().save(str(OUT / "shot_folder_color.png"))
win.set_folder_color(f1, None)
check("couleur retirée", db.list_folders()[0]["color"] is None)

# ---------- enregistrement local de l'état ----------
win.resize(1111, 733)
pump(200)
print("DBG avant fermeture", win.width(), win.height())
db.set_setting("model_aliases", '{"x": "Mon IA"}')
win.close()
db2 = Database(db.path)
win2 = mw.MainWindow(db2)
win2.show()
pump(500)
print("DBG après réouverture", win2.width(), win2.height())
check("taille de la fenêtre retrouvée", abs(win2.width() - 1111) <= 2 and abs(win2.height() - 733) <= 2)
check("historique rouvert comme avant", win2.history_panel.is_open())
check("alias de modèle retrouvés", win2.input._aliases == {"x": "Mon IA"})
check("dossiers / discussions retrouvés", len(db2.list_folders()) == 1 and db2.get_conversation(ids[1]) is not None)
win2.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
