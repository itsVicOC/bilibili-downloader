"""Media reuse and recovery must preserve bytes and respect actual specifications."""

import hashlib
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.errors import ErrorCategory, classify_error
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.library import LibraryRepository, absolute_path
from bilibili_downloader.core.media_policy import SpecificationMismatchError
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    StreamInfo,
    SubtitleInfo,
    TaskStatus,
    VideoInfo,
    VideoPage,
    VideoQuality,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.gui.dialogs.page_selection import (
    PageSelectionDialog,
    parse_page_range,
)
from bilibili_downloader.gui.threads.batch_worker import ImportReport
from tests.test_workspaces import workspace as workspace


def stored(tmp_path):
    media = tmp_path / "lesson.mp4"
    media.write_bytes(b"immutable media bytes")
    item = DownloadItem(video_info=VideoInfo(bvid="BVdemo", cid=123, title="课程", author="作者"), output_dir=str(tmp_path))
    outcome = DownloadOutcome(video_path=str(media), actual_quality=80, actual_video_codec=12, actual_audio_quality=30280)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    library.record_download(item, outcome)
    return library, item, outcome


def no_transfer(monkeypatch, service):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("media transfer must not run")
    monkeypatch.setattr(service._downloader, "download", unexpected)


def test_reuse_survives_task_cleanup_restart_and_hidden_inventory(tmp_path, monkeypatch):
    library, item, original = stored(tmp_path)
    tasks = TaskRepository(tmp_path / "tasks.sqlite3")
    identity = tasks.add(item)
    tasks.update(identity, status=TaskStatus.COMPLETED, outcome=original, output_path=original.video_path)
    tasks.delete(identity)
    library.hide([library.list_assets()[0]["id"]])
    restarted = LibraryRepository(library.database_path)
    service = DownloadService(object(), str(tmp_path), library_repository=restarted)
    no_transfer(monkeypatch, service)
    result = service.download(item, lambda *_: None)
    assert result.reused_media and absolute_path(result.video_path) == absolute_path(original.video_path)
    assert Path(original.video_path).read_bytes() == b"immutable media bytes"


