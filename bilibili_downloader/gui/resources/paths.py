"""Helpers for locating bundled GUI assets."""

import sys
from pathlib import Path

from bilibili_downloader.core.builtin_backgrounds import builtin_background


def asset_path(name: str) -> str:
    """Return an absolute path for an asset in source and frozen builds."""
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS")) / "bilibili_downloader" / "gui" / "assets"
    else:
        root = Path(__file__).resolve().parents[1] / "assets"
    return str(root / name)


def background_path(reference, store=None, *, thumbnail=False):
    """Resolve only catalog entries or the user's content-addressed imports."""
    entry = builtin_background(reference)
    if entry is not None:
        path = Path(asset_path(entry.thumbnail if thumbnail else entry.image))
        return path if path.is_file() and not path.is_symlink() else None
    return store.path(reference) if store is not None else None
