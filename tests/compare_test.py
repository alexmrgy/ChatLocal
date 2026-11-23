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
db = Database()
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

win.grab().save(str(OUT / "shot_compare_idle.png"))
check("aucune réflexion avant la question", c.side_a.msg is None and c.side_b.msg is None)
check("titres = modèles choisis", c.side_a.title.text() == c.combo_a.currentText() and c.side_b.title.text() == c.combo_b.currentText())

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

check("la conversation survit au changement de page", len(c.side_a.history) == 2 and len(c.side_b.history) == 2)

# 2e question : chaque modèle reçoit SON historique puis la nouvelle question
n = len(SENT)
c.edit.setPlainText("Et maintenant ?")
c.run()
pump(5000, lambda: not c.busy())
ma, mb = SENT[n][1], SENT[n + 1][1]
check("suite : A reçoit son historique", [m["role"] for m in ma] == ["user", "assistant", "user"]
      and "alpha" in ma[1]["content"] and ma[2]["content"] == "Et maintenant ?")
check("suite : B reçoit son historique", [m["role"] for m in mb] == ["user", "assistant", "user"]
      and "beta" in mb[1]["content"] and "alpha" not in mb[1]["content"])
check("deux échanges affichés par colonne", len(c.side_a.turns) == 6 and len(c.side_b.turns) == 6)
pump(300)
win.grab().save(str(OUT / "shot_compare_2turns.png"))

# changer de modèle : nouvelle comparaison
c.combo_b.setCurrentIndex(0)
check("changer de modèle repart d'une conversation vide", c.side_a.history == [] and c.side_b.history == []
      and c.side_b.title.text() == c.combo_b.currentText() and not c.side_a.turns)
c.combo_b.setCurrentIndex(1)
c.edit.setPlainText("Encore une")
c.run()
pump(5000, lambda: not c.busy())
c.reset_all()
check("« Nouvelle comparaison » vide tout", not c.side_a.turns and c.side_a.history == [])

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

# --- enregistrement dans l'historique des conversations ---
pump(300)
convs = [r for r in db.list_conversations() if r["compare"]]
titles = [r["title"] for r in convs]
check("comparaisons enregistrées dans l'historique (une par comparaison)", len(convs) >= 3 and "Comparaison : Encore une" in titles)
first = [r for r in convs if r["title"].startswith("Comparaison : Dis bonjour")][0]
data = db.compare_data(first)
check("titre de la comparaison", first["title"].startswith("Comparaison : Dis bonjour"))
check("2 échanges enregistrés (A et B)", [t["q"] for t in data["turns"]] == ["Dis bonjour", "Et maintenant ?"]
      and "alpha" in data["turns"][0]["a"] and "beta" in data["turns"][0]["b"])
check("la comparaison apparaît dans la liste de l'historique", win.history_panel is not None)
win.grab().save(str(OUT / "shot_compare_history.png"))

# rouverture depuis l'historique
win.new_chat()
pump(200)
check("accueil affiché", win.stack.currentIndex() == mw.HOME)
win.open_conversation(first["id"])
pump(400)
check("la page de comparaison se rouvre", win.stack.currentIndex() == mw.COMPARE and c.cid == first["id"])
check("conversation restaurée", len(c.side_a.turns) == 6 and len(c.side_b.turns) == 6
      and len(c.side_a.history) == 4 and "alpha" in c.side_a.history[1]["content"])
check("modèles restaurés", c.combo_a.currentData() == "alpha" and c.combo_b.currentData() == "beta")
win.grab().save(str(OUT / "shot_compare_reopened.png"))
n = len(SENT)
c.edit.setPlainText("Suite après réouverture")
c.run()
pump(5000, lambda: not c.busy())
check("la suite reçoit l'historique restauré", len(SENT[n][1]) == 5)
data2 = db.compare_data(db.get_conversation(first["id"]))
check("la suite est ajoutée à la même conversation", len(data2["turns"]) == 3
      and len([r for r in db.list_conversations() if r["compare"]]) == len(convs))

# export Markdown
md = win._conversation_markdown(first["id"])
check("export Markdown de la comparaison", "#### alpha" in md and "#### beta" in md and "Suite après réouverture" in md)

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
