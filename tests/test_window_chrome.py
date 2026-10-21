"""Caption visibility without losing desktop window identity or controls."""

import ctypes
import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.window_chrome import WindowChrome


def test_expanded_windows_caption_preserves_identity_and_controls(qtbot):
    window = QMainWindow()
    qtbot.addWidget(window)
    window.setWindowTitle("BiliFlow · 星轨收藏站")
    window.setWindowIcon(QIcon(asset_path("app_icon.png")))
    chrome = WindowChrome(window, "win32")
    assert window.windowFlags() & Qt.CustomizeWindowHint
    assert window.windowFlags() & Qt.WindowCloseButtonHint
    window.resize(900, 640)
    window.show()
    qtbot.waitUntil(lambda: not window.windowHandle().flags() & Qt.WindowTitleHint)
    handle = window.windowHandle()
    for transition in (window.showMaximized, window.showNormal, window.hide, window.show):
        transition()
        QApplication.processEvents()
        chrome._sync_native()
        assert not handle.flags() & Qt.WindowTitleHint
        assert not handle.flags() & Qt.FramelessWindowHint
        for flag in (
            Qt.ExpandedClientAreaHint, Qt.CustomizeWindowHint, Qt.WindowSystemMenuHint,
            Qt.WindowMinimizeButtonHint, Qt.WindowMaximizeButtonHint, Qt.WindowCloseButtonHint,
        ):
            assert handle.flags() & flag
        assert handle.title() == window.windowTitle() == "BiliFlow · 星轨收藏站"
        assert not handle.icon().isNull() and not window.windowIcon().isNull()

    # QWidget can reapply its normalized flags when recreating/configuring the
    # window. The next show must clear the duplicate caption again.
    window.hide()
    handle.setFlags(Qt.WindowType(
        (int(handle.flags()) | int(Qt.WindowTitleHint))
        & ~int(Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
    ))
    window.show()
    qtbot.waitUntil(lambda: not handle.flags() & Qt.WindowTitleHint)
    dialog = QDialog(window)
    qtbot.addWidget(dialog)
    dialog.setWindowTitle("选择背景")
    dialog.show()
    assert dialog.windowHandle().flags() & Qt.WindowTitleHint
    assert not dialog.windowHandle().flags() & Qt.ExpandedClientAreaHint


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows")
def test_windows_native_caption_keeps_taskbar_icon_resize_and_system_menu(qtbot, qapp):
    if qapp.platformName() != "windows":
        pytest.skip("Requires the Windows Qt backend")
    from ctypes import wintypes

    window = QMainWindow()
    qtbot.addWidget(window)
    window.setWindowTitle("BiliFlow · 星轨收藏站")
    window.setWindowIcon(QIcon(asset_path("app_icon.png")))
    chrome = WindowChrome(window, "win32")
    window.show()
    qtbot.waitUntil(lambda: not window.windowHandle().flags() & Qt.WindowTitleHint)
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user32.GetSystemMenu.restype = wintypes.HMENU
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    hwnd = wintypes.HWND(int(window.winId()))
    for transition in (window.showMaximized, window.showNormal):
        transition()
        QApplication.processEvents()
        chrome._sync_native()
        style = user32.GetWindowLongW(hwnd, -16)
        # WS_THICKFRAME, WS_SYSMENU, WS_MINIMIZEBOX, WS_MAXIMIZEBOX.
        assert style & 0x00040000 and style & 0x00080000
        assert style & 0x00020000 and style & 0x00010000
        assert not user32.GetWindowLongW(hwnd, -20) & 0x00000080  # WS_EX_TOOLWINDOW
        assert user32.GetSystemMenu(hwnd, False)
        assert user32.SendMessageW(hwnd, 0x007F, 1, 0)  # WM_GETICON / ICON_BIG
        assert not window.windowHandle().flags() & Qt.WindowTitleHint
