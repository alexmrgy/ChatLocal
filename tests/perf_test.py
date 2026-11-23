"""Test : fluidité — ouverture progressive d'une longue conversation, historique paresseux, caches de rendu."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_perf_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui import markdown_render  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
for i in range(300):
    db.create_conversation(f"Discussion {i}", "m")
cid = db.create_conversation("Longue discussion", "m")
code = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(20)) + "\n```\n"
for i in range(50):
    db.add_message(cid, "user", f"Question numéro {i}")
    db.add_message(cid, "assistant", f"## Réponse {i}\n\nTexte **gras**.\n\n{code}\nFin {i}.")
win = mw.MainWindow(db)
win.show()
fails = 0


def pump(ms, until=None):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.005)
        if until and until():
            return True
    return until() if until else True


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


pump(400)
win.poller.models.disconnect()
win.poller.running.disconnect()

# 1) ouverture : seuls les derniers messages sont construits tout de suite
t = time.perf_counter()
win.open_conversation(cid, force=True)
first = time.perf_counter() - t
n_first = len(win.chat._rows)
check(f"ouverture rapide ({first * 1000:.0f} ms)", first < 1.0)
check("seuls les derniers messages sont construits d'abord", 0 < n_first <= win.FIRST_BATCH)
check("historique complet en mémoire pour le modèle", len(win.history) == 100)

# 2) le reste arrive par lots, dans l'ordre, sans casser l'index
check("tous les messages finissent par s'afficher", pump(15000, lambda: len(win.chat._rows) == 100))
idx = [i for _, i in win.chat._rows]
check("messages dans l'ordre", idx == list(range(100)))
bar = win.chat.verticalScrollBar()
pump(300)
check("le défilement reste en bas", bar.value() >= bar.maximum() - 40)
win.grab().save(str(OUT / "shot_perf_long.png"))

# 3) changer de conversation pendant le chargement : aucun message de l'ancienne
other = db.create_conversation("Autre", "m")
db.add_message(other, "user", "Bonjour")
db.add_message(other, "assistant", "Salut")
win.open_conversation(cid, force=True)
win.open_conversation(other, force=True)
pump(1500)
check("ouvrir une autre conversation annule le chargement en cours", len(win.chat._rows) == 2)

# 4) historique : reconstruit seulement quand le panneau est ouvert
win.history_panel._stale = False
win._reload_history()
check("panneau fermé : pas de reconstruction", win.history_panel._stale)
t = time.perf_counter()
win.history_panel.set_open(True)
pump(400)
check("ouverture du panneau : liste complète", len(win.history_panel._order) == 302)

# 5) caches de rendu
markdown_render.code_to_html.cache_clear()
markdown_render.code_to_html("print(1)", "python")
markdown_render.code_to_html("print(1)", "python")
check("coloration du code mise en cache", markdown_render.code_to_html.cache_info().hits >= 1)

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
