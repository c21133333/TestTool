import json
import logging
import shutil
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtCore import QObject, QEvent, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QTreeWidgetItem,
)


class _DialogWatcher(QObject):
    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._last_user_action = time.monotonic()
        self._allow_window_seconds = 0.6

    def eventFilter(self, obj, event) -> bool:
        if event.type() in {QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress}:
            self._last_user_action = time.monotonic()
        if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) and obj.isWindow():
            if obj is self._main_window:
                return False
            if isinstance(obj, QLabel) and obj.parent() is None:
                obj.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                obj.hide()
                obj.deleteLater()
                return True
        return False


class DebugConsole(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Debug Console")
        self.resize(700, 360)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText("Debug log output...")
        clear_button = QPushButton("\u6e05\u7a7a")
        clear_button.clicked.connect(self._log_view.clear)
        close_button = QPushButton("\u5173\u95ed")
        close_button.clicked.connect(self.close)

        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(clear_button)
        controls.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self._log_view, 1)
        layout.addLayout(controls)

    def append_line(self, message: str) -> None:
        current = self._log_view.toPlainText()
        if current:
            self._log_view.setPlainText(f"{current}\n{message}")
        else:
            self._log_view.setPlainText(message)
        self._log_view.verticalScrollBar().setValue(self._log_view.verticalScrollBar().maximum())


class _QtLogHandler(logging.Handler):
    def __init__(self, console: DebugConsole) -> None:
        super().__init__()
        self._console = console

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        QTimer.singleShot(0, lambda: self._console.append_line(message))

