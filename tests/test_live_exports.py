"""Live concat integrity, durable queue and path migration regressions."""

import json
import shutil
import subprocess
from pathlib import Path
from threading import Event

import pytest

from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.live_models import (
    LiveExport,
    LiveRoom,
    RecordingSegment,
    RecordingSession,
)
from bilibili_downloader.core.live_repository import LiveRepository
from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.gui.live_controller import LiveUiController
from bilibili_downloader.utils.config import ConfigManager


def recording(root, identity="one", export=None):
    root.mkdir(parents=True, exist_ok=True)
    source = root / "片段 ' one.flv"
    source.touch()
    return RecordingSession(
        id=identity,
        room=LiveRoom(room_id=1, author="主播"),
        directory=str(root),
        started_at="2026-10-20T01:00:00+00:00",
        status="completed",
        segments=[
            RecordingSegment(path=str(source), finalized_at="2026-10-20T02:00:00+00:00")
        ],
        mp4_export=export,
    )


class QuietService:
    stopped = True

    def __init__(self, *_args):
        pass

    def start(self):
        pass

    def snapshot(self):
        return []

    def messages(self):
        return []

    def request_shutdown(self):
        pass


@pytest.fixture
def controller(tmp_path, qtbot):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings())
    value = LiveUiController(config, service_factory=QuietService)
    yield value
    value.shutdown()
    qtbot.waitUntil(lambda: value.background_stopped)


def test_queue_deduplicates_and_persists_progress(
    controller, tmp_path, qtbot, monkeypatch
):
    started, release = Event(), Event()
    calls = []

    def merge(sources, output, _custom, cancel, progress, **kwargs):
        calls.append((sources, output, kwargs["overwrite"]))
        progress("整理片段 1/2")
        started.set()
        release.wait(3)
        output.write_bytes(b"mp4")
        return True, str(output)

    monkeypatch.setattr(FFmpegManager, "merge_live_segments", merge)
    first = recording(tmp_path / "first")
    controller.repository.save_session(first)
    controller.export_session(first.id, tmp_path / "first.mp4")
    qtbot.waitUntil(started.is_set)
    controller.export_session(first.id, tmp_path / "duplicate.mp4")
    second = recording(
        tmp_path / "second",
        "two",
        LiveExport(path=str(tmp_path / "second.mp4"), automatic=True),
    )
    controller.repository.save_session(second)
    controller.refresh()
    assert len(calls) == 1
    assert controller.repository.session(first.id).mp4_export.progress == "整理片段 1/2"
    release.set()
    qtbot.waitUntil(controller._export.done)
    controller.refresh()
    qtbot.waitUntil(controller._export.done)
    controller.refresh()
    controller.refresh()
    assert [call[2] for call in calls] == [True, False]
    assert not controller.exporting
    assert controller.repository.session("two").mp4_export.status == "completed"
    assert Path(first.segments[0].path).is_file()


def test_shutdown_requeues_and_restart_resumes(
    controller, tmp_path, qtbot, monkeypatch
):
    started = Event()

    def interrupted(_sources, _output, _custom, cancel, _progress, **_kwargs):
        started.set()
        while not cancel():
            Event().wait(0.01)
        return False, "cancelled"

    monkeypatch.setattr(FFmpegManager, "merge_live_segments", interrupted)
    session = recording(tmp_path / "recording")
    controller.repository.save_session(session)
    controller.export_session(session.id, tmp_path / "resumed.mp4")
    qtbot.waitUntil(started.is_set)
    controller.shutdown()
    qtbot.waitUntil(lambda: controller.background_stopped)
    assert controller.repository.session(session.id).mp4_export.status == "queued"

    def complete(_sources, output, *_args, **_kwargs):
        output.write_bytes(b"mp4")
        return True, str(output)

    monkeypatch.setattr(FFmpegManager, "merge_live_segments", complete)
    resumed = LiveUiController(controller.config, service_factory=QuietService)
    try:
        qtbot.waitUntil(resumed._export.done)
        resumed.refresh()
        assert resumed.repository.session(session.id).mp4_export.status == "completed"
    finally:
        resumed.shutdown()
        qtbot.waitUntil(lambda: resumed.background_stopped)


def test_old_history_not_backfilled_and_failed_jobs_not_retried(controller, tmp_path):
    old = recording(tmp_path / "old")
    failed = recording(
        tmp_path / "failed",
        "failed",
        LiveExport(path=str(tmp_path / "out.mp4"), status="failed", error="broken"),
    )
    controller.repository.save_session(old)
    controller.repository.save_session(failed)
    controller.refresh()
    assert controller._export is None
    assert controller.repository.session(old.id).mp4_export is None


def test_startup_pause_defers_recovered_export_until_background_start(
    tmp_path, qtbot, monkeypatch
):
    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings())
    repository = LiveRepository(config.data_dir / "live.sqlite3")
    session = recording(
        tmp_path / "recording",
        export=LiveExport(
            path=str(tmp_path / "recovered.mp4"),
            status="running",
        ),
    )
    repository.save_session(session)
    calls = []

    def merge(_sources, output, *_args, **_kwargs):
        calls.append(output)
        output.write_bytes(b"mp4")
        return True, str(output)

    monkeypatch.setattr(FFmpegManager, "merge_live_segments", merge)
    paused = LiveUiController(config, service_factory=QuietService, autostart=False)
    try:
        assert paused._export is None and not calls
        assert paused.repository.session(session.id).mp4_export.status == "queued"
        paused.start_background()
        paused.refresh()
        qtbot.waitUntil(paused._export.done)
        paused.refresh()
        assert len(calls) == 1
        assert paused.repository.session(session.id).mp4_export.status == "completed"
    finally:
        paused.shutdown()
        qtbot.waitUntil(lambda: paused.background_stopped)


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("media integration requires fixture FFmpeg and ffprobe")
    root = tmp_path_factory.mktemp("直播 合并 ' media")
    for name, size, audio, bframes in (
        ("first", "160x90", True, "0"),
        ("second", "160x90", True, "0"),
        ("changed", "320x180", True, "0"),
        ("silent", "160x90", False, "0"),
        ("bframes", "160x90", True, "2"),
    ):
        args = [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate=25",
        ]
        if audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
        args += [
            "-t",
            "1.17",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-bf",
            bframes,
        ]
        if audio:
            args += ["-c:a", "aac"]
        subprocess.run(
            [*args, str(root / f"{name}.flv")], check=True, capture_output=True
        )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(root / "second.flv"),
            "-c",
            "copy",
            str(root / "second.ts"),
        ],
        check=True,
        capture_output=True,
    )
    return root


