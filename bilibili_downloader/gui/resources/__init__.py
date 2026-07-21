"""GUI resources package."""

from bilibili_downloader.gui.resources.styles import DARK_STYLE, LIGHT_OVERRIDES


def load_stylesheet(is_dark: bool = True) -> str:
    """Return the complete stylesheet for the requested system theme."""
    if is_dark:
        return DARK_STYLE
    return DARK_STYLE + LIGHT_OVERRIDES
