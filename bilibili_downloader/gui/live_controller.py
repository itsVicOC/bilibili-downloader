"""Single GUI owner for live services, history updates and MP4 exports."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.live_repository import LiveRepository
from bilibili_downloader.core.live_service import LiveService


class LiveUiController(QObject):
    snapshot_changed = Signal(list)
    history_changed = Signal(list)
    message_changed = Signal(str, str)
    export_changed = Signal(bool, str)
    addition_changed = Signal(bool)

    def __init__(self, config, parent=None, service_factory=LiveService):
        super().__init__(parent)
        self.config = config
        self.service = None
        self.repository = None
        self.rows = []
        self.sessions = []
        self.message = ""
        self.message_tone = "info"
        self.export_path = ""
        self.exporting = False
        self.adding = False
        self._addition_ids = set()
        self._revision = -1
        self._closed = False
        self._export = None
        self._cancel = Event()
        self._exports = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="live-export"
        )
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(config.data_dir / "live.lock"))
        try:
            if not self.lock.tryLock(0):
                raise RuntimeError(
                    "另一个 BiliFlow 实例正在管理直播录制，请在该实例中操作"
                )
            self.repository = LiveRepository(config.data_dir / "live.sqlite3")
            self.service = service_factory(
                self.repository, config.load().live, config.auth_cookies
            )
            self.service.start()
            self.destroyed.connect(self.service.request_shutdown)
            if self.repository.recovered_database_path:
                self.notify("损坏的直播数据库已隔离备份，请重新添加直播间", "warning")
            elif self.repository.invalid_records:
                self.notify("部分直播记录无法读取，原始记录已保留在数据库中", "warning")
        except Exception as exc:
            self.notify(str(exc), "danger")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def notify(self, message, tone="info"):
        self.message, self.message_tone = redact_sensitive_text(message), tone
        self.message_changed.emit(self.message, tone)

    def command(self, action, **kwargs):
        if not self.service or self._closed:
            return
        self.service.command(action, **kwargs)

    def add(self, source):
        if self.adding or not self.service:
            return
        self.adding = True
        self._addition_ids = {row["room_id"] for row in self.rows}
        self.addition_changed.emit(True)
        self.notify("正在查询直播间…")
        self.command("add", source=source)

    def refresh(self):
        if not self.service:
            return
        self.rows = self.service.snapshot()
        self.snapshot_changed.emit(self.rows)
        messages = self.service.messages()
        for message in messages:
            self.notify(message, "warning")
        added = bool({row["room_id"] for row in self.rows} - self._addition_ids)
        if self.adding and (added or messages):
            self.adding = False
            self.addition_changed.emit(False)
            if added:
                self.notify("直播间已加入监控列表", "success")
        try:
            revision = self.repository.history_revision
            if revision != self._revision:
                self.sessions = self.repository.sessions()
                self._revision = revision
                self.history_changed.emit(self.sessions)
        except (OSError, ValueError) as exc:
            self.notify(str(exc), "danger")
        if self._export and self._export.done():
            try:
                ok, result = self._export.result()
                self.export_path = str(result) if ok else ""
                self.notify(
                    "MP4 导出完成" if ok else result, "success" if ok else "danger"
                )
            except Exception as exc:
                self.export_path = ""
                self.notify(str(exc), "danger")
            self._export = None
            self.exporting = False
            self.export_changed.emit(False, self.export_path)

    def export(self, source, output):
        source, output = Path(source), Path(output)
        if self.exporting:
            return
        if not source.is_file():
            self.notify("片段文件已不存在，请检查保存目录。", "danger")
            return
        if output.resolve() == source.resolve():
            self.notify("请使用不同的导出文件名，以保留录制源文件。", "warning")
            return
        self._cancel.clear()
        self.export_path = ""
        self.exporting = True
        self._export = self._exports.submit(
            FFmpegManager.remux_live,
            source,
            output,
            self.config.load().ffmpeg_path or None,
            self._cancel.is_set,
        )
        self.notify("正在无损转封装，源文件会保留…")
        self.export_changed.emit(True, "")

    def shutdown(self):
        self.timer.stop()
        self._closed = True
        self._cancel.set()
        if self.service:
            self.service.request_shutdown()
            if self.service.stopped:
                self.lock.unlock()
        else:
            self.lock.unlock()
        self._exports.shutdown(wait=False, cancel_futures=True)
