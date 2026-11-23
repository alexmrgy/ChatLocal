"""Test d'intégration UI : clé NVIDIA, sélecteur, envoi en streaming, raccourci de recherche (faux serveur)."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_nv_")

import _mock_nvidia  # noqa: E402

_mock_nvidia.start()

from PySide6.QtCore import QCoreApplication, QElapsedTimer, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
win = MainWindow(Database())
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


pump(1500)
# 1) clé invalide : refusée, rien n'est enregistré
win.add_nvidia_key()
pump(500)
check("fenêtre de clé en mode mot de passe", win.prompt.edit.echoMode().name == "Password")
win.prompt.edit.setText("mauvaise")
win.prompt.ok.click()
pump(2500)
check("clé invalide non enregistrée", win.db.get_secret("nvidia_key") is None and not win.nvidia_models)

# 2) clé valide
win.add_nvidia_key()
pump(500)
win.prompt.edit.setText(_mock_nvidia.GOOD)
win.prompt.ok.click()
check("modèles NVIDIA chargés", pump(5000, lambda: bool(win.nvidia_models)))
check("clé stockée chiffrée", win.db.get_secret("nvidia_key") == _mock_nvidia.GOOD
      and _mock_nvidia.GOOD not in (win.db.get_setting("secret:nvidia_key") or ""))

# 3) sélecteur : section NVIDIA visible + actions de clé
win.input._open_menu()
popup = win.input._popup
popup.grab().save(str(OUT / "shot_nvidia_popup.png"))  # un popup se ferme si la fenêtre perd le focus : on capture tout de suite
popup.close()
pump(100)

# 4) envoi vers NVIDIA
win._choose_model("nvidia:meta/llama-3.1-8b-instruct")
win.on_submit("salut")
check("réponse NVIDIA en streaming", pump(15000, lambda: win.worker is None and win.assistant is None)
      and win.history[-1]["content"] == "Bonjour !")
check("modèle NVIDIA gardé dans la conversation",
      win.db.get_conversation(win.cid)["model"] == "nvidia:meta/llama-3.1-8b-instruct")

# 5) suppression de la clé (sans boîte de dialogue : on court-circuite la confirmation)
import ui.main_window as mw  # noqa: E402

win.remove_nvidia_key()
pump(400)
win.confirm_dialog.ok.click()
pump(400)
check("clé supprimée", win.db.get_secret("nvidia_key") is None and not win.nvidia_models
      and not win.input.model().startswith("nvidia:"))

# 6) raccourcis de recherche
win.new_chat()
pump(300)
QTest.keyClick(win, Qt.Key_K, Qt.ControlModifier)
check("Ctrl+K ouvre la recherche", pump(1000, lambda: win.palette.isVisible()))
win.palette.close_palette()
pump(500)
QTest.keyClick(win, Qt.Key_F, Qt.ControlModifier)
check("Ctrl+F ouvre la recherche", pump(1000, lambda: win.palette.isVisible()))

win.close()
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
