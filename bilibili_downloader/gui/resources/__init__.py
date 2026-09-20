"""GUI resources package."""

from bilibili_downloader.gui.resources.paths import asset_path
from bilibili_downloader.gui.resources.styles import (
    DARK_STYLE,
    LIGHT_OVERRIDES,
    build_component_overrides,
    scale_font_sizes,
)


def load_stylesheet(is_dark: bool = True, font_scale: float = 1.0) -> str:
    """Return the complete stylesheet for the requested system theme."""
    stylesheet = DARK_STYLE if is_dark else DARK_STYLE + LIGHT_OVERRIDES
    stylesheet += build_component_overrides(is_dark)
    stylesheet = scale_font_sizes(stylesheet, font_scale)
    assets = {
        "__CHECKMARK_ICON__": "checkmark.svg",
    }
    for marker, filename in assets.items():
        stylesheet = stylesheet.replace(
            marker, asset_path(filename).replace("\\", "/")
        )
    return stylesheet
