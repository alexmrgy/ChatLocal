"""Test : fichiers joints (texte et image) -> pastilles -> envoi au modèle -> enregistrement -> rechargement."""
import base64
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
TMP = Path(tempfile.mkdtemp(prefix="chatlocal_att_"))
os.environ["CHATLOCAL_DATA_DIR"] = str(TMP / "data")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import attachments  # noqa: E402
import main as app_main  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402

SENT = []


class FakeStream:
    cancelled = False

    def __init__(self, model, messages):
        SENT.append(messages)

    def cancel(self):
        pass

    def run(self):
        yield "content", "réponse de test"


mw.client.ChatStream = FakeStream

# fichiers de test
txt = TMP / "notes.txt"
txt.write_text("ligne un\nligne deux é", encoding="utf-8")
png = TMP / "pixel.png"
png.write_bytes(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
binf = TMP / "data.bin"
binf.write_bytes(b"\x00\x01\x02binaire")

fails = 0


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


# 1) module attachments
f = attachments.read_file(txt)
check("fichier texte lu", f["kind"] == "text" and "ligne deux é" in f["data"])
check("image encodée en base64", attachments.read_file(png)["kind"] == "image")
try:
    attachments.read_file(binf)
    check("fichier binaire refusé", False)
except attachments.AttachmentError:
    check("fichier binaire refusé", True)
check("texte joint avant la question", attachments.with_files("Résume", [f]).endswith("Résume")
      and "notes.txt" in attachments.with_files("Résume", [f]))

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
win = mw.MainWindow(db)
win.show()


def pump(ms, until=None):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.01)
        if until and until():
            return True
    return until() if until else True


pump(500)
win.running = True
win.models = ["m"]
win.input.set_model("m")
win.poller.models.disconnect()
win.poller.running.disconnect()

# 2) ajout dans la barre de saisie
rejected = []
win.input.filesRejected.connect(rejected.append)
win.input.add_paths([str(txt), str(png), str(binf)])
pump(200)
check("2 fichiers joints, binaire refusé", len(win.input.files()) == 2 and len(rejected) == 1)
check("pastilles affichées", win.input.files_row.isVisible())
win.grab().save(str(OUT / "shot_files_input.png"))

# 3) envoi
win.on_submit("Que contient ce fichier ?")
pump(800, lambda: win.worker is None and win.assistant is None)
last = SENT[-1][-1]
check("le texte du fichier part vers le modèle", "ligne un" in last["content"] and last["content"].endswith("Que contient ce fichier ?"))
check("l'image part dans « images »", len(last.get("images", [])) == 1)
check("fichiers retirés après l'envoi", win.input.files() == [] and not win.input.files_row.isVisible())
cid = win.cid
saved = db.get_path(cid)[0]
check("fichiers enregistrés avec le message", [x["name"] for x in saved["files"]] == ["notes.txt", "pixel.png"])
pump(700)
win.grab().save(str(OUT / "shot_files_chat.png"))

# 4) rechargement de la conversation
win.new_chat()
pump(200)
win.open_conversation(cid, force=True)
pump(400)
check("fichiers conservés après rechargement", [x["name"] for x in win.history[0]["files"]] == ["notes.txt", "pixel.png"])
msg = win._model_msg(win.history[0])
check("fichiers toujours envoyés au modèle après rechargement", "ligne un" in msg["content"] and "images" in msg)

# 5) fichier seul, sans texte
win.input.add_paths([str(txt)])
win.input._on_submit()
pump(800, lambda: win.worker is None and win.assistant is None)
check("fichier seul : question par défaut", SENT[-1][-1]["content"].endswith("Analyse le fichier joint."))

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
