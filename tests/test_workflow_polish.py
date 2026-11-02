"""User journeys for persistent selection, contextual recovery and bounded checks."""

import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QLineEdit

from bilibili_downloader.core.library import absolute_path
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    TaskStatus,
    VideoInfo,
    VideoPage,
)
from bilibili_downloader.core.progress import DownloadPhase
from bilibili_downloader.gui.dialogs.attachments import AttachmentDialog
from bilibili_downloader.gui.dialogs.batch_dialog import BatchDialog
from bilibili_downloader.gui.dialogs.naming_fields import (
    NamingFieldDialog,
    insert_naming_field,
)
from bilibili_downloader.gui.dialogs.page_selection import PageSelectionDialog
from bilibili_downloader.gui.dialogs.relocate_directory import RelocateDirectoryDialog
from bilibili_downloader.gui.dialogs.settings_dialog import NAMING_FIELDS
from bilibili_downloader.gui.threads.inventory_worker import InventoryMatchRunner
from tests.test_archive_workflow import stored
from tests.test_workspaces import workspace as workspace


def test_part_search_review_and_range_accumulate_without_changing_source(qtbot):
    pages = [VideoPage(cid=n, page=n, part=f"第{n}课", duration=60 + n) for n in range(1, 9)]
    original = {1}
    dialog = PageSelectionDialog(pages, original)
    qtbot.addWidget(dialog)
    dialog.search.setText("第8课")
    dialog.selection_bar.all_button.click()
    assert [p.cid for p in dialog.selected_pages()] == [1, 8]
    assert "筛选外 1 项" in dialog.selection_bar.summary.text()
    dialog.selection_bar.review_button.click()
    assert [n for n in range(8) if not dialog.list.isRowHidden(n)] == [0, 7]
    dialog.selection_bar.review_button.click()
    assert dialog.search.text() == "第8课"
    dialog.range.setText("2 – 4，6")
    dialog.apply_range()
    assert [p.cid for p in dialog.selected_pages()] == [1, 2, 3, 4, 6, 8]
    dialog.range.setText("0-100")
    dialog.apply_range()
    assert [p.cid for p in dialog.selected_pages()] == [1, 2, 3, 4, 6, 8]
    dialog.reject()
    assert original == {1}


def test_part_keyboard_selects_visible_and_search_enter_does_not_submit(qtbot):
    dialog = PageSelectionDialog([VideoPage(cid=1, part="猫"), VideoPage(cid=2, part="狗")], set())
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.search.setText("狗")
    qtbot.keyClick(dialog.search, Qt.Key_Return)
    assert dialog.isVisible() and dialog.result() != QDialog.Accepted
    dialog.list.setCurrentCell(1, 0)
    qtbot.keyClick(dialog.list, Qt.Key_Space)
    assert [p.cid for p in dialog.selected_pages()] == [2]
    dialog.selection_bar.clear_button.click()
    assert not dialog.confirm_button.isEnabled()


def test_empty_search_can_recover_without_losing_choices(qtbot):
    dialog = PageSelectionDialog([VideoPage(cid=1, part="课程")], {1})
    qtbot.addWidget(dialog)
    dialog.search.setText("无匹配结果")
    assert dialog.results.currentIndex() == 1
    assert [page.cid for page in dialog.selected_pages()] == [1]
    dialog.search.clear()
    assert dialog.results.currentIndex() == 0
    fields = NamingFieldDialog(NAMING_FIELDS)
    qtbot.addWidget(fields)
    fields.search.setText("无匹配结果")
    assert fields.results.currentIndex() == 1
    assert not fields.confirm_button.isEnabled()
    fields.search.clear()
    assert fields.results.currentIndex() == 0


def test_queue_scopes_remain_explicit_across_search_and_actions(workspace):
    table, page = workspace._download_list, workspace._task_page
    for key, title in ((1, "猫"), (2, "狗"), (3, "猫和狗")):
        table.add_item(DownloadItem(video_info=VideoInfo(bvid=f"BV{key}", title=title)), download_id=key, status=TaskStatus.PAUSED)
    page.search.setText("猫")
    table.select_visible()
    page.search.setText("狗")
    assert table.selected_ids() == [1, 3]
    assert page.bulk_ids("resume") == [1, 3]
    assert "筛选外 1 项" in page.selection_bar.summary.text()
    page.selection_bar.all_button.click()
    assert table.selected_ids() == [1, 2, 3]
    page.selection_bar.review_button.click()
    assert all(not table.isRowHidden(row) for row in range(3))
    page.selection_bar.review_button.click()
    assert page.search.text() == "狗" and table.isRowHidden(0)
    page.selection_bar.clear_button.click()
    assert page.bulk_ids("resume") == [2, 3]


