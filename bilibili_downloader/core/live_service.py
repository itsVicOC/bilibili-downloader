"""Desktop-only live supervision. One coordinator owns all state transitions."""

import queue
import random
import shutil
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from bilibili_downloader.api.client import BilibiliAPIError
from bilibili_downloader.api.live import BilibiliLiveClient, LiveAccessError
from bilibili_downloader.core.errors import redact_sensitive_text, user_error_message
from bilibili_downloader.core.live_models import (
    LIVE_STATE_LABELS,
    LiveSettings,
    LiveState,
    LiveSubscription,
    RecordingSegment,
    RecordingSession,
)
from bilibili_downloader.core.live_repository import LiveRepository, utc_now
from bilibili_downloader.core.recorder import MesioBackend, RecorderBackend
from bilibili_downloader.utils.validators import sanitize_filename

RETRY_SECONDS = (2, 5, 10, 30, 60)
ENGINE_ERROR_MESSAGES = {
    "media_open_failed": "暂时无法连接直播流，将重新获取地址",
    "media_processing_failed": "媒体处理失败，已保留文件并准备重连",
    "writer_failed": "录制文件写入失败，请检查输出磁盘",
    "output_directory_failed": "无法访问录制目录，请检查目录权限",
    "output_directory_not_empty": "录制目录已有文件，已停止以避免覆盖",
    "untrusted_media_url": "媒体地址不符合当前支持范围，已停止录制",
    "encrypted_media_unsupported": "当前不支持加密直播流，已停止录制",
    "invalid_playlist": "直播播放列表无效，将重新获取地址",
    "shutdown_timeout": "录制未能及时收尾；未封口文件已保留",
    "recorder_protocol_error": "录制引擎响应异常，请检查是否使用配套版本",
    "relay_bind_failed": "无法启动本机录制连接，请检查系统网络限制",
}


@dataclass
class _Runtime:
    subscription: LiveSubscription
    state: LiveState = LiveState.WAITING
    detail: str = ""
    next_check: float = 0
    cooldown_until: float = 0
    future: Future | None = None
    backend: RecorderBackend | None = None
    session: RecordingSession | None = None
    manual: bool = False
    blocked: bool = False
    retries: int = 0
    offline_checks: int = 0
    stop_reason: str = ""
    skip_pending_broadcast: bool = False
    gap_start: str = ""
    last_media_at: float = 0
    attempt_bytes: int = 0
    attempt_duration: float = 0
    base_bytes: int = 0
    base_duration: float = 0
    speed: float = 0
    attempts: int = 0
    next_disk_check: float = 0
    engine_failed: bool = False
    qualities: list = field(default_factory=list)
    previous_interruption: RecordingSession | None = None


