"""Authentication bundle filtering and privacy tests."""

from bilibili_downloader.api.auth import (
    AuthCookieBundle,
    filter_auth_cookies,
    parse_cookie_input,
)
from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.utils import config as config_module


def test_cookie_bundle_keeps_only_allow_list():
    cookies = filter_auth_cookies(
        {
            "SESSDATA": "session-secret",
            "bili_jct": "csrf-secret",
            "browser_tracking": "discard-me",
        }
    )
    assert cookies == {
        "SESSDATA": "session-secret",
        "bili_jct": "csrf-secret",
    }
    assert AuthCookieBundle(cookies=cookies).is_authenticated


def test_manual_cookie_input_accepts_bare_or_full_cookie_header():
    assert parse_cookie_input("bare-secret").cookies == {
        "SESSDATA": "bare-secret"
    }
    assert parse_cookie_input(
        "SESSDATA=session-secret; bili_jct=csrf-secret; ignored=value"
    ).cookies == {
        "SESSDATA": "session-secret",
        "bili_jct": "csrf-secret",
    }


def test_redaction_covers_whitelisted_cookie_and_signed_pgc_url():
    message = (
        "buvid_fp=fingerprint-secret "
        "https://api.bilibili.com/pgc/player/web/v2/playurl?token=secret&qn=80"
    )
    redacted = redact_sensitive_text(message)
    assert "fingerprint-secret" not in redacted
    assert "token=secret" not in redacted
    assert "buvid_fp=[已隐藏]" in redacted


def test_api_client_discards_non_whitelisted_auth_cookies():
    client = BilibiliAPIClient(
        auth_cookies={"SESSDATA": "secret", "unrelated": "discard"}
    )
    try:
        assert client.auth_cookies == {"SESSDATA": "secret"}
    finally:
        client.close()


def test_keyring_bundle_write_is_read_back_and_verified(monkeypatch):
    stored = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, account, value):
            stored[(service, account)] = value

        @staticmethod
        def get_password(service, account):
            return stored.get((service, account))

    monkeypatch.setattr(config_module, "_get_keyring", lambda: FakeKeyring)
    bundle = AuthCookieBundle(
        cookies={"SESSDATA": "session-secret", "bili_jct": "csrf-secret"}
    )

    assert config_module._save_auth_cookie_bundle(bundle) is True
    assert config_module._load_auth_cookie_bundle() == bundle
