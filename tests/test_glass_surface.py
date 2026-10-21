"""Wallpaper glass preserves text contrast, coordinates and shared cache lifetime."""

import pytest
from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel

from bilibili_downloader.core.appearance import prepare_background
from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.models import BackgroundVisibility, VideoInfo
from bilibili_downloader.gui.resources.styles import (
    contrast_ratio,
    glass_text_color,
    theme_palette,
)
from bilibili_downloader.gui.resources.theme import ThemeManager
from tests.test_ui_polish import flush
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("source_kind", ["builtin", "custom"])
@pytest.mark.parametrize("blur", [0, 18, 40])
def test_glass_blurs_only_wallpaper_and_reuses_cache(workspace, qapp, tmp_path, dark, source_kind, blur):
    theme = ThemeManager(qapp, mode="dark" if dark else "light")
    colors = theme_palette(dark)
    if source_kind == "builtin":
        reference = BUILTIN_BACKGROUNDS[0].reference
    else:
        source = tmp_path / "checker.png"
        image = Image.new("RGB", (480, 320))
        image.putdata([(0, 0, 0) if (x // 6 + y // 6) % 2 else (255, 255, 255) for y in range(320) for x in range(480)])
        image.save(source)
        prepared = prepare_background(source)
        workspace._background_store.install(prepared)
        reference = prepared.reference
    workspace._settings.appearance.backgrounds.download = reference
    workspace._settings.appearance.glass_blur = blur
    workspace.resize(1320, 860)
    workspace._refresh_workspace_background()
    workspace.show()
    flush()
    stack = workspace._workspace_pages
    workspace.grab()
    key = stack._glass.image.cacheKey()
    assert not stack._glass.image.isNull()
    assert workspace._hero.graphicsEffect() is None
    assert workspace._hero_title.graphicsEffect() is None
    image = stack._glass.image.toImage()
    for x in range(10, image.width(), 70):
        for y in range(10, image.height(), 70):
            for color in (colors.text, glass_text_color(colors)):
                assert contrast_ratio(color, image.pixelColor(x, y).name()) >= 4.5
    workspace._on_resolve_success(VideoInfo(bvid="BV1DEMO", title="缓存复用"), [], [], True)
    flush()
    workspace._workspace_scroll.verticalScrollBar().setValue(80)
    workspace.grab()
    assert stack._glass.image.cacheKey() == key
    stack.set_visibility(BackgroundVisibility(light=50, dark=50))
    workspace.grab()
    assert stack._glass.image.cacheKey() != key
    # Actual text bounds still use native Qt glyphs on the background material.
    for label in workspace._hero.findChildren(QLabel):
        if label.isVisible():
            assert label.graphicsEffect() is None
    stack.set_background(None)
    flush()
    assert stack._glass.image.isNull()
    assert not stack.property("customBackground")
    theme.deleteLater()


@pytest.mark.parametrize("dark", [False, True])
def test_hero_title_retains_contrast_on_dark_saturated_art(workspace, qapp, tmp_path, dark):
    theme = ThemeManager(qapp, theme_id="bilibili_blue", mode="dark" if dark else "light")
    source = tmp_path / "blue.png"
    Image.new("RGB", (640, 480), (8, 25, 170)).save(source)
    prepared = prepare_background(source)
    workspace._background_store.install(prepared)
    workspace._settings.appearance.backgrounds.download = prepared.reference
    workspace._refresh_workspace_background()
    workspace.show()
    flush()
    label = workspace._hero_title
    label.hide()
    backdrop = workspace._hero.grab().toImage()
    point = label.mapTo(workspace._hero, QPoint(label.width() // 2, label.height() // 2))
    background = backdrop.pixelColor(round(point.x() * backdrop.devicePixelRatio()), round(point.y() * backdrop.devicePixelRatio())).name()
    label.show()
    assert contrast_ratio(label.palette().color(QPalette.WindowText).name(), background) >= 4.5
    theme.deleteLater()
