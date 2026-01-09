import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.dom import minidom

from PySide6.QtCore import Qt, Signal, QSize, QPoint, QEvent, QTimer
from PySide6.QtGui import QFont, QBrush, QColor, QPixmap, QPainter, QPen, QKeySequence, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QCompleter,
    QGroupBox,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QHeaderView,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QStackedWidget,
    QScrollArea,
    QFileDialog,
    QToolButton,
    QStyle,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QFrame,
)

OPERATOR_LABELS = {
    "contains": "\u5305\u542b",
    "not_contains": "\u4e0d\u5305\u542b",
    "starts_with": "\u5f00\u5934\u4e3a",
    "ends_with": "\u7ed3\u5c3e\u4e3a",
    "matches_regex": "\u6b63\u5219\u5339\u914d",
    "not_null": "\u975e\u7a7a",
    "==": "==",
    "!=": "!=",
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "between": "\u533a\u95f4",
    "exists": "\u5b58\u5728",
    "not_exists": "\u4e0d\u5b58\u5728",
}

TABLE_STYLE = (
    "QTableWidget { background: #f8fafc; gridline-color: #e5e7eb; }"
    "QTableWidget::item { color: #9ca3af; }"
    "QTableWidget::item:selected { background: #eef2f7; color: #111827; }"
    "QTableWidget::item:focus { outline: none; }"
    "QComboBox, QLineEdit, QPlainTextEdit { background: #ffffff; color: #6b7280; "
    "border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 4px; }"
    "QComboBox[activeRow=\"true\"], QLineEdit[activeRow=\"true\"], QPlainTextEdit[activeRow=\"true\"] "
    "{ color: #111827; background: #ffffff; border-color: #93c5fd; }"
    "QSpinBox { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 4px; }"
    "QSpinBox[activeRow=\"true\"] { background: #ffffff; border-color: #93c5fd; }"
)


class CollapsibleSection(QWidget):
    toggled = Signal(bool)
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
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if not collapsed else Qt.ArrowType.UpArrow)
        self._toggle.clicked.connect(self._on_toggled)

        self._actions_widget = QWidget()
        self._actions_layout = QHBoxLayout(self._actions_widget)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(4)
        self._actions_widget.setVisible(False)

        header_layout.addWidget(self._title_label)
        header_layout.addWidget(self._actions_widget)
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

    def add_header_widget(self, widget: QWidget) -> None:
        self._actions_layout.addWidget(widget)
        self._actions_widget.setVisible(self._actions_layout.count() > 0)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def _on_toggled(self, checked: bool) -> None:
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.UpArrow)
        self._content.setVisible(checked)
        self._divider.setVisible(checked)
        self.toggled.emit(checked)

    def eventFilter(self, obj, event) -> bool:
        if obj == self._header and event.type() == event.Type.MouseButtonPress:
            self._on_toggled(not self._content.isVisible())
            return True
        return super().eventFilter(obj, event)


