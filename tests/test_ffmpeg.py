"""Tests for FFmpeg manager."""

from pathlib import Path
from unittest.mock import patch

from src.core.ffmpeg import FFmpegManager


class TestFFmpegFindExecutable:
    def test_not_found_no_mock(self):
        # On a clean system, should return None if not in PATH and no winget
        with patch("src.core.ffmpeg.shutil.which", return_value=None):
            with patch("pathlib.Path.is_dir", return_value=False):
                result = FFmpegManager.find_executable()
                assert result is None

    def test_found_in_path(self):
        with patch("src.core.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            result = FFmpegManager.find_executable()
            assert result == Path("/usr/bin/ffmpeg")

    def test_fallback_location(self):
        with patch("src.core.ffmpeg.shutil.which", return_value=None):
            with patch.object(Path, "is_file", return_value=True):
                # Should find first fallback location
                result = FFmpegManager.find_executable()
                assert result is not None


class TestFFmpegCheckAvailable:
    def test_not_found(self):
        with patch.object(FFmpegManager, "find_executable", return_value=None):
            available, msg = FFmpegManager.check_available()
            assert not available
            assert "not found" in msg.lower()

    def test_found_with_version(self):
        with patch.object(FFmpegManager, "find_executable", return_value=Path("/usr/bin/ffmpeg")):
            mock_result = type("MockResult", (), {
                "returncode": 0,
                "stdout": b"ffmpeg version 6.1.1\nsome other line\n",
                "stderr": b"",
            })()
            with patch("src.core.ffmpeg.subprocess.run", return_value=mock_result):
                available, msg = FFmpegManager.check_available()
                assert available
                assert "ffmpeg version 6.1.1" in msg


class TestFFmpegBuildCommand:
    def test_basic_merge_command(self):
        # build_merge_command now uses absolute (resolved) paths
        video = Path("C:/tmp/video.m4s")
        audio = Path("C:/tmp/audio.m4s")
        output = Path("C:/tmp/output.mp4")
        cmd = FFmpegManager.build_merge_command(video, audio, output)
        assert cmd[0] == "ffmpeg"
        assert cmd[1] == "-y"
        assert cmd[2] == "-i"
        assert "video.m4s" in cmd[3]
        assert cmd[4] == "-i"
        assert "audio.m4s" in cmd[5]
        assert cmd[6:9] == ["-c", "copy", "-movflags"]
        assert "output.mp4" in cmd[-1]

    def test_merge_with_extra_args(self):
        cmd = FFmpegManager.build_merge_command(
            Path("C:/tmp/video.m4s"),
            Path("C:/tmp/audio.m4s"),
            Path("C:/tmp/output.mp4"),
            extra_args=["-vf", "scale=1920:1080"],
        )
        assert "-vf" in cmd
        assert "scale=1920:1080" in cmd
