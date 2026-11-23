"""Fenêtre principale : assemble l'UI et orchestre Ollama + SQLite."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import html
import json
import os
import sys

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

import attachments
from database.db import Database
from database.db import _load_files as load_files
from nvidia import client as nvidia_client
from ollama import client
from ollama.workers import ChatWorker, ModelsPoller, NvidiaModelsWorker

from .home_view import HomePage, TopBar, centered_slot
from .code_panel import CodePanel
from .compare import ComparePage
from .input_bar import InputBar
from .manager import ManagerPage
from .messages import CODE_HOOKS, COLUMN_MAX, AssistantMessage, ChatView
from .action_menu import SEP, ActionMenu, MenuItem
from .dialogs import ConfirmDialog, TextPrompt
from .search_palette import SearchPalette
from .sidebar import TAG_COLORS, HistoryPanel, ResizeHandle, Sidebar, ask_text, confirm
from .titlebar import TITLE_H, TitleBar, make_menu

HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT, HTCAPTION = 15, 16, 17, 2
RESIZE_BORDER = 6
HOME, CHAT, MANAGER, COMPARE = 0, 1, 2, 3


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._t = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, msg: str, ms: int = 4000) -> None:
        self.setText(msg)
        self.adjustSize()
        self.resize(self.width() + 32, 38)
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, 62)
        self.show()
        self.raise_()
        self._t.start(ms)


class MainWindow(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("ChatLocal")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowMinMaxButtonsHint | Qt.WindowSystemMenuHint)
        self.resize(1280, 800)
        self.setMinimumSize(720, 520)

        self.db = db
        self.cid: int | None = None
        self.history: list[dict] = []
        self.hist_ids: list[int | None] = []   # id en base de chaque message de self.history
        self.worker: ChatWorker | None = None
        self._zombies: list[ChatWorker] = []
        self.assistant: AssistantMessage | None = None
        self.buffer = ""
        self._failed = False
        self._dirty = False
        self.models: list[str] = []
        self.running = False
        self.ephemeral = False
        self.nvidia_key = ""
        self.nvidia_models: list[str] = []
        self._nv_workers: list[NvidiaModelsWorker] = []
        self.nav: list[int | None] = [None]
        self.nav_i = 0

        self._build_ui()
        self._build_menus()

        self.flush_timer = QTimer(self, interval=60, timeout=self._flush)
        self.poller = ModelsPoller(parent=self)
        self.poller.running.connect(self._on_running)
        self.poller.models.connect(self._on_models)
        self.poller.start()
        saved = self.db.get_secret("nvidia_key")
        if saved:
            self.nvidia_key = saved
            self._fetch_nvidia(saved, announce=False)
        self._reload_history()
        self._restore_state()
        self.input.focus_input()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.titlebar = TitleBar()
        self.titlebar.backClicked.connect(lambda: self._nav_step(-1))
        self.titlebar.forwardClicked.connect(lambda: self._nav_step(1))
        self.titlebar.sidebarClicked.connect(self.toggle_history)
        self.titlebar.minimizeClicked.connect(self.showMinimized)
        self.titlebar.maximizeClicked.connect(self._toggle_max)
        self.titlebar.closeClicked.connect(self.close)
        outer.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        self.sidebar = Sidebar()
        self.sidebar.homeClicked.connect(self.new_chat)
        self.sidebar.historyClicked.connect(self.toggle_history)
        self.sidebar.managerClicked.connect(self.show_manager)
        self.sidebar.compareClicked.connect(self.show_compare)
        self.sidebar.moreClicked.connect(self._more_menu)
        body.addWidget(self.sidebar)

        hp = self.history_panel = HistoryPanel()
        hp.newChat.connect(self.new_chat)
        hp.openConversation.connect(self.open_conversation)
        hp.bulkDeleteRequested.connect(self.bulk_delete)
        hp.bulkArchiveRequested.connect(self._bulk_archive_from_panel)
        hp.renameConversation.connect(self.rename_conversation)
        hp.deleteConversation.connect(self.delete_conversation)
        hp.moveConversation.connect(self._move_conversation)
        hp.createFolder.connect(self.create_folder)
        hp.renameFolder.connect(self.rename_folder)
        hp.deleteFolder.connect(self.delete_folder)
        hp.toggleFolder.connect(self._toggle_folder)
        hp.folderMenuRequested.connect(self.show_folder_menu)
        hp.searchRequested.connect(self.open_search)
        hp.conversationMenuRequested.connect(self.show_conversation_menu)
        hp.pinRequested.connect(self.toggle_pin)
        body.addWidget(hp)
        handle = self.history_handle = ResizeHandle()
        handle.pressed.connect(hp.begin_drag)
        handle.moved.connect(hp.drag_to)
        handle.released.connect(hp.end_drag)
        handle.doubleClicked.connect(self._reset_history_width)
        hp.openChanged.connect(self.sidebar.set_history_checked)
        hp.widthChanged.connect(lambda w: self.db.set_setting("history_width", str(w)))
        saved_w = self.db.get_setting("history_width")
        if saved_w and saved_w.isdigit():
            hp.set_panel_width(int(saved_w))
        body.addWidget(handle)

        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 6, 4, 4)
        body.addLayout(wrap, 1)
        row_main = QHBoxLayout()
        row_main.setSpacing(0)
        row_main.setContentsMargins(0, 0, 0, 0)
        wrap.addLayout(row_main)
        self.panel = QFrame(objectName="MainPanel")
        row_main.addWidget(self.panel, 1)
        self.code_handle = ResizeHandle()
        self.code_handle.hide()
        row_main.addWidget(self.code_handle)
        self.code_panel = CodePanel()
        row_main.addWidget(self.code_panel)
        self.code_handle.pressed.connect(self.code_panel.begin_drag)
        self.code_handle.moved.connect(lambda dx: self.code_panel.drag_to(-dx))
        self.code_handle.released.connect(self.code_panel.end_drag)
        self.code_panel.openChanged.connect(self._on_code_panel_open)
        self.code_panel.reserved_fn = lambda: (self.history_panel.maximumWidth() if self.history_panel.is_open() else 0) + 10
        self.code_panel.roomNeeded.connect(lambda: self.history_panel.set_open(False) if self.history_panel.is_open() else None)
        self.code_panel.codeEdited.connect(self._on_code_edited)
        self.code_panel.widthChanged.connect(lambda w: self.db.set_setting("code_panel_width", str(w)))
        CODE_HOOKS["open"] = self._open_code_panel
        CODE_HOOKS["update"] = self.code_panel.update_code
        self.code_auto_open = self.db.get_setting("code_auto_open") == "1"
        self._auto_opened: set[int] = set()
        saved_cw = self.db.get_setting("code_panel_width")
        if saved_cw and saved_cw.isdigit():
            self.code_panel.set_panel_width(int(saved_cw))
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        self.topbar = TopBar()
        self.topbar.ephemeralClicked.connect(self.toggle_ephemeral)
        self.topbar.newChatClicked.connect(self.new_chat)
        self.topbar.titleClicked.connect(self.open_title_menu)
        pv.addWidget(self.topbar)
        self.stack = QStackedWidget()
        pv.addWidget(self.stack, 1)

        self.home = HomePage()
        self.home.shortcutClicked.connect(self._shortcut)
        self.stack.addWidget(self.home)

        chat_page = QWidget()
        cv = QVBoxLayout(chat_page)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.chat = ChatView()
        self.chat.editSubmitted.connect(self.edit_prompt)
        self.chat.versionRequested.connect(self.switch_version)
        self.chat.assistantEdited.connect(self._on_assistant_edited)
        self.chat.quoteRequested.connect(lambda text: self.input.set_quote(text))
        cv.addWidget(self.chat, 1)
        self.chat_slot_widget, self.chat_slot = centered_slot(COLUMN_MAX, (24, 4, 24, 18))
        cv.addWidget(self.chat_slot_widget)
        self.stack.addWidget(chat_page)

        self.manager = ManagerPage()
        self.manager.openConversation.connect(self.open_conversation)
        self.manager.deleteRequested.connect(self.bulk_delete)
        self.manager.archiveRequested.connect(self.bulk_archive)
        self.manager.pinRequested.connect(self.bulk_pin)
        self.manager.moveRequested.connect(self.bulk_move)
        self.manager.exportRequested.connect(self.bulk_export)
        self.stack.addWidget(self.manager)

        self.compare = ComparePage()
        self.compare.stream_factory = self._compare_stream
        self.compare.message.connect(lambda msg: self.toast.show_message(msg, 3500))
        self.compare.exchangeDone.connect(self._save_compare)
        self.stack.addWidget(self.compare)

        self.input = InputBar()
        self.input.submitted.connect(self.on_submit)
        self.input.stopRequested.connect(self.stop_generation)
        self.input.filesRejected.connect(lambda msg: self.toast.show_message(msg, 3500))
        self.input.modelChosen.connect(self._choose_model)
        self.input.refreshRequested.connect(self.refresh_models)
        self.input.nvidiaKeyAdd.connect(self.add_nvidia_key)
        self.input.modelRenameRequested.connect(self.rename_model)
        try:
            self.input.set_aliases(json.loads(self.db.get_setting("model_aliases") or "{}"))
        except ValueError:
            pass
        self.input.nvidiaKeyRemove.connect(self.remove_nvidia_key)
        self.home.input_slot.addWidget(self.input)
        self.toast = Toast(self.panel)

        self.palette = SearchPalette(self)
        self.palette.newChat.connect(self.new_chat)
        self.palette.newFolder.connect(self.create_folder)
        self.palette.openConversation.connect(self.open_conversation)
        self.prompt = TextPrompt(self)
        self.confirm_dialog = ConfirmDialog(self)

    def open_search(self) -> None:
        self.palette.open([c for c in self.db.list_conversations() if not c["archived"]])

    def _place_input(self, page: int) -> None:
        (self.home.input_slot if page == HOME else self.chat_slot).addWidget(self.input)
        self.stack.setCurrentIndex(page)
        self.input.show()
        self.input.focus_input()
        self.sidebar.set_manager_checked(False)
        self.sidebar.set_compare_checked(False)
        self._refresh_topbar()

    def _act(self, text, slot, shortcut=None) -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.WindowShortcut)
        a.triggered.connect(lambda _=False: slot())
        self.addAction(a)
        return a

    def _build_menus(self) -> None:
        new = self._act("Nouvelle conversation", self.new_chat, "Ctrl+N")
        refresh = self._act("Actualiser les modèles", self.refresh_models, "F5")
        search = self._act("Rechercher…", self.open_search, "Ctrl+K")
        search.setShortcuts([QKeySequence("Ctrl+K"), QKeySequence("Ctrl+F")])
        self._act("Nouveau dossier", self.create_folder, "Ctrl+O")
        quit_ = self._act("Quitter", self.close, "Ctrl+Q")
        rename = self._act("Renommer la conversation", self.rename_current, "F2")
        rename.setShortcuts([QKeySequence("F2"), QKeySequence("Ctrl+Alt+R")])
        pin = self._act("Épingler / désépingler le chat", lambda: self.cid and self.toggle_pin(self.cid), "Ctrl+Alt+P")
        arch = self._act("Archiver le chat", lambda: self.cid and self.toggle_archive(self.cid), "Ctrl+Shift+A")
        delete = self._act("Supprimer la conversation", lambda: self.cid and self.delete_conversation(self.cid),
                           "Ctrl+Shift+Backspace")
        copy_last = self._act("Copier la dernière réponse", self.copy_last, "Ctrl+Shift+C")
        hist = self._act("Historique des conversations", self.toggle_history, "Ctrl+B")
        full = self._act("Plein écran", self._toggle_fullscreen, "F11")
        allc = self._act("Toutes les discussions", self.show_manager, "Ctrl+Shift+L")
        compare = self._act("Comparer deux modèles", self.show_compare, "Ctrl+Shift+M")
        self._code_auto_action = self._act(self._code_auto_label(), self._toggle_code_auto)
        codeclose = self._act("Fermer le panneau de code", self.code_panel.close_panel)
        state = self._act("État d'Ollama…", self._show_state)
        about = self._act("À propos", self._about)
        reset = self._act("Réactiver les confirmations", self.reset_confirms)
        self._act("Arrêter la génération", self.stop_generation, "Esc")
        ephem = self._act("Chat éphémère", self.toggle_ephemeral, "Ctrl+Shift+N")

        for title, acts in (
            ("Fichier", [new, ephem, search, refresh, None, quit_]),
            ("Modifier", [rename, pin, arch, delete, None, copy_last]),
            ("Affichage", [hist, allc, compare, self._code_auto_action, codeclose, full]),
            ("Aide", [state, reset, about]),
        ):
            m = make_menu(self)
            for a in acts:
                m.addSeparator() if a is None else m.addAction(a)
            self.titlebar.add_menu(title, m)
        self._more = make_menu(self)
        self._more.addAction(new)
        self._more.addAction(compare)
        self._more.addAction(refresh)

    # ------------------------------------------------------------ fenêtre
    # ------------------------------------------------------------ panneau de code (droite)
    def _open_code_panel(self, block) -> None:
        CODE_HOOKS["link"] = block
        self.code_panel.open_code(block.code(), block.lang(), block.is_closed(), editable=not self.chat.locked)

    def _on_code_panel_open(self, on: bool) -> None:
        self.code_handle.setVisible(on)
        if not on:
            CODE_HOOKS["link"] = None

    def _on_code_edited(self, code: str) -> None:
        """Code modifié dans le panneau (enregistrement automatique) : on répercute dans la discussion."""
        block = CODE_HOOKS["link"]
        if block is not None:
            try:
                block.apply_edit(code)
            except RuntimeError:       # bloc supprimé (discussion changée) : rien à synchroniser
                pass

    def _on_assistant_edited(self, index: int, text: str) -> None:
        """Le message de l'IA a changé (code modifié) : historique envoyé au modèle + base mis à jour."""
        if index < len(self.history) and self.history[index]["role"] == "assistant":
            self.history[index]["content"] = text
            mid = self.hist_ids[index] if index < len(self.hist_ids) else None
            if mid and not self.ephemeral:
                self.db.update_message_content(mid, text)

    CODE_AUTO_LINES = 30

    def _auto_open_long_code(self) -> None:
        """Option « code long à droite » : ouvre le panneau dès qu'un bloc dépasse CODE_AUTO_LINES lignes."""
        if not (self.code_auto_open and self.assistant):
            return
        blocks = self.assistant.code_blocks()
        if blocks and blocks[-1].line_count() > self.CODE_AUTO_LINES and id(blocks[-1]) not in self._auto_opened:
            self._auto_opened.add(id(blocks[-1]))
            self._open_code_panel(blocks[-1])

    def _toggle_code_auto(self) -> None:
        self.code_auto_open = not self.code_auto_open
        self.db.set_setting("code_auto_open", "1" if self.code_auto_open else "0")
        self._code_auto_action.setText(self._code_auto_label())
        self.toast.show_message("Le code long s'ouvrira sur la droite" if self.code_auto_open
                                else "Le code reste dans la discussion", 2200)

    def _code_auto_label(self) -> str:
        return f"Code long à droite : {'activé' if self.code_auto_open else 'désactivé'}"

    def _toggle_max(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if hasattr(self, "titlebar"):
            self.titlebar.set_maximized(self.isMaximized())

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                dpr = self.devicePixelRatioF()
                pos = self.mapFromGlobal(QPoint(round(x / dpr), round(y / dpr)))
                if not (self.isMaximized() or self.isFullScreen()):
                    b = RESIZE_BORDER
                    l, r = pos.x() < b, pos.x() >= self.width() - b
                    t, bt = pos.y() < b, pos.y() >= self.height() - b
                    code = (HTTOPLEFT if t and l else HTTOPRIGHT if t and r else HTBOTTOMLEFT if bt and l
                            else HTBOTTOMRIGHT if bt and r else HTLEFT if l else HTRIGHT if r
                            else HTTOP if t else HTBOTTOM if bt else 0)
                    if code:
                        return True, code
                if 0 <= pos.y() < TITLE_H and self.childAt(pos) is self.titlebar:
                    return True, HTCAPTION
        return False, 0

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        for ov in (getattr(self, "palette", None), getattr(self, "prompt", None), getattr(self, "confirm_dialog", None)):
            if ov is not None and ov.isVisible():
                ov.setGeometry(self.rect())
                ov._place() if hasattr(ov, "_place") else ov._layout_card()

    def _save_state(self) -> None:
        """Mémorise localement (base SQLite) la fenêtre et l'historique, pour les retrouver au prochain lancement."""
        try:
            r = self.normalGeometry() if (self.isMaximized() or self.isFullScreen()) else self.geometry()
            self.db.set_setting("win_rect", f"{r.x()},{r.y()},{r.width()},{r.height()}")
            self.db.set_setting("win_max", "1" if self.isMaximized() else "0")
            self.db.set_setting("history_open", "1" if self.history_panel.is_open() else "0")
        except Exception:
            pass

    def _restore_state(self) -> None:
        raw = self.db.get_setting("win_rect")
        if raw:
            try:
                x, y, w, h = (int(v) for v in raw.split(","))
                rect = QRect(x, y, w, h)
                # on ignore une position qui tomberait hors de tout écran (écran débranché…)
                if any(s.availableGeometry().intersects(rect) for s in QApplication.screens()):
                    self.setGeometry(rect)
                else:
                    self.resize(w, h)
            except ValueError:
                pass
        if self.db.get_setting("win_max") == "1":
            self.showMaximized()
        if self.db.get_setting("history_open") == "1":
            self.history_panel.set_open(True)

    def closeEvent(self, e) -> None:
        self.code_panel.cleanup()
        self.compare.cancel()
        self._save_state()
        self._abort_generation()
        self.poller.stop()
        self.poller.wait(3000)
        for w in list(self._zombies):
            w.wait(2000)
        self.db.close()
        super().closeEvent(e)

    # ------------------------------------------------------------ modèles
    def refresh_models(self) -> None:
        self.poller.refresh()
        if self.nvidia_key:
            self._fetch_nvidia(self.nvidia_key, announce=False)
        self.toast.show_message("Actualisation des modèles…", 1500)

    def _compare_stream(self, model: str, msgs: list):
        """Flux de réponse pour la page de comparaison (Ollama ou NVIDIA)."""
        if model.startswith(nvidia_client.PREFIX):
            if not self.nvidia_key:
                raise ValueError("Ajoute ta clé API NVIDIA pour comparer un modèle NVIDIA.")
            return nvidia_client.ChatStream(self.nvidia_key, model[len(nvidia_client.PREFIX):], msgs)
        if not self.running:
            raise ValueError(f"Ollama est injoignable sur {client.BASE_URL}. Lance Ollama puis réessaie.")
        return client.ChatStream(model, msgs)

    def _model_names(self) -> dict[str, str]:
        return {m: self.input.display_name(m) for m in self._all_models()}

    def _save_compare(self) -> None:
        """Enregistre la comparaison dans l'historique des conversations (créée au premier échange)."""
        c = self.compare
        if not c.saved_turns:
            return
        data = c.snapshot()
        if c.cid is None or not self.db.get_conversation(c.cid):
            title = " ".join(c.saved_turns[0]["q"].split())
            title = "Comparaison : " + title[:40] + ("…" if len(title) > 40 else "")
            c.cid = self.db.create_conversation(title, data["a"])
            self._push_nav(c.cid)
        self.db.set_compare(c.cid, data)
        self.cid = c.cid
        self._reload_history()
        self.history_panel.select(c.cid)

    def _open_saved_compare(self, row, push: bool) -> None:
        """Rouvre une comparaison enregistrée depuis l'historique."""
        self._abort_generation()
        self._set_ephemeral(False)
        self.compare.set_models([(m, n) for m, n in self._model_names().items()], prefer=self.input.model())
        self.compare.restore(row["id"], self.db.compare_data(row) or {}, self._model_names())
        self.cid = row["id"]
        self.stack.setCurrentIndex(COMPARE)
        self.sidebar.set_home_checked(False)
        self.sidebar.set_manager_checked(False)
        self.sidebar.set_compare_checked(True)
        if push:
            self._push_nav(row["id"])
        self.history_panel.select(row["id"])
        self._refresh_topbar()
        self.compare.edit.setFocus()

    def show_compare(self) -> None:
        """Page « Comparer deux modèles » : même question, deux réponses côte à côte."""
        self._abort_generation()
        self._set_ephemeral(False)
        models = [(m, self.input.display_name(m)) for m in self._all_models()]
        self.compare.set_models(models, prefer=self.input.model())
        self.cid = self.compare.cid
        self.stack.setCurrentIndex(COMPARE)
        self.sidebar.set_home_checked(False)
        self.sidebar.set_manager_checked(False)
        self.sidebar.set_compare_checked(True)
        self._refresh_topbar()
        self.compare.edit.setFocus()
        if len(models) < 2:
            self.toast.show_message("Il faut au moins deux modèles (Ollama ou NVIDIA) pour comparer.", 4000)

    def _all_models(self) -> list[str]:
        return self.models + [nvidia_client.PREFIX + m for m in self.nvidia_models]

    def _sync_models(self) -> None:
        """Met à jour le sélecteur et corrige le modèle courant s'il n'existe plus."""
        valid = self._all_models()
        cur = self.input.model()
        if cur not in valid:
            last = self.db.get_setting("last_model")
            cur = last if last in valid else (self.models[0] if self.models else (valid[0] if valid else ""))
            self.input.set_model(cur)
        self.input.set_models(self.models, self.running, self.nvidia_models, bool(self.nvidia_key))

    def _on_running(self, running: bool) -> None:
        self.running = running
        self._sync_models()

    def _on_models(self, models: list) -> None:
        self.models = models
        self._sync_models()

    # ---- clé API NVIDIA ----
    def rename_model(self, full: str) -> None:
        """Change seulement le nom AFFICHÉ d'un modèle ; son identifiant réel reste inchangé."""
        real = self.input.default_name(full)

        def done(name: str) -> None:
            try:
                aliases = json.loads(self.db.get_setting("model_aliases") or "{}")
            except ValueError:
                aliases = {}
            if name == real:
                aliases.pop(full, None)         # nom d'origine retapé : on retire l'alias
            else:
                aliases[full] = name
            self.db.set_setting("model_aliases", json.dumps(aliases, ensure_ascii=False))
            self.input.set_aliases(aliases)

        self.prompt.ask("Renommer le modèle", f"Seul le nom affiché change (modèle réel : {real}).",
                        "Nom affiché", self.input.display_name(full), "Renommer", done, icon="brain")

    def add_nvidia_key(self) -> None:
        self.prompt.ask(
            "Clé API NVIDIA",
            "Colle ta clé (nvapi-…). Elle est chiffrée et reste sur ce PC.",
            "nvapi-…", "", "Enregistrer", lambda key: self._fetch_nvidia(key, announce=True),
            icon="key", secret=True)

    def _fetch_nvidia(self, key: str, announce: bool) -> None:
        key = key.strip()
        if announce:
            self.toast.show_message("Vérification de la clé NVIDIA…", 8000)
        w = NvidiaModelsWorker(key, self)
        w.ok.connect(lambda k, ms, a=announce: self._on_nvidia_ok(k, ms, a))
        w.failed.connect(lambda msg, a=announce: self._on_nvidia_failed(msg, a))
        self._nv_workers.append(w)
        w.finished.connect(lambda w=w: self._nv_workers.remove(w) if w in self._nv_workers else None)
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_nvidia_ok(self, key: str, models: list, announce: bool) -> None:
        if announce:  # clé validée par NVIDIA : on la mémorise (chiffrée)
            self.db.set_secret("nvidia_key", key)
            self.toast.show_message(f"Clé NVIDIA enregistrée · {len(models)} modèles disponibles", 4000)
        self.nvidia_key = key
        self.nvidia_models = models
        self._sync_models()

    def _on_nvidia_failed(self, msg: str, announce: bool) -> None:
        # une clé refusée à l'ajout n'est jamais enregistrée ; au démarrage on garde la clé (panne réseau possible)
        self.toast.show_message(msg, 6000)
        self._sync_models()

    def _confirm(self, kind: str, title: str, message: str, button: str, action, icon: str = "trash") -> None:
        """Confirmation en verre dépoli ; « Ne plus me demander » mémorise le choix pour ce type d'action."""
        if self.db.get_setting("skip_confirm:" + kind) == "1":
            action()
            return

        def done(skip: bool) -> None:
            if skip:
                self.db.set_setting("skip_confirm:" + kind, "1")
            action()

        self.confirm_dialog.ask_confirm(title, message, button, done, icon)

    def reset_confirms(self) -> None:
        n = self.db.clear_skip_confirms()
        self.toast.show_message("Confirmations réactivées" if n else "Toutes les confirmations sont déjà actives", 2500)

    def remove_nvidia_key(self) -> None:
        def do() -> None:
            self.db.delete_secret("nvidia_key")
            self.nvidia_key, self.nvidia_models = "", []
            if self.input.model().startswith(nvidia_client.PREFIX):
                self.input.set_model("")
            self._sync_models()
            self.toast.show_message("Clé API NVIDIA supprimée", 2500)

        self._confirm("nvidia_key", "Supprimer la clé API ?",
                      "Les modèles NVIDIA ne seront plus disponibles tant que tu n'en ajoutes pas une nouvelle.",
                      "Supprimer", do, "key")

    def _choose_model(self, name: str) -> None:
        self.input.set_model(name)
        self.db.set_setting("last_model", name)
        if self.cid is not None:
            self.db.set_conversation_model(self.cid, name)
        self.input.focus_input()

    # ------------------------------------------------------------ historique
    def _reload_history(self) -> None:
        folders, convs = self.db.list_folders(), self.db.list_conversations()
        self.history_panel.set_data(folders, convs, self.cid)
        if self.stack.currentIndex() == MANAGER:        # la page « Toutes les discussions » se remplit à l'ouverture
            self.manager.set_data(convs, folders)
        self._refresh_topbar()

    def _refresh_topbar(self) -> None:
        """Bouton « nouveau chat » + titre cliquable ; état verrouillé de la conversation."""
        in_chat = self.stack.currentIndex() == CHAT
        row = self.db.get_conversation(self.cid) if (self.cid is not None and not self.ephemeral) else None
        self.topbar.set_conversation(in_chat, row["title"] if row else None)
        locked = bool(row and row["locked"])
        self.chat.locked = locked
        self.code_panel.set_editable(not locked)
        self.input.set_locked(locked)

    def _reset_history_width(self) -> None:
        if self.history_panel.is_open():
            self.history_panel.reset_width()

    def toggle_history(self) -> None:
        on = not self.history_panel.is_open()
        self.history_panel.set_open(on)
        self.sidebar.set_history_checked(on)

    def rename_conversation(self, cid: int) -> None:
        row = self.db.get_conversation(cid)
        if not row:
            return

        def done(title: str) -> None:
            self.db.rename_conversation(cid, title)
            self._reload_history()

        self.prompt.ask("Renommer la conversation", "Choisis un nouveau titre.", "Titre", row["title"],
                        "Renommer", done, icon="pencil")

    def rename_current(self) -> None:
        if self.cid is not None:
            self.rename_conversation(self.cid)

    def _move_conversation(self, cid: int, fid: int) -> None:
        self.db.move_conversation(cid, fid or None)
        if fid:
            self.db.set_folder_expanded(fid, True)
        self._reload_history()

    def create_folder(self) -> None:
        def done(name: str) -> None:
            self.db.create_folder(name)
            if not self.history_panel.is_open():
                self.toggle_history()
            self._reload_history()

        self.prompt.ask("Nouveau dossier", "Regroupe tes conversations dans un dossier.",
                        "Nom du dossier", "", "Créer", done)

    def rename_folder(self, fid: int) -> None:
        cur = next((f["name"] for f in self.db.list_folders() if f["id"] == fid), "")

        def done(name: str) -> None:
            self.db.rename_folder(fid, name)
            self._reload_history()

        self.prompt.ask("Renommer le dossier", "Choisis un nouveau nom pour ce dossier.",
                        "Nom du dossier", cur, "Renommer", done)

    def delete_folder(self, fid: int) -> None:
        cur = next((f["name"] for f in self.db.list_folders() if f["id"] == fid), "")
        def do() -> None:
            self.db.delete_folder(fid)
            self._reload_history()

        self._confirm("delete_folder", "Supprimer le dossier ?",
                      f"Le dossier « {cur} » sera supprimé. Ses conversations ne sont pas supprimées : elles "
                      "retournent dans Récents.", "Supprimer", do, "folder")

    def _toggle_folder(self, fid: int) -> None:
        f = next((f for f in self.db.list_folders() if f["id"] == fid), None)
        if f:
            self.db.set_folder_expanded(fid, not f["expanded"])
            self._reload_history()

    def delete_conversation(self, cid: int) -> None:
        row = self.db.get_conversation(cid)
        if row and row["locked"]:
            self.toast.show_message("Déverrouille le chat avant de le supprimer.")
            return
        if not row:
            return

        def do() -> None:
            if cid == self.cid:
                self.new_chat()
            self.db.delete_conversation(cid)
            self.nav = [c for c in self.nav if c != cid] or [None]
            self.nav_i = min(self.nav_i, len(self.nav) - 1)
            self._reload_history()

        self._confirm("delete_conversation", "Supprimer la conversation ?",
                      f"« {row['title']} » sera supprimée définitivement. Cette action est irréversible.",
                      "Supprimer", do)

    # ------------------------------------------------------------ navigation
    def _push_nav(self, cid: int | None) -> None:
        if self.nav[self.nav_i] == cid:
            return
        self.nav = self.nav[: self.nav_i + 1] + [cid]
        self.nav_i = len(self.nav) - 1

    def _nav_step(self, d: int) -> None:
        i = self.nav_i + d
        if 0 <= i < len(self.nav):
            self.nav_i = i
            cid = self.nav[i]
            if cid is None or not self.db.get_conversation(cid):
                self._show_new(push=False)
            else:
                self.open_conversation(cid, push=False)

    def new_chat(self) -> None:
        self._show_new(push=True)

    def _set_ephemeral(self, on: bool) -> None:
        self.input.clear_quote()
        self.code_panel.close_panel()
        self.ephemeral = on
        self.topbar.set_ephemeral(on)
        self.home.set_ephemeral(on)

    def toggle_ephemeral(self) -> None:
        """Bascule chat éphémère : rien n'est enregistré (ni base, ni historique)."""
        was = self.ephemeral
        self._show_new(push=False)          # repart d'un écran d'accueil vierge
        self._set_ephemeral(not was)

    def _show_new(self, push: bool) -> None:
        self._abort_generation()
        self._set_ephemeral(False)
        self.cid = None
        self.history = []
        self.hist_ids = []
        self.chat.clear()
        self.history_panel.select(None)
        self.sidebar.set_home_checked(True)
        if push:
            self._push_nav(None)
        self._place_input(HOME)

    def open_conversation(self, cid: int, push: bool = True, force: bool = False) -> None:
        row = self.db.get_conversation(cid)
        if not row:
            return
        if row["compare"]:
            if cid == self.cid and self.stack.currentIndex() == COMPARE and not force:
                return
            self._open_saved_compare(row, push)
            return
        if cid == self.cid and self.stack.currentIndex() == CHAT and not force:
            return
        self._abort_generation()
        self._set_ephemeral(False)
        self.cid = cid
        self.chat.locked = bool(row["locked"])
        self.chat.clear()
        self.history = []
        self.hist_ids = []
        path = self.db.get_path(cid)
        for m in path:
            self.history.append({"role": m["role"], "content": m["content"], "quote": m["quote"],
                                 "files": m["files"]})
            self.hist_ids.append(m["id"])
        # ouverture instantanée : seuls les derniers messages sont construits tout de suite, les plus anciens
        # arrivent ensuite par petits lots (sans faire bouger l'écran)
        tok = self.chat.gen            # change à chaque chat.clear() : invalide les lots en attente
        first = max(0, len(path) - self.FIRST_BATCH)
        for idx in range(first, len(path)):
            self._build_message(path[idx], idx)
        if first:
            QTimer.singleShot(0, lambda: self._load_older(tok, path, first))
        if row["model"] and row["model"] in self.models:
            self.input.set_model(row["model"])
        self.history_panel.select(cid)
        self.sidebar.set_home_checked(False)
        if push:
            self._push_nav(cid)
        self._place_input(CHAT)

    FIRST_BATCH, OLDER_BATCH = 14, 8       # messages construits d'un coup / par lot pour l'historique ancien

    def _build_message(self, m: dict, idx: int) -> None:
        if m["role"] == "user":
            self.chat.add_user(m["content"], idx, m["ver"], m["total"], fade=False, quote=m["quote"],
                               files=m["files"])
        else:
            self.chat.add_assistant(m["content"], idx, fade=False)

    def _load_older(self, token: int, path: list, end: int) -> None:
        """Ajoute, par lots et du plus récent au plus ancien, les messages au-dessus de ceux déjà affichés."""
        if token != self.chat.gen:      # autre conversation ouverte entre-temps
            return
        start = max(0, end - self.OLDER_BATCH)
        self.chat.begin_prepend()
        for idx in range(end - 1, start - 1, -1):
            self._build_message(path[idx], idx)
        self.chat.end_prepend()
        if start:
            QTimer.singleShot(0, lambda: self._load_older(token, path, start))

    def show_manager(self) -> None:
        """Page « Toutes les discussions » (liste, sélection multiple, actions groupées)."""
        self._abort_generation()
        self._set_ephemeral(False)
        self.manager.set_data(self.db.list_conversations(), self.db.list_folders())
        self.stack.setCurrentIndex(MANAGER)
        self.sidebar.set_home_checked(False)
        self.sidebar.set_manager_checked(True)
        self.sidebar.set_compare_checked(False)
        self._refresh_topbar()

    # ---- actions groupées ----
    def _after_bulk(self) -> None:
        self._reload_history()

    def _bulk_archive_from_panel(self, ids: list, on: bool) -> None:
        self.history_panel.drop_selection()
        self.bulk_archive(ids, on)

    def bulk_delete(self, ids: list) -> None:
        rows = [self.db.get_conversation(c) for c in ids]
        rows = [r for r in rows if r]
        locked = [r for r in rows if r["locked"]]
        todo = [r["id"] for r in rows if not r["locked"]]
        if not todo:
            self.toast.show_message("Les discussions sélectionnées sont verrouillées.")
            return
        n = len(todo)
        msg = f"{n} discussion{'s' if n > 1 else ''} sera{'ont' if n > 1 else ''} supprimée{'s' if n > 1 else ''} " \
              "définitivement. Cette action est irréversible."
        if locked:
            msg += f" ({len(locked)} verrouillée{'s' if len(locked) > 1 else ''} ignorée{'s' if len(locked) > 1 else ''}.)"

        def do() -> None:
            for cid in todo:
                if cid == self.cid:
                    self.new_chat()
                self.db.delete_conversation(cid)
                self.nav = [c for c in self.nav if c != cid] or [None]
            self.nav_i = min(self.nav_i, len(self.nav) - 1)
            self._after_bulk()
            self.toast.show_message(f"{n} discussion{'s' if n > 1 else ''} supprimée{'s' if n > 1 else ''}", 2500)

        self.confirm_dialog.ask_confirm(f"Supprimer {n} discussion{'s' if n > 1 else ''} ?", msg, "Supprimer",
                                        lambda skip: do(), "trash", skippable=False)

    def bulk_archive(self, ids: list, on: bool) -> None:
        for cid in ids:
            self.db.set_flag(cid, "archived", on)
            if on and cid == self.cid:
                self.new_chat()
        self._after_bulk()
        self.toast.show_message(f"{len(ids)} archivée{'s' if len(ids) > 1 else ''}" if on else f"{len(ids)} désarchivée{'s' if len(ids) > 1 else ''}", 2000)

    def bulk_pin(self, ids: list, on: bool) -> None:
        for cid in ids:
            self.db.set_flag(cid, "pinned", on)
        self._after_bulk()
        self.toast.show_message("Épinglées" if on else "Désépinglées", 1800)

    def bulk_move(self, ids: list, fid: int) -> None:
        for cid in ids:
            self.db.move_conversation(cid, fid or None)
        if fid:
            self.db.set_folder_expanded(fid, True)
        self._after_bulk()
        self.toast.show_message(f"{len(ids)} déplacée{'s' if len(ids) > 1 else ''}", 2000)

    def bulk_export(self, ids: list) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Exporter les discussions dans le dossier…")
        if not folder:
            return
        used: set[str] = set()
        for cid in ids:
            row = self.db.get_conversation(cid)
            if not row:
                continue
            safe = "".join(ch for ch in row["title"] if ch not in '<>:"/\\|?*').strip() or "conversation"
            name, k = safe, 2
            while name in used or os.path.exists(os.path.join(folder, name + ".md")):
                name, k = f"{safe} ({k})", k + 1
            used.add(name)
            with open(os.path.join(folder, name + ".md"), "w", encoding="utf-8") as f:
                f.write(self._conversation_markdown(cid))
        self.toast.show_message(f"{len(ids)} discussion{'s' if len(ids) > 1 else ''} exportée{'s' if len(ids) > 1 else ''}", 2500)

    def _shortcut(self, prompt: str) -> None:
        self.input.set_text(prompt)

    def _more_menu(self, pos: QPoint) -> None:
        self._more.exec(pos)

    # ------------------------------------------------------------ envoi / streaming
    def on_submit(self, text: str, edit_index: int | None = None, quote: str | None = None,
                  files: list | None = None) -> None:
        if self.worker:
            return
        model = self.input.model()
        is_nvidia = model.startswith(nvidia_client.PREFIX)
        if is_nvidia and not self.nvidia_key:
            self.input.set_text(text)
            self.toast.show_message("Ajoute ta clé API NVIDIA depuis le choix du modèle.")
            return
        if not is_nvidia and not self.running:
            self.input.set_text(text)
            self.toast.show_message(f"Ollama est injoignable sur {client.BASE_URL}. Lance Ollama puis réessaie.")
            return
        if not model:
            self.input.set_text(text)
            self.toast.show_message("Aucun modèle disponible. Installe-en un avec « ollama pull ».")
            return
        if self.cid is not None and not self.ephemeral:
            row = self.db.get_conversation(self.cid)
            if row and row["locked"]:
                self.input.set_text(text)
                self.toast.show_message("Ce chat est verrouillé : déverrouille-le pour continuer.")
                return
        if self.ephemeral:
            if self.stack.currentIndex() == HOME:
                self._place_input(CHAT)
        elif self.cid is None:
            title = " ".join(text.split())
            title = title[:48] + ("…" if len(title) > 48 else "")
            self.cid = self.db.create_conversation(title, model)
            self._push_nav(self.cid)
            self.sidebar.set_home_checked(False)
            self._place_input(CHAT)
        elif (self.db.get_conversation(self.cid)["model"] or "") != model:
            self.db.set_conversation_model(self.cid, model)
        parent = "leaf"
        if edit_index is not None:
            # modification d'un prompt : on garde l'ancienne branche (version) et on en crée une nouvelle
            parent = self.hist_ids[edit_index - 1] if edit_index > 0 else None
            self.history = self.history[:edit_index]
            self.hist_ids = self.hist_ids[:edit_index]
            self.chat.truncate_from(edit_index)
        q = quote if quote is not None else self.input.quote()      # extrait sélectionné joint à ce message
        fl = files if files is not None else self.input.files()      # fichiers joints à ce message
        mid = None if self.ephemeral else self.db.add_message(self.cid, "user", text, parent=parent, quote=q, files=fl)
        ver, total = self.db.version_info(mid) if mid else (1, 1)
        self.chat.add_user(text, len(self.history), ver, total, quote=q, files=fl)
        self.history.append({"role": "user", "content": text, "quote": q, "files": fl})
        if quote is None:
            self.input.clear_quote()
        if files is None:
            self.input.clear_files()
        self.hist_ids.append(mid)
        self.assistant = self.chat.add_assistant(index=len(self.history))
        self.buffer, self._failed, self._dirty = "", False, False
        if not self.ephemeral:
            self._reload_history()
            self.history_panel.select(self.cid)

        msgs = [self._model_msg(m) for m in self.history]
        if is_nvidia and any("images" in m for m in msgs):
            msgs = [{k: v for k, v in m.items() if k != "images"} for m in msgs]
            self.toast.show_message("Les images ne sont pas envoyées aux modèles NVIDIA.", 3500)
        stream = (nvidia_client.ChatStream(self.nvidia_key, model[len(nvidia_client.PREFIX):], msgs) if is_nvidia
                  else client.ChatStream(model, msgs))
        w = ChatWorker(stream, self)
        w.content.connect(self._on_chunk)
        w.failed.connect(self._on_failed)
        w.done.connect(self._on_done)
        self.worker = w
        self.input.set_generating(True)
        self.flush_timer.start()
        w.start()

    @staticmethod
    def _model_msg(m: dict) -> dict:
        """Message envoyé au modèle : l'extrait sélectionné est joint au texte de l'utilisateur."""
        q = m.get("quote")
        content = m["content"]
        if m["role"] == "user" and q:
            content = f'Extrait sélectionné par l\'utilisateur :\n"""\n{q}\n"""\n\n{content}'
        msg = {"role": m["role"], "content": content}
        files = m.get("files") or []
        if m["role"] == "user" and files:
            msg["content"] = attachments.with_files(content, files)
            imgs = attachments.images(files)
            if imgs:
                msg["images"] = imgs
        return msg

    def edit_prompt(self, index: int, text: str) -> None:
        """Modifie un prompt : l'ancienne version reste consultable (‹ 1/2 ›), puis la réponse est régénérée."""
        if self.cid is not None and not self.ephemeral:
            row = self.db.get_conversation(self.cid)
            if row and row["locked"]:
                self.toast.show_message("Ce chat est verrouillé.")
                return
        self._abort_generation()
        keep = self.history[index].get("quote", "") if index < len(self.history) else ""
        keep_files = self.history[index].get("files") or [] if index < len(self.history) else []
        self.on_submit(text, edit_index=index, quote=keep, files=keep_files)

    # ------------------------------------------------------------ menu d'une conversation
    def open_title_menu(self, pos: QPoint) -> None:
        if self.cid is not None and not self.ephemeral:
            self.show_conversation_menu(self.cid, pos)

    def show_conversation_menu(self, cid: int, pos: QPoint) -> None:
        row = self.db.get_conversation(cid)
        if not row:
            return
        pinned, locked, archived = bool(row["pinned"]), bool(row["locked"]), bool(row["archived"])
        folders = self.db.list_folders()
        sub = [MenuItem(f["name"], "folder", callback=lambda fid=f["id"]: self._move_conversation(cid, fid))
               for f in folders]
        if folders:
            sub.append(SEP)
        sub.append(MenuItem("Aucun dossier (Récents)", "chat", callback=lambda: self._move_conversation(cid, 0)))
        sub.append(MenuItem("Nouveau dossier…", "plus", callback=self.create_folder))
        tag = row["tag"]
        sections = [MenuItem("Aucune section", "list", checked=not tag, callback=lambda: self.set_tag(cid, None))]
        sections += [MenuItem(name.capitalize(), dot=color, checked=(tag == name),
                              callback=lambda n=name: self.set_tag(cid, n)) for name, color in TAG_COLORS.items()]
        items = [
            MenuItem("Renommer", "pencil", "Ctrl+Alt+R", callback=lambda: self.rename_conversation(cid)),
            MenuItem("Désépingler" if pinned else "Épingler", "pin", "Ctrl+Alt+P",
                     callback=lambda: self.toggle_pin(cid)),
            MenuItem("Section", "list", submenu=sections),
            MenuItem("Déverrouiller le chat" if locked else "Verrouiller le chat", "unlock" if locked else "lock",
                     callback=lambda: self.toggle_lock(cid)),
            SEP,
            MenuItem("Partager", "export", callback=lambda: self.export_conversation(cid)),
            SEP,
            MenuItem("Copier la conversation", "copy", callback=lambda: self.copy_conversation(cid)),
            SEP,
            MenuItem("Désarchiver" if archived else "Archiver", "archive", "Ctrl+Shift+A",
                     callback=lambda: self.toggle_archive(cid)),
            MenuItem("Supprimer", "trash", danger=True, callback=lambda: self.delete_conversation(cid)),
            SEP,
            MenuItem("Déplacer vers un dossier", "folder_move", submenu=sub),
        ]
        self._ctx_menu = ActionMenu(items, self)
        self._ctx_menu.popup(pos)

    def show_folder_menu(self, fid: int, pos: QPoint) -> None:
        folder = next((f for f in self.db.list_folders() if f["id"] == fid), None)
        if not folder:
            return
        cur = folder["color"]
        colors = [MenuItem("Aucune couleur", "folder", checked=not cur, callback=lambda: self.set_folder_color(fid, None))]
        colors += [MenuItem(name.capitalize(), dot=col, checked=(cur == name),
                            callback=lambda n=name: self.set_folder_color(fid, n)) for name, col in TAG_COLORS.items()]
        items = [
            MenuItem("Renommer", "pencil", callback=lambda: self.rename_folder(fid)),
            MenuItem("Couleur", "palette", submenu=colors),
            SEP,
            MenuItem("Supprimer le dossier", "trash", danger=True, callback=lambda: self.delete_folder(fid)),
        ]
        self._ctx_menu = ActionMenu(items, self)
        self._ctx_menu.popup(pos)

    def set_folder_color(self, fid: int, color: str | None) -> None:
        self.db.set_folder_color(fid, color)
        self._reload_history()

    def set_tag(self, cid: int, tag: str | None) -> None:
        self.db.set_tag(cid, tag)
        self._reload_history()

    def toggle_pin(self, cid: int) -> None:
        row = self.db.get_conversation(cid)
        if row:
            self.db.set_flag(cid, "pinned", not row["pinned"])
            self._reload_history()
            self.toast.show_message("Chat désépinglé" if row["pinned"] else "Chat épinglé", 1800)

    def toggle_lock(self, cid: int) -> None:
        row = self.db.get_conversation(cid)
        if not row:
            return
        self.db.set_flag(cid, "locked", not row["locked"])
        if cid == self.cid and self.stack.currentIndex() == CHAT:
            self.open_conversation(cid, push=False, force=True)   # ré-affiche avec/sans boutons de modification
        self._reload_history()
        self.toast.show_message("Chat déverrouillé" if row["locked"] else "Chat verrouillé (lecture seule)", 2200)

    def toggle_archive(self, cid: int) -> None:
        row = self.db.get_conversation(cid)
        if not row:
            return
        archiving = not row["archived"]
        self.db.set_flag(cid, "archived", archiving)
        if archiving and cid == self.cid:
            self.new_chat()
        self._reload_history()
        self.toast.show_message("Chat archivé" if archiving else "Chat désarchivé", 1800)

    def _conversation_markdown(self, cid: int) -> str:
        row = self.db.get_conversation(cid)
        parts = [f"# {row['title']}", ""]
        cmp = self.db.compare_data(row)
        if cmp:
            names = self._model_names()
            for t in cmp.get("turns", []):
                parts += ["### Vous", "", t.get("q", ""), ""]
                for key, mid in (("a", cmp.get("a")), ("b", cmp.get("b"))):
                    parts += [f"#### {names.get(mid, mid)}", "", t.get(key, ""), ""]
            return "\n".join(parts)
        for m in self.db.get_messages(cid):
            parts += ["### " + ("Vous" if m["role"] == "user" else "Assistant"), ""]
            if m["quote"]:
                parts += ["\n".join("> " + ln for ln in m["quote"].splitlines()), ""]
            for f in load_files(m["files"]):
                parts += [f"📎 {f['name']}", ""]
            parts += [m["content"], ""]
        return "\n".join(parts)

    def export_conversation(self, cid: int) -> None:
        row = self.db.get_conversation(cid)
        if not row:
            return
        safe = "".join(ch for ch in row["title"] if ch not in '<>:"/\\|?*').strip() or "conversation"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la conversation", f"{safe}.md", "Markdown (*.md)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._conversation_markdown(cid))
            self.toast.show_message("Conversation exportée", 2200)

    def copy_conversation(self, cid: int) -> None:
        if self.db.get_conversation(cid):
            QApplication.clipboard().setText(self._conversation_markdown(cid))
            self.toast.show_message("Conversation copiée", 1800)

    def switch_version(self, index: int, delta: int) -> None:
        """Affiche une autre version d'un prompt modifié (avec les réponses qui lui correspondent)."""
        if self.cid is None or self.ephemeral or index >= len(self.hist_ids) or self.hist_ids[index] is None:
            return
        self._abort_generation()
        mid = self.hist_ids[index]
        sibs = self.db.siblings(mid)
        i = sibs.index(mid) + delta
        if 0 <= i < len(sibs):
            self.db.select_version(sibs[i])
            self.open_conversation(self.cid, push=False, force=True)

    def _on_chunk(self, text: str) -> None:
        self.buffer += text
        self._dirty = True

    def _flush(self) -> None:
        if self._dirty and self.assistant:
            self._dirty = False
            self.assistant.set_text(self.buffer)
            self._auto_open_long_code()

    def _on_failed(self, msg: str) -> None:
        self._failed = True
        if self.assistant:
            self._flush()
            self.assistant.set_error(html.escape(msg))

    def _on_done(self, cancelled: bool) -> None:
        w, self.worker = self.worker, None
        self._finalize(cancelled)
        if w:
            self._zombies.append(w)
            w.finished.connect(lambda w=w: self._zombies.remove(w) if w in self._zombies else None)
            w.finished.connect(w.deleteLater)

    def _finalize(self, cancelled: bool = False) -> None:
        self.flush_timer.stop()
        if self.assistant:
            self.assistant.set_text(self.buffer)
            text = self.buffer.strip()
            if text:
                amid = None
                if self.cid is not None and not self.ephemeral:
                    amid = self.db.add_message(self.cid, "assistant", self.buffer)
                self.history.append({"role": "assistant", "content": self.buffer})
                self.hist_ids.append(amid)
            elif not self._failed:
                self.assistant.set_error("Aucune réponse." if not cancelled else "Génération interrompue.")
            self.assistant.finish()
        self.assistant = None
        self.input.set_generating(False)
        self._reload_history()
        self.history_panel.select(self.cid)

    def stop_generation(self) -> None:
        if self.worker:
            self.worker.cancel()

    def _abort_generation(self) -> None:
        """Interrompt proprement la génération (changement de conversation, fermeture)."""
        w = self.worker
        if not w:
            return
        self.worker = None
        for sig in (w.content, w.failed, w.done):
            sig.disconnect()
        w.cancel()
        self._finalize(cancelled=True)
        self._zombies.append(w)
        w.finished.connect(lambda w=w: self._zombies.remove(w) if w in self._zombies else None)
        w.finished.connect(w.deleteLater)

    def copy_last(self) -> None:
        for m in reversed(self.history):
            if m["role"] == "assistant":
                QApplication.clipboard().setText(m["content"])
                self.toast.show_message("Réponse copiée", 1500)
                return

    # ------------------------------------------------------------ aide
    def _show_state(self) -> None:
        txt = (f"Adresse : {client.BASE_URL}\nÉtat : {'en ligne' if self.running else 'hors ligne'}\n"
               f"Modèles installés : {len(self.models)}\n" + "\n".join(f" • {m}" for m in self.models))
        QMessageBox.information(self, "État d'Ollama", txt)

    def _about(self) -> None:
        QMessageBox.about(self, "À propos", "ChatLocal — interface de chat pour tes modèles Ollama locaux.")
