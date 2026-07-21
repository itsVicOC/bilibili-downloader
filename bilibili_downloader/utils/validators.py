"""URL parsing and validation utilities for Bilibili links."""

import re
from typing import Optional
from urllib.parse import urljoin

from bilibili_downloader.api.endpoints import USER_AGENT
from bilibili_downloader.utils.network import BILIBILI_WEB_HOSTS, trusted_https_url

# BV number pattern: BV followed by 10 alphanumeric characters (case insensitive)
BV_PATTERN = re.compile(r"[Bb][Vv]([A-Za-z0-9]{10})")

# AV number pattern: av followed by digits
AV_PATTERN = re.compile(r"av(\d+)", re.IGNORECASE)

# Full URL pattern
FULL_URL_PATTERN = re.compile(
    r"https://(?:www\.|m\.)?bilibili\.com/video/"
    r"(BV[a-zA-Z0-9]{10}|av\d+)(?:[/?#][^\s]*)?",
    re.IGNORECASE,
)

# Short link pattern
SHORT_URL_PATTERN = re.compile(
    r"https://b23\.tv/[A-Za-z0-9]+(?:[/?#][^\s]*)?",
    re.IGNORECASE,
)


def extract_bvid(text: str) -> Optional[str]:
    """Extract BV number from various URL formats.

    Supports:
    - Raw BV number: BV1GJ411x7h7
    - Full URL: https://www.bilibili.com/video/BV1GJ411x7h7
    - m.bilibili.com URL: https://m.bilibili.com/video/BV1GJ411x7h7
    - Short link: https://b23.tv/XXXXX (returns None, use resolve_short_link)

    Returns:
        BV number string (e.g., 'BV1GJ411x7h7') or None.
    """
    text = text.strip()

    # Direct BV number
    match = BV_PATTERN.fullmatch(text)
    if match:
        return f"BV{match.group(1)}"

    # Full URL with BV
    match = FULL_URL_PATTERN.fullmatch(text)
    if match:
        raw = match.group(1)
        if raw.upper().startswith("BV"):
            return raw

    return None


def is_short_link(text: str) -> bool:
    """Check if text is a b23.tv short link."""
    return bool(SHORT_URL_PATTERN.fullmatch(text.strip()))


def resolve_short_link(text: str) -> Optional[str]:
    """Resolve a b23.tv short link to a BV number via HTTP redirect.

    Returns:
        BV number or None if resolution fails.
    """
    import httpx

    text = text.strip()
    match = SHORT_URL_PATTERN.fullmatch(text)
    if not match:
        return None

    try:
        current_url = trusted_https_url(match.group(0), BILIBILI_WEB_HOSTS)
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=10.0,
            follow_redirects=False,
        ) as client:
            for _ in range(8):
                resp = client.get(current_url)
                if not resp.is_redirect:
                    resp.raise_for_status()
                    return extract_bvid(current_url)
                location = resp.headers.get("location")
                if not location:
                    return None
                current_url = trusted_https_url(
                    urljoin(current_url, location),
                    BILIBILI_WEB_HOSTS,
                )
        return None
    except (httpx.HTTPError, ValueError):
        pass
    return None


def extract_aid(text: str) -> Optional[int]:
    """Extract AID (AV number) from text or URL.

    Returns:
        AID as integer or None.
    """
    text = text.strip()

    match = AV_PATTERN.fullmatch(text)
    if match:
        return int(match.group(1))

    match = FULL_URL_PATTERN.fullmatch(text)
    if match:
        raw = match.group(1)
        if raw.lower().startswith("av"):
            return int(raw[2:])

    return None


def is_bilibili_url(text: str) -> bool:
    """Check if text looks like a Bilibili video URL."""
    text = text.strip()
    return bool(
        extract_bvid(text)
        or extract_aid(text)
        or is_short_link(text)
    )


def sanitize_filename(name: str) -> str:
    """Remove invalid filename characters from a string.

    Also blocks Windows reserved device names (CON, PRN, NUL, etc.)
    to prevent filesystem errors on Windows.
    """
    invalid_chars = r'<>:"/\|?*'
    for ch in invalid_chars:
        name = name.replace(ch, "_")
    # Remove control characters
    name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)
    # Trim whitespace and dots
    name = name.strip(". ")
    # Block Windows reserved device names
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    base = name.split(".")[0].upper()
    if base in reserved:
        name = f"_{name}"
    # Limit encoded length as well as characters. UTF-8 filesystems commonly
    # cap one filename component at 255 bytes, so character-only truncation is
    # insufficient for CJK titles.
    if len(name) > 200:
        name = name[:200]
    if len(name.encode("utf-8")) > 200:
        name = name.encode("utf-8")[:200].decode("utf-8", errors="ignore")
    return name or "untitled"
