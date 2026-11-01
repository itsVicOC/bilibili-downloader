"""Regression coverage for multipart naming, durable inventory and bulk removal."""

import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMessageBox

from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.library import LibraryRepository, absolute_path
from bilibili_downloader.core.models import (
    AppSettings,
    DownloadItem,
    DownloadOutcome,
    OutputMode,
    StreamInfo,
    TaskStatus,
    VideoInfo,
    VideoPage,
)
from bilibili_downloader.core.task_repository import TaskRepository
from bilibili_downloader.core.update_protocol import (
    InstallDataInApplicationError,
    ensure_install_data_outside,
)
from scripts import update_helper
from tests.test_updater import installed_root
from tests.test_workspaces import StubService
from tests.test_workspaces import workspace as workspace


def multipart():
    return VideoInfo(
        bvid="BVdemo",
        title="长中文作品总标题" * 25,
        cid=1,
        pages=[
            VideoPage(cid=i, page=i, part=f"第{i}课 / 学习标题") for i in range(1, 111)
        ],
    )


def saved(tmp_path, *, metadata=False):
    media = tmp_path / "lesson.mp4"
    media.write_bytes(b"media")
    subtitle = tmp_path / "lesson.zh.srt"
    subtitle.write_text("subtitle", encoding="utf-8")
    item = DownloadItem(
        video_info=VideoInfo(bvid="BVdemo", cid=1, title="lesson"),
        output_dir=str(tmp_path),
    )
    outcome = DownloadOutcome(
        video_path=str(media),
        subtitle_paths=[str(subtitle)],
        actual_quality=80,
        actual_video_codec=12,
    )
    return item, outcome


@pytest.mark.parametrize(
    "mode,quality,extension",
    [
        (OutputMode.VIDEO, 30280, ".mp4"),
        (OutputMode.AUDIO, 30280, ".m4a"),
        (OutputMode.AUDIO, 30251, ".flac"),
    ],
)
def test_long_titles_keep_110_distinct_page_names(mode, quality, extension):
    info, settings = multipart(), AppSettings()
    items = [
        DownloadItem(
            video_info=info.for_page(p),
            path_template=settings.template_for(info),
            output_mode=mode,
            selected_audio_quality=quality,
        )
        for p in info.pages
    ]
    paths = [item.relative_output_path for item in items]
    assert len(set(paths)) == 110
    assert paths[0].name == f"001 - 第1课 _ 学习标题{extension}"
    assert paths[-1].name.startswith("110 - 第110课")
    assert all(
        len(component.encode()) <= 205 for path in paths for component in path.parts
    )
    info.pages[0].part = ""
    assert (
        DownloadItem(
            video_info=info, path_template=settings.template_for(info)
        ).filename
        == "001 - P1.mp4"
    )


def test_settings_migrate_custom_templates_and_directory_fingerprints(tmp_path):
    assert (
        AppSettings(path_template="{author}/{part}").multipart_path_template
        == "{author}/{part}"
    )
    assert (
        AppSettings(path_template="{title}{part_suffix}").multipart_path_template
        == "{title}/{page_padded} - {part}"
    )
    item, _ = saved(tmp_path)
    assert (
        item.fingerprint
        != item.model_copy(update={"output_dir": str(tmp_path / "other")}).fingerprint
    )
    repo = TaskRepository(tmp_path / "tasks.sqlite3")
    task_id = repo.add(item.model_copy(update={"output_dir": None}))
    repo.bind_output_directories(str(tmp_path / "original"))
    repo.bind_output_directories(str(tmp_path / "changed"))
    assert repo.get(task_id).item.output_dir == str(tmp_path / "original")


def test_task_outcome_survives_remove_undo_and_library_is_independent(tmp_path):
    item, outcome = saved(tmp_path)
    tasks = TaskRepository(tmp_path / "tasks.sqlite3")
    task_id = tasks.add(item, TaskStatus.COMPLETED)
    tasks.update(task_id, output_path=outcome.video_path, outcome=outcome)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    library.import_tasks(tasks.list_tasks())
    library.import_tasks(tasks.list_tasks())
    assert len(library.list_assets()) == 1
    record = tasks.get(task_id)
    tasks.delete_many([task_id])
    assert len(LibraryRepository(tmp_path / "library.sqlite3").list_assets()) == 1
    tasks.restore_records([record])
    assert tasks.get(task_id).outcome == outcome
    asset = library.list_assets()[0]
    library.hide([asset["id"]])
    library.import_tasks(tasks.list_tasks())
    assert library.list_assets() == []
    assert Path(outcome.video_path).read_bytes() == b"media"


