"""Fenêtre « Mémoire » : voir, ajouter, supprimer les souvenirs et activer ou non la mémoire."""
from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)
from PySide6.QtCore import Qt

import memory


class MemoryDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setObjectName("MemoryDialog")
        self.setWindowTitle("Mémoire de l'IA")
        self.resize(560, 440)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        self.enabled = QCheckBox("Utiliser la mémoire")
        self.enabled.setChecked(db.get_setting("memory_enabled", "1") == "1")
        self.enabled.toggled.connect(lambda on: db.set_setting("memory_enabled", "1" if on else "0"))
        v.addWidget(self.enabled)
        hint = QLabel("Écris « Souviens-toi que … » dans une discussion, ou ajoute une information ici. "
                      "Tout reste sur ton PC. Les chats éphémères n'utilisent pas la mémoire.", wordWrap=True)
        v.addWidget(hint)

        self.list = QListWidget(objectName="MemoryList")
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setWordWrap(True)
        v.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.edit = QLineEdit(objectName="MemoryEdit")
        self.edit.setPlaceholderText("Ex. : Je m'appelle Sam et je code en Python")
        self.edit.setMaxLength(memory.MAX_LEN)
        self.add_btn = QPushButton("Ajouter")
        self.add_btn.clicked.connect(self.add)
        row.addWidget(self.edit, 1)
        row.addWidget(self.add_btn)
        v.addLayout(row)

        row = QHBoxLayout()
        self.delete_btn = QPushButton("Supprimer la sélection")
        self.delete_btn.clicked.connect(self.delete_selected)
        close = QPushButton("Fermer")
        close.clicked.connect(self.accept)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        row.addWidget(close)
        v.addLayout(row)
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)
        self.edit.returnPressed.connect(self.add)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for r in self.db.list_memories():
            item = QListWidgetItem(r["content"])
            item.setData(Qt.UserRole, r["id"])
            self.list.addItem(item)

    def add(self) -> None:
        if self.db.add_memory(self.edit.text()):
            self.edit.clear()
            self.reload()

    def delete_selected(self) -> None:
        for item in self.list.selectedItems():
            self.db.delete_memory(item.data(Qt.UserRole))
        self.reload()
