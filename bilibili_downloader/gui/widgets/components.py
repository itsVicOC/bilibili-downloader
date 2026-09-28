"""Shared presentation primitives; no service or persistence ownership."""

from PySide6.QtCore import QByteArray, QEvent, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import DARK_PALETTE, LIGHT_PALETTE

_ICON_PATHS = {
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    "live": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m9 9 6 3-6 3z"/>',
    "tasks": '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="m7 8 1 1 2-2m2 1h5m-10 6 1 1 2-2m2 1h5"/>',
    "settings": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
    "account": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z"/>',
    "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
    "success": '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
    "warning": '<path d="M12 3 2 21h20zM12 9v5m0 3v1"/>',
    "danger": '<circle cx="12" cy="12" r="9"/><path d="m8 8 8 8m0-8-8 8"/>',
    "folder": '<path d="M3 6h7l2 3h9v11H3z"/>',
}


def palette():
    app = QApplication.instance()
    return DARK_PALETTE if app and app.property("darkTheme") else LIGHT_PALETTE


def line_icon(name, color=None, size=24):
    color = color or palette().muted
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICON_PATHS[name]}</svg>'
    )
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class PopupMenu(QMenu):
    """Allow the shared menu's rounded corners to stay transparent."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)


class IconButton(QPushButton):
    def __init__(self, text, icon, role="SubtleButton", parent=None):
        super().__init__(text, parent)
        self.icon_name = icon
        self.full_text = text
        self.setObjectName(role)
        self.setIconSize(QSize(20, 20))
        self.setAccessibleName(text)
        self.setToolTip(text)
        self._sync_icon()

    def _sync_icon(self):
        self.setIcon(line_icon(self.icon_name))

    def event(self, event):
        if event.type() == QEvent.StyleChange and hasattr(self, "icon_name"):
            self._sync_icon()
        return super().event(event)

    def set_compact(self, compact):
        self.setText("" if compact else self.full_text)


class PageHeader(QWidget):
    def __init__(self, title, caption, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        self.caption = QLabel(caption)
        self.caption.setObjectName("Caption")
        self.caption.setWordWrap(True)
        copy.addWidget(self.title)
        copy.addWidget(self.caption)
        row.addLayout(copy, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)


class SectionCard(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 20, 20, 20)
        self.body.setSpacing(12)
        self.header = QHBoxLayout()
        if title:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            self.header.addWidget(label)
        self.header.addStretch()
        if title:
            self.body.addLayout(self.header)


class StatusBadge(QLabel):
    def __init__(self, text="", tone="muted", parent=None):
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.set_tone(tone)

    def set_tone(self, tone):
        self.setProperty("tone", tone)
        repolish(self)


class MessageBox(QMessageBox):
    """Shared typography, semantic icon and actions for auxiliary dialogs."""

    def __init__(
        self,
        title,
        text,
        parent=None,
        tone="info",
        buttons=QMessageBox.Ok,
        default=QMessageBox.Ok,
        rich_text=False,
    ):
        super().__init__(parent)
        self._tone = tone
        self.setWindowTitle(title)
        self.setTextFormat(Qt.RichText if rich_text else Qt.PlainText)
        self.setText(title)
        self.setInformativeText(text)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse
        )
        heading = self.findChild(QLabel, "qt_msgbox_label")
        heading.setObjectName("DialogTitle")
        self.layout().setContentsMargins(24, 24, 24, 24)
        self.layout().setSpacing(12)
        self.setStandardButtons(buttons)
        self.setDefaultButton(default)
        for key, label in (
            (QMessageBox.Ok, "知道了"),
            (QMessageBox.Yes, "继续"),
            (QMessageBox.No, "取消"),
            (QMessageBox.Cancel, "取消"),
            (QMessageBox.Save, "保存修改"),
            (QMessageBox.Discard, "放弃修改"),
        ):
            button = self.button(key)
            if button:
                button.setText(label)
                button.setObjectName(
                    "PrimaryButton"
                    if key in (QMessageBox.Yes, QMessageBox.Save)
                    else "SubtleButton"
                )
                repolish(button)
        self._sync_icon()

    def showEvent(self, event):
        # Standard buttons may have been polished before callers assign a role.
        for button in self.buttons():
            repolish(button)
        super().showEvent(event)

    def _sync_icon(self):
        p = palette()
        color = {"danger": p.danger, "warning": p.warning, "success": p.success}.get(
            self._tone, p.muted
        )
        self.setIconPixmap(line_icon(self._tone, color, 28).pixmap(28, 28))

    def changeEvent(self, event):
        if event.type() == QEvent.StyleChange and hasattr(self, "_tone"):
            self._sync_icon()
        super().changeEvent(event)


class Notice(QFrame):
    def __init__(self, text="", tone="info", action="", callback=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Notice")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(12, 10, 12, 10)
        self.row.setSpacing(10)
        self.symbol = QLabel()
        self.symbol.setFixedSize(20, 20)
        self.label = QLabel()
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.row.addWidget(self.symbol, 0, Qt.AlignTop)
        self.row.addWidget(self.label, 1)
        self.action = QPushButton(action)
        self.action.setObjectName("TextButton")
        self.action.setVisible(bool(action))
        if callback:
            self.action.clicked.connect(callback)
        self.row.addWidget(self.action)
        self.set_message(text, tone)

    def set_message(self, text, tone="info"):
        self.setProperty("tone", tone)
        self.label.setText(text)
        self.label.setProperty("tone", tone)
        self.setVisible(bool(text))
        self._sync_icon()
        repolish(self)
        repolish(self.label)

    def _sync_icon(self):
        tone = self.property("tone") or "info"
        p = palette()
        color = {"success": p.success, "warning": p.warning, "danger": p.danger}.get(
            tone, p.muted
        )
        self.symbol.setPixmap(
            line_icon(tone if tone in _ICON_PATHS else "info", color, 20).pixmap(20, 20)
        )

    def event(self, event):
        if event.type() == QEvent.StyleChange and hasattr(self, "symbol"):
            self._sync_icon()
        return super().event(event)


class StarArt(QWidget):
    """Small scalable brand illustration for all empty states."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(112, 72)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = palette()
        painter.setPen(QPen(QColor(p.border), 1))
        painter.drawEllipse(8, 20, 96, 30)
        painter.setPen(QPen(QColor(p.accent), 1.5))
        painter.drawEllipse(28, 5, 56, 58)
        painter.drawPixmap(40, 20, line_icon("star", p.accent, 32).pixmap(32, 32))
        painter.end()


