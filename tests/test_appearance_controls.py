"""Centered identity and shared, reversible glass appearance controls."""

import io
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QLabel, QLineEdit, QPushButton

from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.settings_sections import SettingsSection
from bilibili_downloader.gui.widgets.background_effects import GlassBlurControl
from bilibili_downloader.gui.widgets.components import AccountButton
from bilibili_downloader.utils.config import ConfigManager
from tests.test_ui_polish import flush
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_avatar_and_name_are_centered_as_one_group(qapp, qtbot, theme_id, dark):
    theme = ThemeManager(qapp, theme_id, mode="dark" if dark else "light")
    button = AccountButton()
    qtbot.addWidget(button)
    button.setProperty("signedIn", True)
    button.full_text = "演示用户"
    button.setText(button.full_text)
    avatar = io.BytesIO()
    Image.new("RGB", (96, 96), (255, 0, 255)).save(avatar, format="PNG")
    button.set_avatar(avatar.getvalue())
    button.resize(176, 38)
    button.show()
    flush()

    def avatar_left():
        pixels = button.grab().toImage()
        dpr = pixels.devicePixelRatio()
        y = pixels.height() // 2
        positions = [x for x in range(pixels.width()) if (lambda c: c.red() > 220 and c.green() < 30 and c.blue() > 220)(pixels.pixelColor(x, y))]
        assert positions
        return min(positions) / dpr

    width = button.iconSize().width() + 4 + button.fontMetrics().horizontalAdvance(button.text())
    assert abs(avatar_left() - (button.width() - width) / 2) <= 4
    button.set_compact(True)
    button.resize(46, 38)
    flush()
    assert not button.text()
    assert abs(avatar_left() - (button.width() - button.iconSize().width()) / 2) <= 2
    theme.deleteLater()


@pytest.mark.parametrize("platform", ["darwin", "win32", "linux"])
def test_settings_have_five_useful_sections_and_no_window_explanations(qtbot, platform):
    panel = SettingsDialog(AppSettings(), desktop_platform=platform)
    qtbot.addWidget(panel)
    assert [panel.tabs.tabText(i) for i in range(panel.tabs.count())] == ["下载", "直播", "外观", "工具与存储", "关于与更新"]
    assert panel.current_section == SettingsSection.DOWNLOAD
    texts = [label.text() for label in panel.findChildren(QLabel)]
    assert not any("窗口与后台运行" in text or "点击红色关闭按钮" in text or "点击 Dock 图标" in text for text in texts)
    if platform == "win32":
        panel.show_section(SettingsSection.APPEARANCE)
        assert panel._controls["windows_close_action"].parentWidget().isVisibleTo(panel.tabs.currentWidget())


@pytest.mark.parametrize("value,expected", [(None,18), (-1,18), (41,18), ("24",18), (True,18), (4.5,18), (0,0), (40,40)])
def test_blur_config_compatibility(value, expected, tmp_path):
    settings = AppSettings(appearance={"glass_blur":value,"theme":"bilibili_blue"})
    config = ConfigManager(tmp_path / "config.json")
    config.save(settings)
    restored = ConfigManager(tmp_path / "config.json").load()
    assert restored.appearance.glass_blur == expected
    assert restored.appearance.theme == "bilibili_blue"
    assert AppSettings(appearance={}).appearance.glass_blur == 18


