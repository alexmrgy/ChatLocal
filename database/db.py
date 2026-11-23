"""Stockage SQLite des conversations (utilisé depuis le thread GUI uniquement)."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path


def _load_files(raw) -> list:
    try:
        return json.loads(raw) if raw else []
    except ValueError:
        return []


def data_dir() -> Path:
    override = os.environ.get("CHATLOCAL_DATA_DIR")
    base = Path(override) if override else Path(os.environ.get("APPDATA", Path.home())) / "ChatLocal"
    base.mkdir(parents=True, exist_ok=True)
    return base


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else data_dir() / "conversations.db"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                model TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, id);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS folders(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                expanded INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL);
            """
        )
        cols = [r["name"] for r in self.db.execute("PRAGMA table_info(conversations)")]
        if "folder_id" not in cols:  # migration des bases créées avant les dossiers
            self.db.execute("ALTER TABLE conversations ADD COLUMN folder_id INTEGER")
        for flag in ("pinned", "locked", "archived"):
            if flag not in cols:
                self.db.execute(f"ALTER TABLE conversations ADD COLUMN {flag} INTEGER NOT NULL DEFAULT 0")
        fcols = [r["name"] for r in self.db.execute("PRAGMA table_info(folders)")]
        if "color" not in fcols:
            self.db.execute("ALTER TABLE folders ADD COLUMN color TEXT")
        if "tag" not in cols:
            self.db.execute("ALTER TABLE conversations ADD COLUMN tag TEXT")
        if "root_selected" not in cols:
            self.db.execute("ALTER TABLE conversations ADD COLUMN root_selected INTEGER")
        if "compare" not in cols:       # comparaison de deux modèles (JSON) : NULL pour une conversation normale
            self.db.execute("ALTER TABLE conversations ADD COLUMN compare TEXT")
        mcols = [r["name"] for r in self.db.execute("PRAGMA table_info(messages)")]
        if "quote" not in mcols:
            self.db.execute("ALTER TABLE messages ADD COLUMN quote TEXT")
        if "files" not in mcols:        # fichiers joints (JSON)
            self.db.execute("ALTER TABLE messages ADD COLUMN files TEXT")
        if "parent_id" not in mcols:  # migration : messages linéaires -> arbre (versions d'un prompt)
            self.db.execute("ALTER TABLE messages ADD COLUMN parent_id INTEGER")
            self.db.execute("ALTER TABLE messages ADD COLUMN selected_child INTEGER")
            for c in self.db.execute("SELECT id FROM conversations").fetchall():
                ids = [r["id"] for r in self.db.execute(
                    "SELECT id FROM messages WHERE conversation_id=? ORDER BY id", (c["id"],))]
                for i, mid in enumerate(ids):
                    self.db.execute("UPDATE messages SET parent_id=?, selected_child=? WHERE id=?",
                                    (ids[i - 1] if i else None, ids[i + 1] if i + 1 < len(ids) else None, mid))
                if ids:
                    self.db.execute("UPDATE conversations SET root_selected=? WHERE id=?", (ids[0], c["id"]))
        self.db.commit()

    # dossiers
    def create_folder(self, name: str) -> int:
        cur = self.db.execute("INSERT INTO folders(name, created_at) VALUES(?,?)", (name, time.time()))
        self.db.commit()
        return cur.lastrowid

    def list_folders(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM folders ORDER BY created_at, id").fetchall()

    def rename_folder(self, fid: int, name: str) -> None:
        self.db.execute("UPDATE folders SET name=? WHERE id=?", (name, fid))
        self.db.commit()

    def set_folder_color(self, fid: int, color: str | None) -> None:
        self.db.execute("UPDATE folders SET color=? WHERE id=?", (color, fid))
        self.db.commit()

    def set_folder_expanded(self, fid: int, expanded: bool) -> None:
        self.db.execute("UPDATE folders SET expanded=? WHERE id=?", (int(expanded), fid))
        self.db.commit()

    def delete_folder(self, fid: int) -> None:
        """Supprime le dossier ; ses conversations reviennent dans Récents."""
        self.db.execute("UPDATE conversations SET folder_id=NULL WHERE folder_id=?", (fid,))
        self.db.execute("DELETE FROM folders WHERE id=?", (fid,))
        self.db.commit()

    def move_conversation(self, cid: int, fid: int | None) -> None:
        self.db.execute("UPDATE conversations SET folder_id=? WHERE id=?", (fid, cid))
        self.db.commit()

    # conversations
    def create_conversation(self, title: str, model: str | None) -> int:
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO conversations(title, model, created_at, updated_at) VALUES(?,?,?,?)",
            (title, model, now, now),
        )
        self.db.commit()
        return cur.lastrowid

    def set_compare(self, cid: int, data: dict) -> None:
        """Enregistre (ou met à jour) les données d'une comparaison de deux modèles."""
        self.db.execute("UPDATE conversations SET compare=?, updated_at=? WHERE id=?",
                        (json.dumps(data, ensure_ascii=False), time.time(), cid))
        self.db.commit()

    @staticmethod
    def compare_data(row) -> dict | None:
        try:
            data = json.loads(row["compare"]) if row["compare"] else None
        except (ValueError, KeyError):
            return None
        return data if isinstance(data, dict) else None

    def list_conversations(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM conversations ORDER BY updated_at DESC, id DESC").fetchall()

    def get_conversation(self, cid: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()

    def set_flag(self, cid: int, flag: str, on: bool) -> None:
        """flag : 'pinned' | 'locked' | 'archived'."""
        if flag not in ("pinned", "locked", "archived"):
            raise ValueError(flag)
        self.db.execute(f"UPDATE conversations SET {flag}=? WHERE id=?", (int(on), cid))
        self.db.commit()

    def set_tag(self, cid: int, tag: str | None) -> None:
        """Section = étiquette de couleur (rouge, orange, jaune, vert, bleu, violet) ou None."""
        self.db.execute("UPDATE conversations SET tag=? WHERE id=?", (tag, cid))
        self.db.commit()

    def rename_conversation(self, cid: int, title: str) -> None:
        self.db.execute("UPDATE conversations SET title=? WHERE id=?", (title, cid))
        self.db.commit()

    def set_conversation_model(self, cid: int, model: str) -> None:
        self.db.execute("UPDATE conversations SET model=? WHERE id=?", (model, cid))
        self.db.commit()

    def delete_conversation(self, cid: int) -> None:
        self.db.execute("DELETE FROM conversations WHERE id=?", (cid,))
        self.db.commit()

    # messages : arbre, chaque message garde le lien vers son parent ; modifier un prompt crée une
    # nouvelle branche (version) sans rien supprimer.
    def current_path(self, cid: int) -> list[sqlite3.Row]:
        conv = self.get_conversation(cid)
        rid = conv["root_selected"] if conv else None
        out, seen = [], set()
        while rid and rid not in seen:
            seen.add(rid)
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (rid,)).fetchone()
            if not row:
                break
            out.append(row)
            rid = row["selected_child"]
        return out

    def add_message(self, cid: int, role: str, content: str, parent="leaf", quote: str | None = None,
                    files: list | None = None) -> int:
        """Ajoute un message. parent="leaf" : à la fin de la branche courante ; sinon id du parent (None = racine)."""
        now = time.time()
        if parent == "leaf":
            path = self.current_path(cid)
            parent_id = path[-1]["id"] if path else None
        else:
            parent_id = parent
        cur = self.db.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at, parent_id, quote, files) VALUES(?,?,?,?,?,?,?)",
            (cid, role, content, now, parent_id, quote or None, json.dumps(files) if files else None),
        )
        mid = cur.lastrowid
        self._point_to(cid, parent_id, mid)
        self.db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, cid))
        self.db.commit()
        return mid

    def update_message_content(self, mid: int, content: str) -> None:
        """Remplace le texte d'un message (ex. code modifié dans le panneau de droite)."""
        self.db.execute("UPDATE messages SET content=? WHERE id=?", (content, mid))
        self.db.commit()

    def _point_to(self, cid: int, parent_id: int | None, mid: int) -> None:
        if parent_id is None:
            self.db.execute("UPDATE conversations SET root_selected=? WHERE id=?", (mid, cid))
        else:
            self.db.execute("UPDATE messages SET selected_child=? WHERE id=?", (mid, parent_id))

    def siblings(self, mid: int) -> list[int]:
        row = self.db.execute("SELECT conversation_id, parent_id FROM messages WHERE id=?", (mid,)).fetchone()
        if not row:
            return []
        if row["parent_id"] is None:
            q = self.db.execute("SELECT id FROM messages WHERE conversation_id=? AND parent_id IS NULL ORDER BY id",
                                (row["conversation_id"],))
        else:
            q = self.db.execute("SELECT id FROM messages WHERE parent_id=? ORDER BY id", (row["parent_id"],))
        return [r["id"] for r in q]

    def version_info(self, mid: int) -> tuple[int, int]:
        """(numéro de version, nombre de versions) de ce message parmi ses frères."""
        sibs = self.siblings(mid)
        return (sibs.index(mid) + 1, len(sibs)) if mid in sibs else (1, 1)

    def select_version(self, mid: int) -> None:
        """Rend `mid` (une version d'un prompt) la branche courante."""
        row = self.db.execute("SELECT conversation_id, parent_id FROM messages WHERE id=?", (mid,)).fetchone()
        if row:
            self._point_to(row["conversation_id"], row["parent_id"], mid)
            self.db.commit()

    def get_path(self, cid: int) -> list[dict]:
        """Branche courante avec, pour chaque message, son numéro de version et le nombre de versions."""
        out = []
        for r in self.current_path(cid):
            ver, total = self.version_info(r["id"])
            out.append({"id": r["id"], "role": r["role"], "content": r["content"], "ver": ver, "total": total,
                        "quote": r["quote"] or "", "files": _load_files(r["files"])})
        return out

    def get_messages(self, cid: int) -> list[sqlite3.Row]:
        return self.current_path(cid)

    # réglages
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)", (key, value))
        self.db.commit()

    def clear_skip_confirms(self) -> int:
        cur = self.db.execute("DELETE FROM settings WHERE key LIKE 'skip_confirm:%'")
        self.db.commit()
        return cur.rowcount

    # secrets (chiffrés)
    def set_secret(self, key: str, value: str) -> None:
        from . import secrets
        self.set_setting("secret:" + key, secrets.protect(value))

    def get_secret(self, key: str) -> str | None:
        from . import secrets
        blob = self.get_setting("secret:" + key)
        return secrets.unprotect(blob) if blob else None

    def delete_secret(self, key: str) -> None:
        self.db.execute("DELETE FROM settings WHERE key=?", ("secret:" + key,))
        self.db.commit()

    def close(self) -> None:
        self.db.close()