def test_receipt_retries_failed_registration_without_stream_urls(tmp_path, monkeypatch):
    item, outcome = saved(tmp_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    original = library.register
    monkeypatch.setattr(
        library,
        "register",
        lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("locked")),
    )
    with pytest.raises(sqlite3.OperationalError):
        library.record_download(item, outcome)
    receipt = next(library.pending_dir.glob("*.json"))
    assert json.loads(receipt.read_text())["item"]["video_info"]["video_streams"] == []
    monkeypatch.setattr(library, "register", original)
    assert library.replay_pending() == []
    assert len(library.list_assets()) == 1
    assert not list(library.pending_dir.glob("*.json"))


def test_inventory_checks_offline_missing_cancel_and_relocation(tmp_path):
    item, outcome = saved(tmp_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    asset_id = library.register(item, outcome)
    library.check_files([asset_id])
    assert {f["state"] for f in library.files_for([asset_id])} == {"available"}
    moved = tmp_path / "moved.mp4"
    Path(outcome.video_path).rename(moved)
    library.check_files([asset_id])
    media = next(f for f in library.files_for([asset_id]) if f["kind"] == "media")
    assert media["state"] == "missing"
    library.relocate(media["id"], moved)
    cancelled = threading.Event()
    cancelled.set()
    library.check_files([asset_id], cancelled)
    assert library.files_for([asset_id])[0]["state"] == "unchecked"
    library.check_files([asset_id])
    assert library.files_for([asset_id])[0]["state"] == "available"
    offline = tmp_path / "offline"
    offline.mkdir()
    item2 = item.model_copy(update={"video_info": VideoInfo(bvid="other", cid=2)})
    second = library.register(
        item2, DownloadOutcome(video_path=str(offline / "gone.mp4"))
    )
    offline.rmdir()
    library.check_files([second])
    assert library.files_for([second])[0]["state"] == "inaccessible"


def test_recycle_is_per_file_skips_shared_changed_and_links(tmp_path):
    item, outcome = saved(tmp_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    asset_id = library.register(item, outcome)
    library.check_files([asset_id])
    entries = library.files_for([asset_id])
    Path(outcome.subtitle_paths[0]).write_text("changed subtitle", encoding="utf-8")
    moved = []

    def trash(path):
        moved.append(path)
        Path(path).rename(Path(path).with_suffix(".trash"))
        return True, path + ".trash"

    result = library.recycle(entries, trash)
    assert moved == [absolute_path(outcome.video_path)]
    assert result[0][1] == "" and "变化" in result[1][1]
    library.check_files([asset_id])
    assert library.files_for([asset_id])[0]["state"] == "recycled"
    other = item.model_copy(update={"video_info": VideoInfo(bvid="other", cid=2)})
    library.register(other, DownloadOutcome(video_path=outcome.subtitle_paths[0]))
    assert "引用" in library.recycle([entries[1]], trash)[0][1]
    link = tmp_path / "link.mp4"
    link.symlink_to(outcome.subtitle_paths[0])
    third = library.register(other, DownloadOutcome(video_path=str(link)))
    assert "符号链接" in library.recycle(library.files_for([third]), trash)[0][1]


def test_unknown_legacy_attachments_are_not_guessed(tmp_path):
    item, outcome = saved(tmp_path)
    tasks = TaskRepository(tmp_path / "tasks.sqlite3")
    task_id = tasks.add(item, TaskStatus.COMPLETED)
    tasks.update(task_id, output_path=outcome.video_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    library.import_tasks(tasks.list_tasks())
    assert [f["kind"] for f in library.list_assets()[0]["files"]] == ["media"]


def test_bulk_remove_110_tasks_waits_for_settlement_undo_and_late_events(
    workspace, tmp_path
):
    window = workspace
    repo, table, page = (
        window._task_repository,
        window._download_list,
        window._task_page,
    )
    media = tmp_path / "saved.mp4"
    media.write_bytes(b"media")
    ids = []
    for index in range(110):
        state = [
            TaskStatus.PAUSED,
            TaskStatus.FAILED,
            TaskStatus.COMPLETED,
            TaskStatus.DOWNLOADING,
        ][index % 4]
        item = DownloadItem(
            video_info=VideoInfo(bvid="BVdemo", cid=index, title=f"第{index}课")
        )
        task_id = repo.add(item, state)
        table.add_item(item, download_id=task_id, status=state)
        ids.append(task_id)
    page.filter.setCurrentIndex(page.filter.findData("paused"))
    table.select_visible()
    assert len(table.selected_ids()) == 28
    assert page.bulk_ids("resume") == table.selected_ids()
    page.filter.setCurrentIndex(page.filter.findData("completed"))
    assert table.selected_ids() == []
    active_id = ids[3]
    paused = []
    worker = SimpleNamespace(pause=lambda: paused.append(True))
    window._download_attempts[active_id] = worker
    window._remove_task_records(ids)
    assert paused and repo.get(ids[0]) is not None
    assert active_id in table.removing_ids
    window._on_download_finished(active_id, DownloadOutcome(video_path=str(media)))
    # A completion during stop is indexed before the removal transaction.
    window._on_worker_settled(active_id, worker)
    assert repo.list_tasks() == []
    assert not table._items
    window._undo_removed_tasks()
    assert len(repo.list_tasks()) == 110
    assert repo.get(active_id).status == TaskStatus.COMPLETED
    assert all(r.status != TaskStatus.DOWNLOADING for r in repo.list_tasks())
    window._remove_task_records(ids)
    window._on_download_progress(active_id, 0.5, "late")
    window._on_download_finished(active_id, DownloadOutcome(video_path=str(media)))
    assert repo.list_tasks() == []
    assert media.read_bytes() == b"media"


def test_inventory_ui_survives_clearing_tasks_and_background_check(
    workspace, qtbot, tmp_path
):
    item, outcome = saved(tmp_path)
    window = workspace
    window._library.record_download(item, outcome)
    page = window._library_page
    page.refresh()
    assert page.table.rowCount() == 1
    page.table.selectRow(0)
    assert page.selected_ids()
    page.check()
    qtbot.waitUntil(lambda: not page._jobs)
    assert page.table.item(0, 4).text() == "文件存在"
    assert page.table.item(0, 3).text() == "5.0 B"
    page.search.setText("no match")
    assert page.selected_ids() == []
    assert not page.recycle_action.isEnabled()


def test_bulk_confirmation_includes_hidden_tasks_and_can_be_cancelled(
    workspace, monkeypatch
):
    item = DownloadItem(video_info=VideoInfo(bvid="demo", cid=1))
    task_id = workspace._task_repository.add(item)
    workspace._download_list.add_item(item, download_id=task_id)
    texts = []

    def cancel(box):
        texts.append(box.text() + box.informativeText())
        return QMessageBox.Cancel

    monkeypatch.setattr(QMessageBox, "exec", cancel)
    workspace._request_remove_tasks([task_id], all_tasks=True)
    assert "全部" in texts[0] and "1 项" in texts[0] and "停止" in texts[0]
    assert workspace._task_repository.get(task_id) is not None


def test_saved_media_is_indexed_before_cancelled_companion_work(tmp_path, monkeypatch):
    item, outcome = saved(tmp_path)
    item.download_danmaku = True
    library = LibraryRepository(tmp_path / "library.sqlite3")
    snapshots = []
    service = DownloadService(
        None,
        str(tmp_path),
        library_repository=library,
        outcome_callback=lambda saved: snapshots.append(saved),
    )
    monkeypatch.setattr(service._downloader, "download", lambda *_: outcome.video_path)

    def progress(_percent, text):
        if "弹幕" in text:
            service.cancel()

    monkeypatch.setattr(
        "bilibili_downloader.core.download_service.DanmakuDownloader.download_and_convert",
        lambda *_: (_ for _ in ()).throw(RuntimeError("cancelled")),
    )
    with pytest.raises(RuntimeError, match="cancelled"):
        service.download(item, progress)
    assert (
        snapshots
        and library.list_assets()[0]["files"][0]["path"]
        == absolute_path(outcome.video_path)
    )
    assert Path(outcome.video_path).read_bytes() == b"media"


def test_unavailable_library_keeps_receipt_and_recovers(tmp_path):
    item, outcome = saved(tmp_path)
    database = tmp_path / "library.sqlite3"
    database.write_bytes(b"invalid database")
    library = LibraryRepository(database, initialize=False)
    with pytest.raises(sqlite3.DatabaseError):
        library.record_download(item, outcome)
    assert len(list(library.pending_dir.glob("*.json"))) == 1
    database.rename(tmp_path / "library.corrupt.sqlite3")
    recovered = LibraryRepository(database)
    assert recovered.replay_pending() == []
    assert recovered.list_assets()[0]["outcome"] == outcome


def test_relocated_assets_do_not_reimport_or_merge_new_downloads(tmp_path):
    item, outcome = saved(tmp_path)
    tasks = TaskRepository(tmp_path / "tasks.sqlite3")
    task_id = tasks.add(item, TaskStatus.COMPLETED)
    tasks.update(task_id, output_path=outcome.video_path, outcome=outcome)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    library.import_tasks(tasks.list_tasks())
    first = library.list_assets()[0]
    moved = tmp_path / "elsewhere.mp4"
    Path(outcome.video_path).rename(moved)
    library.relocate(first["files"][0]["id"], moved)
    library.import_tasks(tasks.list_tasks())
    assert len(library.list_assets()) == 1
    Path(outcome.video_path).write_bytes(b"new download")
    library.record_download(item, outcome)
    assert len(library.list_assets()) == 2


def test_library_backup_restores_wal_and_pending_and_accepts_old_snapshots(tmp_path):
    item, outcome = saved(tmp_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    library.record_download(item, outcome)
    library.pending_dir.mkdir(exist_ok=True)
    (library.pending_dir / "pending.json").write_text("{}")
    snapshot = tmp_path / "snapshot"
    update_helper._snapshot(tmp_path, snapshot)
    library.hide([library.list_assets()[0]["id"]])
    (library.pending_dir / "pending.json").unlink()
    update_helper._restore_snapshot(tmp_path, snapshot)
    assert LibraryRepository(library.database_path).list_assets()
    assert (library.pending_dir / "pending.json").is_file()
    # A helper reading a snapshot made before media inventory existed leaves it alone.
    old = tmp_path / "old-snapshot"
    old.mkdir()
    (old / "files.json").write_text("{}")
    update_helper._restore_snapshot(tmp_path, old)
    assert library.database_path.is_file()


def test_inventory_paths_protected_after_task_removal(tmp_path):
    target, build = installed_root(tmp_path)
    media = target / "user-video.mp4"
    media.write_bytes(b"media")
    data = tmp_path / "data"
    library = LibraryRepository(data / "library.sqlite3")
    item = DownloadItem(video_info=VideoInfo(bvid="BVdemo", cid=1))
    library.register(item, DownloadOutcome(video_path=str(media)))
    with pytest.raises(InstallDataInApplicationError):
        ensure_install_data_outside(target, data, build)


def test_probation_defers_inventory_until_commit(qtbot, tmp_path):
    from bilibili_downloader.gui.live_controller import LiveUiController
    from bilibili_downloader.gui.main_window import MainWindow
    from bilibili_downloader.utils.config import ConfigManager

    config = ConfigManager(tmp_path / "config.json")
    config.save(AppSettings(output_dir=str(tmp_path / "downloads")))
    controller = LiveUiController(config, service_factory=StubService)
    window = MainWindow(
        config,
        TaskRepository(config.task_database_path),
        controller,
        startup_paused=True,
    )
    qtbot.addWidget(window)
    assert not config.library_database_path.exists()
    assert not (config.data_dir / "library-pending").exists()
    window.resume_startup()
    assert config.library_database_path.is_file()
    controller.shutdown()


def test_retry_uses_frozen_directory_after_settings_change(
    workspace, monkeypatch, tmp_path
):
    window = workspace
    original = tmp_path / "original"
    item = DownloadItem(
        video_info=VideoInfo(bvid="BVdemo", cid=1), output_dir=str(original)
    )
    task_id = window._task_repository.add(item, TaskStatus.PAUSED)
    window._download_list.add_item(item, download_id=task_id, status=TaskStatus.PAUSED)
    window._settings.output_dir = str(tmp_path / "changed")
    submitted = []
    monkeypatch.setattr(window._download_pool, "start", submitted.append)
    window._on_retry_download(task_id)
    worker = window._download_attempts[task_id]
    assert worker._output_dir == str(original)
    assert submitted
    window._on_worker_settled(task_id, worker)


def test_failed_recycle_never_unlinks_media(tmp_path):
    item, outcome = saved(tmp_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    asset_id = library.record_download(item, outcome)
    result = library.recycle(library.files_for([asset_id]), lambda _: (False, ""))
    assert all(error for _, error in result)
    assert Path(outcome.video_path).read_bytes() == b"media"
    assert Path(outcome.subtitle_paths[0]).read_text() == "subtitle"


def test_real_workers_stop_110_queued_downloads_before_removal(
    workspace, monkeypatch, qtbot
):
    class WaitingService:
        def __init__(self, *_args, **_kwargs):
            self.cancelled = threading.Event()

        def download(self, _item, _progress):
            assert self.cancelled.wait(10)
            raise RuntimeError("Download cancelled by user")

        def cancel(self):
            self.cancelled.set()

    monkeypatch.setattr(
        "bilibili_downloader.gui.threads.download_worker.DownloadService",
        WaitingService,
    )
    main_thread = threading.get_ident()
    callback_threads = []
    original = workspace._on_download_paused

    def paused(task_id):
        callback_threads.append(threading.get_ident())
        original(task_id)

    monkeypatch.setattr(workspace, "_on_download_paused", paused)
    workspace._download_pool.setMaxThreadCount(1)
    for index in range(110):
        workspace._enqueue_download(
            DownloadItem(
                video_info=VideoInfo(bvid="demo", cid=index, title=f"Lesson {index}")
            )
        )
    assert len(workspace._download_attempts) == 110
    workspace._remove_task_records(list(workspace._download_attempts))
    qtbot.waitUntil(lambda: workspace._pending_removal is None, timeout=15000)
    assert not workspace._download_attempts
    assert callback_threads and set(callback_threads) == {main_thread}
    assert workspace._task_repository.list_tasks() == []
    workspace._undo_removed_tasks()
    assert len(workspace._task_repository.list_tasks()) == 110
    assert all(
        r.status == TaskStatus.PAUSED for r in workspace._task_repository.list_tasks()
    )


def test_committed_file_is_registered_when_last_progress_callback_cancels(
    tmp_path, monkeypatch
):
    client = SimpleNamespace(
        get_play_url=lambda **_: {
            "video_streams": [],
            "audio_streams": [StreamInfo(id=30280, bandwidth=100)],
        }
    )
    item = DownloadItem(
        video_info=VideoInfo(bvid="demo", cid=1, title="audio"),
        output_mode=OutputMode.AUDIO,
    )
    library = LibraryRepository(tmp_path / "library.sqlite3")
    service = DownloadService(client, str(tmp_path), library_repository=library)
    monkeypatch.setattr(
        service._downloader,
        "_download_stream",
        lambda _stream, path, _progress: path.write_bytes(b"audio"),
    )

    def remux(_source, target, **_kwargs):
        target.write_bytes(b"saved media")
        service.cancel()
        return True, "ok"

    monkeypatch.setattr(
        "bilibili_downloader.core.downloader.FFmpegManager.remux_audio", remux
    )
    with pytest.raises(RuntimeError, match="cancelled"):
        service.download(item, lambda *_: None)
    asset = library.list_assets()[0]
    assert Path(asset["files"][0]["path"]).read_bytes() == b"saved media"


def test_file_list_database_failure_preserves_selection_and_files(
    workspace, tmp_path, monkeypatch
):
    item, outcome = saved(tmp_path)
    page = workspace._library_page
    page.repository.record_download(item, outcome)
    page.refresh()
    page.table.selectRow(0)
    selected = page.selected_ids()

    def fail(*_):
        raise sqlite3.OperationalError("read only")

    monkeypatch.setattr(page.repository, "hide", fail)
    page.hide_selected()
    assert page.selected_ids() == selected
    assert page.repository.list_assets()
    assert Path(outcome.video_path).read_bytes() == b"media"
    monkeypatch.setattr(page.repository, "files_for", fail)
    page.recycle_selected()
    assert page.selected_ids() == selected


def test_selection_first_buttons_and_explicit_all(workspace, monkeypatch):
    table, page = workspace._download_list, workspace._task_page
    for task_id, state in (
        (1, TaskStatus.PAUSED),
        (2, TaskStatus.FAILED),
        (3, TaskStatus.DOWNLOADING),
    ):
        table.add_item(
            DownloadItem(video_info=VideoInfo(bvid="demo", cid=task_id)),
            download_id=task_id,
            status=state,
        )
    table.selectRow(0)
    assert page.bulk_ids("resume") == [1]
    assert page.bulk_ids("pause") == []
    assert "所选" in page._bulk_buttons[1].text()
    assert not page._bulk_buttons[0].isEnabled()
    submitted = []
    monkeypatch.setattr(workspace, "_on_retry_download", submitted.append)
    page._bulk_buttons[1].click()
    assert submitted == [1]
    page._resume_entire_action.trigger()
    assert submitted == [1, 1, 2]
    page.filter.setCurrentIndex(page.filter.findData("attention"))
    assert not table.selected_ids()
    assert page.bulk_ids("resume") == [2]
    assert not page.download_detail.isVisible()


def test_ordinary_record_removal_has_no_confirmation_and_keeps_undo(workspace):
    item = DownloadItem(video_info=VideoInfo(bvid="demo", cid=1))
    task_id = workspace._task_repository.add(item, TaskStatus.PAUSED)
    workspace._download_list.add_item(
        item, download_id=task_id, status=TaskStatus.PAUSED
    )
    # The workspace fixture rejects every unexpected dialog.
    workspace._request_remove_tasks([task_id])
    assert workspace._task_repository.get(task_id) is None
    workspace._status_bar.clearMessage()
    assert workspace._task_page.undo_action.isEnabled()
    workspace._task_page.undo_action.trigger()
    assert workspace._task_repository.get(task_id).status == TaskStatus.PAUSED


def test_library_empty_filtered_and_loading_states(workspace, tmp_path):
    page = workspace._library_page
    assert page.stack.currentIndex() == 1
    page.check()
    assert not page._jobs and not page.check_button.isEnabled()
    item, outcome = saved(tmp_path)
    page.repository.record_download(item, outcome)
    page.refresh()
    page.search.setText("no matches")
    assert page.stack.currentIndex() == 2 and not page.check_button.isEnabled()
    page.clear_filters()
    assert page.stack.currentIndex() == 0
    assert "1 / 1" in page.count_label.text()
    page.set_repository(None)
    assert page.stack.currentIndex() == 3
    assert not page.open_action.isEnabled()


def test_file_record_undo_survives_notice_replacement(workspace, tmp_path):
    page = workspace._library_page
    item, outcome = saved(tmp_path)
    asset_id = page.repository.record_download(item, outcome)
    page.refresh()
    page.table.selectRow(0)
    page.hide_selected()
    assert page.repository.list_assets() == []
    assert page._removed_ids == [asset_id]
    page._feedback("其他操作已完成。")
    assert page.undo_action.isEnabled()
    page.undo_action.trigger()
    assert page.repository.list_assets()[0]["id"] == asset_id
    assert Path(outcome.video_path).read_bytes() == b"media"


def test_refresh_preserves_attachment_and_main_actions_target_media(
    workspace, tmp_path, monkeypatch
):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QDesktopServices

    page = workspace._library_page
    item, outcome = saved(tmp_path)
    page.repository.record_download(item, outcome)
    page.refresh()
    page.table.selectRow(0)
    assert not page.attachments_toggle.isChecked()
    page.attachments_toggle.setChecked(True)
    attachment = page.files.topLevelItem(0)
    page.files.setCurrentItem(attachment)
    attachment_id = attachment.data(0, Qt.UserRole)["id"]
    opened = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )
    page.open_action.click()
    page.files.itemDoubleClicked.emit(attachment, 0)
    assert [absolute_path(path) for path in opened] == [
        absolute_path(outcome.video_path),
        absolute_path(outcome.subtitle_paths[0]),
    ]
    page.refresh()
    assert page.attachments_toggle.isChecked()
    assert page.files.currentItem().data(0, Qt.UserRole)["id"] == attachment_id
    page.open_action.click()
    assert absolute_path(opened[-1]) == absolute_path(outcome.video_path)


def test_check_can_cancel_while_open_and_search_remain_available(
    workspace, tmp_path, monkeypatch, qtbot
):
    page = workspace._library_page
    item, outcome = saved(tmp_path)
    page.repository.record_download(item, outcome)
    page.refresh()
    page.table.selectRow(0)
    started = threading.Event()

    def check(_ids, cancel, progress):
        started.set()
        progress(1, 2)
        assert cancel.wait(5)
        return {
            "checked": 1,
            "total": 2,
            "cancelled": True,
            "missing": 0,
            "inaccessible": 0,
            "issues": [],
        }

    monkeypatch.setattr(page.repository, "check_files", check)
    page.check()
    qtbot.waitUntil(started.is_set)
    assert page.open_action.isEnabled() and page.search.isEnabled()
    assert not page.hide_action.isEnabled() and not page.recycle_action.isEnabled()
    page.cancel_button.click()
    qtbot.waitUntil(lambda: not page._jobs)
    assert "检查已取消" in page.notice.label.text()
    assert "1 个文件" in page.notice.label.text()
    assert page.progress_label.text() == ""


def test_recycle_summary_stays_short_with_long_errors_and_lists(
    workspace, tmp_path, monkeypatch, qtbot
):
    from PySide6.QtWidgets import QDialog

    from bilibili_downloader.gui.widgets.library_page import OperationDialog

    page = workspace._library_page
    item, outcome = saved(tmp_path)
    page.repository.record_download(item, outcome)
    page.refresh()
    page.table.selectRow(0)
    prompts = []

    def accept(box):
        prompts.append((box.summary.text(), box.reader.toPlainText()))
        return QDialog.Accepted

    monkeypatch.setattr(OperationDialog, "exec", accept)

    def recycle(entries, progress):
        progress(1, len(entries))
        return [
            (entries[0]["path"], ""),
            (entries[1]["path"], "PermissionError: " + "diagnostic " * 100),
        ]

    monkeypatch.setattr(page.repository, "recycle", recycle)
    page.recycle_selected()
    qtbot.waitUntil(lambda: not page._jobs)
    assert "共 2 个文件" in prompts[0][0] and "1 个附件" in prompts[0][0]
    assert "系统回收站恢复" in prompts[0][0]
    assert absolute_path(outcome.video_path) in prompts[0][1]
    assert page.notice.label.text() == "已回收 1 个文件，1 个未处理。"
    assert "PermissionError" not in page.notice.label.text()
    assert "PermissionError" in page._details
    assert page.notice.action.text() == "查看详情"


def test_check_progress_and_undo_only_restore_changed_ids(tmp_path):
    item, outcome = saved(tmp_path)
    library = LibraryRepository(tmp_path / "library.sqlite3")
    asset_id = library.record_download(item, outcome)
    progress = []
    report = library.check_files(
        [asset_id], progress=lambda done, total: progress.append((done, total))
    )
    assert report["checked"] == 2 and progress == [(1, 2), (2, 2)]
    assert library.hide([asset_id, asset_id, -1]) == [asset_id]
    assert library.hide([asset_id]) == []
    assert library.restore_hidden([asset_id, asset_id, -1]) == [asset_id]
    assert library.restore_hidden([asset_id]) == []


def test_naming_previews_use_audio_quality_and_keep_absolute_path_in_tooltip(
    workspace, tmp_path
):
    from bilibili_downloader.core.models import OutputMode

    panel = workspace._settings_page
    panel._output_dir.setText(str(tmp_path / "output"))
    panel._output_mode_combo.setCurrentIndex(
        panel._output_mode_combo.findData(OutputMode.AUDIO)
    )
    panel._audio_combo.setCurrentIndex(panel._audio_combo.findData(30251))
    preview = panel._template_previews["multipart_path_template"]
    assert preview.text().endswith(".flac")
    assert str(tmp_path) not in preview.text()
    assert str(tmp_path / "output") in preview.toolTip()
    assert preview.toolTip().endswith(".flac")
    assert not panel._template_fields.toggle.isChecked()


def test_batch_summary_counts_expanded_pages(workspace):
    batch = workspace._batch_page
    batch._url_text.setPlainText("BVdemo")
    batch._on_resolved([multipart()], [])
    assert batch._selected_label.text() == "已选 1 个作品 · 110 个任务"
    assert "001 -" in batch._path_preview._full_text
    assert "路径示例" in batch._path_preview._full_text
    assert workspace._settings.output_dir not in batch._path_preview._full_text


def test_expanded_attachment_first_row_fits_compact_window(workspace, tmp_path, qtbot):
    page = workspace._library_page
    item, outcome = saved(tmp_path)
    page.repository.record_download(item, outcome)
    page.refresh()
    workspace.resize(900, 640)
    workspace._show_tasks(3)
    workspace.show()
    page.table.selectRow(0)
    page.attachments_toggle.setChecked(True)
    qtbot.waitUntil(lambda: page.files.isVisible())
    row = page.files.visualItemRect(page.files.topLevelItem(0))
    assert page.files.viewport().rect().contains(row)
    visible = page.files.viewport().visibleRegion().boundingRect()
    assert visible.top() <= row.top() and row.bottom() <= visible.bottom()
    assert not page.table.isColumnHidden(0)
    assert page.table.isColumnHidden(5)


def test_file_select_all_shortcut_respects_filter(workspace, tmp_path, qtbot):
    from PySide6.QtGui import QKeySequence

    page = workspace._library_page
    item, outcome = saved(tmp_path)
    page.repository.record_download(item, outcome)
    other = tmp_path / "other.mp4"
    other.write_bytes(b"other")
    page.repository.record_download(
        item.model_copy(
            update={"video_info": VideoInfo(bvid="other", cid=2, title="Other work")}
        ),
        DownloadOutcome(video_path=str(other)),
    )
    page.refresh()
    page.search.setText("Other work")
    workspace._show_tasks(3)
    workspace.show()
    page.table.setFocus()
    qtbot.keySequence(page.table, QKeySequence(QKeySequence.SelectAll))
    assert len(page.selected_ids()) == 1
    assert page._file()["path"] == absolute_path(other)


def test_single_preview_copy_value_is_absolute_and_has_no_count_suffix(workspace):
    window = workspace
    info = multipart()
    window._current_video = info
    window._populate_page_combo(info)
    window._page_combo.setCurrentIndex(window._page_combo.findData("all"))
    window._refresh_download_summary()
    hint = window._download_path_hint
    assert hint._copy_value.startswith(window._settings.output_dir)
    assert hint._copy_value.endswith(".mp4")
    assert "110 个任务" not in hint._copy_value
    assert "预计" in hint.text()


def test_responsive_columns_preserve_file_and_attachment_selection(
    workspace, tmp_path, qtbot
):
    from PySide6.QtWidgets import QApplication
    page = workspace._library_page
    item, outcome = saved(tmp_path)
    asset_id = page.repository.record_download(item, outcome)
    page.refresh()
    workspace._show_tasks(3)
    workspace.show()
    page.table.selectRow(0)
    page.attachments_toggle.setChecked(True)
    for width, height in ((1320, 860), (900, 640), (1320, 860), (900, 640)):
        workspace.resize(width, height)
        qtbot.waitUntil(lambda: page.width() <= width)
        QApplication.processEvents()
        assert page.selected_ids() == [asset_id]
        assert page.attachments_toggle.isChecked()
        assert page.detail.isVisible() and page.files.isVisible()
