"""Video info display widget."""

import io

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

MAX_COVER_BYTES = 10 * 1024 * 1024
MAX_COVER_PIXELS = 25_000_000


class _AspectCoverLabel(QLabel):
    """A bounded 16:9 preview that rescales its source without distortion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap()
        self._expand = False
        self.setMinimumSize(240, 135)
        self.setMaximumSize(300, 169)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(135, min(169, round(width * 9 / 16)))

    def sizeHint(self) -> QSize:
        return QSize(300, 169)

    def minimumSizeHint(self) -> QSize:
        return QSize(240, 135)

    def set_source_pixmap(self, pixmap: QPixmap, *, expand: bool = False) -> None:
        self._source = pixmap
        self._expand = expand
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
        mode = Qt.KeepAspectRatioByExpanding if self._expand else Qt.KeepAspectRatio
        super().setPixmap(self._source.scaled(self.size(), mode, Qt.SmoothTransformation))

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


class VideoInfoWidget(QWidget):
    """Displays video metadata (title, author, duration, cover)."""

    def __init__(self):
        super().__init__()
        self._cover_url = ""
        self._cover_pool = QThreadPool.globalInstance()
        self._cover_jobs = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.setObjectName("Panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(13)

        header_layout = QHBoxLayout()
        title = QLabel("作品资料卡")
        title.setObjectName("SectionTitle")
        self._state_label = QLabel("等待解析")
        self._state_label.setObjectName("StatusPill")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self._state_label)
        layout.addLayout(header_layout)

        # Cover image
        self._cover_label = _AspectCoverLabel()
        self._cover_label.setObjectName("EmptyCover")
        self._cover_label.setAlignment(Qt.AlignCenter)
        placeholder = QIcon(asset_path("artist_palette.png")).pixmap(QSize(58, 58))
        self._cover_label.set_source_pixmap(placeholder)
        self._cover_label.setToolTip("解析后显示视频封面")
        self._cover_label.setAlignment(Qt.AlignCenter)

        # Info labels
        self._title_label = QLabel("等待新的次元旅程")
        self._title_label.setObjectName("VideoTitle")
        self._title_label.setWordWrap(True)

        self._author_label = _ElidedLabel("UP 主  --")
        self._duration_label = _ElidedLabel("时长  --")
        self._bvid_label = _ElidedLabel("BV 号  --")
        for label in (self._author_label, self._duration_label, self._bvid_label):
            label.setObjectName("InfoChip")

        # Layout
        top_layout = QHBoxLayout()
        top_layout.setSpacing(18)
        top_layout.addWidget(self._cover_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(9)
        info_layout.addWidget(self._title_label)
        subtitle = QLabel("解析完成后，可以在右侧选择画质和编码")
        subtitle.setObjectName("MetaLabel")
        subtitle.setWordWrap(True)
        info_layout.addWidget(subtitle)
        info_layout.addSpacing(4)
        info_layout.addWidget(self._author_label)
        info_layout.addWidget(self._duration_label)
        info_layout.addWidget(self._bvid_label)
        info_layout.addStretch()
        top_layout.addLayout(info_layout)
        top_layout.addStretch()

        layout.addLayout(top_layout)

    def set_video_info(self, info):
        """Update display with video info."""
        self._title_label.setText(info.title or "无标题")
        self._title_label.setToolTip(info.title or "无标题")
        self._author_label.set_full_text(f"UP 主  {info.author or '未知'}")
        self._duration_label.set_full_text(f"时长  {info.duration_str}")
        self._bvid_label.set_full_text(f"BV 号  {info.bvid}")
        self._state_label.setText("READY")

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
        self._cover_jobs = [
            job for job in self._cover_jobs if job[0] is not worker
        ]

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
        self._cover_label.set_source_pixmap(
            QIcon(asset_path("artist_palette.png")).pixmap(QSize(58, 58))
        )
