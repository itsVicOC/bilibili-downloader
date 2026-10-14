"""Pytest fixtures and configuration."""

import pytest


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item):
    yield
    from PySide6.QtCore import QCoreApplication, QEvent

    app = QCoreApplication.instance()
    if app is not None:
        # pytest-qt closes widgets with deleteLater(), but processEvents() alone
        # does not deliver DeferredDelete outside the main event loop. Finish
        # destruction before another test changes the application's stylesheet.
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


@pytest.fixture
def mock_api_responses(responses):
    """Register mock Bilibili API responses for testing."""
    # WBI nav endpoint
    responses.add(
        responses.GET,
        "https://api.bilibili.com/x/web-interface/nav",
        json={
            "code": 0,
            "data": {
                "wbi_img": {
                    "img_url": "https://i0.hdslb.com/bfs/wbi/test_img_key_123.png",
                    "sub_url": "https://i0.hdslb.com/bfs/wbi/test_sub_key_456.png",
                },
                "mid": 123456,
            },
        },
    )
    return responses
