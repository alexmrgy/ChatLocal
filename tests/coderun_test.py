"""Test : éditeur de code modifiable (enregistrement auto + synchro conversation), terminal, lancer Python et C."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_run_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.messages import CodeBlock  # noqa: E402

PY = "name = input('Ton nom ? ')\nprint('Bonjour', name)\nprint(2 + 3)\n"
C = ('#include <stdio.h>\nint main(void) {\n    int n;\n    printf("Nombre ? ");\n    scanf("%d", &n);\n'
     '    printf("Carre = %d\\n", n * n);\n    return 0;\n}\n')
BADC = '#include <stdio.h>\nint main(void) {\n    printf("x")\n    return 0;\n}\n'
MD = ("Voici trois codes :\n\n```python\n" + PY + "```\n\nEt en C :\n\n```c\n" + C + "```\n\nEt du C cassé :\n\n```c\n"
      + BADC + "```\n\nEt du JS :\n\n```js\nconsole.log(1)\n```")

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
cid = db.create_conversation("Code", "m")
db.add_message(cid, "user", "Écris du code")
db.add_message(cid, "assistant", MD)
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
win.open_conversation(cid)
pump(600)
blocks = [b for b in win.chat.findChildren(CodeBlock) if b.isVisible()]
check("4 blocs de code affichés", len(blocks) == 4)
cp = win.code_panel
term = cp.terminal
out = lambda: term.out.toPlainText()  # noqa: E731

# ---------- Python ----------
blocks[0].open_btn.click()
pump(500)
check("éditeur ouvert avec le code Python", cp.is_open() and cp.code() == PY.rstrip("\n") or cp.code().strip() == PY.strip())
check("éditeur modifiable", not cp.editor.isReadOnly())
check("bouton lancer actif (Python)", cp.play_btn.isEnabled())
cp.play_btn.click()
check("terminal affiché + programme en cours", pump(5000, lambda: term.is_running()) and term.isVisible())
check("l'invite du programme s'affiche tout de suite", pump(5000, lambda: "Ton nom ?" in out()))
term.input.setText("Alex")
term._submit()
check("Python : réponse au programme (stdin) puis sortie", pump(8000, lambda: "Terminé (code 0)" in out()))
check("Python : sortie correcte", "Bonjour Alex" in out() and "\n5\n" in out() + "\n")
win.grab().save(str(OUT / "shot_terminal_python.png"))

# ---------- modification dans l'éditeur -> conversation + base ----------
NEW = PY.replace("Bonjour", "Salut")
cp.editor.setPlainText(NEW.rstrip("\n"))
pump(1200)
check("enregistrement automatique signalé", "enregistré" in cp.save_label.text())
check("bloc de la discussion mis à jour", "Salut" in blocks[0].code())
msg = db.get_path(cid)[1]["content"]
check("base : message modifié avec le nouveau code", "Salut" in msg and "Bonjour" not in msg and "```c" in msg)
check("historique envoyé à l'IA mis à jour", "Salut" in win.history[1]["content"])
check("les autres blocs sont intacts", blocks[1].code().startswith("#include") and "console.log(1)" in msg)
win.new_chat()
pump(300)
win.open_conversation(cid)
pump(600)
check("après réouverture : code modifié conservé", any("Salut" in b.code() for b in win.chat.findChildren(CodeBlock) if b.isVisible()))
blocks = [b for b in win.chat.findChildren(CodeBlock) if b.isVisible()]

# lancer le code modifié (sans fichier choisi)
blocks[0].open_btn.click()
pump(400)
cp.play_btn.click()
pump(3000, lambda: "Ton nom ?" in out().split("$ python main.py")[-1])
term.input.setText("Zoé")
term._submit()
check("le code modifié est celui qui est lancé", pump(8000, lambda: "Salut Zoé" in out()))

# ---------- C ----------
blocks[1].open_btn.click()
pump(400)
check("éditeur : code C", cp.lang_label.text() == "c")
term.clear()
cp.play_btn.click()
check("C : compilation puis programme", pump(15000, lambda: "Compilation réussie" in out()))
ok_prompt = pump(10000, lambda: "Nombre ?" in out() or term._blocked)
if term._blocked:
    # Windows (Smart App Control) refuse parfois d'exécuter un .exe tout juste compilé : ce n'est pas un défaut de l'app
    print("SKIP C : exécution bloquée par la stratégie de sécurité de Windows (message affiché dans le terminal)")
    check("C : blocage Windows signalé clairement", "bloqué" in out() and "Smart App Control" in out()
          and "Compilation réussie" in out())
else:
    check("C : invite affichée immédiatement (sortie non tamponnée)", ok_prompt)
    term.input.setText("12")
    term._submit()
    check("C : résultat", pump(8000, lambda: "Carre = 144" in out() and "Terminé (code 0)" in out()))
win.grab().save(str(OUT / "shot_terminal_c.png"))

# erreur de compilation
blocks[2].open_btn.click()
pump(400)
term.clear()
cp.play_btn.click()
check("C cassé : erreur de compilation affichée", pump(15000, lambda: "Échec de la compilation" in out()) and "error" in out().lower())

# ---------- langage non lançable ----------
blocks[3].open_btn.click()
pump(400)
check("JS : bouton lancer désactivé", not cp.play_btn.isEnabled())

# ---------- arrêter un programme ----------
blocks[0].open_btn.click()
pump(400)
cp.editor.setPlainText("import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.2)")
term.clear()
cp.play_btn.click()
check("boucle infinie : en cours", pump(5000, lambda: term.is_running() and "tick" in out()))
check("bouton devient « arrêter »", cp.play_btn.toolTip() == "Arrêter")
cp.play_btn.click()
check("arrêt du programme", pump(5000, lambda: not term.is_running()) and "Arrêté" in out())

# ---------- commande simple dans le terminal ----------
term.clear()
term.input.setText("echo salut-terminal")
term._submit()
check("commande tapée dans le terminal", pump(10000, lambda: "salut-terminal" in out().replace("> echo salut-terminal", "") and "Terminé" in out()))

# ---------- sécurité de l'édition ----------
cp.update_code("print(1)", "python", False)
check("code en cours d'écriture : éditeur en lecture seule", cp.editor.isReadOnly())
cp.update_code("print(1)", "python", True)
check("code terminé : modifiable", not cp.editor.isReadOnly())
cp.set_editable(False)
check("chat verrouillé : lecture seule", cp.editor.isReadOnly())
cp.set_editable(True)

# ---------- largeur maximale ----------
cp.begin_drag()
cp.drag_to(5000)
check("très large mais la discussion garde sa place", cp.maximumWidth() == cp._limit() and cp._limit() >= cp.MIN_W)
cp.end_drag()
check("largeur max supérieure à l'ancienne (900)", cp.MAX_W > 900)

# ---------- fermer le terminal ----------
cp.set_panel_width(560)
blocks[0].open_btn.click()
pump(500)
if not term.isVisible():
    cp.toggle_terminal()
cp.editor.setPlainText("import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.2)")
cp.play_btn.click()
check("programme en cours dans le terminal", pump(5000, lambda: term.is_running()))
term.close_btn.click()
pump(500)
check("croix du terminal : terminal fermé", not term.isVisible())
check("croix du terminal : programme arrêté", not term.is_running())
check("l'éditeur reprend toute la hauteur", cp.editor.height() > 400)
cp.toggle_terminal()
pump(300)
check("bouton terminal : le rouvre", term.isVisible())
cp.toggle_terminal()
pump(300)
check("bouton terminal : le referme", not term.isVisible())

# ---------- agrandir vers la gauche, aussi loin qu'on veut ----------
win.resize(1400, 800)
pump(300)
win.toggle_history()
pump(500)
check("historique ouvert avant de tirer", win.history_panel.is_open())
cp.begin_drag()
before = cp.maximumWidth()
cp.drag_to(3000)
pump(500)
cp.drag_to(3000)
pump(200)
check("tirer très loin referme l'historique pour gagner de la place", not win.history_panel.is_open())
room = win.width() - 52 - 10 - cp.CHAT_MIN
check("panneau bien plus large qu'avant", cp.maximumWidth() > before + 150 and cp.maximumWidth() <= room + 2)
cp.end_drag()
check("la discussion garde au moins sa largeur minimale", win.panel.width() >= cp.CHAT_MIN - 20)
win.grab().save(str(OUT / "shot_codepanel_wide.png"))
win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
