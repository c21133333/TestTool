from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSplitter, QWidget

from requesttool.controller import ApiTestController
from requesttool.ui.panels import CaseListPanel, RightPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("API \u63a5\u53e3\u6d4b\u8bd5\u5de5\u5177")
        self.resize(1200, 800)
        self.setFont(QFont("Segoe UI", 10))
        self._setup_ui()

    def _setup_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = CaseListPanel()
        self.right_panel = RightPanel()

        splitter.addWidget(left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self.setCentralWidget(splitter)

        self.controller = ApiTestController(
            self.right_panel.request_panel,
            self.right_panel.response_panel,
        )
        self.right_panel.send_button.clicked.connect(self._on_send_request)
        self.right_panel.run_suite_button.clicked.connect(self._on_run_suite)
        self.right_panel.cancel_button.clicked.connect(self._on_cancel_suite)
        self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)

    def _set_busy(self, busy: bool, message: str, allow_cancel: bool) -> None:
        self.right_panel.send_button.setEnabled(not busy)
        self.right_panel.run_suite_button.setEnabled(not busy)
        self.right_panel.cancel_button.setEnabled(busy and allow_cancel)
        self.right_panel.progress_label.setText(message)

    def _on_send_request(self) -> None:
        request_data = self.right_panel.request_panel.get_request_data()
        if not request_data.get("method") or not request_data.get("url"):
            return
        self._set_busy(True, "\u6267\u884c\u4e2d...", allow_cancel=False)

        def on_finished(_result: dict) -> None:
            self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)

        def on_error(_error: dict) -> None:
            self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)

        self.controller.send_request_async(on_finished, on_error)

    def _on_run_suite(self) -> None:
        self._set_busy(True, "\u6267\u884c\u4e2d...", allow_cancel=True)

        def on_progress(done: int, total: int) -> None:
            self.right_panel.progress_label.setText(f"\u6279\u91cf\u8fdb\u5ea6: {done}/{total}")

        def on_finished(result: dict, path: str) -> None:
            self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)
            summary = result.get("summary", {})
            total = summary.get("total", 0) or 0
            passed = summary.get("pass", 0) or 0
            rate = (passed / total * 100) if total else 0.0
            canceled = result.get("canceled")
            title = "\u6267\u884c\u5b8c\u6210" if not canceled else "\u5df2\u53d6\u6d88"
            message = f"\u901a\u8fc7\u7387: {rate:.1f}%" + f"\n\u7ed3\u679c\u6587\u4ef6: {path}"
            QMessageBox.information(
                self,
                title,
                message,
            )

        self.controller.run_suite_async(on_progress, on_finished)

    def _on_cancel_suite(self) -> None:
        self.right_panel.progress_label.setText("\u53d6\u6d88\u4e2d...")
        self.controller.cancel_suite()
