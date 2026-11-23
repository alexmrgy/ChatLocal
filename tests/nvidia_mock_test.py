"""Test du client NVIDIA contre un faux serveur local compatible OpenAI (aucune vraie clé nécessaire)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mock_nvidia  # noqa: E402

GOOD = _mock_nvidia.GOOD
_mock_nvidia.start()

from nvidia import client  # noqa: E402
from database import secrets  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


ms = client.list_models(GOOD)
check("liste filtrée (embedding exclu)", ms == ["meta/llama-3.1-8b-instruct", "mistralai/mistral-7b-instruct"])
try:
    client.list_models("mauvaise")
    check("clé invalide refusée", False)
except client.NvidiaError as e:
    check("clé invalide refusée", "refusée" in str(e) and "mauvaise" not in str(e))
out = "".join(t for k, t in client.ChatStream(GOOD, "meta/llama-3.1-8b-instruct", [{"role": "user", "content": "hi"}]).run() if k == "content")
check("streaming SSE", out == "Bonjour !")
enc = secrets.protect(GOOD)
check("chiffrement DPAPI (aller-retour, non lisible)", secrets.unprotect(enc) == GOOD and GOOD not in enc)
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
