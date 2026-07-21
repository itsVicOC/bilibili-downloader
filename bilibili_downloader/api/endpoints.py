"""Bilibili API URL constants."""

# Shared browser User-Agent — used across all HTTP clients
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BASE_URL = "https://api.bilibili.com"
PASSPORT_URL = "https://passport.bilibili.com"
COMMENT_URL = "https://comment.bilibili.com"

# Video info (requires WBI signature)
VIEW_ENDPOINT = "/x/web-interface/view"

# Video playback URL (no WBI required as of 2026, but may change)
PLAYURL_ENDPOINT = "/x/player/playurl"
PLAYER_INFO_ENDPOINT = "/x/player/v2"

# Video page list (multi-part videos)
PAGELIST_ENDPOINT = "/x/player/pagelist"

# Navigation / user info (for WBI key extraction)
NAV_ENDPOINT = "/x/web-interface/nav"

# QR login
QR_GENERATE_ENDPOINT = "/x/passport-login/web/qrcode/generate"
QR_POLL_ENDPOINT = "/x/passport-login/web/qrcode/poll"

# Danmaku (no WBI required)
DANMAKU_XML_URL = "https://comment.bilibili.com/{cid}.xml"

# Subtitle (direct URL from playurl response, no fixed endpoint)
