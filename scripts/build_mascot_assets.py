#!/usr/bin/env python3
"""Pack the selected ImageGen artwork into a small, stable pixel atlas."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/images/mascot/xiaoliu-imagegen.png"
ASSETS = ROOT / "bilibili_downloader/gui/assets"
PREVIEWS = SOURCE.parent
DURATIONS = [1600, 650, 80, 120, 80, 1470]


def main():
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != (2172, 724):
        raise ValueError("Expected the selected six-cell ImageGen source (2172×724)")
    cells = []
    for index in range(4):
        cell = source.crop((362 * index, 0, 362 * (index + 1), 724))
        # One shared crop and baseline: no frame-by-frame fitting or stretching.
        square = Image.new("RGBA", (592, 592))
        square.paste(cell, (115, -70))
        frame = square.resize((40, 40), Image.Resampling.NEAREST)
        frame.putalpha(frame.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
        cells.append(frame)

    neutral = cells[0]

    def pose(eyes=None, sway=False):
        # Reuse the neutral body; extract only the generated animated regions.
        # This also excludes the source sheet's incorrectly mirrored last cell.
        frame = neutral.copy()
        if sway:
            for region in ((28, 5, 33, 22), (8, 17, 12, 22)):
                frame.paste(cells[1].crop(region), region[:2])
        if eyes is not None:
            region = (12, 13, 27, 18)
            frame.paste(cells[eyes].crop(region), region[:2])
        return frame

    frames = [
        neutral,
        pose(sway=True),
        pose(2, True),
        pose(3, True),
        pose(2, True),
        neutral,
    ]
    atlas = Image.new("RGBA", (240, 40))
    for index, frame in enumerate(frames):
        atlas.paste(frame, (index * 40, 0))
    # A shared palette keeps colors stable across all six frames.
    indexed = atlas.quantize(
        colors=24, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE
    )
    atlas = indexed.convert("RGBA")
    ASSETS.mkdir(parents=True, exist_ok=True)
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    atlas.save(ASSETS / "xiaoliu_idle.png", optimize=True)
    still = atlas.crop((0, 0, 40, 40))
    still.save(ASSETS / "xiaoliu.png", optimize=True)
    still.resize((320, 320), Image.Resampling.NEAREST).save(
        PREVIEWS / "xiaoliu-preview.png"
    )
    atlas.resize((1440, 240), Image.Resampling.NEAREST).save(
        PREVIEWS / "xiaoliu-atlas.png"
    )
    animated = [
        indexed.crop((i * 40, 0, (i + 1) * 40, 40)).resize(
            (240, 240), Image.Resampling.NEAREST
        )
        for i in range(6)
    ]
    animated[0].save(
        PREVIEWS / "xiaoliu-idle.gif",
        save_all=True,
        append_images=animated[1:],
        duration=DURATIONS,
        loop=0,
        disposal=2,
        optimize=False,
        transparency=indexed.getpixel((0, 0)),
    )


if __name__ == "__main__":
    main()
