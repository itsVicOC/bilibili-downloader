"""Wallpaper glass preserves text contrast, coordinates and shared cache lifetime."""

import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bilibili_downloader.core.appearance import prepare_background
from bilibili_downloader.core.builtin_backgrounds import BUILTIN_BACKGROUNDS
from bilibili_downloader.core.models import BackgroundVisibility, VideoInfo
from bilibili_downloader.gui.resources.styles import (
    contrast_ratio,
    theme_palette,
    wallpaper_palette,
)
from bilibili_downloader.gui.resources.theme import ThemeManager
from bilibili_downloader.gui.widgets.components import SectionCard
from bilibili_downloader.gui.widgets.dialog_shell import AppDialog
from bilibili_downloader.gui.widgets.glass_surface import GlassBackdrop
from bilibili_downloader.gui.widgets.row_hover import RowHoverTable, RowHoverTree
from bilibili_downloader.gui.widgets.workspace_background import WorkspaceStack
from tests.test_ui_polish import flush
from tests.test_ui_refresh import restore_theme as restore_theme
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize("clear", [False, True])
def test_scene_refraction_stays_within_the_round_edge(qapp, clear):
    size = QSize(124, 82)
    colors = theme_palette(False)
    glass = GlassBackdrop()
    glass.prepare("contrast", size, lambda painter, rect: painter.fillRect(rect, QColor("black")), False, colors)
    area = QRectF(QPoint(), size)

    def draw():
        image = QImage(size, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor(colors.background))
        painter = QPainter(image)
        glass.paint(painter, area, area, clear=clear)
        painter.end()
        return image

    shaded = draw()
    glass.original = QPixmap(size)
    glass.original.fill(QColor("white"))
    lit = draw()
    assert shaded != lit
    assert shaded.copy(14, 14, 96, 54) == lit.copy(14, 14, 96, 54)


