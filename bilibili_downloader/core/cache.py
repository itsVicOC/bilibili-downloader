"""Inspection and cleanup helpers for resumable media parts."""

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CacheSummary:
    path: Path
    file_count: int
    size_bytes: int


def inspect_download_cache(output_dir: str | Path) -> CacheSummary:
    root = Path(output_dir) / ".biliflow-parts"
    file_count = 0
    size_bytes = 0
    if root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            file_count += 1
            try:
                size_bytes += path.stat().st_size
            except OSError:
                continue
    return CacheSummary(root, file_count, size_bytes)


def clear_download_cache(output_dir: str | Path) -> CacheSummary:
    summary = inspect_download_cache(output_dir)
    if summary.path.is_dir():
        shutil.rmtree(summary.path)
    return summary
