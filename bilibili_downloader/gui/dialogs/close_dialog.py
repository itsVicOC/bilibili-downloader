"""An explicit choice between background operation and application exit."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class CloseWindowDialog(QDialog):
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
        title = QLabel("要退出 BiliFlow 吗？")
        title.setObjectName("DialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        description = QLabel(
            "最小化到托盘可让任务继续运行。\n"
            "退出将暂停下载，停止直播监控、录制和导出。"
        )
        description.setTextFormat(Qt.PlainText)
        description.setWordWrap(True)
        layout.addWidget(description)
        self.unavailable = QLabel("系统托盘暂不可用。")
        self.unavailable.setObjectName("FieldError")
        self.unavailable.setWordWrap(True)
        self.unavailable.setVisible(not tray_available)
        layout.addWidget(self.unavailable)
        self.remember = QCheckBox("记住我的选择")
        self.remember.setChecked(False)
        layout.addWidget(self.remember)
        hint = QLabel("可在设置中更改。")
        hint.setObjectName("MetaLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.cancel_button = QPushButton("取消")
        self.quit_button = QPushButton("停止并退出" if active else "退出软件")
        self.tray_button = QPushButton("最小化到托盘")
        for button, role, result in (
            (self.cancel_button, "SubtleButton", self.CANCEL),
            (self.quit_button, "DangerButton", self.QUIT),
            (self.tray_button, "PrimaryButton", self.TRAY),
        ):
            button.setObjectName(role)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, value=result: self.done(value))
            footer.addWidget(button)
        self.tray_button.setEnabled(tray_available)
        default = self.tray_button if tray_available else self.cancel_button
        default.setDefault(True)
        default.setFocus()
        layout.addLayout(footer)
