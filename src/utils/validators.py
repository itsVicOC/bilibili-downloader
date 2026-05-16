"""URL parsing and validation utilities for Bilibili links."""

import re
from typing import Optional


# BV number pattern: BV followed by 10 alphanumeric characters (case insensitive)
BV_PATTERN = re.compile(r"[Bb][Vv]([A-Za-z0-9]{10})")

# AV number pattern: av followed by digits
AV_PATTERN = re.compile(r"av(\d+)", re.IGNORECASE)

# Full URL pattern
FULL_URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+|av\d+)",
    re.IGNORECASE,
)

# Short link pattern
SHORT_URL_PATTERN = re.compile(r"https?://b23\.tv/[A-Za-z0-9]+", re.IGNORECASE)


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
    match = BV_PATTERN.search(text)
    if match:
        return f"BV{match.group(1)}"

    # Full URL with BV
    match = FULL_URL_PATTERN.search(text)
    if match:
        raw = match.group(1)
        if raw.upper().startswith("BV"):
            return raw

    return None


def is_short_link(text: str) -> bool:
    """Check if text is a b23.tv short link."""
    return bool(SHORT_URL_PATTERN.search(text.strip()))


def resolve_short_link(text: str) -> Optional[str]:
    """Resolve a b23.tv short link to a BV number via HTTP redirect.

    Returns:
        BV number or None if resolution fails.
    """
    import httpx

    text = text.strip()
    if not SHORT_URL_PATTERN.search(text):
        return None

    try:
        resp = httpx.get(text, timeout=10.0, follow_redirects=False)
        if resp.status_code in (301, 302, 307, 308):
            location = resp.headers.get("location", "")
            return extract_bvid(location)
    except Exception:
        pass
    return None


def extract_aid(text: str) -> Optional[int]:
    """Extract AID (AV number) from text or URL.

    Returns:
        AID as integer or None.
    """
    text = text.strip()

    match = AV_PATTERN.search(text)
    if match:
        return int(match.group(1))

    match = FULL_URL_PATTERN.search(text)
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
        or FULL_URL_PATTERN.search(text)
        or SHORT_URL_PATTERN.search(text)
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
    # Limit length
    if len(name) > 200:
        name = name[:200]
    return name or "untitled"
