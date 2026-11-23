"""Test : renommer l'affichage d'un modèle (alias), sans changer le modèle réel."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_alias_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QPoint  # noqa: E402
from PySide6.QtGui import QContextMenuEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.input_bar import _ModelRow  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
win = MainWindow(db)
win.show()
fails = 0


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


# jeu de modèles contrôlé (indépendant du PC) : on coupe le sondage d'Ollama avant qu'il ne réponde
win.poller.models.disconnect()
win.poller.running.disconnect()
win.poller.stop()
win.poller.wait(3000)
pump(300)
win.running = True
win.models = ["qwen3.5:9b", "phi4-mini:latest"]
win.nvidia_key = "k"
win.nvidia_models = ["meta/llama-3.1-8b-instruct"]
win.input.set_model("qwen3.5:9b")
win._sync_models()


def popup_rows():
    win.input._open_menu()
    pop = win.input._popup
    return pop, [r for r in pop.findChildren(_ModelRow) if r._rename]


pop, rows = popup_rows()
check("noms réels par défaut", [r._text for r in rows] == ["qwen3.5:9b", "phi4-mini:latest", "meta/llama-3.1-8b-instruct"])
# le crayon d'une ligne demande le renommage
got = []
pop.renameRequested.connect(got.append)
rows[0].renameClicked.emit()
check("crayon : demande de renommage du bon modèle", got == ["qwen3.5:9b"])
pop.close()
pump(100)

# renommage réel via la fenêtre de saisie
win.rename_model("qwen3.5:9b")
pump(400)
check("fenêtre de renommage préremplie", win.prompt.edit.text() == "qwen3.5:9b" and "qwen3.5:9b" in win.prompt.subtitle.text())
win.prompt.edit.setText("Mon assistant")
win.prompt.ok.click()
pump(400)
check("bouton du sélecteur : alias affiché", win.input.model_btn.text() == "Mon assistant")
check("modèle réel inchangé", win.input.model() == "qwen3.5:9b")
pop, rows = popup_rows()
check("liste : alias affiché, autres inchangés", [r._text for r in rows] == ["Mon assistant", "phi4-mini:latest", "meta/llama-3.1-8b-instruct"])
check("infobulle : nom réel", "qwen3.5:9b" in rows[0].toolTip())
pop.grab().save(str(OUT / "shot_alias_popup.png"))
# clic droit sur une ligne
got.clear()
pop.renameRequested.connect(got.append)
QApplication.sendEvent(rows[1], QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(5, 5), rows[1].mapToGlobal(QPoint(5, 5))))
check("clic droit : renommer", got == ["phi4-mini:latest"])
pop.close()
pump(100)

# alias d'un modèle NVIDIA
win.rename_model("nvidia:meta/llama-3.1-8b-instruct")
pump(400)
check("modèle NVIDIA : sous-titre avec le nom réel", "meta/llama-3.1-8b-instruct" in win.prompt.subtitle.text())
win.prompt.edit.setText("Llama rapide")
win.prompt.ok.click()
pump(400)
win._choose_model("nvidia:meta/llama-3.1-8b-instruct")
check("NVIDIA : alias sur le bouton, identifiant réel conservé",
      win.input.model_btn.text() == "Llama rapide" and win.input.model() == "nvidia:meta/llama-3.1-8b-instruct")

# recherche par alias ou par nom réel dans la liste
win.input.set_model("qwen3.5:9b")
win.input._open_menu()
pop = win.input._popup
check("liste longue : pas de champ de recherche sous 9 modèles", pop.search is None)
pop.close()
pump(100)

# mémorisation
check("alias enregistrés en base", "Mon assistant" in (db.get_setting("model_aliases") or ""))
win2 = MainWindow(Database(db.path))
win2.input.set_model("qwen3.5:9b")
check("alias retrouvés au redémarrage", win2.input.display_name("qwen3.5:9b") == "Mon assistant")

# retour au nom d'origine
win.rename_model("qwen3.5:9b")
pump(400)
win.prompt.edit.setText("qwen3.5:9b")
win.prompt.ok.click()
pump(400)
check("nom d'origine retapé : alias retiré", win.input.display_name("qwen3.5:9b") == "qwen3.5:9b"
      and "qwen3.5:9b" not in (db.get_setting("model_aliases") or ""))
win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
