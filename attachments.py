"""Fichiers joints aux messages : lecture, limites, mise en forme pour le modèle.

Un fichier joint est un dict {"name": str, "kind": "text" | "image", "data": str}
(texte du fichier, ou image encodée en base64).
"""
from __future__ import annotations

import base64
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_TEXT = 300_000          # caractères de texte conservés par fichier
MAX_TEXT_FILE = 2_000_000   # octets lus au maximum pour un fichier texte
MAX_IMAGE = 8_000_000       # octets pour une image
MAX_FILES = 8


class AttachmentError(Exception):
    pass


def read_file(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise AttachmentError(f"« {p.name} » n'est pas un fichier.")
    size = p.stat().st_size
    if p.suffix.lower() in IMAGE_EXT:
        if size > MAX_IMAGE:
            raise AttachmentError(f"« {p.name} » est trop lourde (max {MAX_IMAGE // 1_000_000} Mo).")
        return {"name": p.name, "kind": "image", "data": base64.b64encode(p.read_bytes()).decode("ascii")}
    if size > MAX_TEXT_FILE:
        raise AttachmentError(f"« {p.name} » est trop volumineux (max {MAX_TEXT_FILE // 1_000_000} Mo).")
    raw = p.read_bytes()
    if b"\x00" in raw[:8192]:
        raise AttachmentError(f"« {p.name} » n'est pas un fichier texte (PDF, Word, archive… non pris en charge).")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise AttachmentError(f"« {p.name} » n'est pas lisible comme du texte.")
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n… [fichier tronqué]"
    return {"name": p.name, "kind": "text", "data": text}


def with_files(content: str, files: list[dict]) -> str:
    """Texte envoyé au modèle : le contenu des fichiers texte est placé avant la question."""
    blocks = [f'Fichier joint « {f["name"]} » :\n"""\n{f["data"]}\n"""' for f in files if f["kind"] == "text"]
    return "\n\n".join(blocks + [content]) if blocks else content


def images(files: list[dict]) -> list[str]:
    return [f["data"] for f in files if f["kind"] == "image"]
