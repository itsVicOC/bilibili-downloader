"""FFmpeg detection and command builder."""

import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional

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
            )
            if result.returncode == 0:
                version_line = (result.stdout + result.stderr).decode(
                    "utf-8", errors="replace"
                ).split("\n")[0].strip()
                return True, version_line
            return False, f"FFmpeg returned error code {result.returncode}"
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
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

        # Use a temp file in the same directory for atomic rename
        safe_output = output_path.with_suffix(".tmp")
        cmd = cls.build_merge_command(video_path, audio_path, safe_output, executable=str(exe))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300,
            )
            output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            if result.returncode != 0:
                error_lines = []
                for line in output.split("\n"):
                    if any(k in line.lower() for k in ["error", "invalid", "failed", "unsupported"]):
                        error_lines.append(line.strip())
                if error_lines:
                    return False, "\n".join(error_lines[:5])
                return False, f"FFmpeg exit code {result.returncode}\n{output[-500:]}"

            # Atomic rename within same directory (avoids cross-drive copy+delete)
            if safe_output.exists():
                safe_output.replace(output_path)
                return True, output
            return False, f"FFmpeg succeeded but output file not found: {safe_output.name}"
        except subprocess.TimeoutExpired:
            return False, "FFmpeg merge timed out (5 min limit)"
        except FileNotFoundError:
            return False, "FFmpeg executable not found at path"
