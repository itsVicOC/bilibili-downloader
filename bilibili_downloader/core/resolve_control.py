"""Optional observation and cooperative cancellation for metadata imports."""

from dataclasses import dataclass, field
from threading import Event
from typing import Callable

from bilibili_downloader.core.models import ContentFailure, VideoInfo


class ResolveCancelled(Exception):
    """The caller cancelled between metadata requests."""


@dataclass
class ResolveControl:
    cancel: Event = field(default_factory=Event)
    progress: Callable[[str, int, int], None] = lambda *_: None
    item_ready: Callable[[VideoInfo], None] = lambda *_: None
    failure_ready: Callable[[ContentFailure], None] = lambda *_: None

    def checkpoint(self, stage="读取来源", completed=0, total=0):
        if self.cancel.is_set():
            raise ResolveCancelled()
        self.progress(stage, completed, total)