class LiveService:
    def __init__(
        self,
        repository: LiveRepository,
        settings: LiveSettings,
        auth_cookies=None,
        *,
        client_factory=BilibiliLiveClient,
        backend_factory=MesioBackend,
        clock=time.monotonic,
        wall_clock=time.time,
        disk_usage=shutil.disk_usage,
    ):
        self.repository = repository
        self.settings = settings.model_copy(deep=True)
        self._auth = dict(auth_cookies or {})
        self._client_factory = client_factory
        self._backend_factory = backend_factory
        self._clock = clock
        self._wall_clock = wall_clock
        self._disk_usage = disk_usage
        self._commands = queue.Queue()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="live-api")
        self._thread = None
        self._stopping = threading.Event()
        self._snapshot_lock = threading.Lock()
        self._snapshots = []
        self._messages = queue.SimpleQueue()
        self._additions = []
        self._rooms = {
            s.room.room_id: _Runtime(
                s, state=LiveState.WAITING if s.enabled else LiveState.DISABLED
            )
            for s in repository.subscriptions()
        }
        for session in repository.recover_interrupted():
            runtime = self._rooms.get(session.room.room_id)
            if runtime and runtime.previous_interruption is None:
                runtime.previous_interruption = session
        self._last_tick = self._clock()
        self._last_wall_tick = self._wall_clock()
        self._publish()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="live-supervisor", daemon=True
            )
            self._thread.start()

    def command(self, action: str, **kwargs):
        if not self._stopping.is_set():
            self._commands.put((action, kwargs))

    @property
    def active(self):
        return any(row["active"] for row in self.snapshot())

    def snapshot(self):
        with self._snapshot_lock:
            return [dict(row) for row in self._snapshots]

    def messages(self):
        result = []
        while not self._messages.empty():
            result.append(self._messages.get())
        return result

    def request_shutdown(self):
        self._stopping.set()

    @property
    def stopped(self):
        return self._thread is None or not self._thread.is_alive()

    def shutdown(self, timeout=15):
        self.request_shutdown()
        if self._thread:
            self._thread.join(timeout)
        else:
            self._pool.shutdown(wait=False, cancel_futures=True)
        return self.stopped

    def _query(self, room_id, quality, with_streams):
        client = self._client_factory(auth_cookies=dict(self._auth))
        try:
            room = client.get_status(room_id)
            if with_streams and room.live_status == 1:
                room = client.refresh_metadata(room)
            streams = (
                client.get_streams(room_id, quality)
                if with_streams and room.live_status == 1
                else []
            )
            return room, streams
        finally:
            client.close()

    def _resolve(self, source):
        client = self._client_factory(auth_cookies=dict(self._auth))
        try:
            return client.resolve_room(source)
        finally:
            client.close()

    def _run(self):
        try:
            while not self._stopping.is_set():
                self.tick()
                self._stopping.wait(0.2)
        except Exception as exc:
            self._messages.put("直播调度已停止：" + redact_sensitive_text(str(exc)))
        finally:
            for runtime in self._rooms.values():
                if runtime.backend:
                    runtime.stop_reason = "interrupted"
                    runtime.backend.stop()
            deadline = time.monotonic() + 12
            while (
                any(r.backend for r in self._rooms.values())
                and time.monotonic() < deadline
            ):
                for runtime in self._rooms.values():
                    try:
                        self._drain(runtime)
                    except Exception as exc:
                        self._messages.put(
                            "录制收尾失败：" + redact_sensitive_text(str(exc))
                        )
                        if runtime.backend:
                            runtime.backend.kill()
                            runtime.backend = None
                time.sleep(0.05)
            for runtime in self._rooms.values():
                if runtime.backend:
                    runtime.backend.kill()
                    runtime.backend = None
                if runtime.session:
                    try:
                        self._finish(runtime, "interrupted")
                    except Exception as exc:
                        self._messages.put(
                            "保存录制状态失败：" + redact_sensitive_text(str(exc))
                        )
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._publish()

    def tick(self):
        """One nonblocking coordinator step; injectable clock makes recovery testable."""
        now = self._clock()
        wall_now = self._wall_clock()
        if max(now - self._last_tick, wall_now - self._last_wall_tick) > 90:
            for runtime in self._rooms.values():
                runtime.next_check = runtime.cooldown_until
                if runtime.backend:
                    runtime.gap_start = datetime.fromtimestamp(
                        self._last_wall_tick, timezone.utc
                    ).isoformat(timespec="seconds")
                    runtime.detail = "系统恢复运行，重新连接直播流"
                    runtime.backend.stop()
        self._last_tick = now
        self._last_wall_tick = wall_now
        self._handle_commands()
        self._complete_additions()
        for runtime in list(self._rooms.values()):
            try:
                self._drain(runtime)
                if runtime.future and runtime.future.done():
                    future, runtime.future = runtime.future, None
                    self._apply_query(runtime, *future.result())
                if runtime.backend:
                    if now >= runtime.next_disk_check:
                        self._ensure_space(runtime)
                        runtime.next_disk_check = now + 5
                    if now - runtime.last_media_at > 45 and not runtime.stop_reason:
                        runtime.detail = "直播流长时间无数据，重新连接"
                        runtime.backend.stop()
                if (
                    not runtime.blocked
                    and runtime.future is None
                    and now >= max(runtime.next_check, runtime.cooldown_until)
                    and (runtime.subscription.enabled or runtime.manual)
                ):
                    runtime.future = self._pool.submit(
                        self._query,
                        runtime.subscription.room.room_id,
                        runtime.subscription.quality,
                        runtime.backend is None,
                    )
                    runtime.next_check = now + 60 + random.uniform(-10, 10)
            except Exception as exc:
                self._fail(runtime, exc)
        self._publish()

    def _handle_commands(self):
        while True:
            try:
                action, args = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                if action == "add":
                    self._additions.append(
                        (self._pool.submit(self._resolve, args["source"]), args)
                    )
                    continue
                if action == "settings":
                    self.settings = args["settings"].model_copy(deep=True)
                    continue
                if action == "auth":
                    self._auth = dict(args["cookies"])
                    for runtime in self._rooms.values():
                        runtime.blocked = False
                        runtime.next_check = 0
                    continue
                runtime = self._rooms[args["room_id"]]
                if action == "remove" and runtime.backend:
                    raise ValueError("请先停止录制，收尾完成后再移除直播间")
                if action in {"start", "enable"}:
                    runtime.blocked = False
                    runtime.skip_pending_broadcast = False
                    runtime.detail = ""
                    if self._clock() < runtime.cooldown_until:
                        runtime.detail = "请求被限流，冷却至少 5 分钟后重试"
                        if not runtime.backend:
                            runtime.state = LiveState.RECONNECTING
                    runtime.subscription.skipped_broadcast = ""
                    runtime.next_check = 0
                    runtime.manual = action == "start"
                    runtime.retries = 0
                    if action == "enable":
                        runtime.subscription.enabled = True
                elif action in {"stop", "disable", "remove"}:
                    runtime.manual = False
                    if action == "stop":
                        runtime.skip_pending_broadcast = (
                            runtime.future is not None and runtime.backend is None
                        )
                        runtime.subscription.skipped_broadcast = (
                            runtime.subscription.room.broadcast_key
                        )
                    else:
                        runtime.subscription.enabled = False
                    if runtime.backend:
                        runtime.stop_reason = "stopped"
                        runtime.state = LiveState.FINALIZING
                        runtime.backend.stop()
                    elif runtime.session:
                        self._finish(runtime, "stopped")
                    if not runtime.backend:
                        runtime.state = (
                            LiveState.WAITING
                            if runtime.subscription.enabled
                            else LiveState.DISABLED
                        )
                        runtime.detail = (
                            "已停止本场，下次开播自动录制"
                            if action == "stop"
                            else "已关闭自动录制"
                        )
                    if action == "remove":
                        if runtime.backend:
                            raise ValueError("请先停止录制，收尾完成后再移除直播间")
                        self.repository.remove_subscription(args["room_id"])
                        del self._rooms[args["room_id"]]
                        continue
                elif action == "quality":
                    runtime.subscription.quality = int(args["quality"])
                    runtime.detail = "画质设置将在下一次拉流时生效"
                elif action == "room_settings":
                    if runtime.backend or runtime.session:
                        raise ValueError(
                            "请先停止本场并等待收尾，再修改房间目录与分段时长"
                        )
                    runtime.subscription = LiveSubscription.model_validate(
                        {
                            **runtime.subscription.model_dump(),
                            "output_dir": str(
                                Path(args["output_dir"]).expanduser().resolve()
                            ),
                            "segment_seconds": args["segment_seconds"],
                        }
                    )
                self.repository.save_subscription(runtime.subscription)
            except Exception as exc:
                self._messages.put(redact_sensitive_text(str(exc)))

    def _complete_additions(self):
        for future, args in self._additions[:]:
            if not future.done():
                continue
            self._additions.remove((future, args))
            try:
                room = future.result()
                if room.room_id in self._rooms:
                    raise ValueError(f"直播间 {room.room_id} 已在列表中")
                subscription = LiveSubscription(
                    room=room,
                    enabled=args.get("enabled", True),
                    output_dir=self.settings.output_dir,
                    segment_seconds=self.settings.segment_seconds,
                )
                self.repository.save_subscription(subscription)
                self._rooms[room.room_id] = _Runtime(
                    subscription,
                    state=LiveState.WAITING
                    if subscription.enabled
                    else LiveState.DISABLED,
                )
            except Exception as exc:
                self._messages.put(user_error_message(exc))

    def _apply_query(self, runtime, room, streams):
        old_room = runtime.subscription.room
        room.author = room.author or old_room.author
        room.title = room.title or old_room.title
        runtime.subscription.room = room
        if runtime.skip_pending_broadcast:
            runtime.subscription.skipped_broadcast = (
                room.broadcast_key if room.live_status == 1 else ""
            )
            runtime.skip_pending_broadcast = False
        self.repository.save_subscription(runtime.subscription)
        if not runtime.subscription.enabled and not runtime.manual:
            return
        if self._clock() < runtime.cooldown_until:
            runtime.state = (
                LiveState.RECORDING if runtime.backend else LiveState.RECONNECTING
            )
            return
        if room.live_status != 1:
            runtime.offline_checks += 1
            if runtime.offline_checks < 2:
                runtime.next_check = self._clock() + 10
                return
            runtime.subscription.skipped_broadcast = ""
            self.repository.save_subscription(runtime.subscription)
            runtime.manual = False
            if runtime.backend:
                runtime.stop_reason = "completed"
                runtime.state = LiveState.FINALIZING
                runtime.backend.stop()
            elif runtime.session:
                self._finish(runtime, "completed")
            runtime.state = (
                LiveState.WAITING
                if runtime.subscription.enabled
                else LiveState.DISABLED
            )
            runtime.detail = "轮播不录制" if room.live_status == 2 else "等待开播"
            return
        runtime.offline_checks = 0
        if runtime.backend:
            return
        if runtime.subscription.skipped_broadcast == room.broadcast_key:
            runtime.state, runtime.detail = (
                LiveState.WAITING,
                "已停止本场，下次开播自动录制",
            )
            return
        if (
            sum(r.backend is not None for r in self._rooms.values())
            >= self.settings.max_concurrent
        ):
            runtime.state = LiveState.QUEUED
            runtime.detail = "等待录制名额；等待期间的直播无法补录"
            runtime.next_check = self._clock() + 10
            return
        if not streams:
            raise RuntimeError("未获取到可用 AVC 直播流，将重新查询")
        self._begin(runtime, streams)

    def _ensure_space(self, runtime):
        directory = Path(runtime.subscription.output_dir).expanduser()
        if runtime.session and not Path(runtime.session.directory).is_dir():
            raise OSError("录制目录已不可用，已停止录制；恢复目录后重新开始")
        directory.mkdir(parents=True, exist_ok=True)
        if self._disk_usage(directory).free < self.settings.minimum_free_bytes:
            raise OSError("磁盘剩余空间不足，已停止录制；释放空间后点击开始或开启监控")

    def _begin(self, runtime, streams):
        self._ensure_space(runtime)
        runtime.state = LiveState.PREPARING
        stream = streams[runtime.retries % len(streams)]
        runtime.qualities = [q.model_dump() for q in stream.qualities]
        backend = self._backend_factory(self.settings.recorder_path)
        room = runtime.subscription.room
        if runtime.session and runtime.session.room.broadcast_key != room.broadcast_key:
            self._finish(runtime, "completed")
        if runtime.session is None:
            identity = uuid.uuid4().hex
            stamp = utc_now().replace(":", "-")
            directory = (
                Path(runtime.subscription.output_dir).expanduser().resolve()
                / sanitize_filename(redact_sensitive_text(room.author or str(room.uid)))
                / str(room.room_id)
                / f"{stamp}_{identity[:8]}"
            )
            directory.mkdir(parents=True, exist_ok=False)
            runtime.session = RecordingSession(
                id=identity,
                room=room.model_copy(deep=True),
                directory=str(directory),
                started_at=utc_now(),
            )
            runtime.attempts = 0
            if runtime.previous_interruption:
                previous = runtime.previous_interruption
                if previous.room.broadcast_key == room.broadcast_key:
                    last_media = (
                        previous.segments[-1].finalized_at
                        if previous.segments
                        else previous.started_at
                    )
                    runtime.session.gaps.append(
                        {
                            "start": last_media,
                            "end": utc_now(),
                            "reason": "应用中断期间无法补录",
                        }
                    )
                runtime.previous_interruption = None
        session = runtime.session
        session.quality, session.quality_label = stream.quality, stream.quality_label
        session.codec, session.format = stream.codec, stream.format
        if stream.warning and stream.warning not in session.warnings:
            session.warnings.append(stream.warning)
        runtime.attempts += 1
        directory = Path(session.directory) / f"attempt_{runtime.attempts:04d}"
        directory.mkdir(exist_ok=False)
        self.repository.save_session(session)
        try:
            backend.start(stream, directory, runtime.subscription.segment_seconds)
        except Exception:
            backend.kill()
            raise
        runtime.backend = backend
        runtime.engine_failed = False
        runtime.attempt_bytes = 0
        runtime.attempt_duration = 0
        runtime.base_bytes = session.total_size
        runtime.base_duration = sum(s.duration for s in session.segments)
        runtime.last_media_at = self._clock()
        runtime.state = LiveState.RECORDING
        runtime.detail = (
            stream.warning
            or f"{stream.quality_label} · AVC/AAC · {stream.format.upper()}"
        )

    def _drain(self, runtime):
        backend = runtime.backend
        if backend is None:
            return
        exit_code = backend.poll()
        changed = False
        for event in backend.events():
            kind = event["event"]
            if kind == "metrics":
                if event.get("bytes", 0) > runtime.attempt_bytes:
                    runtime.last_media_at = self._clock()
                    if event.get("duration", 0) >= 10:
                        runtime.retries = 0
                    if runtime.gap_start and runtime.session:
                        runtime.session.gaps.append(
                            {
                                "start": runtime.gap_start,
                                "end": utc_now(),
                                "reason": "直播流中断",
                            }
                        )
                        runtime.gap_start = ""
                        changed = True
                runtime.attempt_bytes = event.get("bytes", 0)
                runtime.attempt_duration = event.get("duration", 0)
                runtime.speed = event.get("speed", 0)
            elif kind == "segment_finalized" and runtime.session:
                runtime.last_media_at = self._clock()
                if runtime.gap_start:
                    runtime.session.gaps.append(
                        {
                            "start": runtime.gap_start,
                            "end": utc_now(),
                            "reason": "直播流中断",
                        }
                    )
                    runtime.gap_start = ""
                    changed = True
                if not any(s.path == event["path"] for s in runtime.session.segments):
                    runtime.session.segments.append(
                        RecordingSegment(
                            path=event["path"],
                            duration=event.get("duration", 0),
                            size=event.get("bytes", 0),
                            finalized_at=utc_now(),
                            quality=runtime.session.quality,
                            codec=runtime.session.codec,
                            format=runtime.session.format,
                        )
                    )
                    changed = True
            elif kind == "error":
                runtime.engine_failed = True
                if runtime.blocked and runtime.stop_reason == "failed":
                    continue
                code = event.get("code", "unknown")
                runtime.detail = ENGINE_ERROR_MESSAGES.get(
                    code, "录制引擎发生异常，将重新连接"
                )
                if code in {
                    "untrusted_media_url",
                    "encrypted_media_unsupported",
                    "output_directory_not_empty",
                }:
                    runtime.blocked = True
                    runtime.stop_reason = "failed"
                    runtime.backend.stop()
                if event.get("code") == "rate_limited":
                    runtime.cooldown_until = self._clock() + 300
                    runtime.detail = "媒体服务器限流，冷却至少 5 分钟后重新获取播放地址"
                if runtime.session and runtime.detail not in runtime.session.warnings:
                    runtime.session.warnings.append(runtime.detail)
                    changed = True
        # Consume the entire batch before writing a manifest. A full/unmounted
        # output disk must not discard later file-close events in this batch.
        if changed and runtime.session:
            self.repository.save_session(runtime.session)
        if exit_code is None:
            return
        runtime.backend = None
        runtime.speed = 0
        if self._clock() < runtime.cooldown_until:
            runtime.detail = "请求被限流，冷却至少 5 分钟后重试"
        if exit_code != 0 and runtime.session:
            runtime.engine_failed = True
            runtime.session.warnings.append(
                "录制引擎异常退出；未封口文件已保留在场次目录"
            )
        if runtime.stop_reason:
            self._finish(
                runtime,
                "interrupted"
                if runtime.engine_failed and runtime.stop_reason != "failed"
                else runtime.stop_reason,
            )
            runtime.stop_reason = ""
        else:
            runtime.gap_start = runtime.gap_start or utc_now()
            runtime.state = LiveState.RECONNECTING
            runtime.next_check = (
                self._clock()
                + RETRY_SECONDS[min(runtime.retries, len(RETRY_SECONDS) - 1)]
            )
            runtime.retries += 1

    def _finish(self, runtime, status):
        if runtime.session:
            session = runtime.session
            session.status, session.ended_at = status, utc_now()
            if runtime.gap_start:
                session.gaps.append(
                    {
                        "start": runtime.gap_start,
                        "end": session.ended_at,
                        "reason": "未收到媒体数据",
                    }
                )
            self.repository.save_session(session)
            runtime.session = None
        runtime.gap_start = ""
        runtime.attempt_bytes = runtime.attempt_duration = runtime.speed = 0
        runtime.base_bytes = runtime.base_duration = 0
        runtime.retries = 0
        runtime.state = (
            LiveState.ERROR
            if runtime.blocked
            else LiveState.WAITING
            if runtime.subscription.enabled
            else LiveState.DISABLED
        )

    def _fail(self, runtime, exc):
        runtime.detail = redact_sensitive_text(str(exc))
        rate_limited = (
            isinstance(exc, BilibiliAPIError) and exc.code in {-352, -412}
        ) or (
            isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code in {412, 429}
        )
        permanent = isinstance(exc, (OSError, ValueError, LiveAccessError)) or (
            isinstance(exc, BilibiliAPIError) and exc.code in {-101, -403, 60004}
        )
        if runtime.backend and permanent:
            runtime.stop_reason = "failed"
            runtime.backend.stop()
        runtime.blocked = permanent
        runtime.state = (
            LiveState.ERROR
            if permanent
            else LiveState.RECORDING
            if runtime.backend
            else LiveState.RECONNECTING
        )
        delay = (
            300
            if rate_limited
            else RETRY_SECONDS[min(runtime.retries, len(RETRY_SECONDS) - 1)]
        )
        runtime.next_check = self._clock() + delay
        runtime.retries += 1
        if rate_limited:
            runtime.cooldown_until = runtime.next_check
            runtime.detail = "请求被限流，冷却至少 5 分钟后重试"
        if permanent and runtime.session and not runtime.backend:
            self._finish(runtime, "failed")

    def _publish(self):
        snapshots = []
        for runtime in self._rooms.values():
            session = runtime.session
            snapshots.append(
                {
                    "room_id": runtime.subscription.room.room_id,
                    "author": runtime.subscription.room.author,
                    "title": runtime.subscription.room.title,
                    "enabled": runtime.subscription.enabled,
                    "state": runtime.state.value,
                    "state_label": LIVE_STATE_LABELS[runtime.state],
                    "detail": runtime.detail,
                    "active": runtime.backend is not None,
                    "speed": runtime.speed,
                    "size": max(
                        session.total_size, runtime.base_bytes + runtime.attempt_bytes
                    )
                    if session
                    else 0,
                    "duration": max(
                        sum(s.duration for s in session.segments),
                        runtime.base_duration + runtime.attempt_duration,
                    )
                    if session
                    else 0,
                    "attempt_bytes": runtime.attempt_bytes,
                    "attempt_duration": runtime.attempt_duration,
                    "qualities": runtime.qualities,
                    "quality": runtime.subscription.quality,
                }
            )
            snapshots[-1].update(
                output_dir=runtime.subscription.output_dir,
                segment_seconds=runtime.subscription.segment_seconds,
            )
        with self._snapshot_lock:
            self._snapshots = snapshots
