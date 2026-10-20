"""A quiet, pixel-aligned sidebar companion with no service ownership."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QSizePolicy, QWidget

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.widgets.components import SectionCard

FRAME_SIZE = 40
FRAME_DURATIONS = (1600, 650, 80, 120, 80, 1470)


class PixelMascot(QWidget):
    """Preload an atlas and animate only while visible in the active app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("小流，BiliFlow 像素看板娘")
        self.setToolTip("小流 · BiliFlow 的星轨收藏伙伴")
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(80, 80)
        self._still = QPixmap(asset_path("xiaoliu.png"))
        atlas = QPixmap(asset_path("xiaoliu_idle.png"))
        self._frames = []
        if atlas.size() == QSize(FRAME_SIZE * len(FRAME_DURATIONS), FRAME_SIZE):
            self._frames = [
                atlas.copy(index * FRAME_SIZE, 0, FRAME_SIZE, FRAME_SIZE)
                for index in range(len(FRAME_DURATIONS))
            ]
        self._frame_index = 0
        self._host_window = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance_frame)
        QApplication.instance().applicationStateChanged.connect(self._sync_animation)

    def set_mini(self, mini):
        size = FRAME_SIZE if mini else FRAME_SIZE * 2
        self.setFixedSize(size, size)

    def _application_active(self):
        return QApplication.instance().applicationState() == Qt.ApplicationActive

    def _sync_animation(self, *_args):
        running = (
            bool(self._frames)
            and self.isVisible()
            and not self.window().isMinimized()
            and self._application_active()
        )
        if running:
            if not self._timer.isActive():
                self._timer.start(FRAME_DURATIONS[self._frame_index])
        else:
            self._timer.stop()

    def _advance_frame(self):
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self.update()
        self._sync_animation()

    def showEvent(self, event):
        host = self.window()
        if self._host_window is not host:
            if self._host_window is not None:
                self._host_window.removeEventFilter(self)
            self._host_window = host
            host.installEventFilter(self)
        super().showEvent(event)
        self._sync_animation()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if watched is self._host_window and event.type() == QEvent.WindowStateChange:
            self._sync_animation()
        return super().eventFilter(watched, event)

    def paintEvent(self, event):
        frame = self._frames[self._frame_index] if self._frames else self._still
        if frame.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawPixmap(
            QRect(0, 0, self.width(), self.height()), frame, frame.rect()
        )


class MascotCard(SectionCard):
    """Use a smaller, horizontal companion when the sidebar is short."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("MascotCard")
        self.setAccessibleName("小流 · 次元收藏，随时继续")
        self._mini = False
        self.mascot = PixelMascot(self)
        self.caption = QLabel("次元收藏，随时继续")
        self.caption.setObjectName("SidebarCaption")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.installEventFilter(self)
        self.body.addWidget(self.mascot, 0, Qt.AlignCenter)
        self.body.addWidget(self.caption, 0, Qt.AlignCenter)
        self.body.setSpacing(8)
        self.body.setContentsMargins(12, 12, 12, 12)
        self._sync_height()
        if parent is not None:
            parent.installEventFilter(self)

    def height_for_mode(self, mini):
        line_height = self.caption.fontMetrics().height()
        if mini:
            return max(FRAME_SIZE, line_height * 2) + 14
        return FRAME_SIZE * 2 + line_height + 34

    def _sync_height(self):
        self.setFixedHeight(self.height_for_mode(self._mini))

    def _set_mini(self, mini):
        if self._mini == mini:
            return
        self._mini = mini
        self.mascot.set_mini(mini)
        self.body.setDirection(
            QBoxLayout.LeftToRight if mini else QBoxLayout.TopToBottom
        )
        margin = 6 if mini else 12
        self.body.setContentsMargins(margin, margin, margin, margin)
        self.caption.setText("次元收藏\n随时继续" if mini else "次元收藏，随时继续")
        self.caption.setAlignment(
            Qt.AlignLeft | Qt.AlignVCenter if mini else Qt.AlignCenter
        )
        self._sync_height()

    def _fit_sidebar(self):
        sidebar = self.parentWidget()
        if sidebar is None or sidebar.layout() is None or not self.isVisible():
            return
        required = (
            sidebar.layout().minimumSize().height()
            - self.minimumHeight()
            + self.height_for_mode(False)
        )
        self._set_mini(sidebar.height() < required)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_height()
        self._fit_sidebar()

    def eventFilter(self, watched, event):
        if watched is self.caption and event.type() == QEvent.FontChange:
            self._sync_height()
        elif watched is self.parentWidget() and event.type() in (
            QEvent.Resize,
            QEvent.LayoutRequest,
        ):
            self._fit_sidebar()
        return super().eventFilter(watched, event)
