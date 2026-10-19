"""Shared validation, time quantization and atomic output for timed text."""

import os
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

# Keep timestamps within the signed millisecond range used by media tools.
MAX_SECONDS = Decimal((2**31 - 1) // 1000)


@dataclass
class ConversionReport:
    exported: int = 0
    invalid: int = 0
    unsupported: int = 0
    crowded: int = 0
    normalized: int = 0

    def warnings(self, label: str) -> list[str]:
        messages = []
        if self.invalid:
            messages.append(f"{label}：已跳过 {self.invalid} 条空白、过长或格式异常的内容")
        if self.unsupported:
            messages.append(
                f"{label}：已跳过 {self.unsupported} 条不支持的特殊弹幕；仅转换普通滚动及顶底弹幕"
            )
        if self.crowded:
            messages.append(
                f"{label}：{self.crowded} 条弹幕因画面密集可能重叠，已保留原时间与正文"
            )
        if self.normalized:
            messages.append(
                f"{label}：{self.normalized} 条内容已做兼容处理（花括号使用全角形式、清理异常字符或缩小过大字号）"
            )
        return messages


def time_units(value, units_per_second: int) -> int:
    """Round once to integer units; reject non-finite/negative timestamps."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("时间必须是有效的非负数")
    try:
        seconds = Decimal(str(value))
        if not seconds.is_finite() or seconds < 0 or seconds > MAX_SECONDS:
            raise ValueError("时间超出可导出范围")
        return int((seconds * units_per_second).to_integral_value(rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError("时间格式无效") from exc


def clean_text(text: str) -> str:
    """Normalize line endings without damaging emoji joiners or combining marks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u2028", "\n").replace("\u2029", "\n").replace("\t", "    ")
    return "".join(
        "\ufffd" if unicodedata.category(char) == "Cs" else char
        for char in text
        if char == "\n" or unicodedata.category(char) != "Cc"
    )


@contextmanager
def atomic_text_output(destination: Path):
    """Publish only a completely written UTF-8 file; preserve an existing export."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
