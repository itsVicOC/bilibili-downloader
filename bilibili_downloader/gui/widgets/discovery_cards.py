"""Shared preview cards and bounded, anonymous thumbnail loading."""

import io
from collections import OrderedDict
from dataclasses import dataclass

import httpx
from PIL import Image, ImageOps
from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    QRectF,
    QRunnable,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.widgets.components import PreviewTitle, palette
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url


def _thumbnail(url):
    url = trusted_https_url(url, BILIBILI_RESOURCE_HOSTS, upgrade_http=True)
    content = bytearray()
    with httpx.stream("GET", url, timeout=5.0, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > 4 * 1024 * 1024:
                raise ValueError("封面文件过大")
    with Image.open(io.BytesIO(content)) as original:
        if original.width * original.height > 16_000_000:
            raise ValueError("封面像素尺寸过大")
        image = ImageOps.fit(ImageOps.exif_transpose(original).convert("RGB"), (480, 270))
        output = io.BytesIO()
        image.save(output, "JPEG", quality=86)
        return output.getvalue()


class _ThumbnailJob(QRunnable):
    def __init__(self, url, generation, deliver):
        super().__init__()
        self.url = url
        self.generation = generation
        self.deliver = deliver

    def run(self):
        try:
            data = _thumbnail(self.url)
        except (httpx.HTTPError, OSError, ValueError, Image.DecompressionBombError):
            data = b""
        self.deliver(self.url, self.generation, data)


class _DiscoverySignals(QObject):
    finished = Signal(str, object, object)


class DiscoveryJob(QRunnable):
    def __init__(self, kind, request, load):
        super().__init__()
        self.signals = _DiscoverySignals()
        self.kind = kind
        self.request = request
        self.load = load

    def run(self):
        if not self.request.is_set():
            result = self.load()
            if not self.request.is_set():
                self.signals.finished.emit(self.kind, self.request, result)


class ThumbnailLoader(QObject):
    changed = Signal(str)
    _finished = Signal(str, int, bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._generation = 0
        self._cache = OrderedDict()
        self._pending = set()
        self._finished.connect(self._store, Qt.QueuedConnection)

    def clear(self):
        self.pool.clear()
        self._generation += 1
        self._pending.clear()
        self._cache.clear()

    def resolve(self, urls):
        """Use the first successful image, trying the avatar after a failed cover."""
        for url in urls:
            if not url:
                continue
            if url in self._cache:
                pixmap = self._cache[url]
                self._cache.move_to_end(url)
                if pixmap is not None:
                    return pixmap
                continue
            if url not in self._pending:
                self._pending.add(url)
                self.pool.start(_ThumbnailJob(url, self._generation, self._finished.emit))
            break
        return None

    @Slot(str, int, bytes)
    def _store(self, url, generation, data):
        if generation != self._generation:
            return
        self._pending.discard(url)
        pixmap = QPixmap()
        self._cache[url] = pixmap if data and pixmap.loadFromData(data) else None
        if len(self._cache) > 64:
            self._cache.popitem(last=False)
        self.changed.emit(url)


@dataclass(frozen=True)
class DiscoveryCard:
    key: str
    title: str
    author: str
    images: tuple[str, ...] = ()
    badge: str = ""
    detail: str = ""
    duration: str = ""
    action: str = ""
    opens_video: bool = False
    enabled: bool = True
    badge_tone: str = "muted"


class _CardButton(QPushButton):
    def __init__(self, text=""):
        super().__init__(text)
        self.setFocusPolicy(Qt.StrongFocus)

    def sizeHint(self):
        layout = self.layout()
        return layout.sizeHint() if layout else super().sizeHint()

    def minimumSizeHint(self):
        layout = self.layout()
        return layout.minimumSize() if layout else super().minimumSizeHint()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class _Cover(QWidget):
    def __init__(self, card, parent):
        super().__init__(parent)
        self.card = card
        self.image = None
        policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumHeight(70)
        if card.opens_video:
            parent.installEventFilter(self)

    def heightForWidth(self, width):
        return max(70, round(width * 9 / 16))

    def resizeEvent(self, event):
        self.setFixedHeight(self.heightForWidth(event.size().width()))
        super().resizeEvent(event)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Enter, QEvent.Leave, QEvent.FocusIn, QEvent.FocusOut):
            self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        rect = self.rect()
        colors = palette(self)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), 7, 7)
        painter.setClipPath(clip)
        painter.fillRect(rect, QColor(colors.subtle_selection))
        if self.image:
            painter.drawPixmap(rect, self.image)
        else:
            painter.setPen(QColor(colors.border))
            center = rect.center()
            painter.drawRoundedRect(QRectF(center.x() - 9, center.y() - 7, 18, 14), 2, 2)
            painter.drawLine(center.x() - 6, center.y() + 4, center.x(), center.y() - 2)
            painter.drawLine(center.x(), center.y() - 2, center.x() + 6, center.y() + 4)
        if self.card.badge:
            self._paint_badge(painter, colors)
        if self.card.detail or self.card.duration:
            self._paint_metadata(painter, rect)
        target = self.parentWidget()
        if self.card.opens_video and target.isEnabled() and (target.underMouse() or target.hasFocus()):
            self._paint_play(painter, rect.center())
        painter.end()

    def _paint_badge(self, painter, colors):
        metrics = painter.fontMetrics()
        text = metrics.elidedText(self.card.badge, Qt.ElideRight, max(0, self.width() - 30))
        badge = QRect(7, 7, metrics.horizontalAdvance(text) + 14, metrics.height() + 6)
        tone = self.card.badge_tone
        foreground = {
            "active": colors.active_text, "success": colors.success,
            "warning": colors.warning, "danger": colors.danger,
        }
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(26, 29, 38, 224) if self.card.opens_video else QColor(colors.tone_surface(tone)))
        painter.drawRoundedRect(badge, 5, 5)
        painter.setPen(QColor(Qt.white) if self.card.opens_video else QColor(foreground.get(tone, colors.muted)))
        painter.drawText(badge, Qt.AlignCenter, text)

    def _paint_metadata(self, painter, rect):
        metrics = painter.fontMetrics()
        height = metrics.height() + 20
        shade = QLinearGradient(0, max(0, rect.bottom() - height), 0, rect.bottom())
        shade.setColorAt(0, QColor(0, 0, 0, 0))
        shade.setColorAt(1, QColor(0, 0, 0, 218))
        painter.fillRect(rect.adjusted(0, max(0, rect.height() - height), 0, 0), shade)
        painter.setPen(Qt.white)
        text = rect.adjusted(8, 0, -8, -5)
        duration = self.card.duration
        reserved = metrics.horizontalAdvance(duration) + 8 if duration else 0
        detail = metrics.elidedText(self.card.detail, Qt.ElideRight, max(0, text.width() - reserved))
        painter.drawText(text, Qt.AlignBottom | Qt.AlignLeft, detail)
        painter.drawText(text, Qt.AlignBottom | Qt.AlignRight, duration)

    @staticmethod
    def _paint_play(painter, center):
        x, y = center.x(), center.y()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 23, 32, 218))
        painter.drawEllipse(QRectF(x - 20, y - 20, 40, 40))
        icon = QPainterPath()
        icon.moveTo(x - 4, y - 8)
        icon.lineTo(x + 9, y)
        icon.lineTo(x - 4, y + 8)
        icon.closeSubpath()
        painter.fillPath(icon, QColor(Qt.white))