from requesttool.controller import ApiTestController
from requesttool.app.core.case_schema import CaseSchema
from requesttool.app.core.excel_importer import ExcelImporter
from requesttool.app.core.executor_worker import RunResult, SuiteExecutorWorker
from requesttool.app.core.project_store import ProjectStore
from requesttool.app.core.report_generator import ReportGenerator
from requesttool.app.ui.dialogs.import_result_dialog import ImportResultDialog
from requesttool.ui.panels import CaseListPanel, RightPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._set_window_icon()
        self.setWindowTitle("API \u63a5\u53e3\u6d4b\u8bd5\u5de5\u5177")
        self.resize(1200, 800)
        self.setFont(QFont("Segoe UI", 10))
        self._has_request_selection = False
        self._project_store = ProjectStore()
        self._project_path = self._resolve_data_path()
        self._project_state: dict | None = None
        self._envs: list[dict] = []
        self._runs_index: list[dict] = []
        self._last_report_paths: dict[str, str] = {}
        self._suite_thread: QThread | None = None
        self._suite_worker: SuiteExecutorWorker | None = None
        self._request_state = RequestRunState.IDLE
        self._suite_case_map: dict[str, object] = {}
        self._global_history: list[dict] = []
        self._current_case: dict | None = None
        self._current_case_item = None
        self._current_collection_item: QTreeWidgetItem | None = None
        self._ai_suite_context: dict | None = None
        self._ai_env_context: dict | None = None
        self._apply_scrollbar_style()
        self._setup_ui()

    def _set_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parents[3] / "assets" / "lightning.ico"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)
            QApplication.instance().setWindowIcon(icon)

    def _setup_ui(self) -> None:
        self._debug_console = DebugConsole(self)
        self._dialog_watcher = _DialogWatcher(self)
        QApplication.instance().installEventFilter(self._dialog_watcher)
        logger = logging.getLogger("requesttool")
        if not any(isinstance(h, _QtLogHandler) for h in logger.handlers):
            logger.setLevel(logging.INFO)
            handler = _QtLogHandler(self._debug_console)
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
            logger.addHandler(handler)
        open_console = QShortcut(QKeySequence("F12"), self)
        open_console.activated.connect(self._debug_console.show)
        open_console.activated.connect(self._debug_console.raise_)
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._on_save_request)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.left_panel = CaseListPanel()
        self.right_panel = RightPanel()

        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        self.setCentralWidget(splitter)

        self.controller = ApiTestController(
            self.right_panel.request_panel,
            self.right_panel.response_panel,
            self.right_panel.assertion_panel,
        )
        self.right_panel.send_button.clicked.connect(self._on_send_request)
        self.right_panel.save_button.clicked.connect(self._on_save_request)
        self.right_panel.request_panel.data_changed.connect(self._on_request_data_changed)
        self.right_panel.assertion_panel.data_changed.connect(self._on_request_data_changed)
        self.right_panel.request_panel.name_input.textEdited.connect(self._on_request_name_changed)
        self.right_panel.welcome_new_request_button.clicked.connect(self.left_panel._on_add_request_clicked)
        self.right_panel.welcome_new_folder_button.clicked.connect(self.left_panel._on_add_folder_clicked)
        self.left_panel.request_selected.connect(self._on_request_selected)
        self.left_panel.selection_changed.connect(self._on_tree_selection_changed)
        self.left_panel.request_edited.connect(self._on_request_edited)
        self.left_panel.import_request_clicked.connect(self._on_import_request)
        self.left_panel.import_folder_clicked.connect(self._on_import_folder)
        self.left_panel.import_excel_clicked.connect(self._on_import_excel)
        self.left_panel.export_clicked.connect(self._on_export_cases)
        self.left_panel.run_suite_clicked.connect(self._on_run_suite)
        self.right_panel.export_report_button.clicked.connect(self._on_export_report)
        self.right_panel.collection_panel.data_changed.connect(self._on_collection_data_changed)
        self.left_panel.tree_changed.connect(self._persist_cases)
        self.left_panel.history_selected.connect(self._on_history_selected)
        self._load_saved_cases()
        self._update_request_controls()
        self._apply_request_state(RequestRunState.IDLE)
        self.right_panel.show_welcome()
        self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)

    def _apply_scrollbar_style(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        style = app.styleSheet() or ""
        if "QScrollBar:vertical" in style:
            return
        scrollbar_style = (
            "QScrollBar:vertical { background: #f1f5f9; width: 8px; margin: 2px; border-radius: 4px; }"
            "QScrollBar::handle:vertical { background: #cbd5f5; min-height: 24px; border-radius: 4px; }"
            "QScrollBar::handle:vertical:hover { background: #94a3b8; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
            "QScrollBar:horizontal { background: #f1f5f9; height: 8px; margin: 2px; border-radius: 4px; }"
            "QScrollBar::handle:horizontal { background: #cbd5f5; min-width: 24px; border-radius: 4px; }"
            "QScrollBar::handle:horizontal:hover { background: #94a3b8; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }"
            "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }"
            "QScrollBar::corner { background: transparent; }"
        )
        app.setStyleSheet(style + scrollbar_style)

    def _set_busy(self, busy: bool, message: str, allow_cancel: bool) -> None:
        self.right_panel.send_button.setEnabled(not busy and self._has_request_selection)
        self.right_panel.save_button.setEnabled(not busy and self._has_request_selection)
        if busy:
            self.right_panel.send_button.setToolTip("\u8bf7\u6c42\u6267\u884c\u4e2d...")
        else:
            self.right_panel.send_button.setToolTip("\u53d1\u9001\u8bf7\u6c42\uff08Ctrl + Enter\uff09")
        self.right_panel.progress_label.setText(message)

    def _update_request_controls(self) -> None:
        self.right_panel.save_button.setEnabled(self._has_request_selection)
        self.right_panel.send_button.setEnabled(self._has_request_selection)

    def _on_request_selected(self, item) -> None:
        if item is None:
            folder_item = self.left_panel.get_selected_folder_item()
            if folder_item is not None:
                self._has_request_selection = False
                self._current_case = None
                self._current_case_item = None
                self._current_collection_item = folder_item
                self._update_request_controls()
                return
            self._has_request_selection = False
            self._current_case = None
            self._current_case_item = None
            self.right_panel.request_panel.clear_request()
            self.right_panel.assertion_panel.clear_assertions()
            self.right_panel.response_panel.clear()
            self.right_panel.save_status_label.setText("\u672a\u4fdd\u5b58")
            if not self.left_panel.has_requests():
                self.right_panel.show_welcome()
            else:
                self.right_panel.show_welcome()
            self._update_request_controls()
            return

        self._has_request_selection = True
        data = self._load_request_data(item)
        if not isinstance(data, dict):
            data = {}
        item.setData(0, self.left_panel._DATA_ROLE, data)
        self._current_case = data
        self._current_case_item = item
        if not isinstance(data.get("name"), str) or not data.get("name"):
            data["name"] = item.data(0, self.left_panel._NAME_ROLE) or self.left_panel._strip_method_prefix(item.text(0))
        if not isinstance(data.get("method"), str):
            data["method"] = "GET"
        if not isinstance(data.get("url"), str):
            data["url"] = ""
        self.right_panel.request_panel.set_request_data(data)
        self.right_panel.assertion_panel.set_assertions(data.get("assertions") if isinstance(data, dict) else None)
        status = "\u5df2\u4fdd\u5b58" if self.left_panel.is_request_saved(item) else "\u672a\u4fdd\u5b58"
        self.right_panel.save_status_label.setText(status)
        cached_response = self.left_panel.get_request_response(item)
        if cached_response is not None:
            self.right_panel.response_panel.update_response(cached_response)
        else:
            self.right_panel.response_panel.clear()
        self.right_panel.show_content()
        self._update_request_controls()

    def _on_tree_selection_changed(self, item) -> None:
        folder_item = self.left_panel.get_selected_folder_item()
        if item is None or folder_item is None or item is not folder_item:
            self._current_collection_item = None
            return
        self._current_collection_item = folder_item
        self._has_request_selection = False
        folder_data = self.left_panel.get_folder_data(folder_item)
        name = folder_data.get("name")
        if not name:
            name = folder_item.text(0)
        description = folder_data.get("description") or ""
        globals_rows = folder_data.get("globals") if isinstance(folder_data.get("globals"), list) else []
        self.right_panel.collection_panel.set_data(name, description, globals_rows)
        self.right_panel.show_collection_panel()
        self.right_panel.save_status_label.setText("\u7528\u4f8b\u96c6")
        self._update_request_controls()

    def _on_collection_data_changed(self) -> None:
        item = self._current_collection_item
        if item is None:
            return
        data = self.right_panel.collection_panel.get_data()
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        globals_rows = data.get("globals") if isinstance(data.get("globals"), list) else []
        existing = self.left_panel.get_folder_data(item)
        suite_type = existing.get("suite_type") if isinstance(existing, dict) else None
        suite_id = existing.get("suite_id") if isinstance(existing, dict) else None
        if name:
            self.left_panel.rename_folder(item, name)
        payload = {"name": name or item.text(0), "description": description, "globals": globals_rows}
        if isinstance(suite_type, str):
            payload["suite_type"] = suite_type
        if isinstance(suite_id, str):
            payload["suite_id"] = suite_id
        self.left_panel.set_folder_data(item, payload)
        self.left_panel.tree_changed.emit()

    def _get_parent_folder_item(self, item) -> QTreeWidgetItem | None:
        current = item.parent() if item is not None else None
        while current is not None:
            if current.data(0, self.left_panel._TYPE_ROLE) == "folder":
                return current
            current = current.parent()
        return None

    def _build_global_vars(self, folder_data: dict | None) -> dict:
        if not isinstance(folder_data, dict):
            return {}
        rows = folder_data.get("globals")
        if not isinstance(rows, list):
            return {}
        variables: dict[str, object] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("enabled", True) is False:
                continue
            key = str(row.get("key") or "").strip()
            if not key:
                continue
            value = row.get("value")
            if value is None:
                value = ""
            variables[key] = value
        return variables
    def _on_save_request(self) -> None:
        item = self.left_panel.get_selected_request_item()
        if item is None:
            if self._save_collection():
                return
            return
        data = self.right_panel.request_panel.get_request_data()
        data["assertions"] = self.right_panel.assertion_panel.get_assertion_rows()
        if self._current_case_item is item and isinstance(self._current_case, dict):
            ai_case = self._current_case.get("ai_case")
            if ai_case is not None:
                data["ai_case"] = ai_case
        name_value = data.get("name")
        raw_name = name_value.strip() if isinstance(name_value, str) else ""
        display_name = self.left_panel._strip_method_prefix(item.text(0))
        method_from_name, custom_name_from_name = self._parse_method_and_name(raw_name)
        custom_candidate = (custom_name_from_name or raw_name).strip()
        final_custom_name = custom_candidate or display_name
        method_value = data.get("method")
        if not isinstance(method_value, str):
            method_value = ""
        method_value = method_value.strip().upper()
        parsed_method = method_from_name or method_value
        method_label = parsed_method or "GET"
        final_custom_name = final_custom_name or method_label
        data["method"] = method_label
        data["name"] = final_custom_name
        save_name = final_custom_name
        saved_path = self._save_request_file(item, data, save_name)
        if saved_path is None:
            QMessageBox.warning(self, "\u4fdd\u5b58\u5931\u8d25", "\u8bf7\u6c42\u4fdd\u5b58\u5931\u8d25")
            return
        final_name = data.get("name")
        if isinstance(final_name, str):
            final_name = final_name.strip()
        if not final_name:
            if saved_path is not None:
                final_name = saved_path.stem
            if not final_name:
                final_name = display_name
            data["name"] = final_name
        name_input = self.right_panel.request_panel.name_input
        if name_input.text().strip() != final_name:
            block = name_input.blockSignals(True)
            name_input.setText(final_name)
            name_input.blockSignals(block)
        self.left_panel.set_request_name(item, final_name)
        self.left_panel.set_request_data(item, data)
        self._current_case = data
        self._current_case_item = item
        self.right_panel.save_status_label.setText("\u5df2\u4fdd\u5b58")
        self._persist_cases()
        path_value = self.left_panel.get_item_path(item)
        if path_value:
            QMessageBox.information(self, "\u4fdd\u5b58\u6210\u529f", f"\u6587\u4ef6\u5df2\u4fdd\u5b58\u5230:\n{path_value}")

    def _save_collection(self) -> bool:
        folder_item = self.left_panel.get_selected_folder_item()
        if folder_item is None:
            return False
        data = self.right_panel.collection_panel.get_data()
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()
        globals_rows = data.get("globals") if isinstance(data.get("globals"), list) else []
        existing = self.left_panel.get_folder_data(folder_item)
        suite_type = existing.get("suite_type") if isinstance(existing, dict) else None
        suite_id = existing.get("suite_id") if isinstance(existing, dict) else None
        if name:
            self.left_panel.rename_folder(folder_item, name)
        payload = {"name": name or folder_item.text(0), "description": description, "globals": globals_rows}
        if isinstance(suite_type, str):
            payload["suite_type"] = suite_type
        if isinstance(suite_id, str):
            payload["suite_id"] = suite_id
        self.left_panel.set_folder_data(folder_item, payload)
        folder_path = self._ensure_folder_path(folder_item, name or folder_item.text(0))
        if folder_path is None:
            return False
        self._write_suite_meta(folder_path, payload)
        self._save_folder_requests(folder_item, folder_path)
        self._persist_cases()
        QMessageBox.information(self, "\u4fdd\u5b58\u6210\u529f", "\u7528\u4f8b\u96c6\u5df2\u4fdd\u5b58")
        return True

    def _ensure_folder_path(self, folder_item, name: str) -> Path | None:
        existing = self.left_panel.get_item_path(folder_item)
        if existing:
            path = Path(existing)
            if path.exists():
                return path
        base_dir = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u4fdd\u5b58\u4f4d\u7f6e")
        if not base_dir:
            return None
        folder_path = Path(base_dir) / name
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        self.left_panel.set_item_path(folder_item, str(folder_path))
        return folder_path

    def _save_folder_requests(self, folder_item, folder_path: Path) -> None:
        for idx in range(folder_item.childCount()):
            child = folder_item.child(idx)
            item_type = child.data(0, self.left_panel._TYPE_ROLE)
            if item_type == "folder":
                child_name = child.data(0, self.left_panel._NAME_ROLE) or child.text(0)
                child_path = folder_path / str(child_name)
                try:
                    child_path.mkdir(parents=True, exist_ok=True)
                except Exception:
                    continue
                self.left_panel.set_item_path(child, str(child_path))
                child_data = self.left_panel.get_folder_data(child)
                if isinstance(child_data, dict):
                    self._write_suite_meta(child_path, child_data)
                self._save_folder_requests(child, child_path)
                continue
            if item_type != "request":
                continue
            data = self._load_request_data(child) or {}
            case_name = data.get("name") if isinstance(data.get("name"), str) else child.text(0)
            self._save_request_file(child, data, case_name or "request")

    def _write_suite_meta(self, folder_path: Path, payload: dict) -> None:
        meta_path = folder_path / "_suite.json"
        data = {}
        if isinstance(payload, dict):
            for key in ("name", "description", "suite_type", "suite_id"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    data[key] = value
            globals_rows = payload.get("globals")
            if isinstance(globals_rows, list):
                data["globals"] = globals_rows
        if not data:
            return
        try:
            meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return

    def _safe_case_filename(self, name: str) -> str:
        text = str(name or "").strip()
        if not text:
            return "request"
        invalid = '<>:"/\\|?*'
        cleaned = []
        for ch in text:
            if ch in invalid or ord(ch) < 32:
                cleaned.append("_")
            else:
                cleaned.append(ch)
        safe = "".join(cleaned).strip().strip(".")
        return safe or "request"

    def _parse_method_and_name(self, raw_name: str) -> tuple[str, str]:
        trimmed = raw_name.strip()
        if not trimmed.startswith("[") or "]" not in trimmed:
            return "", ""
        end = trimmed.find("]")
        method_part = trimmed[1:end].strip().upper()
        custom_part = trimmed[end + 1 :].strip()
        return method_part, custom_part

    def _on_request_edited(self, item) -> None:
        if item == self.left_panel.get_selected_request_item():
            if self.right_panel.request_panel.name_input.text().strip() != item.text(0):
                self.right_panel.request_panel.name_input.setText(item.text(0))
            self.right_panel.save_status_label.setText("\u672a\u4fdd\u5b58")

    def _on_request_data_changed(self) -> None:
        item = self.left_panel.get_selected_request_item()
        if item is None:
            return
        case_data = self._current_case if self._current_case_item is item else None
        if case_data is None:
            case_data = self.left_panel.get_request_data(item)
            if case_data is None:
                case_data = {}
                item.setData(0, self.left_panel._DATA_ROLE, case_data)
            self._current_case = case_data
            self._current_case_item = item
        preserved_ai_case = case_data.get("ai_case") if isinstance(case_data, dict) else None
        payload = self.right_panel.request_panel.get_request_data()
        payload["assertions"] = self.right_panel.assertion_panel.get_assertion_rows()
        if not payload.get("name") and case_data.get("name"):
            payload["name"] = case_data.get("name")
        case_data.clear()
        case_data.update(payload)
        if isinstance(preserved_ai_case, dict):
            request_json = preserved_ai_case.get("request_json")
            if not isinstance(request_json, dict):
                request_json = {}
            request_json.update(
                {
                    "method": payload.get("method"),
                    "headers": payload.get("headers") or {},
                    "params": payload.get("params") or {},
                    "body": payload.get("body"),
                }
            )
            preserved_ai_case["request_json"] = request_json
            if isinstance(payload.get("url"), str) and payload.get("url"):
                preserved_ai_case["endpoint"] = payload.get("url")
            case_data["ai_case"] = preserved_ai_case
        item.setData(0, self.left_panel._DATA_ROLE, case_data)
        self.left_panel.set_request_name(
            item,
            case_data.get("name") or self.left_panel._strip_method_prefix(item.text(0)),
        )
        if self.left_panel.is_request_saved(item):
            self.left_panel.set_request_saved(item, False)
        self.right_panel.save_status_label.setText("\u672a\u4fdd\u5b58")

    def _on_request_name_changed(self, text: str) -> None:
        item = self.left_panel.get_selected_request_item()
        if item is None:
            return
        case_data = self._current_case if self._current_case_item is item else None
        if case_data is None:
            case_data = self.left_panel.get_request_data(item)
            if case_data is None:
                case_data = {}
                item.setData(0, self.left_panel._DATA_ROLE, case_data)
            self._current_case = case_data
            self._current_case_item = item
        case_data["name"] = text.strip()
        if isinstance(case_data.get("ai_case"), dict):
            case_data["ai_case"]["name"] = text.strip()
        self.left_panel.set_request_name(
            item,
            case_data.get("name") or self.left_panel._strip_method_prefix(item.text(0)),
        )

    def _on_import_request(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "\u5bfc\u5165\u8bf7\u6c42",
            "",
            "Request (*.json);;All Files (*)",
        )
        if not file_path:
            return
        path = Path(file_path)
        data = self._read_request_file(path)
        if data is None:
            QMessageBox.warning(self, "\u5bfc\u5165\u5931\u8d25", "\u8bf7\u6c42\u6587\u4ef6\u65e0\u6548")
            return
        name = data.get("name") if isinstance(data.get("name"), str) else path.stem
        data["name"] = name
        parent_item = self.left_panel.get_selected_folder_item()
        item = self.left_panel.add_request_from_data(name, data, str(path), parent_item)
        self.left_panel.tree_widget.setCurrentItem(item)
        self._persist_cases()
        QMessageBox.information(self, "\u5bfc\u5165\u6210\u529f", f"\u5df2\u5bfc\u5165:\n{file_path}")

    def _on_import_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, "\u5bfc\u5165\u6587\u4ef6\u5939")
        if not folder_path:
            return
        path = Path(folder_path)
        root_item = self.left_panel.add_folder_from_path(path.name, str(path))
        self._import_folder_contents(path, root_item)
        self.left_panel.tree_widget.setCurrentItem(root_item)
        self._persist_cases()
        QMessageBox.information(self, "\u5bfc\u5165\u6210\u529f", f"\u5df2\u5bfc\u5165:\n{folder_path}")

    def _on_import_excel(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "\u5bfc\u5165 AI \u7528\u4f8b",
            "",
            "Excel (*.xlsx);;All Files (*)",
        )
        if not file_path:
            return
        importer = ExcelImporter()
        try:
            result = importer.import_file(file_path, self._collect_case_ids())
        except Exception as exc:
            QMessageBox.warning(self, "\u5bfc\u5165\u5931\u8d25", str(exc))
            return
        cases: list[CaseSchema] = result.get("cases") or []
        failures: list[dict] = result.get("failures") or []
        if not cases and failures:
            dialog = ImportResultDialog(0, failures, self)
            dialog.exec()
            return
        suite_name = result.get("suite_name") or Path(file_path).stem
        suite_name = self.left_panel._next_name(None, suite_name)
        suite_item = self.left_panel._add_folder_item(None, suite_name, edit=False)
        suite_data = {
            "name": suite_name,
            "description": "",
            "suite_type": "ai_excel",
            "suite_id": uuid.uuid4().hex,
        }
        self.left_panel.set_folder_data(suite_item, suite_data)
        for case in cases:
            case_data = self._build_request_data_from_ai_case(case)
            self.left_panel.add_request_from_data(case.name, case_data, None, suite_item)
        self.left_panel.tree_widget.setCurrentItem(suite_item)
        self._persist_cases()
        dialog = ImportResultDialog(len(cases), failures, self)
        dialog.exec()

    def _import_folder_contents(self, path: Path, parent_item) -> None:
        try:
            entries = sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        except Exception:
            return
        for entry in entries:
            if entry.is_dir():
                folder_item = self.left_panel.add_folder_from_path(entry.name, str(entry), parent_item)
                self._import_folder_contents(entry, folder_item)
                continue
            if entry.suffix.lower() != ".json":
                continue
            if entry.name in {"_suite.json", ".suite.json"}:
                data = self._read_request_file(entry)
                if isinstance(data, dict):
                    merged = {"name": parent_item.text(0), "description": "", "globals": []}
                    merged.update({k: v for k, v in data.items() if k in {"name", "description", "globals", "suite_type", "suite_id"}})
                    self.left_panel.set_folder_data(parent_item, merged)
                continue
            data = self._read_request_file(entry)
            if data is None:
                continue
            name = data.get("name") if isinstance(data.get("name"), str) else entry.stem
            data["name"] = name
            self.left_panel.add_request_from_data(name, data, str(entry), parent_item)

    def _collect_case_ids(self) -> set[str]:
        ids: set[str] = set()

        def walk(item) -> None:
            if item.data(0, self.left_panel._TYPE_ROLE) == "request":
                data = self.left_panel.get_request_data(item) or {}
                ai_case = data.get("ai_case")
                if isinstance(ai_case, dict):
                    case_id = str(ai_case.get("case_id") or "").strip()
                    if case_id:
                        ids.add(case_id)
                return
            for idx in range(item.childCount()):
                walk(item.child(idx))

        for idx in range(self.left_panel.tree_widget.topLevelItemCount()):
            walk(self.left_panel.tree_widget.topLevelItem(idx))
        return ids

    def _build_request_data_from_ai_case(self, case: CaseSchema) -> dict:
        request_json = case.request_json if isinstance(case.request_json, dict) else {}
        method = request_json.get("method") or "POST"
        headers = request_json.get("headers") if isinstance(request_json.get("headers"), dict) else {}
        params = request_json.get("params") or request_json.get("query") or {}
        body = request_json.get("body")
        if body is None:
            body = request_json.get("data")
        return {
            "name": case.name,
            "method": str(method).upper(),
            "url": case.endpoint,
            "headers": headers,
            "params": params,
            "body": body,
            "ai_case": case.to_dict(),
        }

    def _read_request_file(self, path: Path) -> dict | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _load_request_data(self, item) -> dict | None:
        if not self.left_panel.is_request_saved(item):
            return self.left_panel.get_request_data(item)
        path_value = self.left_panel.get_item_path(item)
        if not path_value:
            return self.left_panel.get_request_data(item)
        path = Path(path_value)
        if not path.exists():
            return self.left_panel.get_request_data(item)
        data = self._read_request_file(path)
        if data is None:
            return self.left_panel.get_request_data(item)
        if "name" not in data:
            data["name"] = item.text(0)
        self.left_panel.set_request_data(item, data)
        return data

    def _save_request_file(self, item, data: dict, name: str) -> Path | None:
        path = self._resolve_request_path(item, name)
        if path is None:
            return None
        if not path.suffix:
            path = path.with_suffix(".json")
        desired_name = data.get("name")
        normalized_name = desired_name.strip() if isinstance(desired_name, str) else ""
        if not normalized_name:
            normalized_name = path.stem
        data["name"] = normalized_name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return None
        self.left_panel.set_item_path(item, str(path))
        return path

    def _resolve_request_path(self, item, name: str) -> Path | None:
        existing = self.left_panel.get_item_path(item)
        if existing:
            return Path(existing)
        safe_name = self._safe_case_filename(name)
        parent = item.parent()
        if parent is not None:
            parent_path = self.left_panel.get_item_path(parent)
            if parent_path:
                return Path(parent_path) / f"{safe_name}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "\u4fdd\u5b58\u8bf7\u6c42",
            f"{safe_name}.json",
            "Request (*.json);;All Files (*)",
        )
        if not file_path:
            return None
        return Path(file_path)

    def _resolve_data_path(self) -> Path:
        root = Path(__file__).resolve().parents[3]
        return root / "project.json"

    def _resolve_legacy_path(self) -> Path:
        root = Path(__file__).resolve().parents[3]
        return root / "requests.json"

    def _load_saved_cases(self) -> None:
        project_path = self._project_path
        legacy_path = self._resolve_legacy_path()
        if not project_path.exists() and legacy_path.exists():
            try:
                legacy_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            except Exception:
                legacy_payload = {}
            legacy_cases = legacy_payload.get("cases") if isinstance(legacy_payload, dict) else None
            legacy_state = legacy_payload.get("ui_state") if isinstance(legacy_payload, dict) else None
            project = self._project_store.load_project(project_path)
            if isinstance(legacy_cases, list):
                project["suites"] = legacy_cases
            if isinstance(legacy_state, dict):
                project["ui_state"] = legacy_state
            self._project_store.save_project(project_path, project)
        self._project_state = self._project_store.load_project(project_path)
        suites = self._project_state.get("suites") if isinstance(self._project_state, dict) else None
        if isinstance(suites, list):
            self.left_panel.load_tree(suites)
        ui_state = self._project_state.get("ui_state") if isinstance(self._project_state, dict) else None
        if isinstance(ui_state, dict):
            self.right_panel.apply_ui_state(ui_state)
        self._envs = self._project_state.get("envs") if isinstance(self._project_state, dict) else []
        self._runs_index = self._project_state.get("runsIndex") if isinstance(self._project_state, dict) else []
        if self._runs_index:
            latest = self._runs_index[0]
            if isinstance(latest, dict):
                self._last_report_paths = {
                    "json": latest.get("json_path"),
                    "html": latest.get("html_path"),
                }
                has_report = any(self._last_report_paths.values())
                self.right_panel.export_report_button.setEnabled(has_report)

    def _persist_cases(self) -> None:
        project = self._project_state if isinstance(self._project_state, dict) else {}
        project["suites"] = self.left_panel.serialize_tree()
        project["ui_state"] = self.right_panel.get_ui_state()
        project["envs"] = self._envs if isinstance(self._envs, list) else []
        project["runsIndex"] = self._runs_index if isinstance(self._runs_index, list) else []
        try:
            self._project_store.save_project(self._project_path, project)
            self._project_state = project
        except Exception:
            return

    def _on_export_cases(self) -> None:
        current = self.left_panel.tree_widget.currentItem()
        if current is None:
            QMessageBox.warning(self, "\u65e0\u6cd5\u5bfc\u51fa", "\u8bf7\u9009\u62e9\u8981\u5bfc\u51fa\u7684\u8bf7\u6c42\u6216\u6587\u4ef6\u5939")
            return
        item_type = current.data(0, self.left_panel._TYPE_ROLE)
        if item_type == "request":
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "\u5bfc\u51fa\u8bf7\u6c42",
                f"{current.text(0)}.json",
                "JSON (*.json);;All Files (*)",
            )
            if not file_path:
                return
            data = self._load_request_data(current)
            if data is None:
                QMessageBox.warning(self, "\u5bfc\u51fa\u5931\u8d25", "\u8bf7\u6c42\u5185\u5bb9\u65e0\u6548")
                return
            try:
                Path(file_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                QMessageBox.warning(self, "\u5bfc\u51fa\u5931\u8d25", str(exc))
                return
            QMessageBox.information(self, "\u5bfc\u51fa\u6210\u529f", f"\u6587\u4ef6\u5df2\u4fdd\u5b58\u5230:\n{file_path}")
            return

        if item_type != "folder":
            QMessageBox.warning(self, "\u65e0\u6cd5\u5bfc\u51fa", "\u8bf7\u9009\u62e9\u8bf7\u6c42\u6216\u6587\u4ef6\u5939")
            return

        folder_path = self.left_panel.get_item_path(current)
        if not folder_path:
            QMessageBox.warning(self, "\u5bfc\u51fa\u5931\u8d25", "\u8be5\u6587\u4ef6\u5939\u6ca1\u6709\u5173\u8054\u7684\u786c\u76d8\u8def\u5f84")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55")
        if not target_dir:
            return
        source_root = Path(folder_path)
        exported = 0
        try:
            for file_path in source_root.rglob("*.json"):
                if not file_path.is_file():
                    continue
                relative = file_path.relative_to(source_root)
                dest = Path(target_dir) / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
                exported += 1
        except Exception as exc:
            QMessageBox.warning(self, "\u5bfc\u51fa\u5931\u8d25", str(exc))
            return
        QMessageBox.information(
            self,
            "\u5bfc\u51fa\u6210\u529f",
            f"\u5df2\u5bfc\u51fa {exported} \u4e2a\u6587\u4ef6\u5230:\n{target_dir}",
        )

    def _on_send_request(self) -> None:
        request_data = self.right_panel.request_panel.get_request_data()
        assertions = self.right_panel.assertion_panel.get_assertion_rows()
        current = self.left_panel.get_selected_request_item()
        if current is not None:
            folder_item = self._get_parent_folder_item(current)
            folder_data = self.left_panel.get_folder_data(folder_item) if folder_item is not None else {}
            variables = self._build_global_vars(folder_data)
            if variables:
                request_data["variables"] = variables
        if not request_data.get("method") or not request_data.get("url"):
            return
        self._apply_request_state(RequestRunState.RUNNING)
        self.right_panel.response_panel.show_running()

        def on_finished(result: dict) -> None:
            success = result.get("success") is True
            current = self.left_panel.get_selected_request_item()
            if current is not None:
                self.left_panel.set_request_response(current, result)
                self._append_run_history(current, success, result)
            self._apply_request_state(RequestRunState.SUCCESS if success else RequestRunState.ERROR)

        def on_error(_error: dict) -> None:
            current = self.left_panel.get_selected_request_item()
            if current is not None:
                error_result = {
                    "success": False,
                    "error_type": "WorkerError",
                    "error_message": "request failed",
                }
                self.left_panel.set_request_response(current, error_result)
                self._append_run_history(current, False, error_result)
            self._apply_request_state(RequestRunState.ERROR)

        self.controller.send_request_async(on_finished, on_error, request_data, assertions)

    def _on_run_suite(self) -> None:
        suite = self._build_suite_from_selection()
        if suite is None:
            QMessageBox.warning(self, "\u65e0\u6cd5\u6267\u884c", "\u8bf7\u9009\u62e9\u542b\u6709\u8bf7\u6c42\u7684\u6587\u4ef6\u5939")
            return
        suite_type = suite.get("suite_type")
        if suite_type == "ai_excel":
            self._run_ai_suite(suite)
            return
        if suite_type == "mixed":
            QMessageBox.warning(
                self,
                "\u65e0\u6cd5\u6267\u884c",
                "\u7528\u4f8b\u96c6\u5305\u542b AI \u7528\u4f8b\u548c\u666e\u901a\u7528\u4f8b\uff0c\u8bf7\u5206\u5f00\u6267\u884c\u3002",
            )
            return
        self.controller.set_suite(suite)
        self._apply_request_state(RequestRunState.RUNNING)
        self._set_busy(True, "\u6267\u884c\u4e2d...", allow_cancel=False)
        self.right_panel.export_report_button.setEnabled(False)
        legacy_started_at = time.monotonic()

        def on_progress(done: int, total: int) -> None:
            self.right_panel.progress_label.setText(f"\u6279\u91cf\u8fdb\u5ea6: {done}/{total}")

        def on_case_started(case: dict) -> None:
            case_id = case.get("case_id")
            item = self._suite_case_map.get(case_id)
            if item is not None:
                self.left_panel.set_running_item(item)
                if item == self.left_panel.get_selected_request_item():
                    self.right_panel.response_panel.show_running()

        def on_case_finished(case_result: dict) -> None:
            case_id = case_result.get("case_id")
            item = self._suite_case_map.get(case_id)
            if item is None:
                return
            response = case_result.get("response")
            if isinstance(response, dict):
                self.left_panel.set_request_response(item, response)
                if item == self.left_panel.get_selected_request_item():
                    self.right_panel.response_panel.update_response(response)
            self._append_run_history(
                item,
                case_result.get("result") == "PASS",
                response if isinstance(response, dict) else None,
            )
            result = case_result.get("result")
            success = result == "PASS"
            self.left_panel.set_case_result_icon(item, success)

        def on_finished(result: dict, path: str) -> None:
            self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)
            summary = result.get("summary", {})
            total = summary.get("total", 0) or 0
            passed = summary.get("pass", 0) or 0
            failed = summary.get("fail", 0) or 0
            rate = (passed / total * 100) if total else 0.0
            canceled = result.get("canceled")
            if canceled or failed:
                self._apply_request_state(RequestRunState.ERROR)
            else:
                self._apply_request_state(RequestRunState.SUCCESS)
            self.left_panel.set_running_item(None)
            report_paths = self._generate_legacy_report(result, suite, legacy_started_at)
            title = "\u6267\u884c\u5b8c\u6210" if not canceled else "\u5df2\u53d6\u6d88"
            resolved_path = str(Path(path).resolve()) if path else "-"
            message = f"\u901a\u8fc7\u7387: {rate:.1f}%\n\u7ed3\u679c\u6587\u4ef6:\n{resolved_path}"
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle(title)
            box.setText(message)
            copy_button = box.addButton("\u590d\u5236\u8def\u5f84", QMessageBox.ButtonRole.ActionRole)
            open_button = None
            html_path = report_paths.get("html") if isinstance(report_paths, dict) else None
            if isinstance(html_path, str) and html_path:
                open_button = box.addButton("\u6253\u5f00HTML\u62a5\u544a", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() == copy_button:
                QApplication.clipboard().setText(resolved_path)
            elif open_button is not None and box.clickedButton() == open_button and html_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(html_path).resolve())))

        self.controller.run_suite_async(on_progress, on_finished, on_case_started, on_case_finished)

    def _run_ai_suite(self, suite: dict) -> None:
        if self._suite_thread is not None or self._suite_worker is not None:
            return
        self._apply_request_state(RequestRunState.RUNNING)
        self._set_busy(True, "\u6267\u884c\u4e2d...", allow_cancel=False)
        self.right_panel.export_report_button.setEnabled(False)
        env = self._get_active_env()
        self._ai_suite_context = suite
        self._ai_env_context = env
        worker = SuiteExecutorWorker(suite, env)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        worker.progress.connect(self._on_ai_suite_progress, Qt.ConnectionType.QueuedConnection)
        worker.case_started.connect(self._on_ai_suite_case_started, Qt.ConnectionType.QueuedConnection)
        worker.case_finished.connect(self._on_ai_suite_case_finished, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._on_ai_suite_finished, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._suite_thread = thread
        self._suite_worker = worker
        thread.start()

    @Slot(int, int)
    def _on_ai_suite_progress(self, done: int, total: int) -> None:
        self.right_panel.progress_label.setText(f"\u6279\u91cf\u8fdb\u5ea6: {done}/{total}")

    @Slot(object)
    def _on_ai_suite_case_started(self, case: dict) -> None:
        case_id = case.get("case_id")
        item = self._suite_case_map.get(case_id)
        if item is not None:
            self.left_panel.set_running_item(item)
            if item == self.left_panel.get_selected_request_item():
                self.right_panel.response_panel.show_running()

    @Slot(object)
    def _on_ai_suite_case_finished(self, case_result: dict) -> None:
        case_id = case_result.get("case_id")
        item = self._suite_case_map.get(case_id)
        if item is None:
            return
        response = case_result.get("response")
        if isinstance(response, dict):
            self.left_panel.set_request_response(item, response)
            if item == self.left_panel.get_selected_request_item():
                self.right_panel.response_panel.update_response(response)
        success = case_result.get("result") == "OK"
        self._append_run_history(item, success, response if isinstance(response, dict) else None)
        self.left_panel.set_case_result_icon(item, success)

    @Slot(object)
    def _on_ai_suite_finished(self, result: RunResult) -> None:
        self._suite_thread = None
        self._suite_worker = None
        self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)
        summary = result.summary
        total = summary.get("total", 0) or 0
        ok = summary.get("ok", 0) or 0
        ng = summary.get("ng", 0) or 0
        rate = summary.get("pass_rate", 0)
        if result.canceled or ng:
            self._apply_request_state(RequestRunState.ERROR)
        else:
            self._apply_request_state(RequestRunState.SUCCESS)
        self.left_panel.set_running_item(None)
        suite = self._ai_suite_context or {}
        env = self._ai_env_context or {}
        run_data = {
            "suite_name": suite.get("suite_name"),
            "base_url": env.get("baseUrl") or env.get("base_url") or "",
            "execute_time": datetime.now().isoformat(),
            "summary": summary,
            "items": result.items,
        }
        template_path = self._resolve_report_template_path()
        output_dir = str(self._resolve_runs_dir())
        try:
            generator = ReportGenerator(str(template_path))
            paths = generator.generate(run_data, output_dir)
            self._last_report_paths = paths
            self.right_panel.export_report_button.setEnabled(True)
            self._append_run_index(run_data, paths)
        except Exception as exc:
            QMessageBox.warning(self, "\u62a5\u544a\u751f\u6210\u5931\u8d25", str(exc))
            paths = {}
        title = "\u6267\u884c\u5b8c\u6210" if not result.canceled else "\u5df2\u53d6\u6d88"
        message = f"\u901a\u8fc7\u7387: {rate:.1f}%\n\u603b\u6570: {total}  OK: {ok}  NG: {ng}"
        if paths:
            message += f"\nJSON: {paths.get('json', '-')}\nHTML: {paths.get('html', '-')}"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(title)
        box.setText(message)
        open_button = None
        html_path = paths.get("html") if isinstance(paths, dict) else None
        if isinstance(html_path, str) and html_path:
            open_button = box.addButton("\u6253\u5f00HTML\u62a5\u544a", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if open_button is not None and box.clickedButton() == open_button and html_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(html_path).resolve())))
        self._ai_suite_context = None
        self._ai_env_context = None

    def _on_cancel_suite(self) -> None:
        self.right_panel.progress_label.setText("\u53d6\u6d88\u4e2d...")
        self.controller.cancel_suite()
        if self._suite_worker is not None:
            self._suite_worker.cancel()

    def _apply_request_state(self, state: "RequestRunState") -> None:
        self._request_state = state
        running = state == RequestRunState.RUNNING
        self.right_panel.send_button.setEnabled(self._has_request_selection and not running)
        self.right_panel.save_button.setEnabled(self._has_request_selection and not running)
        if running:
            self.right_panel.send_button.setToolTip("\u8bf7\u6c42\u6267\u884c\u4e2d...")
        else:
            self.right_panel.send_button.setToolTip("\u53d1\u9001\u8bf7\u6c42\uff08Ctrl + Enter\uff09")
        self.right_panel.request_panel.update_run_button_state(state.value)
        self._update_run_state_badge(state)

    def _append_run_history(self, item, success: bool, result: dict | None) -> None:
        run_id = f"#{len(self._global_history) + 1}"
        name = item.data(0, self.left_panel._NAME_ROLE) or item.text(0)
        data = self._load_request_data(item) or {}
        method = (data.get("method") or "GET").upper()
        duration = None
        status_code = None
        error_message = None
        if isinstance(result, dict):
            duration = result.get("elapsed_ms")
            status_code = result.get("status_code")
            error_message = result.get("error_message")
        record = {
            "run_id": run_id,
            "request_name": name,
            "method": method,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "status": "SUCCESS" if success else "ERROR",
            "duration_ms": duration if duration is not None else "-",
            "status_code": status_code if status_code is not None else "-",
            "error_message": error_message if error_message else "",
            "response": result if isinstance(result, dict) else None,
            "request": {
                "name": name,
                "method": method,
                "url": data.get("url") or "",
                "headers": data.get("headers") or {},
                "body": data.get("body"),
            },
        }
        self._global_history.insert(0, record)
        self.left_panel.append_global_history(record)

    def _on_history_selected(self, record: dict) -> None:
        response = record.get("response")
        if isinstance(response, dict):
            self.right_panel.response_panel.update_response(response)
        request = record.get("request")
        if isinstance(request, dict):
            self.right_panel.request_panel.set_request_data(request)

    def _update_run_state_badge(self, state: "RequestRunState") -> None:
        label = self.left_panel.run_state_label
        if state == RequestRunState.RUNNING:
            label.setText("\u6267\u884c\u4e2d")
            label.setStyleSheet(
                "color: #1d4ed8; background: #dbeafe; padding: 3px 8px; border-radius: 10px;"
            )
        elif state == RequestRunState.SUCCESS:
            label.setText("\u5b8c\u6210")
            label.setStyleSheet(
                "color: #065f46; background: #d1fae5; padding: 3px 8px; border-radius: 10px;"
            )
        elif state == RequestRunState.ERROR:
            label.setText("\u5931\u8d25")
            label.setStyleSheet(
                "color: #9a3412; background: #ffedd5; padding: 3px 8px; border-radius: 10px;"
            )
        else:
            label.setText("\u7a7a\u95f2")
            label.setStyleSheet(
                "color: #6b7280; background: #f1f5f9; padding: 3px 8px; border-radius: 10px;"
            )

    def _get_active_env(self) -> dict:
        if isinstance(self._envs, list):
            for env in self._envs:
                if isinstance(env, dict):
                    return env
        return {
            "name": "default",
            "baseUrl": "",
            "headers": {},
            "vars": {},
        }

    def _resolve_report_template_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / "app" / "assets" / "templates" / "report.html"

    def _resolve_runs_dir(self) -> Path:
        root = Path(__file__).resolve().parents[3]
        return root / "runs"

    def _append_run_index(self, run_data: dict, paths: dict[str, str]) -> None:
        entry = {
            "run_id": datetime.now().strftime("run_%Y%m%d_%H%M%S"),
            "suite_name": run_data.get("suite_name") or "",
            "execute_time": run_data.get("execute_time"),
            "summary": run_data.get("summary"),
            "json_path": paths.get("json"),
            "html_path": paths.get("html"),
        }
        self._runs_index.insert(0, entry)
        if not isinstance(self._project_state, dict):
            self._project_state = {}
        self._project_state["runsIndex"] = self._runs_index
        self._persist_cases()

    def _on_export_report(self) -> None:
        if not self._last_report_paths:
            QMessageBox.warning(self, "\u65e0\u6cd5\u5bfc\u51fa", "\u8bf7\u5148\u6267\u884c\u7528\u4f8b\u96c6\u751f\u6210\u62a5\u544a")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55")
        if not target_dir:
            return
        copied = 0
        try:
            for key in ("json", "html"):
                path = self._last_report_paths.get(key)
                if not path:
                    continue
                src = Path(path)
                if not src.exists():
                    continue
                dest = Path(target_dir) / src.name
                shutil.copy2(src, dest)
                copied += 1
        except Exception as exc:
            QMessageBox.warning(self, "\u5bfc\u51fa\u5931\u8d25", str(exc))
            return
        QMessageBox.information(self, "\u5bfc\u51fa\u6210\u529f", f"\u5df2\u5bfc\u51fa {copied} \u4e2a\u62a5\u544a\u6587\u4ef6")

    def _generate_legacy_report(self, result: dict, suite: dict, started_at: float) -> dict[str, str]:
        cases = result.get("cases") if isinstance(result, dict) else None
        if not isinstance(cases, list):
            return {}
        duration_ms = int((time.monotonic() - started_at) * 1000)
        summary = result.get("summary", {}) if isinstance(result, dict) else {}
        total = summary.get("total", 0) or 0
        passed = summary.get("pass", 0) or 0
        failed = summary.get("fail", 0) or 0
        report_summary = {
            "total": total,
            "ok": passed,
            "ng": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "duration_ms": duration_ms,
        }
        items: list[dict] = []
        for case in cases:
            if not isinstance(case, dict):
                continue
            response = case.get("response") if isinstance(case.get("response"), dict) else {}
            assertion_results = case.get("assertion_results") if isinstance(case.get("assertion_results"), list) else []
            assertions = []
            failure_reason = ""
            for assertion in assertion_results:
                if not isinstance(assertion, dict):
                    continue
                passed_flag = assertion.get("result") == "PASS"
                message = assertion.get("message") or assertion.get("reason") or ""
                assertions.append(
                    {
                        "name": assertion.get("type"),
                        "passed": passed_flag,
                        "actual": assertion.get("actual"),
                        "expected": assertion.get("expected"),
                        "message": message,
                    }
                )
                if not passed_flag and not failure_reason:
                    failure_reason = message
            if response.get("success") is False and not failure_reason:
                failure_reason = response.get("error_message") or "request failed"
            result_flag = "OK" if case.get("result") == "PASS" else "NG"
            items.append(
                {
                    "case_id": case.get("case_id"),
                    "name": case.get("name"),
                    "request": case.get("request"),
                    "response": response,
                    "assertions": assertions,
                    "elapsed_ms": response.get("elapsed_ms"),
                    "result": result_flag,
                    "failure_reason": failure_reason,
                }
            )
        run_data = {
            "suite_name": suite.get("suite_name") if isinstance(suite, dict) else "",
            "base_url": "",
            "execute_time": datetime.now().isoformat(),
            "summary": report_summary,
            "items": items,
        }
        template_path = self._resolve_report_template_path()
        output_dir = str(self._resolve_runs_dir())
        try:
            generator = ReportGenerator(str(template_path))
            paths = generator.generate(run_data, output_dir)
            self._last_report_paths = paths
            self.right_panel.export_report_button.setEnabled(True)
            self._append_run_index(run_data, paths)
            return paths
        except Exception as exc:
            QMessageBox.warning(self, "\u62a5\u544a\u751f\u6210\u5931\u8d25", str(exc))
        return {}
    def _build_suite_from_selection(self) -> dict | None:
        self._suite_case_map = {}
        current = self.left_panel.tree_widget.currentItem()
        if current is None:
            return None
        item_type = current.data(0, self.left_panel._TYPE_ROLE)
        legacy_cases: list[dict] = []
        ai_cases: list[dict] = []
        if item_type == "request":
            ai_case = self._build_ai_case_from_item(current)
            if ai_case is not None:
                ai_cases.append(ai_case)
            else:
                case = self._build_case_from_item(current, 1)
                if case is not None:
                    legacy_cases.append(case)
            suite_name = (
                ai_cases[0].get("name")
                if ai_cases
                else legacy_cases[0].get("name") if legacy_cases else "default_suite"
            )
        else:
            suite_name = current.data(0, self.left_panel._NAME_ROLE) or current.text(0)
            self._collect_suite_cases(current, legacy_cases, ai_cases)
        if not legacy_cases and not ai_cases:
            return None
        if ai_cases and not legacy_cases:
            return {
                "suite_name": suite_name,
                "cases": ai_cases,
                "output_dir": "runs",
                "suite_type": "ai_excel",
            }
        if legacy_cases and not ai_cases:
            return {
                "suite_name": suite_name,
                "cases": legacy_cases,
                "output_dir": "results",
                "suite_type": "legacy",
            }
        return {
            "suite_name": suite_name,
            "cases": legacy_cases,
            "output_dir": "results",
            "suite_type": "mixed",
        }

    def _collect_suite_cases(self, item, legacy_cases: list[dict], ai_cases: list[dict]) -> None:
        if item.data(0, self.left_panel._TYPE_ROLE) == "request":
            ai_case = self._build_ai_case_from_item(item)
            if ai_case is not None:
                ai_cases.append(ai_case)
                return
            case = self._build_case_from_item(item, len(legacy_cases) + 1)
            if case is not None:
                legacy_cases.append(case)
            return
        for idx in range(item.childCount()):
            self._collect_suite_cases(item.child(idx), legacy_cases, ai_cases)

    def _build_case_from_item(self, item, index: int) -> dict | None:
        data = self._load_request_data(item) or {}
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            name = item.data(0, self.left_panel._NAME_ROLE) or item.text(0)
        request_data = {
            "method": data.get("method"),
            "url": data.get("url"),
            "headers": data.get("headers") or {},
            "body": data.get("body"),
        }
        folder_item = self._get_parent_folder_item(item)
        folder_data = self.left_panel.get_folder_data(folder_item) if folder_item is not None else {}
        variables = self._build_global_vars(folder_data)
        if variables:
            request_data["variables"] = variables
        pre_processors = data.get("preProcessors")
        post_processors = data.get("postProcessors")
        if not request_data.get("method") or not request_data.get("url"):
            return None
        case_id = f"item_{id(item)}"
        self._suite_case_map[case_id] = item
        return {
            "case_id": case_id,
            "name": name,
            "request": request_data,
            "assertions": self._filter_assertions(data.get("assertions") or []),
            "preProcessors": pre_processors if isinstance(pre_processors, list) else [],
            "postProcessors": post_processors if isinstance(post_processors, list) else [],
        }

    def _build_ai_case_from_item(self, item) -> dict | None:
        data = self._load_request_data(item) or {}
        ai_case = data.get("ai_case")
        if not isinstance(ai_case, dict):
            return None
        case_id = str(ai_case.get("case_id") or "").strip()
        if not case_id:
            return None
        case = dict(ai_case)
        if not case.get("name"):
            name = data.get("name")
            if not isinstance(name, str) or not name.strip():
                name = item.data(0, self.left_panel._NAME_ROLE) or item.text(0)
            case["name"] = name
        self._suite_case_map[case_id] = item
        return case
    def _filter_assertions(self, assertions: list) -> list:
        filtered: list = []
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            if assertion.get("enabled", True) is False:
                continue
            filtered.append(assertion)
        return filtered

    def closeEvent(self, event) -> None:
        self._persist_cases()
        super().closeEvent(event)


class RequestRunState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
