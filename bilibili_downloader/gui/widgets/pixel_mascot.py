"""A quiet, pixel-aligned sidebar companion with no service ownership."""

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QSizePolicy, QWidget

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.widgets.components import SectionCard
from bilibili_downloader.gui.widgets.mascot_animation import (
    CLIPS,
    FRAME_SIZE,
    AnimationPlayer,
    period_for,
)
from bilibili_downloader.gui.widgets.mascot_animation import (
    FRAME_DURATIONS as FRAME_DURATIONS,
)


class PixelMascot(QWidget):
    """Preload an atlas and animate only while visible in the active app."""

    period_changed = Signal(object)

    def __init__(self, parent=None, *, now=None, clock=None, rng=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(80, 80)
        self._still = QPixmap(asset_path("xiaoliu.png"))
        self._clips = {}
        for key, clip in CLIPS.items():
            atlas = QPixmap(asset_path(clip.asset))
            if atlas.size() == QSize(FRAME_SIZE * len(clip.durations), FRAME_SIZE):
                self._clips[key] = [
                    atlas.copy(index * FRAME_SIZE, 0, FRAME_SIZE, FRAME_SIZE)
                    for index in range(len(clip.durations))
                ]
        if "idle" not in self._clips and self._clips and not self._still.isNull():
            # A damaged idle atlas must not disable otherwise healthy actions.
            self._clips["idle"] = [self._still] * len(FRAME_DURATIONS)
        self._player = AnimationPlayer(self._clips, now=now, clock=clock, rng=rng)
        self._displayed_period = None
        self._host_window = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._advance_frame)
        QApplication.instance().applicationStateChanged.connect(self._sync_animation)
        self._refresh_state()

    @property
    def _frames(self):
        return self._clips.get(self._player.clip, [])

    @property
    def _frame_index(self):
        return self._player.frame_index

    def _refresh_state(self):
        period = self._player.period
        action = CLIPS[self._player.clip].name
        description = f"小流 · {period.name} · {action}"
        self.setAccessibleName(description)
        self.setToolTip(f"{description}\n{period.caption}")
        if self._displayed_period != period:
            self._displayed_period = period
            self.period_changed.emit(period)
        self.update()

    def _freeze_preview(self, when, animation="idle", frame=0):
        """Freeze offline documentation captures without relying on wall time."""
        self._timer.stop()
        self._player.pause()
        self._player.period = period_for(when)
        self._player._start_clip(animation if animation in self._clips else "idle")
        self._player.frame_index = frame % len(self._player.durations)
        self._refresh_state()

    def set_mini(self, mini):
        size = FRAME_SIZE if mini else FRAME_SIZE * 2
        self.setFixedSize(size, size)

    def _application_active(self):
        return QApplication.instance().applicationState() == Qt.ApplicationActive

    def _sync_animation(self, *_args):
        running = (
            "idle" in self._clips
            and self.isVisible()
            and not self.window().isMinimized()
            and self._application_active()
        )
        if running:
            self._player.resume()
            self._refresh_state()
            if not self._timer.isActive():
                self._timer.start(self._player.delay_ms)
        else:
            self._timer.stop()
            self._player.pause()

    def _advance_frame(self):
        if not (self.isVisible() and not self.window().isMinimized() and self._application_active()):
            self._sync_animation()
            return
        self._player.tick()
        self._refresh_state()
        if self._player.running:
            self._timer.start(self._player.delay_ms)

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
        self._player.pause()
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
        self._mini = False
        self.mascot = PixelMascot(self)
        self.caption = QLabel()
        self.caption.setObjectName("SidebarCaption")
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.installEventFilter(self)
        self.body.addWidget(self.mascot, 0, Qt.AlignCenter)
        self.body.addWidget(self.caption, 0, Qt.AlignCenter)
        self.body.setSpacing(8)
        self.body.setContentsMargins(12, 12, 12, 12)
        self.mascot.period_changed.connect(self._update_caption)
        self._update_caption(self.mascot._player.period)
        self._sync_height()
        if parent is not None:
            parent.installEventFilter(self)

    def _update_caption(self, period):
        self.caption.setText(period.caption.replace("，", "\n") if self._mini else period.caption)
        self.setAccessibleName(f"小流 · {period.name} · {period.caption}")
        self.setToolTip(period.caption)

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
        self._update_caption(self.mascot._player.period)
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
