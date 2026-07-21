"""Helpers for locating bundled GUI assets."""

import sys
from pathlib import Path


def asset_path(name: str) -> str:
    """Return an absolute path for an asset in source and frozen builds."""
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS")) / "bilibili_downloader" / "gui" / "assets"
    else:
        root = Path(__file__).resolve().parents[1] / "assets"
    return str(root / name)
