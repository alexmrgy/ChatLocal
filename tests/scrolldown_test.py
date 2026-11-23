"""Test : bouton « descendre en bas » de la discussion."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())

from PySide6.QtCore import QCoreApplication, QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as m  # noqa: E402

app = QApplication([])
m.load_fonts(app)
m.load_style(app)
from ui.messages import ChatView  # noqa: E402

fails = 0


def pump(ms):
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def check(name, ok):
    global fails
    print(("OK   " if ok else "FAIL ") + name)
    fails += not ok


v = ChatView()
v.setStyleSheet("")
v.resize(900, 520)
v.show()
pump(100)
check("court : bouton absent", not v.down_btn.isVisible())

long = "\n\n".join(f"Paragraphe {i} : " + "texte " * 40 for i in range(14))
for i in range(3):
    v.add_user(f"question {i}", i * 2, fade=False)
    v.add_assistant(long, i * 2 + 1, fade=False)
pump(600)
sb = v.verticalScrollBar()
check("long : défilement possible", sb.maximum() > 500)
check("en bas : bouton masqué", sb.value() == sb.maximum() and not v.down_btn.isVisible())

sb.setValue(0)
pump(400)
check("remonté : bouton visible", v.down_btn.isVisible() and v._down_fx.opacity() > 0.9)
pos = v.down_btn.pos()
check("bouton centré en bas de la vue", abs(pos.x() + 19 - v.width() // 2) <= 2 and pos.y() > v.height() - 80)
v.grab().save(str(OUT / "shot_scrolldown.png"))

v.down_btn.click()
pump(700)
check("clic : redescend tout en bas", sb.value() == sb.maximum())
check("bouton masqué après la descente", not v.down_btn.isVisible())
check("suivi du texte réactivé", v._stick)

# petite remontée (sous le seuil) : pas de bouton
sb.setValue(sb.maximum() - 60)
pump(300)
check("quasi en bas : bouton masqué", not v.down_btn.isVisible())

# nouveau message pendant qu'on est remonté : le bouton reste, la vue ne saute pas
sb.setValue(0)
pump(300)
before = sb.value()
v.add_assistant("nouveau", 99, fade=False)
v._stick = False
pump(300)
check("remonté + nouveau contenu : la vue ne saute pas, bouton visible", sb.value() == before and v.down_btn.isVisible())
print("RÉSULTAT :", "ÉCHEC" if fails else "SUCCÈS")
sys.exit(1 if fails else 0)
