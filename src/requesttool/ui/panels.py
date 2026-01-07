import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QHeaderView,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QSplitter,
)


class CaseListPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        group = QGroupBox("\u7528\u4f8b\u5217\u8868")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(10, 12, 10, 10)
        group_layout.setSpacing(6)

        self.list_widget = QListWidget()
        group_layout.addWidget(self.list_widget, 1)

        layout.addWidget(group, 1)

    def add_case(self, name: str) -> None:
        self.list_widget.addItem(name)


class RightPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        request_group = QGroupBox("\u8bf7\u6c42\u914d\u7f6e")
        request_layout = QVBoxLayout(request_group)
        request_layout.setContentsMargins(10, 12, 10, 10)
        request_layout.setSpacing(8)
        self.request_panel = RequestPanel()
        request_layout.addWidget(self.request_panel, 1)

        actions_group = QGroupBox("\u64cd\u4f5c")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(10, 12, 10, 10)
        actions_layout.setSpacing(6)
        self.send_button = QPushButton("\u53d1\u9001\u8bf7\u6c42")
        self.send_button.setObjectName("primaryButton")
        self.run_suite_button = QPushButton("\u6267\u884c\u7528\u4f8b\u96c6")
        self.run_suite_button.setObjectName("secondaryButton")
        self.cancel_button = QPushButton("\u53d6\u6d88\u6267\u884c")
        self.cancel_button.setObjectName("dangerButton")
        self.progress_label = QLabel("\u6279\u91cf\u8fdb\u5ea6: 0/0")
        actions_layout.addWidget(self.send_button)
        actions_layout.addWidget(self.run_suite_button)
        actions_layout.addWidget(self.cancel_button)
        actions_layout.addWidget(self.progress_label)

        response_group = QGroupBox("\u54cd\u5e94\u7ed3\u679c")
        response_layout = QVBoxLayout(response_group)
        response_layout.setContentsMargins(10, 12, 10, 10)
        response_layout.setSpacing(8)
        self.response_panel = ResponsePanel()
        response_layout.addWidget(self.response_panel, 1)

        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)
        top_layout.addWidget(request_group, 3)
        top_layout.addWidget(actions_group, 1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top_container)
        splitter.addWidget(response_group)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter, 1)


class RequestPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        container_layout.addLayout(self._init_method_url())
        container_layout.addWidget(self._init_tabs(), 1)

    def _init_method_url(self) -> QHBoxLayout:
        method_label = QLabel("HTTP Method")
        self.method_combo = QComboBox()
        self.method_combo.addItems(["GET", "POST", "PUT", "DELETE"])

        url_label = QLabel("URL")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://api.example.com/resource")
        self.url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(method_label)
        row.addWidget(self.method_combo, 1)
        row.addWidget(url_label)
        row.addWidget(self.url_input, 3)
        return row

    def _init_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._init_headers(), "Headers")
        tabs.addTab(self._init_body(), "Body")
        return tabs

    def _init_headers(self) -> QWidget:
        headers_label = QLabel("Headers")
        headers_label.setObjectName("sectionTitle")
        add_button = QPushButton("\u65b0\u589e")
        add_button.setObjectName("secondaryButton")
        remove_button = QPushButton("\u5220\u9664")
        remove_button.setObjectName("dangerButton")
        add_button.clicked.connect(self._add_header_row)
        remove_button.clicked.connect(self._remove_header_row)
        self.headers_table = QTableWidget(3, 2)
        self.headers_table.setHorizontalHeaderLabels(["Key", "Value"])
        header = self.headers_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.headers_table.verticalHeader().setVisible(False)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        header_row = QHBoxLayout()
        header_row.addWidget(headers_label)
        header_row.addStretch(1)
        header_row.addWidget(add_button)
        header_row.addWidget(remove_button)
        layout.addLayout(header_row)
        layout.addWidget(self.headers_table)
        return panel

    def _init_body(self) -> QWidget:
        body_label = QLabel("Body (JSON)")
        body_label.setObjectName("sectionTitle")
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("{\n  \"key\": \"value\"\n}")
        self.body_edit.setFont(QFont("Consolas"))

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(body_label)
        layout.addWidget(self.body_edit, 1)
        return panel

    def get_headers(self) -> dict:
        headers: dict[str, str] = {}
        for row in range(self.headers_table.rowCount()):
            key_item = self.headers_table.item(row, 0)
            value_item = self.headers_table.item(row, 1)
            key = key_item.text().strip() if key_item else ""
            value = value_item.text() if value_item else ""
            if key:
                headers[key] = value
        return headers

    def _add_header_row(self) -> None:
        row = self.headers_table.rowCount()
        self.headers_table.insertRow(row)

    def _remove_header_row(self) -> None:
        selected = self.headers_table.selectionModel().selectedRows()
        if selected:
            for index in sorted(selected, key=lambda idx: idx.row(), reverse=True):
                self.headers_table.removeRow(index.row())
        else:
            row = self.headers_table.rowCount()
            if row > 0:
                self.headers_table.removeRow(row - 1)
        if self.headers_table.rowCount() == 0:
            self.headers_table.insertRow(0)

    def get_body(self) -> dict | str:
        text = self.body_edit.toPlainText()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def get_request_data(self) -> dict:
        return {
            "method": self.method_combo.currentText(),
            "url": self.url_input.text().strip(),
            "headers": self.get_headers(),
            "body": self.get_body(),
        }

    def set_request_data(self, data: dict) -> None:
        method = data.get("method")
        if isinstance(method, str) and method in {"GET", "POST", "PUT", "DELETE"}:
            self.method_combo.setCurrentText(method)

        url = data.get("url")
        self.url_input.setText(url if isinstance(url, str) else "")

        self.headers_table.setRowCount(3)
        self.headers_table.clearContents()
        headers = data.get("headers")
        if isinstance(headers, dict):
            row = 0
            for key, value in headers.items():
                if row >= self.headers_table.rowCount():
                    self.headers_table.insertRow(row)
                self.headers_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.headers_table.setItem(row, 1, QTableWidgetItem(str(value)))
                row += 1

        body = data.get("body")
        if isinstance(body, (dict, list)):
            self.body_edit.setPlainText(json.dumps(body, indent=2, ensure_ascii=False))
        elif body is None:
            self.body_edit.clear()
        else:
            self.body_edit.setPlainText(str(body))

    def format_json(self) -> None:
        text = self.body_edit.toPlainText().strip()
        if not text:
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "JSON \u683c\u5f0f\u9519\u8bef", str(exc))
            return
        self.body_edit.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))


class ResponsePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        summary_group = QGroupBox("\u54cd\u5e94\u6982\u8981")
        summary_layout = QHBoxLayout(summary_group)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(10)
        self.status_value = QLabel("-")
        self.elapsed_value = QLabel("-")
        self.error_label = QLabel("\u9519\u8bef\u4fe1\u606f")
        self.error_value = QLabel("-")
        summary_layout.addWidget(QLabel("\u72b6\u6001\u7801"))
        summary_layout.addWidget(self.status_value)
        summary_layout.addSpacing(16)
        summary_layout.addWidget(QLabel("\u8017\u65f6(ms)"))
        summary_layout.addWidget(self.elapsed_value)
        summary_layout.addSpacing(16)
        summary_layout.addWidget(self.error_label)
        summary_layout.addWidget(self.error_value)
        summary_layout.addStretch(1)

        self.headers_group = QGroupBox("Response Headers")
        self.headers_group.setCheckable(True)
        self.headers_group.setChecked(False)
        self.headers_view = QTextEdit()
        self.headers_view.setReadOnly(True)
        self.headers_view.setPlaceholderText("\u54cd\u5e94\u5934")
        headers_layout = QVBoxLayout(self.headers_group)
        headers_layout.setContentsMargins(10, 10, 10, 10)
        headers_layout.addWidget(self.headers_view)

        self.error_group = QGroupBox("\u9519\u8bef")
        self.error_group.setVisible(False)
        self.error_title = QLabel("\u8bf7\u6c42\u5931\u8d25")
        self.error_title.setStyleSheet("color: #f87171;")
        self.error_view = QTextEdit()
        self.error_view.setReadOnly(True)
        self.error_view.setPlaceholderText("\u9519\u8bef\u4fe1\u606f")
        self.error_view.setFont(QFont("Consolas"))
        error_layout = QVBoxLayout(self.error_group)
        error_layout.setContentsMargins(10, 10, 10, 10)
        error_layout.setSpacing(6)
        error_layout.addWidget(self.error_title)
        error_layout.addWidget(self.error_view, 1)

        body_group = QGroupBox("\u54cd\u5e94\u5185\u5bb9")
        body_layout = QVBoxLayout(body_group)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(6)
        self.body_view = QTextEdit()
        self.body_view.setReadOnly(True)
        self.body_view.setPlaceholderText("\u54cd\u5e94\u5185\u5bb9")
        self.body_view.setFont(QFont("Consolas"))
        body_layout.addWidget(self.body_view, 1)

        headers_body_splitter = QSplitter(Qt.Orientation.Vertical)
        headers_body_splitter.addWidget(self.headers_group)
        headers_body_splitter.addWidget(body_group)
        headers_body_splitter.setStretchFactor(0, 1)
        headers_body_splitter.setStretchFactor(1, 2)

        container_layout.addWidget(summary_group)
        container_layout.addWidget(self.error_group)
        container_layout.addWidget(headers_body_splitter, 1)

    def update_summary(self, status_code: int | None, elapsed_ms: int | None) -> None:
        self.status_value.setText("-" if status_code is None else str(status_code))
        self.elapsed_value.setText("-" if elapsed_ms is None else str(elapsed_ms))
        self.error_value.setText("-")
        self.error_label.setVisible(False)
        self.error_value.setVisible(False)
        self._apply_status_style(None)

    def update_status(self, success: bool, error_message: str | None = None) -> None:
        if success:
            self.error_value.setText("-")
            self.error_label.setVisible(False)
            self.error_value.setVisible(False)
            self._apply_status_style(True)
            return
        self.error_value.setText(error_message or "-")
        self.error_label.setVisible(True)
        self.error_value.setVisible(True)
        self._apply_status_style(False)

    def _apply_status_style(self, success: bool | None) -> None:
        if success is True:
            self.status_value.setStyleSheet("color: #34d399;")
            self.error_value.setStyleSheet("")
        elif success is False:
            self.status_value.setStyleSheet("color: #f87171;")
            self.error_value.setStyleSheet("color: #f87171;")
        else:
            self.status_value.setStyleSheet("")
            self.error_value.setStyleSheet("")

    def update_body(self, response_text: str, response_json: dict | None) -> None:
        if response_json is not None:
            pretty = json.dumps(response_json, indent=2, ensure_ascii=False)
            self.body_view.setPlainText(pretty)
            return
        text = response_text or ""
        if not text.strip():
            self.body_view.clear()
            return
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            self.body_view.setPlainText(text)
            return
        self.body_view.setPlainText(json.dumps(parsed, indent=2, ensure_ascii=False))

    def update_headers(self, headers: dict) -> None:
        if not headers:
            self.headers_view.clear()
            return
        lines = [f"{key}: {value}" for key, value in headers.items()]
        self.headers_view.setPlainText("\n".join(lines))

    def update_response(self, result: dict) -> None:
        try:
            success = result.get("success")
            status_code = result.get("status_code")
            elapsed_ms = result.get("elapsed_ms")
            error_type = result.get("error_type")
            error_message = result.get("error_message")

            if success is False:
                self.update_summary(None, None)
                self.update_status(False, f"{error_type}: {error_message}".strip())
                self.headers_view.clear()
                self.body_view.clear()
                self.body_view.setVisible(False)
                self.error_title.setText("\u8bf7\u6c42\u5931\u8d25")
                self.error_view.setPlainText(f"{error_type}\n{error_message}".strip())
                self.error_group.setVisible(True)
                return

            self.update_summary(status_code, elapsed_ms)
            self.update_status(True)
            self.error_group.setVisible(False)
            self.body_view.setVisible(True)
            self.update_headers(result.get("headers") or {})
            self.update_body(result.get("response_text", ""), result.get("response_json"))
        except Exception:
            self.update_summary(None, None)
            self.update_status(False, "unexpected error")
            self.headers_view.clear()
            self.body_view.clear()
            self.body_view.setVisible(False)
            self.error_title.setText("\u8bf7\u6c42\u5931\u8d25")
            self.error_view.setPlainText("unexpected error")
            self.error_group.setVisible(True)

    def clear(self) -> None:
        self.update_summary(None, None)
        self.update_status(True)
        self.headers_view.clear()
        self.body_view.clear()
        self.body_view.setVisible(True)
        self.error_view.clear()
        self.error_group.setVisible(False)


class AssertionPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        title = QLabel("\u65ad\u8a00\u914d\u7f6e")
        title.setObjectName("sectionTitle")
        self.table = QTableWidget(3, 4)
        self.table.setHorizontalHeaderLabels(["Type", "JSONPath", "Operator", "Expected"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        result_label = QLabel("\u65ad\u8a00\u7ed3\u679c")
        result_label.setObjectName("sectionTitle")
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(["Type", "Result", "Message"])
        result_header = self.result_table.horizontalHeader()
        result_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.verticalHeader().setVisible(False)

        layout.addWidget(title)
        layout.addWidget(self.table, 1)
        layout.addWidget(result_label)
        layout.addWidget(self.result_table, 1)

    def get_assertions(self) -> list[dict]:
        assertions: list[dict] = []
        for row in range(self.table.rowCount()):
            type_item = self.table.item(row, 0)
            path_item = self.table.item(row, 1)
            op_item = self.table.item(row, 2)
            expected_item = self.table.item(row, 3)

            type_value = type_item.text().strip() if type_item else ""
            path_value = path_item.text().strip() if path_item else ""
            op_value = op_item.text().strip() if op_item else ""
            expected_value = expected_item.text().strip() if expected_item else ""

            if not any([type_value, path_value, op_value, expected_value]):
                continue

            assertion = {"type": type_value}
            if path_value:
                assertion["path"] = path_value
            if op_value:
                assertion["operator"] = op_value
            if expected_value:
                assertion["expected"] = expected_value
            assertions.append(assertion)

        return assertions

    def update_results(self, results: list[dict]) -> None:
        self.result_table.setRowCount(0)
        for item in results:
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            type_value = str(item.get("type", ""))
            result_value = str(item.get("result", ""))
            message_value = str(item.get("message", ""))
            self.result_table.setItem(row, 0, QTableWidgetItem(type_value))
            self.result_table.setItem(row, 1, QTableWidgetItem(result_value))
            self.result_table.setItem(row, 2, QTableWidgetItem(message_value))
