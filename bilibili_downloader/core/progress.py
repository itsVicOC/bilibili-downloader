"""Optional structured stages; legacy (fraction, text) callbacks stay intact."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadPhase:
    stage: str
    label: str
    progress: float | None = None
    done: int = 0
    total: int = 0


def transfer_summary(speed: float, eta: int | None) -> str:
    if speed <= 0:
        return ""
    if speed >= 1024 * 1024:
        rate = f"{speed / 1024 / 1024:.1f} MB/s"
    else:
        rate = f"{speed / 1024:.0f} KB/s"
    if eta is None:
        return rate
    minutes, seconds = divmod(max(0, eta), 60)
    return f"{rate} · 剩余 {minutes:d}:{seconds:02d}"
