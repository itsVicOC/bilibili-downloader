"""Shared presentation primitives; no service or persistence ownership."""

import weakref

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QObject,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTextLayout,
    QTextOption,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.layout_policy import path_preferred_width
from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.styles import (
    UI_METRICS,
    background_reading_alpha,
    theme_palette,
    wallpaper_palette,
)
from bilibili_downloader.gui.widgets.background_readability import wallpaper_active
from bilibili_downloader.gui.widgets.dialog_shell import (
    paint_dialog_glass,
    prepare_dialog,
    remember_focus,
)
from bilibili_downloader.gui.widgets.glass_surface import (
    GlassFrame,
    ScrollEdge,
)
from bilibili_downloader.gui.widgets.header_backdrop import HEADER_HEIGHT
from bilibili_downloader.gui.widgets.motion import StateTransition
from bilibili_downloader.gui.widgets.popup_menu import PopupMenu as PopupMenu
from bilibili_downloader.gui.widgets.responsive_actions import (
    ActionButton,
    FlowLayout,
    ResponsiveActions,
)
from bilibili_downloader.gui.widgets.text_menu import text_context_menu

_ICON_PATHS = {
    "appearance": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    "live": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m9 9 6 3-6 3z"/>',
    "audio": '<path d="M9 17V5l11-2v12M9 8l11-2"/><ellipse cx="6" cy="17" rx="3" ry="2"/><ellipse cx="17" cy="15" rx="3" ry="2"/>',
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
    "external": '<path d="M13 4h7v7m0-7-9 9m0-8H5v14h14v-6"/>',
}


def palette(widget=None):
    app = QApplication.instance()
    dark = bool(app and app.property("darkTheme"))
    colors = theme_palette(
        dark,
        app.property("colorTheme") if app else "star_trail",
    )
    if widget is not None and wallpaper_active(widget):
        return wallpaper_palette(colors, dark, clear=not widget.property("readingView"))
    return colors


def line_icon(name, color=None, size=24):
    color = color or palette().muted
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{UI_METRICS.icon_stroke}" stroke-linecap="round" '
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
        if role in {"NavButton", "NavButtonActive"}:
            self._press_transition = StateTransition(self)
            self.pressed.connect(lambda: self._press_transition.to(1))
            self.released.connect(lambda: self._press_transition.to(0))

    def setObjectName(self, name):
        super().setObjectName(name)
        if hasattr(self, "_nav_transition"):
            self._nav_transition.to(name == "NavButtonActive")

    def _sync_icon(self):
        colors = palette(self)
        color = colors.active_text if self.objectName() == "NavButtonActive" else colors.muted
        self.setIcon(line_icon(self.icon_name, color))

    def event(self, event):
        if event.type() == QEvent.StyleChange and hasattr(self, "icon_name"):
            self._sync_icon()
            if hasattr(self, "_nav_transition"):
                self._nav_transition.to(self.objectName() == "NavButtonActive")
        return super().event(event)

    def paintEvent(self, event):
        if hasattr(self, "_press_transition"):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            colors = palette(self)
            rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
            for shade, opacity in ((colors.subtle_selection, self._nav_transition.value),
                                   (colors.control_pressed, self._press_transition.value)):
                if opacity > 0:
                    color = QColor(shade)
                    color.setAlphaF(opacity)
                    painter.setBrush(color)
                    painter.drawRoundedRect(rect, UI_METRICS.radius, UI_METRICS.radius)
            painter.end()
        super().paintEvent(event)

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

    full_text_changed = Signal(str)

    def __init__(self, text="", parent=None, *, elide_mode=Qt.ElideRight):
        super().__init__(parent)
        self._elide_mode = elide_mode
        self._full_text = text
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._sync_text()
        self.full_text_changed.emit(text)

    def _sync_text(self):
        super().setText(self.fontMetrics().elidedText(self._full_text, self._elide_mode, max(1, self.width())))

    def resizeEvent(self, event):
        self._sync_text()
        super().resizeEvent(event)