def test_file_click_focus_is_separate_from_batch_checkboxes(workspace, qtbot, tmp_path):
    library, item, outcome = stored(tmp_path)
    page = workspace._library_page
    page.set_repository(library)
    page.refresh()
    workspace._show_tasks(3)
    workspace.show()
    qtbot.waitUntil(lambda: page.table.viewport().isVisible())
    qtbot.wait(20)
    page.table.setCurrentCell(0, 0)
    assert not page.selected_ids()
    assert page._file()["path"] == absolute_path(outcome.video_path)
    qtbot.mouseClick(page.table.viewport(), Qt.LeftButton, pos=QPoint(15, page.table.visualItemRect(page.table.item(0, 0)).center().y()))
    assert len(page.selected_ids()) == 1
    assert not page.table.findChildren(QCheckBox)
    page.search.setText("not present")
    assert len(page.selected_ids()) == 1 and "筛选外 1 项" in page.selection_bar.summary.text()
    page.selection_bar.review_button.click()
    assert not page.table.isRowHidden(0)
    page.selection_bar.review_button.click()
    assert page.search.text() == "not present"
    assert item.video_info.title in page.table.item(0, 0).text()


def test_attachment_review_keeps_saved_files_and_only_selects_missing(qtbot, tmp_path):
    _, item, outcome = stored(tmp_path)
    cover = tmp_path / "lesson.jpg"
    cover.write_bytes(b"existing cover")
    outcome.cover_path = str(cover)
    outcome.missing_artifacts = ["subtitle"]
    item.download_cover = item.download_subtitle = True
    dialog = AttachmentDialog(item, outcome=outcome)
    qtbot.addWidget(dialog)
    assert not dialog.choices["cover"].isEnabled()
    assert dialog.choices["subtitle"].isChecked()
    selected = dialog.selected_item()
    assert selected.download_subtitle and not selected.download_cover
    dialog.reject()
    assert item.download_cover and item.download_subtitle
    assert Path(outcome.video_path).read_bytes() == b"immutable media bytes"
    assert cover.read_bytes() == b"existing cover"


def test_unavailable_media_has_recovery_instruction_and_cannot_start(qtbot, tmp_path):
    _, item, outcome = stored(tmp_path)
    Path(outcome.video_path).unlink()
    outcome.missing_artifacts = ["subtitle"]
    dialog = AttachmentDialog(item, outcome=outcome)
    qtbot.addWidget(dialog)
    assert not dialog.confirm_button.isEnabled()
    assert "重新定位" in dialog.notice.label.text()


@pytest.mark.parametrize("variable", list(NAMING_FIELDS))
def test_chinese_field_picker_inserts_real_placeholder_into_selection(qtbot, monkeypatch, variable):
    edit = QLineEdit("前缀 原内容 后缀")
    qtbot.addWidget(edit)
    edit.setSelection(3, 3)
    def choose(dialog):
        row = list(dialog.fields).index(variable)
        assert NAMING_FIELDS[variable][0] in dialog.table.item(row, 0).text()
        dialog.table.setCurrentCell(row, 0)
        return QDialog.Accepted
    monkeypatch.setattr(NamingFieldDialog, "exec", choose)
    insert_naming_field(edit, NAMING_FIELDS)
    assert edit.text() == "前缀 {" + variable + "} 后缀"


def test_field_picker_replaces_the_complete_emoji_selection(qtbot, monkeypatch):
    edit = QLineEdit("前🌠后")
    qtbot.addWidget(edit)
    edit.setSelection(1, 2)  # Qt uses UTF-16 positions, including surrogate pairs.
    def choose(dialog):
        dialog.table.setCurrentCell(0, 0)
        return QDialog.Accepted
    monkeypatch.setattr(NamingFieldDialog, "exec", choose)
    insert_naming_field(edit, NAMING_FIELDS)
    assert edit.text() == "前{title}后"


def test_preset_undo_keeps_other_templates(workspace):
    panel = workspace._settings_page
    key = "path_template"
    panel._controls[key].setText("{bvid}/{title}")
    other = panel._multipart_path_template.text()
    panel._apply_template_preset(key, "{author}/{title}")
    panel._undo_template_preset(key)
    assert panel._controls[key].text() == "{bvid}/{title}"
    assert panel._multipart_path_template.text() == other