def test_new_companion_options_only_download_missing_attachments(tmp_path, monkeypatch):
    library, item, original = stored(tmp_path)
    before = hashlib.sha256(Path(original.video_path).read_bytes()).digest()
    service = DownloadService(object(), str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    requested = item.model_copy(update={"download_metadata": True})
    first = service.download(requested, lambda *_: None)
    assert first.metadata_path and first.reused_media
    assert hashlib.sha256(Path(original.video_path).read_bytes()).digest() == before
    monkeypatch.setattr("bilibili_downloader.core.download_service.write_metadata", lambda *_: pytest.fail("already saved metadata"))
    assert service.download(requested, lambda *_: None).metadata_path == first.metadata_path


def test_attachment_failure_is_independently_recoverable(tmp_path, monkeypatch):
    library, item, original = stored(tmp_path)
    service = DownloadService(object(), str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    requested = item.model_copy(update={"download_danmaku": True})
    def fail(*_):
        raise ConnectionError("offline")
    monkeypatch.setattr("bilibili_downloader.core.download_service.DanmakuDownloader.download_and_convert", fail)
    failed = service.download(requested, lambda *_: None)
    assert failed.missing_artifacts == ["danmaku"]
    assert failed.result_label == "媒体已保存 · 附件待补全"
    monkeypatch.setattr("bilibili_downloader.core.download_service.DanmakuDownloader.download_and_convert", lambda _, target: target.write_text("ASS"))
    result = service.download(requested, lambda *_: None)
    assert not result.missing_artifacts and not result.warnings
    assert absolute_path(result.video_path) == absolute_path(original.video_path)


def test_requesting_all_subtitles_extends_a_previously_single_language_download(tmp_path, monkeypatch):
    library, item, original = stored(tmp_path)
    tracks = [SubtitleInfo(lan="zh-Hans", url="https://example.test/zh"), SubtitleInfo(lan="en", url="https://example.test/en")]
    api = SimpleNamespace(get_subtitle_tracks=lambda *_: tracks)
    service = DownloadService(api, str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    writes = []
    def convert(url, path):
        writes.append(url)
        path.write_text(url)
    monkeypatch.setattr("bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert", convert)
    first = service.download(item.model_copy(update={"download_subtitle": True}), lambda *_: None)
    assert not first.subtitle_discovery_complete
    result = service.download(item.model_copy(update={"download_all_subtitles": True}), lambda *_: None)
    assert result.subtitle_discovery_complete and len(result.subtitle_paths) == 2
    assert writes == [tracks[0].url, tracks[1].url]
    assert Path(original.video_path).read_bytes() == b"immutable media bytes"
    requested = item.model_copy(update={"download_all_subtitles": True})
    reused = service.download(requested, lambda *_: None)
    assert reused.subtitle_discovery_complete and set(reused.subtitle_languages) == {"zh-Hans", "en"}
    assert len(writes) == 2
    Path(reused.subtitle_languages["en"]).unlink()
    assert library.match_media(requested).missing == ("subtitle",)
    repaired = service.download(requested, lambda *_: None)
    assert repaired.subtitle_discovery_complete and writes[-1] == tracks[1].url
    assert len(writes) == 3


def test_chinese_english_ai_subtitles_extend_and_reuse_existing_media(tmp_path, monkeypatch):
    library, item, original = stored(tmp_path)
    tracks = [SubtitleInfo(lan=lan, url=f"https://example.test/{lan}")
              for lan in ("ai-zh", "ai-en", "ai-ja")]
    service = DownloadService(SimpleNamespace(get_subtitle_tracks=lambda *_: tracks),
                              str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    writes = []

    def convert(url, path):
        writes.append(path.name)
        path.write_text(url)

    monkeypatch.setattr("bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert", convert)
    single = item.model_copy(update={"download_subtitle": True, "selected_subtitle_lan": "ai-zh"})
    service.download(single, lambda *_: None)
    pair = item.model_copy(update={"download_subtitle": True, "selected_subtitle_lan": "zh-en"})
    assert library.match_media(pair).missing == ("subtitle",)
    result = service.download(pair, lambda *_: None)
    assert set(result.subtitle_languages) == {"ai-zh", "ai-en"}
    assert len(writes) == 2
    assert library.match_media(pair).state == "saved"
    service.download(pair, lambda *_: None)
    assert len(writes) == 2
    Path(result.subtitle_languages["ai-en"]).unlink()
    assert library.match_media(pair).missing == ("subtitle",)
    service.download(pair, lambda *_: None)
    assert len(writes) == 3
    assert library.match_media(pair.model_copy(update={"download_all_subtitles": True})).missing == ("subtitle",)
    assert Path(original.video_path).read_bytes() == b"immutable media bytes"


def test_gui_subtitle_download_requests_chinese_and_english(workspace):
    workspace._subtitle_check.setChecked(True)
    workspace._all_subtitles_check.setChecked(False)
    item = workspace._make_download_item(VideoInfo(bvid="BVdemo", cid=123))
    assert item.download_subtitle and item.selected_subtitle_lan == "zh-en"
    assert not item.download_all_subtitles


@pytest.mark.parametrize("languages", [
    ["ai-zh"], ["ai-en"], ["zh-Hans", "ai-zh"], ["en-US"], ["ai-ja"], [],
])
def test_available_subtitle_selection_is_complete_and_reused(tmp_path, monkeypatch, languages):
    library, item, _ = stored(tmp_path)
    tracks = [SubtitleInfo(lan=lan, url=f"https://example.test/{lan}") for lan in languages]
    calls = []

    def discover(*_):
        calls.append(True)
        return tracks

    service = DownloadService(SimpleNamespace(get_subtitle_tracks=discover),
                              str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert",
        lambda url, path: path.write_text(url),
    )
    requested = item.model_copy(update={"download_subtitle": True, "selected_subtitle_lan": "zh-en"})
    outcome = service.download(requested, lambda *_: None)
    expected = {lan for lan in languages if lan.removeprefix("ai-").split("-")[0] in {"zh", "en"}}
    assert set(outcome.subtitle_languages) == expected
    assert outcome.missing_artifacts == []
    if expected:
        assert outcome.warnings == []
    # Discovery evidence survives serialization and a repository restart.
    restarted = LibraryRepository(library.database_path)
    match = restarted.match_media(requested)
    assert match.state == "saved"
    assert match.outcome.subtitle_discovery_languages == languages
    service.download(requested, lambda *_: None)
    assert len(calls) == 1


def test_available_subtitle_failure_and_deleted_file_remain_recoverable(tmp_path, monkeypatch):
    library, item, _ = stored(tmp_path)
    tracks = [SubtitleInfo(lan=lan, url=f"https://example.test/{lan}") for lan in ("ai-zh", "ai-en")]
    service = DownloadService(SimpleNamespace(get_subtitle_tracks=lambda *_: tracks),
                              str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    writes = []
    fail_english = True

    def convert(url, path):
        if url.endswith("ai-en") and fail_english:
            raise ConnectionError("offline")
        writes.append(path.name)
        path.write_text(url)

    monkeypatch.setattr("bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert", convert)
    requested = item.model_copy(update={"download_subtitle": True, "selected_subtitle_lan": "zh-en"})
    failed = service.download(requested, lambda *_: None)
    assert failed.missing_artifacts == ["subtitle"]
    assert library.match_media(requested).missing == ("subtitle",)
    fail_english = False
    recovered = service.download(requested, lambda *_: None)
    assert recovered.missing_artifacts == []
    assert library.match_media(requested).state == "saved"
    assert len(writes) == 2
    Path(recovered.subtitle_languages["ai-en"]).unlink()
    assert library.match_media(requested).missing == ("subtitle",)
    service.download(requested, lambda *_: None)
    assert len(writes) == 3
    assert library.match_media(requested).state == "saved"


def test_failed_subtitle_discovery_cannot_complete_a_legacy_single_language_receipt(tmp_path, monkeypatch):
    library, item, original = stored(tmp_path)
    subtitle = tmp_path / "lesson.srt"
    subtitle.write_text("legacy Chinese subtitles")
    original.subtitle_languages = {"ai-zh": str(subtitle)}
    original.subtitle_paths = [str(subtitle)]
    library.record_download(item, original)
    requested = item.model_copy(update={"download_subtitle": True, "selected_subtitle_lan": "zh-en"})
    assert library.match_media(requested).missing == ("subtitle",)

    def discover(*_):
        raise ConnectionError("offline")

    service = DownloadService(SimpleNamespace(get_subtitle_tracks=discover),
                              str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    result = service.download(requested, lambda *_: None)
    assert result.subtitle_discovery_languages is None
    assert result.missing_artifacts == ["subtitle"]
    assert library.match_media(requested).missing == ("subtitle",)


def test_reusing_companions_preserves_their_conversion_warnings(tmp_path, monkeypatch):
    from bilibili_downloader.core.timed_text import ConversionReport
    library, item, _ = stored(tmp_path)
    service = DownloadService(object(), str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    def convert(_cid, target):
        target.write_text("ASS")
        return ConversionReport(exported=1, unsupported=2)
    monkeypatch.setattr("bilibili_downloader.core.download_service.DanmakuDownloader.download_and_convert", convert)
    item.download_danmaku = True
    first = service.download(item, lambda *_: None)
    second = service.download(item, lambda *_: None)
    assert first.warnings == second.warnings and "2" in second.warnings[0]


@pytest.mark.parametrize("change,state", [({"selected_quality": VideoQuality.Q4K}, "specification_mismatch"), ({"selected_video_codec": 7}, "specification_mismatch"), ({"selected_audio_quality": 30251}, "specification_mismatch")])
def test_actual_media_must_satisfy_requested_specifications(tmp_path, change, state):
    library, item, _ = stored(tmp_path)
    assert library.match_media(item.model_copy(update=change)).state == state


def test_missing_or_unverified_specifications_cannot_be_reused(tmp_path):
    library, item, outcome = stored(tmp_path)
    outcome.actual_audio_quality = None
    library.record_download(item, outcome)
    assert library.match_media(item).state == "specification_mismatch"
    Path(outcome.video_path).unlink()
    assert library.match_media(item).state == "unavailable"


def test_changed_media_cannot_be_reused_after_a_quick_existence_check(tmp_path):
    library, item, outcome = stored(tmp_path)
    Path(outcome.video_path).write_bytes(b"truncated")
    library.check_files([library.list_assets()[0]["id"]])
    assert library.match_media(item).state == "unavailable"


def test_explicit_supplement_never_falls_back_to_a_media_transfer(tmp_path, monkeypatch):
    library, item, outcome = stored(tmp_path)
    Path(outcome.video_path).unlink()
    service = DownloadService(object(), str(tmp_path), library_repository=library)
    no_transfer(monkeypatch, service)
    with pytest.raises(ValueError, match="未重新下载"):
        service.download(item.model_copy(update={"reuse_media_path": outcome.video_path}), lambda *_: None)


def test_force_new_bypasses_inventory(tmp_path, monkeypatch):
    library, item, outcome = stored(tmp_path)
    service = DownloadService(object(), str(tmp_path), library_repository=library)
    transfers = []
    def transfer(*_):
        transfers.append(True)
        service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
        service._downloader.last_audio_stream = StreamInfo(id=30280)
        path = tmp_path / "lesson (2).mp4"
        path.write_bytes(b"second copy")
        return str(path)
    monkeypatch.setattr(service._downloader, "download", transfer)
    result = service.download(item.model_copy(update={"force_new": True}), lambda *_: None)
    assert transfers == [True] and result.video_path != outcome.video_path
    assert Path(outcome.video_path).read_bytes() == b"immutable media bytes"


def test_concurrent_services_only_transfer_media_once(tmp_path, monkeypatch):
    library = LibraryRepository(tmp_path / "library.sqlite3")
    item = DownloadItem(video_info=VideoInfo(bvid="BVconcurrent", cid=1), output_dir=str(tmp_path))
    services = [DownloadService(object(), str(tmp_path), library_repository=library) for _ in range(2)]
    transfers, started, release = [], threading.Event(), threading.Event()
    def transfer(service):
        def run(*_):
            transfers.append(True)
            started.set()
            assert release.wait(5)
            service._downloader.last_video_stream = StreamInfo(id=80, codecid=12)
            service._downloader.last_audio_stream = StreamInfo(id=30280)
            path = tmp_path / "concurrent.mp4"
            path.write_bytes(b"one transfer")
            return str(path)
        return run
    for service in services:
        monkeypatch.setattr(service._downloader, "download", transfer(service))
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(services[0].download, item, lambda *_: None)
        assert started.wait(5)
        second = executor.submit(services[1].download, item, lambda *_: None)
        release.set()
        assert absolute_path(first.result().video_path) == absolute_path(second.result().video_path)
    assert transfers == [True]


def test_strict_policy_stops_before_media_transfer(tmp_path, monkeypatch):
    api = SimpleNamespace(get_play_url_for=lambda *_args, **_kwargs: {"video_streams": [StreamInfo(id=64, codecid=7)], "audio_streams": [StreamInfo(id=30280)]})
    downloader = StreamDownloader(api, str(tmp_path))
    monkeypatch.setattr(downloader, "_download_stream", lambda *_: pytest.fail("must stop before transfer"))
    with pytest.raises(SpecificationMismatchError, match="720P"):
        downloader.download(DownloadItem(video_info=VideoInfo(bvid="BVdemo", cid=1), strict_match=True), lambda *_: None)
    assert not (tmp_path / ".bili-cache").exists()


def test_directory_relocation_keeps_companions_and_reuses_new_paths(tmp_path, monkeypatch):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    library, item, original = stored(old)
    subtitle = old / "lesson.zh.srt"
    subtitle.write_text("subtitle")
    item.download_subtitle = True
    original.subtitle_paths = [str(subtitle)]
    original.subtitle_languages = {"zh-Hans": str(subtitle)}
    library.record_download(item, original)
    new.mkdir()
    Path(original.video_path).rename(new / "lesson.mp4")
    subtitle.rename(new / subtitle.name)
    assert len(library.relocate_directory(old, new)) == 2
    library.relocate_directory(old, new, apply=True)
    service = DownloadService(object(), str(old), library_repository=library)
    no_transfer(monkeypatch, service)
    result = service.download(item, lambda *_: None)
    assert absolute_path(result.video_path) == absolute_path(new / "lesson.mp4")
    assert result.subtitle_languages == {"zh-Hans": absolute_path(new / subtitle.name)}


def test_directory_relocation_is_atomic_when_targets_are_missing(tmp_path):
    library, _, original = stored(tmp_path)
    with pytest.raises(ValueError, match="未修改"):
        library.relocate_directory(tmp_path, tmp_path / "absent", apply=True)
    assert library.list_assets()[0]["path"] == absolute_path(original.video_path)


def test_verification_distinguishes_tool_failure_from_corruption(tmp_path, monkeypatch):
    library, item, _ = stored(tmp_path)
    asset_id = library.list_assets()[0]["id"]
    probe = "bilibili_downloader.core.ffmpeg.FFmpegManager.inspect_media"
    monkeypatch.setattr(probe, lambda *_: {"valid": False, "unavailable": True, "message": "工具不可用"})
    assert library.verify_media([asset_id])["inaccessible"] == 1
    assert library.match_media(item).state == "saved"
    monkeypatch.setattr(probe, lambda *_: {"valid": False, "message": "缺少视频轨"})
    assert library.verify_media([asset_id])["invalid"] == 1
    assert library.match_media(item).state == "unavailable"


@pytest.mark.parametrize("text,expected", [("1-3,5", {1, 2, 3, 5}), ("2–4，6", {2, 3, 4, 6}), ("1,1", {1})])
def test_range_parser(text, expected):
    assert parse_page_range(text, 8) == expected


@pytest.mark.parametrize("text", ["0", "3-1", "1-9", "bad", "-1"])
def test_invalid_ranges_are_not_silently_accepted(text):
    with pytest.raises(ValueError):
        parse_page_range(text, 8)


def test_page_search_preserves_explicit_hidden_selection(qtbot):
    pages = [VideoPage(cid=1, part="第一课"), VideoPage(cid=2, part="第二课")]
    dialog = PageSelectionDialog(pages, {1, 2})
    qtbot.addWidget(dialog)
    dialog.search.setText("第二")
    assert [p.cid for p in dialog.selected_pages()] == [1, 2]
    assert "筛选外 1 项" in dialog.selection_bar.summary.text()
    dialog.range.setText("1-2")
    dialog.apply_range()
    assert len(dialog.selected_pages()) == 2


def test_queue_search_and_bulk_scope_are_consistent(workspace):
    for n, title in enumerate(("猫咪", "学习"), 1):
        item = DownloadItem(video_info=VideoInfo(bvid=f"BVdemo{n}", title=title, author=f"author{n}"))
        workspace._download_list.add_item(item, download_id=n, status=TaskStatus.PAUSED)
    workspace._task_page.search.setText("author2")
    assert workspace._download_list.isRowHidden(0)
    assert not workspace._download_list.isRowHidden(1)
    assert workspace._task_page.bulk_ids("resume") == [2]


def test_restoring_completed_tasks_displays_actual_specs(workspace):
    item = DownloadItem(video_info=VideoInfo(bvid="BVfallback"), selected_quality=VideoQuality.Q4K)
    task_id = workspace._task_repository.add(item, TaskStatus.COMPLETED)
    outcome = DownloadOutcome(video_path="/example/video.mp4", actual_quality=80, actual_video_codec=7,
                              actual_audio_quality=30280, spec_warnings=["请求 4K，实际为 1080P"], warnings=["请求 4K，实际为 1080P"])
    workspace._task_repository.update(task_id, outcome=outcome)
    workspace._restore_tasks()
    row = workspace._download_list._row_for(task_id)
    assert "1080P" in workspace._download_list.item(row, 1).text()
    assert "规格回退" in workspace._download_list.item(row, 3).text()


def test_batch_search_keeps_hidden_selection_and_reports_scope(workspace):
    batch = workspace._batch_page
    batch._on_report(ImportReport(items=[VideoInfo(bvid="BV1", title="猫", author="甲"), VideoInfo(bvid="BV2", title="狗", author="乙")]))
    batch.search.setText("乙")
    batch._set_all_checked(True)
    assert [i.bvid for i in batch.get_video_infos()] == ["BV1", "BV2"]
    assert "筛选外 1 项" in batch.selection_bar.summary.text()
    batch.selection_bar.review_button.click()
    assert not any(batch._preview.isRowHidden(row) for row in range(2))
    batch.selection_bar.review_button.click()
    assert batch.search.text() == "乙" and batch._preview.isRowHidden(0)


def test_network_retry_is_durable_cancellable_and_bounded(workspace, monkeypatch):
    item = DownloadItem(video_info=VideoInfo(bvid="BVdemo", title="retry"))
    task_id = workspace._task_repository.add(item)
    workspace._download_list.add_item(item, download_id=task_id)
    worker = SimpleNamespace(retryable=True)
    workspace._download_attempts[task_id] = worker
    workspace._on_download_error(task_id, "网络超时")
    record = workspace._task_repository.get(task_id)
    assert record.status == TaskStatus.QUEUED and record.item.retry_count == 1 and record.item.retry_at
    workspace._download_attempts.pop(task_id)
    workspace._download_list._on_pause_clicked(task_id)
    assert workspace._task_repository.get(task_id).status == TaskStatus.PAUSED
    assert task_id not in workspace._retry_pending
    item.retry_count = 3
    workspace._download_attempts[task_id] = worker
    workspace._on_download_error(task_id, "网络超时")
    assert workspace._task_repository.get(task_id).status == TaskStatus.FAILED
    workspace._download_attempts.clear()


def test_due_retry_restarts_once_without_resetting_budget(workspace, monkeypatch):
    item = DownloadItem(video_info=VideoInfo(bvid="BVdemo"), retry_count=1,
                        retry_at=(datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat())
    task_id = workspace._task_repository.add(item)
    workspace._download_list.add_item(item, download_id=task_id)
    workspace._retry_pending[task_id] = item.retry_at
    starts = []
    monkeypatch.setattr(workspace, "_start_download", lambda *_: starts.append(True))
    workspace._tick_download_retries()
    workspace._tick_download_retries()
    assert starts == [True]
    assert workspace._task_repository.get(task_id).item.retry_count == 1


def test_wrapped_permission_and_network_errors_keep_categories():
    request = httpx.Request("GET", "https://example.test")
    for error, expected in [(httpx.ConnectError("offline"), ErrorCategory.NETWORK),
                            (httpx.HTTPStatusError("denied", request=request, response=httpx.Response(403, request=request)), ErrorCategory.PERMISSION)]:
        wrapped = RuntimeError("下载失败")
        wrapped.__cause__ = error
        assert classify_error(wrapped).category == expected


def test_ffmpeg_reports_intermediate_progress_beyond_five_minutes(tmp_path, monkeypatch):
    elapsed = [0]
    def clock():
        elapsed[0] += 100
        return elapsed[0]
    class Process:
        returncode = 0
        def __init__(self, command, **_):
            self.progress = Path(command[command.index("-progress") + 1])
            Path(command[-1]).write_bytes(b"merged")
            self.polls = 0
        def poll(self):
            self.polls += 1
            self.progress.write_text(f"out_time_us={self.polls * 1000000}\n")
            return None if self.polls < 5 else 0
        def wait(self):
            return 0
        def kill(self):
            pytest.fail("a progressing job must not be killed at five minutes")
    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.time.monotonic", clock)
    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.time.sleep", lambda _: None)
    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.subprocess.Popen", Process)
    progress = []
    ok, _ = FFmpegManager._execute_command(["ffmpeg", "output.mp4"], tmp_path / "output.mp4", None,
                                          timeout_seconds=None, progress_callback=progress.append,
                                          duration_seconds=10, stall_timeout_seconds=600)
    assert ok and any(0 < value < 1 for value in progress) and progress[-1] == 1
    assert elapsed[0] > 300


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="system FFmpeg required for generated fixture")
def test_real_ffmpeg_progress_and_media_inspection(tmp_path):
    exe = shutil.which("ffmpeg")
    source = tmp_path / "generated.mp4"
    subprocess.run([exe, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:r=5",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "0.6", "-c:v", "mpeg4", "-c:a", "aac", str(source)],
                   check=True, capture_output=True, timeout=20)
    progress = []
    target = tmp_path / "merged.mp4"
    ok, message = FFmpegManager.merge_streams(source, source, target, custom_path=exe,
                                             duration_seconds=0.6, progress_callback=progress.append)
    assert ok, message
    assert progress[-1] == 1
    result = FFmpegManager.inspect_media(target, "video", exe)
    assert result["valid"] and result["has_audio"] and result["has_video"] and result["duration"] > 0
    target.write_bytes(b"broken media")
    assert FFmpegManager.inspect_media(target, "video", exe)["valid"] is False
