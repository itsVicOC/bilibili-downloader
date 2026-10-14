"""Standard-library update contract shared with the standalone installer."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import sqlite3
import stat
import sys
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

BUILD_INFO_FILENAME = "biliflow-build.json"
UPDATER_PROTOCOL = 1
DATA_FILES = ("config.json", "tasks.sqlite3", "live.sqlite3")


class UpdateError(ValueError):
    """An update cannot be applied safely."""


class InstallDataInApplicationError(UpdateError):
    """Replacing an application directory would also replace user data."""


def normalize_arch(value: str) -> str:
    value = value.lower()
    return {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(value, value)


@dataclass(frozen=True)
class BuildInfo:
    version: str
    platform: str
    architecture: str
    variant: str
    updater_protocol: int = UPDATER_PROTOCOL

    @classmethod
    def parse(cls, value: dict) -> BuildInfo:
        if not isinstance(value, dict):
            raise UpdateError("构建信息格式无效")
        try:
            info = cls(**{key: value[key] for key in cls.__dataclass_fields__})
        except (KeyError, TypeError) as exc:
            raise UpdateError("构建信息不完整") from exc
        if (
            not isinstance(info.version, str)
            or not info.version
            or info.platform not in ("macOS", "Windows")
            or info.architecture not in ("x86_64", "arm64")
            or info.variant not in ("full", "lite")
            or type(info.updater_protocol) is not int
            or info.updater_protocol != UPDATER_PROTOCOL
        ):
            raise UpdateError("不支持此更新包的构建信息或更新协议")
        return info

    @property
    def archive_root(self) -> str:
        return (
            "BilibiliDownloader.app"
            if self.platform == "macOS"
            else "BilibiliDownloader"
        )

    @property
    def resource_dir(self) -> str:
        return "Contents/Resources" if self.platform == "macOS" else ""

    @property
    def executable(self) -> str:
        return (
            "Contents/MacOS/BilibiliDownloader"
            if self.platform == "macOS"
            else "BilibiliDownloader.exe"
        )

    @property
    def helper(self) -> str:
        return (
            "biliflow-updater" if self.platform == "macOS" else "biliflow-updater.exe"
        )

    def read_from(self, root: Path) -> BuildInfo:
        try:
            return self.parse(
                json.loads(
                    (root / self.resource_dir / BUILD_INFO_FILENAME).read_text("utf-8")
                )
            )
        except (OSError, ValueError) as exc:
            raise UpdateError("无法读取更新包构建信息") from exc


def installed_build(executable: Path | None = None) -> tuple[Path, BuildInfo] | None:
    if executable is None and not getattr(sys, "frozen", False):
        return None
    executable = (executable or Path(sys.executable)).resolve()
    system = {"darwin": "macOS", "win32": "Windows"}.get(sys.platform)
    if system is None:
        return None
    root = executable.parents[2] if system == "macOS" else executable.parent
    resources = root / "Contents/Resources" if system == "macOS" else root
    try:
        info = BuildInfo.parse(
            json.loads((resources / BUILD_INFO_FILENAME).read_text("utf-8"))
        )
        if (
            info.platform != system
            or info.architecture != normalize_arch(platform.machine())
            or (root / info.executable).resolve() != executable
            or not (resources / info.helper).is_file()
        ):
            return None
        return root, info
    except (OSError, ValueError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_archive(path: Path, expected: BuildInfo) -> int:
    """Validate the virtual ZIP tree before any extractor can follow its links."""
    root = expected.archive_root
    names: set[str] = set()
    folded: set[str] = set()
    files: set[str] = set()
    links: dict[str, str] = {}
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > 100_000:
                raise UpdateError("更新包文件数量异常")
            for entry in archive.infolist():
                name = entry.filename.rstrip("/")
                parts = name.split("/")
                if (
                    not name
                    or "\\" in name
                    or "\x00" in name
                    or any(part in ("", ".", "..") or ":" in part for part in parts)
                    or parts[0]
                    not in (
                        (root, "__MACOSX") if expected.platform == "macOS" else (root,)
                    )
                    or name.casefold() in folded
                ):
                    raise UpdateError(f"更新包包含不安全或重复路径：{name}")
                if expected.platform == "Windows" and any(
                    part.endswith((".", " "))
                    or part.split(".")[0].upper()
                    in {
                        "CON",
                        "PRN",
                        "AUX",
                        "NUL",
                        *(f"COM{i}" for i in range(1, 10)),
                        *(f"LPT{i}" for i in range(1, 10)),
                    }
                    for part in parts
                ):
                    raise UpdateError("更新包包含无效的 Windows 路径")
                names.add(name)
                folded.add(name.casefold())
                if not entry.is_dir():
                    files.add(name)
                total += entry.file_size
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    if (
                        expected.platform != "macOS"
                        or parts[0] != root
                        or entry.file_size > 4096
                    ):
                        raise UpdateError("更新包包含不支持的符号链接")
                    target = archive.read(entry).decode("utf-8")
                    if (
                        not target
                        or target.startswith("/")
                        or "\\" in target
                        or "\x00" in target
                        or ":" in target
                    ):
                        raise UpdateError("更新包符号链接目标无效")
                    links[name] = target
                elif stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise UpdateError("更新包包含特殊文件")
            if total > 4 * 1024**3:
                raise UpdateError("更新包解压大小异常")

            def resolve(name):
                pending = name.split("/")
                resolved = []
                count = 0
                while pending:
                    part = pending.pop(0)
                    if part in ("", "."):
                        continue
                    if part == "..":
                        if len(resolved) <= 1:
                            raise UpdateError("更新包符号链接越出应用目录")
                        resolved.pop()
                        continue
                    resolved.append(part)
                    key = "/".join(resolved)
                    if key in links:
                        count += 1
                        if count > 40:
                            raise UpdateError("更新包符号链接形成循环")
                        resolved.pop()
                        pending = links[key].split("/") + pending
                if not resolved or resolved[0] != root:
                    raise UpdateError("更新包符号链接越出应用目录")
                return "/".join(resolved)

            for name in names:
                if name.split("/")[0] == root:
                    resolved = resolve(name)
                    if (
                        name in links
                        and resolved not in names
                        and not any(item.startswith(resolved + "/") for item in names)
                    ):
                        raise UpdateError("更新包包含失效的符号链接")
                    for parent in PurePosixPath(name).parents:
                        key = str(parent)
                        if key in files:
                            raise UpdateError("更新包路径类型冲突")
            resource = PurePosixPath(root) / expected.resource_dir
            required = (
                str(resource / BUILD_INFO_FILENAME),
                str(resource / expected.helper),
                str(PurePosixPath(root) / expected.executable),
            )
            if any(name not in files or name in links for name in required):
                raise UpdateError("更新包缺少程序、构建信息或更新程序")
            info = BuildInfo.parse(json.loads(archive.read(required[0])))
            if info != expected:
                raise UpdateError("更新包版本、平台、架构或 full/lite 类型不匹配")
    except (zipfile.BadZipFile, UnicodeError, KeyError, json.JSONDecodeError) as exc:
        raise UpdateError("更新包结构无效") from exc
    return total


class RuntimeLease:
    """Shared application lifetime lease; exclusive leases protect replacement."""

    def __init__(self, path: Path, *, exclusive=False):
        self.path = path
        self.exclusive = exclusive
        self._stream = None
        self._overlapped = None

    def acquire(self) -> bool:
        if self._stream is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        if os.name == "nt":
            import msvcrt
            from ctypes import wintypes

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            overlap = Overlapped()
            lock = ctypes.windll.kernel32.LockFileEx
            lock.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            lock.restype = wintypes.BOOL
            ok = lock(
                msvcrt.get_osfhandle(stream.fileno()),
                1 | (2 if self.exclusive else 0),
                0,
                1,
                0,
                ctypes.byref(overlap),
            )
            self._overlapped = overlap
        else:
            import fcntl

            try:
                fcntl.flock(
                    stream,
                    (fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH)
                    | fcntl.LOCK_NB,
                )
                ok = True
            except BlockingIOError:
                ok = False
        if not ok:
            stream.close()
            return False
        self._stream = stream
        return True

    def release(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def __enter__(self):
        if not self.acquire():
            raise UpdateError("另一实例正在运行或更新，请关闭其他实例后重试")
        return self

    def __exit__(self, *_args):
        self.release()


def build_payload(info: BuildInfo) -> dict:
    return asdict(info)


def subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for key in list(environment):
        if key.startswith(("_PYI_", "BILIFLOW_UPDATE_")):
            environment.pop(key, None)
    for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        original = environment.pop(key + "_ORIG", None)
        if original is None:
            environment.pop(key, None)
        else:
            environment[key] = original
    return environment


def ensure_install_data_outside(
    target: Path, data: Path, build: BuildInfo, *, extra_paths=()
) -> None:
    """Portable installations must not lose media, caches or custom tools."""
    target = target.resolve()
    bundled_tools = set()
    if build.variant == "full":
        suffix = ".exe" if build.platform == "Windows" else ""
        bundled_tools = {
            target / build.resource_dir / (name + suffix)
            for name in ("ffmpeg", "biliflow-recorder")
        }

    def check(value, *, tool=False, existing=False):
        if not isinstance(value, str) or not value:
            return
        path = Path(value).expanduser()
        if existing and not path.exists():
            return
        if tool and path.resolve() in bundled_tools:
            return
        if any(
            candidate == target or target in candidate.parents
            for candidate in (path.absolute(), path.resolve())
        ):
            raise InstallDataInApplicationError(
                f"保存目录、已有媒体或自定义工具位于程序目录内：{path}。请将数据移到程序目录之外后重试，或手动安装更新。"
            )

    def payload_paths(value):
        if isinstance(value, dict):
            for key, entry in value.items():
                if key in ("output_dir", "output_path", "directory", "path"):
                    check(entry, existing=True)
                elif isinstance(entry, (dict, list)):
                    payload_paths(entry)
        elif isinstance(value, list):
            for entry in value:
                payload_paths(entry)

    try:
        for path in extra_paths:
            check(path, existing=True)
        config = data / "config.json"
        if config.is_file():
            settings = json.loads(config.read_text("utf-8"))
            check(settings.get("output_dir"))
            check(settings.get("ffmpeg_path"), tool=True)
            live = settings.get("live", {})
            check(live.get("output_dir"))
            check(live.get("recorder_path"), tool=True)
        for name, tables in (
            ("tasks.sqlite3", ("tasks",)),
            ("live.sqlite3", ("subscriptions", "sessions")),
        ):
            database = data / name
            if not database.is_file():
                continue
            with sqlite3.connect(
                database.as_uri() + "?mode=ro", uri=True
            ) as connection:
                present = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                for table in tables:
                    if table not in present:
                        continue
                    column = "payload_json" if table == "tasks" else "payload"
                    for row in connection.execute(f"SELECT {column} FROM {table}"):
                        payload_paths(json.loads(row[0]))
                    if table == "tasks":
                        for row in connection.execute("SELECT output_path FROM tasks"):
                            check(row[0], existing=True)
        if any(path.is_dir() for path in target.rglob(".biliflow-parts")):
            raise InstallDataInApplicationError(
                "程序目录内仍有下载断点缓存，请先移到程序目录之外，或手动安装更新。"
            )
    except (OSError, ValueError, sqlite3.Error, AttributeError) as exc:
        if isinstance(exc, InstallDataInApplicationError):
            raise
        raise InstallDataInApplicationError(
            "无法核实用户数据位置，请手动安装以保留现有数据。"
        ) from exc
