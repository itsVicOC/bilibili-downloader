"""Appearance persistence, bounded imports, and transactional GUI drafts."""

import io
import json
from dataclasses import replace

import pytest
from PIL import Image
from PySide6.QtCore import Qt

from bilibili_downloader.core import appearance
from bilibili_downloader.core.appearance import BackgroundStore, prepare_background
from bilibili_downloader.core.models import AppSettings, BackgroundVisibility
from bilibili_downloader.gui.dialogs.settings_dialog import SettingsDialog
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.background_picker import BackgroundPicker
from bilibili_downloader.utils.config import ConfigManager
from tests.test_workspaces import workspace as workspace


@pytest.fixture(autouse=True)
def restore_app_theme(qapp):
    previous = (
        qapp.font(),
        qapp.palette(),
        qapp.styleSheet(),
        qapp.property("darkTheme"),
        qapp.property("colorTheme"),
    )
    yield
    qapp.setFont(previous[0])
    qapp.setPalette(previous[1])
    qapp.setProperty("darkTheme", previous[3])
    qapp.setProperty("colorTheme", previous[4])
    qapp.setStyleSheet(previous[2])


def make_image(path, color="blue", size=(320, 180), **kwargs):
    Image.new("RGB", size, color).save(path, **kwargs)
    return path


@pytest.mark.parametrize("invalid", [None, [], "bad", 12])
def test_invalid_appearance_does_not_reset_download_settings(invalid):
    settings = AppSettings(output_dir="/keep", appearance=invalid)
    assert settings.output_dir == "/keep"
    assert settings.appearance.theme == "star_trail"


def test_bad_appearance_fields_fall_back_independently(tmp_path):
    reference = "a" * 64 + ".png"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "output_dir": "/keep",
                "max_concurrent_downloads": 7,
                "appearance": {
                    "theme": {"bad": True},
                    "backgrounds": {
                        "download": "../escape.png",
                        "live": reference,
                        "tasks": None,
                    },
                },
            }
        )
    )
    settings = ConfigManager(path).load()
    assert settings.output_dir == "/keep"
    assert settings.max_concurrent_downloads == 7
    assert settings.appearance.theme == "star_trail"
    assert settings.appearance.backgrounds.download == ""
    assert settings.appearance.backgrounds.live == reference
    assert settings.appearance.backgrounds.tasks == ""
    assert not path.with_suffix(".json.bak").exists()


def test_background_roundtrip_survives_original_deletion_and_sharing(tmp_path):
    source = make_image(tmp_path / "source.jpg")
    image = prepare_background(source)
    store = BackgroundStore(tmp_path)
    store.install(image)
    source.unlink()
    settings = AppSettings(
        appearance={
            "theme": "bilibili_blue",
            "backgrounds": {
                "download": image.reference,
                "live": image.reference,
            },
        }
    )
    ConfigManager(tmp_path / "config.json").save(settings)
    loaded = ConfigManager(tmp_path / "config.json").load()
    assert loaded.appearance == settings.appearance
    store.cleanup([loaded.appearance.backgrounds.live])
    assert store.path(image.reference).read_bytes() == image.png
    store.cleanup([])
    assert store.path(image.reference) is None


def test_import_orients_resizes_and_removes_metadata(tmp_path):
    source = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    make_image(source, size=(4000, 1000), exif=exif)
    image = prepare_background(source)
    with Image.open(io.BytesIO(image.png)) as decoded:
        assert decoded.size == (960, 3840)
        assert not decoded.getexif()
    with Image.open(io.BytesIO(image.preview)) as preview:
        assert preview.width <= 320 and preview.height <= 180