def test_directory_preview_edits_cancel_and_apply_are_atomic(qtbot, tmp_path):
    library, _, outcome = stored(tmp_path)
    destination = tmp_path / "new"
    destination.mkdir()
    target = destination / Path(outcome.video_path).name
    target.write_bytes(Path(outcome.video_path).read_bytes())
    dialog = RelocateDirectoryDialog(library, str(tmp_path))
    qtbot.addWidget(dialog)
    dialog.new.setText(str(destination))
    dialog.preview()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert dialog.confirm_button.isEnabled()
    assert library.list_assets()[0]["path"] != absolute_path(target)
    dialog.new.setText(str(destination / "not-there"))
    assert not dialog.confirm_button.isEnabled()
    dialog.reject()
    assert library.list_assets()[0]["path"] != absolute_path(target)
    dialog.new.setText(str(destination))
    dialog.preview()
    qtbot.waitUntil(lambda: dialog._job is None)
    dialog.accept()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert library.list_assets()[0]["path"] == absolute_path(target)
    assert Path(outcome.video_path).read_bytes() == target.read_bytes()


def test_batched_check_cancellation_commits_completed_files(tmp_path):
    library, item, outcome = stored(tmp_path)
    for n in range(20):
        file = tmp_path / f"subtitle-{n}.srt"
        file.write_bytes(b"text")
        outcome.subtitle_paths.append(str(file))
    library.record_download(item, outcome)
    asset_id = library.list_assets()[0]["id"]
    with library._connection() as db:
        db.execute("UPDATE files SET state='unchecked',checked_at=NULL")
    cancelled = threading.Event()
    def progress(done, _total):
        if done == 7:
            cancelled.set()
    result = library.check_files([asset_id], cancelled, progress)
    assert result["cancelled"] and result["checked"] == 7
    states = [entry["state"] for entry in library.files_for([asset_id])]
    assert states.count("available") == 7 and states.count("unchecked") == 14
    assert Path(outcome.video_path).read_bytes() == b"immutable media bytes"


def test_directory_preview_failure_keeps_its_reason_visible(qtbot, tmp_path):
    library, _, _ = stored(tmp_path)
    dialog = RelocateDirectoryDialog(library)
    qtbot.addWidget(dialog)
    dialog._finished(PermissionError("目录无读取权限"))
    assert "目录无读取权限" in dialog.notice.label.text()
    assert not dialog.confirm_button.isEnabled()


def test_check_updates_rows_without_loading_the_whole_library(workspace, qtbot, tmp_path, monkeypatch):
    library, _, outcome = stored(tmp_path)
    page = workspace._library_page
    page.repository = library
    page.refresh()
    page.table.selectRow(0)
    selected = page.selected_ids()
    cell = page.table.item(0, 0)
    monkeypatch.setattr(library, "list_assets", lambda **_: pytest.fail("A file check should retain the loaded list"))
    page.check()
    qtbot.waitUntil(lambda: not page._jobs)
    assert page.table.item(0, 0) is cell
    assert page.selected_ids() == selected
    assert page._assets[0]["files"][0]["checked_at"]
    assert page._last_operation_report["checked"] == 1
    assert Path(outcome.video_path).read_bytes() == b"immutable media bytes"


def test_media_anomaly_and_missing_file_agree_in_row_and_details(workspace, qtbot, tmp_path):
    library, item, outcome = stored(tmp_path)
    outcome.media_verification = {"valid": False, "message": "缺少音轨"}
    library.record_download(item, outcome)
    page = workspace._library_page
    page.repository = library
    page.refresh()
    page.table.setCurrentCell(0, 0)
    assert page.table.item(0, 4).text() == "媒体异常"
    assert page.detail.result_badges[0].text() == "媒体异常"
    Path(outcome.video_path).unlink()
    page.check()
    qtbot.waitUntil(lambda: not page._jobs)
    assert page.table.item(0, 4).text() == page.detail.result_badges[0].text() == "文件缺失"


