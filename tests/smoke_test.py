"""Test de bout en bout (Ollama réel, base temporaire) + captures PNG.

Usage : python tests/smoke_test.py [dossier_sortie] [modèle]
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _testenv import default_model  # noqa: E402

MODEL = sys.argv[2] if len(sys.argv) > 2 else default_model()
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_test_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
win = MainWindow(Database())
win.show()


def pump(ms: int, until=None) -> bool:
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.01)
        if until and until():
            return True
    return until() if until else True


def check(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        global failed
        failed = True


failed = False
check("modèles détectés", pump(8000, lambda: bool(win.models)) and MODEL in win.models)
check("ollama détecté en ligne", win.running)
win.input.set_model(MODEL)
win.grab().save(str(OUT / "shot_home.png"))

first_chunk = []
orig = win._on_chunk
win._on_chunk = lambda t: (first_chunk.append(time.time()), orig(t))
win.worker = None
win.on_submit("Écris une fonction Python qui additionne deux nombres, avec un bloc de code, puis une liste de 2 puces.")
# la connexion de signal pointe sur la méthode d'origine : on observe plutôt le buffer
ok = pump(180000, lambda: win.worker is None and win.assistant is None)
check("réponse terminée", ok)
check("réponse non vide", len(win.history) == 2 and len(win.history[1]["content"]) > 20)
print("réponse :", repr(win.history[-1]["content"][:200]) if win.history else None)
win.grab().save(str(OUT / "shot_chat.png"))

cid = win.cid
check("conversation créée en base", cid is not None and len(win.db.get_messages(cid)) == 2)

# persistance : on rouvre la base
db2 = Database(win.db.path)
check("persistance (2 messages relus)", len(db2.get_messages(cid)) == 2)
db2.close()

# changement de conversation + retour
win.new_chat()
check("nouvelle conversation -> accueil", win.stack.currentIndex() == 0 and win.cid is None)
win.open_conversation(cid)
pump(300)
check("réouverture", win.stack.currentIndex() == 1 and len(win.history) == 2)

# rename / delete
win.db.rename_conversation(cid, "Titre renommé")
check("renommage", win.db.get_conversation(cid)["title"] == "Titre renommé")
win.db.delete_conversation(cid)
check("suppression", win.db.get_conversation(cid) is None)

# interruption
win.new_chat()
win.on_submit("Raconte une très longue histoire de 500 mots.")
pump(6000)
win.stop_generation()
check("stop -> fin de génération", pump(15000, lambda: win.worker is None))
win.grab().save(str(OUT / "shot_stop.png"))

win.close()
print("RÉSULTAT :", "ÉCHEC" if failed else "SUCCÈS")
sys.exit(1 if failed else 0)