class AssertionResultCard(QFrame):
    def __init__(
        self,
        *,
        title: str,
        status: str,
        summary: str,
        detail_lines: list[str],
        on_click,
        data: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._data = data
        is_fail = status == "FAIL"
        border = "#fecaca" if is_fail else "#e5e7eb"
        background = "#fef2f2" if is_fail else "#f3f4f6"
        self.setStyleSheet(
            "QFrame { background: %s; border: 1px solid %s; border-radius: 6px; }"
            % (background, border)
        )

        header = QFrame()
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 8, 8, 4)
        header_layout.setSpacing(6)

        status_text = "FAIL" if is_fail else "PASS"
        status_color = "#dc2626" if is_fail else "#16a34a"
        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"color: {status_color}; font-weight: 600;")

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #111827; font-weight: 600;")

        header_layout.addWidget(status_label)
        header_layout.addWidget(title_label, 1)

        summary_label = QLabel(summary)
        summary_label.setContentsMargins(8, 0, 8, 0)
        summary_label.setWordWrap(True)
        if is_fail:
            summary_label.setStyleSheet("color: #b91c1c; font-weight: 600;")
        else:
            summary_label.setStyleSheet("color: #6b7280;")
        summary_label.setVisible(bool(summary))

        detail_label = QLabel("\n".join(detail_lines))
        detail_label.setContentsMargins(8, 0, 8, 8)
        detail_label.setWordWrap(True)
        detail_label.setStyleSheet("color: #111827;" if not is_fail else "color: #991b1b;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(header)
        layout.addWidget(summary_label)
        layout.addWidget(detail_label)

        header.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if callable(self._on_click):
                self._on_click(self._data)
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
        self._compact_mode = False
        self._action_buttons: list[QToolButton] = []
        self._history_splitter: QSplitter | None = None
        self._history_cached_height = 180
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

        create_style = (
            "QToolButton { background-color: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; "
            "border-radius: 6px; padding: 4px 8px; }"
            "QToolButton:hover { background-color: #1d4ed8; }"
            "QToolButton:pressed { background-color: #1e40af; }"
            "QToolButton:disabled { background-color: #9ca3af; border-color: #9ca3af; }"
        )
        create_group_style = (
            "QToolButton { background-color: #16a34a; color: #ffffff; border: 1px solid #15803d; "
            "border-radius: 6px; padding: 4px 8px; }"
            "QToolButton:hover { background-color: #15803d; }"
            "QToolButton:pressed { background-color: #166534; }"
            "QToolButton:disabled { background-color: #9ca3af; border-color: #9ca3af; }"
        )
        data_style = (
            "QToolButton { background-color: #f8fafc; color: #374151; border: 1px solid #d1d5db; "
            "border-radius: 6px; padding: 4px 8px; }"
            "QToolButton:hover { background-color: #e5e7eb; border-color: #cbd5e1; }"
            "QToolButton:pressed { background-color: #d1d5db; }"
            "QToolButton:disabled { background-color: #f1f5f9; color: #9ca3af; border-color: #e2e8f0; }"
        )

        self.new_request_button = self._build_action_button(
            "\u65b0\u589e\u7528\u4f8b",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            "\u65b0\u589e\u7528\u4f8b\n\u65b0\u5efa\u5355\u6761 API \u8bf7\u6c42\u7528\u4f8b",
            create_style,
        )
        self.new_request_button.clicked.connect(self._on_add_request_clicked)
        self.new_folder_button = self._build_action_button(
            "\u65b0\u589e\u7528\u4f8b\u96c6",
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
            "\u65b0\u589e\u7528\u4f8b\u96c6\n\u521b\u5efa\u4e00\u4e2a\u7528\u4f8b\u5206\u7ec4\uff08\u6587\u4ef6\u5939\uff09",
            create_group_style,
        )
        self.new_folder_button.clicked.connect(self._on_add_folder_clicked)
        self.import_button = self._build_action_button(
            "\u5bfc\u5165",
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown),
            "\u4ece\u6587\u4ef6\u5bfc\u5165\u7528\u4f8b\uff08JSON / Postman\uff09",
            data_style,
        )
        self.import_button.clicked.connect(self._on_import_clicked)
        self.export_button = self._build_action_button(
            "\u5bfc\u51fa",
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp),
            "\u5bfc\u51fa\u9009\u4e2d\u6216\u5168\u90e8\u7528\u4f8b",
            data_style,
        )
        self.export_button.clicked.connect(self.export_clicked.emit)

        title_actions = QWidget()
        title_actions_layout = QHBoxLayout(title_actions)
        title_actions_layout.setContentsMargins(0, 0, 0, 0)
        title_actions_layout.setSpacing(6)
        title_actions_layout.addWidget(self.import_button)
        title_actions_layout.addWidget(self.export_button)
        title_row.addWidget(title_actions)
        title_row.addWidget(self.run_state_label)
        subtitle_label = QLabel("API Test Cases")
        subtitle_label.setStyleSheet("font-size: 9pt; color: #6b7280;")
        title_layout.addLayout(title_row)
        title_layout.addWidget(subtitle_label)

        actions_block = QWidget()
        actions_layout = QHBoxLayout(actions_block)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        actions_layout.addWidget(self.new_request_button)
        actions_layout.addWidget(self.new_folder_button)
        search_layout.addWidget(actions_block)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setIndentation(18)
        self.tree_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree_widget.setMouseTracking(True)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.tree_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree_widget.itemChanged.connect(self._on_item_changed)
        self.tree_widget.itemEntered.connect(self._on_item_entered)
        self.tree_widget.viewport().installEventFilter(self)
        self.tree_widget.setStyleSheet(
            "QTreeView::item { padding: 6px 8px; }"
            "QTreeView::item:hover { background-color: #eef2f7; }"
            "QTreeView::item:selected { background-color: #dbeafe; color: #111827; }"
            "QTreeView QLineEdit { border: none; background: transparent; padding: 0 2px; }"
        )

        layout.addWidget(title_block)
        layout.addWidget(search_block)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(5)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet("QSplitter::handle { background: #e2e8f0; }")
        splitter.addWidget(self.tree_widget)

        self.history_group = CollapsibleSection("Run History", collapsed=False)
        clear_history_button = QPushButton("\u6e05\u7a7a\u8bb0\u5f55")
        clear_history_button.setObjectName("secondaryButton")
        clear_history_button.setFixedHeight(24)
        clear_history_button.clicked.connect(self._clear_history)
        self.history_group.add_header_widget(clear_history_button)
        self.history_group.toggled.connect(self._on_history_toggled)
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
        splitter.addWidget(self.history_group)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.splitterMoved.connect(self._on_history_splitter_moved)
        self._history_splitter = splitter
        layout.addWidget(splitter, 1)

    def _build_action_button(
        self,
        text: str,
        icon,
        tooltip: str,
        style_sheet: str,
    ) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setIcon(icon)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(14, 14))
        button.setFixedHeight(28)
        button.setStyleSheet(style_sheet)
        self._action_buttons.append(button)
        return button

    def _set_compact_mode(self, compact: bool) -> None:
        if compact == self._compact_mode:
            return
        self._compact_mode = compact
        if compact:
            for button in self._action_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedWidth(28)
            return
        for button in self._action_buttons:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._set_compact_mode(self.width() < 260)

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
        data = self.get_request_data(item)
        if not isinstance(data, dict):
            data = {}
        data["name"] = name
        item.setData(0, self._DATA_ROLE, data)
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
        self._refresh_history_indices()

    def _on_history_clicked(self, item: QListWidgetItem) -> None:
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self.history_selected.emit(record)

    def _clear_history(self) -> None:
        self.history_list.clear()
        self._refresh_history_indices()

    def _refresh_history_indices(self) -> None:
        for row in range(self.history_list.count()):
            item = self.history_list.item(row)
            widget = self.history_list.itemWidget(item)
            if isinstance(widget, HistoryItemWidget):
                widget.set_index(row + 1)

    def _on_history_toggled(self, expanded: bool) -> None:
        splitter = self._history_splitter
        if splitter is None:
            return
        sizes = splitter.sizes()
        if not sizes or len(sizes) < 2:
            return
        if expanded:
            history_height = max(self._history_cached_height, 120)
            available = max(splitter.height() - history_height, 80)
            splitter.setSizes([available, history_height])
        else:
            self._history_cached_height = max(sizes[1], 60)
            total = sizes[0] + sizes[1]
            splitter.setSizes([total, 0])

    def _on_history_splitter_moved(self, _pos: int, _index: int) -> None:
        splitter = self._history_splitter
        if splitter is None:
            return
        sizes = splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self._history_cached_height = sizes[1]

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
        edit: bool = False,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, self._TYPE_ROLE, "folder")
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        item.setData(0, self._NAME_ROLE, name)
        if parent_item is None:
            self.tree_widget.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
            parent_item.setExpanded(True)
        return item

    def _add_request_item(
        self,
        parent_item: QTreeWidgetItem | None,
        name: str,
        *,
        edit: bool = False,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, self._TYPE_ROLE, "request")
        item.setData(0, self._SAVED_ROLE, False)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        item.setData(0, self._NAME_ROLE, name)
        if parent_item is None:
            self.tree_widget.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
            parent_item.setExpanded(True)
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
        base_name = data.get("name")
        if not isinstance(base_name, str) or not base_name:
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
    def __init__(self, record: dict, index: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        status = record.get("status", "-")
        method = record.get("method", "-")
        name = record.get("request_name", "-")
        code = record.get("status_code", "-")
        duration = record.get("duration_ms", "-")
        timestamp = record.get("timestamp", "-")

        self._index_label = QLabel(str(index))
        self._index_label.setStyleSheet("font-size: 10pt; font-weight: 600; color: #0f172a;")
        self._index_label.setFixedWidth(20)
        self._index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

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
        top_row.addWidget(self._index_label)
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

    def set_index(self, index: int) -> None:
        self._index_label.setText(str(index))


class RightPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._assertion_splitter: QSplitter | None = None
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
        status_row.addWidget(self.save_status_label)
        status_row.addStretch(1)
        request_layout.addLayout(status_row)

        self.assertion_panel = self.request_panel.assertion_panel

        response_group = QGroupBox("\u6267\u884c\u7ed3\u679c")
        response_layout = QVBoxLayout(response_group)
        response_layout.setContentsMargins(10, 12, 10, 10)
        response_layout.setSpacing(8)
        result_row = QHBoxLayout()
        result_row.setSpacing(8)
        self.progress_label = QLabel("\u6279\u91cf\u8fdb\u5ea6: 0/0")
        result_row.addStretch(1)
        result_row.addWidget(self.progress_label)
        response_layout.addLayout(result_row)
        self.response_panel = ResponsePanel()
        response_layout.addWidget(self.response_panel, 1)

        request_group.setMinimumHeight(260)
        request_group.setMaximumHeight(660)
        response_group.setMinimumHeight(240)
        response_group.setMaximumHeight(760)

        self._content_splitter = QSplitter(Qt.Orientation.Vertical)
        self._content_splitter.setHandleWidth(5)
        self._content_splitter.setChildrenCollapsible(False)
        self._content_splitter.setStyleSheet(
            "QSplitter::handle { background: #e2e8f0; }"
        )
        self._content_splitter.addWidget(request_group)
        self._content_splitter.addWidget(response_group)
        self._content_splitter.setStretchFactor(0, 4)
        self._content_splitter.setStretchFactor(1, 3)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._content_splitter, 1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(content)

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
        self.stack.addWidget(scroll_area)

        layout.addWidget(self.stack, 1)

    def show_welcome(self) -> None:
        self.stack.setCurrentWidget(self.welcome_panel)

    def show_content(self) -> None:
        self.stack.setCurrentIndex(1)

    def get_ui_state(self) -> dict:
        return {
            "splitter_sizes": self._content_splitter.sizes(),
            "request_panel": self.request_panel.get_ui_state(),
            "response_panel": self.response_panel.get_ui_state(),
        }

    def apply_ui_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        sizes = state.get("splitter_sizes")
        if isinstance(sizes, list) and sizes:
            self._content_splitter.setSizes([int(size) for size in sizes])
        self.request_panel.apply_ui_state(state.get("request_panel", {}))
        self.response_panel.apply_ui_state(state.get("response_panel", {}))


class RequestPanel(QWidget):
    data_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._syncing_from_url = False
        self._syncing_from_params = False
        self._tabs: QTabWidget | None = None
        self._body_tab: QWidget | None = None
        self._run_icon = None
        self._running_icon = None
        self._headers_splitter: QSplitter | None = None
        self._body_stack: QStackedWidget | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        container_layout.addLayout(self._init_method_url())
        container_layout.addWidget(self._init_tabs(), 1)
        self._update_body_tab_state()

    def _init_method_url(self) -> QHBoxLayout:
        name_label = QLabel("\u540d\u79f0")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("\u8bf7\u6c42\u540d\u79f0")
        self.name_input.textChanged.connect(self._emit_changed)

        method_label = QLabel("HTTP \u65b9\u6cd5")
        self.method_combo = QComboBox()
        self.method_combo.addItems(["GET", "POST", "PUT", "DELETE"])
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)

        url_label = QLabel("URL")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://api.example.com/resource")
        self.url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.url_input.textChanged.connect(self._on_url_changed)

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
        self._tabs = QTabWidget()
        self._tabs.addTab(self._init_params(), "Params")
        self._tabs.addTab(self._init_headers(), "\u8bf7\u6c42\u5934")
        self._tabs.addTab(self._init_body(), "\u8bf7\u6c42\u4f53")
        self.assertion_panel = AssertionPanel()
        self._tabs.addTab(self.assertion_panel, "\u65ad\u8a00")
        self.assertion_panel.data_changed.connect(self._emit_changed)
        return self._tabs

    def _init_params(self) -> QWidget:
        params_label = QLabel("Query \u53c2\u6570")
        params_label.setObjectName("sectionTitle")
        add_button = QPushButton("\u65b0\u589e")
        add_button.setObjectName("secondaryButton")
        add_button.clicked.connect(self._add_param_row)
        header_row_widget = QWidget()
        header_row_layout = QHBoxLayout(header_row_widget)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.addWidget(params_label)
        header_row_layout.addStretch(1)
        header_row_layout.addWidget(add_button)
        remove_button = QPushButton("\u5220\u9664")
        remove_button.setObjectName("dangerButton")
        remove_button.clicked.connect(self._remove_param_row)
        header_row_layout.addWidget(remove_button)
        header_row_widget.setFixedHeight(32)

        self.params_table = ParamsTable(self._on_params_changed)
        self.params_table.apply_rows([])
        self.params_table.setMinimumHeight(140)
        self.params_table.setMaximumHeight(360)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(header_row_widget)
        layout.addWidget(self.params_table, 1)
        return panel

    def _init_headers(self) -> QWidget:
        headers_label = QLabel("\u8bf7\u6c42\u5934")
        headers_label.setObjectName("sectionTitle")
        add_button = QPushButton("\u65b0\u589e")
        add_button.setObjectName("secondaryButton")
        remove_button = QPushButton("\u5220\u9664")
        remove_button.setObjectName("dangerButton")
        add_button.clicked.connect(self._add_header_row)
        remove_button.clicked.connect(self._remove_header_row)
        header_row_widget = QWidget()
        header_row_layout = QHBoxLayout(header_row_widget)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.addWidget(headers_label)
        header_row_layout.addStretch(1)
        header_row_layout.addWidget(add_button)
        header_row_layout.addWidget(remove_button)
        header_row_widget.setFixedHeight(32)

        self.headers_table = HeadersTable(self._emit_changed)
        self.headers_table.apply_rows([])
        self.headers_table.setMinimumHeight(140)
        self.headers_table.setMaximumHeight(360)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._headers_splitter = QSplitter(Qt.Orientation.Vertical)
        self._headers_splitter.setHandleWidth(5)
        self._headers_splitter.setChildrenCollapsible(False)
        self._headers_splitter.setStyleSheet("QSplitter::handle { background: #e2e8f0; }")
        self._headers_splitter.addWidget(header_row_widget)
        self._headers_splitter.addWidget(self.headers_table)
        header_row_widget.setMinimumHeight(32)
        self.headers_table.setMinimumHeight(140)
        self._headers_splitter.setStretchFactor(0, 0)
        self._headers_splitter.setStretchFactor(1, 1)
        layout.addWidget(self._headers_splitter)
        return panel

    def _init_body(self) -> QWidget:
        body_label = QLabel("\u8bf7\u6c42\u4f53")
        body_label.setObjectName("sectionTitle")
        self.body_type_combo = QComboBox()
        self.body_type_combo.addItem("JSON", "json")
        self.body_type_combo.addItem("Form", "form")
        self.body_type_combo.addItem("Raw", "raw")
        self.body_type_combo.currentIndexChanged.connect(self._on_body_type_changed)
        self.body_add_button = QPushButton("\u65b0\u589e")
        self.body_add_button.setObjectName("secondaryButton")
        self.body_add_button.clicked.connect(self._add_body_form_row)

        header_row = QHBoxLayout()
        header_row.addWidget(body_label)
        header_row.addStretch(1)
        header_row.addWidget(self.body_type_combo)
        header_row.addWidget(self.body_add_button)

        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("{\n  \"key\": \"value\"\n}")
        self.body_edit.setFont(QFont("Consolas"))
        self.body_edit.textChanged.connect(self._emit_changed)

        self.body_form_table = ParamsTable(self._emit_changed)
        self.body_form_table.setMinimumHeight(140)
        self.body_form_table.setMaximumHeight(360)

        self.body_raw_edit = QTextEdit()
        self.body_raw_edit.setPlaceholderText("\u8bf7\u8f93\u5165\u539f\u59cb\u8bf7\u6c42\u4f53")
        self.body_raw_edit.setFont(QFont("Consolas"))
        self.body_raw_edit.textChanged.connect(self._emit_changed)

        self._body_stack = QStackedWidget()
        self._body_stack.addWidget(self.body_edit)
        self._body_stack.addWidget(self.body_form_table)
        self._body_stack.addWidget(self.body_raw_edit)

        self.body_disabled_hint = QLabel("\u8be5 HTTP \u65b9\u6cd5\u4e0d\u652f\u6301\u8bf7\u6c42\u4f53")
        self.body_disabled_hint.setStyleSheet("color: #9ca3af;")
        self.body_disabled_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_disabled_hint.setVisible(False)
        self.body_add_button.setVisible(self.get_body_type() == "form")

        panel = QWidget()
        self._body_tab = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(header_row)
        layout.addWidget(self._body_stack, 1)
        layout.addWidget(self.body_disabled_hint)
        return panel

    def _on_body_type_changed(self) -> None:
        if self._body_stack is None:
            return
        index = self.body_type_combo.currentIndex()
        self._body_stack.setCurrentIndex(index)
        self.body_add_button.setVisible(self.get_body_type() == "form")
        self._emit_changed()

    def _on_method_changed(self) -> None:
        self._update_body_tab_state()
        self._emit_changed()

    def _update_body_tab_state(self) -> None:
        if self._tabs is None:
            return
        method = self.method_combo.currentText().upper()
        body_index = self._tabs.indexOf(self._body_tab) if self._body_tab is not None else -1
        disabled = method in {"GET", "DELETE"}
        if body_index >= 0:
            self._tabs.setTabEnabled(body_index, not disabled)
        self.body_disabled_hint.setVisible(disabled)
        self.body_edit.setReadOnly(disabled)
        self.body_form_table.setEnabled(not disabled)
        self.body_raw_edit.setReadOnly(disabled)
        self.body_add_button.setEnabled(not disabled)

    def _on_url_changed(self) -> None:
        if self._loading or self._syncing_from_params:
            self._emit_changed()
            return
        self._syncing_from_url = True
        self._sync_params_from_url()
        self._syncing_from_url = False
        self._emit_changed()

    def _on_params_changed(self) -> None:
        if self._loading or self._syncing_from_url:
            self._emit_changed()
            return
        self._syncing_from_params = True
        self._sync_url_from_params()
        self._syncing_from_params = False
        self._emit_changed()

    def get_headers(self) -> dict:
        headers: dict[str, str] = {}
        for row in self.get_header_rows():
            if not row.get("enabled", True):
                continue
            key = row.get("key", "")
            if key:
                headers[key] = row.get("value", "")
        return headers

    def get_header_rows(self) -> list[dict]:
        return self.headers_table.get_rows()

    def get_param_rows(self) -> list[dict]:
        return self.params_table.get_rows()

    def _add_header_row(self) -> None:
        self.headers_table.add_row()

    def _remove_header_row(self) -> None:
        selected = self.headers_table.selectionModel().selectedRows()
        if selected:
            for index in sorted(selected, key=lambda idx: idx.row(), reverse=True):
                self.headers_table.remove_row(index.row())
            return
        row = self.headers_table.rowCount()
        if row > 0:
            self.headers_table.remove_row(row - 1)

    def _add_param_row(self) -> None:
        self.params_table.add_row()

    def _remove_param_row(self) -> None:
        selected = self.params_table.selectionModel().selectedRows()
        if selected:
            for index in sorted(selected, key=lambda idx: idx.row(), reverse=True):
                self.params_table.remove_row(index.row())
            return
        row = self.params_table.rowCount()
        if row > 0:
            self.params_table.remove_row(row - 1)

    def _add_body_form_row(self) -> None:
        self.body_form_table.add_row()

    def get_body(self) -> dict | str:
        body_type = self.body_type_combo.currentData()
        if body_type == "form":
            params = {}
            for row in self.body_form_table.get_rows():
                if not row.get("enabled", True):
                    continue
                key = row.get("key", "")
                if key:
                    params[key] = row.get("value", "")
            return params
        if body_type == "raw":
            return self.body_raw_edit.toPlainText()
        text = self.body_edit.toPlainText()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def get_body_type(self) -> str:
        value = self.body_type_combo.currentData()
        return value if isinstance(value, str) else "json"

    def _build_url_with_params(self) -> str:
        raw_url = self.url_input.text().strip()
        if not raw_url:
            return ""
        split = urlsplit(raw_url)
        base = urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))
        params = []
        for row in self.get_param_rows():
            if not row.get("enabled", True):
                continue
            key = row.get("key", "")
            if key:
                params.append((key, row.get("value", "")))
        query = urlencode(params, doseq=True)
        return urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))

    def get_request_data(self) -> dict:
        params = {}
        for row in self.get_param_rows():
            if not row.get("enabled", True):
                continue
            key = row.get("key", "")
            if key:
                params[key] = row.get("value", "")
        return {
            "name": self.name_input.text().strip(),
            "method": self.method_combo.currentText(),
            "url": self._build_url_with_params(),
            "headers": self.get_headers(),
            "headers_detail": self.get_header_rows(),
            "body": self.get_body(),
            "body_type": self.get_body_type(),
            "params_detail": self.get_param_rows(),
            "params": params,
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

        params_detail = data.get("params_detail")
        params_map = data.get("params")
        if isinstance(params_detail, list):
            self.params_table.apply_rows(params_detail)
            self._sync_url_from_params()
        elif isinstance(params_map, dict):
            rows = [{"enabled": True, "key": key, "value": value} for key, value in params_map.items()]
            self.params_table.apply_rows(rows)
            self._sync_url_from_params()
        else:
            self._sync_params_from_url()

        headers_detail = data.get("headers_detail")
        if isinstance(headers_detail, list):
            self.headers_table.apply_rows(headers_detail)
        else:
            headers = data.get("headers")
            if isinstance(headers, dict):
                rows = [{"enabled": True, "key": key, "value": value, "value_type": "text"} for key, value in headers.items()]
                self.headers_table.apply_rows(rows)
            else:
                self.headers_table.apply_rows([])

        body = data.get("body")
        body_type = data.get("body_type")
        if isinstance(body_type, str):
            index = max(0, self.body_type_combo.findData(body_type))
            self.body_type_combo.setCurrentIndex(index)
        if self.get_body_type() == "form":
            rows = []
            if isinstance(body, dict):
                rows = [{"enabled": True, "key": key, "value": value} for key, value in body.items()]
            self.body_form_table.apply_rows(rows)
            self.body_edit.clear()
            self.body_raw_edit.clear()
        elif self.get_body_type() == "raw":
            self.body_raw_edit.setPlainText("" if body is None else str(body))
            self.body_edit.clear()
        else:
            self.body_form_table.apply_rows([])
        if isinstance(body, (dict, list)):
            self.body_edit.setPlainText(json.dumps(body, indent=2, ensure_ascii=False))
        elif body is None:
            self.body_edit.clear()
        else:
            self.body_edit.setPlainText(str(body))
        self._update_body_tab_state()
        self._loading = False

    def clear_request(self) -> None:
        self._loading = True
        self.name_input.clear()
        self.method_combo.setCurrentText("GET")
        self.url_input.clear()
        self.headers_table.apply_rows([])
        self.params_table.apply_rows([])
        self.body_edit.clear()
        self.body_raw_edit.clear()
        self.body_form_table.apply_rows([])
        self.body_type_combo.setCurrentIndex(0)
        self._update_body_tab_state()
        self._loading = False

    def _emit_changed(self) -> None:
        if self._loading:
            return
        self.data_changed.emit()

    def _sync_params_from_url(self) -> None:
        if not hasattr(self, "params_table"):
            return
        raw_url = self.url_input.text().strip()
        if not raw_url:
            self.params_table.apply_rows([])
            return
        split = urlsplit(raw_url)
        params = {}
        for key, value in parse_qsl(split.query, keep_blank_values=True):
            params[key] = value
        rows = [{"enabled": True, "key": key, "value": value} for key, value in params.items()]
        was_loading = self._loading
        self._loading = True
        self.params_table.apply_rows(rows)
        self._loading = was_loading

    def _sync_url_from_params(self) -> None:
        raw_url = self.url_input.text().strip()
        split = urlsplit(raw_url)
        base = urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))
        params = []
        for row in self.get_param_rows():
            if not row.get("enabled", True):
                continue
            key = row.get("key", "")
            if key:
                params.append((key, row.get("value", "")))
        query = urlencode(params, doseq=True)
        updated = urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))
        if updated == raw_url:
            return
        cursor = self.url_input.cursorPosition()
        self.url_input.setText(updated)
        if self.url_input.hasFocus():
            self.url_input.setCursorPosition(min(cursor, len(updated)))

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

    def get_ui_state(self) -> dict:
        state = {
            "headers_table_columns": self.headers_table.get_column_widths(),
        }
        if self._headers_splitter is not None:
            state["headers_splitter_sizes"] = self._headers_splitter.sizes()
        if hasattr(self, "params_table"):
            state["params_table_columns"] = self.params_table.get_column_widths()
        if hasattr(self, "assertion_panel"):
            state["assertion_panel"] = self.assertion_panel.get_ui_state()
        return state

    def apply_ui_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        widths = state.get("headers_table_columns")
        if isinstance(widths, list) and widths:
            self.headers_table.apply_column_widths(widths)
        sizes = state.get("headers_splitter_sizes")
        if self._headers_splitter is not None and isinstance(sizes, list) and sizes:
            self._headers_splitter.setSizes([int(size) for size in sizes])
        params_widths = state.get("params_table_columns")
        if hasattr(self, "params_table") and isinstance(params_widths, list) and params_widths:
            self.params_table.apply_column_widths(params_widths)
        assertion_state = state.get("assertion_panel")
        if hasattr(self, "assertion_panel") and isinstance(assertion_state, dict):
            self.assertion_panel.apply_ui_state(assertion_state)


class ResponsePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_result: dict | None = None
        self._assertion_results: list[dict] = []
        self._render_version = 0
        self._headers_rendered_version = -1
        self._body_rendered_version = -1
        self._body_mode = "text"
        self._body_mode_user_override = False
        self._json_path_items: dict[str, QTreeWidgetItem] = {}
        self._failed_json_paths: list[str] = []
        self._last_json_error: str | None = None
        self._assertion_fail_count = 0
        self._last_executed_at = "-"
        self._tab_index: dict[str, int] = {}
        self._toast_label: QLabel | None = None
        self._toast_timer = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.result_tabs = QTabWidget()
        self.result_tabs.currentChanged.connect(self._on_tab_changed)

        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(8)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        status_card, self.status_value = self._build_summary_card("\u72b6\u6001\u7801")
        elapsed_card, self.elapsed_value = self._build_summary_card("\u8017\u65f6(ms)")
        time_card, self.time_value = self._build_summary_card("\u6267\u884c\u65f6\u95f4")
        assertion_card, self.assertion_value = self._build_summary_card("\u65ad\u8a00\u7ed3\u679c")
        cards_row.addWidget(status_card, 1)
        cards_row.addWidget(elapsed_card, 1)
        cards_row.addWidget(time_card, 1)
        cards_row.addWidget(assertion_card, 1)

        self.error_group = QGroupBox("\u9519\u8bef\u4fe1\u606f")
        self.error_group.setVisible(False)
        error_layout = QVBoxLayout(self.error_group)
        error_layout.setContentsMargins(10, 10, 10, 10)
        error_layout.setSpacing(6)
        self.error_view = QTextEdit()
        self.error_view.setReadOnly(True)
        self.error_view.setFont(QFont("Consolas"))
        self.error_view.setPlaceholderText("\u9519\u8bef\u4fe1\u606f")
        error_layout.addWidget(self.error_view)

        summary_layout.addLayout(cards_row)
        summary_layout.addWidget(self.error_group)
        summary_layout.addStretch(1)

        headers_tab = QWidget()
        headers_layout = QVBoxLayout(headers_tab)
        headers_layout.setContentsMargins(10, 10, 10, 10)
        headers_layout.setSpacing(6)
        self.headers_table = QTableWidget(0, 2)
        self.headers_table.setHorizontalHeaderLabels(["Key", "Value"])
        header = self.headers_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.headers_table.verticalHeader().setVisible(False)
        self.headers_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.headers_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.headers_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.headers_table.setStyleSheet(
            "QTableWidget { background: #ffffff; gridline-color: #e5e7eb; }"
            "QTableWidget::item:focus { outline: none; }"
        )
        headers_layout.addWidget(self.headers_table, 1)

        body_tab = QWidget()
        self.body_tab = body_tab
        body_layout = QVBoxLayout(body_tab)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(6)

        body_frame = QFrame()
        body_frame.setObjectName("bodyFrame")
        body_frame.setStyleSheet(
            "#bodyFrame { border: 1px solid #e5e7eb; border-radius: 8px; background: #ffffff; }"
        )
        body_frame_layout = QVBoxLayout(body_frame)
        body_frame_layout.setContentsMargins(10, 10, 10, 10)
        body_frame_layout.setSpacing(8)

        body_toolbar = QWidget()
        body_toolbar_layout = QHBoxLayout(body_toolbar)
        body_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        body_toolbar_layout.setSpacing(6)
        self.body_mode_group = QButtonGroup(self)
        self.body_mode_group.setExclusive(True)
        self.body_mode_buttons: dict[str, QToolButton] = {}
        for label, mode in [
            ("JSON", "json"),
            ("Text", "text"),
            ("Raw", "raw"),
            ("XML", "xml"),
            ("HTML", "html"),
            ("Binary", "binary"),
        ]:
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QToolButton { border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 8px; }"
                "QToolButton:checked { background: #e0e7ff; border-color: #93c5fd; }"
                "QToolButton:hover { background: #f8fafc; }"
            )
            button.clicked.connect(lambda _checked, m=mode: self._on_body_mode_selected(m))
            self.body_mode_group.addButton(button)
            self.body_mode_buttons[mode] = button
            body_toolbar_layout.addWidget(button)
        body_toolbar_layout.addStretch(1)
        self.body_search_input = QLineEdit()
        self.body_search_input.setPlaceholderText("\u641c\u7d22 JSON")
        self.body_search_input.setFixedWidth(160)
        self.body_search_input.textChanged.connect(self._apply_json_search)
        self.body_search_input.setVisible(False)
        body_toolbar_layout.addWidget(self.body_search_input, alignment=Qt.AlignmentFlag.AlignRight)
        self.body_copy_button = QToolButton()
        self.body_copy_button.setText("\u590d\u5236")
        self.body_copy_button.setAutoRaise(True)
        self.body_copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.body_copy_button.clicked.connect(self._copy_body_text)
        body_toolbar_layout.addWidget(self.body_copy_button)

        self._init_toast()

        jsonpath_row = QWidget()
        jsonpath_layout = QHBoxLayout(jsonpath_row)
        jsonpath_layout.setContentsMargins(0, 0, 0, 0)
        jsonpath_layout.setSpacing(6)
        self.jsonpath_label = QLabel("\u9009\u4e2d\u5b57\u6bb5\u7684 JSONPath")
        self.jsonpath_label.setStyleSheet("color: #6b7280;")
        self.jsonpath_copy_button = QToolButton()
        self.jsonpath_copy_button.setText("\u590d\u5236")
        self.jsonpath_copy_button.clicked.connect(self._copy_jsonpath)
        jsonpath_layout.addWidget(self.jsonpath_label, 1)
        jsonpath_layout.addWidget(self.jsonpath_copy_button)
        self.jsonpath_row = jsonpath_row

        self.body_stack = QStackedWidget()
        self.body_text = QPlainTextEdit()
        self.body_text.setReadOnly(True)
        self.body_text.setPlaceholderText("\u54cd\u5e94\u4f53")
        self.body_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.body_text.setFont(QFont("Consolas"))

        self.body_raw = QPlainTextEdit()
        self.body_raw.setReadOnly(True)
        self.body_raw.setPlaceholderText("\u539f\u59cb\u54cd\u5e94")
        self.body_raw.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.body_raw.setFont(QFont("Consolas"))

        self.body_xml = QPlainTextEdit()
        self.body_xml.setReadOnly(True)
        self.body_xml.setPlaceholderText("XML \u89e3\u6790\u5931\u8d25")
        self.body_xml.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.body_xml.setFont(QFont("Consolas"))

        self.body_html = QPlainTextEdit()
        self.body_html.setReadOnly(True)
        self.body_html.setPlaceholderText("HTML \u6e90\u7801")
        self.body_html.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.body_html.setFont(QFont("Consolas"))

        self.body_tree = QTreeWidget()
        self.body_tree.setHeaderLabels(["Key", "Value"])
        self.body_tree.setHeaderHidden(False)
        self.body_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.body_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.body_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.body_tree.itemSelectionChanged.connect(self._on_json_item_selected)
        self.body_tree.installEventFilter(self)

        self.body_binary = QWidget()
        binary_layout = QVBoxLayout(self.body_binary)
        binary_layout.setContentsMargins(10, 10, 10, 10)
        binary_layout.setSpacing(6)
        self.binary_summary = QLabel("\u672a\u68c0\u6d4b\u5230\u4e8c\u8fdb\u5236\u6570\u636e")
        self.binary_summary.setStyleSheet("color: #6b7280;")
        self.binary_save_button = QPushButton("\u4fdd\u5b58\u4e3a\u6587\u4ef6")
        self.binary_save_button.clicked.connect(self._save_binary)
        self.binary_copy_button = QPushButton("\u590d\u5236 Base64")
        self.binary_copy_button.clicked.connect(self._copy_binary_base64)
        binary_actions = QHBoxLayout()
        binary_actions.addWidget(self.binary_save_button)
        binary_actions.addWidget(self.binary_copy_button)
        binary_actions.addStretch(1)
        binary_layout.addWidget(self.binary_summary)
        binary_layout.addLayout(binary_actions)
        binary_layout.addStretch(1)

        self.body_stack.addWidget(self.body_tree)
        self.body_stack.addWidget(self.body_text)
        self.body_stack.addWidget(self.body_raw)
        self.body_stack.addWidget(self.body_xml)
        self.body_stack.addWidget(self.body_html)
        self.body_stack.addWidget(self.body_binary)

        body_frame_layout.addWidget(body_toolbar)
        body_frame_layout.addWidget(self.jsonpath_row)
        body_frame_layout.addWidget(self.body_stack, 1)
        body_layout.addWidget(body_frame, 1)
        body_tab.installEventFilter(self)
        self.body_text.installEventFilter(self)
        self.body_raw.installEventFilter(self)
        self.body_xml.installEventFilter(self)
        self.body_html.installEventFilter(self)

        assertions_tab = QWidget()
        assertions_layout = QVBoxLayout(assertions_tab)
        assertions_layout.setContentsMargins(10, 10, 10, 10)
        assertions_layout.setSpacing(6)
        self.assertion_scroll = QScrollArea()
        self.assertion_scroll.setWidgetResizable(True)
        self.assertion_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.assertion_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertion_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.assertion_container = QWidget()
        self.assertion_container_layout = QVBoxLayout(self.assertion_container)
        self.assertion_container_layout.setContentsMargins(0, 0, 0, 0)
        self.assertion_container_layout.setSpacing(8)
        self.assertion_container_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.assertion_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.assertion_scroll.setWidget(self.assertion_container)
        assertions_layout.addWidget(self.assertion_scroll, 1)

        self._tab_index = {
            "summary": 0,
            "assertions": 1,
            "body": 2,
            "headers": 3,
            "logs": 4,
        }
        self.result_tabs.addTab(summary_tab, "\u6982\u89c8")
        self.result_tabs.addTab(assertions_tab, "\u65ad\u8a00\u7ed3\u679c")
        self.result_tabs.addTab(body_tab, "\u54cd\u5e94\u4f53")
        self.result_tabs.addTab(headers_tab, "\u54cd\u5e94\u5934")

        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(10, 10, 10, 10)
        logs_layout.setSpacing(6)
        self.logs_view = QPlainTextEdit()
        self.logs_view.setReadOnly(True)
        self.logs_view.setPlaceholderText("\u65e0\u65e5\u5fd7")
        self.logs_view.setFont(QFont("Consolas"))
        logs_layout.addWidget(self.logs_view, 1)
        self.result_tabs.addTab(logs_tab, "\u65e5\u5fd7")

        self.result_tabs.setCurrentIndex(self._tab_index["summary"])

        layout.addWidget(self.result_tabs, 1)

    def _build_summary_card(self, title: str) -> tuple[QWidget, QLabel]:
        card = QFrame()
        card.setStyleSheet("QFrame { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #6b7280; font-size: 9pt;")
        value_label = QLabel("-")
        value_label.setStyleSheet("color: #111827; font-weight: 600;")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card, value_label

    def update_response(self, result: dict) -> None:
        self._last_result = result
        self._render_version += 1
        executed_at = datetime.now().strftime("%H:%M:%S")
        self._last_executed_at = executed_at
        success = result.get("success")
        status_code = result.get("status_code")
        elapsed_ms = result.get("elapsed_ms")
        error_type = result.get("error_type")
        error_message = result.get("error_message")

        self.status_value.setText("-" if status_code is None else str(status_code))
        self.elapsed_value.setText("-" if elapsed_ms is None else str(elapsed_ms))
        self.time_value.setText(executed_at)
        self._apply_status_style(success)
        self._update_assertion_summary()

        if success is False:
            self.error_group.setVisible(True)
            self.error_view.setPlainText(f"{error_type}\n{error_message}".strip())
        else:
            self.error_group.setVisible(False)
            self.error_view.clear()

        self._headers_rendered_version = -1
        self._body_rendered_version = -1
        self._body_mode_user_override = False
        self._failed_json_paths = []
        self._clear_json_highlights()
        self.jsonpath_label.setText("\u9009\u4e2d\u5b57\u6bb5\u7684 JSONPath")
        default_mode = self._choose_default_body_mode(result)
        self._set_body_mode(default_mode, user_initiated=False)
        self._update_logs(executed_at)
        self._reset_assertion_tab()
        self.result_tabs.setCurrentIndex(self._tab_index["summary"])
        self._on_tab_changed(self.result_tabs.currentIndex())

    def update_assertion_results(self, results: list[dict]) -> None:
        self._assertion_results = results or []
        self._update_assertion_summary()
        self._failed_json_paths = [
            item.get("path")
            for item in self._assertion_results
            if item.get("result") == "FAIL" and item.get("type") == "json_path" and item.get("path")
        ]
        self._update_assertion_tab_badge()
        if self._assertion_results:
            if self._assertion_fail_count > 0:
                self.append_log(f"assertions_failed={self._assertion_fail_count}")
            else:
                self.append_log("assertions_all_passed")
        if self._assertion_fail_count > 0:
            self.result_tabs.setCurrentIndex(self._tab_index["assertions"])
        if self.result_tabs.currentIndex() == self._tab_index["assertions"]:
            self._render_assertions()
        self._update_logs(self._last_executed_at)
        if self.result_tabs.currentIndex() == self._tab_index["logs"]:
            self._update_logs(self._last_executed_at)

    def clear_assertion_results(self) -> None:
        self._assertion_results = []
        self._clear_assertion_items()
        self._update_assertion_summary()
        self._failed_json_paths = []
        self._assertion_fail_count = 0
        self._update_assertion_tab_badge()

    def show_running(self) -> None:
        self._last_result = {}
        self._render_version += 1
        self.status_value.setText("-")
        self.elapsed_value.setText("-")
        self.time_value.setText("-")
        self._apply_status_style(None)
        self.error_group.setVisible(False)
        self.error_view.clear()
        self.body_text.setPlainText("\u8bf7\u6c42\u6267\u884c\u4e2d...")
        self.body_stack.setCurrentWidget(self.body_text)
        self._body_mode_user_override = False
        self._set_body_mode("text", user_initiated=False)
        self.body_search_input.clear()
        self.logs_view.setPlainText("\u8bf7\u6c42\u6267\u884c\u4e2d...")
        self._reset_assertion_tab()

    def clear(self) -> None:
        self._last_result = None
        self._render_version += 1
        self.status_value.setText("-")
        self.elapsed_value.setText("-")
        self.time_value.setText("-")
        self._apply_status_style(None)
        self.error_group.setVisible(False)
        self.error_view.clear()
        self.headers_table.setRowCount(0)
        self.body_text.clear()
        self.body_tree.clear()
        self._clear_assertion_items()
        self._assertion_results = []
        self._body_mode_user_override = False
        self._set_body_mode("text", user_initiated=False)
        self.body_search_input.clear()
        self.logs_view.clear()
        self._reset_assertion_tab()

    def _apply_status_style(self, success: bool | None) -> None:
        if success is True:
            self.status_value.setStyleSheet(
                "color: #065f46; background: #d1fae5; padding: 2px 6px; border-radius: 6px;"
            )
        elif success is False:
            self.status_value.setStyleSheet(
                "color: #9a3412; background: #ffedd5; padding: 2px 6px; border-radius: 6px;"
            )
        else:
            self.status_value.setStyleSheet("color: #111827; font-weight: 600;")

    def _choose_default_body_mode(self, result: dict) -> str:
        headers = result.get("headers") or {}
        content_type = str(headers.get("Content-Type", headers.get("content-type", ""))).lower()
        if "application/json" in content_type:
            return "json"
        if "application/xml" in content_type or "text/xml" in content_type:
            return "xml"
        if "text/html" in content_type:
            return "html"
        if "application/octet-stream" in content_type or content_type.startswith("image/"):
            return "binary"
        if result.get("response_json") is not None:
            return "json"
        return "text"

    def _on_body_mode_selected(self, mode: str) -> None:
        self._body_mode_user_override = True
        self._set_body_mode(mode, user_initiated=True)

    def _set_body_mode(self, mode: str, *, user_initiated: bool) -> None:
        self._body_mode = mode
        for key, button in self.body_mode_buttons.items():
            button.setChecked(key == mode)
        is_json = mode == "json"
        self.jsonpath_row.setVisible(is_json)
        self.body_search_input.setVisible(is_json)
        if user_initiated:
            self._body_mode_user_override = True
        if self.result_tabs.currentIndex() == self._tab_index.get("body"):
            self._render_body()

    def _copy_body_text(self) -> None:
        text = ""
        if self._body_mode == "raw":
            text = self.body_raw.toPlainText()
        elif self._body_mode in {"xml", "html"}:
            text = self.body_xml.toPlainText() if self._body_mode == "xml" else self.body_html.toPlainText()
        elif self._body_mode == "text":
            text = self.body_text.toPlainText()
        elif self._body_mode == "json":
            text = self.body_text.toPlainText()
        QApplication.clipboard().setText(text)
        self._show_toast("\u590d\u5236\u6210\u529f")

    def _copy_jsonpath(self) -> None:
        path = self.jsonpath_label.text().replace("JSONPath: ", "").strip()
        if path:
            QApplication.clipboard().setText(path)
            self._show_toast("\u590d\u5236\u6210\u529f")

    def _apply_json_search(self, text: str) -> None:
        if self._body_mode != "json":
            return
        query = text.strip().lower()
        self._clear_json_highlights()
        if not query:
            return
        for item in self._iter_json_items():
            key = item.text(0).lower()
            value = item.text(1).lower()
            if query in key or query in value:
                item.setBackground(0, QBrush(QColor("#fde68a")))
                item.setBackground(1, QBrush(QColor("#fde68a")))

    def _clear_json_highlights(self) -> None:
        for item in self._iter_json_items():
            item.setBackground(0, QBrush(Qt.GlobalColor.transparent))
            item.setBackground(1, QBrush(Qt.GlobalColor.transparent))

    def _on_json_item_selected(self) -> None:
        items = self.body_tree.selectedItems()
        if not items:
            return
        path = items[0].data(0, Qt.ItemDataRole.UserRole)
        if isinstance(path, str) and path:
            self.jsonpath_label.setText(f"JSONPath: {path}")

    def _highlight_json_path(self, path: str) -> None:
        if not path:
            return
        item = self._json_path_items.get(path)
        if item is None:
            return
        self._clear_json_highlights()
        item.setBackground(0, QBrush(QColor("#fee2e2")))
        item.setBackground(1, QBrush(QColor("#fee2e2")))
        self.body_tree.setCurrentItem(item)
        self.body_tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
        self.jsonpath_label.setText(f"JSONPath: {path}")

    def _update_assertion_summary(self) -> None:
        if not self._assertion_results:
            self.assertion_value.setText("\u65e0\u65ad\u8a00")
            self.assertion_value.setStyleSheet("color: #6b7280; font-weight: 600;")
            return
        self._assertion_fail_count = sum(
            1 for item in self._assertion_results if item.get("result") == "FAIL"
        )
        has_fail = self._assertion_fail_count > 0
        if has_fail:
            self.assertion_value.setText(f"\u2716 {self._assertion_fail_count} \u6761\u5931\u8d25")
            self.assertion_value.setStyleSheet("color: #dc2626; font-weight: 600;")
        else:
            self.assertion_value.setText("\u2714 \u5168\u90e8\u901a\u8fc7")
            self.assertion_value.setStyleSheet("color: #16a34a; font-weight: 600;")

    def _update_assertion_tab_badge(self) -> None:
        text = "\u65ad\u8a00\u7ed3\u679c"
        if self._assertion_fail_count > 0:
            text = f"\u65ad\u8a00\u7ed3\u679c ({self._assertion_fail_count})"
        index = self._tab_index.get("assertions", 1)
        self.result_tabs.setTabText(index, text)
        color = QColor("#dc2626") if self._assertion_fail_count > 0 else QColor("#374151")
        self.result_tabs.tabBar().setTabTextColor(index, color)

    def _reset_assertion_tab(self) -> None:
        self._assertion_fail_count = 0
        self._update_assertion_tab_badge()

    def _on_tab_changed(self, index: int) -> None:
        if index == self._tab_index.get("headers"):
            self._render_headers()
        elif index == self._tab_index.get("body"):
            self._render_body()
        elif index == self._tab_index.get("assertions"):
            self._render_assertions()

    def _render_headers(self) -> None:
        if self._last_result is None:
            self.headers_table.setRowCount(0)
            return
        if self._headers_rendered_version == self._render_version:
            return
        headers = self._last_result.get("headers") or {}
        self.headers_table.setRowCount(0)
        for key, value in headers.items():
            row = self.headers_table.rowCount()
            self.headers_table.insertRow(row)
            self.headers_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.headers_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self._headers_rendered_version = self._render_version

    def _render_body(self) -> None:
        if self._last_result is None:
            self.body_text.clear()
            self.body_raw.clear()
            self.body_xml.clear()
            self.body_html.clear()
            self.body_tree.clear()
            return
        response_json = self._last_result.get("response_json")
        response_text = self._last_result.get("response_text") or ""
        headers = self._last_result.get("headers") or {}
        content_type = str(headers.get("Content-Type", headers.get("content-type", ""))).lower()
        self._last_json_error = None
        if response_json is None and "application/json" in content_type:
            try:
                response_json = json.loads(response_text)
            except Exception as exc:
                self._last_json_error = str(exc)
                response_json = None

        mode = self._body_mode
        if mode == "json":
            if response_json is None:
                self.body_text.setPlainText("\u65e0\u6cd5\u89e3\u6790 JSON" + (f": {self._last_json_error}" if self._last_json_error else ""))
                self.body_stack.setCurrentWidget(self.body_text)
            else:
                self._render_json_tree(response_json)
                self.body_stack.setCurrentWidget(self.body_tree)
        elif mode == "raw":
            self.body_raw.setPlainText(response_text)
            self.body_stack.setCurrentWidget(self.body_raw)
        elif mode == "xml":
            xml_text = response_text
            if "xml" in content_type or response_text.strip().startswith("<"):
                try:
                    parsed = minidom.parseString(response_text)
                    xml_text = parsed.toprettyxml(indent="  ")
                except Exception as exc:
                    xml_text = f"XML \u89e3\u6790\u5931\u8d25: {exc}\n\n{response_text}"
            self.body_xml.setPlainText(xml_text)
            self.body_stack.setCurrentWidget(self.body_xml)
        elif mode == "html":
            self.body_html.setPlainText(response_text)
            self.body_stack.setCurrentWidget(self.body_html)
        elif mode == "binary":
            self._render_binary(headers, response_text)
            self.body_stack.setCurrentWidget(self.body_binary)
        else:
            self.body_text.setPlainText(response_text)
            self.body_stack.setCurrentWidget(self.body_text)
        self._body_rendered_version = self._render_version

    def _render_json_tree(self, data) -> None:
        self.body_tree.clear()
        self._json_path_items.clear()
        try:
            self.body_text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            self.body_text.clear()
        root = QTreeWidgetItem(["$", ""])
        root.setData(0, Qt.ItemDataRole.UserRole, "$")
        self.body_tree.addTopLevelItem(root)
        self._json_path_items["$"] = root

        def add_item(parent, key, value, path):
            display_value = "" if isinstance(value, (dict, list)) else str(value)
            item = QTreeWidgetItem([str(key), display_value])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            parent.addChild(item)
            self._json_path_items[path] = item
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    add_item(item, child_key, child_value, f"{path}.{child_key}")
            elif isinstance(value, list):
                for idx, child_value in enumerate(value):
                    add_item(item, f"[{idx}]", child_value, f"{path}[{idx}]")

        if isinstance(data, dict):
            for key, value in data.items():
                add_item(root, key, value, f"$.{key}")
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                add_item(root, f"[{idx}]", value, f"$[{idx}]")
        else:
            add_item(root, "value", data, "$.value")
        self.jsonpath_label.setText("JSONPath: $")
        self.body_tree.expandToDepth(1)
        if self._failed_json_paths:
            self._highlight_json_path(self._failed_json_paths[0])

    def _render_assertions(self) -> None:
        self._clear_assertion_items()
        ordered = sorted(
            self._assertion_results,
            key=lambda item: 0 if item.get("result") == "FAIL" else 1,
        )
        for item in ordered:
            widget = self._build_assertion_item(item)
            self.assertion_container_layout.addWidget(widget)
        self.assertion_container_layout.addStretch(1)
        self.assertion_container.setMinimumHeight(self.assertion_container_layout.sizeHint().height())

    def _on_assertion_clicked(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        self.result_tabs.setCurrentIndex(self._tab_index["body"])
        path = data.get("path")
        if data.get("type") == "json_path" and path:
            self._set_body_mode("json", user_initiated=False)
            self._highlight_json_path(path)

    def _clear_assertion_items(self) -> None:
        layout = getattr(self, "assertion_container_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()



    def _iter_json_items(self):
        stack = []
        root = self.body_tree.invisibleRootItem()
        for i in range(root.childCount()):
            stack.append(root.child(i))
        while stack:
            item = stack.pop()
            yield item
            for i in range(item.childCount()):
                stack.append(item.child(i))

    def _render_binary(self, headers: dict, response_text: str) -> None:
        content_type = str(headers.get("Content-Type", headers.get("content-type", "")) or "-")
        length = headers.get("Content-Length") or headers.get("content-length") or str(len(response_text.encode("utf-8")))
        self.binary_summary.setText(
            f"Content-Type: {content_type}\nContent-Length: {length}"
        )

    def _update_logs(self, executed_at: str) -> None:
        if self._last_result is None:
            self.logs_view.clear()
            return
        status = self._last_result.get("status_code")
        elapsed = self._last_result.get("elapsed_ms")
        error_type = self._last_result.get("error_type")
        error_message = self._last_result.get("error_message")
        request_headers = self._last_result.get("request_headers") or {}
        log_lines = [
            f"[{executed_at}] Request finished",
            f"status_code={status} elapsed_ms={elapsed}",
        ]
        if isinstance(request_headers, dict) and request_headers:
            log_lines.append(f"request_headers={json.dumps(request_headers, ensure_ascii=False)}")
        if error_type or error_message:
            log_lines.append(f"error={error_type} {error_message}".strip())
        if self._assertion_results:
            fail_count = sum(1 for item in self._assertion_results if item.get("result") == "FAIL")
            log_lines.append(f"assertions_total={len(self._assertion_results)} fail={fail_count}")
        self.logs_view.setPlainText("\n".join(log_lines))

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        current = self.logs_view.toPlainText()
        line = f"[{timestamp}] {message}"
        if current:
            self.logs_view.setPlainText(f"{current}\n{line}")
        else:
            self.logs_view.setPlainText(line)
        logging.getLogger("requesttool").info(message)

    def _save_binary(self) -> None:
        if self._last_result is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "\u4fdd\u5b58\u4e3a\u6587\u4ef6", "", "All Files (*)")
        if not file_path:
            return
        data = (self._last_result.get("response_text") or "").encode("utf-8", errors="replace")
        try:
            Path(file_path).write_bytes(data)
        except Exception:
            return
        self._show_toast("\u4fdd\u5b58\u6210\u529f")

    def _copy_binary_base64(self) -> None:
        if self._last_result is None:
            return
        data = (self._last_result.get("response_text") or "").encode("utf-8", errors="replace")
        encoded = base64.b64encode(data).decode("ascii")
        QApplication.clipboard().setText(encoded)
        self._show_toast("\u590d\u5236\u6210\u529f")

    def _init_toast(self) -> None:
        self._toast_label = QLabel(self.result_tabs)
        self._toast_label.setStyleSheet(
            "QLabel { background: #ecfdf3; color: #16a34a; border: 1px solid #86efac; "
            "border-radius: 6px; padding: 6px 10px; }"
        )
        self._toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)

    def _show_toast(self, message: str) -> None:
        if self._toast_label is None:
            return
        self._toast_label.setText(message)
        self._toast_label.adjustSize()
        container = self.result_tabs
        x = int((container.width() - self._toast_label.width()) / 2)
        y = int((container.height() - self._toast_label.height()) / 2)
        self._toast_label.move(max(x, 0), max(y, 0))
        self._toast_label.show()
        self._toast_label.raise_()
        if self._toast_timer is not None:
            self._toast_timer.start(1400)

    def _build_assertion_item(self, item: dict) -> QWidget:
        assertion_type = str(item.get("type", ""))
        result_value = str(item.get("result", ""))
        expected = item.get("expected")
        actual = item.get("actual")
        message = item.get("message", "")
        operator = item.get("operator")
        target = item.get("path") or item.get("header") or item.get("target")

        title_text = self._format_assertion_title(item)
        expected_text = self._format_value(expected)
        actual_text = self._format_value(actual)
        summary = ""
        if result_value == "FAIL":
            summary = f"\u671f\u671b\uff1a{expected_text} \uff5c \u5b9e\u9645\uff1a{actual_text}"

        detail_lines = [
            f"\u7c7b\u578b\uff1a{self._format_assertion_type(assertion_type)}",
        ]
        if target:
            detail_lines.append(f"\u76ee\u6807\uff1a{target}")
        if operator:
            detail_lines.append(f"\u64cd\u4f5c\u7b26\uff1a{self._get_operator_label(operator)}")
        detail_lines.append(f"\u671f\u671b\u503c\uff1a{expected_text}")
        detail_lines.append(f"\u5b9e\u9645\u503c\uff1a{actual_text}")
        if message:
            detail_lines.append(f"\u539f\u56e0\uff1a{message}")

        widget = AssertionResultCard(
            title=title_text,
            status=result_value,
            summary=summary,
            detail_lines=detail_lines,
            on_click=self._on_assertion_clicked,
            data=item,
        )
        return widget

    def _format_assertion_title(self, item: dict) -> str:
        mapping = {
            "status_code": "\u72b6\u6001\u7801\u65ad\u8a00",
            "response_body": "\u54cd\u5e94\u4f53\u65ad\u8a00",
            "json_path": "JSONPath \u65ad\u8a00",
            "header": "\u54cd\u5e94\u5934\u65ad\u8a00",
            "response_time": "\u8017\u65f6\u65ad\u8a00",
        }
        assertion_type = str(item.get("type", ""))
        title = mapping.get(assertion_type, "\u65ad\u8a00")
        target = item.get("path") or item.get("header") or item.get("target")
        if target:
            return f"{title} / {target}"
        return title

    def _format_value(self, value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _format_assertion_type(self, assertion_type: str) -> str:
        mapping = {
            "status_code": "\u72b6\u6001\u7801\u65ad\u8a00",
            "response_body": "\u54cd\u5e94\u4f53\u65ad\u8a00",
            "json_path": "JSONPath \u65ad\u8a00",
            "header": "\u54cd\u5e94\u5934\u65ad\u8a00",
            "response_time": "\u8017\u65f6\u65ad\u8a00",
        }
        return mapping.get(assertion_type, "\u65ad\u8a00")

    def _get_operator_label(self, operator: str | None) -> str:
        if not operator:
            return ""
        return OPERATOR_LABELS.get(operator, operator)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.matches(QKeySequence.StandardKey.Find):
            self.body_search_input.setFocus()
            self.body_search_input.selectAll()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._toast_label is not None and self._toast_label.isVisible():
            container = self.result_tabs
            x = int((container.width() - self._toast_label.width()) / 2)
            y = int((container.height() - self._toast_label.height()) / 2)
            self._toast_label.move(max(x, 0), max(y, 0))

    def get_ui_state(self) -> dict:
        return {}

    def apply_ui_state(self, state: dict) -> None:
        return


class ParamsTable(QTableWidget):
    def __init__(self, on_changed, parent: QWidget | None = None) -> None:
        super().__init__(0, 3, parent)
        self._on_changed = on_changed
        self._active_row = -1
        self._resizing = False
        self._column_constraints = {0: (48, 70)}
        self.setHorizontalHeaderLabels(["\u542f\u7528", "\u53c2\u6570\u540d", "\u503c"])
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionResized.connect(self._on_header_resized)
        header.setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(TABLE_STYLE)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.itemChanged.connect(self._notify_changed)
        self.currentCellChanged.connect(self._on_current_cell_changed)
        self.viewport().installEventFilter(self)
        self._apply_default_column_widths()

    def add_row(self, data: dict | None = None) -> None:
        row = self.rowCount()
        self.insertRow(row)
        self._setup_row(row, data or {})

    def remove_row(self, row: int) -> None:
        if row < 0:
            return
        self.removeRow(row)
        if self.rowCount() == 0:
            self.add_row()

    def get_rows(self) -> list[dict]:
        rows: list[dict] = []
        for row in range(self.rowCount()):
            enabled_item = self.item(row, 0)
            enabled = enabled_item is not None and enabled_item.checkState() == Qt.CheckState.Checked
            key = self._get_key(row)
            value = self._get_value(row)
            if not any([key, value]):
                continue
            rows.append(
                {
                    "enabled": enabled,
                    "key": key,
                    "value": value,
                }
            )
        return rows

    def apply_rows(self, rows: list[dict]) -> None:
        self.setRowCount(0)
        if not rows:
            for _ in range(3):
                self.add_row()
            return
        for row in rows:
            self.add_row(row)

    def get_column_widths(self) -> list[int]:
        return [self.columnWidth(idx) for idx in range(self.columnCount())]

    def apply_column_widths(self, widths: list[int]) -> None:
        header = self.horizontalHeader()
        for idx in range(min(len(widths), self.columnCount())):
            header.resizeSection(idx, self._clamp_width(idx, int(widths[idx])))

    def _apply_default_column_widths(self) -> None:
        defaults = [56, 240, 360]
        header = self.horizontalHeader()
        for idx, width in enumerate(defaults):
            header.resizeSection(idx, self._clamp_width(idx, width))

    def _clamp_width(self, column: int, width: int) -> int:
        bounds = self._column_constraints.get(column)
        if not bounds:
            return width
        minimum, maximum = bounds
        return max(minimum, min(maximum, width))

    def _on_header_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if self._resizing:
            return
        bounds = self._column_constraints.get(logical_index)
        if not bounds:
            return
        minimum, maximum = bounds
        if minimum <= new_size <= maximum:
            return
        self._resizing = True
        self.horizontalHeader().resizeSection(logical_index, self._clamp_width(logical_index, new_size))
        self._resizing = False

    def _on_current_cell_changed(self, row: int, _column: int, previous_row: int, _previous_col: int) -> None:
        if previous_row != row:
            self._apply_row_state(previous_row, False)
        self._apply_row_state(row, True)

    def _apply_row_state(self, row: int, active: bool) -> None:
        if row < 0 or row >= self.rowCount():
            return
        enabled_item = self.item(row, 0)
        enabled = enabled_item is not None and enabled_item.checkState() == Qt.CheckState.Checked
        for col in range(self.columnCount()):
            widget = self.cellWidget(row, col)
            if widget is not None:
                widget.setProperty("activeRow", active and enabled)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                line_edit = widget.findChild(QLineEdit)
                if line_edit is not None:
                    line_edit.setProperty("activeRow", active and enabled)
                    line_edit.style().unpolish(line_edit)
                    line_edit.style().polish(line_edit)
        item = self.item(row, 0)
        if item is not None:
            if enabled:
                item.setForeground(QBrush(QColor("#111827" if active else "#9ca3af")))
            else:
                item.setForeground(QBrush(QColor("#9ca3af")))
            item.setBackground(QBrush(Qt.GlobalColor.transparent))

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            if self._handle_paste():
                return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            if key_event.matches(QKeySequence.StandardKey.Paste):
                if self._handle_paste():
                    return True
        return super().eventFilter(obj, event)

    def _handle_paste(self) -> bool:
        text = QApplication.clipboard().text()
        if not text:
            return False
        entries = []
        stripped = text.strip()
        if "&" in stripped and "=" in stripped:
            for key, value in parse_qsl(stripped, keep_blank_values=True):
                if key:
                    entries.append((key, value))
        else:
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                elif ":" in line:
                    key, value = line.split(":", 1)
                else:
                    continue
                key = key.strip()
                value = value.strip()
                if key:
                    entries.append((key, value))
        if not entries:
            return False
        existing = {}
        for row in range(self.rowCount()):
            key = self._get_key(row)
            if key:
                existing[key.lower()] = row
        for key, value in entries:
            lower_key = key.lower()
            row = existing.get(lower_key)
            if row is None:
                row = self.rowCount()
                self.add_row({"key": key, "value": value})
                existing[lower_key] = row
            else:
                self._set_row_value(row, key, value, enabled=True)
        self._notify_changed()
        return True

    def _setup_row(self, row: int, data: dict) -> None:
        enabled_item = QTableWidgetItem("")
        enabled_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
        )
        enabled_item.setCheckState(
            Qt.CheckState.Checked if data.get("enabled", True) else Qt.CheckState.Unchecked
        )
        self.setItem(row, 0, enabled_item)

        key_input = QLineEdit()
        key_input.setText(str(data.get("key", "")))
        key_input.setFixedHeight(28)
        key_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        key_input.textChanged.connect(self._notify_changed)
        self.setCellWidget(row, 1, key_input)

        value_input = QPlainTextEdit()
        value_input.setPlainText(str(data.get("value", "")))
        value_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        value_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        value_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        value_input.setFixedHeight(36)
        value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        value_input.textChanged.connect(self._notify_changed)
        self.setCellWidget(row, 2, value_input)
        self.setRowHeight(row, 44)

        self._apply_row_state(row, row == self.currentRow())

    def _row_for_widget(self, widget: QWidget) -> int:
        parent = widget.parentWidget()
        if parent is None:
            return -1
        pos = parent.mapTo(self.viewport(), QPoint(1, 1))
        return self.indexAt(pos).row()

    def _on_copy_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QWidget):
            return
        row = self._row_for_widget(button)
        if row < 0:
            return
        data = {
            "enabled": self.item(row, 0).checkState() == Qt.CheckState.Checked,
            "key": self._get_key(row),
            "value": self._get_value(row),
        }
        self.add_row(data)
        self._notify_changed()

    def _on_delete_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QWidget):
            return
        row = self._row_for_widget(button)
        if row < 0:
            return
        self.remove_row(row)
        self._notify_changed()

    def _get_key(self, row: int) -> str:
        widget = self.cellWidget(row, 1)
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        return ""

    def _get_value(self, row: int) -> str:
        widget = self.cellWidget(row, 2)
        if isinstance(widget, QLineEdit):
            return widget.text()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()
        return ""

    def _set_row_value(self, row: int, key: str, value: str, enabled: bool = True) -> None:
        item = self.item(row, 0)
        if item is not None:
            item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        key_widget = self.cellWidget(row, 1)
        if isinstance(key_widget, QLineEdit):
            key_widget.setText(key)
        value_widget = self.cellWidget(row, 2)
        if isinstance(value_widget, QLineEdit):
            value_widget.setText(value)

    def _notify_changed(self) -> None:
        if callable(self._on_changed):
            self._on_changed()


