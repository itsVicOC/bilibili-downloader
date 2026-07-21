"""FFmpeg detection and command builder."""

import logging
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


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

        # Keep the media suffix so FFmpeg can infer the output container.
        safe_output = output_path.with_name(
            f"{output_path.stem}.part{output_path.suffix}"
        )
        _remove_partial_output(safe_output)
        cmd = cls.build_merge_command(video_path, audio_path, safe_output, executable=str(exe))

        process = None
        try:
            # A file-backed stderr avoids deadlocking when FFmpeg produces more
            # output than an unread PIPE buffer can hold.
            with tempfile.TemporaryFile() as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=log_file,
                    **_subprocess_window_kwargs(),
                )
                deadline = time.monotonic() + 300
                cancelled = False
                timed_out = False
                while process.poll() is None:
                    if cancel_checker and cancel_checker():
                        cancelled = True
                        process.kill()
                        break

                    if time.monotonic() >= deadline:
                        timed_out = True
                        process.kill()
                        break

                    time.sleep(0.2)

                process.wait()
                log_file.seek(0)
                output = log_file.read().decode("utf-8", errors="replace")

            if cancelled:
                _remove_partial_output(safe_output)
                return False, f"FFmpeg merge cancelled\n{output[-500:]}"
            if timed_out:
                _remove_partial_output(safe_output)
                return False, f"FFmpeg merge timed out (5 min limit)\n{output[-500:]}"
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
