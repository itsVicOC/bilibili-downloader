"""Consistent, bounded workflow dialogs with a fixed action footer."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.widgets.components import Notice, help_text, scroll_area
from bilibili_downloader.gui.widgets.responsive_actions import (
    ActionButton,
    ResponsiveActions,
)
from bilibili_downloader.gui.window_bounds import ScreenBounds


class WorkflowDialog(QDialog):
    def __init__(self, title, description="", parent=None, *, confirm="确认", width=640):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(16)
        heading = QLabel(title)
        heading.setWordWrap(True)
        heading.setObjectName("DialogTitle")
        root.addWidget(heading)
        if description:
            root.addWidget(help_text(description))
        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        self.scroller = scroll_area(self.content)
        root.addWidget(self.scroller, 1)
        self.notice = Notice()
        root.addWidget(self.notice)
        self.footer = QWidget()
        from PySide6.QtWidgets import QBoxLayout
        footer = QBoxLayout(QBoxLayout.LeftToRight, self.footer)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        self.footer_hint = help_text("")
        footer.addWidget(self.footer_hint, 1)
        self.footer_actions = ResponsiveActions()
        self.cancel_button = ActionButton("取消")
        self.cancel_button.setProperty("alwaysVisible", True)
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button = ActionButton(confirm)
        self.confirm_button.setProperty("alwaysVisible", True)
        self.confirm_button.setObjectName("PrimaryButton")
        self.confirm_button.setAutoDefault(False)
        self.confirm_button.clicked.connect(self.accept)
        self.footer_actions.row.addWidget(self.cancel_button)
        self.footer_actions.row.addWidget(self.confirm_button)
        footer.addWidget(self.footer_actions)
        root.addWidget(self.footer)
        self.resize(width, 500)
        self._return_focus = parent.focusWidget() if parent else None
        self.finished.connect(self._restore_focus)
        self._screen_bounds = ScreenBounds(self, QSize(420, 0))

    def _restore_focus(self, _result):
        from shiboken6 import isValid
        if self._return_focus is not None and isValid(self._return_focus):
            self._return_focus.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and isinstance(self.focusWidget(), (QLineEdit, QPlainTextEdit)):
            event.accept()
            return
        super().keyPressEvent(event)
