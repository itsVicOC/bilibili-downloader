"""Tests for stable, actionable and redacted error messages."""

import errno

import httpx
import pytest

from bilibili_downloader.api.client import BilibiliAPIError
from bilibili_downloader.core.errors import (
    ErrorCategory,
    classify_error,
    redact_sensitive_text,
)


@pytest.mark.parametrize(
    ("code", "category", "expected"),
    [
        (-101, ErrorCategory.AUTHENTICATION, "重新登录"),
        (-403, ErrorCategory.PERMISSION, "权限"),
        (-404, ErrorCategory.CONTENT, "不可用"),
        (62002, ErrorCategory.CONTENT, "不可用"),
        (-352, ErrorCategory.RATE_LIMIT, "风控"),
        (-412, ErrorCategory.RATE_LIMIT, "风控"),
    ],
)
def test_classifies_bilibili_api_errors(code, category, expected):
    details = classify_error(BilibiliAPIError(code, "raw API message"))

    assert details.category == category
    assert expected in details.user_message


def test_classifies_network_timeout_without_exposing_url():
    request = httpx.Request(
        "GET", "https://cdn.example/video.m4s?deadline=1&token=secret"
    )

    details = classify_error(httpx.ReadTimeout("timed out", request=request))

    assert details.category == ErrorCategory.NETWORK
    assert "token" not in details.user_message


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (OSError(errno.ENOSPC, "disk full"), "磁盘空间不足"),
        (PermissionError(errno.EACCES, "denied"), "没有权限"),
        (RuntimeError("FFmpeg not found"), "未找到可用的 FFmpeg"),
        (RuntimeError("FFmpeg processing failed: invalid data"), "处理媒体失败"),
    ],
)
def test_classifies_storage_and_ffmpeg_errors(error, expected):
    assert expected in classify_error(error).user_message


def test_redacts_signed_urls_and_credentials_from_unknown_errors():
    error = RuntimeError(
        "failed https://cdn.example/video.m4s?deadline=1&token=secret "
        "SESSDATA=private-value"
    )

    message = classify_error(error).user_message

    assert "secret" not in message
    assert "private-value" not in message
    assert "deadline" not in message
    assert "https://cdn.example/video.m4s?[参数已隐藏]" in message


def test_redaction_preserves_safe_url_path_and_trailing_punctuation():
    text = redact_sensitive_text(
        "open https://www.bilibili.com/video/BV1GJ411x7h7?p=2, then retry"
    )

    assert text == (
        "open https://www.bilibili.com/video/BV1GJ411x7h7?[参数已隐藏], then retry"
    )