class EmptyState(QWidget):
    def __init__(self, title, description, action="", callback=None, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(20, 20, 20, 20)
        column.setSpacing(8)
        column.addStretch()
        column.addWidget(StarArt(), alignment=Qt.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        title_label.setAlignment(Qt.AlignCenter)
        column.addWidget(title_label)
        desc = QLabel(description)
        desc.setObjectName("MetaLabel")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        column.addWidget(desc)
        if action:
            button = QPushButton(action)
            button.setObjectName("SubtleButton")
            if callback:
                button.clicked.connect(callback)
            column.addWidget(button, alignment=Qt.AlignCenter)
        column.addStretch()


class FieldRow(QWidget):
    def __init__(self, label, control, parent=None):
        super().__init__(parent)
        self.control = control
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.label = QLabel(label)
        self.label.setObjectName("FieldLabel")
        self.label.setFixedWidth(92)
        row.addWidget(self.label)
        row.addWidget(control, 1)
        column.addLayout(row)
        self._error_row = QWidget()
        errors = QHBoxLayout(self._error_row)
        errors.setContentsMargins(104, 0, 0, 0)
        self.error = QLabel()
        self.error.setObjectName("FieldError")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.PlainText)
        errors.addWidget(self.error)
        column.addWidget(self._error_row)
        self._error_row.hide()

    def set_error(self, message):
        self.error.setText(message)
        self._error_row.setVisible(bool(message))
        self.control.setProperty("invalid", bool(message))
        repolish(self.control)


def scroll_area(body):
    scroll = QScrollArea()
    scroll.setObjectName("WorkspaceScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(body)
    return scroll


def stepper(spin: QSpinBox):
    spin.setButtonSymbols(QSpinBox.NoButtons)
    spin.setAlignment(Qt.AlignCenter)
    spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    down = QPushButton("−")
    up = QPushButton("+")
    for button, text in ((down, "减少数值"), (up, "增加数值")):
        button.setObjectName("StepperButton")
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setAutoRepeat(True)
    down.clicked.connect(spin.stepDown)
    up.clicked.connect(spin.stepUp)
    spin.valueChanged.connect(
        lambda v: (
            down.setEnabled(v > spin.minimum()),
            up.setEnabled(v < spin.maximum()),
        )
    )
    down.setEnabled(spin.value() > spin.minimum())
    up.setEnabled(spin.value() < spin.maximum())
    layout.addWidget(down)
    layout.addWidget(spin, 1)
    layout.addWidget(up)
    return row, down, up
