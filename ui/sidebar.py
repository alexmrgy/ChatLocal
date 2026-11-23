"""Barre latérale d'icônes (52 px) + panneau Dossiers / Récents."""
from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QEvent, QMimeData, QPoint, QPropertyAnimation, QRect, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .icons import icon_pixmap
from .titlebar import make_menu
from .widgets import IconButton

SIDEBAR_W = 52
MIME_CONV = "application/x-chatlocal-conversations"      # glisser-déposer : ids des conversations (« 3,7,12 »)


def conv_mime(ids: list[int]) -> QMimeData:
    m = QMimeData()
    m.setData(MIME_CONV, ",".join(str(i) for i in ids).encode("ascii"))
    return m


def mime_ids(mime) -> list[int]:
    if not mime.hasFormat(MIME_CONV):
        return []
    raw = bytes(mime.data(MIME_CONV)).decode("ascii", "ignore")
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


class Sidebar(QWidget):
    homeClicked = Signal()
    historyClicked = Signal()
    managerClicked = Signal()
    compareClicked = Signal()
    moreClicked = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_W)
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 14, 8, 12)
        col.setSpacing(8)
        kw = dict(size=(36, 36), icon_size=20, radius=12, bg_checked=theme.BG_ACTIVE, fg=theme.TEXT_DIM)

        self.home = IconButton("home", tooltip="Nouvelle conversation", **{**kw, "fg": theme.TEXT})
        self.home.setCheckable(True)
        self.home.setChecked(True)
        self.home.clicked.connect(self.homeClicked)
        self.history = IconButton("clock", tooltip="Historique des conversations", **kw)
        self.history.clicked.connect(self.historyClicked)
        self.manager = IconButton("list", tooltip="Toutes les discussions (Ctrl+Maj+L)", **kw)
        self.manager.setCheckable(True)
        self.manager.clicked.connect(self.managerClicked)
        self.compare = IconButton("library", tooltip="Comparer deux modèles (Ctrl+Maj+M)", **kw)
        self.compare.setCheckable(True)
        self.compare.clicked.connect(self.compareClicked)
        self.more = IconButton("dots", tooltip="Plus", **kw)
        self.more.clicked.connect(lambda: self.moreClicked.emit(self.more.mapToGlobal(QPoint(self.more.width() + 6, 0))))
        for b in (self.home, self.compare, self.history, self.manager, self.more):
            col.addWidget(b)
        col.addStretch(1)

    def set_history_checked(self, on: bool) -> None:
        self.history.setChecked(on)
        self.history.update()

    def set_manager_checked(self, on: bool) -> None:
        self.manager.setChecked(on)
        self.manager.update()

    def set_compare_checked(self, on: bool) -> None:
        self.compare.setChecked(on)
        self.compare.update()

    def set_home_checked(self, on: bool) -> None:
        self.home.setChecked(on)
        self.home.update()


TAG_COLORS = {"rouge": "#ef5350", "orange": "#ff9f43", "jaune": "#f4d03f", "vert": "#4ade80",
              "bleu": "#5b8cff", "violet": "#a97bff"}