class PreviewTitle(QLabel):
    """Keep the full plain-text title while bounding its painted preview."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.compact = False
        self.line_limit = 2

    def set_full_text(self, text):
        self.setText(text)
        self.setToolTip(text)
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QSize(280, self.heightForWidth(self.width()))

    def minimumSizeHint(self):
        return QSize(0, self.fontMetrics().lineSpacing() * (1 if self.compact else self.line_limit))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        lines = 1 if self.compact and self.fontMetrics().horizontalAdvance(self.text()) <= width else 2
        return self.fontMetrics().lineSpacing() * min(lines, self.line_limit)

    def resizeEvent(self, event):
        if self.compact:
            self.updateGeometry()
        super().resizeEvent(event)

    def paintEvent(self, event):
        text = " ".join(self.text().splitlines())
        rect = self.contentsRect()
        metrics = self.fontMetrics()
        layout = QTextLayout(text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        first = layout.createLine()
        if not first.isValid():
            layout.endLayout()
            return
        first.setLineWidth(max(1, rect.width()))
        length = first.textLength()
        layout.endLayout()
        encoded = text.encode("utf-16-le")
        lines = [encoded[:length * 2].decode("utf-16-le").rstrip()]
        remaining = encoded[length * 2:].decode("utf-16-le").strip()
        if self.line_limit == 1:
            lines = [metrics.elidedText(text, Qt.ElideRight, rect.width())]
        elif remaining:
            lines.append(metrics.elidedText(remaining, Qt.ElideRight, rect.width()))
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        for index, line in enumerate(lines):
            painter.drawText(QRect(rect.left(), rect.top() + index * metrics.lineSpacing(),
                                   rect.width(), metrics.lineSpacing()),
                             Qt.AlignLeft | Qt.AlignVCenter, line)


class ActionBar(GlassFrame):
    """A stable, readable surface for workspace confirmation actions."""

    def __init__(self, parent=None, *, compact=False):
        super().__init__(parent, glass=True)
        self.setProperty("clearGlass", True)
        self.setObjectName("ActionBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._base_height = UI_METRICS.settings_bar_height if compact else 72
        self.setMinimumHeight(self._base_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._layout_queued = False
        self.row = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.row.setContentsMargins(16, 8 if compact else 12, 16, 8 if compact else 12)
        self.row.setSpacing(16)

    def _reflow(self):
        required = sum(self.row.itemAt(i).minimumSize().width() for i in range(self.row.count()))
        margins = self.row.contentsMargins()
        required += margins.left() + margins.right() + self.row.spacing() * max(0, self.row.count() - 1)
        self.row.setDirection(QBoxLayout.TopToBottom if required > self.width() else QBoxLayout.LeftToRight)
        self.setFixedHeight(max(self._base_height, self.row.sizeHint().height() + self.frameWidth() * 2))

    def _schedule_layout(self):
        if not self._layout_queued:
            self._layout_queued = True
            QTimer.singleShot(0, self, self._settle_layout)

    def _settle_layout(self):
        self._layout_queued = False
        self._reflow()

    def event(self, event):
        if event.type() in (QEvent.LayoutRequest, QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "row"):
            self._schedule_layout()
        return super().event(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_layout()


class ActionBarStack(QStackedWidget):
    """Size the shell from the active bar, not a hidden bar's old viewport."""

    def _bar_height(self):
        bar = self.currentWidget()
        return bar.minimumHeight() if bar is not None else 0

    def sizeHint(self):
        hint = self.currentWidget().sizeHint() if self.currentWidget() else QSize()
        return QSize(hint.width(), self._bar_height())

    def minimumSizeHint(self):
        hint = self.currentWidget().minimumSizeHint() if self.currentWidget() else QSize()
        return QSize(hint.width(), self._bar_height())

    def hasHeightForWidth(self):
        return False

    def heightForWidth(self, width):
        return self._bar_height()


