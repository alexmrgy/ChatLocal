"""Test : panneau de code sur la droite (ouverture, copie, enregistrement, mode automatique, largeur)."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_codepanel_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer, QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.code_panel import extension_for  # noqa: E402

CODE = "\n".join(f"print('ligne {i}')" for i in range(1, 61))


class FakeStream:
    cancelled = False

    def __init__(self, model, messages):
        pass

    def cancel(self):
        pass

    def run(self):
        yield "content", "Voici le code :\n\n```python\n"
        for i in range(1, 46):
            yield "content", f"x{i} = {i}\n"
            time.sleep(0.004)
        yield "content", "```\n\nFin."


mw.client.ChatStream = FakeStream
app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
cid = db.create_conversation("Code", "m")
db.add_message(cid, "user", "Écris du code")
db.add_message(cid, "assistant", "Voici :\n\n```python\n" + CODE + "\n```")
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
pump(500)
from ui.messages import CodeBlock  # noqa: E402

blk = [b for b in win.chat.findChildren(CodeBlock) if b.isVisible()][0]
check("par défaut : le code reste dans la discussion, panneau fermé", not win.code_panel.is_open())
check("bouton « ouvrir sur la droite » présent", blk.open_btn.isVisible() and "droite" in blk.open_btn.toolTip())

blk.open_btn.click()
pump(500)
cp = win.code_panel
check("panneau ouvert à droite", cp.is_open() and cp.maximumWidth() == cp.WIDTH and win.code_handle.isVisible())
check("contenu : langue + nombre de lignes", cp.lang_label.text() == "python" and cp.count_label.text() == "60 lignes")
check("numéros de ligne et code", "ligne 60" in cp.view.toPlainText() and "60" in cp.view.toPlainText())
check("discussion toujours visible à gauche", win.panel.width() > 400)
win.grab().save(str(OUT / "shot_codepanel.png"))

cp.copy_btn.click()
check("copier le code (sans numéros)", QApplication.clipboard().text() == CODE)
dest = Path(tempfile.mkdtemp()) / "mon_code.py"
mw.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(dest), ""))
import ui.code_panel as cpmod  # noqa: E402

cpmod.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(dest), ""))
cp.save_btn.click()
check("enregistrer dans un fichier", dest.exists() and dest.read_text(encoding="utf-8") == CODE)
check("extension selon le langage", extension_for("python") == "py" and extension_for("powershell") == "ps1"
      and extension_for("inconnu") == "txt")

# largeur réglable à la souris
h = win.code_handle
g0 = QPointF(h.mapToGlobal(QPoint(2, 100)))


def send(kind, dx, button=Qt.LeftButton, buttons=Qt.LeftButton):
    QApplication.sendEvent(h, QMouseEvent(kind, QPointF(2, 100), g0 + QPointF(dx, 0), button, buttons, Qt.NoModifier))


send(QEvent.MouseButtonPress, 0)
for s in range(1, 9):
    send(QEvent.MouseMove, -30 * s // 8 * 8 // 8, Qt.NoButton)
send(QEvent.MouseButtonRelease, -120, Qt.LeftButton, Qt.NoButton)
pump(300)
check("largeur réglée à la souris (+120)", cp.panel_width() == cp.WIDTH + 120 or cp.panel_width() > cp.WIDTH)
check("largeur mémorisée", db.get_setting("code_panel_width") == str(cp.panel_width()))

cp.close_btn.click()
pump(500)
check("fermeture", not cp.is_open() and cp.maximumWidth() == 0 and not win.code_handle.isVisible())

# mode automatique : le code long s'ouvre tout seul pendant qu'il s'écrit
check("option désactivée par défaut", not win.code_auto_open)
win._toggle_code_auto()
check("option activée et mémorisée", win.code_auto_open and db.get_setting("code_auto_open") == "1"
      and "activé" in win._code_auto_action.text())
win.new_chat()
pump(300)
win.on_submit("Écris beaucoup de code")
check("code long : le panneau s'ouvre automatiquement", pump(8000, lambda: cp.is_open()))
pump(3000, lambda: win.worker is None and win.assistant is None)
pump(400)
check("mise à jour en direct : le panneau contient tout le code", "x45 = 45" in cp.code() and cp.count_label.text() == "45 lignes")
win.grab().save(str(OUT / "shot_codepanel_auto.png"))

# changer de discussion ferme le panneau
win.open_conversation(cid)
pump(500)
check("changer de discussion ferme le panneau", not cp.is_open())

# option désactivée : un code long ne s'ouvre pas à droite
win._toggle_code_auto()
win.new_chat()
pump(300)
win.on_submit("Encore du code")
pump(3000, lambda: win.worker is None and win.assistant is None)
pump(300)
check("option désactivée : rien ne s'ouvre", not cp.is_open())

# réglages retrouvés au redémarrage
win.close()
win2 = mw.MainWindow(Database(db.path))
check("largeur retrouvée au redémarrage", win2.code_panel.panel_width() == cp.panel_width())
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
