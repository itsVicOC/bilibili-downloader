"""Background FFmpeg availability check."""

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.core.ffmpeg import FFmpegManager


class FFmpegCheckWorker(QObject):
    finished = Signal(bool, str)


class FFmpegCheckRunner(QRunnable):
    def __init__(self, worker: FFmpegCheckWorker, custom_path: str | None):
        super().__init__()
        self._worker = worker
        self._custom_path = custom_path
        self.setAutoDelete(True)

    def run(self):
        self._worker.finished.emit(
            *FFmpegManager.check_available(self._custom_path)
        )
