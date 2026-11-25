"""Browsing and thumbnails use the same local download inventory."""

import json
import threading

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDesktopServices, QImage
from PySide6.QtWidgets import QAbstractItemView

from bilibili_downloader.core.library import LibraryRepository, absolute_path
from bilibili_downloader.core.models import (
    ContentKind,
    DownloadItem,
    DownloadOutcome,
    OutputMode,
    VideoInfo,
    VideoPage,
)
from bilibili_downloader.gui.widgets import library_thumbnails
from bilibili_downloader.gui.widgets.library_page import LibraryPage
from bilibili_downloader.gui.widgets.library_thumbnails import (
    ThumbnailFile,
    ThumbnailSource,
)
from bilibili_downloader.utils.config import ConfigManager
from tests.test_workspaces import workspace as workspace


def _register(repo, root, name, info, *, size=12, cover=None, audio=False, date=None):
    media = root / name
    media.write_bytes(b"x" * size)
    item = DownloadItem(video_info=info, output_mode=OutputMode.AUDIO if audio else OutputMode.VIDEO)
    outcome = DownloadOutcome(video_path=str(media), actual_quality=80, actual_video_codec=12, cover_path=cover)
    return repo.register(item, outcome, created_at=date)


def _page(qtbot, tmp_path):
    page = LibraryPage()
    qtbot.addWidget(page)
    page.repository = LibraryRepository(tmp_path / "inventory.sqlite3")
    page.resize(730, 520)
    return page


def test_search_and_file_selection_survive_view_switches(qtbot, tmp_path, monkeypatch):
    page = _page(qtbot, tmp_path)
    repo = page.repository
    parts = [VideoPage(cid=1, page=1, part="开头"), VideoPage(cid=2, page=2, part="细节")]
    work = VideoInfo(bvid="BV1sample", aid=22, title="城市徒步", author="甲", collection_title="散步合集", pages=parts)
    first = _register(repo, tmp_path, "开头.mp4", work.for_page(parts[0]).model_copy(
        update={"collection_title": "城市徒步"},
    ), size=24, date="2024-01-01")
    second = _register(repo, tmp_path, "第二段 演示.mp4", work.for_page(parts[1]), date="2024-02-01")
    variant = _register(repo, tmp_path, "第二段 纯音频.m4a", work.for_page(parts[1]), audio=True)
    season = VideoInfo(content_kind=ContentKind.BANGUMI_EPISODE, series_title="猫咪", season_title="春季", season_id=4)
    later = _register(repo, tmp_path, "两只.mp4", season.model_copy(update={
        "episode_id": 6, "cid": 6, "episode_index": 2, "episode_number": "第2话", "episode_title": "两只猫",
    }))
    page.refresh()
    page.show()
    assert page.browser.currentWidget() is page.grid
    assert list(page.view_buttons) == ["grid", "list"]
    page.select_visible()
    assert set(page.selected_ids()) == {first, second, variant, later}
    page._clear_selection()
    query = "Ｐ２ 散步合集 av22"
    page.search.setText(query)
    assert set(page.visible_ids()) == {second, variant}
    page.grid.setCurrentIndex(page.grid.model().index_for(second))
    qtbot.keyClick(page.grid, Qt.Key_Space)
    assert page.selected_ids() == [second]

    page.set_view_mode("list")
    assert page.search.text() == query
    assert page.table.currentIndex().data(Qt.UserRole) == second
    assert page.table.currentIndex().data(Qt.CheckStateRole) == Qt.Checked
    index = page.table.currentIndex()
    expected_media = absolute_path(tmp_path / "第二段 演示.mp4")
    assert index.data().splitlines() == ["002 - 细节 · 城市徒步", "甲 · 散步合集"]
    assert expected_media == absolute_path(index.data(Qt.ToolTipRole).splitlines()[-1])
    assert "第二段 演示.mp4" not in index.data()
    assert page.table.item(page._table_rows[variant], 1).text().startswith("仅音频")
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        lambda url: opened.append(absolute_path(url.toLocalFile())) or True)
    qtbot.keyClick(page.table, Qt.Key_Return)
    assert opened == [expected_media]
    position = page.table.visualRect(index).center()
    qtbot.mouseClick(page.table.viewport(), Qt.LeftButton, pos=position)
    qtbot.mouseDClick(page.table.viewport(), Qt.LeftButton, pos=position)
    assert opened == [expected_media] * 2
    page.search.setText("ep6 春季 两只猫")
    assert page.visible_ids() == [later]
    assert page.table.item(page._table_rows[later], 0).text().splitlines() == ["第2话 · 两只猫", "春季"]
    assert "筛选外 1 项" in page.selection_bar.summary.text()
    page.selection_bar.review_button.click()
    assert page.visible_ids() == [second]
    page.selection_bar.review_button.click()
    page.clear_filters()
    page.sort.setCurrentIndex(page.sort.findData("size"))
    assert page.table.item(0, 0).data(Qt.UserRole) == first
    assert page.table.item(0, 0).text().splitlines() == ["001 - 开头 · 城市徒步", "甲"]
    assert page.selected_ids() == [second]
    page.search.setText(str(tmp_path / "第二段 演示.mp4"))
    assert page.visible_ids() == [second]
    page.set_view_mode("grid")
    assert page.sort_mode == "size" and page.selected_ids() == [second]
    assert page.grid.currentIndex().data(Qt.UserRole) == second


