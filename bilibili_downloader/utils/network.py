"""Network boundary helpers for URLs supplied by remote API responses."""

from urllib.parse import urlparse

BILIBILI_WEB_HOSTS = ("bilibili.com", "b23.tv")
BILIBILI_RESOURCE_HOSTS = (
    "bilibili.com",
    "bilivideo.com",
    "bilivideo.cn",
    "hdslb.com",
    "edge.mountaintoys.cn",
)


def trusted_https_url(url: str, allowed_domains: tuple[str, ...]) -> str:
    """Return a normalized HTTPS URL or raise for an untrusted destination."""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("仅允许不含凭据的 HTTPS 地址")
    if not any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains):
        raise ValueError(f"不受信任的网络目标：{hostname}")
    return url
