import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QBrush, QColor, QPixmap, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QStackedWidget,
    QFileDialog,
    QToolButton,
    QStyle,
    QListWidget,
    QListWidgetItem,
    QFrame,
)


class CollapsibleSection(QWidget):
    def __init__(self, title: str, *, collapsed: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._header = QWidget()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("font-weight: 600; color: #111827;")
        self._toggle = QToolButton()
        self._toggle.setAutoRaise(True)
        self._toggle.setFixedSize(18, 18)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if not collapsed else Qt.ArrowType.RightArrow)
        self._toggle.clicked.connect(self._on_toggled)

        header_layout.addWidget(self._title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self._toggle)

        self._content = QWidget()
        self._content.setVisible(not collapsed)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        self._divider = QFrame()
        self._divider.setFrameShape(QFrame.Shape.HLine)
        self._divider.setFrameShadow(QFrame.Shadow.Plain)
        self._divider.setStyleSheet("color: #e5e7eb;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._header)
        layout.addWidget(self._divider)
        layout.addWidget(self._content)
        self._header.installEventFilter(self)

    def set_content_layout(self, layout: QVBoxLayout) -> None:
        QWidget().setLayout(self._content_layout)
        self._content_layout = layout
        self._content.setLayout(layout)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def _on_toggled(self, checked: bool) -> None:
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self._content.setVisible(checked)
        self._divider.setVisible(checked)

    def eventFilter(self, obj, event) -> bool:
        if obj == self._header and event.type() == event.Type.MouseButtonPress:
            self._on_toggled(not self._content.isVisible())
            return True
        return super().eventFilter(obj, event)

class CaseListPanel(QWidget):
    _TYPE_ROLE = Qt.ItemDataRole.UserRole
    _DATA_ROLE = Qt.ItemDataRole.UserRole + 1
    _SAVED_ROLE = Qt.ItemDataRole.UserRole + 2
    _PATH_ROLE = Qt.ItemDataRole.UserRole + 3
    _NAME_ROLE = Qt.ItemDataRole.UserRole + 4
    _RESPONSE_ROLE = Qt.ItemDataRole.UserRole + 5
    _HISTORY_ROLE = Qt.ItemDataRole.UserRole + 6
    request_selected = Signal(object)
    request_edited = Signal(object)
    import_request_clicked = Signal()
    import_folder_clicked = Signal()
    export_clicked = Signal()
    run_suite_clicked = Signal()
    tree_changed = Signal()
    history_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running_item: QTreeWidgetItem | None = None
        self._pass_icon = None
        self._fail_icon = None
        self._hover_item: QTreeWidgetItem | None = None
        self._updating_label = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("caseListPanel")
        self.setStyleSheet(
            "#caseListPanel { background-color: #f8fafc; border-right: 1px solid #e5e7eb; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(8, 6, 8, 0)
        title_layout.setSpacing(2)
        title_row = QHBoxLayout()
        title_label = QLabel("\u8bf7\u6c42\u4e2d\u5fc3")
        title_label.setStyleSheet("font-weight: 600; font-size: 11pt; color: #111827;")
        self.run_state_label = QLabel("\u7a7a\u95f2")
        self.run_state_label.setStyleSheet(
            "color: #6b7280; background: #f1f5f9; padding: 3px 8px; border-radius: 10px;"
        )
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        title_row.addWidget(self.run_state_label)
        subtitle_label = QLabel("API Test Cases")
        subtitle_label.setStyleSheet("font-size: 9pt; color: #6b7280;")
        title_layout.addLayout(title_row)
        title_layout.addWidget(subtitle_label)

        search_block = QWidget()
        search_layout = QHBoxLayout(search_block)
        search_layout.setContentsMargins(8, 0, 8, 0)
        search_layout.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("\u641c\u7d22\u7528\u4f8b / \u7528\u4f8b\u96c6 / URL")
        self.search_input.setMinimumWidth(220)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_input.textChanged.connect(self._apply_filter)
        search_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        self.search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addSpacing(6)

        self.new_request_button = QToolButton()
        self.new_request_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self.new_request_button.setToolTip("\u65b0\u5efa\u8bf7\u6c42")
        self.new_request_button.setFixedSize(24, 24)
        self.new_request_button.clicked.connect(self._on_add_request_clicked)
        self.new_folder_button = QToolButton()
        self.new_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        self.new_folder_button.setToolTip("\u65b0\u5efa\u7528\u4f8b\u96c6")
        self.new_folder_button.setFixedSize(24, 24)
        self.new_folder_button.clicked.connect(self._on_add_folder_clicked)
        self.import_button = QToolButton()
        self.import_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.import_button.setToolTip("\u5bfc\u5165")
        self.import_button.setFixedSize(24, 24)
        self.import_button.clicked.connect(self._on_import_clicked)
        self.export_button = QToolButton()
        self.export_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.export_button.setToolTip("\u5bfc\u51fa")
        self.export_button.setFixedSize(24, 24)
        self.export_button.clicked.connect(self.export_clicked.emit)
        search_layout.addWidget(self.new_request_button)
        search_layout.addWidget(self.new_folder_button)
        search_layout.addWidget(self.import_button)
        search_layout.addWidget(self.export_button)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setIndentation(18)
        self.tree_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.tree_widget.setMouseTracking(True)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.tree_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree_widget.itemChanged.connect(self._on_item_changed)
        self.tree_widget.itemEntered.connect(self._on_item_entered)
        self.tree_widget.itemClicked.connect(self._on_item_clicked)
        self.tree_widget.viewport().installEventFilter(self)
        self.tree_widget.setStyleSheet(
            "QTreeView::item { padding: 6px 8px; }"
            "QTreeView::item:hover { background-color: #eef2f7; }"
            "QTreeView::item:selected { background-color: #dbeafe; color: #111827; }"
            "QTreeView QLineEdit { border: none; background: transparent; padding: 0 2px; }"
        )

        layout.addWidget(title_block)
        layout.addWidget(search_block)
        layout.addWidget(self.tree_widget, 1)

        self.history_group = CollapsibleSection("Run History", collapsed=False)
        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self._on_history_clicked)
        self.history_list.setSpacing(6)
        self.history_list.setFrameShape(QFrame.Shape.NoFrame)
        self.history_list.setStyleSheet(
            "QListWidget::item { padding: 4px; border-bottom: 1px solid #e5e7eb; }"
            "QListWidget::item:selected { background: #eef2f7; }"
        )
        history_layout = self.history_group.content_layout()
        history_layout.setContentsMargins(8, 8, 8, 8)
        history_layout.addWidget(self.history_list)
        layout.addWidget(self.history_group)

    def add_case(self, name: str) -> None:
        self._add_request_item(None, name, edit=False)

    def has_requests(self) -> bool:
        for idx in range(self.tree_widget.topLevelItemCount()):
            if self._has_request_in_item(self.tree_widget.topLevelItem(idx)):
                return True
        return False

    def get_selected_request_item(self) -> QTreeWidgetItem | None:
        item = self.tree_widget.currentItem()
        if item is None:
            return None
        if item.data(0, self._TYPE_ROLE) == "request":
            return item
        return None

    def get_selected_folder_item(self) -> QTreeWidgetItem | None:
        item = self.tree_widget.currentItem()
        if item is None:
            return None
        if item.data(0, self._TYPE_ROLE) == "folder":
            return item
        return None

    def get_request_data(self, item: QTreeWidgetItem) -> dict | None:
        data = item.data(0, self._DATA_ROLE)
        return data if isinstance(data, dict) else None

    def set_request_data(self, item: QTreeWidgetItem, data: dict) -> None:
        item.setData(0, self._DATA_ROLE, data)
        item.setData(0, self._SAVED_ROLE, True)
        self._apply_request_style(item)
        self._apply_request_label(item)

    def set_request_name(self, item: QTreeWidgetItem, name: str) -> None:
        item.setData(0, self._NAME_ROLE, name)
        self._apply_request_label(item)

    def set_request_saved(self, item: QTreeWidgetItem, saved: bool) -> None:
        item.setData(0, self._SAVED_ROLE, saved)
        self._apply_request_style(item)

    def is_request_saved(self, item: QTreeWidgetItem) -> bool:
        return bool(item.data(0, self._SAVED_ROLE))

    def set_request_response(self, item: QTreeWidgetItem, response: dict) -> None:
        item.setData(0, self._RESPONSE_ROLE, response)

    def get_request_response(self, item: QTreeWidgetItem) -> dict | None:
        value = item.data(0, self._RESPONSE_ROLE)
        return value if isinstance(value, dict) else None

    def set_request_history(self, item: QTreeWidgetItem, history: list[dict]) -> None:
        item.setData(0, self._HISTORY_ROLE, history)

    def get_request_history(self, item: QTreeWidgetItem) -> list[dict]:
        value = item.data(0, self._HISTORY_ROLE)
        return value if isinstance(value, list) else []

    def append_global_history(self, record: dict) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, record)
        widget = HistoryItemWidget(record)
        item.setSizeHint(widget.sizeHint())
        self.history_list.insertItem(0, item)
        self.history_list.setItemWidget(item, widget)
        self.history_list.setCurrentRow(0)

    def _on_history_clicked(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self.history_selected.emit(record)

    def get_item_path(self, item: QTreeWidgetItem) -> str | None:
        value = item.data(0, self._PATH_ROLE)
        return value if isinstance(value, str) else None

    def set_item_path(self, item: QTreeWidgetItem, path: str | None) -> None:
        item.setData(0, self._PATH_ROLE, path or None)

    def add_request_from_data(
        self,
        name: str,
        data: dict,
        path: str | None,
        parent_item: QTreeWidgetItem | None = None,
    ) -> QTreeWidgetItem:
        item = self._add_request_item(parent_item, name, edit=False)
        item.setData(0, self._DATA_ROLE, data)
        item.setData(0, self._SAVED_ROLE, True)
        if path:
            self.set_item_path(item, path)
        self._apply_request_style(item)
        self._apply_request_label(item)
        return item

    def add_folder_from_path(
        self,
        name: str,
        path: str,
        parent_item: QTreeWidgetItem | None = None,
    ) -> QTreeWidgetItem:
        item = self._add_folder_item(parent_item, name, edit=False)
        self.set_item_path(item, path)
        return item

    def _on_context_menu(self, pos) -> None:
        item = self.tree_widget.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        item_type = item.data(0, self._TYPE_ROLE)
        add_request_action = menu.addAction("\u65b0\u5efa\u8bf7\u6c42")
        run_suite_action = None
        if item_type == "folder":
            run_suite_action = menu.addAction("\u6267\u884c\u7528\u4f8b\u96c6")
        rename_action = menu.addAction("\u91cd\u547d\u540d")
        copy_action = None
        if item_type == "request":
            copy_action = menu.addAction("\u590d\u5236")
        delete_action = menu.addAction("\u5220\u9664")
        action = menu.exec(self.tree_widget.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action == add_request_action:
            parent_item = item if item_type == "folder" else item.parent()
            self._add_request_item(
                parent_item,
                self._next_name(parent_item, "\u65b0\u5efa\u8bf7\u6c42"),
            )
        elif run_suite_action is not None and action == run_suite_action:
            self.run_suite_clicked.emit()
        elif action == rename_action:
            self._rename_item(item)
        elif action == copy_action:
            self._copy_request_item(item)
        elif action == delete_action:
            self._delete_item(item)

    def _get_target_parent(self) -> QTreeWidgetItem | None:
        selected = self.tree_widget.currentItem()
        if selected is None:
            return None
        if selected.data(0, self._TYPE_ROLE) == "folder":
            return selected
        return selected.parent()

    def _on_add_request_clicked(self) -> None:
        parent_item = self._get_target_parent()
        item = self._add_request_item(parent_item, self._next_name(parent_item, "\u65b0\u5efa\u8bf7\u6c42"))
        self.tree_widget.setCurrentItem(item)

    def _on_add_folder_clicked(self) -> None:
        parent_item = self._get_target_parent()
        base_dir = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u4fdd\u5b58\u4f4d\u7f6e")
        if not base_dir:
            return
        name = self._next_name(parent_item, "\u65b0\u5efa\u7528\u4f8b\u96c6")
        item = self._add_folder_item(parent_item, name)
        folder_path = Path(base_dir) / name
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.set_item_path(item, str(folder_path))
        self.tree_widget.setCurrentItem(item)

    def _on_import_clicked(self) -> None:
        menu = QMenu(self)
        import_request_action = menu.addAction("\u5bfc\u5165\u8bf7\u6c42")
        import_folder_action = menu.addAction("\u5bfc\u5165\u6587\u4ef6\u5939")
        action = menu.exec(self.import_button.mapToGlobal(self.import_button.rect().topLeft()))
        if action == import_request_action:
            self.import_request_clicked.emit()
        elif action == import_folder_action:
            self.import_folder_clicked.emit()

    def _copy_request_item(self, item: QTreeWidgetItem) -> None:
        if item.data(0, self._TYPE_ROLE) != "request":
            return
        parent_item = item.parent()
        name = self._next_name(parent_item, f"{item.text(0)} Copy")
        data = self.get_request_data(item) or {}
        copy_item = self._add_request_item(parent_item, name, edit=False)
        copy_item.setData(0, self._DATA_ROLE, data)
        copy_item.setData(0, self._SAVED_ROLE, False)
        self._apply_request_style(copy_item)
        self.tree_widget.setCurrentItem(copy_item)
        self.tree_changed.emit()

    def _delete_item(self, item: QTreeWidgetItem) -> None:
        parent = item.parent()
        if parent is None:
            index = self.tree_widget.indexOfTopLevelItem(item)
            if index >= 0:
                self.tree_widget.takeTopLevelItem(index)
        else:
            parent.removeChild(item)
        self.tree_changed.emit()

    def _on_selection_changed(self) -> None:
        self.request_selected.emit(self.get_selected_request_item())

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating_label:
            return
        item_type = item.data(0, self._TYPE_ROLE)
        prev_name = item.data(0, self._NAME_ROLE)
        current = item.text(0)
        if item_type == "request":
            current = self._strip_method_prefix(current)
        if prev_name != current:
            self._rename_item_path(item, prev_name, current, item_type)
        item.setData(0, self._NAME_ROLE, current)
        if item_type != "request":
            return
        if self.is_request_saved(item):
            item.setData(0, self._SAVED_ROLE, False)
            self._apply_request_style(item)
            self.request_edited.emit(item)
        self._apply_request_label(item)

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        for idx in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(idx)
            self._apply_filter_to_item(item, query)

    def _apply_filter_to_item(self, item: QTreeWidgetItem, query: str) -> bool:
        matched = query in item.text(0).lower() if query else True
        child_matched = False
        for child_index in range(item.childCount()):
            child = item.child(child_index)
            if self._apply_filter_to_item(child, query):
                child_matched = True
        item.setHidden(not (matched or child_matched))
        return matched or child_matched

    def _add_folder_item(
        self,
        parent_item: QTreeWidgetItem | None,
        name: str,
        *,
        edit: bool = True,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, self._TYPE_ROLE, "folder")
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        item.setData(0, self._NAME_ROLE, name)
        if parent_item is None:
            self.tree_widget.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
            parent_item.setExpanded(True)
        if edit:
            self.tree_widget.setCurrentItem(item)
            self.tree_widget.setFocus()
            self.tree_widget.editItem(item, 0)
        return item

    def _rename_item(self, item: QTreeWidgetItem) -> None:
        self.tree_widget.setCurrentItem(item)
        self.tree_widget.setFocus()
        self.tree_widget.editItem(item, 0)

    def _add_request_item(
        self,
        parent_item: QTreeWidgetItem | None,
        name: str,
        *,
        edit: bool = True,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, self._TYPE_ROLE, "request")
        item.setData(0, self._SAVED_ROLE, False)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        item.setData(0, self._NAME_ROLE, name)
        if parent_item is None:
            self.tree_widget.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
            parent_item.setExpanded(True)
        if edit:
            self.tree_widget.setCurrentItem(item)
            self.tree_widget.setFocus()
            self.tree_widget.editItem(item, 0)
        self._apply_request_style(item)
        self._apply_request_label(item)
        return item

    def _next_name(self, parent_item: QTreeWidgetItem | None, base_name: str) -> str:
        existing = set()
        if parent_item is None:
            count = self.tree_widget.topLevelItemCount()
            for idx in range(count):
                existing.add(self.tree_widget.topLevelItem(idx).text(0))
        else:
            for idx in range(parent_item.childCount()):
                existing.add(parent_item.child(idx).text(0))
        if base_name not in existing:
            return base_name
        index = 2
        while True:
            candidate = f"{base_name} ({index})"
            if candidate not in existing:
                return candidate
            index += 1

    def _has_request_in_item(self, item: QTreeWidgetItem) -> bool:
        if item.data(0, self._TYPE_ROLE) == "request":
            return True
        for idx in range(item.childCount()):
            if self._has_request_in_item(item.child(idx)):
                return True
        return False

    def _apply_request_style(self, item: QTreeWidgetItem) -> None:
        saved = self.is_request_saved(item)
        color = QColor("#10b981" if saved else "#f97316")
        item.setForeground(0, QBrush(color))
        item.setToolTip(0, "\u5df2\u4fdd\u5b58" if saved else "\u672a\u4fdd\u5b58")

    def _apply_request_label(self, item: QTreeWidgetItem) -> None:
        data = self.get_request_data(item) or {}
        method = data.get("method")
        method_label = method.upper() if isinstance(method, str) else "GET"
        base_name = item.data(0, self._NAME_ROLE)
        if not isinstance(base_name, str) or not base_name:
            base_name = self._strip_method_prefix(item.text(0))
        self._updating_label = True
        try:
            item.setText(0, f"[{method_label}]  {base_name}")
        finally:
            self._updating_label = False

    def set_running_item(self, item: QTreeWidgetItem | None) -> None:
        if self._running_item is not None:
            self._running_item.setBackground(0, QBrush())
        self._running_item = item
        if item is not None:
            item.setBackground(0, QBrush(QColor("#e0f2fe")))
            self.tree_widget.setCurrentItem(item)

    def set_case_result_icon(self, item: QTreeWidgetItem, success: bool) -> None:
        icon = self._get_status_icon(success)
        if icon is not None:
            item.setIcon(0, icon)

    def _get_status_icon(self, success: bool):
        if success and self._pass_icon is not None:
            return self._pass_icon
        if not success and self._fail_icon is not None:
            return self._fail_icon
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#16a34a") if success else QColor("#dc2626")
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "\u2713" if success else "\u00d7")
        painter.end()
        if success:
            self._pass_icon = pixmap
            return self._pass_icon
        self._fail_icon = pixmap
        return self._fail_icon

    def _strip_method_prefix(self, text: str) -> str:
        if text.startswith("[") and "]" in text:
            return text.split("]", 1)[-1].strip()
        return text

    def _on_item_entered(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, self._TYPE_ROLE) != "request":
            if self._hover_item is not None:
                self._apply_request_label(self._hover_item)
            self._hover_item = None
            return
        if self._hover_item is not None and self._hover_item != item:
            self._apply_request_label(self._hover_item)
        self._hover_item = item
        self._apply_request_label(item)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, self._TYPE_ROLE) != "request":
            return
        if item == self._hover_item:
            base_name = item.data(0, self._NAME_ROLE) or self._strip_method_prefix(item.text(0))
            item.setText(0, str(base_name))
            self._hover_item = None
            self.tree_widget.editItem(item, 0)

    def eventFilter(self, obj, event) -> bool:
        if obj == self.tree_widget.viewport() and event.type() == event.Type.Leave:
            if self._hover_item is not None:
                self._apply_request_label(self._hover_item)
                self._hover_item = None
        return super().eventFilter(obj, event)


    def _rename_item_path(
        self,
        item: QTreeWidgetItem,
        previous: str | None,
        current: str,
        item_type: str | None,
    ) -> None:
        path_value = self.get_item_path(item)
        if not path_value or not previous:
            return
        try:
            path = Path(path_value)
        except Exception:
            return
        if item_type == "folder":
            new_path = path.with_name(current)
        elif item_type == "request":
            suffix = path.suffix or ".json"
            new_path = path.with_name(f"{current}{suffix}")
        else:
            return
        if new_path == path:
            return
        try:
            if path.exists():
                path.rename(new_path)
        except Exception:
            return
        self.set_item_path(item, str(new_path))

    def serialize_tree(self) -> list[dict]:
        nodes: list[dict] = []
        for idx in range(self.tree_widget.topLevelItemCount()):
            node = self._serialize_item(self.tree_widget.topLevelItem(idx))
            if node is not None:
                nodes.append(node)
        return nodes

    def load_tree(self, nodes: list[dict]) -> None:
        self.tree_widget.clear()
        for node in nodes:
            self._load_item(node, None)

    def _serialize_item(self, item: QTreeWidgetItem) -> dict | None:
        item_type = item.data(0, self._TYPE_ROLE)
        if item_type == "request":
            if not self.is_request_saved(item):
                return None
            data = self.get_request_data(item) or {}
            data.setdefault("name", item.text(0))
            return {
                "type": "request",
                "name": item.text(0),
                "data": data,
                "path": self.get_item_path(item),
            }
        children: list[dict] = []
        for idx in range(item.childCount()):
            child = self._serialize_item(item.child(idx))
            if child is not None:
                children.append(child)
        if not children:
            return None
        return {
            "type": "folder",
            "name": item.text(0),
            "path": self.get_item_path(item),
            "children": children,
        }

    def _load_item(self, node: dict, parent: QTreeWidgetItem | None) -> None:
        node_type = node.get("type")
        name = node.get("name") or ""
        if node_type == "folder":
            item = self._add_folder_item(parent, name, edit=False)
            path_value = node.get("path")
            if isinstance(path_value, str):
                self.set_item_path(item, path_value)
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    self._load_item(child, item)
            return
        if node_type == "request":
            item = self._add_request_item(parent, name, edit=False)
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            if "name" not in data:
                data["name"] = name
            path_value = node.get("path")
            if isinstance(path_value, str):
                self.set_item_path(item, path_value)
            item.setData(0, self._DATA_ROLE, data)
            item.setData(0, self._SAVED_ROLE, True)
            self._apply_request_style(item)


