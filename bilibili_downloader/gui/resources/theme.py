"""System-aware application theme and typography management."""

import sys

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QAbstractButton

from bilibili_downloader.gui.resources import load_stylesheet
from bilibili_downloader.gui.resources.styles import theme_palette

DEFAULT_FONT_POINT_SIZE = 10.5
REFERENCE_LOGICAL_DPI = 96.0


class _ButtonFocusFilter(QObject):
    """Distinguish keyboard focus from a mouse click without changing geometry."""

    def eventFilter(self, target, event):
        if isinstance(target, QAbstractButton):
            kind = event.type()
            if kind == QEvent.FocusIn:
                visible = event.reason() in (
                    Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason,
                )
            elif kind in (QEvent.FocusOut, QEvent.MouseButtonPress):
                visible = False
            elif kind == QEvent.KeyPress:
                visible = True
            else:
                return False
            if target.property("keyboardFocus") != visible:
                target.setProperty("keyboardFocus", visible)
                target.style().unpolish(target)
                target.style().polish(target)
                target.update()
        return False


def platform_font_scale(platform: str, logical_dpi: float) -> float:
    """Keep macOS point sizes at the same logical size as the 96-DPI preview.

    Cocoa reports 72 logical DPI, while Qt's offscreen renderer reports 96.
    Device pixel ratio is deliberately excluded: Qt already scales for Retina.
    Windows/Linux keep their native point-size and text-scaling behavior.
    """
    if logical_dpi <= 0:
        raise ValueError("logical DPI must be positive")
    if platform == "darwin":
        return REFERENCE_LOGICAL_DPI / logical_dpi
    return 1.0


class ThemeManager(QObject):
    """Apply and live-update the theme based on the operating system setting."""

    changed = Signal()

    def __init__(self, app, theme_id="star_trail", mode="system"):
        super().__init__(app)
        self._app = app
        self._is_dark = False
        self._theme_id = theme_id
        self._mode = "system"
        self._native_dark = app.palette().color(QPalette.Window).lightness() < 128
        if not hasattr(app, "_button_focus_filter"):
            app._button_focus_filter = _ButtonFocusFilter(app)
            app.installEventFilter(app._button_focus_filter)
        screen = app.primaryScreen()
        dpi = screen.logicalDotsPerInchY() if screen else REFERENCE_LOGICAL_DPI
        self._font_scale = platform_font_scale(sys.platform, dpi)
        self._apply_platform_font()
        style_hints = app.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self._on_color_scheme_changed)
        self.set_mode(mode)

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
        font.setStyleStrategy(QFont.PreferAntialias)
        font.setHintingPreference(
            QFont.PreferFullHinting if sys.platform == "win32" else QFont.PreferDefaultHinting
        )
        self._font_family = font.family()
        self._app.setFont(font)

    @property
    def is_dark(self) -> bool:
        return self._is_dark

    @property
    def theme_id(self) -> str:
        return self._theme_id

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in ("system", "light", "dark") else "system"
        hints = self._app.styleHints()
        if hasattr(hints, "setColorScheme"):
            hints.setColorScheme({
                "system": Qt.ColorScheme.Unknown,
                "light": Qt.ColorScheme.Light,
                "dark": Qt.ColorScheme.Dark,
            }[self._mode])
        self.apply_theme(self._system_prefers_dark() if self._mode == "system" else self._mode == "dark")

    def set_color_theme(self, theme_id: str) -> None:
        self._theme_id = theme_id if theme_id in ("star_trail", "bilibili_blue") else "star_trail"
        self.apply_theme(self._is_dark)

    def _system_prefers_dark(self) -> bool:
        scheme = self._app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        return self._native_dark

    def _on_color_scheme_changed(self, scheme):
        if self._mode != "system":
            return
        if scheme == Qt.ColorScheme.Unknown:
            self.apply_theme(self._system_prefers_dark())
        else:
            self.apply_theme(scheme == Qt.ColorScheme.Dark)

    def apply_theme(self, is_dark: bool) -> None:
        """Apply a theme immediately; also useful for visual verification."""
        self._is_dark = is_dark
        self._app.setProperty("darkTheme", is_dark)
        self._app.setProperty("colorTheme", self._theme_id)
        self._app.setProperty("appearanceMode", self._mode)
        colors = theme_palette(is_dark, self._theme_id)
        palette = QPalette(self._app.palette())
        for role, color in (
            (QPalette.Window, colors.background),
            (QPalette.WindowText, colors.text),
            (QPalette.Base, colors.surface),
            (QPalette.Text, colors.text),
            (QPalette.Button, colors.surface_raised),
            (QPalette.ButtonText, colors.text),
            (QPalette.PlaceholderText, colors.muted),
            (QPalette.Link, colors.active_text),
            (QPalette.Highlight, colors.text_selection),
            (QPalette.HighlightedText, colors.text_selection_text),
        ):
            palette.setColor(role, QColor(color))
        self._app.setPalette(palette)
        self._app.setStyleSheet(
            load_stylesheet(
                is_dark, font_scale=self._font_scale, font_family=self._font_family,
                theme_id=self._theme_id,
            )
        )
        for widget in self._app.topLevelWidgets():
            widget.setProperty("darkTheme", is_dark)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.changed.emit()