class ReadOnlyPath(QLineEdit):
    """Selectable full path, with a whole-value copy action even when clipped."""

    def __init__(self, parent=None, *, show_end=False):
        super().__init__(parent)
        self.setObjectName("FooterPath")
        self.setReadOnly(True)
        self.setFixedHeight(22)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setAccessibleName("完整保存目录")
        self._full_text = ""
        self._copy_value = ""
        self._show_end = show_end
        if show_end:
            self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._update_height()

    def _update_height(self):
        height = max(22, self.fontMetrics().height() + 2)
        if self.height() != height:
            self.setFixedHeight(height)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange) and hasattr(self, "_copy_value"):
            self._update_height()

    def set_full_text(self, text, *, copy_value=None):
        self._copy_value = copy_value if copy_value is not None else text.removeprefix("保存至 ")
        self.setToolTip(copy_value if copy_value is not None else text)
        if text == self.text():
            return
        self._full_text = text
        self.setText(text)
        if self._show_end:
            self.end(False)
        else:
            self.setCursorPosition(0)
        self.updateGeometry()

    def sizeHint(self):
        return QSize(path_preferred_width(self.fontMetrics(), self.text()), max(22, self.fontMetrics().height() + 2))

    def minimumSizeHint(self):
        return QSize(0, max(22, self.fontMetrics().height() + 2))

    def createStandardContextMenu(self):
        return text_context_menu(self)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        menu.exec(event.globalPos())
        menu.deleteLater()


