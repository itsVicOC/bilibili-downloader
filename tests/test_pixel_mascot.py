"""Pixel fidelity, animation lifecycle, fallback and sidebar geometry."""

from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets import pixel_mascot
from bilibili_downloader.gui.widgets.mascot_animation import CLIPS, PERIODS
from bilibili_downloader.gui.widgets.pixel_mascot import FRAME_DURATIONS, PixelMascot
from tests.test_mascot_animation import FakeClock
from tests.test_workspaces import workspace as workspace


def flush():
    for _ in range(4):
        QApplication.processEvents()


def test_atlas_has_binary_alpha_shared_palette_and_stable_body():
    with Image.open(asset_path("xiaoliu_idle.png")) as source:
        atlas = source.convert("RGBA")
    with Image.open(asset_path("xiaoliu.png")) as source:
        still = source.convert("RGBA")
    assert atlas.size == (240, 40)
    assert still.size == (40, 40)
    assert len(atlas.getcolors()) <= 24
    assert {alpha for _, alpha in atlas.getchannel("A").getcolors()} == {0, 255}
    assert sum(FRAME_DURATIONS) == 4000
    base = atlas.crop((0, 0, 40, 40))
    assert base.tobytes() == still.tobytes()
    for index in range(6):
        frame = atlas.crop((index * 40, 0, (index + 1) * 40, 40))
        assert (
            frame.crop((0, 22, 40, 40)).tobytes()
            == base.crop((0, 22, 40, 40)).tobytes()
        )
    half_closed = atlas.crop((2 * 40 + 12, 13, 2 * 40 + 27, 18))
    closed = atlas.crop((3 * 40 + 12, 13, 3 * 40 + 27, 18))
    assert half_closed.tobytes() != base.crop((12, 13, 27, 18)).tobytes()
    assert closed.tobytes() != half_closed.tobytes()


@pytest.mark.parametrize("dpr", [1, 1.5, 2])
@pytest.mark.parametrize("action", list(CLIPS))
def test_paint_keeps_each_source_pixel_crisp(qtbot, dpr, action):
    mascot = PixelMascot()
    qtbot.addWidget(mascot)
    mascot._freeze_preview(datetime(2026, 10, 21, 10), action, 3)
    image = QImage(round(80 * dpr), round(80 * dpr), QImage.Format_RGBA8888)
    image.setDevicePixelRatio(dpr)
    image.fill(Qt.transparent)
    mascot.render(image)
    block = round(2 * dpr)
    for y in range(40):
        for x in range(40):
            color = image.pixelColor(x * block, y * block)
            for dy in range(block):
                for dx in range(block):
                    assert image.pixelColor(x * block + dx, y * block + dy) == color


def test_animation_pauses_when_hidden_minimized_or_inactive(qtbot, qapp, monkeypatch):
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    clock = FakeClock()
    mascot = PixelMascot(host, now=clock.now, clock=clock.monotonic)
    layout.addWidget(mascot)
    active = [True]
    monkeypatch.setattr(mascot, "_application_active", lambda: active[0])
    host.show()
    flush()
    assert mascot._timer.isActive()
    mascot._timer.stop()
    clock.advance(mascot._player.delay_ms + 1)
    mascot._advance_frame()
    assert mascot._frame_index == 1
    assert mascot._timer.interval() == mascot._player.durations[1]

    mascot.hide()
    assert not mascot._timer.isActive()
    mascot.show()
    assert mascot._frame_index == 1
    assert mascot._timer.isActive()
    host.hide()
    assert not mascot._timer.isActive()
    host.show()
    flush()
    assert mascot._timer.isActive()
    host.showMinimized()
    flush()
    assert not mascot._timer.isActive()
    host.showNormal()
    flush()
    assert mascot._timer.isActive()

    active[0] = False
    qapp.applicationStateChanged.emit(Qt.ApplicationInactive)
    assert not mascot._timer.isActive()
    active[0] = True
    qapp.applicationStateChanged.emit(Qt.ApplicationActive)
    assert mascot._timer.isActive()


