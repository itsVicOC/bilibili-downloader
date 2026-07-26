"""User-facing error classification and sensitive detail redaction."""

import errno
import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit, urlunsplit

import httpx

from bilibili_downloader.api.client import BilibiliAPIError


class ErrorCategory(str, Enum):
    """Stable categories shared by the GUI and CLI."""

    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    CONTENT = "content"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    STORAGE = "storage"
    FFMPEG = "ffmpeg"
    INPUT = "input"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorDetails:
    """Actionable, safe-to-display error information."""

    category: ErrorCategory
    message: str
    suggestion: str

    @property
    def user_message(self) -> str:
        return f"{self.message}\n建议：{self.suggestion}"


_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_COOKIE_PATTERN = re.compile(
    r"(?i)(SESSDATA|bili_jct|DedeUserID|refresh_token)\s*[=:]\s*[^\s;,]+"
)


def classify_error(error: BaseException) -> ErrorDetails:
    """Classify an exception without exposing credentials or signed URLs."""
    if isinstance(error, BilibiliAPIError):
        if error.code == -101:
            return ErrorDetails(
                ErrorCategory.AUTHENTICATION,
                "登录状态已失效或当前操作需要登录。",
                "重新登录后再试。",
            )
        if error.code == -403:
            return ErrorDetails(
                ErrorCategory.PERMISSION,
                "当前账号没有访问此内容的权限。",
                "确认账号权限、会员状态或内容可见范围。",
            )
        if error.code in {-404, 62002, 62004}:
            return ErrorDetails(
                ErrorCategory.CONTENT,
                "视频不存在、已失效或暂时不可用。",
                "在浏览器中确认内容仍可访问，并检查输入链接。",
            )
        if error.code in {-352, -412}:
            return ErrorDetails(
                ErrorCategory.RATE_LIMIT,
                "请求被 Bilibili 风控或限流。",
                "降低并发并稍后重试；频繁出现时检查代理和系统时间。",
            )
        detail = redact_sensitive_text(error.message).strip()
        suffix = f"：{detail}" if detail else ""
        return ErrorDetails(
            ErrorCategory.UNKNOWN,
            f"Bilibili 接口返回错误（{error.code}）{suffix}",
            "稍后重试；持续失败时更新应用并查看故障排查文档。",
        )

    if isinstance(error, httpx.TimeoutException):
        return ErrorDetails(
            ErrorCategory.NETWORK,
            "网络请求超时。",
            "检查网络或代理，降低并发后重试。",
        )
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in {401, 403}:
            return ErrorDetails(
                ErrorCategory.PERMISSION,
                f"服务器拒绝了请求（HTTP {status}）。",
                "重新登录并确认账号有权访问此内容。",
            )
        if status in {404, 410}:
            return ErrorDetails(
                ErrorCategory.CONTENT,
                f"请求的内容已不可用（HTTP {status}）。",
                "重新解析视频，并确认内容在浏览器中仍可访问。",
            )
        if status == 429:
            return ErrorDetails(
                ErrorCategory.RATE_LIMIT,
                "请求过于频繁（HTTP 429）。",
                "降低并发并等待一段时间后重试。",
            )
        if status >= 500:
            return ErrorDetails(
                ErrorCategory.NETWORK,
                f"Bilibili 服务暂时异常（HTTP {status}）。",
                "稍后重试，未完成任务可继续下载。",
            )
        return ErrorDetails(
            ErrorCategory.NETWORK,
            f"网络请求失败（HTTP {status}）。",
            "检查网络、代理和内容访问权限后重试。",
        )
    if isinstance(error, (httpx.NetworkError, ConnectionError)):
        return ErrorDetails(
            ErrorCategory.NETWORK,
            "无法连接到 Bilibili 或媒体服务器。",
            "检查网络、DNS 和代理设置后重试。",
        )

    if isinstance(error, OSError):
        if error.errno == errno.ENOSPC:
            return ErrorDetails(
                ErrorCategory.STORAGE,
                "磁盘空间不足，无法继续写入文件。",
                "释放输出盘空间后继续任务。",
            )
        if isinstance(error, PermissionError) or error.errno in {
            errno.EACCES,
            errno.EPERM,
            errno.EROFS,
        }:
            return ErrorDetails(
                ErrorCategory.STORAGE,
                "没有权限写入输出目录或任务文件。",
                "选择可写目录，并检查文件是否被其他程序占用。",
            )

    safe_message = redact_sensitive_text(str(error)).strip()
    lowered = safe_message.lower()
    if "ffmpeg" in lowered:
        if "not found" in lowered or "找不到" in safe_message:
            return ErrorDetails(
                ErrorCategory.FFMPEG,
                "未找到可用的 FFmpeg。",
                "安装 FFmpeg，或在下载设置中选择其可执行文件。",
            )
        return ErrorDetails(
            ErrorCategory.FFMPEG,
            "FFmpeg 处理媒体失败。",
            "检查 FFmpeg 配置、磁盘空间和输出目录后重试。",
        )
    if isinstance(error, ValueError):
        return ErrorDetails(
            ErrorCategory.INPUT,
            safe_message or "输入参数无效。",
            "检查链接和下载选项后重试。",
        )

    return ErrorDetails(
        ErrorCategory.UNKNOWN,
        safe_message or "操作失败，但没有返回具体原因。",
        "重试一次；持续失败时查看脱敏日志和故障排查文档。",
    )


def user_error_message(error: BaseException) -> str:
    """Return the normalized message shown by GUI and CLI surfaces."""
    return classify_error(error).user_message


def redact_sensitive_text(value: object) -> str:
    """Remove cookie values and URL query/fragment data from arbitrary text."""
    text = str(value)
    text = _COOKIE_PATTERN.sub(lambda match: f"{match.group(1)}=[已隐藏]", text)
    return _URL_PATTERN.sub(_redact_url, text)


def _redact_url(match: re.Match) -> str:
    raw_url = match.group(0)
    trailing = ""
    while raw_url and raw_url[-1] in ".,;:!?)】]":
        trailing = raw_url[-1] + trailing
        raw_url = raw_url[:-1]
    try:
        parsed = urlsplit(raw_url)
        query = "[参数已隐藏]" if parsed.query else ""
        sanitized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    except ValueError:
        sanitized = "[链接已隐藏]"
    return sanitized + trailing