class OutputActionBar(ActionBar):
    """Shared fixed output confirmation card for single and batch downloads."""

    edit_requested = Signal()
    submit_requested = Signal()
    directory_requested = Signal()
    review_requested = Signal()

    def __init__(self, status="待解析", parent=None):
        super().__init__(parent)
        self.setObjectName("OutputActionBar")
        self.setAccessibleName("下载输出与队列操作")
        row = self.row
        row.setContentsMargins(16, 8, 16, 8)
        self._copy = QWidget()
        copy = QVBoxLayout(self._copy)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(4)
        heading = QBoxLayout(QBoxLayout.LeftToRight)
        self._heading = heading
        heading.setSpacing(12)
        self.status = QLabel(status)
        self.status.setObjectName("OutputSelection")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(76)
        heading.addWidget(self.status)
        self.specs = ElidedLabel()
        self.specs.setObjectName("MetaLabel")
        self._compact_output = False
        self.specs.full_text_changed.connect(lambda text: self.specs.setVisible(bool(text) and not self._compact_output))
        self.specs.hide()
        heading.addWidget(self.specs, 1)
        copy.addLayout(heading)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.directory = ReadOnlyPath()
        path_row.addWidget(self.directory)
        self.directory_button = ActionButton("修改目录")
        self.directory_button.setObjectName("TextButton")
        self.directory_button.setFixedHeight(32)
        self.directory_button.setFocusPolicy(Qt.StrongFocus)
        self.directory_button.setCursor(Qt.PointingHandCursor)
        self.directory_button.clicked.connect(self.directory_requested.emit)
        path_row.addWidget(self.directory_button)
        self.review_button = ActionButton("完整配置")
        self.review_button.setObjectName("TextButton")
        self.review_button.setFixedHeight(32)
        self.review_button.clicked.connect(self.review_requested.emit)
        path_row.addStretch(1)
        copy.addLayout(path_row)
        row.addWidget(self._copy, 1)
        self.action_strip = ResponsiveActions()
        self.actions = self.action_strip.row
        row.addWidget(self.action_strip)
        self.actions.addWidget(self.review_button)
        self.edit_button = ActionButton("修改规格")
        self.edit_button.setProperty("actionPriority", 50)
        self.edit_button.setObjectName("OutputSecondaryButton")
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.setAutoDefault(False)
        self.edit_button.setFocusPolicy(Qt.StrongFocus)
        self.edit_button.clicked.connect(self.edit_requested.emit)
        self.actions.addWidget(self.edit_button)
        self.primary_button = ActionButton("加入队列")
        self.primary_button.setProperty("alwaysVisible", True)
        self.primary_button.setObjectName("OutputPrimaryButton")
        self.primary_button.setFixedHeight(44)
        self.primary_button.setMinimumWidth(128)
        self.primary_button.setAutoDefault(False)
        self.primary_button.setFocusPolicy(Qt.StrongFocus)
        self.primary_button.setCursor(Qt.PointingHandCursor)
        self.primary_button.setEnabled(False)
        self.primary_button.clicked.connect(self.submit_requested.emit)
        self.actions.addWidget(self.primary_button)

    def set_compact_output(self):
        self._compact_output = True
        self.specs.hide()
        self.edit_button.hide()
        self.review_button.hide()
        self.action_strip.schedule()

    def _reflow(self):
        if not hasattr(self, "action_strip"):
            return
        # Reserve the common count label in both empty and ready workspaces.
        # Recompute with the actual font so system text scaling keeps them aligned.
        self.primary_button.ensurePolished()
        self.primary_button.setMinimumWidth(max(
            128, self.primary_button.fontMetrics().horizontalAdvance("加入队列（99 项）") + 32,
        ))
        margins = self.row.contentsMargins()
        available = self.width() - margins.left() - margins.right()
        status_width = self.status.fontMetrics().horizontalAdvance(self.status.text()) + 8
        copy_width = max(self.directory_button.sizeHint().width() + 96, min(320, status_width))
        minimum = copy_width + self.primary_button.sizeHint().width() + self.action_strip.more.sizeHint().width() + 24
        stacked = available < minimum
        self.row.setDirection(QBoxLayout.TopToBottom if stacked else QBoxLayout.LeftToRight)
        self._heading.setDirection(QBoxLayout.TopToBottom if self.specs._full_text and status_width + 120 > self._copy.width() else QBoxLayout.LeftToRight)
        self.status.setMinimumWidth(min(status_width, max(76, self._copy.width())))
        self.action_strip.force_overflow(self.review_button, stacked)
        self.action_strip.reflow()
        height = self.row.totalHeightForWidth(self.width())
        self.setFixedHeight(max(self._base_height, height if height >= 0 else self.row.sizeHint().height()))


class WindowDragSurface(GlassFrame):
    """Move the native window from unused chrome, leaving controls interactive."""

    def __init__(self, parent=None):
        super().__init__(parent, glass=True)

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
        self.setProperty("glassEdge", Qt.BottomEdge)
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

class SectionCard(GlassFrame):
    def __init__(self, title="", parent=None, *, glass=False):
        super().__init__(parent, glass=glass, reading=not glass)
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

    def set_plain(self):
        self.setProperty("readingSurface", False)
        self.setProperty("sectionStyle", "plain")


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


def paint_segment_track(painter, rect, colors, *, dark, wallpaper):
    fill = QColor(colors.surface_raised)
    opacity = 144
    if wallpaper:
        foreground = wallpaper_palette(colors, dark).muted
        opacity = max(opacity, background_reading_alpha(colors.surface_raised, foreground, colors.text))
    fill.setAlpha(opacity)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(fill)
    painter.drawRoundedRect(QRectF(rect).adjusted(0, 2, 0, -2), UI_METRICS.radius + 2, UI_METRICS.radius + 2)
    painter.restore()


