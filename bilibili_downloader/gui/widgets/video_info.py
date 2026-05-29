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

    loaded = Signal(object)  # QPixmap
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
                pixmap = QPixmap()
                if pixmap.loadFromData(resp.content):
                    scaled = pixmap.scaled(
                        200, 120,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                    self._worker.loaded.emit(scaled)
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
        layout.setContentsMargins(10, 10, 10, 10)

        # Cover image
        self._cover_label = QLabel()
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setFixedSize(200, 120)
        self._cover_label.setStyleSheet(
            "QLabel { background-color: #1e1e1e; border-radius: 4px; }"
        )
        self._cover_label.setText("封面")
        self._cover_label.setAlignment(Qt.AlignCenter)

        # Info labels
        self._title_label = QLabel("未选择视频")
        self._title_label.setStyleSheet(
            "QLabel { font-size: 16px; font-weight: bold; }"
        )
        self._title_label.setWordWrap(True)

        self._author_label = QLabel("UP主：--")
        self._duration_label = QLabel("时长：--")
        self._bvid_label = QLabel("BV号：--")

        # Layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(self._cover_label)
        top_layout.addSpacing(10)

        info_layout = QVBoxLayout()
        info_layout.addWidget(self._title_label)
        info_layout.addSpacing(5)
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

        # Load cover image
        if info.cover_url:
            self._load_cover(info.cover_url)

    def _load_cover(self, url: str):
        """Download and display cover image asynchronously."""
        worker = _CoverLoadWorker()
        worker.loaded.connect(self._cover_label.setPixmap)
        runner = _CoverLoadRunner(worker, url)
        QThreadPool.globalInstance().start(runner)
