"""Chiffrement des clés API au repos : DPAPI Windows (lié à la session de l'utilisateur)."""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import sys


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    inp = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    ok = (fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)) if encrypt
          else fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)))
    if not ok:
        raise OSError("DPAPI a échoué")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(text: str) -> str:
    raw = text.encode("utf-8")
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
    return "plain:" + base64.b64encode(raw).decode()   # hors Windows : simple encodage (pas de DPAPI)


def unprotect(blob: str) -> str | None:
    try:
        kind, _, b64 = blob.partition(":")
        raw = base64.b64decode(b64)
        if kind == "dpapi":
            raw = _dpapi(raw, False)
        return raw.decode("utf-8")
    except Exception:
        return None