class WorkspaceTabBar(QTabBar):
    def __init__(self):
        super().__init__()
        self.setObjectName("WorkspaceTabBar")
        self.setExpanding(False)
        self.setDrawBase(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_segment_track(painter, self.rect(), palette(), dark=bool(QApplication.instance().property("darkTheme")),
                            wallpaper=wallpaper_active(self))
        painter.end()
        super().paintEvent(event)


class WorkspaceTabs(QTabWidget):
    """Group the workspace's adjacent tabs with a single quiet fill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkspaceTabs")
        self.setTabBar(WorkspaceTabBar())


class CommandBar(QWidget):
    """Keep filters before actions in visual and keyboard order when wrapped."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolSurface")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 4, 0, 4)
        self._grid.setSpacing(8)
        self._filters = QWidget()
        self._actions = ResponsiveActions()
        self._status = None
        self.compact_actions = ()
        self.filters = FlowLayout(self._filters)
        self.actions = self._actions.row
        for row in (self.filters, self.actions):
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
        self._grid.addWidget(self._filters, 0, 0)
        self._grid.addWidget(self._actions, 0, 1)
        self._grid.setColumnStretch(0, 1)
        self.wrapped = False

    def set_context(self, widget):
        self._grid.addWidget(widget, 2, 0, 1, 2)

    def set_status(self, widget):
        self._status = widget
        self._place_controls(self.wrapped)

    def _place_controls(self, wrapped):
        self._grid.removeWidget(self._actions)
        if self._status is None:
            self._grid.addWidget(self._actions, 1 if wrapped else 0, 0 if wrapped else 1,
                                 1, 2 if wrapped else 1, Qt.AlignRight)
        else:
            self._grid.removeWidget(self._filters)
            self._grid.removeWidget(self._status)
            self._grid.addWidget(self._filters, 0, 0, 1, 2 if wrapped else 1)
            self._grid.addWidget(self._actions, 1 if wrapped else 0, 1, Qt.AlignRight)
            self._grid.addWidget(self._status, 1, 0, 1, 1 if wrapped else 2)

    def _reflow(self, width):
        for button in self.compact_actions:
            self._actions.force_overflow(button, width < 880)
        required = self._filters.sizeHint().width() + self._actions.sizeHint().width() + 32
        wrapped = width < max(UI_METRICS.toolbar_wrap_width, required)
        if self.wrapped != wrapped:
            self.wrapped = wrapped
            self._place_controls(wrapped)

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
        self._hidden_rows = set()
        self._visible_rows = ()
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)

    def add_field(self, field):
        self._rows.append(field)
        self._reflow()

    def set_field_visible(self, field, visible):
        if visible:
            self._hidden_rows.discard(field)
        else:
            self._hidden_rows.add(field)
        field.setVisible(visible)
        self._reflow()

    def _reflow(self):
        columns = 2 if self.width() >= self._column_width * 2 else 1
        visible = tuple(field for field in self._rows if field not in self._hidden_rows)
        if columns == self._columns and visible == self._visible_rows:
            return
        self._columns = columns
        self._visible_rows = visible
        for field in self._rows:
            self._grid.removeWidget(field)
        for index, field in enumerate(visible):
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
        self._result_item = self._result_outcome = self._result_repair = None
        self._result_media_state = ""
        self.body.setSpacing(8)
        heading = QBoxLayout(QBoxLayout.LeftToRight)
        self._heading_layout = heading
        self.title = PreviewTitle("")
        self.title.compact = True
        self.title.line_limit = 1
        self.title.setObjectName("SectionTitle")
        self.status = StatusBadge()
        heading.addWidget(self.title, 1)
        heading.addWidget(self.status)
        self.body.addLayout(heading)
        self.result_row = QWidget()
        result_layout = FlowLayout(self.result_row)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(8)
        self.result_badges = [StatusBadge() for _ in range(3)]
        for badge in self.result_badges:
            result_layout.addWidget(badge)
        result_layout.addStretch()
        self.result_row.hide()
        self.body.addWidget(self.result_row)
        self.specs = ElidedLabel()
        self.specs.setObjectName("DetailValue")
        self.path = ReadOnlyPath()
        self.diagnostics = ElidedLabel()
        self.diagnostics.setObjectName("MetaLabel")
        self.body.addWidget(self.specs)
        self._detail_footer = QWidget()
        footer = QBoxLayout(QBoxLayout.LeftToRight, self._detail_footer)
        self._footer_layout = footer
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(self.path, 1)
        self.action_strip = ResponsiveActions()
        self.details_button = ActionButton("完整详情")
        self.details_button.setObjectName("TextButton")
        self.details_button.clicked.connect(self.show_details)
        self.primary_action = ActionButton()
        self.primary_action.setProperty("alwaysVisible", True)
        self.primary_action.setObjectName("TableSubtleButton")
        self.secondary_action = ActionButton()
        self.secondary_action.setObjectName("TableSubtleButton")
        for button in (self.primary_action, self.secondary_action):
            button.hide()
            self.action_strip.row.addWidget(button)
        self.details_button.setProperty("actionPriority", 20)
        self.action_strip.row.addWidget(self.details_button)
        footer.addWidget(self.action_strip)
        self.body.addWidget(self._detail_footer)
        self.body.addWidget(self.diagnostics)
        self.body.addStretch(1)

    def set_docked(self, docked):
        direction = QBoxLayout.TopToBottom if docked else QBoxLayout.LeftToRight
        self.title.line_limit = 2 if docked else 1
        self.title.updateGeometry()
        self.title.update()
        self._heading_layout.setDirection(direction)
        self._heading_layout.setAlignment(self.status, Qt.AlignLeft if docked else Qt.Alignment())
        self._footer_layout.setDirection(direction)
        self.setMinimumWidth(UI_METRICS.queue_detail_width if docked else 0)
        self.setMaximumWidth(UI_METRICS.queue_detail_width if docked else 16777215)

    def show_details(self):
        from bilibili_downloader.gui.dialogs.result_details import ResultDetailsDialog
        repair = self._result_repair
        dialog = ResultDetailsDialog("保存与处理详情", self._full_text, self,
                                     item=self._result_item, outcome=self._result_outcome,
                                     media_state=self._result_media_state,
                                     can_supplement=repair is not None)
        if dialog.exec() and dialog.repair_requested:
            repair()

    def set_actions(self, primary=None, secondary=None, *, secondary_required=False):
        self.secondary_action.setProperty("alwaysVisible", secondary_required)
        for button, action in ((self.primary_action, primary), (self.secondary_action, secondary)):
            if button.property("hasCallback"):
                button.clicked.disconnect()
            button.setProperty("hasCallback", bool(action))
            button.setVisible(bool(action))
            if action:
                button.setText(action[0])
                button.clicked.connect(action[1])
        self.action_strip.schedule()

    def set_result(self, item, outcome, *, media_state="", supplement=None):
        from bilibili_downloader.gui.dialogs.result_details import result_summary
        self._result_item, self._result_outcome = item, outcome
        self._result_repair = supplement
        self._result_media_state = media_state
        issues = len(outcome.warnings) + len(outcome.spec_warnings) if outcome else 0
        self.details_button.setText(f"完整详情（{issues}）" if issues else "完整详情")
        summaries = list(result_summary(item, outcome))
        if media_state:
            summaries[0] = media_state
        self.result_row.show()
        self.status.hide()
        for badge, text in zip(self.result_badges, summaries):
            badge.setText(text)
            badge.set_tone("danger" if "媒体异常" in text else "warning" if any(word in text for word in ("回退", "补全", "缺失", "无法")) else "muted" if "待" in text or "未选择" in text else "success")
        self.specs.hide()
        self.diagnostics.hide()
        if outcome:
            self._full_text = "\n".join(filter(None, (item.display_title, *summaries, *outcome.spec_warnings,
                                                      *outcome.warnings, outcome.media_verification.get("message", ""))))

    def set_details(self, title, status, specs, path, diagnostics="", tone="muted"):
        self._result_item = self._result_outcome = None
        self._result_repair = None
        self._result_media_state = ""
        self.details_button.setText("完整详情")
        self.result_row.hide()
        self.status.show()
        self.set_actions()
        self.title.set_full_text(title)
        self.status.setText(status.replace("\n", " · "))
        self.status.set_tone(tone)
        self.specs.set_full_text(specs.replace("\n", " · "))
        self.specs.setVisible(bool(specs))
        self.path.set_full_text(f"保存位置：{path}" if path else "保存位置未生成")
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
        remember_focus(self, parent)
        self.setWindowTitle(title)
        self.setTextFormat(Qt.RichText if rich_text else Qt.PlainText)
        self.setText(title)
        if len(text) > (700 if rich_text else 180) or text.count("\n") > 12:
            self.setInformativeText("可在下方选择、复制完整信息。")
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
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            | Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard
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
        prepare_dialog(self)
        for button in self.buttons():
            repolish(button)
        super().showEvent(event)
        self._layout_reading_area()

    def paintEvent(self, event):
        super().paintEvent(event)
        paint_dialog_glass(self)

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


