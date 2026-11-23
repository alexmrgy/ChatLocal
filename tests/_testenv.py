"""Aides communes aux tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def default_model() -> str:
    """Un modèle Ollama réellement installé (les modèles du PC changent : on ne fige rien)."""
    from ollama import client
    models = client.list_models()
    for pref in ("gemma4:e2b", "phi4-mini:latest"):
        if pref in models:
            return pref
    return models[0]
