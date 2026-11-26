"""Mémoire de l'IA : informations à retenir d'une conversation à l'autre (stockées localement)."""
from __future__ import annotations

import re

MAX_LEN = 500          # longueur maximale d'un souvenir
MAX_ITEMS = 100        # au-delà, seuls les plus récents sont envoyés au modèle

# « souviens-toi que… », « retiens que… », « mémorise : … », « n'oublie pas que… » en début de phrase
_TRIGGER = re.compile(
    r"(?:^|[.!?\n]\s*)"
    r"(?:(?:s'il te pla[iî]t|stp)[\s,]+)?"
    r"(?:souviens[- ]toi|rappelle[- ]toi|retiens|m[ée]morise|n'oublie pas|note)"
    r"(?:\s+bien)?"
    r"(?:\s+(?:que\s+|qu')|\s*[:,]\s*)"
    r"([^\n]+)",
    re.IGNORECASE,
)


def extract(text: str) -> str | None:
    """Renvoie l'information à retenir si le message le demande, sinon None."""
    m = _TRIGGER.search(text.replace("’", "'"))
    if not m:
        return None
    fact = m.group(1).strip().rstrip(" .!;,")
    return fact[:MAX_LEN] or None


def system_block(facts: list[str]) -> dict | None:
    """Message système qui communique les souvenirs au modèle (None si la mémoire est vide)."""
    if not facts:
        return None
    lines = "\n".join(f"- {f}" for f in facts[-MAX_ITEMS:])
    return {"role": "system", "content": (
        "Mémoire : informations que l'utilisateur t'a demandé de retenir lors de conversations précédentes "
        "(les « je » et « mon » désignent l'utilisateur). Sers-t'en quand c'est utile, sans les réciter "
        f"inutilement.\n{lines}")}