class MascotIllustration(QWidget):
    """Decorative, scene-specific pixel art for an empty state."""

    _WIDE_SCENES = {
        "download_source", "live_empty", "downloads_empty",
        "recordings_empty", "recording_history_empty", "files_empty",
    }

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.art = QPixmap(asset_path(f"xiaoliu_state_{scene}.png"))
        if self.art.size() != QSize(96, 54):
            self.art = QPixmap(asset_path("xiaoliu.png"))
        self.setFixedSize(QSize(176, 99) if scene in self._WIDE_SCENES else QSize(112, 72))
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _event):
        if self.art.isNull():
            return
        size = self.art.size().scaled(self.size(), Qt.KeepAspectRatio)
        target = QRect(0, 0, size.width(), size.height())
        target.moveCenter(self.rect().center())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawPixmap(target, self.art)
        painter.end()


class InlineNotice(QWidget):
    """A local status within a summary row, without another full-width card."""

    def __init__(self, *, action="", callback=None, parent=None):
        super().__init__(parent)
        self.message = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.label = ElidedLabel()
        self.label.setObjectName("MetaLabel")
        row.addWidget(self.label, 1)
        self.action = QPushButton(action)
        self.action.setObjectName("TextButton")
        self.action.setFixedHeight(24)
        if callback:
            self.action.clicked.connect(callback)
        row.addWidget(self.action)
        self.hide()

    def set_message(self, text, tone="info"):
        self.message = text
        self.label.set_full_text(text)
        self.label.setProperty("tone", tone)
        repolish(self.label)
        self.setVisible(bool(text))


