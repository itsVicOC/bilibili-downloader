"""Video info display widget."""

import io
from dataclasses import replace

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import (
    QObject,
    QPointF,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from bilibili_downloader.gui.layout_policy import COMFORTABLE
from bilibili_downloader.gui.resources.styles import UI_METRICS
from bilibili_downloader.gui.widgets.components import (
    PreviewTitle,
    StatusBadge,
    line_icon,
)
from bilibili_downloader.gui.widgets.glass_surface import GlassWidget
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

MAX_COVER_BYTES = 10 * 1024 * 1024
MAX_COVER_PIXELS = 25_000_000


class _AspectCoverLabel(QLabel):
    """A bounded 16:9 preview that rescales its source without distortion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap()
        self._expand = False
        self._density = COMFORTABLE
        self.featured = False
        self.setMinimumSize(160, 90)
        self.setMaximumSize(176, 99)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if self.featured and not self._density.compact:
            return max(144, min(292, round(width * 9 / 16)))
        if self._density.compact:
            return self._density.cover_height
        return max(90, min(99, round(width * 9 / 16)))

    def sizeHint(self) -> QSize:
        width = self._density.cover_width
        if self.featured and self._density.compact and self._expand and not self._source.isNull():
            width = min(width, max(36, round(self._density.cover_height * self._source.width() / self._source.height())))
        return QSize(width, self._density.cover_height)

    def minimumSizeHint(self) -> QSize:
        if self.featured and not self._density.compact:
            return QSize(240, 135)
        if self._density.compact:
            return self.sizeHint()
        return QSize(160, 90)

    def set_density(self, density):
        self._density = density
        self.setMinimumSize(240 if self.featured and not density.compact else self.sizeHint().width() if density.compact else 160,
                            135 if self.featured and not density.compact else density.cover_height if density.compact else 90)
        self.setMaximumSize(self.sizeHint())
        self.updateGeometry()

    def set_source_pixmap(self, pixmap: QPixmap, *, expand: bool = False) -> None:
        self._source = pixmap
        self._expand = expand
        if self.featured and self._density.compact:
            self.set_density(self._density)
        self._render_source()

    def _render_source(self) -> None:
        if self._source.isNull():
            self.clear()
            return
        if not self._expand and (
            self._source.width() <= self.width()
            and self._source.height() <= self.height()
        ):
            super().setPixmap(self._source)
            return
        mode = Qt.KeepAspectRatioByExpanding if self._expand and not self.featured else Qt.KeepAspectRatio
        dpr = self.devicePixelRatioF()
        rendered = self._source.scaled(self.size() * dpr, mode, Qt.SmoothTransformation)
        rendered.setDevicePixelRatio(dpr)
        super().setPixmap(rendered)

    def paintEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        shape = QPainterPath()
        size = pixmap.deviceIndependentSize()
        target = QRectF(QPointF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2), size)
        shape.addRoundedRect(target.intersected(QRectF(self.contentsRect())), UI_METRICS.radius, UI_METRICS.radius)
        painter.setClipPath(shape)
        painter.drawPixmap(target.topLeft(), pixmap)

    def resizeEvent(self, event):
        self.setFixedHeight(self.heightForWidth(event.size().width()))
        self._render_source()
        super().resizeEvent(event)


class _ElidedLabel(QLabel):
    """Display a single-line value compactly while retaining its full text."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._sync_text()

    def _sync_text(self) -> None:
        width = max(1, self.contentsRect().width())
        QLabel.setText(
            self,
            self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width),
        )

    def resizeEvent(self, event):
        self._sync_text()
        super().resizeEvent(event)


class _CoverLoadWorker(QObject):
    """Signals for async cover image loading."""

    loaded = Signal(str, bytes)
    failed = Signal(str)
    finished = Signal(object)


class _CoverLoadRunner(QRunnable):
    """Downloads cover image in a background thread."""

    def __init__(self, worker: _CoverLoadWorker, url: str):
        super().__init__()
        self._worker = worker
        self._url = url
        self.setAutoDelete(True)

    def run(self):
        import httpx

        try:
            url = trusted_https_url(
                self._url,
                BILIBILI_RESOURCE_HOSTS,
                upgrade_http=True,
            )
            content = bytearray()
            with httpx.stream("GET", url, timeout=10.0) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_COVER_BYTES:
                        raise ValueError("封面文件过大")
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > MAX_COVER_PIXELS:
                    raise ValueError("封面像素尺寸过大")
                image.verify()
            self._worker.loaded.emit(self._url, bytes(content))
        except (httpx.HTTPError, UnidentifiedImageError, ValueError, OSError):
            self._worker.failed.emit(self._url)
        finally:
            self._worker.finished.emit(self._worker)


