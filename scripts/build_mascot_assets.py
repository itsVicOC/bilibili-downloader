#!/usr/bin/env python3
"""Pack the selected ImageGen artwork into a small, stable pixel atlas."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/images/mascot/xiaoliu-imagegen.png"
ASSETS = ROOT / "bilibili_downloader/gui/assets"
PREVIEWS = SOURCE.parent
DURATIONS = [1600, 650, 80, 120, 80, 1470]


def build_actions():
    """Normalize generated pose sheets without changing their drawn anatomy."""
    sys.path.insert(0, str(ROOT))
    from bilibili_downloader.gui.widgets.mascot_animation import CLIPS

    destination = PREVIEWS / "actions"
    originals = destination / "originals"
    neutral = Image.open(ASSETS / "xiaoliu.png").convert("RGBA")
    colors = sorted({rgb[:3] for rgb in neutral.get_flattened_data() if rgb[3]})
    palette = Image.new("P", (1, 1))
    palette.putpalette([component for rgb in colors + [colors[-1]] * (256 - len(colors)) for component in rgb])

    def indexed(frame):
        result = frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE)
        result = result.point(lambda index: min(index, len(colors) - 1))
        result.paste(255, mask=frame.getchannel("A").point(lambda a: 255 if a < 128 else 0))
        result.info["transparency"] = 255
        return result

    all_frames = {}
    for key, clip in CLIPS.items():
        if key == "idle":
            source = Image.open(ASSETS / clip.asset).convert("RGBA")
            frames = [source.crop((i * 40, 0, (i + 1) * 40, 40)) for i in range(6)]
        else:
            source = Image.open(originals / f"{key}.png").convert("RGBA")
            if source.width != source.height or source.width % 2:
                raise ValueError(f"{key}: expected an even square 2×2 pose sheet")
            side = source.width // 2
            cells = [source.crop((x * side, y * side, (x + 1) * side, (y + 1) * side))
                     for y in range(2) for x in range(2)]
            for cell in cells:
                cell.putalpha(cell.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
            bounds = [cell.getbbox() for cell in cells]
            if any(box is None for box in bounds):
                raise ValueError(f"{key}: empty pose")
            # One shared scale per sheet; seated poses retain their shorter body.
            height = max(box[3] - box[1] for box in bounds)
            extent = max(max(side / 2 - box[0], box[2] - side / 2) for box in bounds)
            target_height = 30 if key == "doze" else 34 if key == "hop" else 36
            scale = min(target_height / height, 18 / extent)
            poses = []
            for i, (cell, box) in enumerate(zip(cells, bounds)):
                size = round(side * scale)
                small = cell.resize((size, size), Image.Resampling.NEAREST)
                frame = Image.new("RGBA", (40, 40))
                baseline = 36 if key == "hop" and i == 1 else 38
                frame.paste(small, (round(20 - side * scale / 2), baseline - round(box[3] * scale)))
                frame = indexed(frame).convert("RGBA")
                poses.append(frame)
            # Start/end at the existing neutral pose for every action transition.
            frames = [neutral, poses[0], poses[1], poses[2], poses[1], poses[2], poses[3], neutral]
            atlas = Image.new("RGBA", (40 * len(frames), 40))
            for i, frame in enumerate(frames):
                atlas.paste(frame, (i * 40, 0))
            atlas.save(ASSETS / clip.asset, optimize=True)
        all_frames[key] = frames
        animated = [indexed(frame).resize((240, 240), Image.Resampling.NEAREST) for frame in frames]
        animated[0].save(destination / f"xiaoliu-{key}.gif", save_all=True,
                         append_images=animated[1:], duration=clip.durations, loop=0,
                         disposal=2, optimize=False, transparency=255)

    font_path = next((path for path in (Path("/System/Library/Fonts/PingFang.ttc"),
                     Path("/System/Library/Fonts/STHeiti Medium.ttc"),
                     Path("C:/Windows/Fonts/msyh.ttc"),
                     Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")) if path.exists()), Path("missing-font"))
    font = ImageFont.truetype(str(font_path), 18) if font_path.exists() else ImageFont.load_default()
    overview = Image.new("RGB", (960, 660), "#eef6fc")
    draw = ImageDraw.Draw(overview)
    for i, (key, frames) in enumerate(all_frames.items()):
        x, y = (i % 4) * 240, (i // 4) * 220
        enlarged = frames[3].resize((160, 160), Image.Resampling.NEAREST)
        overview.paste(enlarged, (x + 40, y + 12), enlarged)
        draw.text((x + 120, y + 185), CLIPS[key].name if font_path.exists() else key,
                  font=font, fill="#27364a", anchor="mm")
    overview.save(destination / "xiaoliu-actions.png")

    # A synchronized looping overview makes all twelve animations reviewable.
    timeline = []
    for phase in range(8):
        canvas = Image.new("RGB", (960, 660), "#eef6fc")
        draw = ImageDraw.Draw(canvas)
        for i, (key, frames) in enumerate(all_frames.items()):
            x, y = (i % 4) * 240, (i // 4) * 220
            frame = frames[min(phase, len(frames) - 1)].resize((160, 160), Image.Resampling.NEAREST)
            canvas.paste(frame, (x + 40, y + 12), frame)
            draw.text((x + 120, y + 185), CLIPS[key].name if font_path.exists() else key,
                      font=font, fill="#27364a", anchor="mm")
        timeline.append(canvas)
    timeline[0].save(destination / "xiaoliu-actions.gif", save_all=True,
                     append_images=timeline[1:], duration=400, loop=0)


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actions", action="store_true", help="Build the eleven generated full-body actions and previews")
    args = parser.parse_args()
    if args.actions:
        build_actions()
    else:
        main()
