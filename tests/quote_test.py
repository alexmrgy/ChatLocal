"""Test : sélection de texte -> « Demander à … » -> carte « Sélection » -> texte transmis à l'IA."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_quote_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication, QTextBrowser  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402

SENT = []


class FakeStream:
    """Faux flux Ollama : mémorise ce que l'app envoie au modèle."""
    cancelled = False

    def __init__(self, model, messages):
        SENT.append(messages)

    def cancel(self):
        pass

    def run(self):
        yield "content", "réponse de test"


mw.client.ChatStream = FakeStream

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
cid = db.create_conversation("Discussion rapide", "m")
db.add_message(cid, "user", "Parle-moi de Python")
db.add_message(cid, "assistant", "Python est un langage **simple** et puissant, très utilisé en data science.")
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


pump(500)
win.running = True
win.models = ["m"]
win.input.set_model("m")
win.poller.models.disconnect()
win.poller.running.disconnect()
win.open_conversation(cid)
pump(400)

# 1) sélection dans la réponse + relâchement de la souris -> pastille
tbs = [t for t in win.chat.findChildren(QTextBrowser) if t.isVisible() and "langage" in t.toPlainText()]
tb = tbs[0]
c = tb.textCursor()
c.setPosition(0)
c.movePosition(QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor, 4)
tb.setTextCursor(c)
sel = win.chat.selected_text(tb)
pt = tb.viewport().mapFromGlobal(tb.mapToGlobal(tb.cursorRect().center()))
glob = tb.viewport().mapToGlobal(pt)
QApplication.sendEvent(tb.viewport(), QMouseEvent(QEvent.MouseButtonRelease, QPointF(pt), QPointF(glob), Qt.LeftButton,
                                                  Qt.NoButton, Qt.NoModifier))
pump(300)
check("texte sélectionné détecté", sel.startswith("Python est"))
check("pastille « Demander à… » affichée", win.chat.pill.isVisible())
win.grab().save(str(OUT / "shot_pill.png"))

# 2) clic sur la pastille -> carte « Sélection » dans la barre de saisie
win.chat.pill.click()
pump(300)
check("carte « Sélection » affichée", win.input.quote_chip.isVisible() and win.input.quote() == sel)
check("pastille masquée, sélection retirée", not win.chat.pill.isVisible() and not tb.textCursor().hasSelection())
win.grab().save(str(OUT / "shot_quote_chip.png"))

# 3) envoi : l'extrait part avec le message vers le modèle
win.on_submit("Explique ça plus simplement")
pump(600, lambda: win.worker is None and win.assistant is None)
last = SENT[-1]
check("l'IA reçoit l'extrait sélectionné", sel in last[-1]["content"] and last[-1]["content"].endswith("Explique ça plus simplement"))
check("l'IA reçoit aussi le contexte précédent", len(last) == 3 and last[0]["content"] == "Parle-moi de Python")
check("carte retirée après l'envoi", not win.input.quote_chip.isVisible() and win.input.quote() == "")
check("extrait enregistré avec le message", db.get_path(cid)[2]["quote"] == sel and db.get_path(cid)[2]["content"] == "Explique ça plus simplement")
pump(500)
print("DBG hauteur de la barre après envoi :", win.input.height(), win.input.sizeHint().height())
check("la barre retrouve sa hauteur normale après l'envoi", win.input.height() <= 60)
win.grab().save(str(OUT / "shot_quote_sent.png"))

# 4) l'extrait reste lié au message : réouverture de la conversation + tour suivant
win.new_chat()
pump(200)
win.open_conversation(cid)
pump(400)
check("extrait réaffiché après réouverture", win.history[2]["quote"] == sel)
win.on_submit("Et en une phrase ?")
pump(600, lambda: win.worker is None and win.assistant is None)
last = SENT[-1]
check("tour suivant : l'extrait précédent reste dans le contexte envoyé", sel in last[2]["content"])

