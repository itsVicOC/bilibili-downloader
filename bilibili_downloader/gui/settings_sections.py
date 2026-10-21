"""Stable destinations shared by navigation, settings and desktop actions."""

from enum import Enum


class SettingsSection(str, Enum):
    DOWNLOAD = "download"
    LIVE = "live"
    APPEARANCE = "appearance"
    TOOLS = "tools"
    ABOUT = "about"


APPEARANCE_MODES = (("跟随系统", "system"), ("日间", "light"), ("夜间", "dark"))
