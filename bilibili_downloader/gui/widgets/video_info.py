"""Video info display widget."""

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class _CoverLoadWorker(QObject):
    """Signals for async cover image loading."""

    loaded = Signal(bytes)
    failed = Signal()


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
            resp = httpx.get(self._url, timeout=10.0)
            if resp.status_code == 200:
                self._worker.loaded.emit(resp.content)
                return
        except httpx.HTTPError:
            pass
        self._worker.failed.emit()


class VideoInfoWidget(QWidget):
    """Displays video metadata (title, author, duration, cover)."""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.setObjectName("Panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        title = QLabel("当前视频")
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
        self._cover_label.setFixedSize(220, 124)
        self._cover_label.setText("封面预览")
        self._cover_label.setAlignment(Qt.AlignCenter)

        # Info labels
        self._title_label = QLabel("未选择视频")
        self._title_label.setObjectName("VideoTitle")
        self._title_label.setWordWrap(True)

        self._author_label = QLabel("UP主：--")
        self._duration_label = QLabel("时长：--")
        self._bvid_label = QLabel("BV号：--")
        for label in (self._author_label, self._duration_label, self._bvid_label):
            label.setObjectName("MetaLabel")

        # Layout
        top_layout = QHBoxLayout()
        top_layout.setSpacing(14)
        top_layout.addWidget(self._cover_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(7)
        info_layout.addWidget(self._title_label)
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
        self._author_label.setText(f"UP主：{info.author or '未知'}")
        self._duration_label.setText(f"时长：{info.duration_str}")
        self._bvid_label.setText(f"BV号：{info.bvid}")
        self._state_label.setText("已解析")

        # Load cover image
        if info.cover_url:
            self._load_cover(info.cover_url)
        else:
            self._on_cover_failed()

    def _load_cover(self, url: str):
        """Download and display cover image asynchronously."""
        worker = _CoverLoadWorker()
        worker.loaded.connect(self._on_cover_loaded)
        worker.failed.connect(self._on_cover_failed)
        runner = _CoverLoadRunner(worker, url)
        QThreadPool.globalInstance().start(runner)

    def _on_cover_loaded(self, image_data: bytes):
        """Create and show the cover pixmap on the GUI thread."""
        pixmap = QPixmap()
        if pixmap.loadFromData(image_data):
            scaled = pixmap.scaled(
                220, 124,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._cover_label.setPixmap(scaled)

    def _on_cover_failed(self):
        """Restore cover placeholder when cover loading fails."""
        self._cover_label.clear()
        self._cover_label.setText("封面预览")