class NavRow(QWidget):
    """Ligne cliquable (icône optionnelle + texte). Pour une conversation : pastille de section et,
    au survol, boutons « épingler » et « ⋯ »."""
    clicked = Signal()
    context = Signal(QPoint)
    pinClicked = Signal()
    menuClicked = Signal(QPoint)
    dropped = Signal(list)           # ids de conversations déposées sur cette ligne

    def __init__(self, text: str, icon: str | None = None, indent: int = 0, selected: bool = False,
                 actions: bool = False, pinned: bool = False, tag: str | None = None, icon_color: str | None = None,
                 checked: bool = False, parent=None):
        super().__init__(parent)
        self._text, self._icon, self._indent, self._selected = text, icon, indent, selected
        self._actions, self._pinned, self._tag = actions, pinned, tag
        self._icon_color = icon_color
        self._checked = checked          # sélection multiple (Ctrl / Maj + clic)
        self.drag_ids = None             # fonction -> ids à glisser (None : cette ligne ne se glisse pas)
        self._press = None
        self._dragging = False
        self._drop_hover = False
        self.last_mods = Qt.NoModifier   # touches maintenues lors du dernier clic
        self._hover = False
        self._hover_btn = None   # "pin" | "menu" | None
        self.setFixedHeight(34)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(text)
        f = QFont(self.font())
        f.setPixelSize(15)
        self.setFont(f)

    def _btn_rects(self):
        s = 28
        y = (self.height() - s) // 2
        menu = QRect(self.width() - 6 - s, y, s, s)
        return QRect(menu.left() - 2 - s, y, s, s), menu

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover, self._hover_btn = False, None
        self.update()

    def mousePressEvent(self, e) -> None:
        self._press = e.position().toPoint() if e.button() == Qt.LeftButton else None
        self._dragging = False

    def make_drag(self) -> QDrag | None:
        ids = self.drag_ids() if self.drag_ids else []
        if not ids:
            return None
        drag = QDrag(self)
        drag.setMimeData(conv_mime(ids))
        pm = self.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(self._press or QPoint(20, 17))
        return drag

    def mouseMoveEvent(self, e) -> None:
        if (self._press is not None and self.drag_ids and e.buttons() & Qt.LeftButton
                and (e.position().toPoint() - self._press).manhattanLength() >= QApplication.startDragDistance()):
            drag = self.make_drag()
            self._press = None
            if drag is not None:
                self._dragging = True
                self._hover = False
                self.update()
                drag.exec(Qt.MoveAction)
                self._dragging = False
                return
        if self._actions:
            pin, menu = self._btn_rects()
            pos = e.position().toPoint()
            hb = "pin" if pin.contains(pos) else "menu" if menu.contains(pos) else None
            if hb != self._hover_btn:
                self._hover_btn = hb
                self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._dragging:
            self._press = None
            return
        self._press = None
        pos = e.position().toPoint()
        if not self.rect().contains(pos):
            return
        if self._actions:
            pin, menu = self._btn_rects()
            if pin.contains(pos):
                self.pinClicked.emit()
                return
            if menu.contains(pos):
                self.menuClicked.emit(self.mapToGlobal(QPoint(menu.left(), menu.bottom() + 4)))
                return
        self.last_mods = e.modifiers()
        self.clicked.emit()

    def contextMenuEvent(self, e) -> None:
        self.context.emit(e.globalPos())

    # ----- cible de dépôt -----
    def dragEnterEvent(self, e) -> None:
        if mime_ids(e.mimeData()):
            e.acceptProposedAction()
            self._drop_hover = True
            self.update()

    def dragMoveEvent(self, e) -> None:
        if mime_ids(e.mimeData()):
            e.acceptProposedAction()

    def dragLeaveEvent(self, e) -> None:
        self._drop_hover = False
        self.update()

    def dropEvent(self, e) -> None:
        self._drop_hover = False
        self.update()
        ids = mime_ids(e.mimeData())
        if ids:
            e.acceptProposedAction()
            self.dropped.emit(ids)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._drop_hover:                       # cible de dépôt : contour bleu
            p.setPen(QColor("#5b8cff"))
            p.setBrush(QColor(91, 140, 255, 45))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
        elif self._checked or self._selected or self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#2f4a86" if self._checked else "#2d2d2e" if self._selected else "#252627"))
            p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        x = 12 + self._indent
        if self._icon:
            pm = icon_pixmap(self._icon, self._icon_color or theme.TEXT, 18, self.devicePixelRatioF())
            p.drawPixmap(x, (self.height() - 18) // 2, pm)
            x += 28
        if self._tag in TAG_COLORS:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(TAG_COLORS[self._tag]))
            p.drawEllipse(QRectF(x, (self.height() - 8) / 2, 8, 8))
            x += 16
        show_actions = self._actions and self._hover
        p.setPen(QColor(theme.TEXT if self._selected else "#dcdcdc"))
        fm = QFontMetrics(self.font())
        right = 66 if show_actions else 10
        txt = fm.elidedText(self._text, Qt.ElideRight, max(10, self.width() - x - right))
        p.drawText(x, 0, self.width() - x, self.height(), Qt.AlignVCenter | Qt.AlignLeft, txt)
        if show_actions:
            pin, menu = self._btn_rects()
            for name, rect, icon in (("pin", pin, "pin"), ("menu", menu, "dots")):
                if self._hover_btn == name:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, 30))
                    p.drawRoundedRect(QRectF(rect), 8, 8)
                color = "#8fb0ff" if (name == "pin" and self._pinned) else theme.TEXT_DIM
                pm = icon_pixmap(icon, color, 17, self.devicePixelRatioF())
                p.drawPixmap(rect.left() + (rect.width() - 17) // 2, rect.top() + (rect.height() - 17) // 2, pm)


class _DropContent(QWidget):
    """Fond de la liste : y déposer des conversations les sort de leur dossier."""
    dropped = Signal(list)
    hovering = Signal(QPoint)

    def __init__(self, parent=None, **kw):
        super().__init__(parent, **kw)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e) -> None:
        if mime_ids(e.mimeData()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if mime_ids(e.mimeData()):
            e.acceptProposedAction()
            self.hovering.emit(self.mapToGlobal(e.position().toPoint()))

    def dropEvent(self, e) -> None:
        ids = mime_ids(e.mimeData())
        if ids:
            e.acceptProposedAction()
            self.dropped.emit(ids)


class SectionHeader(QWidget):
    def __init__(self, text: str, action_icon: str | None = None, tip: str = "", parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 4, 2)
        self.label = QLabel(text, objectName="HistorySection")
        h.addWidget(self.label)
        h.addStretch(1)
        self.button = None
        if action_icon:
            self.button = IconButton(action_icon, size=(26, 26), icon_size=16, radius=7, tooltip=tip)
            h.addWidget(self.button)


class ResizeHandle(QWidget):
    """Fine poignée entre l'historique et la conversation : glisser pour ouvrir, régler ou fermer."""
    pressed = Signal()
    moved = Signal(int)
    released = Signal()
    doubleClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(5)
        self.setCursor(Qt.SizeHorCursor)
        self.setMouseTracking(True)
        self._down_x = None
        self._hover = False

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._down_x = e.globalPosition().x()
            self.pressed.emit()

    def mouseMoveEvent(self, e) -> None:
        if self._down_x is not None:
            self.moved.emit(int(e.globalPosition().x() - self._down_x))

    def mouseReleaseEvent(self, e) -> None:
        if self._down_x is not None:
            self._down_x = None
            self.released.emit()

    def mouseDoubleClickEvent(self, e) -> None:
        self.doubleClicked.emit()

    def paintEvent(self, e) -> None:
        if self._hover or self._down_x is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(86, 140, 255, 150))
            p.drawRoundedRect(QRectF(self.width() / 2 - 1, 14, 2, self.height() - 28), 1, 1)


