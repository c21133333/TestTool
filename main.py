import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent
    src_path = root / "src"
    sys.path.insert(0, str(src_path))


def main() -> int:
    _ensure_src_on_path()
    from requesttool.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "assets" / "lightning.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    style = [
        "QMainWindow { background-color: #f3f4f6; }",
        "QWidget { background-color: #f3f4f6; color: #111827; }",
        "QLabel { color: #111827; }",
        "QSplitter::handle { background-color: #e5e7eb; }",
        "QGroupBox { background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 6px; margin-top: 10px; }",
        "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #374151; font-weight: 600; }",
        "QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QTableWidget, QListWidget { background-color: #ffffff; color: #111827; border: 1px solid #d1d5db; border-radius: 4px; padding: 6px; }",
        "QLineEdit { min-height: 28px; font-size: 10pt; }",
        "QTextEdit, QPlainTextEdit { font-family: Consolas, \"Courier New\", monospace; background-color: #ffffff; color: #111827; }",
        "QLineEdit::placeholder, QTextEdit::placeholder, QPlainTextEdit::placeholder { color: #9ca3af; }",
        "QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover { background-color: #ffffff; }",
        "QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #93c5fd; background-color: #ffffff; }",
        "QHeaderView::section { background-color: #f3f4f6; color: #374151; border: 1px solid #d1d5db; padding: 4px; font-weight: 600; }",
        "QTableView::item { min-height: 26px; padding: 4px; }",
        "QTableView::item:hover { background-color: #f1f5f9; }",
        "QTableWidget::item:selected { background-color: #e0e7ff; }",
        "QLabel#sectionTitle { font-weight: 600; }",
        "QTabWidget::pane { border: 1px solid #d1d5db; border-radius: 4px; }",
        "QTabBar::tab { background-color: #e5e7eb; color: #374151; padding: 6px 12px; border: 1px solid #d1d5db; }",
        "QTabBar::tab:selected { background-color: #ffffff; }",
        "QPushButton { background-color: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; border-radius: 4px; padding: 6px 12px; }",
        "QPushButton:hover { background-color: #1d4ed8; }",
        "QPushButton:pressed { background-color: #1e40af; }",
        "QPushButton:disabled { background-color: #9ca3af; color: #f3f4f6; border: 1px solid #9ca3af; }",
        "QPushButton#secondaryButton { background-color: #16a34a; border: 1px solid #15803d; }",
        "QPushButton#secondaryButton:hover { background-color: #15803d; }",
        "QPushButton#dangerButton { background-color: #dc2626; border: 1px solid #b91c1c; }",
        "QPushButton#dangerButton:hover { background-color: #b91c1c; }",
    ]
    app.setStyleSheet("\n".join(style))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
