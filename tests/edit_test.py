"""Test : copier / modifier un prompt (Ollama réel, base temporaire)."""
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
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_edit_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.messages import UserMessage  # noqa: E402

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


def idle():
    return win.worker is None and win.assistant is None


check("modèles détectés", pump(8000, lambda: MODEL in win.models))
win.input.set_model(MODEL)
win.on_submit("Réponds juste : un")
pump(120000, idle)
win.on_submit("Réponds juste : deux")
pump(120000, idle)
check("2 échanges (4 messages)", len(win.history) == 4)

users = win.findChildren(UserMessage)
check("2 messages utilisateur affichés", len(users) == 2)

# boutons visibles seulement au survol
check("boutons masqués au repos", users[0]._fx.opacity() == 0.0)
users[0].enterEvent(None)
pump(300)
check("boutons visibles au survol", users[0]._fx.opacity() == 1.0)
win.grab().save(str(OUT / "shot_hover.png"))
users[0].leaveEvent(None)
pump(300)
check("boutons masqués après le survol", users[0]._fx.opacity() == 0.0)

# copier
users[0].copy_btn.click()
check("copie du prompt dans le presse-papiers", QApplication.clipboard().text() == "Réponds juste : un")

# modifier le 1er prompt
users[0].edit_btn.click()
pump(200)
check("éditeur visible", users[0].edit_box.isVisible() and not users[0].show_box.isVisible())
win.grab().save(str(OUT / "shot_edit.png"))
users[0].editor.setPlainText("Réponds juste : trois")
users[0].send_btn.click()
check("régénération terminée", pump(120000, lambda: idle() and len(win.history) == 2))
check("historique tronqué puis refait", win.history[0]["content"] == "Réponds juste : trois")
msgs = db.get_messages(win.cid)
check("base : 2 messages, 1er = prompt modifié", len(msgs) == 2 and msgs[0]["content"] == "Réponds juste : trois")
vis = [m for m in win.findChildren(UserMessage) if m.isVisible()]  # les widgets supprimés ne sont détruits qu'à la boucle d'événements suivante
check("1 seul message utilisateur affiché", len(vis) == 1)
win.grab().save(str(OUT / "shot_edit_done.png"))

# versions : l'ancienne version reste consultable
check("base : 6 messages au total (ancienne branche conservée)",
      db.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 6)
vis0 = vis[0]
check("navigation visible (2/2)", vis0.nav.isVisible() and vis0.ver_label.text() == "2/2")
win.grab().save(str(OUT / "shot_versions.png"))
vis0.prev_btn.click()
pump(500)
check("ancienne version affichée avec sa réponse",
      len(win.history) == 4 and win.history[0]["content"] == "Réponds juste : un"
      and win.history[2]["content"] == "Réponds juste : deux")
vis_now = [m for m in win.findChildren(UserMessage) if m.isVisible()]
check("navigation 1/2 sur l'ancienne version", len(vis_now) == 2 and vis_now[0].ver_label.text() == "1/2")
win.grab().save(str(OUT / "shot_versions_old.png"))
vis_now[0].next_btn.click()
pump(500)
check("retour à la version modifiée",
      len(win.history) == 2 and win.history[0]["content"] == "Réponds juste : trois")
vis = [m for m in win.findChildren(UserMessage) if m.isVisible()]

# annuler une édition
u = vis[0]
u.edit_btn.click()
pump(100)
u.cancel_btn.click()
check("annulation : bulle réaffichée, rien changé", u.show_box.isVisible() and len(win.history) == 2)

win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)

