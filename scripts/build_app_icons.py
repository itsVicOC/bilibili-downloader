"""Build runtime and platform app icons from the public source artwork."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "bilibili_downloader" / "gui" / "assets"


def build_icons() -> None:
    source = Image.open(ASSET_DIR / "app_icon_source.png").convert("RGBA")
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle(
        (34, 34, 990, 990),
        radius=218,
        fill="#18171e",
        outline="#51465d",
        width=12,
    )
    draw.rounded_rectangle(
        (76, 76, 948, 948),
        radius=182,
        outline="#2d2935",
        width=6,
    )
    draw.polygon([(744, 82), (932, 82), (932, 270)], fill="#ff79b3")
    draw.polygon([(92, 754), (92, 932), (270, 932)], fill="#62d5ff")

    artwork = source.resize((760, 760), Image.Resampling.LANCZOS)
    canvas.alpha_composite(artwork, (132, 132))

    canvas.save(ASSET_DIR / "app_icon.png", optimize=True)
    canvas.save(ASSET_DIR / "app_icon.icns", format="ICNS")
    canvas.save(
        ASSET_DIR / "app_icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_icons()
