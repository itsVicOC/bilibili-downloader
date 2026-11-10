"""Shared settings, truthful feedback and disclosure behavior after the redesign."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    OutputMode,
    VideoInfo,
)
from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.resources.theme import ThemeManager
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(8):
        QApplication.processEvents()


def test_shared_settings_preserve_both_sources_and_audio_roundtrip(workspace):
    window = workspace
    settings = window._settings.model_dump()
    window.show()
    window._configuration.edit.click()
    window._url_input.setText("BVsingle")
    window._on_resolve_success(VideoInfo(bvid="BVsingle", cid=1), [], [], True)
    window._aspect_combo.setCurrentIndex(1)
    window._strict_match_check.setChecked(True)
    window._configuration.advanced.set_expanded(False)
    batch = window._batch_page
    batch._url_text.setPlainText("BVbatch")
    batch._on_resolved([VideoInfo(bvid="BVbatch", cid=2)], [])
    window._download_tabs.setCurrentIndex(1)
    window._show_output_options()
    flush()
    assert window._download_tabs.currentIndex() == 1
    assert window._configuration.content.isVisible()
    assert window._parts_row.isHidden() and window._batch_parts.isVisible()
    assert "4:3" in window._configuration.advanced_summary._full_text
    assert "严格匹配" in window._configuration.advanced_summary._full_text
    item = window._make_download_item(batch.get_video_infos()[0])
    assert item.display_aspect_ratio == "4:3" and item.strict_match
    audio = window._audio_combo
    window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.AUDIO))
    flush()
    assert audio.isVisible() and audio.parentWidget() is window._audio_common_host
    assert window._aspect_row.isHidden() and window._codec_row.isHidden()
    assert "4:3" not in window._configuration.advanced_summary._full_text
    assert window._make_download_item(batch.get_video_infos()[0]).display_aspect_ratio == "original"
    window._download_tabs.setCurrentIndex(0)
    window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.VIDEO))
    flush()
    assert audio is window._audio_combo and audio.parentWidget() is window._audio_advanced_host
    assert window._aspect_combo.currentData() == "4:3"
    assert window._strict_match_check.isChecked()
    assert window._url_input.text() == "BVsingle" and batch._url_text.toPlainText() == "BVbatch"
    assert window._settings.model_dump() == settings


def test_advanced_error_opens_and_scrolls_to_the_actual_field(workspace):
    window = workspace
    window.resize(900, 640)
    window.show()
    window._configuration.reveal_error(window._codec_row, "请选择可用的视频编码。")
    flush()
    field = window._codec_row
    assert window._configuration.content.isVisible()
    assert window._configuration.advanced.toggle.isChecked()
    assert field.error.isVisible() and field.control.property("invalid")
    assert field.visibleRegion().boundingRect().contains(field.rect())
    assert field.control.focusPolicy() != Qt.NoFocus


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("name,row", [
    ("_codec_combo", "_codec_row"),
    ("_audio_combo", "_advanced_audio_row"),
    ("_aspect_combo", "_aspect_row"),
    ("_match_policy", "_match_policy_row"),
])
def test_enqueue_reveals_invalid_advanced_fields_and_recovers(workspace, monkeypatch, batch, name, row):
    window = workspace
    info = VideoInfo(bvid="BVvalidate", cid=1)
    window._url_input.setText(info.bvid)
    window._on_resolve_success(info, [], [], True)
    if batch:
        window._batch_page._on_resolved([info], [])
        window._download_tabs.setCurrentIndex(1)
    window.resize(900, 640)
    window.show()
    confirmations, queued = [], []
    monkeypatch.setattr(window, "_confirm_copyright_acknowledgement", lambda: confirmations.append(True) or True)
    monkeypatch.setattr(window, "_enqueue_download", lambda item: queued.append(item) or True)
    control, field = getattr(window, name), getattr(window, row)
    control.setCurrentIndex(-1)
    window._configuration.advanced.set_expanded(False)
    enqueue = (lambda: window._enqueue_batch_from_page([info])) if batch else window._on_download_clicked
    enqueue()
    flush()
    assert not queued and not confirmations
    assert window._configuration.advanced.toggle.isChecked()
    assert field.error.isVisible() and control.property("invalid")
    assert window.focusWidget() is control
    assert field.visibleRegion().boundingRect().contains(field.rect())
    control.setCurrentIndex(0)
    assert not field.error.isVisible() and not control.property("invalid")
    enqueue()
    assert len(queued) == len(confirmations) == 1


@pytest.mark.parametrize("batch", [False, True])
def test_audio_enqueue_validates_audio_and_ignores_inactive_video_fields(workspace, monkeypatch, batch):
    window = workspace
    info = VideoInfo(bvid="BVaudio", cid=1)
    window._url_input.setText(info.bvid)
    window._on_resolve_success(info, [], [], True)
    if batch:
        window._batch_page._on_resolved([info], [])
        window._download_tabs.setCurrentIndex(1)
    window._output_mode_combo.setCurrentIndex(window._output_mode_combo.findData(OutputMode.AUDIO))
    window._quality_combo.setCurrentIndex(-1)
    window._codec_combo.setCurrentIndex(-1)
    window._aspect_combo.setCurrentIndex(-1)
    window.show()
    queued = []
    monkeypatch.setattr(window, "_confirm_copyright_acknowledgement", lambda: True)
    monkeypatch.setattr(window, "_enqueue_download", lambda item: queued.append(item) or True)
    enqueue = (lambda: window._enqueue_batch_from_page([info])) if batch else window._on_download_clicked
    window._audio_combo.setCurrentIndex(-1)
    enqueue()
    flush()
    assert not queued
    assert window._audio_row.error.isVisible() and window._audio_combo.property("invalid")
    assert window.focusWidget() is window._audio_combo
    window._audio_combo.setCurrentIndex(0)
    enqueue()
    assert len(queued) == 1 and queued[0].output_mode == OutputMode.AUDIO


def test_empty_source_does_not_reserve_height_for_hidden_batch_results(workspace):
    window = workspace
    window.resize(900, 640)
    window.show()
    window._download_tabs.setCurrentIndex(1)
    window._batch_page._url_text.setPlainText("BVbatch")
    window._batch_page._on_resolved([VideoInfo(bvid=f"BV{n}", cid=n + 1) for n in range(130)], [])
    window._download_tabs.setCurrentIndex(0)
    flush()
    summary = window._configuration.summary
    assert summary.isVisible() and summary.visibleRegion().boundingRect().contains(summary.rect())
    assert window._workspace_scroll.verticalScrollBar().maximum() == 0


def test_resolve_clears_an_error_after_repopulating_available_specs(workspace):
    window = workspace
    info = VideoInfo(bvid="BVspecs", cid=1)
    window._url_input.setText(info.bvid)
    window._on_resolve_success(info, [], [], True)
    window._codec_combo.setCurrentIndex(-1)
    window._on_download_clicked()
    assert window._codec_combo.property("invalid")
    window._on_resolve_success(info, [], [], True)
    assert window._codec_combo.currentData() is not None
    assert not window._codec_combo.property("invalid")
    assert window._codec_row.error.text() == ""
    assert window._codec_row._error_row.isHidden()


@pytest.mark.parametrize("scale", [1.25, 1.5])
def test_larger_fonts_keep_the_shared_rail_and_option_labels_readable(workspace, qapp, scale):
    manager = ThemeManager(qapp, "star_trail", "light")
    qapp.setStyleSheet(load_stylesheet(False, manager._font_scale * scale, manager._font_family))
    window = workspace
    window.resize(1320, 860)
    window.show()
    window._on_resolve_success(VideoInfo(bvid="BVfont", cid=1), [], [], True)
    flush()
    for card in (window._danmaku_check, window._subtitle_check, window._cover_check, window._metadata_check):
        window._workspace_scroll.ensureWidgetVisible(card, 0, 8)
        flush()
        assert card.width() >= card.minimumSizeHint().width()
        assert card.visibleRegion().boundingRect().contains(card.rect())
    assert window._workspace_scroll.horizontalScrollBar().maximum() == 0
    assert window._download_btn.visibleRegion().boundingRect().contains(window._download_btn.rect())
    manager.deleteLater()


@pytest.mark.parametrize("changes,warm,detail", [
    ({}, True, "已存好，留着慢慢看。"),
    ({"warnings": ["封面不可用"]}, False, "1 条提示"),
    ({"spec_warnings": ["画质回退"]}, False, "1 条提示"),
    ({"missing_artifacts": ["subtitle"]}, False, "附件待补全"),
    ({"media_verification": {"valid": False}}, False, "媒体核验异常"),
])
def test_warm_feedback_only_follows_an_unqualified_saved_result(workspace, monkeypatch, tmp_path, changes, warm, detail):
    window = workspace
    item = DownloadItem(video_info=VideoInfo(bvid="BVsaved", cid=1))
    task_id = window._task_repository.add(item)
    window._download_list.add_item(item, download_id=task_id)
    media = tmp_path / "saved.mp4"
    media.write_bytes(b"offline demo")
    messages = []
    monkeypatch.setattr(window, "_download_feedback", lambda _, text: messages.append(text))
    window._on_download_finished(task_id, DownloadOutcome(video_path=str(media), **changes))
    assert detail in messages[-1]
    assert ("留着慢慢看" in messages[-1]) is warm