class HeadersTable(QTableWidget):
    COMMON_HEADERS = [
        "Accept",
        "Accept-Encoding",
        "Accept-Language",
        "Authorization",
        "Cache-Control",
        "Content-Type",
        "Cookie",
        "Origin",
        "Pragma",
        "Referer",
        "User-Agent",
    ]

    def __init__(self, on_changed, parent: QWidget | None = None) -> None:
        super().__init__(0, 3, parent)
        self._on_changed = on_changed
        self._active_row = -1
        self._resizing = False
        self._column_constraints = {0: (48, 70)}
        self.setHorizontalHeaderLabels(["\u542f\u7528", "\u952e", "\u503c", "\u7c7b\u578b"])
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionResized.connect(self._on_header_resized)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(TABLE_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        header.setStretchLastSection(True)
        self.itemChanged.connect(self._on_item_changed)
        self.viewport().installEventFilter(self)
        self.currentCellChanged.connect(self._on_current_cell_changed)
        self._apply_default_column_widths()

    def add_row(self, data: dict | None = None) -> None:
        row = self.rowCount()
        self.insertRow(row)
        self._setup_row(row, data or {})

    def remove_row(self, row: int) -> None:
        if row < 0:
            return
        self.removeRow(row)
        if self.rowCount() == 0:
            self.add_row()

    def get_rows(self) -> list[dict]:
        rows: list[dict] = []
        for row in range(self.rowCount()):
            enabled_item = self.item(row, 0)
            enabled = enabled_item is not None and enabled_item.checkState() == Qt.CheckState.Checked
            key = self._get_key(row)
            value = self._get_value(row)
            value_type = self._get_type(row)
            if not any([key, value, value_type]):
                continue
            rows.append(
                {
                    "enabled": enabled,
                    "key": key,
                    "value": value,
                    "value_type": value_type,
                }
            )
        return rows

    def apply_rows(self, rows: list[dict]) -> None:
        self.setRowCount(0)
        if not rows:
            for _ in range(3):
                self.add_row()
            return
        for row in rows:
            self.add_row(row)

    def get_column_widths(self) -> list[int]:
        return [self.columnWidth(idx) for idx in range(self.columnCount())]

    def apply_column_widths(self, widths: list[int]) -> None:
        header = self.horizontalHeader()
        for idx in range(min(len(widths), self.columnCount())):
            header.resizeSection(idx, self._clamp_width(idx, int(widths[idx])))

    def _apply_default_column_widths(self) -> None:
        defaults = [56, 160, 360, 110]
        header = self.horizontalHeader()
        for idx, width in enumerate(defaults):
            header.resizeSection(idx, self._clamp_width(idx, width))

    def _clamp_width(self, column: int, width: int) -> int:
        bounds = self._column_constraints.get(column)
        if not bounds:
            return width
        minimum, maximum = bounds
        return max(minimum, min(maximum, width))

    def _on_header_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if self._resizing:
            return
        bounds = self._column_constraints.get(logical_index)
        if not bounds:
            return
        minimum, maximum = bounds
        if minimum <= new_size <= maximum:
            return
        self._resizing = True
        self.horizontalHeader().resizeSection(logical_index, self._clamp_width(logical_index, new_size))
        self._resizing = False

    def _on_current_cell_changed(self, row: int, _column: int, previous_row: int, _previous_col: int) -> None:
        if previous_row != row:
            self._apply_row_state(previous_row, False)
        self._apply_row_state(row, True)

    def _apply_row_state(self, row: int, active: bool) -> None:
        if row < 0 or row >= self.rowCount():
            return
        enabled_item = self.item(row, 0)
        enabled = enabled_item is not None and enabled_item.checkState() == Qt.CheckState.Checked
        for col in range(self.columnCount()):
            widget = self.cellWidget(row, col)
            if widget is not None:
                widget.setProperty("activeRow", active and enabled)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                line_edit = widget.findChild(QLineEdit)
                if line_edit is not None:
                    line_edit.setProperty("activeRow", active and enabled)
                    line_edit.style().unpolish(line_edit)
                    line_edit.style().polish(line_edit)
        item = self.item(row, 0)
        if item is not None:
            item.setForeground(QBrush(QColor("#111827" if active else "#9ca3af")))
            item.setBackground(QBrush(Qt.GlobalColor.transparent))

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            if self._handle_paste():
                return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            if key_event.matches(QKeySequence.StandardKey.Paste):
                if self._handle_paste():
                    return True
        return super().eventFilter(obj, event)

    def _handle_paste(self) -> bool:
        text = QApplication.clipboard().text()
        if not text:
            return False
        entries = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            entries.append((key, value))
        if not entries:
            return False
        existing = {}
        for row in range(self.rowCount()):
            key = self._get_key(row)
            if key:
                existing[key.lower()] = row
        for key, value in entries:
            lower_key = key.lower()
            row = existing.get(lower_key)
            if row is None:
                row = self.rowCount()
                self.add_row({"key": key, "value": value})
                existing[lower_key] = row
            else:
                self._set_row_value(row, key, value, enabled=True)
        QMessageBox.information(self, "\u8bf7\u6c42\u5934", f"\u5df2\u8bc6\u522b {len(entries)} \u4e2a\u8bf7\u6c42\u5934")
        self._notify_changed()
        return True

    def _setup_row(self, row: int, data: dict) -> None:
        enabled_item = QTableWidgetItem("")
        enabled_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
        )
        enabled_state = data.get("enabled", True)
        enabled_item.setCheckState(
            Qt.CheckState.Checked if enabled_state else Qt.CheckState.Unchecked
        )
        self.setItem(row, 0, enabled_item)

        key_combo = QComboBox()
        key_combo.setEditable(True)
        key_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        key_combo.addItems(self.COMMON_HEADERS)
        completer = QCompleter(self.COMMON_HEADERS)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        key_combo.setCompleter(completer)
        key_combo.setCurrentText(str(data.get("key", "")))
        key_combo.setFixedHeight(28)
        key_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        key_combo.currentTextChanged.connect(self._notify_changed)
        self.setCellWidget(row, 1, key_combo)
        line_edit = key_combo.lineEdit()
        if line_edit is not None:
            line_edit.installEventFilter(self)

        value_edit = QPlainTextEdit()
        value_edit.setPlainText(str(data.get("value", "")))
        value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        value_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        value_edit.setFixedHeight(36)
        value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        value_edit.textChanged.connect(self._notify_changed)
        value_edit.installEventFilter(self)
        self.setCellWidget(row, 2, value_edit)
        self.setRowHeight(row, 44)

        type_combo = QComboBox()
        type_combo.addItem("\u6587\u672c", "text")
        type_combo.addItem("JSON", "json")
        type_combo.addItem("Token", "token")
        type_combo.addItem("Cookie", "cookie")
        type_combo.setCurrentIndex(max(0, type_combo.findData(str(data.get("value_type", "text")))))
        type_combo.setFixedHeight(28)
        type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        type_combo.currentTextChanged.connect(self._notify_changed)
        self.setCellWidget(row, 3, type_combo)

        self._apply_row_state(row, row == self.currentRow())
        self._apply_row_enabled(row, enabled_state)

    def _row_for_widget(self, widget: QWidget) -> int:
        parent = widget.parentWidget()
        if parent is None:
            return -1
        pos = parent.mapTo(self.viewport(), QPoint(1, 1))
        return self.indexAt(pos).row()

    def _on_copy_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QWidget):
            return
        row = self._row_for_widget(button)
        if row < 0:
            return
        data = {
            "enabled": self.item(row, 0).checkState() == Qt.CheckState.Checked,
            "key": self._get_key(row),
            "value": self._get_value(row),
            "value_type": self._get_type(row),
        }
        self.add_row(data)
        self._notify_changed()

    def _on_delete_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QWidget):
            return
        row = self._row_for_widget(button)
        if row < 0:
            return
        self.remove_row(row)
        self._notify_changed()

    def _get_key(self, row: int) -> str:
        widget = self.cellWidget(row, 1)
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return ""

    def _get_value(self, row: int) -> str:
        widget = self.cellWidget(row, 2)
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()
        return ""

    def _get_type(self, row: int) -> str:
        widget = self.cellWidget(row, 3)
        if isinstance(widget, QComboBox):
            value = widget.currentData()
            if isinstance(value, str):
                return value
            return widget.currentText().strip()
        return "text"

    def _set_row_value(self, row: int, key: str, value: str, enabled: bool = True) -> None:
        item = self.item(row, 0)
        if item is not None:
            item.setCheckState(Qt.CheckState.Checked if enabled else Qt.CheckState.Unchecked)
        key_widget = self.cellWidget(row, 1)
        if isinstance(key_widget, QComboBox):
            key_widget.setCurrentText(key)
        value_widget = self.cellWidget(row, 2)
        if isinstance(value_widget, QPlainTextEdit):
            value_widget.setPlainText(value)
        self._apply_row_enabled(row, enabled)

    def _notify_changed(self) -> None:
        if callable(self._on_changed):
            self._on_changed()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            enabled = item.checkState() == Qt.CheckState.Checked
            self._apply_row_enabled(item.row(), enabled)
        self._notify_changed()

    def _apply_row_enabled(self, row: int, enabled: bool) -> None:
        if row < 0 or row >= self.rowCount():
            return
        for col in range(1, 4):
            widget = self.cellWidget(row, col)
            if widget is None:
                continue
            widget.setEnabled(enabled)
            widget.setProperty("rowDisabled", not enabled)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            line_edit = widget.findChild(QLineEdit)
            if line_edit is not None:
                line_edit.setProperty("rowDisabled", not enabled)
                line_edit.style().unpolish(line_edit)
                line_edit.style().polish(line_edit)
        actions = self.cellWidget(row, 4)
        if actions is not None:
            copy_button = actions.findChild(QToolButton, "copyButton")
            if copy_button is not None:
                copy_button.setEnabled(enabled)
        item = self.item(row, 0)
        if item is not None:
            item.setBackground(QBrush(QColor("#f3f4f6" if not enabled else Qt.GlobalColor.transparent)))


