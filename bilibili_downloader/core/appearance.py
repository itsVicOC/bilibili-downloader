"""Bounded local image import and content-addressed background storage."""

import hashlib
import io
import os
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from bilibili_downloader.core.models import BACKGROUND_REFERENCE

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_EDGE = 3840


@dataclass(frozen=True)
class PreparedBackground:
    reference: str
    png: bytes
    preview: bytes


def prepare_background(path: Path) -> PreparedBackground:
    """Decode in a worker; retain only an oriented, bounded, metadata-free PNG."""
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("图片不能超过 20 MiB")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as original:
                if original.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("请选择静态 PNG、JPEG 或 WebP 图片")
                if getattr(original, "is_animated", False):
                    raise ValueError("暂不支持动画图片，请选择静态图片")
                if original.width * original.height > MAX_IMAGE_PIXELS:
                    raise ValueError("图片不能超过 4000 万像素")
                image = ImageOps.exif_transpose(original)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA")
                image.thumbnail(
                    (MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS
                )
                # A fresh image drops EXIF, ICC and text metadata from the import.
                clean = Image.new("RGBA", image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, format="PNG")
                preview = io.BytesIO()
                clean.thumbnail((320, 180), Image.Resampling.LANCZOS)
                clean.save(preview, format="PNG")
        png = output.getvalue()
        return PreparedBackground(
            hashlib.sha256(png).hexdigest() + ".png", png, preview.getvalue()
        )
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("图片无法读取或已损坏，请重新选择有效图片") from exc


class BackgroundStore:
    def __init__(self, data_dir: Path):
        self.directory = data_dir / "backgrounds"

    def path(self, reference: str) -> Path | None:
        if not BACKGROUND_REFERENCE.fullmatch(reference):
            return None
        path = self.directory / reference
        if self.directory.is_symlink() or path.is_symlink():
            return None
        return path if path.is_file() else None

    def install(self, image: PreparedBackground) -> None:
        """Publish immutable assets before committing the referencing config."""
        if image.reference != hashlib.sha256(image.png).hexdigest() + ".png":
            raise ValueError("背景图片校验失败，请重新选择")
        if self.directory.is_symlink():
            raise OSError("背景目录不能是符号链接")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / image.reference
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.directory, prefix=".import-", delete=False
            ) as file:
                temporary = Path(file.name)
                file.write(image.png)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def cleanup(self, references) -> None:
        """Remove only our own unused images, never source files or symlinks."""
        keep = set(references)
        if self.directory.is_symlink() or not self.directory.is_dir():
            return
        for path in self.directory.iterdir():
            if (
                BACKGROUND_REFERENCE.fullmatch(path.name)
                and path.name not in keep
                and path.is_file()
                and not path.is_symlink()
            ):
                path.unlink(missing_ok=True)
