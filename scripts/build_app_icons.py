"""Export application icons from the editable BiliFlow artwork."""

import argparse
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "bilibili_downloader" / "gui" / "assets"
ARTWORK_DIR = ROOT / "design" / "branding"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
ICNS_SIZES = (32, 64, 128, 256, 512, 1024)


def _load_artwork(filename: str) -> QSvgRenderer:
    path = ARTWORK_DIR / filename
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ValueError(f"Cannot read icon artwork: {path}")
    return renderer


def _render(renderer: QSvgRenderer, size: int, *, scale: float = 1.0) -> Image.Image:
    canvas = QImage(size, size, QImage.Format_RGBA8888)
    canvas.fill(0)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    inset = size * (1 - scale) / 2
    renderer.render(painter, QRectF(inset, inset, size * scale, size * scale))
    painter.end()
    return Image.frombytes("RGBA", (size, size), bytes(canvas.constBits()))


def build_icons(output_dir: Path = ASSET_DIR) -> None:
    full = _load_artwork("app-icon.svg")
    small = _load_artwork("app-icon-small.svg")
    mac_frames = [_render(full, size) for size in ICNS_SIZES]
    windows_frames = [
        _render(small, size) if size <= 32 else _render(full, size, scale=1.08)
        for size in ICO_SIZES
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    mac_frames[-1].save(output_dir / "app_icon.png", optimize=True)
    mac_frames[-1].save(
        output_dir / "app_icon.icns", append_images=mac_frames,
    )
    windows_frames[-1].save(
        output_dir / "app_icon.ico",
        sizes=[(size, size) for size in ICO_SIZES],
        append_images=windows_frames[:-1],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ASSET_DIR)
    build_icons(parser.parse_args().output_dir)
