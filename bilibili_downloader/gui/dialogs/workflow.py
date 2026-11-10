"""Consistent, bounded workflow dialogs with a fixed action footer."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.widgets.components import (
    Notice,
    SectionCard,
    help_text,
    repolish,
    scroll_area,
)
from bilibili_downloader.gui.widgets.dialog_shell import AppDialog, prepare_dialog
from bilibili_downloader.gui.widgets.responsive_actions import (
    ActionButton,
    ResponsiveActions,
)


class WorkflowDialog(AppDialog):
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
        prepare_dialog(self)
    def showEvent(self, event):
        for group in self.content.findChildren(SectionCard):
            group.setProperty("sectionStyle", "plain")
            repolish(group)
        super().showEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and isinstance(self.focusWidget(), (QLineEdit, QPlainTextEdit)):
            event.accept()
            return
        super().keyPressEvent(event)