def test_download_view_and_sort_preferences_are_saved(workspace, qtbot):
    page = workspace._library_page
    assert (page.view_mode, page.sort_mode) == ("grid", "recent")
    page.view_buttons["list"].click()
    page.sort.setCurrentIndex(page.sort.findData("title"))
    saved = ConfigManager(workspace._config.data_dir / "config.json").load()
    reopened = LibraryPage(view_mode=saved.library_view_mode, sort_mode=saved.library_sort_mode)
    qtbot.addWidget(reopened)
    assert reopened.browser.currentWidget() is reopened.table
    assert reopened.sort_mode == "title"


@pytest.mark.parametrize(("stored", "expected"), [(None, "grid"), ("works", "grid"), ("invalid", "grid"), ("grid", "grid")])
def test_library_view_preferences_migrate_on_load(tmp_path, stored, expected):
    config_path = tmp_path / "config.json"
    data = {"library_sort_mode": "size"}
    if stored is not None:
        data["library_view_mode"] = stored
    config_path.write_text(json.dumps(data))
    saved = ConfigManager(config_path).load()
    assert (saved.library_view_mode, saved.library_sort_mode) == (expected, "size")


def test_local_cover_revalidates_and_falls_back_to_video(qtbot, tmp_path, monkeypatch):
    cover = tmp_path / "cover.png"
    image = QImage(18, 9, QImage.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(cover))
    media = tmp_path / "video.mp4"
    media.write_bytes(b"local media")
    calls = []
    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.FFmpegManager.find_executable", lambda _: tmp_path / "ffmpeg")
    monkeypatch.setattr("bilibili_downloader.core.ffmpeg.FFmpegManager.thumbnail_frame",
                        lambda path, *_: calls.append(path) or b"")
    source = ThumbnailSource(ThumbnailFile(str(cover), "available", None),
                             ThumbnailFile(str(media), "available", None), 3, None)
    first = library_thumbnails._read_thumbnail(source, None)
    assert first.image.pixelColor(0, 0) == QColor("red")
    assert not calls
    image.fill(QColor("blue"))
    replacement = tmp_path / "replacement.png"
    assert image.save(str(replacement))
    replacement.replace(cover)
    updated = library_thumbnails._read_thumbnail(source, first)
    assert updated.image.pixelColor(0, 0) == QColor("blue")
    cover.write_bytes(b"broken cover")
    assert library_thumbnails._read_thumbnail(source, updated).image.isNull()
    assert calls == [media]
    assert ThumbnailFile.from_entry({"state": "inaccessible", "path": str(media)}) is None


@pytest.mark.parametrize("mode", ["grid", "list"])
def test_views_schedule_only_visible_media_and_drop_stale_results(qtbot, tmp_path, monkeypatch, mode):
    page = _page(qtbot, tmp_path)
    started = []
    release = threading.Event()

    def read(source, _previous):
        started.append(source.video.path)
        release.wait(5)
        return library_thumbnails._Thumbnail((), QImage(8, 4, QImage.Format_RGB32))

    monkeypatch.setattr(library_thumbnails, "_read_thumbnail", read)
    for number in range(40):
        _register(page.repository, tmp_path, f"Clip {number}.mp4",
                  VideoInfo(bvid=f"BVclip{number}", cid=number + 1, title=f"片段 {number}"))
    page.refresh()
    page.set_view_mode(mode)
    page.show()
    try:
        qtbot.waitUntil(lambda: len(started) == 2)
        view = page.browser.currentWidget()
        model = view.model()
        first_screen = {
            str(page._records[model.index(row, 0).data(Qt.UserRole)].path)
            for row in range(model.rowCount())
            if view.viewport().rect().intersects(view.visualRect(model.index(row, 0)))
        }
        assert set(started).issubset(first_screen)
        assert len(first_screen) < model.rowCount()
        view.scrollTo(model.index(39, 0), QAbstractItemView.PositionAtBottom)
        qtbot.waitUntil(lambda: view.verticalScrollBar().value() > 0)
        scroll = view.verticalScrollBar().value()
        page.set_view_mode("list" if mode == "grid" else "grid")
        assert len(page._thumbnails._active) == 2
        page.search.setText("no matching files")
        release.set()
        qtbot.waitUntil(lambda: not page._thumbnails._active)
        assert len(started) == 2
        assert not page._thumbnails._cache
        page.search.clear()
        page.set_view_mode(mode)
        qtbot.waitUntil(lambda: view.verticalScrollBar().value() == scroll)
        qtbot.waitUntil(lambda: len(started) > 2)
        assert all(path not in first_screen for path in started[2:])
    finally:
        release.set()


def test_grid_and_list_share_a_local_cover(qtbot, tmp_path, monkeypatch):
    page = _page(qtbot, tmp_path)
    image = QImage(64, 36, QImage.Format_RGB32)
    image.fill(QColor("green"))
    cover = str(tmp_path / "cover.png")
    assert image.save(cover)
    asset_id = _register(page.repository, tmp_path, "clip.mp4", VideoInfo(bvid="BVcover", cid=1), cover=cover)
    seen = []
    original = library_thumbnails._read_thumbnail

    def read(source, previous):
        result = original(source, previous)
        seen.append((previous, result))
        return result

    monkeypatch.setattr(library_thumbnails, "_read_thumbnail", read)
    page.refresh()
    page.show()
    source = page._thumbnail_source(page._records[asset_id])
    qtbot.waitUntil(lambda: not page._thumbnails.image(source).isNull())
    thumbnail = page._thumbnails._cache[source]
    page.set_view_mode("list")
    assert page.table.model().index(0, 0).data() == "clip.mp4"
    assert page._thumbnails._cache[source] is thumbnail
    qtbot.waitUntil(lambda: source in page._thumbnails._validated)
    assert seen == [(None, thumbnail), (thumbnail, thumbnail)]
