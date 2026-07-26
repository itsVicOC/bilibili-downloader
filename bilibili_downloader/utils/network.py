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


class UntrustedResourceURLError(ValueError):
    """Raised when a remote response points outside the trusted URL boundary."""


def trusted_https_url(
    url: str,
    allowed_domains: tuple[str, ...],
    *,
    upgrade_http: bool = False,
) -> str:
    """Return a normalized HTTPS URL or raise for an untrusted destination."""
    if url.startswith("//"):
        url = "https:" + url
    elif upgrade_http and url.lower().startswith("http://"):
        # Some Bilibili metadata still returns HTTP resource URLs. Upgrade the
        # scheme before validation so no plaintext request is ever sent.
        url = "https://" + url[7:]
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise UntrustedResourceURLError("仅允许不含凭据的 HTTPS 地址")
    if not any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains):
        raise UntrustedResourceURLError(f"不受信任的网络目标：{hostname}")
    return url