class EmptyState(QWidget):
    def __init__(self, title, description="", action="", callback=None, parent=None, *, scene):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(20, 20, 20, 20)
        column.setSpacing(8)
        column.addStretch()
        column.addWidget(MascotIllustration(scene), alignment=Qt.AlignCenter)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("SectionTitle")
            title_label.setAlignment(Qt.AlignCenter)
            column.addWidget(title_label)
        if description:
            desc = help_text(description)
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
    def __init__(self, label, control, parent=None, *, stacked=False, label_width=92):
        super().__init__(parent)
        self.control = control
        focus = control.focusProxy()
        if focus is None and control.focusPolicy() == Qt.NoFocus:
            focus = next((child for child in control.findChildren(QWidget)
                          if isinstance(child, (QLineEdit, QComboBox, QSpinBox))), None)
            if focus is not None:
                control.setFocusProxy(focus)
        self._error_control = focus or control
        self._field_description = self._error_control.accessibleDescription()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        row = QVBoxLayout() if stacked else QHBoxLayout()
        self._field_layout = row
        row.setSpacing(8 if stacked else 12)
        self.label = QLabel(label)
        self.label.setWordWrap(True)
        self.label.setObjectName("FieldLabel")
        self.label.setBuddy(self._error_control)
        if not control.accessibleName():
            control.setAccessibleName(label)
        if not self._error_control.accessibleName():
            self._error_control.setAccessibleName(label)
        if isinstance(self._error_control, QSpinBox):
            for button in control.findChildren(QPushButton):
                if button.objectName() == "StepperButton":
                    action = "减少" if button.text() == "−" else "增加"
                    button.setAccessibleName(action + label)
                    button.setToolTip(action + label)
        if not stacked:
            self.label.setFixedWidth(label_width)
        row.addWidget(self.label)
        row.addWidget(control, 1)
        column.addLayout(row)
        self._error_row = QWidget()
        errors = QHBoxLayout(self._error_row)
        self._errors_layout = errors
        errors.setContentsMargins(0 if stacked else label_width + row.spacing(), 0, 0, 0)
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
        if self._error_control is not self.control:
            self._error_control.setProperty("invalid", bool(message))
            repolish(self._error_control)
        self._error_control.setAccessibleDescription("\n".join(filter(None, (self._field_description, message))))


