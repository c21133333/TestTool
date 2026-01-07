import json
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSplitter, QWidget, QFileDialog, QApplication

from requesttool.controller import ApiTestController
from requesttool.ui.panels import CaseListPanel, RightPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("API \u63a5\u53e3\u6d4b\u8bd5\u5de5\u5177")
        self.resize(1200, 800)
        self.setFont(QFont("Segoe UI", 10))
        self._has_request_selection = False
        self._data_path = self._resolve_data_path()
        self._request_state = RequestRunState.IDLE
        self._suite_case_map: dict[str, object] = {}
        self._global_history: list[dict] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
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
        )
        self.right_panel.send_button.clicked.connect(self._on_send_request)
        self.right_panel.save_button.clicked.connect(self._on_save_request)
        self.right_panel.request_panel.data_changed.connect(self._on_request_data_changed)
        self.right_panel.welcome_new_request_button.clicked.connect(self.left_panel._on_add_request_clicked)
        self.right_panel.welcome_new_folder_button.clicked.connect(self.left_panel._on_add_folder_clicked)
        self.left_panel.request_selected.connect(self._on_request_selected)
        self.left_panel.request_edited.connect(self._on_request_edited)
        self.left_panel.import_request_clicked.connect(self._on_import_request)
        self.left_panel.import_folder_clicked.connect(self._on_import_folder)
        self.left_panel.export_clicked.connect(self._on_export_cases)
        self.left_panel.run_suite_clicked.connect(self._on_run_suite)
        self.left_panel.tree_changed.connect(self._persist_cases)
        self.left_panel.history_selected.connect(self._on_history_selected)
        self._load_saved_cases()
        self._update_request_controls()
        self._apply_request_state(RequestRunState.IDLE)
        self.right_panel.show_welcome()
        self._set_busy(False, "\u7a7a\u95f2", allow_cancel=False)

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
            self._has_request_selection = False
            self.right_panel.request_panel.clear_request()
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
        if data is None:
            self.right_panel.request_panel.clear_request()
        else:
            self.right_panel.request_panel.set_request_data(data)
        if not self.right_panel.request_panel.name_input.text().strip():
            raw_name = item.data(0, self.left_panel._NAME_ROLE)
            self.right_panel.request_panel.name_input.setText(raw_name if isinstance(raw_name, str) else item.text(0))
        status = "\u5df2\u4fdd\u5b58" if self.left_panel.is_request_saved(item) else "\u672a\u4fdd\u5b58"
        self.right_panel.save_status_label.setText(status)
        cached_response = self.left_panel.get_request_response(item)
        if cached_response is not None:
            self.right_panel.response_panel.update_response(cached_response)
        else:
            self.right_panel.response_panel.clear()
        self.right_panel.show_content()
        self._update_request_controls()

    def _on_save_request(self) -> None:
        item = self.left_panel.get_selected_request_item()
        if item is None:
            return
        data = self.right_panel.request_panel.get_request_data()
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            name = name.strip()
            self.left_panel.set_request_name(item, name)
        else:
            name = item.text(0)
            data["name"] = name
        if not self._save_request_file(item, data, name):
            QMessageBox.warning(self, "\u4fdd\u5b58\u5931\u8d25", "\u8bf7\u6c42\u4fdd\u5b58\u5931\u8d25")
            return
        self.left_panel.set_request_data(item, data)
        self.right_panel.save_status_label.setText("\u5df2\u4fdd\u5b58")
        self._persist_cases()
        path_value = self.left_panel.get_item_path(item)
        if path_value:
            QMessageBox.information(self, "\u4fdd\u5b58\u6210\u529f", f"\u6587\u4ef6\u5df2\u4fdd\u5b58\u5230:\n{path_value}")

    def _on_request_edited(self, item) -> None:
        if item == self.left_panel.get_selected_request_item():
            if self.right_panel.request_panel.name_input.text().strip() != item.text(0):
                self.right_panel.request_panel.name_input.setText(item.text(0))
            self.right_panel.save_status_label.setText("\u672a\u4fdd\u5b58")

    def _on_request_data_changed(self) -> None:
        item = self.left_panel.get_selected_request_item()
        if item is None:
            return
        name = self.right_panel.request_panel.name_input.text().strip()
        if name:
            self.left_panel.set_request_name(item, name)
        if self.left_panel.is_request_saved(item):
            self.left_panel.set_request_saved(item, False)
        self.right_panel.save_status_label.setText("\u672a\u4fdd\u5b58")

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
            data = self._read_request_file(entry)
            if data is None:
                continue
            name = data.get("name") if isinstance(data.get("name"), str) else entry.stem
            data["name"] = name
            self.left_panel.add_request_from_data(name, data, str(entry), parent_item)

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

    def _save_request_file(self, item, data: dict, name: str) -> bool:
        path = self._resolve_request_path(item, name)
        if path is None:
            return False
        if not path.suffix:
            path = path.with_suffix(".json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return False
        self.left_panel.set_item_path(item, str(path))
        return True

    def _resolve_request_path(self, item, name: str) -> Path | None:
        existing = self.left_panel.get_item_path(item)
        if existing:
            return Path(existing)
        parent = item.parent()
        if parent is not None:
            parent_path = self.left_panel.get_item_path(parent)
            if parent_path:
                return Path(parent_path) / f"{name}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "\u4fdd\u5b58\u8bf7\u6c42",
            f"{name}.json",
            "Request (*.json);;All Files (*)",
        )
        if not file_path:
            return None
        return Path(file_path)

    def _resolve_data_path(self) -> Path:
        root = Path(__file__).resolve().parents[3]
        return root / "requests.json"

    def _load_saved_cases(self) -> None:
        if not self._data_path.exists():
            return
        try:
            content = self._data_path.read_text(encoding="utf-8")
            payload = json.loads(content)
        except Exception:
            return
        nodes = payload.get("cases") if isinstance(payload, dict) else None
        if isinstance(nodes, list):
            self.left_panel.load_tree(nodes)

    def _persist_cases(self) -> None:
        payload = {"cases": self.left_panel.serialize_tree()}
        try:
            self._data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
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
        if not request_data.get("method") or not request_data.get("url"):
            return
        current = self.left_panel.get_selected_request_item()
        if current is not None and self._is_request_dirty(current, request_data):
            name = current.data(0, self.left_panel._NAME_ROLE) or current.text(0)
            QMessageBox.warning(self, "未保存", f"检测到未保存的修改，请先保存：{name}")
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

        self.controller.send_request_async(on_finished, on_error)

    def _on_run_suite(self) -> None:
        dirty_names = self._collect_dirty_requests()
        if dirty_names:
            preview = "\n".join(dirty_names[:5])
            extra = "" if len(dirty_names) <= 5 else f"\n...共 {len(dirty_names)} 条"
            QMessageBox.warning(self, "未保存", f"检测到未保存的修改，请先保存：\n{preview}{extra}")
            return
        suite = self._build_suite_from_selection()
        if suite is None:
            QMessageBox.warning(self, "\u65e0\u6cd5\u6267\u884c", "\u8bf7\u9009\u62e9\u542b\u6709\u8bf7\u6c42\u7684\u6587\u4ef6\u5939")
            return
        self.controller.set_suite(suite)
        self._apply_request_state(RequestRunState.RUNNING)
        self._set_busy(True, "\u6267\u884c\u4e2d...", allow_cancel=False)

        def on_progress(done: int, total: int) -> None:
            self.right_panel.progress_label.setText(f"\u6279\u91cf\u8fdb\u5ea6: {done}/{total}")

        def on_case_started(case: dict) -> None:
            case_id = case.get("case_id")
            item = self._suite_case_map.get(case_id)
            if item is not None:
                self.left_panel.set_running_item(item)

        def on_case_finished(case_result: dict) -> None:
            case_id = case_result.get("case_id")
            item = self._suite_case_map.get(case_id)
            if item is None:
                return
            response = case_result.get("response")
            if isinstance(response, dict):
                self.left_panel.set_request_response(item, response)
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
            title = "\u6267\u884c\u5b8c\u6210" if not canceled else "\u5df2\u53d6\u6d88"
            resolved_path = str(Path(path).resolve()) if path else "-"
            message = f"\u901a\u8fc7\u7387: {rate:.1f}%\n\u7ed3\u679c\u6587\u4ef6:\n{resolved_path}"
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle(title)
            box.setText(message)
            copy_button = box.addButton("\u590d\u5236\u8def\u5f84", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Ok)
            box.exec()
            if box.clickedButton() == copy_button:
                QApplication.clipboard().setText(resolved_path)

        self.controller.run_suite_async(on_progress, on_finished, on_case_started, on_case_finished)

    def _on_cancel_suite(self) -> None:
        self.right_panel.progress_label.setText("\u53d6\u6d88\u4e2d...")
        self.controller.cancel_suite()

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

    def _collect_dirty_requests(self) -> list[str]:
        current = self.left_panel.tree_widget.currentItem()
        if current is None:
            return []
        items: list = []
        if current.data(0, self.left_panel._TYPE_ROLE) == "request":
            items.append(current)
        else:
            self._collect_request_items(current, items)
        dirty: list[str] = []
        for item in items:
            if self._is_request_dirty(item):
                name = item.data(0, self.left_panel._NAME_ROLE) or item.text(0)
                dirty.append(str(name))
        return dirty

    def _collect_request_items(self, item, items: list) -> None:
        if item.data(0, self.left_panel._TYPE_ROLE) == "request":
            items.append(item)
            return
        for idx in range(item.childCount()):
            self._collect_request_items(item.child(idx), items)

    def _is_request_dirty(self, item, current_data: dict | None = None) -> bool:
        saved = self._load_saved_request_data(item)
        if saved is None:
            return True
        if current_data is None:
            current_data = self.left_panel.get_request_data(item)
        if current_data is None:
            return False
        return self._normalize_request_data(current_data) != self._normalize_request_data(saved)

    def _load_saved_request_data(self, item) -> dict | None:
        path_value = self.left_panel.get_item_path(item)
        if path_value:
            path = Path(path_value)
            if path.exists():
                data = self._read_request_file(path)
                if isinstance(data, dict):
                    return data
        data = self.left_panel.get_request_data(item)
        return data if isinstance(data, dict) else None

    def _normalize_request_data(self, data: dict) -> dict:
        return {
            "name": data.get("name"),
            "method": data.get("method"),
            "url": data.get("url"),
            "headers": data.get("headers") or {},
            "body": data.get("body"),
        }

    def _append_run_history(self, item, success: bool, result: dict | None) -> None:
        run_id = f"#{len(self._global_history) + 1}"
        name = item.data(0, self.left_panel._NAME_ROLE) or item.text(0)
        data = self._load_request_data(item) or {}
        method = (data.get("method") or "GET").upper()
        duration = None
        status_code = None
        if isinstance(result, dict):
            duration = result.get("elapsed_ms")
            status_code = result.get("status_code")
        record = {
            "run_id": run_id,
            "request_name": name,
            "method": method,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "status": "SUCCESS" if success else "ERROR",
            "duration_ms": duration if duration is not None else "-",
            "status_code": status_code if status_code is not None else "-",
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

    def _build_suite_from_selection(self) -> dict | None:
        self._suite_case_map = {}
        current = self.left_panel.tree_widget.currentItem()
        if current is None:
            return None
        item_type = current.data(0, self.left_panel._TYPE_ROLE)
        cases: list[dict] = []
        if item_type == "request":
            case = self._build_case_from_item(current, 1)
            if case is not None:
                cases.append(case)
            suite_name = case.get("name") if case else "default_suite"
        else:
            suite_name = current.data(0, self.left_panel._NAME_ROLE) or current.text(0)
            self._collect_cases(current, cases)
        if not cases:
            return None
        return {
            "suite_name": suite_name,
            "cases": cases,
            "output_dir": "results",
        }


    def _collect_cases(self, item, cases: list[dict]) -> None:
        if item.data(0, self.left_panel._TYPE_ROLE) == "request":
            case = self._build_case_from_item(item, len(cases) + 1)
            if case is not None:
                cases.append(case)
            return
        for idx in range(item.childCount()):
            self._collect_cases(item.child(idx), cases)

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
        if not request_data.get("method") or not request_data.get("url"):
            return None
        case_id = f"item_{id(item)}"
        self._suite_case_map[case_id] = item
        return {
            "case_id": case_id,
            "name": name,
            "request": request_data,
            "assertions": data.get("assertions") or [],
        }


class RequestRunState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