class _CardWidget(QWidget):
    def __init__(self, card, act, open_video):
        super().__init__()
        self.card = card
        self.setObjectName("DiscoveryCard")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.video_button = None
        self.action_button = None
        if card.opens_video:
            content = self.video_button = _CardButton()
            content.setObjectName("DiscoveryVideo")
            content.setAutoDefault(False)
            content.setProperty("ownFocusRing", True)
            content.setCursor(Qt.PointingHandCursor)
            content.setAccessibleName(f"在浏览器打开视频 · {card.title}")
            content.setToolTip(f"在浏览器打开视频 · {card.title}")
            content.clicked.connect(lambda: open_video(card.key))
        else:
            content = QWidget()
        content_policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        content_policy.setHeightForWidth(True)
        content.setSizePolicy(content_policy)
        body = QVBoxLayout(content)
        body.setContentsMargins(1, 1, 1, 1)
        body.setSpacing(0)
        self.cover = _Cover(card, content)
        body.addWidget(self.cover)
        self.title = PreviewTitle(card.title)
        self.title.setObjectName("DiscoveryTitle")
        self.title.setContentsMargins(7, 0, 7, 0)
        self.title.setToolTip(content.toolTip() if card.opens_video else card.title)
        body.addSpacing(4)
        body.addWidget(self.title)
        if card.opens_video:
            for child in (self.cover, self.title):
                child.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(content)

        footer = QHBoxLayout()
        self._footer_layout = footer
        footer.setContentsMargins(8, 0, 6, 4)
        footer.setSpacing(6)
        author = PreviewTitle(card.author)
        author.line_limit = 1
        author.setObjectName("MetaLabel")
        author.setToolTip(card.author)
        author.setAccessibleName(card.author)
        footer.addWidget(author, 1)
        if card.action:
            action = self.action_button = _CardButton(card.action)
            action.setObjectName("DiscoveryAction")
            action.setAccessibleName(f"{card.action} · {card.title}")
            if card.opens_video:
                action.setAccessibleDescription("解析后可选择下载规格并确认入队")
                action.setToolTip(action.accessibleDescription())
            action.setAutoDefault(False)
            action.setEnabled(card.enabled)
            action.clicked.connect(lambda: act(card.key))
            footer.addWidget(action)
        layout.addLayout(footer)

    def row_height(self, width):
        return (
            self.cover.heightForWidth(width - 4) + self.title.heightForWidth(width - 18)
            + self._footer_layout.sizeHint().height() + 8
        )


