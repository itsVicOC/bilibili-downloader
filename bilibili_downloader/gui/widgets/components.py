"""Shared presentation primitives; no service or persistence ownership."""

from PySide6.QtCore import QByteArray, QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.styles import UI_METRICS, theme_palette
from bilibili_downloader.gui.widgets.glass_surface import GlassFrame
from bilibili_downloader.gui.widgets.header_backdrop import (
    HEADER_HEIGHT,
    paint_header_backdrop,
)
from bilibili_downloader.gui.widgets.motion import StateTransition

_ICON_PATHS = {
    "appearance": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z"/>',
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
    return theme_palette(
        bool(app and app.property("darkTheme")),
        app.property("colorTheme") if app else "star_trail",
    )


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
        self._nav_transition = StateTransition(self, float(role == "NavButtonActive"))

    def setObjectName(self, name):
        super().setObjectName(name)
        if hasattr(self, "_nav_transition"):
            self._nav_transition.to(name == "NavButtonActive")

    def _sync_icon(self):
        color = palette().active_text if self.objectName() == "NavButtonActive" else None
        self.setIcon(line_icon(self.icon_name, color))

    def event(self, event):
        if event.type() == QEvent.StyleChange and hasattr(self, "icon_name"):
            self._sync_icon()
            if hasattr(self, "_nav_transition"):
                self._nav_transition.to(self.objectName() == "NavButtonActive")
        return super().event(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not hasattr(self, "_nav_transition") or self._nav_transition.value <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(palette().accent)
        color.setAlphaF(self._nav_transition.value)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        height = 8 + 12 * self._nav_transition.value
        painter.drawRoundedRect(QRectF(2, (self.height() - height) / 2, 3, height), 1.5, 1.5)
        painter.end()

    def set_compact(self, compact):
        self.setText("" if compact else self.full_text)


class AccountButton(IconButton):
    """Keep the account avatar through theme and compact-layout changes."""

    def __init__(self, parent=None):
        self._avatar = QPixmap()
        super().__init__("未登录", "account", "SidebarAction", parent)

    def set_compact(self, compact):
        if self.property("compact") != compact:
            self.setProperty("compact", compact)
            repolish(self)
        super().set_compact(compact)

    def setText(self, text):
        # Usernames are literal text, including any ampersands.
        super().setText(text.replace("&", "&&"))

    def set_avatar(self, data: bytes = b""):
        self._avatar = QPixmap()
        if data:
            self._avatar.loadFromData(data)
        self._sync_icon()

    def account_icon(self):
        """Give the account view the source pixels rather than a sidebar thumbnail."""
        return QIcon(self._avatar) if not self._avatar.isNull() else line_icon("account", size=64)

    def _sync_icon(self):
        if self._avatar.isNull():
            self.setIconSize(QSize(20, 20))
            super()._sync_icon()
            return
        size = 28
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(QRectF(0, 0, size * 2, size * 2))
        painter.setClipPath(path)
        scaled = self._avatar.scaled(
            pixmap.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        painter.drawPixmap(
            (pixmap.width() - scaled.width()) // 2,
            (pixmap.height() - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        pixmap.setDevicePixelRatio(2)
        self.setIconSize(QSize(size, size))
        self.setIcon(QIcon(pixmap))


class ElidedLabel(QLabel):
    """Single-line text with its full value available to hover and assistive tools."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._sync_text()

    def _sync_text(self):
        super().setText(self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, max(1, self.width())))

    def resizeEvent(self, event):
        self._sync_text()
        super().resizeEvent(event)


class ActionBar(GlassFrame):
    """A stable, readable surface for workspace confirmation actions."""

    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent)
        self.setObjectName("ActionBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(UI_METRICS.settings_bar_height if compact else 72)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(16, 6 if compact else 12, 16, 6 if compact else 12)
        self.row.setSpacing(16)


class ReadOnlyPath(QLineEdit):
    """Selectable full path, with a whole-value copy action even when clipped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FooterPath")
        self.setReadOnly(True)
        self.setFixedHeight(22)
        self.setMinimumWidth(0)
        self.setAccessibleName("完整保存目录")
        self._full_text = ""

    def set_full_text(self, text):
        if text == self.text():
            return
        self._full_text = text
        self.setText(text)
        self.setToolTip(text)
        self.setCursorPosition(0)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.addSeparator()
        menu.addAction("复制完整路径", lambda: QApplication.clipboard().setText(self.text().removeprefix("保存至 ")))
        menu.exec(event.globalPos())
        menu.deleteLater()


class OutputActionBar(ActionBar):
    """Shared fixed output confirmation card for single and batch downloads."""

    edit_requested = Signal()
    submit_requested = Signal()
    directory_requested = Signal()

    def __init__(self, status="待解析", parent=None):
        super().__init__(parent)
        self.setObjectName("OutputActionBar")
        self.setAccessibleName("下载输出与队列操作")
        row = self.row
        row.setContentsMargins(16, 8, 16, 8)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        heading = QHBoxLayout()
        heading.setSpacing(12)
        self.status = QLabel(status)
        self.status.setObjectName("OutputSelection")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setMinimumWidth(76)
        heading.addWidget(self.status)
        self.specs = ElidedLabel()
        self.specs.setObjectName("MetaLabel")
        heading.addWidget(self.specs, 1)
        copy.addLayout(heading)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.directory = ReadOnlyPath()
        path_row.addWidget(self.directory, 1)
        self.directory_button = QPushButton("修改目录")
        self.directory_button.setObjectName("TextButton")
        self.directory_button.setFixedHeight(32)
        self.directory_button.setFocusPolicy(Qt.StrongFocus)
        self.directory_button.clicked.connect(self.directory_requested.emit)
        path_row.addWidget(self.directory_button)
        copy.addLayout(path_row)
        row.addLayout(copy, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)
        self.edit_button = QPushButton("修改规格")
        self.edit_button.setObjectName("OutputSecondaryButton")
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setAutoDefault(False)
        self.edit_button.setFocusPolicy(Qt.StrongFocus)
        self.edit_button.clicked.connect(self.edit_requested.emit)
        self.actions.addWidget(self.edit_button)
        self.primary_button = QPushButton("加入下载队列")
        self.primary_button.setObjectName("OutputPrimaryButton")
        self.primary_button.setFixedHeight(44)
        self.primary_button.setMinimumWidth(128)
        self.primary_button.setAutoDefault(False)
        self.primary_button.setFocusPolicy(Qt.StrongFocus)
        self.primary_button.setCursor(Qt.PointingHandCursor)
        self.primary_button.setEnabled(False)
        self.primary_button.clicked.connect(self.submit_requested.emit)
        self.actions.addWidget(self.primary_button)


class WindowDragSurface(QFrame):
    """Move the native window from unused chrome, leaving controls interactive."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window().windowHandle():
            if self.window().windowHandle().startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class PageHeader(WindowDragSurface):
    def __init__(self, title, caption, parent=None):
        super().__init__(parent)
        self.setObjectName("PageHeader")
        self.setAccessibleName(title)
        self.setAccessibleDescription(caption)
        self.setFixedHeight(HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel(title)
        self.title.setObjectName("PageTitle")
        # Keep the caption API for callers, without a second visual heading.
        self.caption = QLabel(caption, self)
        self.caption.setObjectName("Caption")
        self.caption.hide()
        row.addWidget(self.title, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)

    def set_shell_geometry(self, sidebar_width, margins):
        left, top, right, bottom = margins
        self.layout().setContentsMargins(max(24, left - sidebar_width), top, right, bottom)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        app = QApplication.instance()
        paint_header_backdrop(
            painter, self.rect(), bool(app.property("darkTheme")),
            app.property("colorTheme"),
        )
        painter.end()


class SectionCard(GlassFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.body = QVBoxLayout(self)
        padding = UI_METRICS.card_padding
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(12)
        self.header = QHBoxLayout()
        if title:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            self.header.addWidget(label)
        self.header.addStretch()
        if title:
            self.body.addLayout(self.header)


class CollapsibleSection(SectionCard):
    """Keep advanced fields discoverable without consuming the first screen."""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.toggle = DisclosureButton("展开")
        self.toggle.setObjectName("TextButton")
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName(f"展开或收起{title}")
        self.header.addWidget(self.toggle)
        self.content = QWidget()
        self.body.addWidget(self.content)
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(12)
        self.content.hide()
        self.toggle.toggled.connect(self.set_expanded)

    def set_expanded(self, expanded):
        self.toggle.setChecked(expanded)
        self.toggle.setText("收起" if expanded else "展开")
        self.content.setVisible(expanded)


class DisclosureButton(QPushButton):
    """Animate the disclosure glyph without delaying content or validation."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setProperty("disclosure", True)
        self._turn = StateTransition(self, duration=UI_METRICS.motion_expand)
        self.toggled.connect(lambda checked: self._turn.to(float(checked)))

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() - 14, self.height() / 2)
        painter.rotate(180 * self._turn.value)
        painter.setPen(QPen(QColor(palette().muted), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(-3, -1.5), QPointF(0, 1.5))
        painter.drawLine(QPointF(0, 1.5), QPointF(3, -1.5))
        painter.end()


class CommandBar(GlassFrame):
    """Keep filters before actions in visual and keyboard order when wrapped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolSurface")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(12, 8, 12, 8)
        self._grid.setSpacing(8)
        self._filters = QWidget()
        self._actions = QWidget()
        self.filters = QHBoxLayout(self._filters)
        self.actions = QHBoxLayout(self._actions)
        for row in (self.filters, self.actions):
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
        self._grid.addWidget(self._filters, 0, 0)
        self._grid.addWidget(self._actions, 0, 1)
        self._grid.setColumnStretch(0, 1)
        self.wrapped = False

    def _reflow(self, width):
        required = self._filters.sizeHint().width() + self._actions.sizeHint().width() + 32
        wrapped = width < max(UI_METRICS.toolbar_wrap_width, required)
        if self.wrapped != wrapped:
            self.wrapped = wrapped
            self._grid.removeWidget(self._actions)
            self._grid.addWidget(self._actions, 1 if wrapped else 0, 0 if wrapped else 1,
                                 1, 2 if wrapped else 1, Qt.AlignRight)

    def event(self, event):
        if event.type() == QEvent.LayoutRequest and hasattr(self, "wrapped"):
            self._reflow(self.width())
        return super().event(event)

    def resizeEvent(self, event):
        self._reflow(event.size().width())
        super().resizeEvent(event)


class ResponsiveSplit(QWidget):
    """Reflow existing panes using their actual viewport allocation."""

    def __init__(self, first, second, parent=None):
        super().__init__(parent)
        self.row = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(UI_METRICS.section_gap)
        self.row.addWidget(first, 3, Qt.AlignTop)
        self.row.addWidget(second, 2, Qt.AlignTop)

    def resizeEvent(self, event):
        from bilibili_downloader.gui.layout_policy import output_side_by_side
        wide = output_side_by_side(event.size().width())
        self.row.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
        self.row.setStretch(0, 3 if wide else 0)
        self.row.setStretch(1, 2 if wide else 0)
        super().resizeEvent(event)


class ResponsiveFields(QWidget):
    """Use a second form column only when both controls have room to breathe."""

    def __init__(self, parent=None, *, column_width=280):
        super().__init__(parent)
        self._column_width = column_width
        self._rows = []
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)

    def add_field(self, field):
        self._rows.append(field)
        self._reflow()

    def _reflow(self):
        columns = 2 if self.width() >= self._column_width * 2 else 1
        if columns == self._columns and self._grid.count() == len(self._rows):
            return
        self._columns = columns
        for index, field in enumerate(self._rows):
            self._grid.removeWidget(field)
            alignment = Qt.AlignTop
            if field.maximumWidth() < 16777215:
                alignment |= Qt.AlignLeft
            self._grid.addWidget(field, index // columns, index % columns, alignment)
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1 if columns == 2 else 0)

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)


def help_text(text):
    label = QLabel(text)
    label.setObjectName("MetaLabel")
    label.setWordWrap(True)
    label.setTextFormat(Qt.PlainText)
    return label


class StatusBadge(QLabel):
    def __init__(self, text="", tone="muted", parent=None):
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.set_tone(tone)

    def set_tone(self, tone):
        self.setProperty("tone", tone)
        repolish(self)


class TaskDetailPanel(SectionCard):
    """A scan-friendly summary with complete, selectable diagnostics on demand."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._full_text = ""
        self.body.setSpacing(8)
        heading = QHBoxLayout()
        self.title = ElidedLabel()
        self.title.setObjectName("SectionTitle")
        self.status = StatusBadge()
        heading.addWidget(self.title, 1)
        heading.addWidget(self.status)
        self.body.addLayout(heading)
        self.specs = ElidedLabel()
        self.specs.setObjectName("DetailValue")
        self.path = ReadOnlyPath()
        self.diagnostics = ElidedLabel()
        self.diagnostics.setObjectName("MetaLabel")
        self.body.addWidget(self.specs)
        footer = QHBoxLayout()
        footer.addWidget(self.path, 1)
        self.details_button = QPushButton("完整详情")
        self.details_button.setObjectName("TextButton")
        self.details_button.clicked.connect(lambda: MessageBox("任务详情", self._full_text, self).exec())
        footer.addWidget(self.details_button)
        self.body.addLayout(footer)
        self.body.addWidget(self.diagnostics)

    def set_details(self, title, status, specs, path, diagnostics="", tone="muted"):
        self.title.set_full_text(title)
        self.status.setText(status.replace("\n", " · "))
        self.status.set_tone(tone)
        self.specs.set_full_text(specs.replace("\n", " · "))
        self.specs.setVisible(bool(specs))
        self.path.set_full_text(f"保存位置：{path}" if path else "保存位置尚未生成")
        self.diagnostics.set_full_text(diagnostics.replace("\n", " · "))
        self.diagnostics.setVisible(bool(diagnostics))
        self.diagnostics.setProperty("tone", tone if tone in ("warning", "danger") else "muted")
        repolish(self.diagnostics)
        self._full_text = "\n".join(filter(None, (title, status, specs, f"保存位置：{path}" if path else "", diagnostics)))

    def toPlainText(self):
        return self._full_text


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
        if len(text) > 700 or text.count("\n") > 12:
            self.setInformativeText("完整信息可在下方选择、复制。")
            from PySide6.QtWidgets import QTextEdit
            self.setDetailedText(text)
            self.reading_area = self.findChild(QTextEdit)
            self.reading_area.setMinimumWidth(360)
            self.reading_area.setFixedHeight(200)
            self.reading_area.setAccessibleName("完整信息")
            self._reader_opened = False
        else:
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
        self._layout_reading_area()

    def _layout_reading_area(self):
        if not hasattr(self, "reading_area"):
            return
        buttons = self.findChild(QDialogButtonBox)
        for button in buttons.buttons():
            if buttons.buttonRole(button) == QDialogButtonBox.ActionRole:
                if not self._reader_opened:
                    self._reader_opened = True
                    button.click()
                    button.clicked.connect(lambda: button.setText("收起详情" if self.reading_area.isVisible() else "展开详情"))
                button.setText("收起详情" if self.reading_area.isVisible() else "展开详情")
                break

    def _sync_icon(self):
        p = palette()
        color = {"danger": p.danger, "warning": p.warning, "success": p.success}.get(
            self._tone, p.muted
        )
        self.setIconPixmap(line_icon(self._tone, color, 28).pixmap(28, 28))

    def changeEvent(self, event):
        if event.type() == QEvent.StyleChange and hasattr(self, "_tone"):
            self._sync_icon()
            if self.isVisible():
                self._layout_reading_area()
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
    def __init__(self, label, control, parent=None, *, stacked=False):
        super().__init__(parent)
        self.control = control
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        row = QVBoxLayout() if stacked else QHBoxLayout()
        self._field_layout = row
        row.setSpacing(8 if stacked else 12)
        self.label = QLabel(label)
        self.label.setObjectName("FieldLabel")
        self.label.setBuddy(control)
        if not control.accessibleName():
            control.setAccessibleName(label)
        if not stacked:
            self.label.setFixedWidth(92)
        row.addWidget(self.label)
        row.addWidget(control, 1)
        column.addLayout(row)
        self._error_row = QWidget()
        errors = QHBoxLayout(self._error_row)
        self._errors_layout = errors
        errors.setContentsMargins(0 if stacked else 104, 0, 0, 0)
        self.error = QLabel()
        self.error.setObjectName("FieldError")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.PlainText)
        errors.addWidget(self.error)
        column.addWidget(self._error_row)
        self._error_row.hide()

    def set_stacked(self, stacked):
        self._field_layout.setDirection(QBoxLayout.TopToBottom if stacked else QBoxLayout.LeftToRight)
        self._field_layout.setSpacing(8)
        self.label.setMinimumWidth(0 if stacked else 76)
        self.label.setMaximumWidth(16777215 if stacked else 76)
        self._errors_layout.setContentsMargins(0 if stacked else 84, 0, 0, 0)

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
    row.setFocusProxy(spin)
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
