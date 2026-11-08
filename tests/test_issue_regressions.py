"""Issue #30/#31: saved paths for 110 parts and real media track guarantees."""

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.models import (
    DownloadItem,
    OutputMode,
    StreamInfo,
    TaskStatus,
    VideoInfo,
    VideoPage,
)
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize(
    "mode,template,extension",
    [
        (OutputMode.VIDEO, "{title}/{page_padded} - {part}", ".mp4"),
        (OutputMode.AUDIO, "{author}/{title}/{page_padded} - {part}", ".m4a"),
    ],
)
def test_issue_30_settings_to_110_actual_files(
    workspace, tmp_path, monkeypatch, mode, template, extension
):
    window = workspace
    output_root = tmp_path / "用户指定的保存位置"
    panel = window._settings_page
    panel._output_dir.setText(str(output_root))
    panel._multipart_path_template.setText(template)
    panel._output_mode_combo.setCurrentIndex(panel._output_mode_combo.findData(mode))
    panel._codec_combo.setCurrentIndex(panel._codec_combo.findData(7))
    monkeypatch.setattr(window._live_controller, "apply_live_settings", lambda *_: None)
    monkeypatch.setattr(window._live_page, "check_engine", lambda: None)
    assert window._save_settings()
    assert window._config.load().output_dir == str(output_root)
    info = VideoInfo(
        bvid="BVissue30",
        title="高级系统项目管理课程完整版" * 20,
        cid=1,
        author="课程作者",
        pages=[
            VideoPage(cid=n, page=n, part=f"第{n}课 - 实际分P名称")
            for n in range(1, 111)
        ],
    )
    submitted = []
    monkeypatch.setattr(
        window,
        "_start_download",
        lambda item, task_id: submitted.append((task_id, item)),
    )
    window._enqueue_batch_infos([info])
    assert len(submitted) == 110
    assert all(
        item.output_dir == str(output_root) and item.output_mode == mode
        for _, item in submitted
    )

    def transfer(_downloader, stream, destination, progress, **_kwargs):
        destination.write_bytes(b"video" if stream.base_url == "video" else b"audio")
        progress(1.0)

    def merge(video, audio, destination, **_kwargs):
        assert video.read_bytes() == b"video" and audio.read_bytes() == b"audio"
        destination.write_bytes(b"video+audio")
        return True, "ok"

    def remux(audio, destination, **_kwargs):
        destination.write_bytes(audio.read_bytes())
        return True, "ok"

    monkeypatch.setattr(StreamDownloader, "_download_stream", transfer)
    monkeypatch.setattr(FFmpegManager, "merge_streams", merge)
    monkeypatch.setattr(FFmpegManager, "remux_audio", remux)
    api = SimpleNamespace(
        get_play_url=lambda **_: {
            "video_streams": [StreamInfo(id=80, codecid=7, base_url="video")],
            "audio_streams": [StreamInfo(id=30280, base_url="audio")],
        }
    )
    changed_root = tmp_path / "稍后修改的保存位置"
    window._settings.output_dir = str(changed_root)
    for task_id, item in submitted:
        service = DownloadService(
            api, str(changed_root), library_repository=window._library
        )
        outcome = service.download(item, lambda *_: None)
        window._on_download_finished(task_id, outcome)
    files = sorted(output_root.rglob(f"*{extension}"))
    assert len(files) == 110
    assert {p.name for p in files} == {
        f"{n:03d} - 第{n}课 - 实际分P名称{extension}" for n in range(1, 111)
    }
    assert all(p.parent != output_root for p in files)
    assert all(" (" not in p.name for p in files)
    assert {p.read_bytes() for p in files} == {
        b"audio" if mode == OutputMode.AUDIO else b"video+audio"
    }
    assert not list(changed_root.rglob(f"*{extension}"))
    assert all(
        r.status == TaskStatus.COMPLETED for r in window._task_repository.list_tasks()
    )
    assert len(window._library.list_assets()) == 110
    # The exact "More > remove all" action from #31 works for all completed parts.
    window._task_page._remove_all_action.trigger()
    assert window._task_repository.list_tasks() == []
    assert len(list(output_root.rglob(f"*{extension}"))) == 110
    assert len(window._library.list_assets()) == 110


