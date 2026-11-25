"""Threads Qt qui isolent les appels réseau Ollama de l'interface."""
from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from claude_api import client as claude_client
from claude_api.client import ClaudeError
from nvidia import client as nvidia_client
from nvidia.client import NvidiaError

from . import client


class ChatWorker(QThread):
    content = Signal(str)
    thinking = Signal()
    failed = Signal(str)
    # finished (QThread) est émis à la fin ; done porte l'état d'annulation
    done = Signal(bool)

    def __init__(self, stream, parent=None):
        """stream : ollama.client.ChatStream ou nvidia.client.ChatStream (run/cancel/cancelled)."""
        super().__init__(parent)
        self._stream = stream

    def cancel(self) -> None:
        self._stream.cancel()

    def run(self) -> None:
        try:
            for kind, text in self._stream.run():
                if kind == "content":
                    self.content.emit(text)
                else:
                    self.thinking.emit()
        except (client.OllamaError, NvidiaError, ClaudeError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # filet de sécurité : ne jamais tuer le thread en silence
            self.failed.emit(f"Erreur inattendue : {e}")
        self.done.emit(self._stream.cancelled)


class CallWorker(QThread):
    """Exécute une fonction bloquante hors du thread UI (suppression, préchauffage de modèle…)."""
    ok = Signal()
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self._fn()
        except client.OllamaError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:
            self.failed.emit(f"Erreur inattendue : {e}")
            return
        self.ok.emit()


class NvidiaModelsWorker(QThread):
    """Vérifie une clé NVIDIA en récupérant la liste des modèles (une seule requête)."""
    ok = Signal(str, list)      # (clé, modèles)
    failed = Signal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key

    def run(self) -> None:
        try:
            self.ok.emit(self._key, nvidia_client.list_models(self._key))
        except NvidiaError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Erreur inattendue : {type(e).__name__}")


class ClaudeModelsWorker(QThread):
    """Vérifie une clé API Claude en récupérant la liste des modèles (une seule requête)."""
    ok = Signal(str, list)      # (clé, modèles)
    failed = Signal(str)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key

    def run(self) -> None:
        try:
            self.ok.emit(self._key, claude_client.list_models(self._key))
        except ClaudeError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Erreur inattendue : {type(e).__name__}")


class ModelsPoller(QThread):
    """Interroge /api/tags périodiquement ; émet seulement quand l'état change."""
    models = Signal(list)
    running = Signal(bool)

    def __init__(self, interval: float = 4.0, parent=None):
        super().__init__(parent)
        self._interval = interval
        self._wake = threading.Event()
        self._stop = threading.Event()

    def refresh(self) -> None:
        self._last = None  # force la ré-émission
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def run(self) -> None:
        self._last = None
        while not self._stop.is_set():
            try:
                state = (True, client.list_models())
            except client.OllamaError:
                state = (False, [])
            if state != self._last:
                self._last = state
                self.running.emit(state[0])
                self.models.emit(state[1])
            self._wake.wait(self._interval)
            self._wake.clear()
