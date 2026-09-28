"""Versioned subprocess boundary for the bundled Rust recorder."""

import json
import math
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Protocol

from bilibili_downloader.core.ffmpeg import _subprocess_window_kwargs
from bilibili_downloader.core.live_models import LiveStream

ENGINE_REVISION = "1897d736a4560f267700d7c4c1cf02dffc3c4c56"


class RecorderBackend(Protocol):
    def start(self, stream: LiveStream, directory: Path, segment_seconds: int): ...
    def stop(self): ...
    def events(self) -> list[dict]: ...
    def poll(self): ...
    def kill(self): ...


def find_recorder(custom_path: str = "") -> Path:
    name = (
        "biliflow-recorder.exe"
        if platform.system() == "Windows"
        else "biliflow-recorder"
    )
    if custom_path:
        path = Path(custom_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError("录制引擎路径不存在，请在直播设置中重新选择")
        return path
    candidates = []
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [executable_dir / name, executable_dir.parent / "Resources" / name]
        )
        if getattr(sys, "_MEIPASS", None):
            candidates.append(Path(sys._MEIPASS) / name)
    else:
        candidates.append(
            Path(__file__).resolve().parents[2]
            / "native"
            / "recorder"
            / "target"
            / "release"
            / name
        )
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "未找到录制引擎：请使用 full 包，或在直播设置中选择 biliflow-recorder"
    )


def check_recorder(path: Path, *, allow_test_engine=False):
    result = subprocess.run(
        [str(path), "--check"],
        capture_output=True,
        timeout=5,
        **_subprocess_window_kwargs(),
    )
    if result.returncode != 0 or len(result.stdout) > 65536:
        raise ValueError("录制引擎自检失败")
    try:
        info = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("录制引擎未返回有效协议") from exc
    if (
        not isinstance(info, dict)
        or info.get("v") != 1
        or info.get("name") != "biliflow-recorder"
        or info.get("engine_revision") != ENGINE_REVISION
        or not isinstance(info.get("formats"), list)
        or not {"flv", "ts", "fmp4"}.issubset(info.get("formats", []))
        or (info.get("test_fixtures") is not False and not allow_test_engine)
    ):
        raise ValueError("录制引擎版本或能力不匹配，请安装本版本配套引擎")
    return info


class MesioBackend:
    def __init__(self, custom_path="", *, allow_test_engine=False):
        self.path = find_recorder(custom_path)
        check_recorder(self.path, allow_test_engine=allow_test_engine)
        self._process = None
        self._events = queue.Queue(maxsize=512)
        self._metrics = None
        self._lock = threading.Lock()
        self._output_dir = None
        self._stopping_at = None
        self._reader = None

    def start(self, stream: LiveStream, directory: Path, segment_seconds: int):
        if self._process is not None:
            raise RuntimeError("一个录制引擎实例只能开始一次")
        self._output_dir = directory.resolve()
        command = {
            "v": 1,
            "command": "start",
            "url": stream.url,
            "output_dir": str(self._output_dir),
            "format": stream.format,
            "segment_seconds": segment_seconds,
        }
        encoded = (json.dumps(command) + "\n").encode()
        if len(encoded) > 65536:
            raise ValueError("录制启动参数超过协议大小限制")
        self._process = subprocess.Popen(
            [str(self.path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            **_subprocess_window_kwargs(),
        )
        self._reader = threading.Thread(
            target=self._read, name="live-recorder-events", daemon=True
        )
        self._reader.start()
        try:
            self._process.stdin.write(encoded)
            self._process.stdin.flush()
        except OSError:
            self._process.kill()
            raise RuntimeError("无法向录制引擎发送启动指令") from None

    def _read(self):
        try:
            while True:
                line = self._process.stdout.readline(65537)
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError("oversized event")
                event = json.loads(line)
                if (
                    not isinstance(event, dict)
                    or event.get("v") != 1
                    or event.get("event")
                    not in {
                        "ready",
                        "started",
                        "metrics",
                        "segment_finalized",
                        "error",
                        "stopped",
                    }
                ):
                    raise ValueError("invalid event")
                if event["event"] == "error" and (
                    not isinstance(event.get("code"), str) or len(event["code"]) > 128
                ):
                    raise ValueError("invalid error code")
                if event["event"] == "segment_finalized":
                    path = Path(event["path"]).resolve(strict=True)
                    if not path.is_file() or self._output_dir not in path.parents:
                        raise ValueError("invalid segment path")
                    event["path"] = str(path)
                for key in ("bytes", "duration", "speed"):
                    if key in event and (
                        not isinstance(event[key], (int, float))
                        or isinstance(event[key], bool)
                        or not math.isfinite(event[key])
                        or event[key] < 0
                    ):
                        raise ValueError("invalid metrics")
                if event["event"] == "metrics":
                    with self._lock:
                        self._metrics = event
                else:
                    self._events.put(event, timeout=1)
        except (ValueError, KeyError, TypeError, OSError, queue.Full):
            self._process.kill()
            # A fixed error avoids reflecting a signed URL from a malformed event.
            try:
                self._events.put_nowait(
                    {"event": "error", "code": "recorder_protocol_error"}
                )
            except queue.Full:
                pass
        finally:
            self._process.stdout.close()

    def stop(self):
        if self._process is None or self._stopping_at is not None:
            return
        self._stopping_at = time.monotonic()
        if self._process.stdin.closed:
            return
        try:
            self._process.stdin.write(b'{"v":1,"command":"stop"}\n')
            self._process.stdin.flush()
            self._process.stdin.close()
        except OSError:
            pass

    def poll(self):
        if self._process is None:
            return None
        if (
            self._stopping_at is not None
            and self._process.poll() is None
            and time.monotonic() - self._stopping_at > 10
        ):
            self._process.kill()
        # Do not finish until the event reader has consumed finalized files.
        if self._reader and self._reader.is_alive():
            return None
        result = self._process.poll()
        if (
            result is not None
            and self._process.stdin
            and not self._process.stdin.closed
        ):
            try:
                self._process.stdin.close()
            except OSError:
                pass
        return result

    def events(self):
        result = []
        with self._lock:
            if self._metrics is not None:
                result.append(self._metrics)
                self._metrics = None
        while True:
            try:
                result.append(self._events.get_nowait())
            except queue.Empty:
                return result

    def kill(self):
        if self._process and self._process.poll() is None:
            self._process.kill()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
