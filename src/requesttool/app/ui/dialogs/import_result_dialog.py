from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class ImportResultDialog(QDialog):
    def __init__(self, success_count: int, failures: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入结果")
        self.resize(620, 360)

        summary = QLabel(f"成功: {success_count}  失败: {len(failures)}")
        summary.setStyleSheet("font-weight: 600;")

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["行号", "字段", "原因"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setRowCount(len(failures))
        for row, failure in enumerate(failures):
            self._set_item(row, 0, str(failure.get("row", "")))
            self._set_item(row, 1, str(failure.get("field", "")))
            self._set_item(row, 2, str(failure.get("reason", "")))

        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        close_button.setObjectName("secondaryButton")

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(summary)
        layout.addWidget(self.table, 1)
        layout.addLayout(footer)

    def _set_item(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, column, item)
