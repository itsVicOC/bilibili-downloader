"""Bilibili login module - QR code login and SESSDATA management."""

import logging
from urllib.parse import urljoin

import httpx
import qrcode
from PIL import Image

from bilibili_downloader.api import endpoints as ep
from bilibili_downloader.api.auth import AUTH_COOKIE_NAMES, filter_auth_cookies
from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.utils.network import BILIBILI_WEB_HOSTS, trusted_https_url

logger = logging.getLogger(__name__)


def _find_cookie(cookies: httpx.Cookies, name: str) -> str | None:
    """Find a cookie by name without raising on duplicate domains/paths."""
    for cookie in cookies.jar:
        if cookie.name == name and cookie.value:
            return cookie.value
    return None


def _collect_cookies(*cookie_jars: httpx.Cookies) -> dict[str, str]:
    values: dict[str, str] = {}
    for cookies in cookie_jars:
        for cookie in cookies.jar:
            if cookie.name in AUTH_COOKIE_NAMES and cookie.value:
                values[cookie.name] = cookie.value
    return filter_auth_cookies(values)


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
            # Recent passport responses set SESSDATA directly on the poll
            # response. Keep the SSO redirect as a compatibility fallback for
            # older responses that only return a URL.
            result["code"] = 0
            cookies = _collect_cookies(resp.cookies, self._client.cookies)
            if cookies.get("SESSDATA"):
                logger.info("Authentication cookies extracted from QR response")
                result["cookies"] = cookies
                return result

            sso_url = data.get("data", {}).get("url", "")
            result["cookies"] = self._extract_cookies_from_sso(sso_url)

        return result

    def _extract_cookies_from_sso(self, sso_url: str) -> dict:
        """Follow SSO URL to extract SESSDATA cookie.

        Bilibili returns cookies via a redirect chain after successful QR login.
        We follow the SSO URL with cookie tracking to extract SESSDATA.
        """
        if not sso_url:
            logger.warning("SSO URL is empty, cannot extract cookies")
            return {}

        try:
            # Follow only trusted Bilibili redirects while accumulating cookies.
            with httpx.Client(
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": "https://passport.bilibili.com/",
                },
                timeout=30.0,
                follow_redirects=False,
            ) as sso_client:
                current_url = trusted_https_url(sso_url, BILIBILI_WEB_HOSTS)
                sso_resp = None
                for _ in range(10):
                    sso_resp = sso_client.get(current_url)
                    if not sso_resp.is_redirect:
                        break
                    location = sso_resp.headers.get("location")
                    if not location:
                        break
                    current_url = trusted_https_url(
                        urljoin(current_url, location),
                        BILIBILI_WEB_HOSTS,
                    )
                if sso_resp is None:
                    return {}
                # Cookies are accumulated in the client during redirects
                cookies = _collect_cookies(
                    sso_client.cookies,
                    sso_resp.cookies,
                    self._client.cookies,
                )
                if cookies.get("SESSDATA"):
                    logger.info("Authentication cookies extracted from SSO redirect")
                    return cookies

                # Fallback: check response cookies directly
                logger.warning("SESSDATA not found in SSO cookies")
                return {}
        except (httpx.HTTPError, ValueError) as e:
            logger.warning("SSO request failed: %s", e)
            return {}

    def validate_sessdata(self, sessdata: str) -> bool:
        """Validate a SESSDATA cookie by checking user info."""
        return bool(self.validate_cookies({"SESSDATA": sessdata}))

    def validate_cookies(self, cookies: dict[str, str]) -> dict:
        """Validate an allow-listed cookie bundle and return account metadata."""
        cookies = filter_auth_cookies(cookies)
        if not cookies.get("SESSDATA"):
            return {}
        client = httpx.Client(
            base_url=ep.BASE_URL,
            cookies=cookies,
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"},
            timeout=10.0,
        )
        try:
            resp = client.get(ep.NAV_ENDPOINT)
            resp.raise_for_status()
            data = resp.json()
            nav = data.get("data") or {}
            return nav if data.get("code") == 0 and nav.get("mid") else {}
        except httpx.HTTPError:
            return {}
        finally:
            client.close()

    def close(self):
        self._client.close()
