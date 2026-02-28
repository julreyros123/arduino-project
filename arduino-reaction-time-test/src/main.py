import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

# Allow running with `python src/main.py` while keeping package-style imports.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ui.main_window import MainWindow


def _load_stylesheet(app):
    style_path = Path(__file__).resolve().parent / "ui" / "styles.css"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))


def main():
    app = QApplication(sys.argv)
    _load_stylesheet(app)

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
