"""GUI resources package."""

from bilibili_downloader.gui.resources.styles import DARK_STYLE


def load_stylesheet() -> str:
    """Return the dark theme QSS stylesheet."""
    return DARK_STYLE
