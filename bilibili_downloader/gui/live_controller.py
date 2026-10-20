"""Single GUI owner for live services, history updates and MP4 exports."""

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Event

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.live_models import LiveExport
from bilibili_downloader.core.live_repository import LiveRepository
from bilibili_downloader.core.live_service import LiveService


class LiveUiController(QObject):
    snapshot_changed = Signal(list)
    history_changed = Signal(list)
    message_changed = Signal(str, str)
    export_changed = Signal(bool, str)
    addition_changed = Signal(bool)
    settings_applied = Signal(bool, str)

    def __init__(self, config, parent=None, service_factory=LiveService, *, autostart=True):
        super().__init__(parent)
        self.config = config
        self._service_factory = service_factory
        self.service = None
        self.repository = None
        self.rows = []
        self.sessions = []
        self.message = ""
        self.message_tone = "info"
        self.export_path = ""
        self.export_source = ""
        self.export_destination = ""
        self.exporting = False
        self.adding = False
        self._addition_ids = set()
        self._revision = -1
        self._closed = False
        self._background_enabled = autostart
        self._export = None
        self._settings_result = None
        self._active_session = None
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
            for session in self.repository.sessions():
                if session.mp4_export and session.mp4_export.status == "running":
                    resumed = session.mp4_export.model_copy(update={
                        "status": "queued", "progress": "等待继续导出",
                    })
                    self.repository.update_export(session.id, resumed)
            self.service = service_factory(
                self.repository, config.load().live, config.auth_cookies
            )
            if autostart:
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

    def apply_live_settings(self, settings, directory_modes):
        if directory_modes:
            self._settings_result = Future()
            self.command("settings", settings=settings, directory_modes=directory_modes,
                         completion=self._settings_result)
        else:
            self.command("settings", settings=settings)

    def refresh(self):
        if not self.service:
            return
        self.rows = self.service.snapshot()
        self.snapshot_changed.emit(self.rows)
        messages = self.service.messages()
        for message in messages:
            self.notify(message, "warning")
        if self._settings_result and self._settings_result.done():
            ok, message = self._settings_result.result()
            self.settings_applied.emit(ok, message)
            self.notify(message, "success" if ok else "danger")
            self._settings_result = None
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
                self.export_path = (str(result) if self._active_session else self.export_destination) if ok else ""
                self.notify(
                    "MP4 导出完成" if ok else result, "success" if ok else "danger"
                )
            except Exception as exc:
                self.export_path = ""
                self.notify(str(exc), "danger")
            self._export = None
            self._active_session = None
        if not self._closed and self._background_enabled and self._export is None:
            self._start_next_export()
        self.exporting = self._export is not None or any(
            s.mp4_export and s.mp4_export.status == "queued" for s in self.sessions
        )
        self.export_changed.emit(self.exporting, self.export_path)

    def export_session(self, session_id, output):
        if self._closed or not self.repository:
            return
        session = self.repository.session(session_id)
        if not session or session.status == "recording" or not session.segments:
            self.notify("请等待场次收尾完成，并确认已有封口片段。", "warning")
            return
        if session.mp4_export and session.mp4_export.status in {"queued", "running"}:
            return
        self.repository.update_export(session.id, LiveExport(path=str(Path(output).expanduser().resolve())))
        self.notify("已加入合并队列，原始分段会保留。")
        self.refresh()

    def _start_next_export(self):
        for session in reversed(self.repository.sessions()):
            if not session.mp4_export or session.mp4_export.status != "queued":
                continue
            export = session.mp4_export.model_copy(update={"status": "running", "progress": "准备导出"})
            self.repository.update_export(session.id, export)
            self._cancel.clear()
            self._active_session = session.id
            self.export_source = ""
            self.export_destination = export.path
            self._export = self._exports.submit(self._run_session_export, session, export)
            break

    def _run_session_export(self, session, export):
        def progress(message):
            export.progress = message
            self.repository.update_export(session.id, export)

        try:
            settings = self.config.load()
            ok, result = FFmpegManager.merge_live_segments(
                [s.path for s in session.segments], Path(export.path),
                settings.ffmpeg_path or None, self._cancel.is_set, progress,
                minimum_free_bytes=settings.live.minimum_free_bytes,
                overwrite=not export.automatic,
            )
            if ok:
                export.status, export.path, export.progress = "completed", str(result), "已导出 MP4"
            elif self._cancel.is_set():
                export.status, export.progress = "queued", "下次启动继续导出"
            else:
                export.status, export.error, export.progress = "failed", redact_sensitive_text(result), "导出失败"
            self.repository.update_export(session.id, export)
            return ok, result
        except Exception as exc:
            export.status, export.error, export.progress = "failed", redact_sensitive_text(str(exc)), "导出失败"
            self.repository.update_export(session.id, export)
            return False, export.error

    def export(self, source, output):
        source, output = Path(source), Path(output)
        if self.exporting or self._closed:
            return
        if not source.is_file():
            self.notify("片段文件已不存在，请检查保存目录。", "danger")
            return
        if output.resolve() == source.resolve():
            self.notify("请使用不同的导出文件名，以保留录制源文件。", "warning")
            return
        self._cancel.clear()
        self.export_path = ""
        self.export_source = str(source.resolve())
        self.export_destination = str(output)
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
            if self.background_stopped:
                self.lock.unlock()
        else:
            self.lock.unlock()
        self._exports.shutdown(wait=False, cancel_futures=True)

    @property
    def background_stopped(self):
        stopped = (self.service is None or self.service.stopped) and (
            self._export is None or self._export.done()
        )
        if stopped and self._closed:
            self.lock.unlock()
        return stopped

    def start_background(self):
        if self.service and not self._closed:
            self._background_enabled = True
            self.service.start()

    def restart_after_update_abort(self):
        if not self.background_stopped:
            return False
        self.lock.unlock()
        self._closed = False
        self._background_enabled = True
        self._cancel.clear()
        self._export = None
        self._active_session = None
        self.exporting = False
        self._exports = ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-export")
        try:
            if not self.lock.tryLock(0):
                raise RuntimeError("另一个实例正在管理直播录制，请重新打开软件")
            self.service = self._service_factory(self.repository, self.config.load().live, self.config.auth_cookies)
            self.service.start()
            self.destroyed.connect(self.service.request_shutdown)
        except Exception as exc:
            self.notify(str(exc), "danger")
            self.service = None
        self.timer.start(1000)
        return True
