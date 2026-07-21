"""System-aware application theme management."""

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QPalette

from bilibili_downloader.gui.resources import load_stylesheet


class ThemeManager(QObject):
    """Apply and live-update the theme based on the operating system setting."""

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._is_dark = False
        style_hints = app.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self._on_color_scheme_changed)
        self.apply_theme(self._system_prefers_dark())

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
        self._app.setStyleSheet(load_stylesheet(is_dark))
        for widget in self._app.topLevelWidgets():
            widget.setProperty("darkTheme", is_dark)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
