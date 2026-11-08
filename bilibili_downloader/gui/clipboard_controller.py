"""Foreground-only, event-driven clipboard offers; parsing requires confirmation."""

import hashlib

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
)
from shiboken6 import isValid

from bilibili_downloader.gui.widgets.components import ElidedLabel
from bilibili_downloader.utils.clipboard_sources import (
    MAX_CLIPBOARD_CHARACTERS,
    extract_clipboard_sources,
)


def clipboard_access_allowed(window):
    return (window.isVisible() and not window.isMinimized()
            and QApplication.instance().applicationState() == Qt.ApplicationActive)


class ClipboardPrompt(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ClipboardPrompt")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("SectionTitle")
        self.title.setTextFormat(Qt.PlainText)
        layout.addWidget(self.title)
        self.summary = ElidedLabel()
        layout.addWidget(self.summary)
        self.explanation = QLabel()
        self.explanation.setObjectName("MetaLabel")
        self.explanation.setWordWrap(True)
        self.explanation.setTextFormat(Qt.PlainText)
        layout.addWidget(self.explanation)
        actions = QHBoxLayout()
        actions.addStretch()
        self.ignore = QPushButton("忽略")
        self.ignore.setObjectName("TableSubtleButton")
        self.confirm = QPushButton("解析")
        self.confirm.setObjectName("ClipboardResolveButton")
        for button in (self.ignore, self.confirm):
            button.setFixedHeight(32)
            button.setCursor(Qt.PointingHandCursor)
            button.setAutoDefault(False)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.hide()


class ClipboardController(QObject):
    def __init__(self, window, *, clipboard=None, foreground=None):
        super().__init__(window)
        self.window = window
        self.clipboard = clipboard if clipboard is not None else QApplication.clipboard()
        self.foreground = foreground or (lambda: clipboard_access_allowed(window))
        self.prompt = ClipboardPrompt(window._workspace_pages)
        self.candidate = None
        self._content = None
        self._handled = None
        self._disposed = False
        self._refreshing = False
        self._menu_depth = 0
        self._menus = window.menuBar().findChildren(QMenu)
        for menu in self._menus:
            menu.aboutToShow.connect(self._menu_opened)
            menu.aboutToHide.connect(self._menu_closed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.check)
        self.clipboard.dataChanged.connect(self.schedule)
        app = QApplication.instance()
        app.applicationStateChanged.connect(self.schedule)
        app.focusWindowChanged.connect(self.schedule)
        # Filtering only lifecycle/show events does not inspect clipboard content.
        app.installEventFilter(self)
        self.prompt.ignore.clicked.connect(self.dismiss)
        self.prompt.confirm.clicked.connect(self.confirm)
        window._url_input.textChanged.connect(self.refresh_prompt)
        window._batch_page._url_text.textChanged.connect(self.refresh_prompt)
        window._batch_page._resolve_btn.installEventFilter(self)
        window._resolve_btn.installEventFilter(self)
        self.schedule()

    def available(self):
        w = self.window
        return (not self._disposed and isValid(w) and w._settings.clipboard_monitor_enabled
                and not w._startup_paused and not w._quit_requested and not w._update_in_progress
                and getattr(w, "_shell_enabled", True) and w.isVisible() and not w.isMinimized() and self.foreground()
                and not self._menu_depth
                and QApplication.activeModalWidget() is None and QApplication.activePopupWidget() is None)

    def _menu_opened(self):
        # Cocoa's native menu bar does not create an activePopupWidget.
        self._menu_depth += 1
        self.schedule()

    def _menu_closed(self):
        self._menu_depth = max(0, self._menu_depth - 1)
        QTimer.singleShot(0, self, self.schedule)

    def schedule(self, *_args):
        if self._disposed:
            return
        if not self.available():
            self.timer.stop()
            self.prompt.hide()
            return
        self.timer.start()

    def check(self):
        if not self.available():
            self.prompt.hide()
            return
        mime = self.clipboard.mimeData()
        if mime is None or not mime.hasText() or (mime.hasUrls() and any(url.isLocalFile() for url in mime.urls())):
            self._replace(None, None)
            return
        text = mime.text()
        if len(text) > MAX_CLIPBOARD_CHARACTERS:
            self._replace(None, None)
            return
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        if digest != self._content:
            self._handled = None
        candidate = extract_clipboard_sources(text)
        self._replace(candidate, digest)

    def _replace(self, candidate, digest):
        self._content = digest
        self.candidate = candidate
        self.refresh_prompt()

    def refresh_prompt(self, *_args):
        if self._refreshing or self._disposed:
            return
        self._refreshing = True
        try:
            candidate = self.candidate
            if (candidate is None or not self.available() or self._handled == candidate.fingerprint
                    or self.window._clipboard_source_is_current(candidate)):
                self.prompt.hide()
                return
            count = len(candidate.sources)
            source_type = "短链" if candidate.target == "auto" else "作品／单集" if candidate.target == "single" else "下载来源"
            self.prompt.title.setText(f"发现 {count} 个 B 站{source_type}")
            self.prompt.summary.set_full_text(candidate.sources[0] + (f" 等 {count} 个来源" if count > 1 else ""))
            occupied = self.window._clipboard_target_occupied(candidate.target)
            self.prompt.confirm.setText("替换并解析" if occupied else "批量解析" if candidate.target == "batch" else "解析")
            self.prompt.explanation.setText(
                ("短链展开后可能替换单个或批量解析区的现有内容，已加入的任务不受影响。" if candidate.target == "auto" else "将替换对应解析区的现有来源和结果，已加入的下载任务不受影响。") if occupied else
                "确认后读取作品信息，不会自动加入下载队列。"
            )
            busy = self.window._clipboard_resolution_busy()
            self.prompt.confirm.setEnabled(not busy)
            self.prompt.confirm.setToolTip("请等待当前解析完成，再确认新来源。" if busy else "")
            self.reposition()
            self.prompt.show()
            self.prompt.raise_()
        finally:
            self._refreshing = False

    def reposition(self):
        area = self.window._workspace_pages
        width = min(480, max(0, area.width() - 32))
        self.prompt.setFixedWidth(width)
        self.prompt.adjustSize()
        self.prompt.move(max(16, area.width() - width - 16), 16)

    def dismiss(self):
        if self.candidate:
            self._handled = self.candidate.fingerprint
        self.prompt.hide()

    def confirm(self):
        snapshot = self.candidate
        if snapshot is None or not self.available() or self.window._clipboard_resolution_busy():
            return
        if self.window._accept_clipboard_source(snapshot):
            # The displayed snapshot, rather than a new read, is the confirmed input.
            self._handled = snapshot.fingerprint
            self.prompt.hide()

    def settings_changed(self):
        if not self.window._settings.clipboard_monitor_enabled:
            self.timer.stop()
            self.candidate = self._content = self._handled = None
            self.prompt.hide()
        else:
            self.schedule()

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.timer.stop()
        self.prompt.hide()
        self.clipboard.dataChanged.disconnect(self.schedule)
        self.window._url_input.textChanged.disconnect(self.refresh_prompt)
        self.window._batch_page._url_text.textChanged.disconnect(self.refresh_prompt)
        for menu in self._menus:
            if isValid(menu):
                menu.aboutToShow.disconnect(self._menu_opened)
                menu.aboutToHide.disconnect(self._menu_closed)
        self._menus.clear()
        app = QApplication.instance()
        app.applicationStateChanged.disconnect(self.schedule)
        app.focusWindowChanged.disconnect(self.schedule)
        app.removeEventFilter(self)

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.window and kind == QEvent.DeferredDelete:
            self.dispose()
        elif kind in (QEvent.WindowActivate, QEvent.WindowDeactivate, QEvent.ApplicationActivate,
                      QEvent.ApplicationDeactivate, QEvent.Show, QEvent.Hide):
            self.schedule()
        elif watched is self.window._workspace_pages and kind == QEvent.Resize:
            if self.prompt.isVisible():
                self.reposition()
        elif kind == QEvent.EnabledChange and watched in (self.window._resolve_btn, self.window._batch_page._resolve_btn):
            QTimer.singleShot(0, self, self.refresh_prompt)
        return False
