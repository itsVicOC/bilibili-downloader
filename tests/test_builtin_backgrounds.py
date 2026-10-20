"""Offline catalog, isolated gallery drafts and wallpaper compatibility."""

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog

from bilibili_downloader.core.appearance import BackgroundStore, prepare_background
from bilibili_downloader.core.builtin_backgrounds import (
    BUILTIN_BACKGROUNDS,
    builtin_background,
)
from bilibili_downloader.core.models import (
    AppSettings,
    BackgroundVisibility,
    WorkspaceBackgrounds,
)
from bilibili_downloader.gui.dialogs.background_gallery import BackgroundGallery
from bilibili_downloader.gui.resources.paths import asset_path, background_path
from bilibili_downloader.gui.resources.styles import (
    background_overlay_alpha,
    theme_palette,
)
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.appearance_preview import WorkspacePreview
from bilibili_downloader.gui.widgets.background_picker import BackgroundPicker
from bilibili_downloader.gui.widgets.workspace_background import (
    WorkspaceStack,
    background_pixmap,
)
from bilibili_downloader.utils.config import ConfigManager
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(4):
        QApplication.processEvents()


def local_image(path):
    Image.new("RGB", (384, 216), "#123456").save(path)
    return path


@pytest.fixture(autouse=True)
def restore_theme(qapp):
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
    qapp.setStyleSheet(previous[2])
    qapp.setProperty("darkTheme", previous[3])
    qapp.setProperty("colorTheme", previous[4])


