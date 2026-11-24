"""Client REST Ollama (stdlib uniquement, aucune dépendance Qt)."""
from __future__ import annotations

import http.client
import json
import os
import threading
from typing import Iterator
from urllib.parse import urlparse

import system_prompt

BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if "://" not in BASE_URL:
    BASE_URL = "http://" + BASE_URL


class OllamaError(Exception):
    """Erreur de communication avec Ollama (message lisible pour l'utilisateur)."""


def _conn(timeout: float, base: str = BASE_URL) -> http.client.HTTPConnection:
    u = urlparse(base)
    return http.client.HTTPConnection(u.hostname or "localhost", u.port or 11434, timeout=timeout)


def list_models(base: str = BASE_URL, timeout: float = 3.0) -> list[str]:
    """GET /api/tags -> noms exacts des modèles installés."""
    conn = _conn(timeout, base)
    try:
        conn.request("GET", "/api/tags")
        resp = conn.getresponse()
        data = resp.read()
        if resp.status != 200:
            raise OllamaError(f"Ollama a répondu HTTP {resp.status}")
        return [m["name"] for m in json.loads(data).get("models", [])]
    except OllamaError:
        raise
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise OllamaError(f"Ollama injoignable sur {base} ({e})") from e
    finally:
        conn.close()


KEEP_ALIVE = "30m"   # le modèle reste chargé en mémoire : plus de rechargement (lent) entre deux messages


def delete_model(name: str, base: str = BASE_URL, timeout: float = 30.0) -> None:
    """DELETE /api/delete : supprime le modèle du disque."""
    conn = _conn(timeout, base)
    try:
        conn.request("DELETE", "/api/delete", body=json.dumps({"model": name}),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", "replace")
        if resp.status != 200:
            try:
                data = json.loads(data).get("error", data)
            except ValueError:
                pass
            raise OllamaError(f"Suppression impossible (HTTP {resp.status}) : {data}")
    except OllamaError:
        raise
    except (OSError, http.client.HTTPException) as e:
        raise OllamaError(f"Ollama injoignable sur {base} ({e})") from e
    finally:
        conn.close()


def warm_up(name: str, base: str = BASE_URL) -> None:
    """Charge le modèle en mémoire à l'avance (requête vide) pour que la 1re réponse soit immédiate."""
    conn = _conn(120, base)
    try:
        conn.request("POST", "/api/generate", body=json.dumps({"model": name, "keep_alive": KEEP_ALIVE}),
                     headers={"Content-Type": "application/json"})
        conn.getresponse().read()
    except (OSError, http.client.HTTPException):
        pass
    finally:
        conn.close()


class ChatStream:
    """POST /api/chat en streaming. Itérer sur run() ; cancel() est thread-safe."""

    def __init__(self, model: str, messages: list[dict], base: str = BASE_URL):
        self.model = model
        self.messages = messages
        self.base = base
        self._conn: http.client.HTTPConnection | None = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        c = self._conn
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def run(self) -> Iterator[tuple[str, str]]:
        """Produit ('thinking'|'content', texte)."""
        body = json.dumps({"model": self.model, "messages": system_prompt.with_time(self.messages), "stream": True,
                           "keep_alive": KEEP_ALIVE})
        conn = self._conn = _conn(600, self.base)
        try:
            conn.request("POST", "/api/chat", body=body, headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                raw = resp.read().decode("utf-8", "replace")
                try:
                    raw = json.loads(raw).get("error", raw)
                except ValueError:
                    pass
                raise OllamaError(f"Ollama (HTTP {resp.status}) : {raw}")
            while not self._cancelled.is_set():
                line = resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if "error" in obj:
                    raise OllamaError(str(obj["error"]))
                msg = obj.get("message") or {}
                if msg.get("thinking"):
                    yield "thinking", msg["thinking"]
                if msg.get("content"):
                    yield "content", msg["content"]
                if obj.get("done"):
                    break
        except OllamaError:
            raise
        except (OSError, http.client.HTTPException) as e:
            if self._cancelled.is_set():
                return
            raise OllamaError(f"Connexion à Ollama perdue ({e})") from e
        finally:
            try:
                conn.close()
            except Exception:
                pass