def test_file_context_menu_preserves_checks_and_names_bulk_scope(workspace, tmp_path, monkeypatch):
    library, item, outcome = stored(tmp_path)
    second = item.model_copy(deep=True)
    second.video_info.cid += 1
    second.video_info.bvid = "BVSECOND"
    other = tmp_path / "other.mp4"
    other.write_bytes(b"other")
    library.record_download(second, outcome.model_copy(update={"video_path": str(other)}))
    page = workspace._library_page
    page.repository = library
    page.refresh()
    page.table.selectRow(0)
    checked = page.selected_ids()
    labels = []
    from PySide6.QtWidgets import QMenu
    class QuietMenu(QMenu):
        def exec(self, *_):
            labels.extend(action.text() for action in self.actions())
    monkeypatch.setattr("bilibili_downloader.gui.widgets.library_page.PopupMenu", QuietMenu)
    page._context_menu(page.table.visualItemRect(page.table.item(1, 0)).center())
    assert page.selected_ids() == checked
    assert page.selection.state.focused == page.table.item(1, 0).data(Qt.UserRole)
    assert "移除所选 1 项记录" in labels


def test_file_model_exposes_unvisited_rows_and_checked_state(qtbot):
    from bilibili_downloader.gui.widgets.file_table import FileTable
    from bilibili_downloader.gui.widgets.selection import TableSelection
    table = FileTable()
    qtbot.addWidget(table)
    table.replace_rows([[f"文件 {n}", "作者", "1080P", "1 B", "待检查", "/目录"] for n in range(10000)], list(range(10000)), ["作品"] * 10000)
    binding = TableSelection(table, paint_only=True)
    binding.reset()
    binding.set_visible(range(10000))
    assert not table._cells
    assert table.model().data(table.model().index(9999, 0)) == "文件 9999"
    binding.select_visible()
    assert table.model().data(table.model().index(9999, 0), Qt.CheckStateRole) == Qt.Checked
    table.model().setData(table.model().index(9999, 0), Qt.Unchecked, Qt.CheckStateRole)
    assert 9999 not in binding.state.selected and len(binding.state.selected) == 9999
    assert len(table._cells) < 10


def test_batch_search_reuses_paths_and_directory_changes_invalidate_them(qtbot, tmp_path):
    dialog = BatchDialog()
    qtbot.addWidget(dialog)
    calls, directory = [], [str(tmp_path / "before")]
    def factory(info):
        calls.append(info.content_identity)
        return DownloadItem(video_info=info, output_dir=directory[0])
    dialog.output_item_factory = factory
    dialog._on_resolved([VideoInfo(bvid=f"BV{n}", cid=n + 1, title=f"课程 {n}") for n in range(20)], [])
    baseline_calls = len(calls)
    dialog.search.setText("课程 1")
    dialog.selection.clear()
    dialog.selection.select_visible()
    assert len(calls) == baseline_calls
    assert len(dialog.get_video_infos()) == 11
    assert "11 个任务" in dialog._selected_label.text()
    directory[0] = str(tmp_path / "after")
    dialog.set_output_summary("1080P", directory[0])
    assert len(calls) == baseline_calls + 20
    assert str(tmp_path / "after") in dialog._path_preview.toolTip()


def test_old_check_results_never_overwrite_a_new_location(tmp_path):
    library, _, outcome = stored(tmp_path)
    asset_id = library.list_assets()[0]["id"]
    media = library.files_for([asset_id])[0]
    destination = tmp_path / "moved.mp4"
    destination.write_bytes(b"new media")
    result = library.check_files([asset_id], progress=lambda *_: library.relocate(media["id"], destination))
    assert result["skipped_changed"] == 1
    updated = library.files_for([asset_id])[0]
    assert updated["path"] == absolute_path(destination) and updated["state"] == "unchecked"
    assert updated["signature"] is None
    assert Path(outcome.video_path).read_bytes() == b"immutable media bytes"


def test_inventory_preview_distinguishes_media_from_missing_companions(tmp_path):
    library, item, _ = stored(tmp_path)
    requested = item.model_copy(update={"download_subtitle": True})
    runner = InventoryMatchRunner(library, [[item], [requested]])
    results = []
    runner.signals.finished.connect(results.extend)
    runner.run()
    assert results[0].saved
    assert results[1].counts()["missing_attachments"] == 1
    assert "待补附件" in results[1].label