class VideoInfoWidget(GlassWidget):
    """Displays video metadata (title, author, duration, cover)."""

    def __init__(self):
        super().__init__(reading=True)
        self._featured = False
        self._cover_url = ""
        self._cover_pool = QThreadPool.globalInstance()
        self._cover_jobs = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.setObjectName("Panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._state_label = StatusBadge("等待解析")

        # Cover image
        self._cover_label = _AspectCoverLabel()
        self._cover_label.setObjectName("EmptyCover")
        self._cover_label.setAlignment(Qt.AlignCenter)
        placeholder = line_icon("star", size=48).pixmap(48, 48)
        self._cover_label.set_source_pixmap(placeholder)
        self._cover_label.setToolTip("解析后显示视频封面")
        self._cover_label.setAlignment(Qt.AlignCenter)

        # Info labels
        self._title_label = PreviewTitle("等待新的次元旅程")
        self._title_label.setObjectName("VideoTitle")
        self._title_label.setTextFormat(Qt.PlainText)

        self._author_label = _ElidedLabel("UP 主  --")
        self._duration_label = _ElidedLabel("时长  --")
        self._bvid_label = _ElidedLabel("BV 号  --")
        for label in (self._author_label, self._duration_label, self._bvid_label):
            label.setObjectName("InfoChip")

        # Layout
        top_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self._identity_layout = top_layout
        top_layout.setSpacing(16)
        top_layout.addWidget(self._cover_label, 0, Qt.AlignTop)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(12)
        heading.addWidget(self._title_label, 1)
        heading.addWidget(self._state_label, 0, Qt.AlignTop)
        info_layout.addLayout(heading)
        self._author_row = QHBoxLayout()
        self._author_row.addWidget(self._author_label, 1)
        info_layout.addLayout(self._author_row)
        metadata = QHBoxLayout()
        metadata.setSpacing(16)
        metadata.addWidget(self._duration_label, 1)
        metadata.addWidget(self._bvid_label, 2)
        info_layout.addLayout(metadata)
        info_layout.addStretch()
        top_layout.addLayout(info_layout, 1)

        layout.addLayout(top_layout)
        layout.addStretch()

    def resizeEvent(self, event):
        self._identity_layout.setDirection(
            QBoxLayout.TopToBottom if (self._featured and not self._cover_label._density.compact) or event.size().width() < 380 else QBoxLayout.LeftToRight
        )
        super().resizeEvent(event)

    def set_featured(self, featured):
        self._featured = featured
        self._cover_label.featured = featured
        self.setProperty("featured", featured)
        self.set_density(COMFORTABLE)

    def set_density(self, density):
        if self._featured and not density.compact:
            density = replace(density, cover_width=520, cover_height=292)
        padding = density.card_padding
        self.layout().setContentsMargins(padding, padding, padding, padding)
        self._identity_layout.setSpacing(12 if density.compact else 16)
        self._cover_label.set_density(density)
        self._title_label.compact = density.compact
        self._title_label.updateGeometry()

    def set_video_info(self, info):
        """Update display with video info."""
        self._title_label.setText(info.title or "无标题")
        self._title_label.setToolTip(info.title or "无标题")
        if info.episode_id:
            context = " · ".join(
                value
                for value in (
                    info.series_title,
                    info.season_title,
                    info.section_title,
                )
                if value
            )
            self._author_label.set_full_text(f"番剧  {context or '未知'}")
        else:
            self._author_label.set_full_text(f"UP 主  {info.author or '未知'}")
        self._duration_label.set_full_text(f"时长  {info.duration_str}")
        identity = f"ep{info.episode_id}" if info.episode_id else info.bvid
        self._bvid_label.set_full_text(f"作品号  {identity}")
        self._state_label.setText("已解析")
        self._state_label.set_tone("success")
        self._state_label.setVisible(not self._featured)

        # Load cover image
        if info.cover_url:
            self._load_cover(info.cover_url)
        else:
            self._cover_url = ""
            self._on_cover_failed("")

    def _load_cover(self, url: str):
        """Download and display cover image asynchronously."""
        self._cover_url = url
        worker = _CoverLoadWorker()
        runner = _CoverLoadRunner(worker, url)
        job = (worker, runner)
        self._cover_jobs.append(job)
        worker.loaded.connect(self._on_cover_loaded)
        worker.failed.connect(self._on_cover_failed)
        worker.finished.connect(self._finish_cover_job)
        self._cover_pool.start(runner)

    def _finish_cover_job(self, worker):
        self._cover_jobs = [job for job in self._cover_jobs if job[0] is not worker]

    def _on_cover_loaded(self, url: str, image_data: bytes):
        """Create and show the cover pixmap on the GUI thread."""
        if url != self._cover_url:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(image_data):
            self._cover_label.set_source_pixmap(pixmap, expand=True)

    def _on_cover_failed(self, url: str):
        """Restore cover placeholder when cover loading fails."""
        if url and url != self._cover_url:
            return
        self._cover_label.set_source_pixmap(line_icon("star", size=48).pixmap(48, 48))
