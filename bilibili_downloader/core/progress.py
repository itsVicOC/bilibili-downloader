"""Optional structured stages; legacy (fraction, text) callbacks stay intact."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadPhase:
    stage: str
    label: str
    progress: float | None = None
    done: int = 0
    total: int = 0