@pytest.mark.parametrize("bad_atlas", ["missing", "corrupt", "wrong_size"])
def test_unavailable_animation_uses_static_first_frame(
    qtbot, tmp_path, monkeypatch, bad_atlas
):
    invalid = tmp_path / "atlas.png"
    if bad_atlas == "corrupt":
        invalid.write_bytes(b"not a PNG")
    elif bad_atlas == "wrong_size":
        invalid = Path(asset_path("xiaoliu.png"))
    resolve = pixel_mascot.asset_path
    monkeypatch.setattr(
        pixel_mascot,
        "asset_path",
        lambda name: str(invalid) if name.startswith("xiaoliu_") else resolve(name),
    )
    mascot = PixelMascot()
    qtbot.addWidget(mascot)
    monkeypatch.setattr(mascot, "_application_active", lambda: True)
    mascot.show()
    flush()
    assert mascot._frames == []
    assert not mascot._timer.isActive()
    assert not mascot._still.isNull()
    assert mascot._still.size().width() == 40
    assert not mascot.grab().isNull()


def test_frozen_bundle_loads_both_assets(qtbot, tmp_path, monkeypatch):
    import sys

    bundle = tmp_path / "bilibili_downloader/gui/assets"
    bundle.mkdir(parents=True)
    for name in ("xiaoliu.png", *(clip.asset for clip in CLIPS.values())):
        (bundle / name).write_bytes(Path(asset_path(name)).read_bytes())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    mascot = PixelMascot()
    qtbot.addWidget(mascot)
    assert set(mascot._clips) == set(CLIPS)
    assert len(mascot._frames) == 6
    assert not mascot._still.isNull()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_sidebar_fits_both_mascot_sizes_and_compact_navigation(
    workspace, qapp, monkeypatch, theme_id, dark
):
    previous = (
        qapp.font(),
        qapp.palette(),
        qapp.styleSheet(),
        qapp.property("darkTheme"),
        qapp.property("colorTheme"),
    )
    theme = ThemeManager(qapp, theme_id)
    try:
        theme.apply_theme(dark)
        window = workspace
        card = window._mascot_card
        monkeypatch.setattr(card.mascot, "_application_active", lambda: True)
        window.show()
        # Return through each mode to exercise repeated transitions.
        for width, height in (
            (1120, 640),
            (1120, 760),
            (900, 640),
            (1320, 860),
            (1120, 640),
        ):
            window.resize(width, height)
            flush()
            assert (window.width(), window.height()) == (width, height)
            for control in (
                *window._nav_buttons,
                window._settings_nav,
                window._mode_button,
                window._header_login,
            ):
                rect = QRect(control.mapTo(window._sidebar, QPoint()), control.size())
                assert window._sidebar.rect().contains(rect)
                assert (
                    not control.geometry().intersects(card.geometry())
                    or not card.isVisible()
                )
            if width < 1120:
                assert not card.isVisible()
                assert not card.mascot._timer.isActive()
                continue
            assert card.isVisible()
            required = window._side_layout.minimumSize().height() - card.minimumHeight() + card.height_for_mode(False)
            assert card._mini == (window._sidebar.height() < required)
            assert card.mascot.width() == (40 if card._mini else 80)
            assert card.mascot._timer.isActive()
            for child in (card.mascot, card.caption):
                rect = QRect(child.mapTo(card, QPoint()), child.size())
                assert card.rect().contains(rect)
            assert not card.mascot.geometry().intersects(card.caption.geometry())
    finally:
        qapp.setFont(previous[0])
        qapp.setPalette(previous[1])
        qapp.setStyleSheet(previous[2])
        qapp.setProperty("darkTheme", previous[3])
        qapp.setProperty("colorTheme", previous[4])
        theme.deleteLater()


