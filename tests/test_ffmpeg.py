"""Tests for FFmpeg manager."""

from pathlib import Path
from unittest.mock import patch

from bilibili_downloader.core.ffmpeg import FFmpegManager, _subprocess_window_kwargs


class TestFFmpegFindExecutable:
    def test_not_found_no_mock(self):
        # On a clean system, should return None if not in PATH and no winget
        with patch("bilibili_downloader.core.ffmpeg.shutil.which", return_value=None):
            with patch.object(Path, "is_dir", return_value=False), \
                    patch.object(Path, "is_file", return_value=False):
                result = FFmpegManager.find_executable()
                assert result is None

    def test_found_in_path(self):
        with patch("bilibili_downloader.core.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"):
            result = FFmpegManager.find_executable()
            assert result == Path("/usr/bin/ffmpeg")

    def test_fallback_location(self):
        with patch("bilibili_downloader.core.ffmpeg.shutil.which", return_value=None):
            with patch.object(Path, "is_file", return_value=True):
                # Should find first fallback location
                result = FFmpegManager.find_executable()
                assert result is not None


def test_windows_subprocesses_hide_console(monkeypatch):
    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "bilibili_downloader.core.ffmpeg.subprocess.CREATE_NO_WINDOW", 0x08000000,
        raising=False,
    )

    assert _subprocess_window_kwargs() == {"creationflags": 0x08000000}


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
            with patch("bilibili_downloader.core.ffmpeg.subprocess.run", return_value=mock_result):
                available, msg = FFmpegManager.check_available()
                assert available
                assert "ffmpeg version 6.1.1" in msg

    def test_permission_error_is_reported(self):
        with patch.object(
            FFmpegManager, "find_executable", return_value=Path("/not/executable")
        ), patch(
            "bilibili_downloader.core.ffmpeg.subprocess.run",
            side_effect=PermissionError("denied"),
        ):
            available, msg = FFmpegManager.check_available()

        assert not available
        assert "denied" in msg


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


class TestFFmpegMerge:
    def test_temp_output_keeps_media_suffix(self, monkeypatch, tmp_path):
        commands = []

        class FakeProcess:
            returncode = 0

            def __init__(self, cmd, **_kwargs):
                commands.append(cmd)
                Path(cmd[-1]).write_bytes(b"merged")

            def poll(self):
                return 0

            def wait(self):
                return 0

        monkeypatch.setattr(
            FFmpegManager, "find_executable", lambda _custom=None: Path("/fake/ffmpeg")
        )
        monkeypatch.setattr("bilibili_downloader.core.ffmpeg.subprocess.Popen", FakeProcess)

        output = tmp_path / "episode.mp4"
        success, _ = FFmpegManager.merge_streams(
            tmp_path / "video.m4s", tmp_path / "audio.m4s", output
        )

        assert success
        assert output.read_bytes() == b"merged"
        assert commands[0][-1].endswith("episode.part.mp4")

    def test_keyboard_interrupt_kills_ffmpeg(self, monkeypatch, tmp_path):
        state = {"killed": False, "waited": False}

        class FakeProcess:
            returncode = None

            def __init__(self, *_args, **_kwargs):
                pass

            def poll(self):
                return None

            def kill(self):
                state["killed"] = True

            def wait(self):
                state["waited"] = True

        monkeypatch.setattr(
            FFmpegManager, "find_executable", lambda _custom=None: Path("/fake/ffmpeg")
        )
        monkeypatch.setattr(
            "bilibili_downloader.core.ffmpeg.subprocess.Popen", FakeProcess
        )
        monkeypatch.setattr(
            "bilibili_downloader.core.ffmpeg.time.sleep",
            lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
        )

        try:
            FFmpegManager.merge_streams(
                tmp_path / "video.m4s",
                tmp_path / "audio.m4s",
                tmp_path / "output.mp4",
            )
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("KeyboardInterrupt should propagate")

        assert state == {"killed": True, "waited": True}
