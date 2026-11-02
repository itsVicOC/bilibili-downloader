"""Rich local inventory previews; the download service remains authoritative."""

import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Signal


@dataclass(frozen=True)
class InventoryGroupResult:
    matches: tuple

    @property
    def saved(self):
        return bool(self.matches) and all(match.state == 'saved' for match in self.matches)

    def counts(self):
        result = {key: 0 for key in ('saved', 'missing_attachments', 'not_saved', 'specification_mismatch', 'unavailable')}
        for match in self.matches:
            result[match.state] = result.get(match.state, 0) + 1
        return result

    @property
    def label(self):
        counts = self.counts()
        if self.saved:
            return f'完整保存 {len(self.matches)} P'
        parts = []
        for key, text in (('saved', '已保存'), ('missing_attachments', '待补附件'), ('specification_mismatch', '规格不足'), ('unavailable', '文件不可用'), ('not_saved', '未保存')):
            if counts[key]:
                parts.append(f'{text} {counts[key]}')
        return ' · '.join(parts) or '待确认'


def inventory_summary(groups):
    counts = {key: 0 for key in ('saved', 'missing_attachments', 'not_saved', 'specification_mismatch', 'unavailable')}
    for group in groups:
        for key, count in group.counts().items():
            counts[key] = counts.get(key, 0) + count
    new = counts['not_saved'] + counts['specification_mismatch'] + counts['unavailable']
    return f"复用 {counts['saved']} · 补附件 {counts['missing_attachments']} · 新下载 {new}"


class InventorySignals(QObject):
    finished = Signal(object)


class InventoryMatchRunner(QRunnable):
    def __init__(self, repository, groups):
        super().__init__()
        self.signals = InventorySignals()
        self.repository, self.groups = repository, groups
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    def run(self):
        try:
            result = []
            for group in self.groups:
                matches = []
                for item in group:
                    if self._cancelled.is_set():
                        raise InterruptedError("Inventory preview cancelled")
                    matches.append(self.repository.match_media(item))
                result.append(InventoryGroupResult(tuple(matches)))
        except Exception as exc:
            result = exc
        self.signals.finished.emit(result)
