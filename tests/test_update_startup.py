import json
from dataclasses import replace

import pytest

from bilibili_downloader import __version__
from bilibili_downloader.core.models import AppSettings, UpdateChannel
from bilibili_downloader.core.update_protocol import (
    BuildInfo,
    UpdateError,
    atomic_json,
    subprocess_environment,
)
from bilibili_downloader.utils import update_startup
from bilibili_downloader.utils.config import ConfigManager


def test_old_config_update_defaults_and_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"output_dir": str(tmp_path)}))
    config = ConfigManager(path)
    settings = config.load()
    assert (
        settings.auto_check_updates and settings.update_channel == UpdateChannel.STABLE
    )
    assert settings.skipped_update_versions == []
    settings.auto_check_updates = False
    settings.update_channel = UpdateChannel.LATEST
    settings.skipped_update_versions = ["0.9.0b1"]
    config.save(settings)
    loaded = ConfigManager(path).load()
    assert (
        not loaded.auto_check_updates and loaded.update_channel == UpdateChannel.LATEST
    )
    assert loaded.skipped_update_versions == ["0.9.0b1"]
    assert AppSettings().skipped_update_versions == []


def test_startup_transaction_is_bound_to_installed_build_and_data_dir(
    tmp_path, monkeypatch
):
    data = tmp_path / "data"
    path = data / "updates" / ("a" * 32) / "transaction.json"
    root = tmp_path / "application"
    info = BuildInfo(__version__, "macOS", "arm64", "lite")
    value = {
        "protocol": 1,
        "token": "token",
        "target": str(root),
        "data_dir": str(data),
        "build": info.__dict__,
    }
    atomic_json(path, value)
    monkeypatch.setattr(update_startup, "installed_build", lambda: (root, info))
    monkeypatch.setenv("BILIFLOW_UPDATE_TRANSACTION", str(path))
    monkeypatch.setenv("BILIFLOW_UPDATE_TOKEN", "token")
    assert update_startup.startup_transaction(data) == (path, value)
    monkeypatch.setenv("BILIFLOW_UPDATE_TRANSACTION", str(path))
    monkeypatch.setenv("BILIFLOW_UPDATE_TOKEN", "wrong")
    with pytest.raises(UpdateError):
        update_startup.startup_transaction(data)
    monkeypatch.setenv("BILIFLOW_UPDATE_TRANSACTION", str(path))
    monkeypatch.setenv("BILIFLOW_UPDATE_TOKEN", "token")
    monkeypatch.setattr(
        update_startup, "installed_build", lambda: (root, replace(info, variant="full"))
    )
    with pytest.raises(UpdateError):
        update_startup.startup_transaction(data)


def test_failure_receipt_must_be_inside_update_directory(tmp_path, monkeypatch):
    path = tmp_path / "updates" / "transaction" / "status.json"
    atomic_json(path, {"state": "failed", "message": "restored"})
    monkeypatch.setenv("BILIFLOW_UPDATE_FAILURE", str(path))
    assert update_startup.startup_failure(tmp_path) == "restored"
    monkeypatch.setenv("BILIFLOW_UPDATE_FAILURE", str(path))
    assert update_startup.startup_failure(tmp_path / "different-data") == ""


def test_restart_environment_discards_private_pyinstaller_and_old_handshake(
    monkeypatch,
):
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/old/runtime")
    monkeypatch.setenv("BILIFLOW_UPDATE_TRANSACTION", "/old/transaction")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/old/libraries")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/libraries")
    result = subprocess_environment()
    assert result["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "_PYI_APPLICATION_HOME_DIR" not in result
    assert "BILIFLOW_UPDATE_TRANSACTION" not in result
    assert result["LD_LIBRARY_PATH"] == "/system/libraries"
