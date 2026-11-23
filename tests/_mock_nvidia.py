"""Faux serveur NVIDIA (API compatible OpenAI) pour les tests : démarre sur un port libre."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

GOOD = "nvapi-test-key"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        if self.headers.get("Authorization") != f"Bearer {GOOD}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"detail":"nope"}')
            return False
        return True

    def do_GET(self):
        if self._auth() and self.path == "/v1/models":
            body = json.dumps({"data": [{"id": "meta/llama-3.1-8b-instruct"}, {"id": "nvidia/nv-embedqa-e5-v5"},
                                        {"id": "mistralai/mistral-7b-instruct"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if not self._auth():
            return
        n = int(self.headers["Content-Length"])
        req = json.loads(self.rfile.read(n))
        assert req["stream"] is True and req["model"] == "meta/llama-3.1-8b-instruct"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for part in ("Bon", "jour", " !"):
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": part}}]}).encode() + b"\n\n")
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")


def start():
    srv = HTTPServer(("127.0.0.1", 0), H)
    os.environ["NVIDIA_BASE_URL"] = f"http://127.0.0.1:{srv.server_port}/v1"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

