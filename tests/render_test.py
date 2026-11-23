"""Capture du rendu Markdown / code / historique (sans Ollama)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
os.environ["CHATLOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="chatlocal_render_")

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

SAMPLE = """# Titre

Voici une **réponse** avec `du code inline` et un [lien](https://example.com).

- premier point
- second point

```python
def add(a, b):
    # additionne
    return a + b

print(add(2, 3))
```

| Entreprise | Secteur | Année de création |
|------------|---------|------------------:|
| Apple      | Technologie | 1976 |
| Microsoft  | Informatique | 1975 |
| Google     | Internet / IA | 1998 |

Fin avec un bloc non fermé :

```js
const x = 1;
"""

app = QApplication([])
app_main.load_fonts(app)
app_main.load_style(app)
db = Database()
cid = db.create_conversation("Test de rendu Markdown", "phi4-mini:latest")
db.add_message(cid, "user", "Montre-moi du Markdown et du code.")
db.add_message(cid, "assistant", SAMPLE)
c2 = db.create_conversation("Autre conversation", "qwen3.5:9b")
f1 = db.create_folder("Avenor")
c3 = db.create_conversation("Analyser l'accueil et la démo", "qwen3.5:9b")
db.move_conversation(c3, f1)
db.create_folder("Dossier vide")
for t in ("Installer Phi 4 Mini", "Attendre avant de trader", "Alternatives gratuites à Bloomberg"):
    db.create_conversation(t, "phi4-mini:latest")
win = MainWindow(db)
win.show()


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


pump(1500)
win.open_conversation(cid)
win.toggle_history()
pump(800)
win.models, win.running = ["qwen3.5:9b", "phi4-mini:latest"], True
win.input.set_models(win.models, True)
win.input._open_menu()
pump(300)
win.input._popup.grab().save(str(OUT / "shot_popup.png"))
win.input._popup.close()
# clic sur « Copier » du 1er bloc de code + copier la réponse
from ui.messages import CodeBlock  # noqa: E402
cb = win.findChildren(CodeBlock)[0]
cb.copy_btn.click()
am = win.chat.findChildren(__import__("ui.messages", fromlist=["AssistantMessage"]).AssistantMessage)[0]
am.copy_btn.click()
pump(300)
win.grab().save(str(OUT / "shot_render.png"))
win.resize(1280, 800)
win.open_search()
pump(120)
win.grab().save(str(OUT / "shot_palette_mid.png"))
pump(500)
win.grab().save(str(OUT / "shot_palette.png"))
win.palette.edit.setText("mark")
pump(100)
assert len(win.palette._rows) == 1, len(win.palette._rows)
win.palette.close_palette()
pump(500)
assert not win.palette.isVisible()
n_before = len(db.list_folders())
win.create_folder()
pump(600)
win.grab().save(str(OUT / "shot_prompt.png"))
win.prompt.edit.setText("Mon nouveau dossier")
win.prompt.ok.click()
pump(500)
assert len(db.list_folders()) == n_before + 1 and not win.prompt.isVisible()
win.resize(760, 560)
pump(500)
win.grab().save(str(OUT / "shot_small.png"))
win.close()