def probe(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-ignore_editlist",
            "1",
            "-count_packets",
            "-show_entries",
            "format=duration:stream=codec_type,nb_read_packets",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def frames(path):
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        line.rsplit(",", 1)[-1].strip()
        for line in result.stdout.splitlines()
        if not line.startswith("#")
    ]


@pytest.mark.parametrize(
    "names",
    [
        ("first.flv", "second.flv"),
        ("first.flv", "second.ts"),
        ("silent.flv", "silent.flv"),
        ("first.flv",),
        ("bframes.flv", "bframes.flv"),
    ],
)
def test_concat_preserves_frames_packets_and_timeline(media, tmp_path, names):
    sources = [media / name for name in names]
    output = tmp_path / "完整 直播.mp4"
    progress = []
    ok, error = FFmpegManager.merge_live_segments(
        sources, output, progress_callback=progress.append
    )
    assert ok, error
    assert frames(output) == [frame for source in sources for frame in frames(source)]
    expected = {}
    for source in sources:
        for stream in probe(source)["streams"]:
            key = stream["codec_type"]
            expected[key] = expected.get(key, 0) + int(stream["nb_read_packets"])
    exported = probe(output)
    assert {
        s["codec_type"]: int(s["nb_read_packets"]) for s in exported["streams"]
    } == expected
    assert abs(float(exported["format"]["duration"]) - len(names) * 1.2) < 0.2
    assert progress[0].startswith("整理片段 1/")
    assert not list(tmp_path.glob(".live-merge-*"))


def test_incompatible_missing_cancelled_and_existing_output_are_safe(media, tmp_path):
    output = tmp_path / "existing.mp4"
    output.write_bytes(b"existing")
    for sources, cancel in (
        ([media / "first.flv", media / "changed.flv"], None),
        ([media / "missing.flv"], None),
        ([media / "first.flv", media / "silent.flv"], None),
        ([media / "first.flv"], lambda: True),
    ):
        ok, _ = FFmpegManager.merge_live_segments(
            sources, output, cancel_checker=cancel
        )
        assert not ok
        assert output.read_bytes() == b"existing"
        assert not list(tmp_path.glob(".live-merge-*"))
    ok, path = FFmpegManager.merge_live_segments(
        [media / "first.flv"], output, overwrite=False
    )
    assert ok, path
    assert Path(path).name == "existing (1).mp4"
    assert output.read_bytes() == b"existing"


def test_export_metadata_update_keeps_final_segments(tmp_path):
    repository = LiveRepository(tmp_path / "live.sqlite3")
    session = recording(tmp_path / "recording")
    repository.save_session(session)
    repository.update_export(session.id, LiveExport(path="result.mp4"))
    result = repository.session(session.id)
    assert result.segments == session.segments
    assert (
        json.loads((Path(session.directory) / "manifest.json").read_text())[
            "mp4_export"
        ]["path"]
        == "result.mp4"
    )


def test_cancel_after_first_segment_cleans_staging(media, tmp_path):
    cancel = Event()
    output = tmp_path / "cancelled.mp4"

    def progress(message):
        if "2/2" in message:
            cancel.set()

    ok, _ = FFmpegManager.merge_live_segments(
        [media / "first.flv", media / "second.flv"],
        output,
        cancel_checker=cancel.is_set,
        progress_callback=progress,
    )
    assert not ok and not output.exists()
    assert not list(tmp_path.glob(".live-merge-*"))


def test_automatic_collision_does_not_follow_destination_symlink(media, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    existing = outside / "existing.mp4"
    existing.write_bytes(b"existing")
    destination = tmp_path / "whole.mp4"
    try:
        destination.symlink_to(existing)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    ok, result = FFmpegManager.merge_live_segments(
        [media / "first.flv"], destination, overwrite=False
    )
    assert ok, result
    assert Path(result) == tmp_path / "whole (1).mp4"
    assert existing.read_bytes() == b"existing"


def test_exclusive_publish_on_filesystems_without_hardlinks(tmp_path, monkeypatch):
    import errno
    import platform

    from bilibili_downloader.core.ffmpeg import _publish_without_overwrite

    if platform.system() == "Windows":
        pytest.skip("Windows already uses exclusive rename")
    source, target = tmp_path / "staged.mp4", tmp_path / "final.mp4"
    source.write_bytes(b"complete")

    def unsupported(*_args):
        raise OSError(errno.EOPNOTSUPP, "no hardlinks")

    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.os.link", unsupported)
    _publish_without_overwrite(source, target)
    assert target.read_bytes() == b"complete"
    source.write_bytes(b"second")
    with pytest.raises(FileExistsError):
        _publish_without_overwrite(source, target)
    assert source.read_bytes() == b"second" and target.read_bytes() == b"complete"