class DiscoveryGrid(QWidget):
    action_requested = Signal(str)
    video_requested = Signal(str)
    can_expand = Signal(bool)

    def __init__(self, thumbnails, parent=None):
        super().__init__(parent)
        self._thumbnails = thumbnails
        thumbnails.changed.connect(self._load_visible)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._cards = ()
        self._widgets = []
        self._shape = None
        self._viewport = None
        self._expanded = False
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._settle_layout)

    def set_scroll_area(self, scroll):
        self._viewport = scroll.viewport()
        scroll.verticalScrollBar().valueChanged.connect(self._load_visible)

    def set_cards(self, cards):
        cards = tuple(cards)
        if cards != self._cards:
            self._cards = cards
            self._reflow(force=True)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self._reflow()

    def _focus_controls(self):
        return [
            button for card in self._widgets for button in (card.video_button, card.action_button)
            if button is not None and button.isEnabled() and button.isVisible()
        ]

    def focusNextPrevChild(self, forward):
        # Keep the card actions reachable with macOS text-only Tab navigation.
        controls = self._focus_controls()
        focused = QApplication.focusWidget()
        if focused in controls:
            index = controls.index(focused) + (1 if forward else -1)
            if 0 <= index < len(controls):
                controls[index].setFocus(Qt.TabFocusReason if forward else Qt.BacktabFocusReason)
                return True
        return super().focusNextPrevChild(forward)

    def _columns(self):
        return 4 if self.width() >= 970 else 3 if self.width() >= 695 else 2

    def _visible_cards(self, columns):
        return self._cards if self._expanded else self._cards[:columns]

    def _reflow(self, *, force=False):
        columns = self._columns()
        visible = self._visible_cards(columns)
        shape = (columns, visible)
        if not force and shape == self._shape:
            return
        old_columns = self._shape[0] if self._shape is not None else columns
        self._shape = shape
        keep = 0
        for widget, card in zip(self._widgets, visible):
            if widget.card != card:
                break
            keep += 1
        for widget in self._widgets[keep:]:
            self._layout.removeWidget(widget)
            widget.hide()
            widget.deleteLater()
        del self._widgets[keep:]
        if columns != old_columns:
            for index, widget in enumerate(self._widgets):
                self._layout.removeWidget(widget)
                self._layout.addWidget(widget, index // columns, index % columns)
        for index, card in enumerate(visible[keep:], keep):
            widget = _CardWidget(card, self.action_requested.emit, self.video_requested.emit)
            self._layout.addWidget(widget, index // columns, index % columns)
            self._widgets.append(widget)
        for index in range(4):
            self._layout.setColumnStretch(index, int(index < columns))
        self.can_expand.emit(len(self._cards) > columns)
        self._layout_timer.start(0)

    def _settle_layout(self):
        self._reflow()
        self._load_visible()

    def _load_visible(self, *_args):
        if self.isVisible():
            for widget in self._widgets:
                if self._viewport is not None and not QRect(
                    widget.mapTo(self._viewport, widget.rect().topLeft()), widget.size()
                ).intersects(self._viewport.rect()):
                    continue
                widget.cover.image = self._thumbnails.resolve(widget.card.images)
                widget.cover.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_timer.start(0)

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_timer.start(0)


class ProgressiveDiscoveryGrid(DiscoveryGrid):
    """Materialize a viewport of cards at a time while keeping the earlier rows."""

    def __init__(self, thumbnails, parent=None):
        super().__init__(thumbnails, parent)
        self._limit = None
        self._bar = None
        self._scroll_value = 0
        self._footer_position = None
        self._append_timer = QTimer(self)
        self._append_timer.setSingleShot(True)
        self._append_timer.timeout.connect(self._append_screen)
        self.more = _CardButton("加载更多")
        self.more.setParent(self)
        self.more.setObjectName("DiscoveryHeaderAction")
        self.more.setAutoDefault(False)
        self.more.clicked.connect(self._append_screen)
        self.more.hide()

    def set_scroll_area(self, scroll):
        super().set_scroll_area(scroll)
        self._viewport.installEventFilter(self)
        self._bar = scroll.verticalScrollBar()
        self._scroll_value = self._bar.value()
        self._bar.valueChanged.connect(self._on_scroll)

    def set_cards(self, cards):
        cards = tuple(cards)
        if cards != self._cards:
            self._limit = None
            self._append_timer.stop()
        super().set_cards(cards)

    def _screen_size(self, columns, *, initial=False):
        if self._viewport is None or not self._widgets:
            return columns
        gap = self._layout.verticalSpacing()
        width = (self.width() - (columns - 1) * self._layout.horizontalSpacing()) // columns
        row = self._widgets[0].row_height(width)
        height = self._viewport.height()
        if initial:
            top = self.mapTo(self._viewport, QPoint()).y() + self._bar.value()
            height -= max(0, top)
        return max(1, (height + gap) // (row + gap)) * columns

    def _visible_cards(self, columns):
        if not self.isVisible():
            return self._cards[:len(self._widgets)]
        limit = self._limit if self._limit is not None else self._screen_size(columns, initial=True)
        return self._cards[:limit]

    def _reflow(self, *, force=False):
        super()._reflow(force=force)
        columns = self._columns()
        count = len(self._widgets)
        has_more = 0 < count < len(self._cards)
        position = ((count + columns - 1) // columns, columns)
        if has_more and position != self._footer_position:
            self._layout.removeWidget(self.more)
            self._layout.addWidget(self.more, position[0], 0, 1, columns, Qt.AlignHCenter)
            self._footer_position = position
        self.more.setVisible(has_more)

    def event(self, event):
        if event.type() == QEvent.LayoutRequest:
            self._layout_timer.start(0)
        return super().event(event)

    def _focus_controls(self):
        controls = super()._focus_controls()
        if self.more.isVisible():
            controls.append(self.more)
        return controls

    def _on_scroll(self, value):
        previous = self._scroll_value
        self._scroll_value = value
        if value > previous and value == self._bar.maximum():
            self._queue_append()

    def _queue_append(self):
        if self.more.isVisible():
            self._append_timer.start(0)

    def _append_screen(self):
        self._append_timer.stop()
        if not self.more.isVisible():
            return
        previous_count = len(self._widgets)
        keyboard = self.more.hasFocus() and self.more.property("keyboardFocus")
        columns = self._columns()
        next_row = ((previous_count + columns - 1) // columns) * columns
        self._limit = next_row + self._screen_size(columns)
        self._reflow()
        if keyboard:
            self._widgets[previous_count].video_button.setFocus(Qt.TabFocusReason)

    def eventFilter(self, watched, event):
        if watched is self._viewport:
            if event.type() == QEvent.Resize:
                self._layout_timer.start(0)
            elif event.type() == QEvent.Wheel and self._bar.value() == self._bar.maximum():
                delta = event.pixelDelta().y() or event.angleDelta().y()
                if delta < 0:
                    self._queue_append()
        return super().eventFilter(watched, event)
