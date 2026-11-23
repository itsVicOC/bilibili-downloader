"""Verify the distinct illustrations and actions of the existing empty states."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QPushButton

from bilibili_downloader.core.models import VideoPage
from bilibili_downloader.gui.dialogs.naming_fields import NamingFieldDialog
from bilibili_downloader.gui.dialogs.page_selection import PageSelectionDialog
from bilibili_downloader.gui.widgets import components
from bilibili_downloader.gui.widgets.components import MascotIllustration
from tests.test_workspaces import workspace as workspace

SCENES = {
    "download_source", "live_empty", "downloads_empty", "downloads_filtered",
    "recordings_empty", "recording_history_empty", "files_empty", "files_filtered",
    "files_loading", "files_error", "batch_filtered", "parts_filtered", "naming_filtered",
}


def _action(container, text):
    return next(button for button in container.findChildren(QPushButton) if button.text() == text)


def test_every_shared_empty_state_has_distinct_offline_art(workspace, qtbot):
    parts = PageSelectionDialog([VideoPage(cid=1, page=1, part="样片")], set(), workspace)
    naming = NamingFieldDialog({"title": ("作品名", "示例")}, workspace)
    qtbot.addWidget(parts)
    qtbot.addWidget(naming)
    widgets = workspace.findChildren(MascotIllustration)
    assert len(widgets) == len(SCENES)
    assert {widget.scene for widget in widgets} == SCENES
    pixels = set()
    for widget in widgets:
        assert widget.focusPolicy() == Qt.NoFocus
        assert widget.testAttribute(Qt.WA_TransparentForMouseEvents)
        path = components.asset_path(f"xiaoliu_state_{widget.scene}.png")
        with Image.open(path) as art:
            assert art.mode == "RGBA" and art.size == (96, 54)
            alpha = art.getchannel("A")
            assert alpha.getextrema() == (0, 255)
            left, top, right, bottom = alpha.getbbox()
            assert 0 < left < right < art.width and 0 < top < bottom < art.height
            pixels.add(art.tobytes())
        assert widget.art.toImage() == QPixmap(path).toImage()
    assert len(pixels) == len(SCENES)

    for dialog in (parts, naming):
        dialog.search.setText("没有这个关键词")
        assert dialog.results.currentIndex() == 1
        _action(dialog.results.currentWidget(), "清除搜索").click()
        assert dialog.search.text() == ""
        assert dialog.results.currentIndex() == 0


def test_mascot_uses_static_character_if_artwork_cannot_load(qtbot, tmp_path, monkeypatch):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"bad image")
    static_path = Path(components.asset_path("xiaoliu.png"))
    monkeypatch.setattr(
        components, "asset_path", lambda name: str(static_path if name == "xiaoliu.png" else broken),
    )
    illustration = MascotIllustration("live_empty")
    qtbot.addWidget(illustration)
    assert illustration.art.toImage() == QPixmap(str(static_path)).toImage()
    assert (illustration.width(), illustration.height()) == (176, 99)


def test_mascot_empty_states_keep_navigation_and_retry_actions(workspace, tmp_path, monkeypatch):
    workspace.show()
    workspace._show_workspace(1)
    live = workspace._live_page
    _action(live._room_stack.currentWidget(), "添加房间").click()
    assert workspace.focusWidget() is live.source
    workspace._show_workspace(2)
    tasks = workspace._task_page
    _action(tasks._download_stack.currentWidget(), "去下载").click()
    assert workspace._workspace_pages.currentIndex() == 0

    library = workspace._library_page
    library.set_repository(None)
    assert library.stack.currentWidget().findChild(MascotIllustration).scene == "files_loading"

    def fail():
        raise OSError("fixture")

    monkeypatch.setattr(library, "repository", SimpleNamespace(list_assets=fail, pending_dir=tmp_path))
    requests = []
    monkeypatch.setattr(library, "_run", lambda _job, *, kind: requests.append(kind))
    library.refresh()
    assert library.stack.currentWidget().findChild(MascotIllustration).scene == "files_error"
    _action(library.stack.currentWidget(), "重试").click()
    assert requests == ["recover"]
    assert library.stack.currentWidget().findChild(MascotIllustration).scene == "files_loading"
