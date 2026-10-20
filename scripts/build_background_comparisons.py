"""Compose reproducible before/after UI comparisons from native captures."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "docs" / "images" / "backgrounds"
PAIRS = (
    ("download", "视频下载", "biliflow-background-download-anime-cloud-light.png"),
    ("live", "直播录制", "biliflow-background-live-watercolor-firefly-light.png"),
    ("tasks", "任务中心", "biliflow-background-tasks-pixel-cargo-dark.png"),
    ("settings", "设置", "biliflow-background-settings-watercolor-journal-light.png"),
    ("gallery", "选择背景", "biliflow-background-gallery-980.png"),
)


def main():
    output = ROOT / "comparisons"
    output.mkdir(exist_ok=True)
    font_path = Path("/System/Library/Fonts/STHeiti Medium.ttc")
    if not font_path.is_file():
        raise SystemExit("Set font_path to an installed Chinese font before composing labels.")
    title_font = ImageFont.truetype(str(font_path), 27)
    label_font = ImageFont.truetype(str(font_path), 20)
    sheets = []
    for key, title, filename in PAIRS:
        images = [Image.open(ROOT / folder / filename).convert("RGB")
                  for folder in ("before-optimization", "native")]
        height = round(660 * images[0].height / images[0].width)
        sheet = Image.new("RGB", (1384, height + 110), "#f4f6f8")
        draw = ImageDraw.Draw(sheet)
        draw.text((24, 18), title, font=title_font, fill="#1f2937")
        for index, (label, image) in enumerate(zip(("优化前", "优化后"), images)):
            x = 24 + index * 676
            draw.text((x, 60), label, font=label_font, fill="#526072")
            image = image.resize((660, height), Image.Resampling.LANCZOS)
            sheet.paste(image, (x, 94))
        sheet.save(output / f"{key}-before-after.jpg", quality=92, optimize=True)
        if key != "gallery":
            sheets.append(sheet)
    overview = Image.new("RGB", (1384, sum(s.height for s in sheets) + 16 * (len(sheets) - 1)), "#e6ebf0")
    top = 0
    for sheet in sheets:
        overview.paste(sheet, (0, top))
        top += sheet.height + 16
    overview.save(output / "four-pages-before-after.jpg", quality=92, optimize=True)
    print(output)


if __name__ == "__main__":
    main()