class HistoryPanel(QWidget):
    """Panneau coulissant : Nouveau chat, Dossiers (créables), Récents."""
    newChat = Signal()
    openConversation = Signal(int)
    renameConversation = Signal(int)
    deleteConversation = Signal(int)
    moveConversation = Signal(int, int)   # (conversation, dossier ; 0 = aucun)
    createFolder = Signal()
    renameFolder = Signal(int)
    deleteFolder = Signal(int)
    toggleFolder = Signal(int)
    searchRequested = Signal()
    conversationMenuRequested = Signal(int, QPoint)
    pinRequested = Signal(int)
    folderMenuRequested = Signal(int, QPoint)
    bulkDeleteRequested = Signal(list)      # ids des conversations sélectionnées
    bulkArchiveRequested = Signal(list, bool)
    bulkMoveRequested = Signal(list, int)   # (ids, dossier ; 0 = aucun) : glisser-déposer
    widthChanged = Signal(int)     # largeur choisie à la souris (à mémoriser)
    openChanged = Signal(bool)     # ouvert / fermé (aussi par glissement)

    WIDTH = 292                    # largeur par défaut
    MIN_W, MAX_W, COLLAPSE_W = 200, 520, 140

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HistoryPanel")
        self.setMaximumWidth(0)
        self.setMinimumWidth(0)
        self._open = False
        self._folders, self._convs, self._current = [], [], None
        self._show_archived = False
        self._sel: set[int] = set()          # sélection multiple (Ctrl / Maj + clic)
        self._anchor: int | None = None
        self._order: list[int] = []          # conversations visibles, dans l'ordre d'affichage
        self._width = self.WIDTH
        self._drag_start = 0
        self._anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 4)
        self.frame = QFrame(objectName="HistoryFrame")
        self.frame.setFixedWidth(self._width)
        outer.addWidget(self.frame, 1, Qt.AlignLeft)

        v = QVBoxLayout(self.frame)
        v.setContentsMargins(8, 10, 4, 8)
        v.setSpacing(2)
        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 4, 0)
        head.addWidget(QLabel("ChatLocal", objectName="HistoryTitle"))
        head.addStretch(1)
        self.search_btn = IconButton("search", size=(30, 30), icon_size=17, radius=8, tooltip="Rechercher (Ctrl+K)")
        self.search_btn.clicked.connect(self.searchRequested)
        head.addWidget(self.search_btn)
        v.addLayout(head)
        new = NavRow("Nouveau chat", "new_chat")
        new.clicked.connect(self.newChat)
        v.addWidget(new)

        self.scroll = QScrollArea(objectName="HistoryScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = _DropContent(objectName="HistoryContent")
        self.content.dropped.connect(lambda ids: self._drop_ids(ids, 0))
        self.content.hovering.connect(self._autoscroll)
        self.col = QVBoxLayout(self.content)
        self.col.setContentsMargins(0, 0, 4, 0)
        self.col.setSpacing(1)
        self.scroll.setWidget(self.content)
        v.addWidget(self.scroll, 1)

        # barre d'actions de la sélection multiple
        self.sel_bar = QFrame(objectName="SelBar")
        sv = QVBoxLayout(self.sel_bar)
        sv.setContentsMargins(12, 8, 6, 8)
        sv.setSpacing(6)
        top = QHBoxLayout()
        self.sel_label = QLabel(objectName="SelLabel")
        top.addWidget(self.sel_label, 1)
        close = IconButton("win_close", size=(26, 26), icon_size=12, radius=8, tooltip="Annuler la sélection (Échap)")
        close.clicked.connect(self.clear_selection)
        top.addWidget(close)
        sv.addLayout(top)
        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 6, 0)
        btns.setSpacing(6)
        self.sel_archive = QPushButton("Archiver", objectName="SelBtn")
        self.sel_delete = QPushButton("Supprimer", objectName="SelBtnDanger")
        for b_ in (self.sel_archive, self.sel_delete):
            b_.setCursor(Qt.PointingHandCursor)
            b_.setFocusPolicy(Qt.NoFocus)
            b_.setMinimumHeight(32)
            btns.addWidget(b_, 1)
        sv.addLayout(btns)
        self.sel_archive.clicked.connect(lambda: self.bulkArchiveRequested.emit(self.selected_ids(), True))
        self.sel_delete.clicked.connect(lambda: self.bulkDeleteRequested.emit(self.selected_ids()))
        self.sel_bar.hide()
        v.addWidget(self.sel_bar)

    # ----- ouverture -----
    def is_open(self) -> bool:
        return self._open

    def panel_width(self) -> int:
        return self._width

    def set_panel_width(self, w: int) -> None:
        self._width = max(self.MIN_W, min(self.MAX_W, int(w)))
        self.frame.setFixedWidth(self._width)
        if self._open:
            self.setMaximumWidth(self._width)

    def set_open(self, on: bool) -> None:
        self._open = on
        if on and getattr(self, "_stale", False):
            self._rebuild()
        self._anim.stop()
        if on:
            self.frame.setFixedWidth(self._width)
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(self._width if on else 0)
        self._anim.start()
        self.openChanged.emit(on)

    # ----- redimensionnement à la souris (poignée) -----
    def begin_drag(self) -> None:
        self._anim.stop()
        self._drag_start = self.maximumWidth() if self._open or self.maximumWidth() > 0 else 0
        if self._drag_start == 0:
            self.frame.setFixedWidth(self._width)

    def drag_to(self, dx: int) -> None:
        w = max(0, min(self.MAX_W, self._drag_start + dx))
        self.setMaximumWidth(w)
        self.frame.setFixedWidth(max(w, self.MIN_W))   # le contenu ne s'écrase pas : il est rogné

    def end_drag(self) -> None:
        w = self.maximumWidth()
        if w < self.COLLAPSE_W:                 # tiré assez loin : fermeture
            self._open = False
            self._anim.setStartValue(w)
            self._anim.setEndValue(0)
            self._anim.start()
            self.openChanged.emit(False)
        else:
            self._open = True
            self._width = max(self.MIN_W, min(self.MAX_W, w))
            self.setMaximumWidth(self._width)
            self.frame.setFixedWidth(self._width)
            self.widthChanged.emit(self._width)
            self.openChanged.emit(True)

    def reset_width(self) -> None:
        self.set_panel_width(self.WIDTH)
        self.widthChanged.emit(self._width)

    # ----- données -----
    def set_data(self, folders, convs, current: int | None) -> None:
        self._folders, self._convs, self._current = list(folders), list(convs), current
        self._sel &= {c["id"] for c in self._convs}      # une conversation supprimée quitte la sélection
        self._rebuild()

    # ----- sélection multiple -----
    def selected_ids(self) -> list[int]:
        return [cid for cid in self._order if cid in self._sel] + [c for c in self._sel if c not in self._order]

    def drop_selection(self) -> None:
        """Oublie la sélection sans redessiner (la liste est rechargée juste après)."""
        self._sel.clear()
        self._anchor = None

    def clear_selection(self) -> None:
        self._sel.clear()
        self._anchor = None
        self._rebuild()

    def _on_conv_click(self, cid: int, mods) -> None:
        if mods & Qt.ControlModifier:                    # Ctrl + clic : ajoute / retire
            self._sel ^= {cid}
            self._anchor = cid
        elif mods & Qt.ShiftModifier and self._order:    # Maj + clic : plage depuis la dernière ligne cliquée
            start = self._anchor if self._anchor in self._order else (
                self._current if self._current in self._order else cid)
            i, j = sorted((self._order.index(start), self._order.index(cid)))
            self._sel |= set(self._order[i:j + 1])
            self._anchor = start
        else:
            if self._sel:                                # clic simple : annule la sélection puis ouvre
                self._sel.clear()
                self._rebuild()
            self._anchor = cid
            self.openConversation.emit(cid)
            return
        self._rebuild()

    def event(self, e) -> bool:
        # Échap annule la sélection au lieu de déclencher le raccourci « arrêter la génération »
        if e.type() == QEvent.ShortcutOverride and e.key() == Qt.Key_Escape and self._sel:
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape and self._sel:
            self.clear_selection()
        elif e.key() == Qt.Key_Delete and self._sel:
            self.bulkDeleteRequested.emit(self.selected_ids())
        elif e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier and self._order:
            self._sel = set(self._order)
            self._rebuild()
        else:
            super().keyPressEvent(e)

    def select(self, cid: int | None) -> None:
        self._current = cid
        self._rebuild()

    def _rebuild(self) -> None:
        if not self._open and self.maximumWidth() == 0:      # panneau fermé : on reconstruira à l'ouverture
            self._stale = True
            return
        self._stale = False
        vpos = self.scroll.verticalScrollBar().value()
        while self.col.count():
            it = self.col.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        self._order = []
        live = [c for c in self._convs if not c["archived"]]
        pinned = [c for c in live if c["pinned"]]
        convs = [c for c in live if not c["pinned"]]
        archived = [c for c in self._convs if c["archived"]]
        if pinned:
            self.col.addWidget(SectionHeader("Épinglés"))
            for c in pinned:
                self.col.addWidget(self._conv_row(c, 0))
            self.col.addSpacing(8)
        hdr = SectionHeader("Dossiers", "plus", "Nouveau dossier")
        hdr.button.clicked.connect(self.createFolder)
        self.col.addWidget(hdr)
        by_folder: dict[int, list] = {}
        for c in convs:
            if c["folder_id"] is not None:
                by_folder.setdefault(c["folder_id"], []).append(c)
        for f in self._folders:
            fid = f["id"]
            expanded = bool(f["expanded"])
            row = NavRow(f["name"], "folder_open" if expanded else "folder", icon_color=TAG_COLORS.get(f["color"]))
            row.clicked.connect(lambda fid=fid: self.toggleFolder.emit(fid))
            row.context.connect(lambda pos, fid=fid: self._folder_menu(fid, pos))
            row.setAcceptDrops(True)
            row.dropped.connect(lambda ids, fid=fid: self._drop_ids(ids, fid))
            self.col.addWidget(row)
            if expanded:
                kids = by_folder.get(fid, [])
                for c in kids:
                    self.col.addWidget(self._conv_row(c, 26))
                if not kids:
                    self.col.addWidget(self._muted("Dossier vide", 38))
        if not self._folders:
            self.col.addWidget(self._muted("Crée un dossier avec +"))
        self.col.addSpacing(8)
        self.col.addWidget(SectionHeader("Récents"))
        loose = [c for c in convs if c["folder_id"] is None]
        for c in loose:
            self.col.addWidget(self._conv_row(c, 0))
        if not loose:
            self.col.addWidget(self._muted("Aucune conversation"))
        if archived:
            self.col.addSpacing(8)
            arow = NavRow(f"Archivés ({len(archived)})", "archive")
            arow.clicked.connect(self._toggle_archived)
            self.col.addWidget(arow)
            if self._show_archived:
                for c in archived:
                    self.col.addWidget(self._conv_row(c, 26))
        self.col.addStretch(1)
        self.scroll.verticalScrollBar().setValue(vpos)
        n = len(self._sel)
        self.sel_bar.setVisible(n > 0)
        if n:
            self.sel_label.setText(f"{n} sélectionnée{'s' if n > 1 else ''}")
        self.setFocusPolicy(Qt.StrongFocus if n else Qt.NoFocus)
        if n:
            self.setFocus()

    def _drop_ids(self, ids: list, fid: int) -> None:
        """Conversations déposées sur un dossier (fid) ou hors de tout dossier (0)."""
        self.drop_selection()
        self.bulkMoveRequested.emit(ids, fid)

    def _drag_ids(self, cid: int) -> list[int]:
        """Conversations emportées par le glisser : toute la sélection si la ligne en fait partie."""
        return self.selected_ids() if cid in self._sel else [cid]

    def _autoscroll(self, global_pos: QPoint) -> None:
        """Fait défiler la liste quand on glisse près du bord haut ou bas."""
        vp = self.scroll.viewport()
        y = vp.mapFromGlobal(global_pos).y()
        bar = self.scroll.verticalScrollBar()
        if y < 30:
            bar.setValue(bar.value() - 24)
        elif y > vp.height() - 30:
            bar.setValue(bar.value() + 24)

    def _toggle_archived(self) -> None:
        self._show_archived = not self._show_archived
        self._rebuild()

    def _muted(self, text: str, indent: int = 12) -> QLabel:
        lb = QLabel(text, objectName="HistoryEmpty")
        lb.setContentsMargins(indent, 4, 0, 4)
        return lb

    def _conv_row(self, c, indent: int) -> NavRow:
        cid = c["id"]
        self._order.append(cid)
        row = NavRow(c["title"], None, indent, selected=(cid == self._current), actions=True,
                     pinned=bool(c["pinned"]), tag=c["tag"], checked=(cid in self._sel))
        row.clicked.connect(lambda cid=cid, row=row: self._on_conv_click(cid, row.last_mods))
        row.context.connect(lambda pos, cid=cid: self._conv_menu(cid, pos))
        row.menuClicked.connect(lambda pos, cid=cid: self._conv_menu(cid, pos))
        row.pinClicked.connect(lambda cid=cid: self.pinRequested.emit(cid))
        row.drag_ids = lambda cid=cid: self._drag_ids(cid)       # la ligne se glisse vers un dossier
        row.setAcceptDrops(True)                                 # et sert de cible : même dossier que cette ligne
        target = 0 if c["pinned"] else int(c["folder_id"] or 0)
        row.dropped.connect(lambda ids, t=target: self._drop_ids(ids, t))
        return row

    # ----- menus contextuels -----
    def _conv_menu(self, cid: int, pos: QPoint) -> None:
        self.conversationMenuRequested.emit(cid, pos)

    def _folder_menu(self, fid: int, pos: QPoint) -> None:
        self.folderMenuRequested.emit(fid, pos)


def ask_text(parent, title: str, label: str, text: str = "") -> str | None:
    value, ok = QInputDialog.getText(parent, title, label, QLineEdit.Normal, text)
    value = value.strip()
    return value if ok and value else None


def confirm(parent, title: str, text: str, info: str, button: str = "Supprimer") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setInformativeText(info)
    yes = box.addButton(button, QMessageBox.DestructiveRole)
    box.addButton("Annuler", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes

