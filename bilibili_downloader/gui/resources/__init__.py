"""GUI resources package."""

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.styles import DARK_STYLE, LIGHT_OVERRIDES


def load_stylesheet(is_dark: bool = True) -> str:
    """Return the complete stylesheet for the requested system theme."""
    stylesheet = DARK_STYLE if is_dark else DARK_STYLE + LIGHT_OVERRIDES
    assets = {
        "__CHECKMARK_ICON__": "checkmark.svg",
    }
    for marker, filename in assets.items():
        stylesheet = stylesheet.replace(
            marker, asset_path(filename).replace("\\", "/")
        )
    return stylesheet
