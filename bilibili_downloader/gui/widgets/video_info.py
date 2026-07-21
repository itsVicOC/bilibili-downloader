"""Video info display widget."""

import io

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.utils.network import BILIBILI_RESOURCE_HOSTS, trusted_https_url

MAX_COVER_BYTES = 10 * 1024 * 1024
MAX_COVER_PIXELS = 25_000_000


class _CoverLoadWorker(QObject):
    """Signals for async cover image loading."""

    loaded = Signal(str, bytes)
    failed = Signal(str)


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
            url = trusted_https_url(self._url, BILIBILI_RESOURCE_HOSTS)
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
            return
        except (httpx.HTTPError, UnidentifiedImageError, ValueError, OSError):
            pass
        self._worker.failed.emit(self._url)


class VideoInfoWidget(QWidget):
    """Displays video metadata (title, author, duration, cover)."""

    def __init__(self):
        super().__init__()
        self._cover_url = ""
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
        self._cover_label = QLabel()
        self._cover_label.setObjectName("EmptyCover")
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setFixedSize(300, 169)
        placeholder = QIcon(asset_path("artist_palette.png")).pixmap(QSize(58, 58))
        self._cover_label.setPixmap(placeholder)
        self._cover_label.setToolTip("解析后显示视频封面")
        self._cover_label.setAlignment(Qt.AlignCenter)

        # Info labels
        self._title_label = QLabel("等待新的次元旅程")
        self._title_label.setObjectName("VideoTitle")
        self._title_label.setWordWrap(True)

        self._author_label = QLabel("UP 主  --")
        self._duration_label = QLabel("时长  --")
        self._bvid_label = QLabel("BV 号  --")
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
        self._author_label.setText(f"UP 主  {info.author or '未知'}")
        self._duration_label.setText(f"时长  {info.duration_str}")
        self._bvid_label.setText(f"BV 号  {info.bvid}")
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
        worker.loaded.connect(self._on_cover_loaded)
        worker.failed.connect(self._on_cover_failed)
        runner = _CoverLoadRunner(worker, url)
        QThreadPool.globalInstance().start(runner)

    def _on_cover_loaded(self, url: str, image_data: bytes):
        """Create and show the cover pixmap on the GUI thread."""
        if url != self._cover_url:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(image_data):
            scaled = pixmap.scaled(
                300, 169,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self._cover_label.setPixmap(scaled)

    def _on_cover_failed(self, url: str):
        """Restore cover placeholder when cover loading fails."""
        if url and url != self._cover_url:
            return
        self._cover_label.clear()
        self._cover_label.setPixmap(
            QIcon(asset_path("artist_palette.png")).pixmap(QSize(58, 58))
        )