def test_invalid_large_and_animated_imports(tmp_path, monkeypatch):
    path = tmp_path / "bad.png"
    path.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="损坏"):
        prepare_background(path)
    make_image(path)
    monkeypatch.setattr(appearance, "MAX_IMAGE_BYTES", 8)
    with pytest.raises(ValueError, match="20 MiB"):
        prepare_background(path)
    monkeypatch.setattr(appearance, "MAX_IMAGE_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr(appearance, "MAX_IMAGE_PIXELS", 8)
    with pytest.raises(ValueError, match="4000 万"):
        prepare_background(path)
    path = tmp_path / "animated.webp"
    Image.new("RGB", (16, 16), "red").save(
        path,
        save_all=True,
        append_images=[Image.new("RGB", (16, 16), "blue")],
        duration=100,
    )
    with pytest.raises(ValueError, match="动画"):
        prepare_background(path)


def test_store_never_follows_external_references_or_symlinks(tmp_path):
    store = BackgroundStore(tmp_path)
    assert store.path("../outside.png") is None
    outside = make_image(tmp_path / "outside.png")
    image = prepare_background(outside)
    store.directory.mkdir()
    link = store.directory / image.reference
    link.symlink_to(outside)
    assert store.path(image.reference) is None
    store.cleanup([])
    assert outside.exists() and link.is_symlink()
    with pytest.raises(ValueError):
        store.install(replace(image, reference="../escape.png"))


def test_background_picker_decodes_async_and_discards_stale_results(qtbot, tmp_path):
    picker = BackgroundPicker("Download", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    path = make_image(tmp_path / "image.png")
    picker.select_path(path)
    assert picker.busy
    picker.set_reference("")
    qtbot.waitUntil(lambda: not picker._jobs)
    assert picker.reference == "" and picker.prepared is None
    picker.select_path(path)
    qtbot.waitUntil(lambda: not picker.busy)
    assert picker.prepared is not None
    assert "保存" in picker.status.text()
    assert not (tmp_path / "backgrounds").exists()


def test_background_effect_preview_uses_draft_theme_and_isolated_mode(qtbot, monkeypatch, qapp, tmp_path):
    from PySide6.QtWidgets import QDialog

    from bilibili_downloader.gui.widgets.appearance_preview import WorkspacePreview

    picker = BackgroundPicker("下载", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    picker.select_path(make_image(tmp_path / "image.png"))
    qtbot.waitUntil(lambda: not picker.busy)
    picker.set_theme("bilibili_blue")
    previous = (qapp.property("darkTheme"), qapp.property("colorTheme"))
    inspected = []

    def inspect(dialog):
        preview = dialog.findChild(WorkspacePreview)
        assert preview.theme_id == "bilibili_blue"
        (dialog.effects.light_button if preview.is_dark else dialog.effects.dark_button).click()
        assert preview.is_dark == dialog.effects.dark_button.isChecked()
        assert not preview.grab().isNull()
        inspected.append(True)
        return QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect)
    picker.preview.click()
    assert inspected == [True]
    assert (qapp.property("darkTheme"), qapp.property("colorTheme")) == previous
    assert not (tmp_path / "backgrounds").exists()


def test_settings_merge_appearance_per_field_and_discard(qtbot, tmp_path):
    baseline = AppSettings()
    dialog = SettingsDialog(baseline, background_store=BackgroundStore(tmp_path))
    qtbot.addWidget(dialog)
    dialog._theme_combo.setCurrentIndex(1)
    latest = baseline.model_copy(deep=True)
    latest.appearance.backgrounds.live = "b" * 64 + ".png"
    latest.copyright_notice_version = 20
    merged = dialog.merge_into(latest)
    assert merged.appearance.theme == "bilibili_blue"
    assert merged.appearance.backgrounds.live == latest.appearance.backgrounds.live
    assert merged.copyright_notice_version == 20
    dialog.load_settings(latest)
    assert not dialog.dirty
    assert "丢失" in dialog._background_pickers["live"].status.text()
    assert [dialog.tabs.tabText(i) for i in range(5)] == [
        "下载",
        "直播",
        "工具与存储",
        "软件更新",
        "外观",
    ]


def test_save_failure_preserves_background_and_draft(
    workspace, qtbot, tmp_path, monkeypatch
):
    window = workspace
    source = make_image(tmp_path / "old.png", "green")
    old = prepare_background(source)
    window._background_store.install(old)
    window._settings.appearance.backgrounds.download = old.reference
    window._config.save(window._settings)
    window._settings_page.load_settings(window._settings)
    window._refresh_workspace_background()
    picker = window._settings_page._background_pickers["download"]
    picker.select_path(make_image(tmp_path / "new.png", "red"))
    qtbot.waitUntil(lambda: not picker.busy)

    def fail(_settings):
        raise OSError("unwritable")

    monkeypatch.setattr(window._config, "save", fail)
    assert not window._save_settings()
    assert window._settings.appearance.backgrounds.download == old.reference
    assert window._settings_page.dirty
    assert window._workspace_pages.property("customBackground")
    assert window._background_store.path(old.reference) is not None


def test_saved_appearance_applies_without_recreating_workspaces(
    workspace, qtbot, tmp_path
):
    window = workspace
    pages, service = window._workspace_pages, window._live_controller.service
    panel = window._settings_page
    source = make_image(tmp_path / "image.png")
    for picker in panel._background_pickers.values():
        picker.select_path(source)
    qtbot.waitUntil(
        lambda: all(not picker.busy for picker in panel._background_pickers.values())
    )
    panel._theme_combo.setCurrentIndex(1)
    assert not pages.property("customBackground")
    assert window._save_settings()
    assert window._theme_manager.theme_id == "bilibili_blue"
    assert not panel.dirty
    source.unlink()
    for index in range(4):
        window._show_workspace(index)
        assert pages.property("customBackground")
    assert pages is window._workspace_pages
    assert service is window._live_controller.service
    panel._background_pickers["download"].set_reference("")
    assert window._save_settings()
    assert window._settings.appearance.backgrounds.download == ""
    assert len(list(window._background_store.directory.glob("*.png"))) == 1


def test_theme_switch_keeps_system_mode(qapp):
    theme = ThemeManager(qapp)
    try:
        theme._on_color_scheme_changed(Qt.ColorScheme.Dark)
        theme.set_color_theme("bilibili_blue")
        assert theme.is_dark
        theme._on_color_scheme_changed(Qt.ColorScheme.Light)
        assert not theme.is_dark and theme.theme_id == "bilibili_blue"
    finally:
        theme.set_color_theme("star_trail")
        qapp.styleHints().colorSchemeChanged.disconnect(theme._on_color_scheme_changed)
        theme.deleteLater()


def test_each_workspace_uses_its_own_image_and_handles_corruption(workspace, tmp_path):
    window = workspace
    names = ("download", "live", "tasks", "settings")
    colors = ("#123456", "#234567", "#345678", "#456789")
    for name, color in zip(names, colors):
        image = prepare_background(make_image(tmp_path / f"{name}.png", color))
        window._background_store.install(image)
        setattr(window._settings.appearance.backgrounds, name, image.reference)
    window._config.save(window._settings)
    window._settings_page.load_settings(window._settings)
    for index, color in enumerate(colors):
        window._show_workspace(index)
        assert (
            window._workspace_pages._background.toImage().pixelColor(0, 0).name()
            == color
        )
    reference = window._settings.appearance.backgrounds.download
    window._background_store.path(reference).write_bytes(b"broken")
    window._settings_page.load_settings(window._settings)
    window._show_workspace(0)
    assert not window._workspace_pages.property("customBackground")
    assert (
        "丢失或损坏"
        in window._settings_page._background_pickers["download"].status.text()
    )


def test_reselecting_missing_background_can_be_saved(workspace, qtbot, tmp_path):
    window = workspace
    path = make_image(tmp_path / "image.png")
    image = prepare_background(path)
    window._settings.appearance.backgrounds.download = image.reference
    window._settings_page.load_settings(window._settings)
    picker = window._settings_page._background_pickers["download"]
    picker.select_path(path)
    qtbot.waitUntil(lambda: not picker.busy)
    assert window._settings_page.dirty
    assert window._save_settings()
    assert window._background_store.path(image.reference) is not None


def test_visibility_settings_fall_back_per_mode_and_workspace(tmp_path):
    settings = AppSettings(
        output_dir="/keep",
        appearance={
            "theme": "bilibili_blue",
            "background_visibility": {
                "download": {"light": 60, "dark": 101},
                "live": {"light": True, "dark": 35},
                "tasks": "broken",
                "settings": {"light": "70", "dark": -1},
            },
        },
    )
    visibility = settings.appearance.background_visibility
    assert visibility.download == BackgroundVisibility(light=60)
    assert visibility.live == BackgroundVisibility(dark=35)
    assert visibility.tasks == visibility.settings == BackgroundVisibility()
    config = ConfigManager(tmp_path / "config.json")
    config.save(settings)
    assert config.load() == settings
    assert AppSettings(appearance={"background_visibility": []}).output_dir


@pytest.mark.parametrize("accepted", [False, True])
def test_preview_visibility_is_local_until_applied(qtbot, monkeypatch, tmp_path, accepted):
    from PySide6.QtWidgets import QDialog, QPushButton, QSlider

    from bilibili_downloader.gui.widgets.appearance_preview import WorkspacePreview

    picker = BackgroundPicker("下载", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    picker.select_path(make_image(tmp_path / "image.png", size=(1600, 900)))
    qtbot.waitUntil(lambda: not picker.busy)
    baseline = BackgroundVisibility(light=20, dark=30)
    picker.set_visibility(baseline)

    def inspect(dialog):
        preview = dialog.findChild(WorkspacePreview)
        slider = dialog.findChild(QSlider)
        dialog.effects.light_button.setChecked(True)
        assert slider.value() == 20
        assert preview.pixmap.width() == 1600  # Preview uses the processed full image.
        slider.setValue(70)
        dialog.effects.dark_button.setChecked(True)
        assert slider.value() == 30
        slider.setValue(45)
        assert picker.visibility == baseline
        reset = next(b for b in dialog.findChildren(QPushButton) if "当前模式默认" in b.text())
        reset.click()
        assert preview.visibility.dark is None
        dialog.effects.light_button.setChecked(True)
        assert slider.value() == 70
        assert not preview.grab().isNull()
        return QDialog.Accepted if accepted else QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect)
    picker.preview.click()
    assert picker.visibility == (BackgroundVisibility(light=70) if accepted else baseline)
    assert baseline == BackgroundVisibility(light=20, dark=30)
    assert not picker.store.directory.exists()


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
def test_preview_and_workspace_render_identical_visibility(qapp, qtbot, tmp_path, dark, theme_id):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPixmap

    from bilibili_downloader.gui.widgets.appearance_preview import WorkspacePreview
    from bilibili_downloader.gui.widgets.workspace_background import WorkspaceStack

    path = make_image(tmp_path / "solid.png", "#123456")
    qapp.setProperty("darkTheme", dark)
    qapp.setProperty("colorTheme", theme_id)
    workspace = WorkspaceStack()
    qtbot.addWidget(workspace)
    workspace.resize(640, 360)
    workspace.set_background(path)
    preview = WorkspacePreview("下载", QPixmap(str(path)), theme_id)
    qtbot.addWidget(preview)
    preview.resize(640, 360)
    from PySide6.QtCore import QSize
    preview.viewport_size = QSize(640, 360)
    preview.resize(644, 364)
    colors = []
    for percent in (0, 50, 100):
        visibility = BackgroundVisibility(light=percent, dark=percent)
        workspace.set_visibility(visibility)
        preview.visibility = visibility
        actual = workspace.grab().toImage().pixelColor(QPoint(8, 8))
        draft = preview.grab().toImage().pixelColor(QPoint(80, 78))
        assert actual == draft
        colors.append(actual.name())
    assert len(set(colors)) == 3
    assert colors[-1] == "#123456"


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
def test_full_settings_page_reveals_fixed_workspace_background(
    workspace, qtbot, tmp_path, qapp, dark, theme_id
):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from bilibili_downloader.core.models import WORKSPACE_NAMES
    from bilibili_downloader.gui.resources.styles import theme_palette
    from bilibili_downloader.gui.widgets.workspace_background import (
        paint_workspace_background,
    )

    window = workspace
    theme = ThemeManager(qapp, theme_id)
    theme.apply_theme(dark)
    window._settings.appearance.theme = theme_id
    source = tmp_path / "position-markers.png"
    image = Image.new("RGB", (384, 216))
    image.putdata([
        (x * 255 // 383, y * 255 // 215, 60 + (x // 48 % 2) * 100)
        for y in range(216) for x in range(384)
    ])
    image.save(source)
    prepared = prepare_background(source)
    window._background_store.install(prepared)
    window.resize(900, 640)
    window.show()
    stack = window._workspace_pages
    panel = window._settings_page

    def widget_color(widget, point):
        image = widget.grab().toImage()
        return image.pixelColor(
            round(point.x() * image.devicePixelRatio()),
            round(point.y() * image.devicePixelRatio()),
        )

    def assert_backdrop(points):
        actual = stack.grab().toImage()
        expected = QImage(actual.size(), QImage.Format_ARGB32_Premultiplied)
        expected.setDevicePixelRatio(actual.devicePixelRatio())
        painter = QPainter(expected)
        paint_workspace_background(
            painter, stack.rect(), stack._background, dark, theme_id, percent
        )
        painter.end()
        for point in points:
            pixel = QPoint(
                round(point.x() * actual.devicePixelRatio()),
                round(point.y() * actual.devicePixelRatio()),
            )
            assert actual.pixelColor(pixel) == expected.pixelColor(pixel)

    try:
        for percent in (0, 50, 100):
            for name in WORKSPACE_NAMES:
                setattr(window._settings.appearance.backgrounds, name, prepared.reference)
                setattr(
                    window._settings.appearance.background_visibility, name,
                    BackgroundVisibility(light=percent, dark=percent),
                )
            panel.load_settings(window._settings)
            for index in range(4):
                window._show_workspace(index)
                QApplication.processEvents()
                assert_backdrop([QPoint(8, 80)])
            assert panel.property("embedded") is True
            for index in range(panel.tabs.count()):
                panel.tabs.setCurrentIndex(index)
                QApplication.processEvents()
                scroll = panel.tabs.widget(index)
                viewport = scroll.viewport()
                for offset in (0, scroll.verticalScrollBar().maximum()):
                    scroll.verticalScrollBar().setValue(offset)
                    QApplication.processEvents()
                    assert_backdrop([
                        panel.mapTo(stack, QPoint(panel.width() - 8, 8)),
                        viewport.mapTo(stack, QPoint(viewport.width() - 2, viewport.height() // 2)),
                    ])
                scroll.verticalScrollBar().setValue(0)
                QApplication.processEvents()
                card = scroll.widget().layout().itemAt(0).widget()
                # Decorative card space reveals the image; controls stay opaque.
                assert widget_color(card, QPoint(card.width() - 24, 20)) != QColor(
                    theme_palette(dark, theme_id).surface
                )
            assert widget_color(panel._action_bar, QPoint(8, 36)) == QColor(
                theme_palette(dark, theme_id).surface
            )
        for reference in ("", prepared.reference):
            if reference:
                window._background_store.path(reference).write_bytes(b"broken")
            window._settings.appearance.backgrounds.settings = reference
            panel.load_settings(window._settings)
            window._refresh_workspace_background()
            QApplication.processEvents()
            assert stack._background.isNull()
            assert_backdrop([panel.mapTo(stack, QPoint(panel.width() - 8, 8))])
        standalone = SettingsDialog(window._settings)
        qtbot.addWidget(standalone)
        standalone.show()
        QApplication.processEvents()
        assert standalone.property("embedded") is False
        assert widget_color(standalone, QPoint(8, 8)) == QColor(
            theme_palette(dark, theme_id).background
        )
    finally:
        qapp.styleHints().colorSchemeChanged.disconnect(theme._on_color_scheme_changed)
        theme.deleteLater()


def test_visibility_drafts_merge_save_fail_retry_and_restore(workspace, qtbot, tmp_path, monkeypatch):
    window = workspace
    panel = window._settings_page
    image = prepare_background(make_image(tmp_path / "shared.png"))
    window._background_store.install(image)
    for name in ("download", "live"):
        setattr(window._settings.appearance.backgrounds, name, image.reference)
    window._config.save(window._settings)
    panel.load_settings(window._settings)
    window._refresh_workspace_background()
    picker = panel._background_pickers["download"]
    picker.set_visibility(BackgroundVisibility(light=65, dark=40))
    latest = window._config.load().model_copy(deep=True)
    latest.appearance.background_visibility.live.dark = 80
    latest.appearance.background_visibility.download.dark = 55
    latest.sessdata = "concurrent-login"
    merged = panel.merge_into(latest)
    assert merged.appearance.background_visibility.live.dark == 80
    assert merged.sessdata == "concurrent-login"
    assert merged.appearance.background_visibility.download == picker.visibility
    # An unchanged mode merges independently instead of overwriting a newer value.
    picker.set_visibility(BackgroundVisibility(light=65))
    assert panel.merge_into(latest).appearance.background_visibility.download.dark == 55
    assert window._workspace_pages._visibility == BackgroundVisibility()

    original_save = window._config.save
    def fail(_settings):
        raise OSError("unwritable")
    monkeypatch.setattr(window._config, "save", fail)
    assert not window._save_settings()
    assert panel.dirty and picker.visibility.light == 65
    assert window._workspace_pages._visibility == BackgroundVisibility()
    assert window._config.load().appearance.background_visibility.download.light is None
    monkeypatch.setattr(window._config, "save", original_save)
    assert window._save_settings()
    assert not panel.dirty
    window._show_workspace(0)
    assert window._workspace_pages._visibility.light == 65
    assert window._config.load().appearance.background_visibility.download.light == 65
    window._show_workspace(1)
    assert window._workspace_pages._visibility == BackgroundVisibility()
    assert len(list(window._background_store.directory.glob("*.png"))) == 1
    picker.set_visibility(BackgroundVisibility(light=90))
    panel._reset_btn.click()
    assert picker.visibility.light == 65 and not panel.dirty
    picker.reset.click()
    assert picker.visibility == BackgroundVisibility()
    assert window._save_settings()
    assert window._background_store.path(image.reference) is not None
