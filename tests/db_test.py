"""Test base de données : arbre de messages (versions d'un prompt) + migration d'une ancienne base."""
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database.db import Database  # noqa: E402

fails = 0


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


tmp = Path(tempfile.mkdtemp())

# --- ancienne base (avant l'arbre) ---
old = sqlite3.connect(tmp / "old.db")
old.executescript("""
CREATE TABLE conversations(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, model TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL,
  role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
INSERT INTO conversations VALUES(1,'ancienne','m',1,1);
INSERT INTO messages(conversation_id,role,content,created_at) VALUES(1,'user','q1',1),(1,'assistant','r1',2),(1,'user','q2',3);
""")
old.commit()
old.close()
db = Database(tmp / "old.db")
check("migration : conversation linéaire conservée",
      [(r["role"], r["content"]) for r in db.get_messages(1)] == [("user", "q1"), ("assistant", "r1"), ("user", "q2")])
db.close()

# --- arbre ---
db = Database(tmp / "new.db")
cid = db.create_conversation("t", "m")
u1 = db.add_message(cid, "user", "A")
a1 = db.add_message(cid, "assistant", "réponse A")
u2 = db.add_message(cid, "user", "B")
a2 = db.add_message(cid, "assistant", "réponse B")
check("branche initiale (4 messages, 1/1)", [m["content"] for m in db.get_path(cid)] == ["A", "réponse A", "B", "réponse B"]
      and db.version_info(u1) == (1, 1))

# modification de B (parent = a1) : nouvelle version, l'ancienne est conservée
u2b = db.add_message(cid, "user", "B modifié", parent=a1)
a2b = db.add_message(cid, "assistant", "réponse B modifié")
path = db.get_path(cid)
check("nouvelle branche active", [m["content"] for m in path] == ["A", "réponse A", "B modifié", "réponse B modifié"])
check("version 2/2 sur le prompt modifié", (path[2]["ver"], path[2]["total"]) == (2, 2))
check("ancienne version conservée en base", db.siblings(u2b) == [u2, u2b])

db.select_version(u2)
check("retour à la version 1 (avec sa réponse)", [m["content"] for m in db.get_path(cid)] == ["A", "réponse A", "B", "réponse B"])

# modification du tout premier message (racine)
u1b = db.add_message(cid, "user", "A modifié", parent=None)
check("racine : 2 versions, branche vide ensuite", [m["content"] for m in db.get_path(cid)] == ["A modifié"]
      and db.version_info(u1b) == (2, 2))
db.select_version(u1)
check("retour à la racine d'origine (branche imbriquée conservée)",
      [m["content"] for m in db.get_path(cid)] == ["A", "réponse A", "B", "réponse B"])
db.select_version(u2b)
check("version imbriquée toujours disponible", db.get_path(cid)[-1]["content"] == "réponse B modifié")
db.delete_conversation(cid)
check("suppression de conversation : messages supprimés",
      db.db.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (cid,)).fetchone()[0] == 0)
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
