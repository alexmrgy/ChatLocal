"""Heure de l'ordinateur, communiquée aux modèles pour qu'ils puissent répondre à « quelle heure est-il ? »."""
from __future__ import annotations

from datetime import datetime

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def now_text(now: datetime | None = None) -> str:
    n = (now or datetime.now()).astimezone()
    off = n.utcoffset()
    minutes = int(off.total_seconds() // 60) if off else 0
    sign = "+" if minutes >= 0 else "-"
    zone = f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
    return (f"{JOURS[n.weekday()]} {n.day} {MOIS[n.month - 1]} {n.year}, {n:%H:%M:%S} "
            f"(heure de l'ordinateur de l'utilisateur, fuseau {zone})")


def system_message(now: datetime | None = None) -> dict:
    return {"role": "system", "content": (
        f"Date et heure actuelles : {now_text(now)}. "
        "Si l'utilisateur te demande l'heure ou la date, réponds avec ces informations exactes, "
        "dans sa langue, sans dire que tu n'y as pas accès.")}


def with_time(messages: list[dict], now: datetime | None = None) -> list[dict]:
    """Ajoute le message système avec l'heure, en tête (sans modifier la liste d'origine)."""
    return [system_message(now)] + list(messages)
