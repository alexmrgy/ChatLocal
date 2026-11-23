"""Page « Comparer deux modèles » : une conversation suivie, deux réponses côte à côte, avec temps et longueur."""
from __future__ import annotations

import time
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from ollama.workers import ChatWorker

from .input_bar import PromptEdit
from .messages import AssistantMessage
from .widgets import IconButton


class _Side(QFrame):
    """Une colonne : nom du modèle et conversation complète (questions + réponses en streaming)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CompareSide")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 8, 8)
        v.setSpacing(4)
        self.title = QLabel(objectName="CompareTitle")
        v.addWidget(self.title)
        self.scroll = QScrollArea(objectName="CompareScroll", widgetResizable=True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget(objectName="CompareBody")
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 8, 8, 8)
        self.body_lay.setSpacing(8)
        self.body_lay.addStretch(1)
        self.scroll.setWidget(self.body)
        v.addWidget(self.scroll, 1)
        self.hint = QLabel("La réponse apparaîtra ici.", objectName="CompareStats")
        self.hint.setAlignment(Qt.AlignCenter)
        self.body_lay.insertWidget(0, self.hint)
        self.history: list[dict] = []              # messages envoyés à CE modèle (questions + ses réponses)
        self.turns: list[QWidget] = []
        self.msg: AssistantMessage | None = None   # réponse en cours (ou dernière réponse)
        self.stats = QLabel(objectName="CompareStats")
        self.question = ""
        self.buffer = ""
        self.dirty = False
        self.t0 = 0.0
        self.first = 0.0
        self.worker: ChatWorker | None = None

    def clear(self, label: str) -> None:
        """Nouvelle conversation : plus aucun message, aucun indicateur de réflexion."""
        self.title.setText(label)
        for w in self.turns:
            self.body_lay.removeWidget(w)
            w.hide()
            w.deleteLater()
        self.turns = []
        self.history = []
        self.msg = None
        self.buffer, self.dirty, self.question = "", False, ""
        self.hint.show()

    def begin_turn(self, question: str) -> None:
        self.question = question
        self._build_turn(question, "En attente…")
        self.buffer, self.dirty = "", False
        self.t0, self.first = time.monotonic(), 0.0
        self._to_end()

    def restore_turn(self, question: str, answer: str, stats: str) -> None:
        """Remet à l'écran un échange enregistré (conversation rouverte depuis l'historique)."""
        self._build_turn(question, stats)
        self.msg.set_text(answer)
        self.msg.finish()           # retire l'indicateur de réflexion même sans réponse
        if answer.strip():
            self.history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        self.buffer = answer

    def _build_turn(self, question: str, stats: str) -> None:
        self.hint.hide()
        bubble_row = QWidget()
        h = QHBoxLayout(bubble_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        bubble = QFrame(objectName="UserBubble")
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 8, 14, 8)
        lab = QLabel(question, wordWrap=True)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(lab)
        bubble.setMaximumWidth(420)
        h.addWidget(bubble)
        self.stats = QLabel(stats, objectName="CompareStats")
        self.msg = AssistantMessage()
        for w in (bubble_row, self.stats, self.msg):
            self.body_lay.insertWidget(self.body_lay.count() - 1, w)
            self.turns.append(w)

    def messages(self, question: str) -> list[dict]:
        return self.history + [{"role": "user", "content": question}]

    def _to_end(self) -> None:
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def on_chunk(self, text: str) -> None:
        if not self.first:
            self.first = time.monotonic() - self.t0
        self.buffer += text
        self.dirty = True

    def flush(self) -> None:
        if self.dirty and self.msg:
            self.dirty = False
            bar = self.scroll.verticalScrollBar()
            at_end = bar.value() >= bar.maximum() - 4
            self.msg.set_text(self.buffer)
            if at_end:
                self._to_end()
        if self.worker is not None and self.t0:
            self.stats.setText(self._stats_text(running=True))

    def _stats_text(self, running: bool) -> str:
        total = time.monotonic() - self.t0
        parts = [f"{total:.1f} s"]
        if self.first:
            parts.append(f"1er mot après {self.first:.1f} s")
        parts.append(f"{len(self.buffer)} caractères")
        return ("⏳ " if running else "✓ ") + " · ".join(parts)

    def finish(self, cancelled: bool) -> None:
        if self.msg:
            self.msg.set_text(self.buffer)
            self.msg.finish()
        self.stats.setText(("⏹ Arrêté · " if cancelled else "") + self._stats_text(running=False).lstrip("⏳✓ "))
        if self.buffer.strip():     # le modèle se souvient de cet échange pour la question suivante
            self.history += [{"role": "user", "content": self.question},
                             {"role": "assistant", "content": self.buffer}]

    def fail(self, msg: str) -> None:
        if self.msg:
            self.flush()
            self.msg.set_error(msg.replace("&", "&amp;").replace("<", "&lt;"))
        self.stats.setText("⚠ Erreur")


class ComparePage(QWidget):
    message = Signal(str)     # message d'information à afficher (toast)
    exchangeDone = Signal()   # un échange (question + 2 réponses) est terminé : à enregistrer

    def __init__(self, parent=None):
        super().__init__(parent)
        # (modèle complet, messages) -> flux ; peut lever ValueError(message) si le modèle n'est pas utilisable
        self.stream_factory: Callable[[str, list], object] | None = None
        self._zombies: list[ChatWorker] = []
        self._running = 0
        self.cid: int | None = None      # conversation enregistrée correspondant à cette comparaison
        self.saved_turns: list[dict] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 14, 24, 18)
        v.setSpacing(12)
        v.addWidget(QLabel("Comparer deux modèles", objectName="Title"))
        v.addWidget(QLabel("Pose une question : les deux modèles répondent en même temps, puis continue la "
                           "conversation.", objectName="Sub"))

        pick = QHBoxLayout()
        pick.setSpacing(12)
        self.combo_a, self.combo_b = QComboBox(objectName="CompareCombo"), QComboBox(objectName="CompareCombo")
        for c in (self.combo_a, self.combo_b):
            c.setMinimumHeight(36)
            c.setCursor(Qt.PointingHandCursor)
        pick.addWidget(self.combo_a, 1)
        vs = QLabel("VS", objectName="CompareVs")
        vs.setAlignment(Qt.AlignCenter)
        pick.addWidget(vs)
        pick.addWidget(self.combo_b, 1)
        self.new_btn = QPushButton("Nouvelle comparaison", objectName="Action")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setMinimumHeight(36)
        self.new_btn.clicked.connect(self.reset_all)
        pick.addWidget(self.new_btn)
        v.addLayout(pick)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        self.side_a, self.side_b = _Side(), _Side()
        cols.addWidget(self.side_a, 1)
        cols.addWidget(self.side_b, 1)
        v.addLayout(cols, 1)

        bar = QFrame(objectName="InputBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 7, 8, 7)
        bl.setSpacing(6)
        self.edit = PromptEdit()
        self.edit.setPlaceholderText("Ta question pour les deux modèles")
        self.edit.submit.connect(self.run)
        self.send = IconButton("arrow_up", size=(32, 32), icon_size=19, fg="#181818", fg_hover="#181818",
                               bg="#ececec", bg_hover="#ffffff", tooltip="Comparer (Entrée)")
        self.send.clicked.connect(self._on_send)
        bl.addWidget(self.edit, 1, Qt.AlignVCenter)
        bl.addWidget(self.send, 0, Qt.AlignBottom)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        bar.setMaximumWidth(760)
        wrap.addWidget(bar, 1000)
        wrap.addStretch(1)
        v.addLayout(wrap)

        self.timer = QTimer(self, interval=60, timeout=self._tick)
        self.combo_a.currentIndexChanged.connect(lambda _: self.reset_all())
        self.combo_b.currentIndexChanged.connect(lambda _: self.reset_all())
        self.reset_all()

    def reset_all(self) -> None:
        """Nouvelle comparaison : on repart d'une conversation vide pour les deux modèles."""
        if self.busy():
            return
        self.cid, self.saved_turns = None, []
        self.side_a.clear(self.combo_a.currentText() or "Modèle A")
        self.side_b.clear(self.combo_b.currentText() or "Modèle B")

    # ----- modèles -----
    def set_models(self, models: list[tuple[str, str]], prefer: str = "") -> None:
        """models : [(identifiant complet, nom affiché)]. Garde les choix actuels s'ils existent encore."""
        keep = [self.combo_a.currentData(), self.combo_b.currentData()]
        for c in (self.combo_a, self.combo_b):
            c.blockSignals(True)
            c.clear()
            for full, label in models:
                c.addItem(label, full)
        ids = [m[0] for m in models]
        a = keep[0] if keep[0] in ids else (prefer if prefer in ids else (ids[0] if ids else None))
        b = keep[1] if keep[1] in ids and keep[1] != a else next((i for i in ids if i != a), a)
        for c, want in ((self.combo_a, a), (self.combo_b, b)):
            if want is not None:
                c.setCurrentIndex(ids.index(want))
        for c in (self.combo_a, self.combo_b):
            c.blockSignals(False)
        if keep != [self.combo_a.currentData(), self.combo_b.currentData()]:   # même choix : la conversation continue
            self.reset_all()

    def snapshot(self) -> dict:
        """Données à enregistrer dans l'historique."""
        return {"a": self.combo_a.currentData(), "b": self.combo_b.currentData(), "turns": self.saved_turns}

    def restore(self, cid: int, data: dict, names: dict[str, str]) -> None:
        """Rouvre une comparaison enregistrée. names : identifiant -> nom affiché (pour les modèles disparus)."""
        self.cancel()
        a, b = data.get("a"), data.get("b")
        for combo, mid in ((self.combo_a, a), (self.combo_b, b)):
            combo.blockSignals(True)
            if mid and combo.findData(mid) < 0:
                combo.addItem(names.get(mid, mid), mid)
            if mid:
                combo.setCurrentIndex(combo.findData(mid))
            combo.blockSignals(False)
        self.side_a.clear(self.combo_a.currentText() or "Modèle A")
        self.side_b.clear(self.combo_b.currentText() or "Modèle B")
        self.saved_turns = []
        for t in data.get("turns", []):
            q = str(t.get("q", ""))
            self.side_a.restore_turn(q, str(t.get("a", "")), str(t.get("sa", "")))
            self.side_b.restore_turn(q, str(t.get("b", "")), str(t.get("sb", "")))
            self.saved_turns.append(t)
        self.cid = cid
        self.side_a._to_end()
        self.side_b._to_end()

    # ----- exécution -----
    def busy(self) -> bool:
        return self._running > 0

    def _on_send(self) -> None:
        if self.busy():
            self.cancel()
        else:
            self.run()

    def run(self) -> None:
        if self.busy():
            return
        text = self.edit.toPlainText().strip()
        a, b = self.combo_a.currentData(), self.combo_b.currentData()
        if not text:
            return
        if not a or not b:
            self.message.emit("Aucun modèle disponible. Lance Ollama ou ajoute une clé NVIDIA.")
            return
        if a == b:
            self.message.emit("Choisis deux modèles différents.")
            return
        streams = []
        try:
            for full, side in ((a, self.side_a), (b, self.side_b)):
                streams.append(self.stream_factory(full, side.messages(text)))
        except ValueError as e:
            self.message.emit(str(e))
            return
        self.edit.clear()
        for side, stream in ((self.side_a, streams[0]), (self.side_b, streams[1])):
            side.begin_turn(text)
            w = ChatWorker(stream, self)
            side.worker = w
            w.content.connect(side.on_chunk)
            w.failed.connect(side.fail)
            w.done.connect(lambda cancelled, s=side: self._done(s, cancelled))
            self._running += 1
            w.start()
        self._set_busy(True)

    def _done(self, side: _Side, cancelled: bool) -> None:
        w, side.worker = side.worker, None
        side.finish(cancelled)
        self._running = max(0, self._running - 1)
        if w:
            self._zombies.append(w)
            w.finished.connect(lambda w=w: self._zombies.remove(w) if w in self._zombies else None)
            w.finished.connect(w.deleteLater)
        if not self._running:
            self._set_busy(False)
            a, b = self.side_a, self.side_b
            if a.buffer.strip() or b.buffer.strip():
                self.saved_turns.append({"q": a.question, "a": a.buffer, "b": b.buffer,
                                         "sa": a.stats.text(), "sb": b.stats.text()})
                self.exchangeDone.emit()

    def _set_busy(self, on: bool) -> None:
        self.combo_a.setEnabled(not on)
        self.combo_b.setEnabled(not on)
        self.new_btn.setEnabled(not on)
        if on:
            self.send.set_icon("stop")
            self.send.setToolTip("Arrêter")
            self.timer.start()
        else:
            self.send.set_icon("arrow_up")
            self.send.setToolTip("Comparer (Entrée)")
            self.timer.stop()
            self.side_a.flush()
            self.side_b.flush()

    def _tick(self) -> None:
        self.side_a.flush()
        self.side_b.flush()

    def cancel(self) -> None:
        for side in (self.side_a, self.side_b):
            if side.worker is not None:
                side.worker.cancel()

    def hideEvent(self, e) -> None:
        self.cancel()           # on quitte la page : on arrête les deux réponses
        super().hideEvent(e)