class HistoryItemWidget(QWidget):
    def __init__(self, record: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        status = record.get("status", "-")
        method = record.get("method", "-")
        name = record.get("request_name", "-")
        code = record.get("status_code", "-")
        duration = record.get("duration_ms", "-")
        timestamp = record.get("timestamp", "-")

        status_dot = QLabel("\u25cf")
        status_dot.setStyleSheet(
            "color: #16a34a;" if status == "SUCCESS" else "color: #ea580c;"
        )
        method_label = QLabel(f"[{method}]")
        method_label.setStyleSheet("color: #1d4ed8; font-weight: 600;")
        title = QLabel(name)
        title.setStyleSheet("color: #111827;")
        status_label = QLabel(status)
        status_label.setStyleSheet("color: #16a34a;" if status == "SUCCESS" else "color: #ea580c;")

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        top_row.addWidget(status_dot)
        top_row.addWidget(status_label)
        top_row.addWidget(method_label)
        top_row.addWidget(title)
        top_row.addStretch(1)

        meta = QLabel(f"{code}   {duration}ms   {timestamp}")
        meta.setStyleSheet("color: #6b7280; font-size: 9pt;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addLayout(top_row)
        layout.addWidget(meta)


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
        self.send_button = self.request_panel.send_button
        self.save_button = self.request_panel.save_button
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.save_status_label = QLabel("\u672a\u4fdd\u5b58")
        self.progress_label = QLabel("\u6279\u91cf\u8fdb\u5ea6: 0/0")
        status_row.addWidget(self.save_status_label)
        status_row.addStretch(1)
        status_row.addWidget(self.progress_label)
        request_layout.addLayout(status_row)

        response_group = QWidget()
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

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top_container)
        splitter.addWidget(response_group)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(splitter, 1)

        self.welcome_panel = QWidget()
        welcome_layout = QVBoxLayout(self.welcome_panel)
        welcome_layout.setContentsMargins(16, 16, 16, 16)
        welcome_layout.addStretch(1)
        welcome_icon = QLabel("\u26a1")
        welcome_icon.setStyleSheet("font-size: 28px; color: #2563eb;")
        welcome_title = QLabel("\u6b22\u8fce\u4f7f\u7528 API \u63a5\u53e3\u6d4b\u8bd5\u5de5\u5177")
        welcome_title.setStyleSheet("font-size: 14pt; font-weight: 600; color: #111827;")
        welcome_hint = QLabel("\u8bf7\u5728\u5de6\u4fa7\u65b0\u589e\u8bf7\u6c42\u6216\u9009\u62e9\u5df2\u6709\u8bf7\u6c42")
        welcome_hint.setStyleSheet("font-size: 10pt; color: #6b7280;")
        welcome_layout.addWidget(welcome_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_title, alignment=Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_hint, alignment=Qt.AlignmentFlag.AlignCenter)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        self.welcome_new_request_button = QPushButton("\u65b0\u5efa\u8bf7\u6c42")
        self.welcome_new_request_button.setObjectName("primaryButton")
        self.welcome_new_folder_button = QPushButton("\u65b0\u5efa\u6587\u4ef6\u5939")
        self.welcome_new_folder_button.setObjectName("secondaryButton")
        button_row.addStretch(1)
        button_row.addWidget(self.welcome_new_request_button)
        button_row.addWidget(self.welcome_new_folder_button)
        button_row.addStretch(1)
        welcome_layout.addLayout(button_row)

        welcome_layout.addStretch(1)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome_panel)
        self.stack.addWidget(content)

        layout.addWidget(self.stack, 1)

    def show_welcome(self) -> None:
        self.stack.setCurrentWidget(self.welcome_panel)

    def show_content(self) -> None:
        self.stack.setCurrentIndex(1)


