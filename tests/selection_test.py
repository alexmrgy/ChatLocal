"""Capture de la couleur de sélection du texte (réponse + bloc de code)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
OUT = Path(sys.argv[1])

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication, QTextBrowser  # noqa: E402

import main as m  # noqa: E402

app = QApplication([])
m.load_fonts(app)
m.load_style(app)
from ui.messages import AssistantMessage  # noqa: E402

w = AssistantMessage()
w.resize(620, 10)
w.set_text("Voici une **réponse** avec du texte à surligner.\n\n```python\nprint('bonjour')\n```")
w.finish()
w.show()
for _ in range(20):
    QCoreApplication.processEvents()
for tb in w.findChildren(QTextBrowser):
    c = tb.textCursor()
    c.setPosition(0)
    c.setPosition(min(30, len(tb.toPlainText())), QTextCursor.KeepAnchor)
    tb.setTextCursor(c)
    for _ in range(10):
        QCoreApplication.processEvents()
w.grab().save(str(OUT / "shot_sel.png"))
