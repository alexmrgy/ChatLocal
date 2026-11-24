"""Point d'entrée : python main.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from database.db import Database  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def load_style(app: QApplication) -> None:
    pal = app.palette()
    pal.setColor(QPalette.Highlight, QColor(86, 140, 255, 105))  # sélection : bleu translucide
    pal.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    app.setPalette(pal)
    app.setStyleSheet((ROOT / "styles" / "dark.qss").read_text(encoding="utf-8"))


def load_fonts(app: QApplication) -> None:
    """Polices fournies avec l'app (assets/fonts/*.ttf|otf), prioritaires sur les polices système."""
    for f in (ROOT / "assets" / "fonts").glob("*"):
        if f.suffix.lower() in (".ttf", ".otf"):
            QFontDatabase.addApplicationFont(str(f))
    families = set(QFontDatabase.families())
    first = next((f for f in ("Nunito", "OpenAI Sans", "Söhne", "Inter", "Segoe UI Variable Text", "Segoe UI")
                  if f in families), "Segoe UI")
    font = QFont(first, 10)
    font.setHintingPreference(QFont.PreferNoHinting)   # pas de hinting : texte lisse, sans effet pixelisé
    font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
    app.setFont(font)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ChatLocal")
    app.setWindowIcon(QIcon(str(ROOT / "assets" / "logo.png")))
    load_fonts(app)
    load_style(app)
    win = MainWindow(Database())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


