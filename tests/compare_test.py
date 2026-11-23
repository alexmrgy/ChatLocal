"""Test : comparaison de deux modèles — même question, deux réponses simultanées (flux simulés)."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_cmp_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402

SENT = []


class FakeStream:
    def __init__(self, model, messages):
        self.model, self.cancelled = model, False
        SENT.append((model, messages))

    def cancel(self):
        self.cancelled = True

    def run(self):
        words = (f"**{self.model}** répond : " + "bonjour " * 6).split(" ")
        for w in words:
            if self.cancelled:
                return
            time.sleep(0.03 if self.model == "alpha" else 0.06)
            yield "content", w + " "


mw.client.ChatStream = FakeStream
app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
win = mw.MainWindow(Database())
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


pump(400)
win.running = True
win.models = ["alpha", "beta"]
win.poller.models.disconnect()
win.poller.running.disconnect()
win.input.set_models(["alpha", "beta"], True)
win.sidebar.compare.click()          # bouton de la barre latérale
pump(200)
c = win.compare
check("bouton de la sidebar coché", win.sidebar.compare.isChecked())
check("page de comparaison affichée", win.stack.currentIndex() == mw.COMPARE)
check("deux modèles différents présélectionnés", c.combo_a.currentData() != c.combo_b.currentData() and c.combo_a.count() == 2)

# même modèle des deux côtés : refusé
msgs = []
c.message.connect(msgs.append)
c.combo_b.setCurrentIndex(c.combo_a.currentIndex())
c.edit.setPlainText("Salut")
c.run()
check("même modèle refusé", bool(msgs) and not c.busy())
c.combo_a.setCurrentIndex(0)
c.combo_b.setCurrentIndex(1)

c.edit.setPlainText("Dis bonjour")
c.run()
check("comparaison démarrée", c.busy() and len(SENT) == 2)
pump(5000, lambda: not c.busy())
check("les deux modèles ont reçu la même question", [m for _, m in SENT] == [[{"role": "user", "content": "Dis bonjour"}]] * 2)
check("réponse du modèle A", "alpha" in c.side_a.buffer and c.side_a.buffer.count("bonjour") == 6)
check("réponse du modèle B", "beta" in c.side_b.buffer and c.side_b.buffer.count("bonjour") == 6)
check("statistiques affichées", "caractères" in c.side_a.stats.text() and "caractères" in c.side_b.stats.text())
check("A (plus rapide) a fini avant B", c.side_a.first and c.side_a.first < c.side_b.first + 0.5)
pump(300)
win.grab().save(str(OUT / "shot_compare.png"))

win.sidebar.home.click()
pump(200)
check("retour accueil décoche le bouton", not win.sidebar.compare.isChecked())
win.sidebar.compare.click()
pump(200)

# arrêt en cours de route
c.edit.setPlainText("Encore")
c.run()
pump(150)
c.cancel()
check("arrêt des deux réponses", pump(3000, lambda: not c.busy()))

# quitter la page arrête aussi
c.edit.setPlainText("Et encore")
c.run()
pump(100)
win.new_chat()
check("quitter la page arrête les réponses", pump(3000, lambda: not c.busy()))

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
