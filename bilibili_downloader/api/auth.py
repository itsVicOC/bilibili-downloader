"""Whitelisted Bilibili authentication cookies."""

from __future__ import annotations

from http.cookies import CookieError, SimpleCookie
from typing import Mapping

from pydantic import BaseModel, Field

AUTH_COOKIE_NAMES = frozenset(
    {
        "SESSDATA",
        "DedeUserID",
        "DedeUserID__ckMd5",
        "bili_jct",
        "sid",
        "b_nut",
        "buvid3",
        "buvid4",
        "buvid_fp",
        "_uuid",
    }
)


class AuthCookieBundle(BaseModel):
    """Versioned, allow-listed record suitable for system credential storage."""

    version: int = 1
    cookies: dict[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context) -> None:
        self.cookies = filter_auth_cookies(self.cookies)

    @property
    def is_authenticated(self) -> bool:
        return bool(self.cookies.get("SESSDATA"))


def filter_auth_cookies(cookies: Mapping[str, object] | None) -> dict[str, str]:
    """Return non-empty, allow-listed string cookie values only."""
    if not cookies:
        return {}
    return {
        name: str(value)
        for name, value in cookies.items()
        if name in AUTH_COOKIE_NAMES and value is not None and str(value)
    }


def parse_cookie_input(value: str) -> AuthCookieBundle:
    """Parse either a bare SESSDATA value or a browser Cookie header."""
    text = value.strip()
    if not text:
        return AuthCookieBundle()
    if "=" not in text:
        return AuthCookieBundle(cookies={"SESSDATA": text})

    parsed = SimpleCookie()
    try:
        parsed.load(text)
    except CookieError:
        return AuthCookieBundle()
    return AuthCookieBundle(
        cookies={name: morsel.value for name, morsel in parsed.items()}
    )