class RequestPanel(QWidget):
    data_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._run_icon = None
        self._running_icon = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        container_layout.addLayout(self._init_method_url())
        container_layout.addWidget(self._init_tabs(), 1)

    def _init_method_url(self) -> QHBoxLayout:
        name_label = QLabel("\u540d\u79f0")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("\u8bf7\u6c42\u540d\u79f0")
        self.name_input.textChanged.connect(self._emit_changed)

        method_label = QLabel("HTTP Method")
        self.method_combo = QComboBox()
        self.method_combo.addItems(["GET", "POST", "PUT", "DELETE"])
        self.method_combo.currentIndexChanged.connect(self._emit_changed)

        url_label = QLabel("URL")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://api.example.com/resource")
        self.url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.url_input.textChanged.connect(self._emit_changed)

        self.send_button = QToolButton()
        self._run_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self._running_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self.send_button.setIcon(self._run_icon)
        self.send_button.setToolTip("\u53d1\u9001\u8bf7\u6c42\uff08Ctrl + Enter\uff09")
        self.send_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.send_button.setFixedSize(44, 32)
        self.send_button.setStyleSheet(
            "QToolButton { background-color: #2563eb; color: white; border: 1px solid #1d4ed8; border-radius: 6px; }"
            "QToolButton:hover { background-color: #1d4ed8; }"
            "QToolButton:pressed { background-color: #1e40af; }"
            "QToolButton:disabled { background-color: #9ca3af; border-color: #9ca3af; }"
        )
        self.save_button = QToolButton()
        self.save_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_button.setToolTip("\u4fdd\u5b58\u8bf7\u6c42\uff08Ctrl + S\uff09")
        self.save_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.save_button.setFixedSize(32, 32)
        self.save_button.setStyleSheet(
            "QToolButton { background-color: #f8fafc; border: 1px solid #cbd5f5; border-radius: 6px; }"
            "QToolButton:hover { background-color: #e5e7eb; }"
            "QToolButton:pressed { background-color: #e2e8f0; }"
        )

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(name_label)
        row.addWidget(self.name_input, 2)
        row.addWidget(method_label)
        row.addWidget(self.method_combo, 1)
        row.addWidget(url_label)
        row.addWidget(self.url_input, 3)
        row.addWidget(self.send_button)
        row.addWidget(self.save_button)
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
        self.headers_table.itemChanged.connect(self._emit_changed)

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
        self.body_edit.textChanged.connect(self._emit_changed)

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
            "name": self.name_input.text().strip(),
            "method": self.method_combo.currentText(),
            "url": self.url_input.text().strip(),
            "headers": self.get_headers(),
            "body": self.get_body(),
        }

    def set_request_data(self, data: dict) -> None:
        self._loading = True
        name = data.get("name")
        self.name_input.setText(name if isinstance(name, str) else "")
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
        self._loading = False

    def clear_request(self) -> None:
        self._loading = True
        self.name_input.clear()
        self.method_combo.setCurrentText("GET")
        self.url_input.clear()
        self.headers_table.setRowCount(3)
        self.headers_table.clearContents()
        self.body_edit.clear()
        self._loading = False

    def _emit_changed(self) -> None:
        if self._loading:
            return
        self.data_changed.emit()

    def update_run_button_state(self, state: str) -> None:
        if state == "running":
            if self._running_icon is not None:
                self.send_button.setIcon(self._running_icon)
        else:
            if self._run_icon is not None:
                self.send_button.setIcon(self._run_icon)

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

        self.headers_group = CollapsibleSection("Response Headers", collapsed=True)
        self.headers_view = QTextEdit()
        self.headers_view.setReadOnly(True)
        self.headers_view.setPlaceholderText("\u54cd\u5e94\u5934")
        headers_layout = self.headers_group.content_layout()
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
            self.status_value.setStyleSheet(
                "color: #065f46; background: #d1fae5; padding: 2px 6px; border-radius: 6px;"
            )
            self.error_value.setStyleSheet("")
        elif success is False:
            self.status_value.setStyleSheet(
                "color: #9a3412; background: #ffedd5; padding: 2px 6px; border-radius: 6px;"
            )
            self.error_value.setStyleSheet("color: #9a3412;")
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

    def show_running(self) -> None:
        self.update_summary(None, None)
        self.update_status(True)
        self.headers_view.clear()
        self.body_view.setPlainText("\u8bf7\u6c42\u6267\u884c\u4e2d...")
        self.body_view.setVisible(True)
        self.error_view.clear()
        self.error_group.setVisible(False)

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