@pytest.mark.parametrize("accepted", [False, True])
@pytest.mark.parametrize("restore_default", [False, True])
def test_gallery_only_previews_appearance_blur_and_returns_background_drafts(workspace, qtbot, monkeypatch, accepted, restore_default):
    panel = workspace._settings_page
    panel._glass_blur.setValue(5)
    panel._path_template.setText("edited/{title}")
    assert all(picker.glass_blur == 5 for picker in panel._background_pickers.values())
    assert panel._settings.appearance.glass_blur == 18

    def inspect(dialog):
        assert dialog.effects.preview.glass_blur == 5
        assert not dialog.findChildren(GlassBlurControl)
        assert not any("模糊" in label.text() for label in dialog.findChildren(QLabel))
        dialog.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
        qtbot.waitUntil(lambda: not dialog.busy)
        dialog.resize(720, 520)
        dialog._set_compact_view("preview")
        dialog.show()
        flush()
        effects = dialog.effects
        preview = effects.preview.geometry()
        visibility = QRect(effects.slider.mapTo(effects, QPoint()), effects.slider.size())
        reset = QRect(effects.reset.mapTo(effects, QPoint()), effects.reset.size())
        assert preview.bottom() < visibility.top()
        assert visibility.right() < reset.left()
        assert effects.rect().contains(visibility) and effects.rect().contains(reset)
        assert dialog.rect().contains(QRect(dialog.buttons.mapTo(dialog, QPoint()), dialog.buttons.size()))
        effects.slider.setValue(67)
        effects.dark_button.click()
        effects.slider.setValue(71)
        effects.reset.click()
        assert dialog.visibility.light == 67 and dialog.visibility.dark is None
        effects.original_button.click()
        effects.page_button.click()
        if restore_default:
            dialog.restore_default()
        assert effects.preview.glass_blur == 5
        assert panel._glass_blur.value() == 5
        dialog.hide()
        return QDialog.Accepted if accepted else QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect)
    panel._background_pickers["download"]._choose()
    picker = panel._background_pickers["download"]
    assert picker.reference == (BUILTIN_BACKGROUNDS[0].reference if accepted and not restore_default else "")
    assert picker.visibility.light == (67 if accepted and not restore_default else None)
    assert panel._glass_blur.value() == 5
    assert all(picker.glass_blur == 5 for picker in panel._background_pickers.values())
    assert workspace._config.load().appearance.glass_blur == 18
    assert panel._path_template.text() == "edited/{title}"
    panel._reset_btn.click()
    assert panel._glass_blur.value() == 18 and not panel.dirty


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("size", [(900, 640), (1120, 760), (1320, 860)])
def test_download_and_live_directories_share_picker_visuals_and_drafts(workspace, qapp, qtbot, monkeypatch, tmp_path, theme_id, dark, size):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: pytest.fail("synchronous native picker"))
    theme = ThemeManager(qapp, theme_id, mode="dark" if dark else "light")
    panel = workspace._settings_page
    workspace.resize(*size)
    workspace.show()
    fills, heights = [], []
    for key, section in (("output_dir", SettingsSection.DOWNLOAD), ("live.output_dir", SettingsSection.LIVE)):
        workspace._show_settings_tab(section)
        flush()
        entry = panel._controls[key]
        browse = panel._field_rows[key].findChild(QPushButton)
        assert entry.isReadOnly() and entry.isEnabled()
        assert entry.isVisible() and browse.isVisible()
        assert entry.cursorPosition() == 0
        image = entry.grab().toImage()
        dpr = image.devicePixelRatio()
        fills.append(image.pixelColor(round(6 * dpr), image.height() // 2).name())
        heights.append(entry.height())
        original = entry.text()
        entry.selectAll()
        assert entry.selectedText() == original
        qtbot.keyClicks(entry, "must-not-edit")
        assert entry.text() == original
        browse.click()
        picker = panel._file_picker
        assert picker.dialog.isVisible() and picker.dialog.parentWidget() is workspace
        picker.dialog.reject()
        assert entry.text() == original
        chosen = str(tmp_path / section.value / "new directory")
        Path(chosen).mkdir(parents=True)
        browse.click()
        picker.dialog.findChild(QLineEdit, "fileNameEdit").setText(chosen)
        picker.dialog.accept()
        qtbot.waitUntil(lambda: picker.dialog is None)
        assert entry.text() == chosen and entry.toolTip() == chosen
        assert entry.cursorPosition() == 0 and panel.dirty
        settings = workspace._config.load()
        assert (settings.output_dir if key == "output_dir" else settings.live.output_dir) == original
    assert fills[0] == fills[1] and heights[0] == heights[1]
    assert not panel._controls["ffmpeg_path"].isReadOnly()
    assert workspace._save_settings()
    saved = workspace._config.load()
    assert saved.output_dir == panel._output_dir.text()
    assert saved.live.output_dir == panel._live_directory.text()
    panel._output_dir.setText("/discarded-draft")
    panel._reset_btn.click()
    assert panel._output_dir.text() == saved.output_dir and not panel.dirty
    theme.deleteLater()


def test_blur_failure_retry_runtime_and_immediate_mode_preserve_drafts(workspace, monkeypatch):
    panel = workspace._settings_page
    panel._glass_blur.slider.setFocus()
    panel._glass_blur.slider.setValue(32)
    assert panel.dirty
    workspace._set_appearance_mode("dark")
    assert panel._glass_blur.value() == 32
    assert workspace._config.load().appearance.glass_blur == 18
    save = workspace._config.save
    monkeypatch.setattr(workspace._config, "save", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    assert not workspace._save_settings()
    assert panel._glass_blur.value() == 32 and panel.dirty
    assert workspace._workspace_pages._glass_blur == 18
    monkeypatch.setattr(workspace._config, "save", save)
    assert workspace._save_settings()
    assert workspace._workspace_pages._glass_blur == 32
    assert ConfigManager(workspace._config.data_dir / "config.json").load().appearance.glass_blur == 32
    panel._glass_blur.setValue(0)
    panel._reset_btn.click()
    assert panel._glass_blur.value() == 32
    assert panel._mode_buttons.checkedButton().text() == "夜间"


def test_blur_slider_changes_preview_without_saving_or_blurring_text(workspace, qtbot):
    panel = workspace._settings_page
    workspace._show_settings_tab(SettingsSection.APPEARANCE)
    workspace.show()
    flush()
    panel._glass_blur.setValue(0)
    panel._glass_preview.grab()
    first = panel._glass_preview._glass.image.cacheKey()
    qtbot.keyClick(panel._glass_blur.slider, Qt.Key_End)
    assert panel._glass_blur.value() == 40
    panel._glass_preview.grab()
    assert panel._glass_preview._glass.image.cacheKey() != first
    assert panel._glass_blur.display.text() == "40 px"
    assert workspace._settings.appearance.glass_blur == 18
    assert panel._glass_preview.findChild(QLabel).graphicsEffect() is None