class AssertionPanel(QWidget):
    data_changed = Signal()

    TYPE_OPTIONS = [
        ("status_code", "\u72b6\u6001\u7801"),
        ("response_body", "\u54cd\u5e94\u4f53"),
        ("json_path", "JSONPath"),
        ("header", "\u54cd\u5e94\u5934"),
        ("response_time", "\u54cd\u5e94\u8017\u65f6"),
    ]
    OPERATOR_MAP = {
        "status_code": ["==", "!=", ">", ">=", "<", "<=", "between"],
        "response_body": ["contains", "not_contains", "starts_with", "ends_with", "matches_regex"],
        "json_path": ["==", "!=", ">", ">=", "<", "<=", "contains", "not_contains", "exists", "not_exists", "not_null"],
        "header": ["contains", "not_contains", "==", "!=", "exists", "not_exists"],
        "response_time": ["<", "<=", ">", ">=", "between"],
    }
    NO_EXPECTED_OPERATORS = {"exists", "not_exists"}
    TARGET_PLACEHOLDERS = {
        "json_path": "$.data.id",
        "header": "Header-Key (例如 Content-Type)",
        "response_body": "\u5173\u952e\u5b57/\u6b63\u5219",
        "response_time": "\u6beb\u79d2 (ms)",
    }
    EXPECTED_PLACEHOLDERS = {
        "status_code": "200",
        "response_body": "\u5173\u952e\u5b57/\u6b63\u5219",
        "json_path": "\u503c",
        "header": "\u503c",
        "response_time": "0",
    }
    RANGE_PLACEHOLDERS = {
        "status_code": ("0", "600"),
        "response_time": ("0", "2000"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_row = -1
        self._resizing = False
        self._column_constraints = {0: (50, 70)}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        config_block = QWidget()
        config_block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        config_layout = QVBoxLayout(config_block)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title = QLabel("\u65ad\u8a00\u914d\u7f6e")
        title.setObjectName("sectionTitle")
        add_button = QPushButton("\u65b0\u589e")
        add_button.setObjectName("secondaryButton")
        add_button.clicked.connect(self._add_row)
        delete_button = QPushButton("\u5220\u9664")
        delete_button.setObjectName("secondaryButton")
        delete_button.clicked.connect(self._remove_row)
        delete_button.setStyleSheet(
            "QPushButton { background-color: #dc2626; color: #ffffff; border: none; border-radius: 4px; padding: 4px 12px; }"
            "QPushButton:hover { background-color: #b91c1c; }"
            "QPushButton:disabled { background-color: #fca5a5; }"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(add_button)
        title_row.addWidget(delete_button)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [
                "\u542f\u7528",
                "\u7c7b\u578b",
                "\u76ee\u6807/\u8def\u5f84",
                "\u64cd\u4f5c\u7b26",
                "\u671f\u671b\u503c",
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionResized.connect(self._on_header_resized)
        header.setStretchLastSection(True)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { background: #f8fafc; gridline-color: #e5e7eb; }"
            "QTableWidget::item { color: #9ca3af; }"
            "QTableWidget::item:selected { background: #eef2f7; color: #111827; }"
            "QTableWidget::item:focus { outline: none; }"
            "QComboBox, QLineEdit, QPlainTextEdit { background: #ffffff; color: #6b7280; "
            "border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 4px; }"
            "QComboBox[activeRow=\"true\"], QLineEdit[activeRow=\"true\"], QPlainTextEdit[activeRow=\"true\"] "
            "{ color: #111827; background: #ffffff; border-color: #93c5fd; }"
            "QSpinBox { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 4px; padding: 2px 4px; }"
            "QSpinBox[activeRow=\"true\"] { background: #ffffff; border-color: #93c5fd; }"
        )
        self.table.itemChanged.connect(self._emit_changed)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)

        config_layout.addLayout(title_row)
        config_layout.addWidget(self.table, 1)
        config_block.setMinimumHeight(180)
        config_block.setMaximumHeight(620)
        layout.addWidget(config_block, 1)
        self._apply_default_column_widths()
        for _ in range(3):
            self._add_row()

    def get_assertions(self) -> list[dict]:
        return [row for row in self.get_assertion_rows() if row.get("enabled", True)]

    def get_assertion_rows(self) -> list[dict]:
        assertions: list[dict] = []
        for row in range(self.table.rowCount()):
            enabled_item = self.table.item(row, 0)
            enabled = enabled_item is not None and enabled_item.checkState() == Qt.CheckState.Checked
            assertion_type = self._get_type(row)
            target = self._get_target(row)
            operator = self._get_operator(row)
            expected = self._get_expected(row)
            if not any([assertion_type, target, operator, expected]):
                continue
            assertion = {
                "enabled": enabled,
                "type": assertion_type,
                "operator": operator,
                "expected": expected,
            }
            if assertion_type == "json_path":
                assertion["path"] = target
            elif assertion_type == "header":
                assertion["header"] = target
            else:
                if target:
                    assertion["target"] = target
            assertions.append(assertion)
        return assertions

    def set_assertions(self, rows: list[dict] | None) -> None:
        self.table.setRowCount(0)
        if not rows:
            self._add_row({"enabled": False, "expected": ""})
            return
        for row in rows:
            self._add_row(row)

    def clear_assertions(self) -> None:
        self.set_assertions([])
        return

    def get_ui_state(self) -> dict:
        return {
            "assertion_table_columns": [self.table.columnWidth(idx) for idx in range(self.table.columnCount())],
        }

    def apply_ui_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        widths = state.get("assertion_table_columns")
        if isinstance(widths, list) and widths:
            header = self.table.horizontalHeader()
            for idx in range(min(len(widths), self.table.columnCount())):
                header.resizeSection(idx, self._clamp_width(idx, int(widths[idx])))

    def _apply_default_column_widths(self) -> None:
        defaults = [56, 130, 220, 110, 260]
        header = self.table.horizontalHeader()
        for idx, width in enumerate(defaults):
            header.resizeSection(idx, self._clamp_width(idx, width))

    def _clamp_width(self, column: int, width: int) -> int:
        bounds = self._column_constraints.get(column)
        if not bounds:
            return width
        minimum, maximum = bounds
        return max(minimum, min(maximum, width))

    def _on_header_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if self._resizing:
            return
        bounds = self._column_constraints.get(logical_index)
        if not bounds:
            return
        minimum, maximum = bounds
        if minimum <= new_size <= maximum:
            return
        self._resizing = True
        self.table.horizontalHeader().resizeSection(logical_index, self._clamp_width(logical_index, new_size))
        self._resizing = False

    def _on_current_cell_changed(self, row: int, _column: int, previous_row: int, _previous_col: int) -> None:
        if previous_row != row:
            self._apply_row_state(previous_row, False)
        self._apply_row_state(row, True)

    def _apply_row_state(self, row: int, active: bool) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        for col in range(self.table.columnCount()):
            widget = self.table.cellWidget(row, col)
            if widget is not None:
                widget.setProperty("activeRow", active)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                spin = widget.findChild(QSpinBox)
                if spin is not None:
                    spin.setProperty("activeRow", active)
                    spin.style().unpolish(spin)
                    spin.style().polish(spin)
        item = self.table.item(row, 0)
        if item is not None:
            item.setForeground(QBrush(QColor("#111827" if active else "#9ca3af")))
            item.setBackground(QBrush(Qt.GlobalColor.transparent))

    def _add_row(self, data: dict | None = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._setup_row(row, data or {})

    def _remove_row(self) -> None:
        if self.table.rowCount() == 0:
            return
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        if row < 0:
            return
        self.table.removeRow(row)
        if self.table.rowCount() == 0:
            self._add_row()
        else:
            new_row = min(row, self.table.rowCount() - 1)
            self.table.selectRow(new_row)
        self._emit_changed()

    def _setup_row(self, row: int, data: dict) -> None:
        row_data = {**self._default_row_data(), **data}
        enabled_item = QTableWidgetItem("")
        enabled_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
        )
        enabled_item.setCheckState(
            Qt.CheckState.Checked if data.get("enabled", True) else Qt.CheckState.Unchecked
        )
        self.table.setItem(row, 0, enabled_item)

        type_combo = QComboBox()
        for key, label in self.TYPE_OPTIONS:
            type_combo.addItem(label, key)
        type_value = row_data.get("type") or "status_code"
        type_combo.setCurrentIndex(max(0, type_combo.findData(type_value)))
        type_combo.currentIndexChanged.connect(lambda _index, _row=row: self._on_type_changed(_row))
        type_combo.setFixedHeight(28)
        type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.setCellWidget(row, 1, type_combo)

        target_input = QLineEdit()
        target_input.setText(str(row_data.get("path") or row_data.get("header") or row_data.get("target") or ""))
        target_input.setFixedHeight(28)
        target_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        target_input.textChanged.connect(self._emit_changed)
        self.table.setCellWidget(row, 2, target_input)

        operator_combo = QComboBox()
        operator_combo.setFixedHeight(28)
        operator_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.setCellWidget(row, 3, operator_combo)
        operator_combo.currentIndexChanged.connect(self._emit_changed)
        operator_combo.currentIndexChanged.connect(lambda _value, _row=row: self._handle_operator_changed(_row))
        self._update_operator(row, type_value, row_data.get("operator"), row_data.get("expected"))

        self._update_placeholders(row, type_value)
        self.table.setRowHeight(row, 44)
        self._apply_row_state(row, row == self.table.currentRow())

    def _default_row_data(self) -> dict:
        return {"enabled": True, "type": "status_code", "operator": "==", "expected": "200"}

    def _on_type_changed(self, row: int | None = None) -> None:
        if row is None:
            combo = self.sender()
            if not isinstance(combo, QComboBox):
                return
            row = self._row_for_widget(combo)
        if row is None or row < 0:
            return
        assertion_type = self._get_type(row)
        current_expected = self._get_expected(row)
        self._update_operator(row, assertion_type, None, current_expected)
        self._update_placeholders(row, assertion_type)
        self._emit_changed()

    def _update_operator(
        self,
        row: int,
        assertion_type: str,
        current: str | None,
        expected_value: str | None = None,
    ) -> None:
        operator_combo = self.table.cellWidget(row, 3)
        if not isinstance(operator_combo, QComboBox):
            return
        operator_combo.blockSignals(True)
        operator_combo.clear()
        for operator in self.OPERATOR_MAP.get(assertion_type, []):
            operator_combo.addItem(OPERATOR_LABELS.get(operator, operator), operator)
        selected = self._select_operator(assertion_type, current)
        if selected is not None:
            index = operator_combo.findData(selected)
            if index >= 0:
                operator_combo.setCurrentIndex(index)
        operator_combo.blockSignals(False)
        self._refresh_expected_widget(row, assertion_type, selected, expected_value)

    def _refresh_expected_widget(
        self,
        row: int,
        assertion_type: str,
        operator: str | None = None,
        value: str | None = None,
    ) -> None:
        operator_value = operator or self._get_operator(row)
        expected_value = value if value is not None else self._get_expected(row)
        self._set_expected_widget(row, assertion_type, operator_value, expected_value)

    def _select_operator(self, assertion_type: str, current: str | None) -> str | None:
        options = self.OPERATOR_MAP.get(assertion_type, [])
        if not options:
            return current
        if current in options:
            return current
        return options[0]

    def _handle_operator_changed(self, row: int) -> None:
        assertion_type = self._get_type(row)
        operator = self._get_operator(row)
        self._refresh_expected_widget(row, assertion_type, operator)

    def _update_placeholders(self, row: int, assertion_type: str) -> None:
        target_input = self.table.cellWidget(row, 2)
        if not isinstance(target_input, QLineEdit):
            return
        target_input.setPlaceholderText(self._target_placeholder_for(assertion_type))

    def _target_placeholder_for(self, assertion_type: str) -> str:
        return self.TARGET_PLACEHOLDERS.get(assertion_type, '')

    def _expected_placeholder_for(self, assertion_type: str) -> str:
        return self.EXPECTED_PLACEHOLDERS.get(assertion_type, '')

    def _range_placeholders_for(self, assertion_type: str) -> tuple[str, str]:
        return self.RANGE_PLACEHOLDERS.get(assertion_type, ('0', '0'))

    def _set_expected_widget(
        self,
        row: int,
        assertion_type: str,
        operator: str | None,
        value: object | None,
    ) -> None:
        if operator in self.NO_EXPECTED_OPERATORS:
            placeholder = "\u4e0d\u9700\u8f93\u5165"
            disabled = QLineEdit()
            disabled.setPlaceholderText(placeholder)
            disabled.setEnabled(False)
            disabled.setToolTip("\u5b58\u5728/\u4e0d\u5b58\u5728\u7c7b\u65ad\u8a00\u4e0d\u9700\u6ce8\u518c\u671f\u671b\u503c")
            disabled.setStyleSheet(
                "QLineEdit { color: #9ca3af; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 4px; }"
            )
            self.table.setCellWidget(row, 4, disabled)
            return
        if assertion_type in {"status_code", "response_time"}:
            if operator == "between":
                self._build_range_widget(row, value, assertion_type)
                return
            self._build_numeric_widget(row, value, assertion_type)
            return
        if assertion_type in {"response_body", "json_path"}:
            expected_input = QPlainTextEdit()
            expected_input.setPlainText("" if value is None else str(value))
            expected_input.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            expected_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            expected_input.setFixedHeight(36)
            expected_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            expected_input.setPlaceholderText(self._expected_placeholder_for(assertion_type))
            expected_input.textChanged.connect(self._emit_changed)
            self.table.setCellWidget(row, 4, expected_input)
            return
        if assertion_type == "header":
            expected_input = QLineEdit()
            expected_input.setText("" if value is None else str(value))
            expected_input.setPlaceholderText(self._expected_placeholder_for(assertion_type))
            expected_input.setFixedHeight(28)
            expected_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            expected_input.textChanged.connect(self._emit_changed)
            self.table.setCellWidget(row, 4, expected_input)
            return
        expected_input = QLineEdit()
        expected_input.setText("" if value is None else str(value))
        expected_input.setFixedHeight(28)
        expected_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        expected_input.setPlaceholderText(self._expected_placeholder_for(assertion_type))
        expected_input.textChanged.connect(self._emit_changed)
        self.table.setCellWidget(row, 4, expected_input)

    def _build_numeric_widget(self, row: int, value: object | None, assertion_type: str) -> None:
        text = "" if value is None else str(value)
        placeholder = self._expected_placeholder_for(assertion_type)
        editor = QLineEdit()
        editor.setPlaceholderText(placeholder)
        editor.setText(text)
        editor.setFixedHeight(28)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        validator = QIntValidator(0, 1000000, self)
        editor.setValidator(validator)
        editor.textChanged.connect(self._emit_changed)
        self.table.setCellWidget(row, 4, editor)

    def _build_range_widget(self, row: int, value: object | None, assertion_type: str) -> None:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        low_input = QLineEdit()
        high_input = QLineEdit()
        low_input.setValidator(QIntValidator(0, 1000000, self))
        low_input.setFixedHeight(28)
        low_input.setMaximumWidth(110)
        low_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        low_placeholder, high_placeholder = self._range_placeholders_for(assertion_type)
        low_input.setPlaceholderText(low_placeholder)
        low_input.textChanged.connect(self._emit_changed)
        high_input.setValidator(QIntValidator(0, 1000000, self))
        high_input.setFixedHeight(28)
        high_input.setMaximumWidth(110)
        high_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        high_input.setPlaceholderText(high_placeholder)
        high_input.textChanged.connect(self._emit_changed)
        range_values = self._parse_range_text(value)
        if range_values is not None:
            low_input.setText(str(range_values[0]))
            high_input.setText(str(range_values[1]))
        layout.addWidget(low_input)
        separator = QLabel("~")
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(separator)
        layout.addWidget(high_input)
        layout.addStretch(1)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.setCellWidget(row, 4, container)

    def _parse_range_text(self, value: object | None) -> tuple[int, int] | None:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace("～", "~").replace("—", "~")
        separator = "~" if "~" in normalized else ("-" if "-" in normalized else None)
        if not separator:
            return None
        parts = [part.strip() for part in normalized.split(separator, 1)]
        if len(parts) != 2:
            return None
        low = self._to_int(parts[0])
        high = self._to_int(parts[1])
        if low is None or high is None:
            return None
        return (min(low, high), max(low, high))

    def _to_int(self, value: object | None) -> int | None:
        if value is None:
            return None
        try:
            return int(float(str(value)))
        except ValueError:
            return None

    def _on_copy_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QWidget):
            return
        row = self._row_for_widget(button)
        if row < 0:
            return
        data = {
            "enabled": self.table.item(row, 0).checkState() == Qt.CheckState.Checked,
            "type": self._get_type(row),
            "operator": self._get_operator(row),
            "expected": self._get_expected(row),
        }
        target = self._get_target(row)
        if data["type"] == "json_path":
            data["path"] = target
        elif data["type"] == "header":
            data["header"] = target
        else:
            data["target"] = target
        self._add_row(data)
        self._emit_changed()

    def _on_delete_clicked(self) -> None:
        button = self.sender()
        if not isinstance(button, QWidget):
            return
        row = self._row_for_widget(button)
        if row < 0:
            return
        self.table.removeRow(row)
        if self.table.rowCount() == 0:
            self._add_row()
        self._emit_changed()

    def _row_for_widget(self, widget: QWidget) -> int:
        parent = widget.parentWidget()
        if parent is None:
            return -1
        pos = parent.mapTo(self.table.viewport(), QPoint(1, 1))
        return self.table.indexAt(pos).row()

    def _get_type(self, row: int) -> str:
        widget = self.table.cellWidget(row, 1)
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            if isinstance(data, str):
                return data
            return widget.currentText().strip()
        return ""

    def _get_target(self, row: int) -> str:
        widget = self.table.cellWidget(row, 2)
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        return ""

    def _get_operator(self, row: int) -> str:
        widget = self.table.cellWidget(row, 3)
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            if isinstance(data, str):
                return data
            return widget.currentText().strip()
        return ""

    def _get_expected(self, row: int) -> str:
        widget = self.table.cellWidget(row, 4)
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        if isinstance(widget, QWidget):
            editors = widget.findChildren(QLineEdit)
            if len(editors) == 2:
                return f"{editors[0].text().strip()}~{editors[1].text().strip()}"
            if len(editors) == 1:
                return editors[0].text().strip()
        return ""

    def _emit_changed(self) -> None:
        self.data_changed.emit()
