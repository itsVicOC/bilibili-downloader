"""Pure layout decisions shared by live widgets and isolated previews."""

from dataclasses import dataclass

from bilibili_downloader.gui.resources.styles import UI_METRICS


@dataclass(frozen=True)
class LayoutDensity:
    compact: bool
    page_margin: int
    card_padding: int
    section_gap: int
    cover_width: int
    cover_height: int


COMFORTABLE = LayoutDensity(False, 24, 16, 16, 176, 99)
COMPACT = LayoutDensity(True, 16, 12, 12, 128, 72)


def density_for_height(height, previous=None):
    compact = height < 800 if previous is None else height < (824 if previous.compact else 800)
    return COMPACT if compact else COMFORTABLE


def output_side_by_side(width):
    return width >= UI_METRICS.output_split_width


def field_columns(width):
    return 2 if width >= UI_METRICS.download_field_column_width * 2 else 1


def path_preferred_width(font_metrics, text):
    return font_metrics.horizontalAdvance(text) + 8
