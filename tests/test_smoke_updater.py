import json

import pytest

from scripts import smoke_updater


@pytest.mark.parametrize("marker_name", ["new-ready.json", "rollback-ready.json"])
def test_cleanup_waits_for_bootloader_after_application_exits(
    tmp_path, monkeypatch, marker_name
):
    marker = tmp_path / marker_name
    marker.write_text(json.dumps({"pid": 101, "bootloader_pid": 202}))
    parent_states = iter([True, True, False])
    sleeps = []

    def process_alive(pid):
        if pid == 101:
            return False
        assert pid == 202
        return next(parent_states)

    monkeypatch.setattr(smoke_updater, "process_alive", process_alive)
    monkeypatch.setattr(smoke_updater.time, "sleep", sleeps.append)
    smoke_updater._wait_for_application_exit(marker)

    # The executable remains occupied for two polls after the Python child exits.
    assert len(sleeps) == 2
    assert list(parent_states) == []


def test_cleanup_does_not_ignore_bootloader_exit_timeout(tmp_path, monkeypatch):
    marker = tmp_path / "new-ready.json"
    marker.write_text(json.dumps({"pid": 101, "bootloader_pid": 202}))
    monkeypatch.setattr(smoke_updater, "process_alive", lambda pid: pid == 202)
    clock = iter([0, 31])
    monkeypatch.setattr(smoke_updater.time, "monotonic", lambda: next(clock))

    with pytest.raises(RuntimeError, match="timed out"):
        smoke_updater._wait_for_application_exit(marker)
