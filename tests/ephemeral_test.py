"""Test du chat éphémère (Ollama réel, base temporaire) : rien ne doit être enregistré."""
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

MODEL = default_model()
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_eph_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
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


check("modèles détectés", pump(8000, lambda: MODEL in win.models))
win.input.set_model(MODEL)

win.topbar.temp_btn.click()
pump(200)
check("mode éphémère actif + bouton enfoncé", win.ephemeral and win.topbar.temp_btn.isChecked())
check("titre « Chat éphémère »", win.home.heading.text() == "Chat éphémère" and not win.home.subtitle.isHidden())
win.grab().save(str(OUT / "shot_ephemeral.png"))

win.on_submit("Réponds juste : ok")
check("réponse reçue", pump(120000, lambda: win.worker is None and win.assistant is None) and len(win.history) == 2)
check("aucune conversation en base", db.list_conversations() == [])
win.grab().save(str(OUT / "shot_ephemeral_chat.png"))

win.topbar.temp_btn.click()          # quitte le mode éphémère
pump(200)
check("sortie du mode éphémère (écran d'accueil vierge)",
      not win.ephemeral and win.stack.currentIndex() == 0 and win.history == [] and win.home.heading.text().startswith("Comment"))

# une conversation normale reste enregistrée
win.on_submit("Réponds juste : ok")
pump(120000, lambda: win.worker is None and win.assistant is None)
check("conversation normale enregistrée", len(db.list_conversations()) == 1)

win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
