"""Test : bouton nouveau chat, titre cliquable et menu de conversation (actions réelles)."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_menu_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.messages import UserMessage  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
cid = db.create_conversation("Idées d'applications Windows indispensables", "phi4-mini:latest")
db.add_message(cid, "user", "Donne-moi des idées")
db.add_message(cid, "assistant", "Voici **trois** idées.")
f1 = db.create_folder("Projets")
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


def row():
    return db.get_conversation(cid)


pump(800)
check("accueil : ni titre ni bouton", not win.topbar._left.isVisible())
win.open_conversation(cid)
pump(300)
check("bouton nouveau chat visible", win.topbar.new_btn.isVisible())
check("titre de la discussion affiché", win.topbar.title_btn.isVisible()
      and win.topbar.title_btn.text().startswith("Idées d"))
win.grab().save(str(OUT / "shot_topbar.png"))

# menu au clic sur le titre
win.topbar.title_btn.click()
pump(200)
check("menu ouvert au clic sur le titre", win._ctx_menu.isVisible())
win._ctx_menu.grab().save(str(OUT / "shot_ctx_menu.png"))
win._ctx_menu.close()
pump(100)

# renommer (vraie fenêtre de saisie)
win.rename_conversation(cid)
pump(400)
win.prompt.edit.setText("Mon titre renommé")
win.prompt.ok.click()
pump(400)
check("renommage réel (base + barre du haut)", row()["title"] == "Mon titre renommé"
      and win.topbar.title_btn.text() == "Mon titre renommé")

# épingler
win.toggle_pin(cid)
check("épinglé (base)", bool(row()["pinned"]))
win.toggle_pin(cid)
check("désépinglé", not row()["pinned"])

# verrouiller : envoi, modification et suppression bloqués
win.toggle_lock(cid)
pump(400)
n = len(win.history)
win.on_submit("test verrou")
pump(200)
check("verrouillé : envoi refusé", len(win.history) == n and win.worker is None)
check("verrouillé : saisie en lecture seule", win.input.edit.isReadOnly())
users = [m for m in win.findChildren(UserMessage) if m.isVisible()]
check("verrouillé : bouton modifier masqué", users and not users[0].edit_btn.isVisible())
win.delete_conversation(cid)
check("verrouillé : suppression refusée", db.get_conversation(cid) is not None)
win.toggle_lock(cid)
pump(400)
check("déverrouillé : saisie à nouveau possible", not win.input.edit.isReadOnly())

# déplacer dans un dossier
win._move_conversation(cid, f1)
check("déplacé dans le dossier", row()["folder_id"] == f1)
win._move_conversation(cid, 0)
check("retiré du dossier", row()["folder_id"] is None)

# copier / exporter
win.copy_conversation(cid)
clip = QApplication.clipboard().text()
check("copie de la conversation", "# Mon titre renommé" in clip and "Donne-moi des idées" in clip)
dest = Path(tempfile.mkdtemp()) / "export.md"
mw.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(dest), ""))
win.export_conversation(cid)
check("export Markdown écrit", dest.exists() and "Voici **trois** idées." in dest.read_text(encoding="utf-8"))

# boutons au survol d'une ligne « Récents » (épingler et ⋯) + clic droit
from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QContextMenuEvent  # noqa: E402

from ui.action_menu import _Row  # noqa: E402
from ui.sidebar import NavRow  # noqa: E402

win.toggle_history()
pump(500)
rows = [r for r in win.history_panel.findChildren(NavRow) if r._actions and r.isVisible() and r._text == "Mon titre renommé"]
check("ligne de conversation dans Récents", len(rows) == 1)
r = rows[0]
r.enterEvent(None)
r.resize(260, 34)
pin_rect, menu_rect = r._btn_rects()
QTest.mouseClick(r, Qt.LeftButton, Qt.NoModifier, pin_rect.center())
check("bouton épingle de la ligne", bool(row()["pinned"]))
win.toggle_pin(cid)
pump(300)
r = [x for x in win.history_panel.findChildren(NavRow) if x._actions and x.isVisible() and x._text == "Mon titre renommé"][0]
r.resize(260, 34)
pin_rect, menu_rect = r._btn_rects()
QTest.mouseClick(r, Qt.LeftButton, Qt.NoModifier, menu_rect.center())
pump(200)
labels = [w.item.text for w in win._ctx_menu.findChildren(_Row)]
check("bouton ⋯ : menu identique aux captures",
      labels == ["Renommer", "Épingler", "Section", "Verrouiller le chat", "Partager",
                 "Copier la conversation", "Archiver", "Supprimer", "Déplacer vers un dossier"])
win._ctx_menu.grab().save(str(OUT / "shot_ctx_menu2.png"))
win._ctx_menu.close()
pump(100)
win._ctx_menu = None
ev = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(5, 5), r.mapToGlobal(QPoint(5, 5)))
QApplication.sendEvent(r, ev)
pump(200)
check("clic droit : même menu", win._ctx_menu is not None and win._ctx_menu.isVisible()
      and len(win._ctx_menu.findChildren(_Row)) == len(labels))
win._ctx_menu.close()
pump(100)
win.set_tag(cid, "bleu")
check("section (étiquette de couleur)", row()["tag"] == "bleu")
win.set_tag(cid, None)
win.toggle_history()
pump(300)

# raccourci clavier d'épinglage
QTest.keyClick(win, Qt.Key_P, Qt.ControlModifier | Qt.AltModifier)
pump(300)
check("raccourci Ctrl+Alt+P", bool(row()["pinned"]))
win.toggle_pin(cid)

# archiver
win.toggle_archive(cid)
pump(300)
check("archivé : retour à l'accueil", bool(row()["archived"]) and win.stack.currentIndex() == 0)
win.open_search()
pump(300)
check("archivé : absent de la recherche", all("Mon titre" not in r[0]._text for r in win.palette._rows))
win.palette.close_palette()
pump(400)
win.toggle_archive(cid)
check("désarchivé", not row()["archived"])

# bouton nouveau chat
win.open_conversation(cid)
pump(300)
win.topbar.new_btn.click()
pump(300)
check("bouton nouveau chat : retour à l'accueil vierge", win.cid is None and win.stack.currentIndex() == 0)

# suppression avec la fenêtre de confirmation en verre
win.open_conversation(cid)
win.delete_conversation(cid)
pump(400)
dlg = win.confirm_dialog
check("confirmation affichée (rien supprimé avant le clic)", dlg.isVisible() and db.get_conversation(cid) is not None)
check("texte de la confirmation", "Mon titre renommé" in dlg.subtitle.text() and dlg.ok.text() == "Supprimer")
win.grab().save(str(OUT / "shot_confirm.png"))
dlg.cancel.click()
pump(400)
check("Annuler : conversation conservée", db.get_conversation(cid) is not None and not dlg.isVisible())
win.delete_conversation(cid)
pump(400)
dlg.ok.click()
pump(400)
check("suppression réelle", db.get_conversation(cid) is None and win.cid is None)

# « Ne plus me demander »
c2 = db.create_conversation("Deuxième", "m")
c3 = db.create_conversation("Troisième", "m")
win._reload_history()
win.delete_conversation(c2)
pump(400)
dlg.check.set_checked(True)
dlg.ok.click()
pump(400)
check("coché : suppression + choix mémorisé", db.get_conversation(c2) is None
      and db.get_setting("skip_confirm:delete_conversation") == "1")
win.delete_conversation(c3)
pump(300)
check("ensuite : suppression directe sans fenêtre", db.get_conversation(c3) is None and not dlg.isVisible())
win.reset_confirms()
c4 = db.create_conversation("Quatrième", "m")
win._reload_history()
win.delete_conversation(c4)
pump(400)
check("confirmations réactivées (Aide)", dlg.isVisible() and db.get_conversation(c4) is not None)
dlg.cancel.click()
pump(300)

win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)