@pytest.mark.parametrize("action", [key for key in CLIPS if key != "idle"])
def test_action_assets_have_shared_palette_clear_poses_and_neutral_endpoints(action):
    with Image.open(asset_path(CLIPS[action].asset)) as source:
        atlas = source.convert("RGBA")
    with Image.open(asset_path("xiaoliu.png")) as source:
        neutral = source.convert("RGBA")
    assert atlas.size == (320, 40)
    assert {alpha for _, alpha in atlas.getchannel("A").getcolors()} == {0, 255}
    palette = {pixel[:3] for pixel in neutral.get_flattened_data() if pixel[3]}
    assert {pixel[:3] for pixel in atlas.get_flattened_data() if pixel[3]} <= palette
    assert atlas.crop((0, 0, 40, 40)).tobytes() == neutral.tobytes()
    assert atlas.crop((280, 0, 320, 40)).tobytes() == neutral.tobytes()
    body_poses = set()
    for index in range(1, 7):
        frame = atlas.crop((index * 40, 0, (index + 1) * 40, 40))
        left, top, right, bottom = frame.getbbox()
        assert 0 < left < right < 40
        assert 0 < top < bottom < 40
        body_poses.add(frame.crop((0, 20, 40, 40)).tobytes())
    assert len(body_poses) >= 3
    assert sum(CLIPS[action].durations) == (6000 if action == "doze" else 2560)
    assert Path(asset_path(CLIPS[action].asset)).stat().st_size < 15000


@pytest.mark.parametrize("hour,period", list(zip((6, 10, 14, 20, 1), PERIODS)))
def test_caption_keeps_time_period_across_layout_changes(qtbot, hour, period):
    card = pixel_mascot.MascotCard()
    qtbot.addWidget(card)
    card.mascot._freeze_preview(datetime(2026, 10, 21, hour))
    assert card.caption.text() == period.caption
    card._set_mini(True)
    assert card.caption.text() == period.caption.replace("，", "\n")
    card._set_mini(False)
    assert card.caption.text() == period.caption
    assert period.name in card.accessibleName()
    assert period.caption in card.mascot.toolTip()


def test_one_bad_action_is_skipped_and_missing_library_uses_legacy_idle(qtbot, tmp_path, monkeypatch):
    resolve = pixel_mascot.asset_path
    invalid = str(tmp_path / "missing.png")
    monkeypatch.setattr(pixel_mascot, "asset_path", lambda name: invalid if name == "xiaoliu_cheer.png" else resolve(name))
    clock = FakeClock()
    mascot = PixelMascot(now=clock.now, clock=clock.monotonic)
    qtbot.addWidget(mascot)
    mascot._player.resume()
    assert "cheer" not in mascot._clips
    assert mascot._player.clip == "hop"
    monkeypatch.setattr(pixel_mascot, "asset_path", lambda name: resolve(name) if name in ("xiaoliu.png", "xiaoliu_idle.png") else invalid)
    legacy = PixelMascot(now=clock.now, clock=clock.monotonic)
    qtbot.addWidget(legacy)
    legacy._player.resume()
    assert legacy._player.clip == "idle"
    assert legacy._player.running
    assert legacy._player.idle_remaining_ms is None


def test_damaged_idle_still_allows_healthy_actions(qtbot, tmp_path, monkeypatch):
    resolve = pixel_mascot.asset_path
    monkeypatch.setattr(pixel_mascot, "asset_path", lambda name: str(tmp_path / "missing.png") if name == "xiaoliu_idle.png" else resolve(name))
    clock = FakeClock()
    mascot = PixelMascot(now=clock.now, clock=clock.monotonic)
    qtbot.addWidget(mascot)
    mascot._player.resume()
    assert mascot._player.clip == "cheer"
    assert mascot._player.running
    assert mascot._clips["idle"][0].toImage() == mascot._still.toImage()
