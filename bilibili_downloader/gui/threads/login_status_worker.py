"""Background login checks and bounded, credential-free avatar loading."""

import io

import httpx
from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, Signal

from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.utils.network import trusted_https_url

MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 4_000_000


def load_avatar(url: str) -> bytes:
    """Return a small normalized PNG without sending account cookies to the CDN."""
    url = trusted_https_url(url, ("hdslb.com",), upgrade_http=True)
    content = bytearray()
    with httpx.stream("GET", url, timeout=5.0, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > MAX_AVATAR_BYTES:
                raise ValueError("头像文件过大")
    with Image.open(io.BytesIO(content)) as image:
        if image.width * image.height > MAX_AVATAR_PIXELS:
            raise ValueError("头像像素尺寸过大")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((192, 192), Image.Resampling.LANCZOS)
        image = image.convert("RGBA")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


class LoginStatusWorker(QObject):
    finished = Signal(int, object)
    error = Signal(int, str)
    avatar_ready = Signal(int, bytes)

    def __init__(self, client, request_id: int):
        super().__init__()
        self.client = client
        self.request_id = request_id


class LoginStatusRunner(QRunnable):
    def __init__(self, worker: LoginStatusWorker):
        super().__init__()
        self._worker = worker
        self.setAutoDelete(True)

    def run(self):
        try:
            info = self._worker.client.get_nav_info()
            self._worker.finished.emit(self._worker.request_id, info)
        except Exception as e:  # noqa: BLE001
            self._worker.error.emit(
                self._worker.request_id, redact_sensitive_text(e)
            )
            return
        if info.get("isLogin") and info.get("face"):
            try:
                avatar = load_avatar(info["face"])
            except Exception:  # noqa: BLE001
                # A missing avatar must not invalidate a successful login.
                return
            self._worker.avatar_ready.emit(self._worker.request_id, avatar)
