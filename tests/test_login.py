"""Tests for Bilibili QR login cookie handling."""

import httpx

from bilibili_downloader.api.login import LoginManager


def _manager_with_transport(handler) -> LoginManager:
    manager = LoginManager()
    manager._client.close()
    manager._client = httpx.Client(
        base_url="https://passport.bilibili.com",
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    return manager


def test_qr_success_extracts_sessdata_from_poll_response(monkeypatch):
    def poll_response(_request):
        return httpx.Response(
            200,
            headers={
                "set-cookie": "SESSDATA=poll-secret; Domain=.bilibili.com; Path=/"
            },
            json={
                "code": 0,
                "data": {
                    "code": 0,
                    "url": "https://passport.bilibili.com/sso",
                },
            },
        )

    manager = _manager_with_transport(poll_response)
    monkeypatch.setattr(
        manager,
        "_extract_cookies_from_sso",
        lambda _url: (_ for _ in ()).throw(AssertionError("SSO fallback used")),
    )
    try:
        result = manager.check_qr_status("qr-key")
    finally:
        manager.close()

    assert result == {
        "status": 0,
        "code": 0,
        "cookies": {"SESSDATA": "poll-secret"},
    }


def test_qr_success_uses_sso_fallback_when_poll_has_no_sessdata(monkeypatch):
    def poll_response(_request):
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "code": 0,
                    "url": "https://passport.bilibili.com/sso",
                },
            },
        )

    manager = _manager_with_transport(poll_response)
    seen_urls = []

    def extract_from_sso(url):
        seen_urls.append(url)
        return {"SESSDATA": "sso-secret"}

    monkeypatch.setattr(manager, "_extract_cookies_from_sso", extract_from_sso)
    try:
        result = manager.check_qr_status("qr-key")
    finally:
        manager.close()

    assert seen_urls == ["https://passport.bilibili.com/sso"]
    assert result["cookies"] == {"SESSDATA": "sso-secret"}


def test_qr_waiting_status_does_not_attempt_sso(monkeypatch):
    def poll_response(_request):
        return httpx.Response(
            200,
            json={"code": 0, "data": {"code": 86101}},
        )

    manager = _manager_with_transport(poll_response)
    monkeypatch.setattr(
        manager,
        "_extract_cookies_from_sso",
        lambda _url: (_ for _ in ()).throw(AssertionError("SSO fallback used")),
    )
    try:
        result = manager.check_qr_status("qr-key")
    finally:
        manager.close()

    assert result == {"status": 86101}
