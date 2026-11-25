"""Viewport-scoped, offline thumbnails for downloaded media."""

import stat
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader

from bilibili_downloader.core.ffmpeg import FFmpegManager


@dataclass(frozen=True)
class ThumbnailFile:
    path: str
    state: str
    signature: str | None

    @classmethod
    def from_entry(cls, entry):
        if entry and entry["state"] in {"available", "unchecked"}:
            return cls(entry["path"], entry["state"], entry.get("signature"))
        return None

    def version(self):
        try:
            facts = Path(self.path).lstat()
            if stat.S_ISREG(facts.st_mode) and facts.st_size:
                return facts.st_dev, facts.st_ino, facts.st_size, facts.st_mtime_ns
        except OSError:
            pass
        return None


@dataclass(frozen=True)
class ThumbnailSource:
    cover: ThumbnailFile | None
    video: ThumbnailFile | None
    duration: int
    ffmpeg_path: str | None


@dataclass
class _Thumbnail:
    versions: tuple
    image: QImage


def _read_thumbnail(source, previous):
    versions = tuple(entry.version() if entry else None for entry in (source.cover, source.video))
    if previous is not None and previous.versions == versions:
        return previous
    image = QImage()
    if versions[0]:
        reader = QImageReader(source.cover.path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and not size.isEmpty():
            size.scale(QSize(480, 480), Qt.KeepAspectRatio)
            reader.setScaledSize(size)
            image = reader.read()
    if image.isNull() and versions[1]:
        executable = FFmpegManager.find_executable(source.ffmpeg_path)
        if executable:
            image = QImage.fromData(FFmpegManager.thumbnail_frame(Path(source.video.path), executable, source.duration))
    return _Thumbnail(versions, image)


class _ThumbnailSignals(QObject):
    finished = Signal(object, int, object)


class _ThumbnailJob(QRunnable):
    def __init__(self, source, generation, previous):
        super().__init__()
        self.source, self.generation, self.previous = source, generation, previous
        self.signals = _ThumbnailSignals()

    def run(self):
        try:
            thumbnail = _read_thumbnail(self.source, self.previous)
        except (OSError, ValueError):
            thumbnail = _Thumbnail((), QImage())
        self.signals.finished.emit(self.source, self.generation, thumbnail)


class LibraryThumbnails(QObject):
    changed = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._cache = OrderedDict()
        self._visible = {}
        self._validated = set()
        self._active = set()
        self._generation = 0

    def image(self, source):
        if source in self._cache:
            self._cache.move_to_end(source)
            return self._cache[source].image
        return QImage()

    def reset(self):
        self._generation += 1
        self._visible.clear()
        self._validated.clear()

    def show(self, sources):
        self._visible = {source: ids for source, ids in sources.items() if source.cover or source.video}
        self._validated.intersection_update(self._visible)
        self._start_visible()

    def _start_visible(self):
        for source in self._visible:
            if len(self._active) >= 2:
                break
            token = source, self._generation
            if source in self._validated or token in self._active:
                continue
            self._active.add(token)
            job = _ThumbnailJob(source, self._generation, self._cache.get(source))
            job.signals.finished.connect(self._finished)
            self._pool.start(job)

    def _finished(self, source, generation, thumbnail):
        self._active.discard((source, generation))
        if generation == self._generation and source in self._visible:
            self._validated.add(source)
            self._cache[source] = thumbnail
            self._cache.move_to_end(source)
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
            self.changed.emit(self._visible[source])
        self._start_visible()
