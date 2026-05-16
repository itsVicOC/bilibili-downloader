"""Bilibili login module - QR code login and SESSDATA management."""

import logging
from io import BytesIO
from typing import Optional

import httpx
import qrcode
from PIL import Image

from bilibili_downloader.api import endpoints as ep
from bilibili_downloader.api.endpoints import USER_AGENT

logger = logging.getLogger(__name__)


class LoginManager:
    """Handles Bilibili login via QR code or manual SESSDATA."""

    def __init__(self):
        self._client = httpx.Client(
            base_url=ep.PASSPORT_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
            follow_redirects=False,
        )

    def generate_qr(self) -> tuple[str, str, Image.Image]:
        """Generate QR code for login.

        Returns:
            (url, qrcode_key, qr_image)
        """
        resp = self._client.get(ep.QR_GENERATE_ENDPOINT)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"QR generation failed: {data.get('message')}")

        url = data["data"]["url"]
        qrcode_key = data["data"]["qrcode_key"]

        # Generate QR image
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        return url, qrcode_key, qr_img

    def check_qr_status(self, qrcode_key: str) -> dict:
        """Poll QR login status.

        Returns:
            dict with keys:
            - status: 86101=waiting, 86090=scanned, 86038=expired, 0=success
            - code: 0=success
            - cookies: dict (on success)
        """
        resp = self._client.get(
            ep.QR_POLL_ENDPOINT,
            params={"qrcode_key": qrcode_key},
        )
        resp.raise_for_status()
        data = resp.json()

        poll_code = data.get("data", {}).get("code", -1)
        result = {"status": poll_code}

        if poll_code == 0:
            # Login successful — need to follow SSO URL to get cookies
            result["code"] = 0
            sso_url = data.get("data", {}).get("url", "")
            cookies = self._extract_cookies_from_sso(sso_url)
            result["cookies"] = cookies

        return result

    def _extract_cookies_from_sso(self, sso_url: str) -> dict:
        """Follow SSO URL to extract SESSDATA cookie.

        Bilibili returns cookies via a redirect chain after successful QR login.
        We follow the SSO URL with cookie tracking to extract SESSDATA.
        """
        if not sso_url:
            logger.warning("SSO URL is empty, cannot extract cookies")
            return {}

        def _find_cookie(cookies, name: str) -> str | None:
            """Find first cookie by name, avoiding CookieConflict on duplicates."""
            for cookie in cookies.jar:
                if cookie.name == name:
                    return cookie.value
            return None

        try:
            # Use a new client that follows redirects and captures cookies
            with httpx.Client(
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://passport.bilibili.com/",
                },
                timeout=30.0,
                follow_redirects=True,
            ) as sso_client:
                sso_resp = sso_client.get(sso_url)
                # Cookies are accumulated in the client during redirects
                sessdata = _find_cookie(sso_client.cookies, "SESSDATA")
                if sessdata:
                    logger.info("SESSDATA extracted from SSO redirect")
                    return {"SESSDATA": sessdata}

                # Fallback: check response cookies directly
                sessdata = _find_cookie(sso_resp.cookies, "SESSDATA")
                if sessdata:
                    logger.info("SESSDATA extracted from SSO response")
                    return {"SESSDATA": sessdata}

                logger.warning("SESSDATA not found in SSO cookies")
                return {}
        except httpx.HTTPError as e:
            logger.warning("SSO request failed: %s", e)
            return {}

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