def scroll_area(body, *, scroll_edge=False):
    scroll = QScrollArea()
    scroll.setObjectName("WorkspaceScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(body)
    if scroll_edge:
        ScrollEdge(scroll)
    return scroll


class _FieldReveal(QObject):
    """Keep a newly revealed error visible through font/disclosure layout changes."""

    def __init__(self, scroll, field, margin):
        super().__init__(field)
        self.scroll, self.field = weakref.ref(scroll), weakref.ref(field)
        self.margin, self.queued, self.active = margin, False, True
        self.target = weakref.ref(field.control.focusProxy() or field.control)
        for widget in (field, scroll.widget(), scroll.viewport(), self.target()):
            widget.installEventFilter(self)
        scroll.verticalScrollBar().sliderPressed.connect(self.cancel)
        scroll.verticalScrollBar().rangeChanged.connect(self.schedule)
        scroll.verticalScrollBar().valueChanged.connect(self.schedule)
        self.schedule()

    def cancel(self):
        self.active = False

    def schedule(self, *_args):
        if self.active and not self.queued:
            self.queued = True
            QTimer.singleShot(0, self, self.locate)

    def locate(self):
        from shiboken6 import isValid
        self.queued = False
        scroll, field = self.scroll(), self.field()
        if not self.active or scroll is None or field is None or not isValid(scroll) or not isValid(field):
            return
        if not field.error.text():
            self.cancel()
            return
        ancestors = []
        current = field
        while current is not None and current is not scroll:
            ancestors.append(current)
            current = current.parentWidget()
        # Nested disclosure bodies can initially have zero height. Resolve
        # their hints bottom-up, then allocate geometry from the outer layout.
        for current in ancestors:
            if current.layout():
                current.layout().activate()
        for current in reversed(ancestors):
            if current.layout():
                current.layout().activate()
        center = field.mapTo(scroll.widget(), field.rect().center())
        scroll.ensureVisible(center.x(), center.y(), field.width() // 2, field.height() // 2 + self.margin)

    def eventFilter(self, watched, event):
        user_focus_out = watched is self.target() and event.type() == QEvent.FocusOut and event.reason() in (
            Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.MouseFocusReason, Qt.PopupFocusReason,
        )
        if event.type() in (QEvent.Wheel, QEvent.MouseButtonPress) or user_focus_out:
            self.cancel()
        elif event.type() in (QEvent.LayoutRequest, QEvent.Resize, QEvent.Show):
            self.schedule()
        return False


def reveal_field(scroll, field, margin=16):
    """Reveal the whole field and its error, independently of its focus child."""
    previous = getattr(scroll, "_field_reveal", None)
    if previous is not None:
        from shiboken6 import isValid
        if isValid(previous):
            previous.cancel()
            previous.deleteLater()
    scroll._field_reveal = _FieldReveal(scroll, field, margin)


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
