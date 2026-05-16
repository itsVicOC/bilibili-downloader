"""Bilibili login module - QR code login and SESSDATA management."""

import base64
from io import BytesIO
from typing import Optional

import httpx
import qrcode
from PIL import Image

from bilibili_downloader.api import endpoints as ep
from bilibili_downloader.api.endpoints import USER_AGENT


class LoginManager:
    """Handles Bilibili login via QR code or manual SESSDATA."""

    def __init__(self):
        self._client = httpx.Client(
            base_url=ep.PASSPORT_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
        )

    def generate_qr(self) -> tuple[str, str, Image.Image]:
        """Generate QR code for login.

        Returns:
            (url, oauth_key, qr_image)
        """
        resp = self._client.get(ep.QR_GENERATE_ENDPOINT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"QR generation failed: {data.get('message')}")

        url = data["data"]["url"]
        oauth_key = data["data"]["qrcode_key"]

        # Generate QR image
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        return url, oauth_key, qr_img

    def check_qr_status(self, oauth_key: str) -> dict:
        """Poll QR login status.

        Returns:
            dict with keys:
            - status: 86101=waiting, 86090=scanned, 86038=expired, 0=success
            - code: 0=success
            - cookies: dict (on success)
        """
        resp = self._client.get(
            ep.QR_POLL_ENDPOINT,
            params={"qrcode_key": oauth_key},
        )
        resp.raise_for_status()
        data = resp.json()

        poll_code = data.get("data", {}).get("code", -1)
        result = {"status": poll_code}

        if poll_code == 0:
            # Login successful
            result["code"] = 0
            # Extract SESSDATA from Set-Cookie headers using httpx.Cookies
            cookies = httpx.Cookies()
            for cookie_header in resp.headers.get_list("set-cookie"):
                cookies.extract_cookies(
                    httpx.Response(200, headers={"Set-Cookie": cookie_header}),
                    httpx.URL(ep.PASSPORT_URL),
                )
            sessdata = cookies.get("SESSDATA")
            if sessdata:
                result["cookies"] = {"SESSDATA": sessdata}
            else:
                result["cookies"] = {}

        return result

    def validate_sessdata(self, sessdata: str) -> bool:
        """Validate a SESSDATA cookie by checking user info."""
        client = httpx.Client(
            base_url=ep.BASE_URL,
            cookies={"SESSDATA": sessdata},
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"},
            timeout=10.0,
        )
        try:
            resp = client.get(ep.NAV_ENDPOINT)
            resp.raise_for_status()
            data = resp.json()
            return data.get("code") == 0 and bool(data.get("data", {}).get("mid"))
        except httpx.HTTPError:
            return False
        finally:
            client.close()

    def close(self):
        self._client.close()
