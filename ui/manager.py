"""Page « Toutes les discussions » : liste avec sélection multiple et actions groupées."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from . import theme
from .action_menu import SEP, ActionMenu, MenuItem
from .dialogs import _Check
from .icons import icon_pixmap

COL_STATUS, COL_DATE, COL_FOLDER = 78, 150, 170


def _box(p: QPainter, x: float, y: float, on: bool, partial: bool = False) -> None:
    r = QRectF(x, y, 20, 20)
    if on or partial:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor("#ffffff"))
        if partial and not on:
            p.drawLine(int(x + 5), int(y + 10), int(x + 15), int(y + 10))
        else:
            p.drawPixmap(int(x + 2), int(y + 2), icon_pixmap("check", "#ffffff", 16, p.device().devicePixelRatioF()))
    else:
        p.setPen(QColor(90, 90, 90))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


class _HeaderRow(QWidget):
    """Ligne d'en-tête du tableau + case « tout sélectionner » (tri-état)."""
    toggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.ArrowCursor)
        self.state = 0   # 0 aucun, 1 partiel, 2 tout
        f = QFont(self.font())
        f.setPixelSize(13)
        self.setFont(f)

    def set_state(self, s: int) -> None:
        self.state = s
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and e.position().x() < 56:
            self.toggled.emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        _box(p, 18, (self.height() - 20) / 2, self.state == 2, self.state == 1)
        p.setPen(QColor(theme.TEXT_MUTE))
        w = self.width()
        p.drawText(56, 0, w - 56 - COL_STATUS - COL_DATE - COL_FOLDER, self.height(), Qt.AlignVCenter, "Titre")
        p.drawText(w - COL_STATUS - COL_DATE - COL_FOLDER, 0, COL_FOLDER, self.height(), Qt.AlignVCenter, "Dossier")
        p.drawText(w - COL_STATUS - COL_DATE, 0, COL_DATE, self.height(), Qt.AlignVCenter, "Dernière activité")
        p.setPen(QColor(255, 255, 255, 22))
        p.drawLine(12, self.height() - 1, w - 12, self.height() - 1)


