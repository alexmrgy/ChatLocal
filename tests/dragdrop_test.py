"""Test : glisser-déposer des conversations vers un dossier (ou hors d'un dossier), avec sélection multiple."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_dnd_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.sidebar import NavRow, conv_mime, mime_ids  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
fa, fb = db.create_folder("Travail"), db.create_folder("Perso")
ids = [db.create_conversation(f"Chat {i}", "m") for i in range(1, 6)]
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


def folder_of(cid):
    return db.get_conversation(cid)["folder_id"]


def row(text):
    pump(150)          # laisse la liste se reconstruire et s'afficher
    return next(r for r in win.history_panel.findChildren(NavRow) if r._text == text and r.isVisible())


def drop(widget, cids):
    mime = conv_mime(cids)            # garder la référence : l'événement n'est pas propriétaire du mime
    ev = QDropEvent(QPointF(20, 15), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    widget.dropEvent(ev)              # (Qt ne livre les « drop » qu'au cours d'un vrai glisser : appel direct)
    pump(300)


pump(400)
win.poller.models.disconnect()
win.poller.running.disconnect()
win.history_panel.set_open(True)
pump(500)
hp = win.history_panel

check("le format de glisser-déposer se relit", mime_ids(conv_mime([3, 7, 12])) == [3, 7, 12])

# 1) la ligne d'une conversation produit un glisser avec son identifiant
r = row("Chat 3")
r._press = QPoint(30, 15)
d = r.make_drag()
check("glisser une conversation emporte son id", d is not None and mime_ids(d.mimeData()) == [ids[2]])

# 2) glisser une ligne de la sélection emporte toute la sélection
QTest.mouseClick(row("Chat 2"), Qt.LeftButton, Qt.ControlModifier, QPoint(40, 17))
QTest.mouseClick(row("Chat 4"), Qt.LeftButton, Qt.ControlModifier, QPoint(40, 17))
pump(200)
r = row("Chat 2")
r._press = QPoint(30, 15)
d = r.make_drag()
check("glisser une ligne sélectionnée emporte toute la sélection", sorted(mime_ids(d.mimeData())) == sorted([ids[1], ids[3]]))
win.grab().save(str(OUT / "shot_dnd_selection.png"))

# 3) dépôt sur un dossier : toute la sélection y est déplacée
drop(row("Travail"), [ids[1], ids[3]])
check("dépôt de la sélection sur un dossier", folder_of(ids[1]) == fa and folder_of(ids[3]) == fa)
check("sélection vidée après le dépôt", hp.selected_ids() == [])
check("les autres conversations ne bougent pas", folder_of(ids[0]) is None and folder_of(ids[2]) is None)

# 4) dépôt d'une conversation seule sur un autre dossier
drop(row("Perso"), [ids[0]])
check("dépôt d'une conversation sur un dossier", folder_of(ids[0]) == fb)

# 5) dépôt sur une conversation rangée dans un dossier : même dossier
drop(row("Chat 4"), [ids[4]])
check("dépôt sur une conversation d'un dossier : elle y entre aussi", folder_of(ids[4]) == fa)

# 6) dépôt sur le fond de la liste : sortie du dossier
drop(hp.content, [ids[1]])
check("dépôt sur le fond de la liste sort du dossier", folder_of(ids[1]) is None)
win.grab().save(str(OUT / "shot_dnd_after.png"))

# 7) données invalides ignorées
from PySide6.QtCore import QMimeData  # noqa: E402
bad = QMimeData()
bad.setText("texte")
row("Travail").dropEvent(QDropEvent(QPointF(5, 5), Qt.MoveAction, bad, Qt.LeftButton, Qt.NoModifier))
pump(200)
check("un dépôt qui n'est pas une conversation est ignoré", folder_of(ids[3]) == fa)

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
