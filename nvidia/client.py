"""Client NVIDIA (API NIM compatible OpenAI) : liste des modèles + chat en streaming SSE.

Aucune dépendance Qt. La clé n'est jamais journalisée ni incluse dans les messages d'erreur.
"""
from __future__ import annotations

import http.client
import json
import os
import threading
from typing import Iterator
from urllib.parse import urlparse

import clock

BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
PREFIX = "nvidia:"   # préfixe d'un identifiant de modèle NVIDIA dans l'app

# modèles non conversationnels exclus de la liste
_EXCLUDE = ("embed", "rerank", "reward", "guard", "safety", "parse", "retriev", "clip", "classif", "nemoguard")


class NvidiaError(Exception):
    """Erreur lisible par l'utilisateur."""


def _connect(timeout: float):
    u = urlparse(BASE_URL)
    https = u.scheme == "https"
    cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    return cls(u.hostname or "localhost", u.port or (443 if https else 80), timeout=timeout), u.path


def _headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}


def _http_error(status: int, raw: bytes) -> NvidiaError:
    if status in (401, 403):
        return NvidiaError(f"Clé API NVIDIA refusée (HTTP {status}). Vérifie qu'elle est valide.")
    if status == 429:
        return NvidiaError("NVIDIA : trop de requêtes (HTTP 429). Réessaie dans un instant.")
    detail = ""
    try:
        obj = json.loads(raw.decode("utf-8", "replace"))
        detail = obj.get("detail") or (obj.get("error") or {}).get("message") or ""
        if isinstance(detail, list):
            detail = str(detail[0])
    except (ValueError, AttributeError):
        pass
    return NvidiaError(f"NVIDIA (HTTP {status}) {detail}".strip())


def list_models(key: str, timeout: float = 20.0) -> list[str]:
    conn, path = _connect(timeout)
    try:
        conn.request("GET", path + "/models", headers=_headers(key))
        resp = conn.getresponse()
        data = resp.read()
        if resp.status != 200:
            raise _http_error(resp.status, data)
        ids = [m["id"] for m in json.loads(data).get("data", []) if "id" in m]
        return sorted({i for i in ids if not any(x in i.lower() for x in _EXCLUDE)})
    except NvidiaError:
        raise
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise NvidiaError(f"NVIDIA injoignable ({type(e).__name__}). Vérifie ta connexion.") from e
    finally:
        conn.close()


class ChatStream:
    """POST /chat/completions en streaming. Même interface que ollama.client.ChatStream."""

    def __init__(self, key: str, model: str, messages: list[dict]):
        self._key, self.model, self.messages = key, model, messages
        self._conn = None
        self._cancelled = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()
        c = self._conn
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def run(self) -> Iterator[tuple[str, str]]:
        body = json.dumps({"model": self.model, "messages": clock.with_time(self.messages), "stream": True,
                           "max_tokens": 4096})
        conn, path = _connect(600)
        self._conn = conn
        try:
            headers = {**_headers(self._key), "Accept": "text/event-stream"}
            conn.request("POST", path + "/chat/completions", body=body, headers=headers)
            resp = conn.getresponse()
            if resp.status != 200:
                raise _http_error(resp.status, resp.read())
            while not self._cancelled.is_set():
                line = resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                if "error" in obj:
                    err = obj["error"]
                    raise NvidiaError(str(err.get("message") if isinstance(err, dict) else err))
                for ch in obj.get("choices", []):
                    delta = ch.get("delta") or {}
                    if delta.get("reasoning_content") or delta.get("reasoning"):
                        yield "thinking", ""
                    if delta.get("content"):
                        yield "content", delta["content"]
        except NvidiaError:
            raise
        except (OSError, http.client.HTTPException) as e:
            if self._cancelled.is_set():
                return
            raise NvidiaError(f"Connexion à NVIDIA perdue ({type(e).__name__}).") from e
        finally:
            try:
                conn.close()
            except Exception:
                pass
