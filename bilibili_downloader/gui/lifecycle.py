"""Desktop window residency, tray access and application-level quit routing."""

import sys

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from bilibili_downloader.core.models import TaskStatus, WindowCloseAction
from bilibili_downloader.gui.dialogs.close_dialog import CloseWindowDialog
from bilibili_downloader.gui.resources.paths import asset_path


class ApplicationLifecycle(QObject):
    def __init__(self, app, window, *, desktop_platform=None, tray_factory=QSystemTrayIcon):
        super().__init__(window)
        self.app, self.window = app, window
        self.platform = desktop_platform or sys.platform
        self._allow_quit = False
        self._disposed = False
        self._dialog = None
        self._tray_factory = tray_factory
        self._tray_notified = False
        self._restore_state = None
        self._previous_quit_on_close = app.quitOnLastWindowClosed()
        self.tray = None
        window._lifecycle = self
        if self.platform in ("darwin", "win32"):
            app.setQuitOnLastWindowClosed(False)
        app.installEventFilter(self)
        if self.platform == "win32":
            self.tray = tray_factory(QIcon(asset_path("app_icon.ico")), self)
            self.tray_menu = QMenu(window)
            for label, callback in (
                ("显示主窗口", self.restore_window),
                ("任务中心", lambda: self._open_workspace(2)),
                ("设置", lambda: self._open_workspace(3)),
            ):
                self.tray_menu.addAction(label, callback)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction(window._actions["quit"])
            self.tray.setContextMenu(self.tray_menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.messageClicked.connect(self.restore_window)
            self.tray.show()
            self.refresh_activity()

    def eventFilter(self, target, event):
        if target is self.app and not self._disposed:
            if event.type() == QEvent.Quit and not self._allow_quit:
                event.ignore()
                # Avoid running a nested dialog inside a native termination callback.
                QTimer.singleShot(0, self.window.request_quit)
                return True
            if (event.type() == QEvent.ApplicationActivate and self.platform == "darwin"
                    and self.window.isHidden() and not self.window._quit_requested):
                QTimer.singleShot(0, self.restore_window)
        return False

    def tray_available(self):
        return self.tray is not None and self._tray_factory.isSystemTrayAvailable()

    def close_window(self):
        if self.platform == "darwin":
            self.hide_window()
            return
        if self._dialog is not None:
            self._dialog.raise_()
            self._dialog.activateWindow()
            return
        action = self.window._settings.windows_close_action
        if action == WindowCloseAction.QUIT:
            self.window.request_quit()
            return
        if action == WindowCloseAction.TRAY and self.tray_available():
            self.hide_window()
            return
        dialog = CloseWindowDialog(
            self.window, active=self.window.has_background_tasks(),
            tray_available=self.tray_available(),
        )
        self._dialog = dialog
        try:
            choice = dialog.exec()
            remember = dialog.remember.isChecked()
        finally:
            self._dialog = None
            dialog.deleteLater()
        if choice == CloseWindowDialog.TRAY:
            # The shell may have disappeared while the dialog was open.
            if not self.tray_available():
                self.window._status_bar.showMessage("系统托盘不可用，窗口已保持打开。")
                return
            if remember:
                self.window.remember_close_action(WindowCloseAction.TRAY)
            self.hide_window()
        elif choice == CloseWindowDialog.QUIT:
            if self.window.request_quit(confirmed=True) and remember:
                self.window.remember_close_action(WindowCloseAction.QUIT)

    def hide_window(self):
        self.window.flush_window_state()
        self._restore_state = self.window.windowState() & ~Qt.WindowMinimized
        self.window.hide()
        if self.tray and not self._tray_notified:
            self._tray_notified = True
            if self.tray.supportsMessages():
                self.tray.showMessage(
                    "BiliFlow 正在后台运行", "后台任务将继续运行。点击托盘图标可恢复窗口。",
                    QSystemTrayIcon.Information, 5000,
                )

    def restore_window(self):
        if self._disposed:
            return
        if self._restore_state is not None:
            self.window.setWindowState(self._restore_state)
            self._restore_state = None
        elif self.window.isMinimized():
            self.window.setWindowState(self.window.windowState() & ~Qt.WindowMinimized)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        if not self.window._quit_requested:
            self.window.show_deferred_update()

    def _open_workspace(self, index):
        self.restore_window()
        if not self.window._quit_requested:
            self.window._show_workspace(index)

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_window()

    def refresh_activity(self):
        if not self.tray:
            return
        downloads = sum(state in {TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.MERGING}
                        for state in self.window._download_list._states.values())
        rows = self.window._live_controller.rows
        self.tray.setToolTip(
            f"BiliFlow\n下载 {downloads} · 录制 {sum(bool(row['active']) for row in rows)}"
            f" · 监控 {sum(bool(row.get('enabled')) for row in rows)}"
            f" · 导出 {int(self.window._live_controller.exporting)}"
        )

    def finish_quit(self):
        self._allow_quit = True
        if self.tray:
            self.tray.hide()
        QTimer.singleShot(0, self.app.quit)

    def dispose(self):
        """Detach a lifecycle when a host/test destroys an embedded window."""
        if self._disposed:
            return
        self._disposed = True
        self.app.removeEventFilter(self)
        self.app.setQuitOnLastWindowClosed(self._previous_quit_on_close)
        if self.tray:
            self.tray.hide()
        self.window._lifecycle = None