# 5) modifier le message conserve l'extrait
win.edit_prompt(2, "Version modifiée")
pump(600, lambda: win.worker is None and win.assistant is None)
check("modification : l'extrait est conservé", sel in SENT[-1][2]["content"] and SENT[-1][2]["content"].endswith("Version modifiée"))

# 6) croix : retire la carte
win.input.set_quote("autre texte")
check("carte affichée", win.input.quote_chip.isVisible())
win.input.quote_chip.removed.emit()
check("croix : carte retirée", not win.input.quote_chip.isVisible() and win.input.quote() == "")

# 7) clic ailleurs : pastille masquée
tb.setTextCursor(c)
QApplication.sendEvent(tb.viewport(), QMouseEvent(QEvent.MouseButtonRelease, QPointF(pt), QPointF(glob), Qt.LeftButton,
                                                  Qt.NoButton, Qt.NoModifier))
pump(200)
shown = win.chat.pill.isVisible()
QApplication.sendEvent(win.chat.viewport(), QMouseEvent(QEvent.MouseButtonPress, QPointF(5, 5), QPointF(win.chat.viewport().mapToGlobal(win.chat.viewport().rect().topLeft()) ), Qt.LeftButton,
                                                        Qt.LeftButton, Qt.NoModifier))
pump(100)
check("clic ailleurs : pastille masquée", shown and not win.chat.pill.isVisible())
# 8) la pastille survit au défilement automatique (texte qui arrive pendant la sélection)
win.chat.clear()
win.chat.add_assistant("Texte " * 3, 0, fade=False)
pump(300)
tb2 = [t for t in win.chat.findChildren(QTextBrowser) if t.isVisible()][0]
c2 = tb2.textCursor()
c2.setPosition(0)
c2.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
tb2.setTextCursor(c2)
pt2 = tb2.viewport().rect().center()
g2 = tb2.viewport().mapToGlobal(pt2)
QApplication.sendEvent(tb2.viewport(), QMouseEvent(QEvent.MouseButtonRelease, QPointF(pt2), QPointF(g2), Qt.LeftButton,
                                                   Qt.NoButton, Qt.NoModifier))
pump(200)
before = win.chat.pill.isVisible()
for i in range(8):                                  # du contenu arrive : la vue défile toute seule
    win.chat.add_assistant("Ligne " * 60, 10 + i, fade=False)
    pump(80)
check("pastille toujours là après défilement automatique", before and win.chat.pill.isVisible())
win.chat.pill.hide()

# 9) clic droit sur un texte -> « Demander à Ollama »
from ui.action_menu import _Row as MenuRow  # noqa: E402
from ui.messages import show_text_menu  # noqa: E402

win.chat.clear()
win.chat.add_assistant("Un texte à interroger", 0, fade=False)
pump(300)
tb3 = [t for t in win.chat.findChildren(QTextBrowser) if t.isVisible()][0]
c3 = tb3.textCursor()
c3.setPosition(3)
c3.setPosition(8, QTextCursor.MoveMode.KeepAnchor)
tb3.setTextCursor(c3)
show_text_menu(tb3, tb3.mapToGlobal(tb3.rect().center()))
pump(200)
rows = [r for r in tb3._menu.findChildren(MenuRow)]
check("menu du clic droit : Copier / Demander à Ollama / Tout sélectionner",
      [r.item.text for r in rows] == ["Copier", "Demander à Ollama", "Tout sélectionner"] and rows[1].isEnabled())
rows[1].clicked.emit()
pump(300)
check("clic droit -> carte « Sélection »", win.input.quote_chip.isVisible() and win.input.quote() == "texte")

# 10) carte « Sélection » seule : on peut envoyer sans écrire de question
SENT.clear()
win.input.edit.clear()
win.input.set_quote("un extrait sans question")
win.input._on_submit()
pump(800, lambda: win.worker is None and win.assistant is None)
check("envoi avec la carte seule : question par défaut",
      SENT and SENT[-1][-1]["content"].endswith("Explique cet extrait.") and "un extrait sans question" in SENT[-1][-1]["content"])
win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
