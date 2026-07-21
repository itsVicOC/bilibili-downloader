"""Worker and runner for async video URL resolution."""

import logging

from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.batch import BatchResolver
from bilibili_downloader.core.models import VideoQuality

logger = logging.getLogger(__name__)


class ResolveWorker(QObject):
    """Holds resolution parameters and signals.

    Signals:
        finished: (VideoInfo, video_streams, audio_streams, playurl_ok)
        error: (error_message)
    """

    finished = Signal(object, list, list, bool)
    error = Signal(str)

    def __init__(self, client: BilibiliAPIClient, source: str):
        super().__init__()
        self._client = client
        self._source = source


class ResolveRunner(QRunnable):
    """Runs ResolveWorker in a thread pool."""

    def __init__(self, worker: ResolveWorker):
        super().__init__()
        self._worker = worker

    def run(self):
        try:
            resolver = BatchResolver(self._worker._client)
            info = resolver.resolve_one(self._worker._source)
            # Try to fetch playurl for quality discovery (degraded on failure)
            video_streams = []
            audio_streams = []
            playurl_ok = False
            try:
                playurl_data = self._worker._client.get_play_url(
                    bvid=info.bvid,
                    cid=info.cid,
                    quality=VideoQuality.Q8K,
                    discover_all=True,
                )
                video_streams = playurl_data.get("video_streams", [])
                audio_streams = playurl_data.get("audio_streams", [])
                playurl_ok = True
            except Exception as e:  # noqa: BLE001
                # playurl failure is non-fatal; show video info anyway
                logger.warning("Playurl fetch failed for %s: %s", info.bvid, e)

            self._worker.finished.emit(
                info, video_streams, audio_streams, playurl_ok
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Video resolution failed for %s", self._worker._source)
            self._worker.error.emit(str(e))
