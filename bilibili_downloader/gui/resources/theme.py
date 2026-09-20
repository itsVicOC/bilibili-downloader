"""System-aware application theme and typography management."""

import sys

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QFont, QFontDatabase, QPalette

from bilibili_downloader.gui.resources import load_stylesheet

DEFAULT_FONT_POINT_SIZE = 10.0
MACOS_FONT_SCALE = 1.15


class ThemeManager(QObject):
    """Apply and live-update the theme based on the operating system setting."""

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._is_dark = False
        self._font_scale = MACOS_FONT_SCALE if sys.platform == "darwin" else 1.0
        self._apply_platform_font()
        style_hints = app.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self._on_color_scheme_changed)
        self.apply_theme(self._system_prefers_dark())

    def _apply_platform_font(self) -> None:
        """Use a native CJK UI font while preserving platform DPI scaling."""
        if sys.platform == "darwin":
            candidates = ("PingFang SC", "Hiragino Sans GB")
        elif sys.platform == "win32":
            candidates = ("Microsoft YaHei UI", "Microsoft YaHei")
        else:
            candidates = ("Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Micro Hei")

        available = set(QFontDatabase.families())
        family = next((name for name in candidates if name in available), "")
        font = QFont(self._app.font())
        if family:
            font.setFamily(family)
        font.setPointSizeF(DEFAULT_FONT_POINT_SIZE * self._font_scale)
        self._app.setFont(font)

    @property
    def is_dark(self) -> bool:
        return self._is_dark

    def _system_prefers_dark(self) -> bool:
        scheme = self._app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        window = self._app.palette().color(QPalette.Window)
        return window.lightness() < 128

    def _on_color_scheme_changed(self, scheme):
        if scheme == Qt.ColorScheme.Unknown:
            self.apply_theme(self._system_prefers_dark())
        else:
            self.apply_theme(scheme == Qt.ColorScheme.Dark)

    def apply_theme(self, is_dark: bool) -> None:
        """Apply a theme immediately; also useful for visual verification."""
        self._is_dark = is_dark
        self._app.setProperty("darkTheme", is_dark)
        self._app.setStyleSheet(
            load_stylesheet(is_dark, font_scale=self._font_scale)
        )
        for widget in self._app.topLevelWidgets():
            widget.setProperty("darkTheme", is_dark)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
