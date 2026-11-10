"""An explicit choice between background operation and application exit."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.widgets.check_box import CheckBox
from bilibili_downloader.gui.widgets.components import scroll_area
from bilibili_downloader.gui.widgets.dialog_shell import AppDialog
from bilibili_downloader.gui.widgets.responsive_actions import (
    ActionButton,
    ResponsiveActions,
)


class CloseWindowDialog(AppDialog):
    CANCEL = 0
    TRAY = 1
    QUIT = 2

    def __init__(self, parent=None, *, active=False, tray_available=True):
        super().__init__(parent)
        self.setWindowTitle("关闭提示")
        self.setMinimumWidth(480)
        self.resize(520, 300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel("退出 BiliFlow？")
        title.setObjectName("DialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        description = QLabel(
            "最小化到托盘，任务继续运行。\n"
            "退出将暂停下载，停止直播监控、录制和导出。"
        )
        description.setTextFormat(Qt.PlainText)
        description.setWordWrap(True)
        body.addWidget(description)
        self.unavailable = QLabel("系统托盘暂不可用。")
        self.unavailable.setObjectName("FieldError")
        self.unavailable.setWordWrap(True)
        self.unavailable.setVisible(not tray_available)
        body.addWidget(self.unavailable)
        self.remember = CheckBox("记住选择")
        self.remember.setChecked(False)
        body.addWidget(self.remember)
        hint = QLabel("可在设置中更改。")
        hint.setObjectName("MetaLabel")
        hint.setWordWrap(True)
        body.addWidget(hint)
        body.addStretch()
        self.scroller = scroll_area(content)
        layout.addWidget(self.scroller, 1)
        self.actions = ResponsiveActions()
        footer = self.actions.row
        self.cancel_button = ActionButton("取消")
        self.quit_button = ActionButton("停止并退出" if active else "退出")
        self.tray_button = ActionButton("最小化到托盘")
        for button, role, result in (
            (self.cancel_button, "SubtleButton", self.CANCEL),
            (self.quit_button, "DangerButton", self.QUIT),
            (self.tray_button, "PrimaryButton", self.TRAY),
        ):
            button.setObjectName(role)
            button.setAutoDefault(False)
            button.setProperty("alwaysVisible", True)
            button.clicked.connect(lambda _checked=False, value=result: self.done(value))
            footer.addWidget(button)
        self.tray_button.setEnabled(tray_available)
        default = self.tray_button if tray_available else self.cancel_button
        default.setDefault(True)
        default.setFocus()
        layout.addWidget(self.actions)
