#!/usr/bin/env python3
"""Export the approved ImageGen originals as bounded runtime wallpapers."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilibili_downloader.core.builtin_backgrounds import (
    BUILTIN_BACKGROUNDS,
    STYLE_TITLES,
    WORKSPACE_TITLES,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Export completed originals during production",
    )
    args = parser.parse_args()
    originals = ROOT / "docs/images/backgrounds/originals"
    assets = ROOT / "bilibili_downloader/gui/assets"
    (assets / "backgrounds").mkdir(parents=True, exist_ok=True)
    completed = []
    for entry in BUILTIN_BACKGROUNDS:
        source = originals / f"{entry.id}.png"
        if not source.exists() and args.partial:
            continue
        pixel = entry.style == "pixel"
        method = Image.Resampling.NEAREST if pixel else Image.Resampling.LANCZOS
        size = (640, 360) if pixel else (2560, 1440)
        with Image.open(source) as original:
            image = ImageOps.fit(original.convert("RGB"), size, method=method)
        if pixel:
            image.save(assets / entry.image, optimize=True)
        else:
            image.save(assets / entry.image, quality=88, method=6)
        image.resize((320, 180), method).save(assets / entry.thumbnail, optimize=True)
        completed.append(entry)
    runtime_size = sum(
        path.stat().st_size
        for path in (assets / "backgrounds").iterdir()
        if path.is_file()
    )
    if runtime_size > 12 * 1024 * 1024:
        raise ValueError(f"Runtime collection exceeds 12 MiB: {runtime_size} bytes")
    print(
        f"Exported {len(completed)} wallpapers; runtime total {runtime_size / 1024 / 1024:.2f} MiB"
    )
    if len(completed) != len(BUILTIN_BACKGROUNDS):
        return
    fonts = (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    )
    font = next(
        (ImageFont.truetype(path, 21) for path in fonts if Path(path).exists()),
        ImageFont.load_default(),
    )
    small = next(
        (ImageFont.truetype(path, 15) for path in fonts if Path(path).exists()),
        ImageFont.load_default(),
    )
    overview = Image.new("RGB", (1536, 1336), "#f0f3f7")
    draw = ImageDraw.Draw(overview)
    draw.text((24, 12), "小流 · 十二景 / BiliFlow", font=font, fill="#27364a")
    for i, entry in enumerate(completed):
        x, y = 24 + i % 3 * 504, 54 + i // 3 * 320
        with Image.open(assets / entry.image) as image:
            overview.paste(
                image.resize(
                    (480, 270),
                    Image.Resampling.NEAREST
                    if entry.style == "pixel"
                    else Image.Resampling.LANCZOS,
                ),
                (x, y),
            )
        draw.text((x, y + 276), entry.title, font=font, fill="#243347")
        draw.text(
            (x + 190, y + 281),
            f"{WORKSPACE_TITLES[entry.workspace]} · {STYLE_TITLES[entry.style]}",
            font=small,
            fill="#627086",
        )
    overview.save(originals.parent / "xiaoliu-collection.jpg", quality=92)


if __name__ == "__main__":
    main()
