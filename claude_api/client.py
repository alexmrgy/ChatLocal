"""Client Claude (API Anthropic, clé API console.anthropic.com) : liste des modèles + chat en streaming SSE.

Aucune dépendance Qt. La clé n'est jamais journalisée ni incluse dans les messages d'erreur.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import threading
from typing import Iterator
from urllib.parse import urlparse

import system_prompt

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
PREFIX = "claude:"          # préfixe d'un identifiant de modèle Claude dans l'app
API_VERSION = "2023-06-01"
MAX_TOKENS = 8192

DISPLAY_NAMES: dict[str, str] = {}   # id du modèle -> nom lisible (rempli par list_models)


class ClaudeError(Exception):
    """Erreur lisible par l'utilisateur."""


def _connect(timeout: float):
    u = urlparse(BASE_URL)
    https = u.scheme == "https"
    cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    return cls(u.hostname or "localhost", u.port or (443 if https else 80), timeout=timeout), u.path


def _headers(key: str) -> dict:
    return {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}


def _http_error(status: int, raw: bytes) -> ClaudeError:
    if status in (401, 403):
        return ClaudeError(f"Clé API Claude refusée (HTTP {status}). Vérifie qu'elle est valide.")
    if status == 429:
        return ClaudeError("Claude : trop de requêtes ou quota atteint (HTTP 429). Réessaie dans un instant.")
    if status == 529:
        return ClaudeError("Claude est surchargé (HTTP 529). Réessaie dans un instant.")
    detail = ""
    try:
        obj = json.loads(raw.decode("utf-8", "replace"))
        detail = (obj.get("error") or {}).get("message") or ""
    except (ValueError, AttributeError):
        pass
    return ClaudeError(f"Claude (HTTP {status}) {detail}".strip())


def list_models(key: str, timeout: float = 20.0) -> list[str]:
    """GET /v1/models -> identifiants des modèles (les plus récents d'abord)."""
    conn, path = _connect(timeout)
    try:
        conn.request("GET", path + "/v1/models?limit=100", headers=_headers(key))
        resp = conn.getresponse()
        data = resp.read()
        if resp.status != 200:
            raise _http_error(resp.status, data)
        items = [m for m in json.loads(data).get("data", []) if "id" in m]
        for m in items:
            if m.get("display_name"):
                DISPLAY_NAMES[m["id"]] = m["display_name"]
        return [m["id"] for m in items]
    except ClaudeError:
        raise
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise ClaudeError(f"Claude injoignable ({type(e).__name__}). Vérifie ta connexion.") from e
    finally:
        conn.close()


def _media_type(b64: str) -> str:
    try:
        head = base64.b64decode(b64[:48] + "=" * (-len(b64[:48]) % 4))
    except Exception:
        return "image/png"
    if head.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def build_request(messages: list[dict]) -> tuple[str, list[dict]]:
    """Sépare le message système et convertit les messages (images comprises) au format Anthropic."""
    system, out = [], []
    for m in system_prompt.with_time(messages):
        role, content = m.get("role"), m.get("content", "")
        if role == "system":
            system.append(str(content))
            continue
        if role not in ("user", "assistant"):
            continue
        imgs = m.get("images") or []
        if imgs and role == "user":
            blocks = [{"type": "image", "source": {"type": "base64", "media_type": _media_type(i), "data": i}}
                      for i in imgs]
            blocks.append({"type": "text", "text": str(content) or "Décris cette image."})
            out.append({"role": role, "content": blocks})
        elif str(content).strip():
            out.append({"role": role, "content": str(content)})
    return "\n\n".join(system), out


class ChatStream:
    """POST /v1/messages en streaming. Même interface que ollama.client.ChatStream."""

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
        system, msgs = build_request(self.messages)
        body = json.dumps({"model": self.model, "max_tokens": MAX_TOKENS, "stream": True,
                           "system": system, "messages": msgs})
        conn, path = _connect(600)
        self._conn = conn
        try:
            headers = {**_headers(self._key), "accept": "text/event-stream"}
            conn.request("POST", path + "/v1/messages", body=body, headers=headers)
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
                try:
                    obj = json.loads(line[5:].strip())
                except ValueError:
                    continue
                kind = obj.get("type")
                if kind == "error":
                    err = obj.get("error") or {}
                    raise ClaudeError(str(err.get("message") or err or "erreur"))
                if kind == "content_block_delta":
                    delta = obj.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield "content", delta["text"]
                    elif delta.get("type") == "thinking_delta":
                        yield "thinking", ""
                elif kind == "message_stop":
                    break
        except ClaudeError:
            raise
        except (OSError, http.client.HTTPException) as e:
            if self._cancelled.is_set():
                return
            raise ClaudeError(f"Connexion à Claude perdue ({type(e).__name__}).") from e
        finally:
            try:
                conn.close()
            except Exception:
                pass