class _Row(QWidget):
    toggled = Signal()
    opened = Signal()

    def __init__(self, conv, folder: str, selected: bool, parent=None):
        super().__init__(parent)
        self.conv, self.folder, self.selected, self._hover = conv, folder, selected, False
        self.setFixedHeight(46)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        f = QFont(self.font())
        f.setPixelSize(15)
        self.setFont(f)
        self.setToolTip(conv["title"])

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        if e.position().x() < 56:
            self.toggled.emit()
        else:
            self.opened.emit()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, w, h = self.conv, self.width(), self.height()
        if self.selected or self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(72, 103, 190, 40) if self.selected else QColor(255, 255, 255, 12))
            p.drawRoundedRect(QRectF(6, 2, w - 12, h - 4), 10, 10)
        _box(p, 18, (h - 20) / 2, self.selected)
        x = 56
        if c["tag"]:
            from .sidebar import TAG_COLORS
            col = TAG_COLORS.get(c["tag"])
            if col:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(col))
                p.drawEllipse(QRectF(x, (h - 8) / 2, 8, 8))
                x += 16
        tw = w - x - COL_STATUS - COL_DATE - COL_FOLDER - 12
        fm = QFontMetrics(self.font())
        p.setPen(QColor(theme.TEXT))
        p.drawText(x, 0, tw, h, Qt.AlignVCenter, fm.elidedText(c["title"], Qt.ElideRight, tw))
        p.setPen(QColor(theme.TEXT_DIM))
        fx = w - COL_STATUS - COL_DATE - COL_FOLDER
        p.drawText(fx, 0, COL_FOLDER - 10, h, Qt.AlignVCenter, fm.elidedText(self.folder or "—", Qt.ElideRight, COL_FOLDER - 10))
        p.drawText(w - COL_STATUS - COL_DATE, 0, COL_DATE, h, Qt.AlignVCenter,
                   datetime.fromtimestamp(c["updated_at"]).strftime("%d/%m/%Y  %H:%M"))
        sx = w - COL_STATUS + 4
        for flag, icon in (("pinned", "pin"), ("locked", "lock"), ("archived", "archive")):
            if c[flag]:
                p.drawPixmap(sx, (h - 16) // 2, icon_pixmap(icon, theme.TEXT_DIM, 16, self.devicePixelRatioF()))
                sx += 22


class ManagerPage(QWidget):
    openConversation = Signal(int)
    deleteRequested = Signal(list)
    archiveRequested = Signal(list, bool)
    pinRequested = Signal(list, bool)
    moveRequested = Signal(list, int)      # (ids, dossier ; 0 = aucun)
    exportRequested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._convs, self._folders = [], []
        self._selected: set[int] = set()
        self._tab = 0
        self._visible_ids: list[int] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(44, 8, 44, 18)
        v.setSpacing(10)
        top = QHBoxLayout()
        title = QLabel("Toutes les discussions", objectName="ManagerTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.search = QLineEdit(objectName="ManagerSearch")
        self.search.setPlaceholderText("Rechercher")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda _: self._rebuild())
        top.addWidget(self.search)
        v.addLayout(top)

        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        grp = QButtonGroup(self)
        for i, name in enumerate(("Toutes", "Épinglées", "Archivées")):
            b = QPushButton(name, objectName="PaletteTab")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, i=i: self._set_tab(i))
            grp.addButton(b)
            tabs.addWidget(b)
        tabs.addStretch(1)
        self.count = QLabel(objectName="ManagerCount")
        tabs.addWidget(self.count)
        v.addLayout(tabs)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btns: dict[str, QPushButton] = {}
        for key, text, icon in (("pin", "Épingler", "pin"), ("archive", "Archiver", "archive"),
                                ("move", "Déplacer", "folder_move"), ("export", "Exporter", "export"),
                                ("delete", "Supprimer", "trash")):
            b = QPushButton(text, objectName="ManagerBtn")
            b.setProperty("danger", key == "delete")
            b.setIcon(QIcon(icon_pixmap(icon, "#ff6b6b" if key == "delete" else theme.TEXT, 17, self.devicePixelRatioF())))
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(36)
            b.clicked.connect(lambda _=False, k=key: self._action(k))
            self.btns[key] = b
            bar.addWidget(b)
        bar.addStretch(1)
        self.sel_label = QLabel(objectName="ManagerCount")
        bar.addWidget(self.sel_label)
        v.addLayout(bar)

        self.header = _HeaderRow()
        self.header.toggled.connect(self.toggle_all)
        v.addWidget(self.header)
        self.scroll = QScrollArea(objectName="ManagerScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget(objectName="ManagerContent")
        self.col = QVBoxLayout(self.content)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(0)
        self.scroll.setWidget(self.content)
        v.addWidget(self.scroll, 1)
        self._sync_buttons()

    # ----- données -----
    def set_data(self, convs, folders) -> None:
        self._convs, self._folders = list(convs), list(folders)
        ids = {c["id"] for c in self._convs}
        self._selected &= ids                 # une discussion supprimée n'est plus sélectionnée
        self._rebuild()

    def _set_tab(self, i: int) -> None:
        self._tab = i
        self._rebuild()

    def selected_ids(self) -> list[int]:
        return [c["id"] for c in self._convs if c["id"] in self._selected]

    def _filtered(self) -> list:
        q = self.search.text().strip().lower()
        out = []
        for c in self._convs:
            if self._tab == 0 and c["archived"]:
                continue
            if self._tab == 1 and not (c["pinned"] and not c["archived"]):
                continue
            if self._tab == 2 and not c["archived"]:
                continue
            if q and q not in c["title"].lower():
                continue
            out.append(c)
        return out

    def _rebuild(self) -> None:
        while self.col.count():
            it = self.col.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        fname = {f["id"]: f["name"] for f in self._folders}
        rows = self._filtered()
        self._visible_ids = [c["id"] for c in rows]
        for c in rows:
            r = _Row(c, fname.get(c["folder_id"], ""), c["id"] in self._selected)
            r.toggled.connect(lambda cid=c["id"]: self._toggle(cid))
            r.opened.connect(lambda cid=c["id"]: self.openConversation.emit(cid))
            self.col.addWidget(r)
        if not rows:
            lb = QLabel("Aucune discussion", objectName="HistoryEmpty")
            lb.setAlignment(Qt.AlignCenter)
            lb.setContentsMargins(0, 40, 0, 0)
            self.col.addWidget(lb)
        self.col.addStretch(1)
        self._sync_buttons()

    # ----- sélection -----
    def _toggle(self, cid: int) -> None:
        self._selected ^= {cid}
        self._rebuild()

    def toggle_all(self) -> None:
        """Tout sélectionner (parmi les discussions affichées) ; si tout l'est déjà, tout désélectionner."""
        vis = set(self._visible_ids)
        if vis and vis <= self._selected:
            self._selected -= vis
        else:
            self._selected |= vis
        self._rebuild()

    def _sync_buttons(self) -> None:
        sel = self.selected_ids()
        vis = set(self._visible_ids)
        n_vis_sel = len(vis & self._selected)
        self.header.set_state(0 if n_vis_sel == 0 else 2 if n_vis_sel == len(vis) else 1)
        self.count.setText(f"{len(vis)} discussion{'s' if len(vis) > 1 else ''}")
        self.sel_label.setText(f"{len(sel)} sélectionnée{'s' if len(sel) > 1 else ''}" if sel else "Aucune sélection")
        for b in self.btns.values():
            b.setEnabled(bool(sel))
        rows = [c for c in self._convs if c["id"] in self._selected]
        all_pinned = bool(rows) and all(c["pinned"] for c in rows)
        all_arch = bool(rows) and all(c["archived"] for c in rows)
        self.btns["pin"].setText("Désépingler" if all_pinned else "Épingler")
        self.btns["archive"].setText("Désarchiver" if all_arch else "Archiver")

    def _action(self, key: str) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        rows = [c for c in self._convs if c["id"] in self._selected]
        if key == "delete":
            self.deleteRequested.emit(ids)
        elif key == "export":
            self.exportRequested.emit(ids)
        elif key == "archive":
            self.archiveRequested.emit(ids, not all(c["archived"] for c in rows))
        elif key == "pin":
            self.pinRequested.emit(ids, not all(c["pinned"] for c in rows))
        elif key == "move":
            items = [MenuItem(f["name"], "folder", callback=lambda fid=f["id"]: self.moveRequested.emit(ids, fid))
                     for f in self._folders]
            if items:
                items.append(SEP)
            items.append(MenuItem("Aucun dossier (Récents)", "chat", callback=lambda: self.moveRequested.emit(ids, 0)))
            self._menu = ActionMenu(items, self)
            b = self.btns["move"]
            self._menu.popup(b.mapToGlobal(QPoint(0, b.height() + 6)))