def test_video_request_rejects_missing_video_metadata(tmp_path):
    api = SimpleNamespace(
        get_play_url=lambda **_: {
            "video_streams": [],
            "audio_streams": [StreamInfo(id=30280, base_url="audio")],
        }
    )
    service = DownloadService(api, str(tmp_path))
    with pytest.raises(RuntimeError, match="No matching video stream"):
        service.download(
            DownloadItem(video_info=VideoInfo(bvid="demo", cid=1)), lambda *_: None
        )
    assert not list(tmp_path.rglob("*.mp4"))
    assert not list(tmp_path.rglob("*.m4a"))


@pytest.fixture(scope="module")
def real_media(tmp_path_factory):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Real FFmpeg/ffprobe are required for track-level verification")
    root = tmp_path_factory.mktemp("issue-real-media")
    video, audio = root / "video.m4s", root / "audio.m4a"
    commands = [
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:r=5",
            "-t",
            "0.2",
            "-c:v",
            "mpeg4",
            "-f",
            "mp4",
            str(video),
        ],
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000",
            "-t",
            "0.2",
            "-c:a",
            "aac",
            str(audio),
        ],
    ]
    for command in commands:
        subprocess.run(command, check=True, capture_output=True, timeout=20)
    return ffmpeg, ffprobe, video, audio


def track_types(ffprobe, path):
    data = json.loads(
        subprocess.check_output(
            [ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)],
            text=True,
            timeout=10,
        )
    )
    return {stream["codec_type"] for stream in data["streams"]}


def test_real_mux_keeps_both_video_and_audio(real_media, tmp_path):
    ffmpeg, ffprobe, video, audio = real_media
    output = tmp_path / "video.mp4"
    success, message = FFmpegManager.merge_streams(
        video, audio, output, custom_path=ffmpeg
    )
    assert success, message
    assert track_types(ffprobe, output) == {"video", "audio"}


def test_real_mux_does_not_accept_audio_as_video(real_media, tmp_path):
    ffmpeg, _ffprobe, _video, audio = real_media
    wrong_video = tmp_path / "wrong-video.m4s"
    shutil.copyfile(audio, wrong_video)
    output = tmp_path / "must-not-succeed.mp4"
    success, _message = FFmpegManager.merge_streams(
        wrong_video, audio, output, custom_path=ffmpeg
    )
    assert not success
    assert not output.exists()


def test_real_mux_requires_audio_too(real_media, tmp_path):
    ffmpeg, _ffprobe, video, _audio = real_media
    output = tmp_path / "must-not-be-silent.mp4"
    success, _message = FFmpegManager.merge_streams(
        video, video, output, custom_path=ffmpeg
    )
    assert not success
    assert not output.exists()


def test_explicit_audio_output_still_works(real_media, tmp_path):
    ffmpeg, ffprobe, _video, audio = real_media
    output = tmp_path / "audio.m4a"
    success, message = FFmpegManager.remux_audio(audio, output, custom_path=ffmpeg)
    assert success, message
    assert track_types(ffprobe, output) == {"audio"}


def test_video_workflow_does_not_register_audio_only_result(
    real_media, tmp_path, monkeypatch
):
    from bilibili_downloader.core.library import LibraryRepository

    ffmpeg, _ffprobe, _video, audio = real_media
    api = SimpleNamespace(
        get_play_url=lambda **_: {
            "video_streams": [
                StreamInfo(id=80, codecid=7, base_url="advertised-video")
            ],
            "audio_streams": [StreamInfo(id=30280, base_url="audio")],
        }
    )

    def transfer(_downloader, _stream, destination, progress, **_kwargs):
        shutil.copyfile(audio, destination)
        progress(1.0)

    monkeypatch.setattr(StreamDownloader, "_download_stream", transfer)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    saved = []
    service = DownloadService(
        api,
        str(tmp_path),
        ffmpeg_path=ffmpeg,
        library_repository=library,
        outcome_callback=saved.append,
    )
    with pytest.raises(RuntimeError, match="FFmpeg processing failed"):
        service.download(
            DownloadItem(
                video_info=VideoInfo(bvid="demo", cid=1, title="Video requested"),
                selected_video_codec=7,
            ),
            lambda *_: None,
        )
    assert saved == []
    assert library.list_assets() == []
    assert not list(tmp_path.rglob("*.mp4"))
