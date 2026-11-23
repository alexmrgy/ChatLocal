"""Génère toutes les captures d'écran du README dans docs/ (données de démonstration, base temporaire).

Usage : python scripts/make_screenshots.py
"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_demo_")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.sidebar import NavRow  # noqa: E402

DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

MODELS = ["gemma3:4b", "llama3.2:3b", "qwen3:8b"]


class DemoStream:
    """Faux flux : réponses de démonstration, propres à chaque modèle."""
    cancelled = False
    ANSWERS = {
        "gemma3:4b": "## Une fonction Python\n\nVoici une version **simple** et lisible :\n\n```python\ndef moyenne(notes):\n    return sum(notes) / len(notes)\n```\n\n Elle accepte n'importe quelle liste de nombres.",
        "llama3.2:3b": "## Calculer une moyenne\n\nIl suffit de **diviser la somme par le nombre d'éléments** :\n\n- additionne toutes les notes\n- divise par `len(notes)`\n\n Pense à gérer le cas d'une liste vide.",
    }

    def __init__(self, model, messages):
        self.model = model

    def cancel(self):
        pass

    def run(self):
        yield "content", self.ANSWERS.get(self.model, "Bonjour ! ")


mw.client.ChatStream = DemoStream

app = QApplication([])
main.load_fonts(app)
main.load_style(app)

db = Database()
work = db.create_folder("Travail")
perso = db.create_folder("Projets perso")
db.set_folder_color(work, "bleu")


def conv(title, folder=None, pinned=False, msgs=()):
    cid = db.create_conversation(title, MODELS[0])
    for role, text in msgs:
        db.add_message(cid, role, text)
    if folder:
        db.move_conversation(cid, folder)
    if pinned:
        db.set_flag(cid, "pinned", True)
    return cid


CODE = ("## Une fonction qui compte les mots\n\nVoici une version simple et lisible :\n\n```python\n"
        "def compter_mots(texte):\n    mots = texte.split()\n    return len(mots)\n\n"
        "print(compter_mots(\"Bonjour tout le monde\"))\n```\n\n Elle renvoie **4** pour cet exemple. "
        "Tu peux la lancer directement avec le bouton de lancement du bloc de code.")
c_main = conv("Compter les mots d'un texte", msgs=[("user", "Écris-moi une fonction Python qui compte les mots d'un texte."),
                                                    ("assistant", CODE)])
conv("Idées de cadeaux", pinned=True, msgs=[("user", "Des idées de cadeau pour ma sœur ?"),
                                            ("assistant", " Voici quelques idées : un livre, une plante, un atelier de poterie…")])
conv("Résumé de la réunion", folder=work, msgs=[("user", "Résume ma réunion."), ("assistant", " Voici le résumé…")])
conv("Plan de la semaine", folder=work, msgs=[("user", "Aide-moi à planifier."), ("assistant", " Lundi : …")])
conv("Recette de crêpes", folder=perso, msgs=[("user", "Recette de crêpes ?"), ("assistant", " 250 g de farine…")])
conv("Traduire un e-mail", msgs=[("user", "Traduis ce mail."), ("assistant", " Voici la traduction…")])
conv("Exercice de maths", msgs=[("user", "Explique les fractions."), ("assistant", " Une fraction…")])
conv("Idée de nom pour mon chien", msgs=[("user", "Un nom de chien ?"), ("assistant", " Max, Luna, Filou…")])

win = mw.MainWindow(db)
win.resize(1180, 740)
win.show()
win.poller.models.disconnect()
win.poller.running.disconnect()
win.running = True
win.models = list(MODELS)
win.input.set_models(list(MODELS), True)
win.input.set_model(MODELS[0])


def pump(ms=300):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def shot_with_popup(name, popup):
    """Capture de la fenêtre avec une fenêtre flottante (menu, liste) dessinée à sa vraie place."""
    from PySide6.QtGui import QPainter
    pump(400)
    img = win.grab().toImage()
    pos = popup.mapToGlobal(QPoint(0, 0)) - win.mapToGlobal(QPoint(0, 0))
    p = QPainter(img)
    p.drawPixmap(pos, popup.grab())
    p.end()
    img.save(str(DOCS / f"{name}.png"))
    print("  ", name)


def shot(name):
    pump(500)
    win.grab().save(str(DOCS / f"{name}.png"))
    print("  ", name)


pump(600)

# 1) accueil
win._reload_history()
shot("screenshot")

# 2) historique + dossiers + sélection multiple
win.history_panel.set_open(True)
pump(500)
win.open_conversation(c_main, force=True)
pump(800)


def click_row(title, mods=Qt.NoModifier):
    r = next(r for r in win.history_panel.findChildren(NavRow) if r._text == title and r.isVisible())
    QTest.mouseClick(r, Qt.LeftButton, mods, QPoint(40, 17))
    pump(250)


shot("history")
click_row("Traduire un e-mail", Qt.ControlModifier)
click_row("Exercice de maths", Qt.ControlModifier)
shot("selection")
win.history_panel.clear_selection()

# 3) discussion avec bloc de code, puis panneau de code
win.history_panel.set_open(False)
pump(400)
shot("chat")
blocks = win.chat.findChildren(type(win.code_panel).__mro__[0]) if False else None
from ui.messages import CodeBlock  # noqa: E402

cb = win.chat.findChildren(CodeBlock)
if cb:
    win._open_code_panel(cb[0])
    pump(900)
    shot("code")
    win.code_panel.close_panel()
    pump(500)

# 4) fichiers joints
win.new_chat()
pump(300)
tmp = Path(tempfile.mkdtemp(prefix="demo_files_"))
(tmp / "notes_reunion.txt").write_text("Points à traiter : budget, planning, équipe.", encoding="utf-8")
(tmp / "tableau.csv").write_text("nom;note\nAlice;15\nBob;12\n", encoding="utf-8")
win.input.add_paths([str(tmp / "notes_reunion.txt"), str(tmp / "tableau.csv")])
win.input.set_text("Peux-tu résumer ces fichiers ?")
shot("files")
win.input.clear_files()
win.input.set_text("")

# 5) menu « Déplacer vers un dossier »
win.history_panel.set_open(True)
pump(500)
win.show_conversation_menu(c_main, QPoint(330, 250))
pump(300)
from ui.action_menu import _Row  # noqa: E402

move = next(r for r in win._ctx_menu.findChildren(_Row) if r.isVisible() and r.item.text == "Déplacer vers un dossier")
move.clicked.emit()
pump(400)
shot_with_popup("move_menu", win._ctx_menu)
win._ctx_menu.close()
pump(300)
win.history_panel.set_open(False)
pump(400)

# 6) recherche rapide
win.open_search()
pump(700)
win.palette.edit.setText("c")
pump(600)
shot("search")
win.palette.close() if hasattr(win.palette, "close") else None
win.palette.hide()
pump(300)

# 7) comparaison de deux modèles (conversation à deux questions)
win.show_compare()
pump(300)
c = win.compare
c.combo_a.setCurrentIndex(0)
c.combo_b.setCurrentIndex(1)
c.edit.setPlainText("Comment calculer la moyenne d'une liste de notes ?")
c.run()
t = QElapsedTimer()
t.start()
while c.busy() and t.elapsed() < 8000:
    pump(50)
pump(600)
shot("compare")

# 8) choix du modèle
win.new_chat()
pump(300)
win.input._open_menu()
pump(500)
shot_with_popup("models", win.input._popup)
win.input._popup.close()

# met à jour les paramètres ?v= des images dans le README (rechargement forcé sur GitHub)
readme = ROOT / "README.md"
if readme.exists():
    text = readme.read_text(encoding="utf-8")
    stamp = int(time.time())
    text = re.sub(r"(docs/[a-z_]+\.png)(\?v=\d+)?", rf"\g<1>?v={stamp}", text)
    readme.write_text(text, encoding="utf-8")
print("Captures enregistrées dans", DOCS)
os._exit(0)
