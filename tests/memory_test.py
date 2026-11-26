"""Test : mémoire de l'IA (capture, envoi au modèle dans une autre discussion, chat éphémère, fenêtre)."""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_mem_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
import memory  # noqa: E402
import system_prompt  # noqa: E402
import ui.main_window as mw  # noqa: E402
from database.db import Database  # noqa: E402
from ui.memory_dialog import MemoryDialog  # noqa: E402

SENT = []


class FakeStream:
    cancelled = False

    def __init__(self, model, messages):
        SENT.append(messages)

    def cancel(self):
        pass

    def run(self):
        yield "content", "d'accord"


mw.client.ChatStream = FakeStream
fails = 0


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


# détection des demandes
check("« souviens-toi que » détecté", memory.extract("Souviens-toi que je m'appelle Sam.") == "je m'appelle Sam")
check("apostrophe typographique et « retiens bien qu' »", memory.extract("Retiens bien qu’il me faut du Python !") == "il me faut du Python")
check("après une première phrase, avec « : »", memory.extract("Salut. Mémorise : mon chien s'appelle Rex") == "mon chien s'appelle Rex")
check("question ordinaire ignorée", memory.extract("Tu te souviens que j'ai un chien ?") is None
      and memory.extract("N'oublie pas de saluer") is None)
merged = system_prompt.with_time([memory.system_block(["je code en Python"]), {"role": "user", "content": "x"}])
check("un seul message système, avec la mémoire", [m["role"] for m in merged] == ["system", "user"]
      and "je code en Python" in merged[0]["content"] and "français" in merged[0]["content"])

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
        time.sleep(0.005)
        if until and until():
            break


def send(text):
    win.on_submit(text)
    pump(2000, lambda: win.worker is None)
    pump(100)
    return SENT[-1]


pump(400)
win.poller.models.disconnect()
win.poller.running.disconnect()
win.running = True
win.models = ["m"]
win.input.set_models(["m"], True)
win.input.set_model("m")

msgs = send("Bonjour")
check("sans souvenir : rien d'ajouté", [m["role"] for m in msgs] == ["user"])
msgs = send("Souviens-toi que je m'appelle Sam")
check("souvenir enregistré", [r["content"] for r in db.list_memories()] == ["je m'appelle Sam"])
check("souvenir envoyé au modèle", msgs[0]["role"] == "system" and "je m'appelle Sam" in msgs[0]["content"])
send("Souviens-toi que je m'appelle Sam")
check("pas de doublon", len(db.list_memories()) == 1)

win.new_chat()
msgs = send("Comment je m'appelle ?")
check("mémoire présente dans une NOUVELLE discussion", "je m'appelle Sam" in msgs[0]["content"] and len(msgs) == 2)
check("la mémoire n'est pas enregistrée dans la discussion", all("Mémoire :" not in m["content"] for m in db.get_path(win.cid)))

win.new_chat()
win.toggle_ephemeral()
msgs = send("Retiens que mon code est 1234")
check("chat éphémère : ni mémoire envoyée ni enregistrée", [m["role"] for m in msgs] == ["user"] and len(db.list_memories()) == 1)
win.toggle_ephemeral()

db.set_setting("memory_enabled", "0")
win.new_chat()
msgs = send("Retiens que j'aime le thé")
check("mémoire désactivée : rien envoyé ni ajouté", [m["role"] for m in msgs] == ["user"] and len(db.list_memories()) == 1)

dlg = MemoryDialog(db, win)
dlg.show()
pump(200)
check("la case reflète le réglage", not dlg.enabled.isChecked())
dlg.enabled.setChecked(True)
check("réactivation enregistrée", db.get_setting("memory_enabled") == "1")
dlg.edit.setText("Je préfère les réponses courtes")
dlg.add()
check("ajout manuel", dlg.list.count() == 2 and len(db.list_memories()) == 2)
dlg.grab().save(str(OUT / "shot_memory.png"))
dlg.list.item(0).setSelected(True)
dlg.delete_selected()
check("suppression", [r["content"] for r in db.list_memories()] == ["Je préfère les réponses courtes"])
dlg.close()

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
