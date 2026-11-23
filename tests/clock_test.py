"""Test : l'heure de l'ordinateur est transmise aux modèles (message système) à chaque requête."""
import json
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clock  # noqa: E402
from ollama import client  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


fixed = datetime(2026, 11, 23, 14, 5, 9)
txt = clock.now_text(fixed)
check("date en français", txt.startswith("lundi 23 novembre 2026, 14:05:09"))
msgs = [{"role": "user", "content": "Quelle heure est-il ?"}]
out = clock.with_time(msgs, fixed)
check("message système placé en tête", out[0]["role"] == "system" and out[1] == msgs[0] and len(msgs) == 1)
check("consigne de répondre avec l'heure", "14:05:09" in out[0]["content"] and "heure" in out[0]["content"])

# requête réelle vers un faux serveur Ollama : le corps contient l'heure courante
BODIES = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        BODIES.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write((json.dumps({"message": {"content": "ok"}, "done": True}) + "\n").encode())

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
list(client.ChatStream("m", msgs, base=f"http://127.0.0.1:{srv.server_port}").run())
sent = BODIES[0]["messages"]
now_year = str(datetime.now().year)
check("la requête Ollama contient l'heure de l'ordinateur", sent[0]["role"] == "system" and now_year in sent[0]["content"]
      and datetime.now().strftime("%H:") in sent[0]["content"])
check("la question de l'utilisateur suit", sent[-1] == msgs[0] and len(sent) == 2)

print("RÉSULTAT :", "SUCCÈS" if not fails else f"{fails} ÉCHEC(S)")
os._exit(1 if fails else 0)
