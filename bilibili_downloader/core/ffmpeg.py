"""FFmpeg detection and command builder."""

import ctypes
import errno
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _bundled_executable_candidates() -> list[Path]:
    """Return possible FFmpeg locations in a frozen full distribution."""
    if not getattr(sys, "frozen", False):
        return []

    executable_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    executable_dir = Path(sys.executable).resolve().parent
    candidates = [executable_dir / executable_name]

    if platform.system() == "Darwin":
        candidates.insert(0, executable_dir.parent / "Resources" / executable_name)

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / executable_name)

    return candidates


class FFmpegManager:
    """Locate FFmpeg and build commands for stream merging."""

    @staticmethod
    def find_executable(custom_path: Optional[str] = None) -> Optional[Path]:
        """Search for ffmpeg binary in custom path, PATH, and common locations."""
        # Check custom path first
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return p
            logger.warning("Custom FFmpeg path not found: %s", custom_path)

        for bundled_path in _bundled_executable_candidates():
            if bundled_path.is_file():
                return bundled_path

        # Check PATH first
        found = shutil.which("ffmpeg")
        if found:
            return Path(found)

        # Platform-specific search paths
        search_paths = [
            Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
        ]
        if platform.system() == "Windows":
            search_paths.extend([
                Path("C:/ffmpeg/bin/ffmpeg.exe"),
                Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
            ])

            # Winget FFmpeg location - search recursively for bin/ffmpeg.exe
            winget_dir = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
            if winget_dir.is_dir():
                for d in winget_dir.iterdir():
                    if "FFmpeg" in d.name and d.is_dir():
                        bin_dir = d / "bin"
                        if not bin_dir.is_dir():
                            for sub in d.iterdir():
                                if sub.is_dir() and (sub / "bin").is_dir():
                                    bin_dir = sub / "bin"
                                    break
                        exe = bin_dir / "ffmpeg.exe"
                        if exe.is_file():
                            return exe

        elif platform.system() == "Darwin":
            search_paths.extend([
                Path("/usr/local/bin/ffmpeg"),
                Path("/opt/homebrew/bin/ffmpeg"),
            ])
        else:
            search_paths.extend([
                Path("/usr/bin/ffmpeg"),
                Path("/usr/local/bin/ffmpeg"),
            ])

        for p in search_paths:
            if p.is_file():
                return p
        return None

    @classmethod
    def check_available(cls, custom_path: Optional[str] = None) -> tuple[bool, str]:
        """Check if FFmpeg is available and return version info.

        Args:
            custom_path: Optional user-configured path to check first.

        Returns:
            (available, version_string_or_error_message)
        """
        exe = cls.find_executable(custom_path)
        if exe is None:
            return False, "FFmpeg not found. Please install FFmpeg or set the path in settings."

        try:
            result = subprocess.run(
                [str(exe), "-version"],
                capture_output=True,
                timeout=5,
                **_subprocess_window_kwargs(),
            )
            if result.returncode == 0:
                version_line = (result.stdout + result.stderr).decode(
                    "utf-8", errors="replace"
                ).split("\n")[0].strip()
                return True, version_line
            return False, f"FFmpeg returned error code {result.returncode}"
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"FFmpeg check failed: {e}"

    @staticmethod
    def build_live_remux_command(source: Path, output: Path, executable="ffmpeg") -> list[str]:
        return [executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-protocol_whitelist", "file", "-i", str(source.resolve()),
                "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
                "-movflags", "+faststart", str(output.resolve())]

    @classmethod
    def remux_live(cls, source: Path, output: Path, custom_path=None, cancel_checker=None):
        exe = cls.find_executable(custom_path)
        if exe is None:
            return False, "未找到 FFmpeg，请安装 full 包或选择 FFmpeg 路径"
        if source.resolve() == output.resolve():
            return False, "导出路径不能覆盖录制源文件"
        if output.suffix.lower() != ".mp4":
            return False, "导出文件必须使用 .mp4 扩展名"
        demuxer = {".flv": "flv", ".ts": "mpegts", ".m4s": "mov", ".mp4": "mov"}.get(source.suffix.lower())
        if demuxer is None:
            return False, "不支持此录制文件格式"
        try:
            result = subprocess.run([str(exe), "-hide_banner", "-demuxers"],
                capture_output=True, timeout=5, **_subprocess_window_kwargs())
            formats = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            if result.returncode or not any(demuxer in line.split()[1].split(',')
                    for line in formats.splitlines() if len(line.split()) >= 2 and line.split()[0] == "D"):
                return False, f"当前 FFmpeg 缺少 {demuxer} 输入支持，请更新 full 包或选择完整 FFmpeg"
        except (OSError, subprocess.TimeoutExpired):
            return False, "FFmpeg 能力检查失败"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.live-{uuid.uuid4().hex}.part.mp4")
        return cls._execute_command(cls.build_live_remux_command(source, output, str(exe)),
                                    output, cancel_checker, temporary_path=temporary)

    @staticmethod
    def _live_stream_signature(source: Path, executable: str) -> tuple:
        """Inspect with the same binary used for export (no ffprobe dependency).

        FFmpeg's input-only invocation exits nonzero because there is no output.
        Require complete stream headers instead of treating that exit as failure.
        Inspect normalized MP4s so container tags and time bases are comparable.
        """
        result = subprocess.run(
            [executable, "-nostdin", "-hide_banner", "-protocol_whitelist", "file",
             "-i", str(source.resolve())], capture_output=True, timeout=30,
            **_subprocess_window_kwargs(),
        )
        info = result.stderr.decode("utf-8", errors="replace")
        video = re.search(r"Video: ([^,\n]+),\s*([^,\n]+),\s*(\d+x\d+)", info)
        audio = re.search(r"Audio: ([^,\n]+),\s*(\d+) Hz,\s*([^,\n]+)", info)
        if not video or not video[1].startswith("h264 "):
            raise ValueError("无法确认 H.264 视频参数，暂不能无损合并")
        if "Audio:" in info and (not audio or not audio[1].startswith("aac ")):
            raise ValueError("无法确认 AAC 音频参数，暂不能无损合并")
        return (*video.groups(), audio.groups() if audio else None)

    @classmethod
    def merge_live_segments(
        cls, sources, output: Path, custom_path=None, cancel_checker=None,
        progress_callback=None, *, minimum_free_bytes=0, overwrite=True,
    ) -> tuple[bool, str]:
        """Normalize closed segments then losslessly concatenate in manifest order.

        All staging stays beside the destination, making publication atomic and
        cleanup independent from the original recording directory.
        """
        sources = [Path(source).expanduser().resolve() for source in sources]
        requested = Path(output).expanduser()
        # Resolve the directory, not an existing destination symlink: automatic
        # collision handling must keep the numbered result in this session.
        output = requested.parent.resolve() / requested.name
        exe = cls.find_executable(custom_path)
        if exe is None:
            return False, "未找到 FFmpeg，请安装 full 包或选择 FFmpeg 路径"
        if not sources:
            return False, "本场没有已封口片段，无法导出"
        if output.suffix.lower() != ".mp4":
            return False, "导出文件必须使用 .mp4 扩展名"
        for source in sources:
            if not source.is_file():
                return False, f"片段文件已不存在：{source}"
            if overwrite and (source == output.resolve() or (output.exists() and source.samefile(output))):
                return False, "导出路径不能覆盖录制源文件"
            if source.suffix.lower() not in {".flv", ".ts", ".m4s", ".mp4"}:
                return False, f"不支持此录制文件格式：{source.name}"

        def report(message):
            if progress_callback:
                progress_callback(message)

        try:
            if cancel_checker and cancel_checker():
                return False, "导出已取消"
            formats = subprocess.run(
                [str(exe), "-hide_banner", "-demuxers"], capture_output=True,
                timeout=5, **_subprocess_window_kwargs(),
            )
            demuxers = (formats.stdout + formats.stderr).decode("utf-8", errors="replace")
            filters = subprocess.run(
                [str(exe), "-hide_banner", "-bsfs"], capture_output=True,
                timeout=5, **_subprocess_window_kwargs(),
            )
            if (formats.returncode or filters.returncode
                    or not re.search(r"\bD\s+concat\b", demuxers)
                    or b"h264_mp4toannexb" not in filters.stdout + filters.stderr):
                return False, "当前 FFmpeg 缺少直播拼接支持，请更新 full 包或选择完整 FFmpeg"
            output.parent.mkdir(parents=True, exist_ok=True)
            required = int(sum(p.stat().st_size for p in sources) * 2.1) + minimum_free_bytes
            if shutil.disk_usage(output.parent).free < required:
                return False, "导出目录空间不足，需要容纳临时片段、合并文件及保留空间"
            with tempfile.TemporaryDirectory(prefix=".live-merge-", dir=output.parent) as directory:
                workspace = Path(directory)
                signature = None
                names = []
                for index, source in enumerate(sources, 1):
                    if cancel_checker and cancel_checker():
                        return False, "导出已取消"
                    report(f"整理片段 {index}/{len(sources)}")
                    normalized = workspace / f"{index:06d}.mp4"
                    command = cls.build_live_remux_command(source, normalized, str(exe))
                    # MP4 records packet-derived duration, unlike FLV's rounded
                    # metadata. Do not copy the broadcast's absolute timestamps.
                    command[-1:-1] = ["-video_track_timescale", "90000", "-xerror"]
                    ok, error = cls._execute_command(
                        command, normalized, cancel_checker, timeout_seconds=None,
                    )
                    if not ok:
                        return False, f"片段 {index}（{source.name}）处理失败：{error}"
                    current = cls._live_stream_signature(normalized, str(exe))
                    if signature is not None and current != signature:
                        return False, f"片段 {index}（{source.name}）与首段的编码、分辨率或音频参数不兼容，无法无损合并"
                    signature = current
                    names.append(f"file {normalized.name}\n")
                manifest = workspace / "segments.ffconcat"
                manifest.write_text("ffconcat version 1.0\n" + "".join(names), encoding="ascii")
                report(f"合并 {len(sources)} 个片段 · 整理 MP4")
                assembled = workspace / "merged.mp4"
                command = [str(exe), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                           "-protocol_whitelist", "file", "-f", "concat", "-safe", "1",
                           "-i", str(manifest), "-map", "0:v:0", "-map", "0:a:0?",
                           "-c", "copy", "-movflags", "+faststart", "-xerror", str(assembled)]
                ok, error = cls._execute_command(command, assembled, cancel_checker, timeout_seconds=None)
                if not ok:
                    return False, f"合并失败：{error}"
                if cancel_checker and cancel_checker():
                    return False, "导出已取消"
                if overwrite:
                    assembled.replace(output)
                else:
                    # Atomic no-clobber publication, including files created
                    # while this job was processing. Never reserve empty files.
                    candidate = output
                    index = 1
                    while True:
                        try:
                            _publish_without_overwrite(assembled, candidate)
                            output = candidate
                            break
                        except FileExistsError:
                            candidate = output.with_name(f"{output.stem} ({index}).mp4")
                            index += 1
                return True, str(output)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return False, f"直播合并导出失败：{exc}"

    @staticmethod
    def build_merge_command(
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        executable: str = "ffmpeg",
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Build ffmpeg command to merge video and audio streams.

        Uses absolute paths for all files to avoid cross-directory issues.
        Uses -c copy for lossless muxing (no re-encoding).

        Args:
            executable: Path to ffmpeg executable (default: "ffmpeg" from PATH).
        """
        cmd = [
            executable,
            "-y",  # Overwrite output without asking
            "-i", str(video_path.resolve()),
            "-i", str(audio_path.resolve()),
            "-c", "copy",
            "-movflags", "+faststart",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(str(output_path.resolve()))
        return cmd

    @staticmethod
    def build_audio_command(
        audio_path: Path,
        output_path: Path,
        executable: str = "ffmpeg",
    ) -> list[str]:
        """Build a lossless audio-only remux command."""
        return [
            executable,
            "-y",
            "-i", str(audio_path.resolve()),
            "-vn",
            "-c:a", "copy",
            str(output_path.resolve()),
        ]

    @classmethod
    def merge_streams(
        cls,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        custom_path: Optional[str] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str]:
        """Execute FFmpeg to merge video and audio streams.

        Uses absolute paths for reliable cross-platform operation.

        Args:
            custom_path: Optional user-configured FFmpeg path.

        Returns:
            (success, stdout+stderr output)
        """
        exe = cls.find_executable(custom_path)
        if exe is None:
            return False, "FFmpeg not found"

        cmd = cls.build_merge_command(video_path, audio_path, output_path, executable=str(exe))
        return cls._execute_command(cmd, output_path, cancel_checker)

    @classmethod
    def remux_audio(
        cls,
        audio_path: Path,
        output_path: Path,
        custom_path: Optional[str] = None,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[bool, str]:
        """Losslessly remux one DASH audio stream into a standalone file."""
        exe = cls.find_executable(custom_path)
        if exe is None:
            return False, "FFmpeg not found"
        cmd = cls.build_audio_command(audio_path, output_path, executable=str(exe))
        return cls._execute_command(cmd, output_path, cancel_checker)

    @staticmethod
    def _execute_command(
        command: list[str],
        output_path: Path,
        cancel_checker: Optional[Callable[[], bool]],
        *,
        temporary_path: Optional[Path] = None,
        timeout_seconds: float | None = 300,
    ) -> tuple[bool, str]:
        # Keep the media suffix so FFmpeg can infer the output container.
        safe_output = temporary_path or output_path.with_name(
            f"{output_path.stem}.part{output_path.suffix}"
        )
        command = [*command[:-1], str(safe_output.resolve())]
        _remove_partial_output(safe_output)

        process = None
        try:
            if cancel_checker and cancel_checker():
                return False, "FFmpeg processing cancelled"
            # A file-backed stderr avoids deadlocking when FFmpeg produces more
            # output than an unread PIPE buffer can hold.
            with tempfile.TemporaryFile() as log_file:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=log_file,
                    **_subprocess_window_kwargs(),
                )
                deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
                cancelled = False
                timed_out = False
                while process.poll() is None:
                    if cancel_checker and cancel_checker():
                        cancelled = True
                        process.kill()
                        break

                    if deadline is not None and time.monotonic() >= deadline:
                        timed_out = True
                        process.kill()
                        break

                    time.sleep(0.2)

                process.wait()
                log_file.seek(0)
                output = log_file.read().decode("utf-8", errors="replace")

            if cancelled or (cancel_checker and cancel_checker()):
                _remove_partial_output(safe_output)
                return False, f"FFmpeg processing cancelled\n{output[-500:]}"
            if timed_out:
                _remove_partial_output(safe_output)
                return False, f"FFmpeg processing timed out (5 min limit)\n{output[-500:]}"
            if process.returncode != 0:
                _remove_partial_output(safe_output)
                error_lines = []
                for line in output.split("\n"):
                    if any(k in line.lower() for k in ["error", "invalid", "failed", "unsupported"]):
                        error_lines.append(line.strip())
                if error_lines:
                    return False, "\n".join(error_lines[:5])
                return False, f"FFmpeg exit code {process.returncode}\n{output[-500:]}"

            # Atomic rename within same directory (avoids cross-drive copy+delete)
            if safe_output.exists():
                safe_output.replace(output_path)
                return True, output
            return False, f"FFmpeg succeeded but output file not found: {safe_output.name}"
        except OSError as e:
            _remove_partial_output(safe_output)
            return False, f"FFmpeg could not be started: {e}"
        except KeyboardInterrupt:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            _remove_partial_output(safe_output)
            raise


def _publish_without_overwrite(source: Path, destination: Path) -> None:
    """Atomically publish on both native disks and external FAT/exFAT disks."""
    if platform.system() == "Windows":
        # Windows rename, unlike POSIX rename, refuses an existing destination.
        os.rename(source, destination)
        return
    try:
        os.link(source, destination)
        return
    except OSError as exc:
        if exc.errno not in {errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS}:
            raise
    # FAT/exFAT do not support hard links. Use each platform's exclusive atomic
    # rename rather than creating an empty reservation or exposing partial MP4s.
    libc = ctypes.CDLL(None, use_errno=True)
    if platform.system() == "Darwin" and hasattr(libc, "renamex_np"):
        function = libc.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        arguments = (os.fsencode(source), os.fsencode(destination), 4)  # RENAME_EXCL
    elif hasattr(libc, "renameat2"):
        function = libc.renameat2
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        arguments = (-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
    else:
        raise OSError(errno.EOPNOTSUPP, "当前磁盘不支持安全发布，请手动另存到其他目录")
    function.restype = ctypes.c_int
    if function(*arguments):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def _remove_partial_output(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("Failed to remove partial FFmpeg output: %s", path)


def _subprocess_window_kwargs() -> dict:
    """Prevent console flashes for FFmpeg launched by the Windows GUI build."""
    if platform.system() == "Windows":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}