def test_stage_display_uses_stage_progress_and_separates_pending_attachments(workspace):
    table = workspace._download_list
    item = DownloadItem(video_info=VideoInfo(bvid="BVstage", title="阶段"))
    key = table.add_item(item)
    table.update_phase(key, DownloadPhase("mux", "封装媒体", .25))
    table.update_progress(key, .85, "正在封装媒体", TaskStatus.MERGING)
    bar = table._progress_at(table._row_for(key))
    assert bar.value() == 25 and "25%" in bar.property("stageCaption")
    table.mark_done(key, DownloadOutcome(video_path="/demo/video.mp4", missing_artifacts=["subtitle"]))
    assert bar.property("stageCaption") == "媒体已保存"


def test_late_library_read_after_widget_deletion_is_ignored(qapp, qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool

    from bilibili_downloader.gui.widgets.library_page import LibraryPage
    library, _, _ = stored(tmp_path)
    original = library.list_assets
    release = threading.Event()
    entered = threading.Event()
    def delayed():
        result = original()
        entered.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(library, 'list_assets', delayed)
    pool = QThreadPool()
    page = LibraryPage(pool=pool)
    page.set_repository(library)
    qtbot.waitUntil(entered.is_set)
    page.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    release.set()
    assert pool.waitForDone(2000)
    qapp.processEvents()


def test_stale_library_load_preserves_newer_rows_and_selection(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QThreadPool

    from bilibili_downloader.gui.widgets.library_page import LibraryPage
    library, item, _ = stored(tmp_path)
    snapshot = library.list_assets()
    release = threading.Event()
    entered = threading.Event()
    def delayed():
        entered.set()
        assert release.wait(5)
        return snapshot
    pool = QThreadPool()
    page = LibraryPage(pool=pool)
    qtbot.addWidget(page)
    page.repository = library
    monkeypatch.setattr(library, 'list_assets', delayed)
    page.refresh_async()
    qtbot.waitUntil(entered.is_set)
    monkeypatch.undo()
    second = tmp_path / 'second.mp4'
    second.write_bytes(b'media')
    library.record_download(item, DownloadOutcome(video_path=str(second)))
    page.refresh()
    page.select_visible()
    selected = page.selected_ids()
    release.set()
    qtbot.waitUntil(lambda: not page._read_jobs)
    assert page.table.rowCount() == 2 and page.selected_ids() == selected


def test_file_check_exposes_missing_attachment_in_context(workspace, qtbot, tmp_path):
    library, item, outcome = stored(tmp_path)
    subtitle = tmp_path / 'lesson.srt'
    subtitle.write_bytes(b'subtitle')
    outcome.subtitle_paths = [str(subtitle)]
    library.record_download(item, outcome)
    subtitle.unlink()
    page = workspace._library_page
    page.set_repository(library)
    page.refresh()
    page.table.selectRow(0)
    page.check()
    qtbot.waitUntil(lambda: not page._jobs)
    assert '待补全' in page.detail.result_badges[2].text()
    assert page.detail.secondary_action.text() == '补全附件…'
    assert 'subtitle' in page._presented_outcome(page._assets[0]).missing_artifacts


@pytest.mark.parametrize("accepted", [False, True])
def test_auth_recovery_retries_only_after_accepted_login(workspace, monkeypatch, accepted):
    retries = []
    monkeypatch.setattr(workspace, "_on_login_triggered", lambda: accepted)
    monkeypatch.setattr(workspace, "_on_retry_download", retries.append)
    workspace._recover_download(123, "authentication")
    assert retries == ([123] if accepted else [])


def test_storage_recovery_changes_only_the_explicit_task_and_retries(workspace, monkeypatch, tmp_path):
    from types import SimpleNamespace
    ids = []
    for n in range(2):
        item = DownloadItem(video_info=VideoInfo(bvid=f"BV{n}"), output_dir=str(tmp_path / "old"))
        identity = workspace._task_repository.add(item, TaskStatus.FAILED)
        workspace._download_list.add_item(item, download_id=identity, status=TaskStatus.FAILED)
        ids.append(identity)
    retries = []
    monkeypatch.setattr(workspace, "_on_retry_download", retries.append)
    monkeypatch.setattr("bilibili_downloader.gui.dialogs.file_picker.file_picker", lambda _: SimpleNamespace(directory=lambda _title, _old, callback: callback(str(tmp_path / "new"))))
    workspace._recover_download(ids[0], "storage")
    assert retries == [ids[0]]
    assert workspace._task_repository.get(ids[0]).item.output_dir == str(tmp_path / "new")
    assert workspace._task_repository.get(ids[1]).item.output_dir == str(tmp_path / "old")
