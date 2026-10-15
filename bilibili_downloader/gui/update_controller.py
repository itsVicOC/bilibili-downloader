"""Asynchronous update ownership for the main window."""

from threading import Event

import httpx
from packaging.version import Version
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.updater import UpdateCancelled, UpdateService


class _Signals(QObject):
    finished = Signal(int, object)
    error = Signal(int, str)
    progress = Signal(int, int)


class _Job(QRunnable):
    def __init__(self, signals, request_id, operation):
        super().__init__()
        self.signals, self.request_id, self.operation = signals, request_id, operation

    def run(self):
        try:
            result = self.operation()
            self.signals.finished.emit(self.request_id, result)
        except Exception as exc:
            try:
                if isinstance(exc, UpdateCancelled):
                    message = "更新已取消"
                elif isinstance(exc, httpx.TimeoutException):
                    message = "连接 GitHub 超时，请检查网络后重试。"
                elif isinstance(exc, httpx.RequestError):
                    message = "无法连接 GitHub，请检查网络或代理后重试。"
                elif isinstance(exc, httpx.HTTPStatusError):
                    message = (
                        f"GitHub 返回 HTTP {exc.response.status_code}，请稍后重试。"
                    )
                else:
                    message = redact_sensitive_text(str(exc))
                self.signals.error.emit(self.request_id, message)
            except RuntimeError:
                pass


class UpdateController(QObject):
    status_changed = Signal(str, str)
    busy_changed = Signal(bool, str)
    progress_changed = Signal(int)
    available = Signal(object)
    prepared = Signal(object)
    pending_changed = Signal(object)
    failed = Signal(str, bool)

    def __init__(self, config, parent=None, *, service=None):
        super().__init__(parent)
        self.config = config
        self.service = service or UpdateService(config.data_dir)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._signals = _Signals(self)
        self._signals.finished.connect(self._finished)
        self._signals.error.connect(self._error)
        self._signals.progress.connect(self._progress)
        self._request_id = 0
        self._cancel = Event()
        self._kind = ""
        self._manual = False
        self._invalidated = False
        self._closed = False
        self.has_checked = False
        self.pending = self.service.load_prepared()
        self.release = self.pending.release if self.pending else None

    @property
    def busy(self):
        return bool(self._kind)

    def invalidate_check(self, *_args):
        if self._kind == "check":
            self._invalidated = True
            self._cancel.set()

    def _start(self, kind, operation, *, manual=True):
        if self.busy or self._closed:
            return False
        self._request_id += 1
        self._kind, self._manual, self._invalidated = kind, manual, False
        self._cancel = Event()
        self.busy_changed.emit(True, kind)
        self.pool.start(_Job(self._signals, self._request_id, operation))
        return True

    def check(self, channel, *, manual=True):
        if self.busy or self._closed:
            return False
        self.has_checked = True
        self.status_changed.emit("正在检查更新…", "info")
        return self._start(
            "check", lambda: self.service.check(channel, self._cancel), manual=manual
        )

    def download(self, release):
        if self.busy:
            return False
        self.release = release
        self.status_changed.emit("正在下载并校验更新包…", "info")
        self.progress_changed.emit(0)
        return self._start(
            "download",
            lambda: self.service.prepare(
                release,
                self._cancel,
                lambda value: self._signals.progress.emit(self._request_id, value),
            ),
        )

    def prepare_install(self):
        if self.busy or self.pending is None:
            return False
        self.status_changed.emit("正在重新校验并准备安装…", "info")
        return self._start(
            "stage", lambda: self.service.stage(self.pending, self._cancel)
        )

    def cancel(self):
        self._cancel.set()
        self.status_changed.emit("正在取消更新…", "info")

    def shutdown(self):
        self._closed = True
        self._cancel.set()

    def _progress(self, request_id, value):
        if request_id == self._request_id and not self._cancel.is_set():
            self.progress_changed.emit(value)

    def _finish_job(self, request_id):
        if request_id != self._request_id:
            return None
        kind = self._kind
        self._kind = ""
        self.busy_changed.emit(False, kind)
        return kind

    def _finished(self, request_id, result):
        kind = self._finish_job(request_id)
        if not kind:
            return
        if self._closed:
            return
        if self._invalidated:
            self.status_changed.emit("通道已修改，请重新检查更新。", "info")
            return
        if self._cancel.is_set():
            self.status_changed.emit("更新已取消", "info")
            return
        if kind == "check":
            self.release = result
            if result is None:
                self.status_changed.emit("当前已是所选通道的最新版本", "success")
            else:
                skipped = {
                    Version(value)
                    for value in self.config.load().skipped_update_versions
                    if _valid_version(value)
                }
                if not self._manual and Version(result.version) in skipped:
                    self.status_changed.emit(
                        f"已跳过 v{result.version}；手动检查仍可更新。", "info"
                    )
                    return
                self.status_changed.emit(f"发现新版本 v{result.version}", "success")
                self.available.emit(result)
        else:
            self.pending = result
            self.pending_changed.emit(result)
            self.status_changed.emit(
                result.reason or f"v{result.release.version} 已准备好，可安装并重启。",
                "warning" if result.reason else "success",
            )
            self.prepared.emit(result)

    def _error(self, request_id, message):
        kind = self._finish_job(request_id)
        if not kind:
            return
        if self._closed:
            return
        if self._invalidated:
            self.status_changed.emit("通道已修改，请重新检查更新。", "info")
            return
        cancelled = self._cancel.is_set()
        self.status_changed.emit(
            "更新已取消" if cancelled else f"更新失败：{message}",
            "info" if cancelled else "danger",
        )
        if not cancelled:
            self.failed.emit(message, self._manual)


def _valid_version(value):
    try:
        Version(value)
        return True
    except (ValueError, TypeError):
        return False
