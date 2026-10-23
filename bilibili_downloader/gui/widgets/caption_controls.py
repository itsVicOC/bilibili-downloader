"""Fluent caption controls in the same backing store as the page header."""

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget

from bilibili_downloader.gui.resources.styles import (
    UI_METRICS,
    blend_color,
    theme_palette,
)
from bilibili_downloader.gui.widgets.motion import StateTransition

CAPTION_ACTIONS = ("minimize", "maximize", "close")
CAPTION_LABELS = {"minimize": "最小化", "maximize": "最大化", "close": "关闭"}


def caption_rects(client_width, scale=1.0):
    """Physical client rectangles; round shared edges once at fractional DPI."""
    width, height = UI_METRICS.caption_width, UI_METRICS.caption_height
    edges = [client_width - round(width * remaining * scale) for remaining in (3, 2, 1, 0)]
    return {name: QRect(edges[i], 0, edges[i + 1] - edges[i], round(height * scale))
            for i, name in enumerate(CAPTION_ACTIONS)}


class CaptionButton(QAbstractButton):
    def __init__(self, action, parent):
        super().__init__(parent)
        self.action, self.hovered, self.restore = action, False, False
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedSize(UI_METRICS.caption_width, UI_METRICS.caption_height)
        self.setAccessibleName(CAPTION_LABELS[action])
        self.setToolTip(CAPTION_LABELS[action])
        self._hover = StateTransition(self)

    def set_hovered(self, hovered):
        if self.hovered != hovered:
            self.hovered = hovered
            self._hover.to(hovered)

    def reset(self):
        self.setDown(False)
        self.set_hovered(False)
        self._hover.settle()

    def event(self, event):
        native_tracking = getattr(self.parentWidget(), "native_tracking", False)
        if event.type() == QEvent.Enter and not native_tracking:
            self.set_hovered(True)
        elif event.type() == QEvent.Leave and not native_tracking:
            self.set_hovered(False)
        elif event.type() in (QEvent.Hide, QEvent.EnabledChange):
            self.reset()
        return super().event(event)

    def paintEvent(self, event):
        app = QApplication.instance()
        p = theme_palette(bool(app.property("darkTheme")), app.property("colorTheme"))
        foreground = p.text if self.window().isActiveWindow() else p.muted
        background = p.background
        if self.isEnabled():
            target = p.caption_close_pressed if self.action == "close" and self.isDown() else (
                p.caption_close_hover if self.action == "close" else
                p.caption_pressed if self.isDown() else p.caption_hover
            )
            amount = 1.0 if self.isDown() else self._hover.value
            background = blend_color(background, target, amount)
            if self.action == "close" and amount:
                foreground = blend_color(foreground, "#ffffff", amount)
        else:
            foreground = p.disabled
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(background))
        # Paint on physical pixel centres, without depending on an icon font.
        dpr = self.devicePixelRatioF()
        painter.scale(1 / dpr, 1 / dpr)
        stroke, size = max(1, round(dpr)), round(10 * dpr)
        x = round((self.width() * dpr - size) / 2) + stroke / 2
        y = round((self.height() * dpr - size) / 2) + stroke / 2
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(foreground), stroke))
        painter.setBrush(Qt.NoBrush)
        if self.action == "minimize":
            painter.drawLine(QPointF(x, y + size / 2), QPointF(x + size - stroke, y + size / 2))
        elif self.action == "close":
            painter.drawLine(QPointF(x, y), QPointF(x + size - stroke, y + size - stroke))
            painter.drawLine(QPointF(x + size - stroke, y), QPointF(x, y + size - stroke))
        elif self.restore:
            offset = round(2 * dpr)
            painter.drawRect(QRectF(x + offset, y, size - stroke - offset, size - stroke - offset))
            painter.fillRect(QRectF(x - stroke / 2, y + offset - stroke / 2,
                                    size - offset, size - offset), QColor(background))
            painter.drawRect(QRectF(x, y + offset, size - stroke - offset, size - stroke - offset))
        else:
            painter.drawRect(QRectF(x, y, size - stroke, size - stroke))
        if self.hasFocus() and self.property("keyboardFocus"):
            painter.setPen(QPen(QColor(p.focus), max(1, round(2 * dpr))))
            painter.drawRect(QRectF(3 * dpr, 3 * dpr, (self.width() - 6) * dpr, (self.height() - 6) * dpr))
        painter.end()


class CaptionControls(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("CaptionControls")
        self.native_tracking = False
        self.buttons = {}
        for index, name in enumerate(CAPTION_ACTIONS):
            button = CaptionButton(name, self)
            button.move(index * UI_METRICS.caption_width, 0)
            button.clicked.connect(lambda _checked=False, action=name: self.invoke(action))
            self.buttons[name] = button
        self.sync()

    def sync(self):
        window = self.window()
        width = 3 * UI_METRICS.caption_width
        self.setGeometry(window.width() - width, 0, width, UI_METRICS.caption_height)
        self.setVisible(not window.isFullScreen())
        self.raise_()
        maximum = self.buttons["maximize"]
        maximum.restore = window.isMaximized()
        label = "还原" if maximum.restore else "最大化"
        maximum.setAccessibleName(label)
        maximum.setToolTip(label)
        for button in self.buttons.values():
            button.update()

    def reset(self):
        self.native_tracking = False
        for button in self.buttons.values():
            button.reset()

    def hover(self, action, *, native=False):
        if native:
            self.native_tracking = True
        for name, button in self.buttons.items():
            button.set_hovered(name == action)

    def leave_native(self):
        self.native_tracking = False
        self.hover(None)

    def invoke(self, action):
        window = self.window()
        if not self.isEnabled() or not window.isEnabled():
            return
        self.reset()
        if action == "minimize":
            window.showMinimized()
        elif action == "maximize":
            window.showNormal() if window.isMaximized() else window.showMaximized()
        else:
            window.close()
