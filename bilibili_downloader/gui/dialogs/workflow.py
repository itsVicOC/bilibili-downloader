"""Consistent, bounded workflow dialogs with a fixed action footer."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.widgets.components import Notice, help_text, scroll_area


class WorkflowDialog(QDialog):
    def __init__(self, title, description="", parent=None, *, confirm="确认", width=640):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        root.addWidget(heading)
        if description:
            root.addWidget(help_text(description))
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        self.scroller = scroll_area(self.content)
        root.addWidget(self.scroller, 1)
        self.notice = Notice()
        root.addWidget(self.notice)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.footer_hint = help_text("")
        footer.addWidget(self.footer_hint, 1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button = QPushButton(confirm)
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.setAutoDefault(False)
        self.confirm_button.clicked.connect(self.accept)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.confirm_button)
        root.addLayout(footer)
        self.resize(width, 500)
        self._return_focus = parent.focusWidget() if parent else None
        self.finished.connect(self._restore_focus)

    def _restore_focus(self, _result):
        from shiboken6 import isValid
        if self._return_focus is not None and isValid(self._return_focus):
            self._return_focus.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and isinstance(self.focusWidget(), (QLineEdit, QPlainTextEdit)):
            event.accept()
            return
        super().keyPressEvent(event)