@pytest.mark.parametrize("dark", [False, True])
def test_clear_chrome_preserves_more_stripe_detail(qapp, dark):
    size = QSize(480, 94)
    stripes = QImage(size, QImage.Format_RGB32)
    painter = QPainter(stripes)
    for x in range(0, size.width(), 24):
        painter.fillRect(x, 0, 24, size.height(), Qt.white if x // 24 % 2 else Qt.black)
    painter.end()
    glass = GlassBackdrop()
    glass.prepare("stripes", size, lambda p, rect: p.drawImage(rect, stripes), dark, theme_palette(dark))

    def brightness_spread(material):
        image = material.toImage()
        samples = [image.pixelColor(x, image.height() // 2).lightness() for x in range(108, 384, 24)]
        return max(samples) - min(samples)

    assert brightness_spread(glass.clear_image) >= 1.20 * brightness_spread(glass.image) > 0


@pytest.mark.parametrize("kind", ["table", "tree"])
def test_clear_space_moves_with_last_visible_row_without_rebuilding_wallpaper(qtbot, qapp, tmp_path, kind):
    theme = ThemeManager(qapp, mode="light")
    source = tmp_path / "black.png"
    Image.new("RGB", (640, 480), "black").save(source)
    host = WorkspaceStack()
    qtbot.addWidget(host)
    host.set_background(source)
    host.set_visibility(BackgroundVisibility(light=100, dark=100))
    if kind == "table":
        view = RowHoverTable(1, 1)
        view.setItem(0, 0, QTableWidgetItem("一项任务"))
        expand = lambda: view.setRowCount(30)
    else:
        view = RowHoverTree()
        group = QTreeWidgetItem(view, ["录制记录"])
        for row in range(30):
            QTreeWidgetItem(group, [f"记录 {row + 1}"])
        expand = lambda: group.setExpanded(True)
    host.addWidget(view)
    host.resize(640, 480)
    host.show()
    flush()
    surface = view._reading_surface
    top = surface._blank_top()
    assert top is not None and top > view.viewport().y()
    glass = host.backdrop.glass
    keys = glass.reading.cacheKey(), glass.clear_image.cacheKey()

    def snapshot():
        image = surface.grab().toImage()
        dpr = image.devicePixelRatio()
        x = round(surface.width() / 2 * dpr)
        return [image.pixelColor(x, round(y * dpr)).lightness() for y in (top - 4, top + 7, top + 24)]

    above, fade, blank = snapshot()
    assert above > fade > blank
    expand()
    flush()
    assert surface._blank_top() is None
    assert snapshot() == [above] * 3
    assert (glass.reading.cacheKey(), glass.clear_image.cacheKey()) == keys
    theme.deleteLater()


@pytest.mark.parametrize("theme_id", ["star_trail", "bilibili_blue"])
@pytest.mark.parametrize("dark", [False, True])
def test_reading_surface_reveals_wallpaper_and_clips_item_view(qtbot, qapp, tmp_path, theme_id, dark):
    theme = ThemeManager(qapp, theme_id=theme_id, mode="dark" if dark else "light")
    colors = wallpaper_palette(theme_palette(dark, theme_id), dark)
    source = tmp_path / "split.png"
    picture = Image.new("RGB", (800, 560), "black")
    ImageDraw.Draw(picture).rectangle((400, 0, 800, 560), fill="white")
    picture.save(source)
    host = WorkspaceStack()
    qtbot.addWidget(host)
    host.set_background(source)
    host.set_visibility(BackgroundVisibility(light=100, dark=100))
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(26, 26, 26, 26)
    table = RowHoverTable(20, 2)
    table.setHorizontalHeaderLabels(["作品", "状态"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.verticalHeader().hide()
    table.setAlternatingRowColors(True)
    for row in range(table.rowCount()):
        table.setItem(row, 0, QTableWidgetItem(f"任务 {row + 1}"))
        table.setItem(row, 1, QTableWidgetItem("待下载"))
    form = SectionCard()
    entry = QLineEdit()
    form.body.addWidget(entry)
    layout.addWidget(table)
    layout.addWidget(form)
    host.addWidget(page)
    host.resize(800, 560)
    host.show()
    host.setFocus()
    flush()

    def rgb(image, widget, x, y):
        dpr = image.devicePixelRatio()
        point = widget.mapTo(host, QPoint(x, y))
        return image.pixelColor(round(point.x() * dpr), round(point.y() * dpr))

    screenshot = host.grab().toImage()
    original = host.backdrop._viewport.toImage()
    for view, y in ((table.viewport(), table.rowHeight(0) // 2), (form, form.height() // 2), (entry, 10)):
        left = rgb(screenshot, view, view.width() // 4, y)
        right = rgb(screenshot, view, view.width() * 3 // 4, y)
        assert right.lightness() - left.lightness() >= 18, view.objectName()
        assert min(contrast_ratio(colors.text, value.name()) for value in (left, right)) >= 4.5
    assert table.horizontalHeader().geometry().topLeft().manhattanLength() >= 16
    assert table.verticalScrollBar().maximum() > 0
    cache = host.backdrop.glass.reading.cacheKey()
    for row in (0, table.rowCount() - 1):
        table.selectRow(row)
        table.scrollToItem(table.item(row, 0))
        flush()
        screenshot = host.grab().toImage()
        for x in (1, table.width() - 2):
            for y in (1, table.height() - 2):
                assert rgb(screenshot, table, x, y) == rgb(original, table, x, y)
        assert host.backdrop.glass.reading.cacheKey() == cache
    theme.deleteLater()


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("source_kind", ["builtin", "custom"])
@pytest.mark.parametrize("blur", [0, 18, 40])
def test_glass_blurs_only_wallpaper_and_reuses_cache(workspace, qapp, tmp_path, dark, source_kind, blur):
    theme = ThemeManager(qapp, mode="dark" if dark else "light")
    colors = wallpaper_palette(theme_palette(dark), dark)
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
    glass = workspace.backdrop.glass
    materials = (glass.image, glass.reading, glass.clear_image)
    keys = tuple(material.cacheKey() for material in materials)
    assert not glass.image.isNull()
    assert stack.backdrop is workspace.backdrop
    assert workspace._hero.graphicsEffect() is None
    for material in materials:
        image = material.toImage()
        for x in range(10, image.width(), 70):
            for y in range(10, image.height(), 70):
                base = image.pixelColor(x, y).name()
                for color in (colors.text, colors.muted, colors.active_text, colors.success, colors.warning, colors.danger):
                    assert contrast_ratio(color, base) >= 4.5
                for color in (colors.control_border, colors.focus):
                    assert contrast_ratio(color, base) >= 3
    workspace._on_resolve_success(VideoInfo(bvid="BV1DEMO", title="缓存复用"), [], [], True)
    flush()
    workspace._workspace_scroll.verticalScrollBar().setValue(80)
    workspace.grab()
    assert (glass.image.cacheKey(), glass.reading.cacheKey(), glass.clear_image.cacheKey()) == keys
    stack.set_visibility(BackgroundVisibility(light=50, dark=50))
    workspace.grab()
    assert glass.image.cacheKey() != keys[0]
    assert glass.reading.cacheKey() != keys[1]
    assert glass.clear_image.cacheKey() != keys[2]
    # Actual text bounds still use native Qt glyphs on the background material.
    for label in workspace._hero.findChildren(QLabel):
        if label.isVisible():
            assert label.graphicsEffect() is None
    stack.set_background(None)
    flush()
    assert workspace.backdrop.image.isNull()
    assert not workspace.property("customBackground")
    theme.deleteLater()


@pytest.mark.parametrize("dark", [False, True])
def test_glass_toolbar_title_retains_contrast_on_saturated_art(workspace, qapp, tmp_path, dark):
    theme = ThemeManager(qapp, theme_id="bilibili_blue", mode="dark" if dark else "light")
    source = tmp_path / "blue.png"
    Image.new("RGB", (640, 480), (8, 25, 170)).save(source)
    prepared = prepare_background(source)
    workspace._background_store.install(prepared)
    workspace._settings.appearance.backgrounds.download = prepared.reference
    workspace._refresh_workspace_background()
    workspace.show()
    flush()
    header = workspace._download_header
    label = header.title
    label.hide()
    backdrop = header.grab().toImage()
    point = label.mapTo(header, QPoint(24, label.height() // 2))
    background = backdrop.pixelColor(round(point.x() * backdrop.devicePixelRatio()), round(point.y() * backdrop.devicePixelRatio())).name()
    label.show()
    assert contrast_ratio(label.palette().color(QPalette.WindowText).name(), background) >= 4.5
    theme.deleteLater()


def test_main_wallpaper_changes_chrome_and_dialog_inherits_opening_page(workspace, qtbot, qapp):
    theme = ThemeManager(qapp, mode="dark")
    workspace.show()
    flush()
    regions = (workspace._sidebar, workspace._download_header, workspace._status_bar)

    def samples():
        image = workspace.grab().toImage()
        dpr = image.devicePixelRatio()
        length = round(10 * dpr)
        patches = []
        for widget in regions:
            points = [widget.mapTo(workspace, QPoint(x, widget.height() // 2 - 5))
                      for x in (12, widget.width() // 3, widget.width() // 2, widget.width() - 14)]
            patches.append([image.copy(QRect(round(point.x() * dpr), round(point.y() * dpr), length, length))
                            for point in points])
        return patches

    previous = samples()
    workspace._settings.appearance.backgrounds.download = BUILTIN_BACKGROUNDS[0].reference
    workspace._settings.appearance.background_visibility.download = BackgroundVisibility(light=100, dark=100)
    workspace._refresh_workspace_background()
    flush()
    for widget, first, second in zip(regions, previous, samples()):
        assert first != second, widget.objectName()

    dialog = AppDialog(workspace)
    qtbot.addWidget(dialog)
    dialog.show()
    flush()
    assert dialog.backdrop.image.cacheKey() == workspace.backdrop.image.cacheKey()
    workspace._show_workspace(1)
    assert workspace.backdrop.image.isNull() and not dialog.backdrop.image.isNull()
    dialog.hide()
    dialog.show()
    flush()
    assert dialog.backdrop.image.isNull()
    theme.deleteLater()