def test_all_catalog_references_roundtrip_without_changing_defaults(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    assert WorkspaceBackgrounds().model_dump() == {
        name: "" for name in ("download", "live", "tasks", "settings")
    }
    for entry in BUILTIN_BACKGROUNDS:
        settings = AppSettings(
            appearance={"backgrounds": {"download": entry.reference}}
        )
        config.save(settings)
        assert config.load().appearance.backgrounds.download == entry.reference
        assert builtin_background(entry.reference) is entry
    legacy = "a" * 64 + ".png"
    assert WorkspaceBackgrounds(download=legacy).download == legacy
    for invalid in (
        "builtin:missing",
        "builtin:../xiaoliu",
        "builtin:/tmp/a",
        "../../image.png",
        None,
        [],
    ):
        assert WorkspaceBackgrounds(download=invalid).download == ""


def test_collection_assets_are_complete_and_fit_the_budget():
    assert len(BUILTIN_BACKGROUNDS) == 12
    assert len({entry.id for entry in BUILTIN_BACKGROUNDS}) == 12
    for page_name in ("download", "live", "tasks", "settings"):
        assert {
            entry.style for entry in BUILTIN_BACKGROUNDS if entry.workspace == page_name
        } == {"anime", "pixel", "watercolor"}
    for entry in BUILTIN_BACKGROUNDS:
        with Image.open(background_path(entry.reference)) as image:
            assert image.size == (
                (640, 360) if entry.style == "pixel" else (2560, 1440)
            )
            assert image.format == ("PNG" if entry.style == "pixel" else "WEBP")
            assert not getattr(image, "is_animated", False)
        with Image.open(background_path(entry.reference, thumbnail=True)) as image:
            assert image.size == (320, 180)
    assert (
        sum(path.stat().st_size for path in Path(asset_path("backgrounds")).iterdir())
        <= 12 * 1024 * 1024
    )


def test_builtin_resources_do_not_enter_local_cleanup(tmp_path):
    store = BackgroundStore(tmp_path)
    prepared = prepare_background(local_image(tmp_path / "local.png"))
    store.install(prepared)
    entry = BUILTIN_BACKGROUNDS[0]
    bundled = background_path(entry.reference, store)
    assert bundled and bundled.is_file()
    assert store.path(entry.reference) is None
    store.cleanup([entry.reference])
    assert bundled.is_file()
    assert not store.path(prepared.reference)


@pytest.mark.parametrize("workspace", ["download", "live", "tasks", "settings"])
def test_gallery_filters_and_responsive_grid(qtbot, tmp_path, workspace):
    picker = BackgroundPicker("背景", BackgroundStore(tmp_path), workspace=workspace)
    qtbot.addWidget(picker)
    dialog = BackgroundGallery(picker)
    qtbot.addWidget(dialog)
    dialog.show()
    flush()
    visible = lambda: [card for card in dialog._cards if not card.isHidden()]
    assert len(visible()) == 12
    assert all(card.entry.workspace == workspace for card in visible()[:3])
    dialog.page_filter.setCurrentIndex(dialog.page_filter.findData(workspace))
    assert len(visible()) == 3
    dialog.style_filter.setCurrentIndex(dialog.style_filter.findData("pixel"))
    assert len(visible()) == 1
    dialog.page_filter.setCurrentIndex(0)
    assert len(visible()) == 4
    dialog.style_filter.setCurrentIndex(0)
    assert len(visible()) == 12
    for size in ((720, 540), (980, 660), (1280, 720)):
        dialog.resize(*size)
        flush()
        assert dialog.scroll.horizontalScrollBar().maximum() == 0
        assert dialog.rect().contains(
            QRect(
                dialog.apply_button.mapTo(dialog, QPoint()), dialog.apply_button.size()
            )
        )
        card = visible()[0]
        assert card.width() <= dialog.scroll.viewport().width()
    visible()[0].setFocus(Qt.TabFocusReason)
    qtbot.keyClick(visible()[0], Qt.Key_Space)
    assert dialog.reference == visible()[0].entry.reference


@pytest.mark.parametrize("accepted", [False, True])
def test_gallery_apply_and_cancel_keep_the_parent_draft_isolated(
    qtbot, monkeypatch, tmp_path, accepted
):
    picker = BackgroundPicker("下载", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    picker.set_visibility(BackgroundVisibility(light=20, dark=30))

    def inspect(dialog):
        dialog.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
        dialog.effects.light_button.setChecked(True)
        assert dialog.effects.slider.value() == 20
        dialog.effects.slider.setValue(70)
        assert picker.reference == ""
        assert picker.visibility.light == 20
        return QDialog.Accepted if accepted else QDialog.Rejected

    monkeypatch.setattr(BackgroundGallery, "exec", inspect)
    picker.choose.click()
    assert picker.reference == (BUILTIN_BACKGROUNDS[0].reference if accepted else "")
    assert picker.visibility.light == (70 if accepted else 20)
    assert not picker.store.directory.exists()


def test_custom_import_and_late_result_do_not_override_a_builtin(qtbot, tmp_path):
    picker = BackgroundPicker("下载", BackgroundStore(tmp_path))
    qtbot.addWidget(picker)
    dialog = BackgroundGallery(picker)
    qtbot.addWidget(dialog)
    dialog.select_path(local_image(tmp_path / "custom.png"))
    dialog.select_builtin(BUILTIN_BACKGROUNDS[0].reference)
    qtbot.waitUntil(lambda: not dialog._jobs)
    assert dialog.reference == BUILTIN_BACKGROUNDS[0].reference
    assert dialog.prepared is None
    dialog.select_path(tmp_path / "custom.png")
    qtbot.waitUntil(lambda: not dialog.busy)
    assert dialog.prepared is not None
    assert builtin_background(dialog.reference) is None
    assert picker.reference == ""
    assert not picker.store.directory.exists()
    dialog.select_path(tmp_path / "missing.png")
    qtbot.waitUntil(lambda: not dialog.busy)
    assert dialog.prepared is not None
    assert dialog.apply_button.isEnabled()
    assert "损坏" in dialog.import_status.text()


def test_custom_builtin_save_restore_and_restart(workspace, tmp_path):
    window = workspace
    picker = window._settings_page._background_pickers["download"]
    custom = prepare_background(local_image(tmp_path / "picture.png"))
    picker.reference, picker.prepared = custom.reference, custom
    assert window._save_settings()
    assert window._background_store.path(custom.reference)
    picker.set_reference(BUILTIN_BACKGROUNDS[0].reference)
    picker.set_visibility(BackgroundVisibility(light=65))
    assert window._settings.appearance.backgrounds.download == custom.reference
    assert window._save_settings()
    assert (
        window._config.load().appearance.backgrounds.download
        == BUILTIN_BACKGROUNDS[0].reference
    )
    assert not window._background_store.path(custom.reference)
    picker.set_reference(BUILTIN_BACKGROUNDS[1].reference)
    window._settings_page.load_settings(window._settings)
    assert picker.reference == BUILTIN_BACKGROUNDS[0].reference
    picker._restore_default()
    assert window._save_settings()
    assert window._config.load().appearance.backgrounds.download == ""
    assert picker.visibility == BackgroundVisibility()


def test_missing_resource_falls_back_without_erasing_saved_reference(
    workspace, monkeypatch
):
    from bilibili_downloader.gui import main_window

    entry = BUILTIN_BACKGROUNDS[0]
    window = workspace
    window._settings.appearance.backgrounds.download = entry.reference
    monkeypatch.setattr(main_window, "background_path", lambda *_args: None)
    window._refresh_workspace_background()
    assert window._workspace_pages._background.isNull()
    assert not window._workspace_pages.property("mascotBackground")
    assert window._settings.appearance.backgrounds.download == entry.reference


def test_failed_save_keeps_builtin_draft_available_for_retry(workspace, monkeypatch):
    window = workspace
    panel = window._settings_page
    entry = BUILTIN_BACKGROUNDS[0]
    picker = panel._background_pickers["download"]
    picker.set_reference(entry.reference)
    save = window._config.save
    monkeypatch.setattr(
        window._config,
        "save",
        lambda _settings: (_ for _ in ()).throw(OSError("disk full")),
    )
    assert not window._save_settings()
    assert picker.reference == entry.reference
    assert window._settings.appearance.backgrounds.download == ""
    monkeypatch.setattr(window._config, "save", save)
    assert window._save_settings()
    assert window._config.load().appearance.backgrounds.download == entry.reference


def test_frozen_installation_resolves_full_images_and_thumbnails(tmp_path, monkeypatch):
    import sys

    bundled = tmp_path / "bilibili_downloader/gui/assets"
    for entry in BUILTIN_BACKGROUNDS[:2]:
        for name in (entry.image, entry.thumbnail):
            destination = bundled / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path(asset_path(name)).read_bytes())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    for entry in BUILTIN_BACKGROUNDS[:2]:
        assert background_path(entry.reference) == bundled / entry.image
        assert (
            background_path(entry.reference, thumbnail=True)
            == bundled / entry.thumbnail
        )
        assert not background_pixmap(background_path(entry.reference)).isNull()


@pytest.mark.parametrize("dark", [False, True])
def test_builtin_defaults_and_manual_visibility_match_preview(qtbot, qapp, dark):
    theme = ThemeManager(qapp, "bilibili_blue")
    theme.apply_theme(dark)
    entry = BUILTIN_BACKGROUNDS[1]
    pixmap = background_pixmap(background_path(entry.reference))
    workspace = WorkspaceStack()
    qtbot.addWidget(workspace)
    workspace.resize(576, 316)
    workspace.set_background(
        background_path(entry.reference), builtin=True, pixel_art=True
    )
    preview = WorkspacePreview(
        "下载", pixmap, "bilibili_blue", builtin=True, pixel_art=True
    )
    qtbot.addWidget(preview)
    preview.resize(640, 360)
    for visibility in (None, 0, 50, 100):
        values = BackgroundVisibility(light=visibility, dark=visibility)
        workspace.set_visibility(values)
        preview.visibility = values
        # Compare the exposed preview margin with the shared renderer at the
        # same page size, including crop and nearest-neighbour sampling.
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QImage, QPainter

        from bilibili_downloader.gui.widgets.workspace_background import (
            paint_workspace_background,
        )
        preview.viewport_size = QSize(640, 360)
        preview.resize(644, 364)
        actual = preview.grab().toImage()
        dpr = actual.devicePixelRatio()
        expected = QImage(actual.size(), QImage.Format_ARGB32_Premultiplied)
        expected.setDevicePixelRatio(dpr)
        painter = QPainter(expected)
        painter.translate(2, 2)
        paint_workspace_background(painter, preview.background_rect(), pixmap, dark,
                                   "bilibili_blue", visibility, builtin=True, pixel_art=True)
        painter.end()
        assert actual.pixelColor(round(80 * dpr), round(78 * dpr)) == expected.pixelColor(round(80 * dpr), round(78 * dpr))
    assert background_overlay_alpha(dark, builtin=True) == round(
        255 * (20 if dark else 10) / 100
    )
    assert background_overlay_alpha(
        dark, visibility=70, builtin=True
    ) == background_overlay_alpha(dark, visibility=70)
    theme.deleteLater()


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
def test_builtin_surfaces_and_three_window_sizes(
    workspace, qapp, tmp_path, dark, theme_id
):
    window = workspace
    theme = ThemeManager(qapp, theme_id)
    theme.apply_theme(dark)
    colors = theme_palette(dark, theme_id)
    for page in ("download", "live", "tasks", "settings"):
        setattr(
            window._settings.appearance.backgrounds,
            page,
            BUILTIN_BACKGROUNDS[0].reference,
        )
    window.show()
    for width, height in ((900, 640), (1120, 760), (1320, 860)):
        window.resize(width, height)
        for page in range(4):
            window._show_workspace(page)
            flush()
            assert (window.width(), window.height()) == (width, height)
            assert window._workspace_pages.property("mascotBackground")
    card = window._settings_page._background_cards[0]
    image = card.grab().toImage()
    assert image.pixelColor(
        round((card.width() - 24) * image.devicePixelRatio()),
        round(20 * image.devicePixelRatio()),
    ) != QColor(colors.surface)
    custom = prepare_background(local_image(tmp_path / "plain.png"))
    window._background_store.install(custom)
    window._settings.appearance.backgrounds.settings = custom.reference
    window._refresh_workspace_background()
    flush()
    image = card.grab().toImage()
    assert image.pixelColor(
        round((card.width() - 24) * image.devicePixelRatio()),
        round(20 * image.devicePixelRatio()),
    ) != QColor(colors.surface)
    theme.deleteLater()
