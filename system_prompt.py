"""Consignes envoyées à tous les modèles : heure du PC, réponses en français, emojis."""
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


STYLE = (
    "Réponds TOUJOURS en français, même si la question est posée dans une autre langue ; "
    "ne change de langue que si l'utilisateur demande explicitement une traduction ou une autre langue. "
    "Le code, les commandes, les noms techniques et les citations restent inchangés. "
    "Rends tes réponses vivantes avec des emojis pertinents qui correspondent au sujet : "
    "un emoji au début des titres et des points de liste, et quelques-uns dans le texte "
    "(environ un à trois par paragraphe), variés et jamais au hasard. N'en mets jamais dans les blocs de code. "
    "Dans le code que tu écris (tout bloc de code) : n'écris AUCUN commentaire (ni # ni // ni /* */ ni docstring "
    "ni commentaire HTML) et n'utilise AUCUN emoji, ni dans le code, ni dans les chaînes de caractères, ni dans "
    "les messages affichés par le programme ; donne uniquement le code, propre et sans annotation. "
    "Explique si besoin en dehors du bloc de code, dans le texte de ta réponse."
)


def system_message(now: datetime | None = None) -> dict:
    return {"role": "system", "content": (
        f"{STYLE}\n\n"
        f"Date et heure actuelles : {now_text(now)}. "
        "Si l'utilisateur te demande l'heure ou la date, réponds avec ces informations exactes, "
        "sans dire que tu n'y as pas accès.")}


def with_time(messages: list[dict], now: datetime | None = None) -> list[dict]:
    """Ajoute le message système avec l'heure, en tête (sans modifier la liste d'origine).

    Les autres messages système (mémoire…) sont fusionnés dedans : certains modèles n'en lisent qu'un.
    """
    head = system_message(now)
    extra = [m["content"] for m in messages if m["role"] == "system"]
    if extra:
        head["content"] = "\n\n".join([head["content"], *extra])
    return [head] + [m for m in messages if m["role"] != "system"]
