"""Tests for ConfigManager."""

import json
from pathlib import Path

from bilibili_downloader.core.models import AppSettings
from bilibili_downloader.utils import config as config_module
from bilibili_downloader.utils.config import ConfigManager


class TestConfigManager:
    def test_load_defaults_when_no_file(self, tmp_path):
        """Should return default settings when no config file exists."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(config_path=config_path)
        settings = manager.load()
        assert isinstance(settings, AppSettings)
        assert settings.output_dir == str(Path.home() / "Downloads" / "bilibili")
        assert settings.max_concurrent_downloads == 3

    def test_save_and_load_roundtrip(self, tmp_path):
        """Settings should survive a save/load cycle."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(config_path=config_path)
        settings = AppSettings(output_dir="/custom/path", max_concurrent_downloads=5)
        manager.save(settings)

        manager2 = ConfigManager(config_path=config_path)
        loaded = manager2.load()
        assert loaded.output_dir == "/custom/path"
        assert loaded.max_concurrent_downloads == 5
        assert not list(tmp_path.glob("*.tmp"))

    def test_corrupted_config_backs_up(self, tmp_path):
        """Corrupted JSON should be backed up and defaults returned."""
        config_path = tmp_path / "config.json"
        backup_path = tmp_path / "config.json.bak"

        # Write invalid JSON
        config_path.write_text("{ invalid json }", encoding="utf-8")

        manager = ConfigManager(config_path=config_path)
        settings = manager.load()

        assert isinstance(settings, AppSettings)
        assert backup_path.exists()
        assert "{ invalid json }" in backup_path.read_text(encoding="utf-8")

    def test_unreadable_config_falls_back_to_defaults(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("{}", encoding="utf-8")
        original_read_text = Path.read_text

        def fail_for_config(path, *args, **kwargs):
            if path == config_path:
                raise PermissionError("denied")
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fail_for_config)

        settings = ConfigManager(config_path=config_path).load()

        assert isinstance(settings, AppSettings)

    def test_update_sets_field(self, tmp_path):
        """Update should modify and persist a specific field."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(config_path=config_path)

        result = manager.update(output_dir="/new/dir")
        assert result.output_dir == "/new/dir"

        # Should be persisted
        loaded = manager.load()
        assert loaded.output_dir == "/new/dir"

    def test_sessdata_saved_to_keyring_when_available(self, monkeypatch, tmp_path):
        """SESSDATA should stay out of JSON when keyring storage succeeds."""
        saved = {}
        monkeypatch.setattr(
            config_module,
            "_save_sessdata_to_keyring",
            lambda sessdata: saved.setdefault("sessdata", sessdata) is not None,
        )
        monkeypatch.setattr(
            config_module,
            "_load_sessdata_from_keyring",
            lambda: saved.get("sessdata", ""),
        )

        config_path = tmp_path / "config.json"
        ConfigManager(config_path=config_path).save(AppSettings(sessdata="secret"))

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert raw["sessdata"] == ""

        loaded = ConfigManager(config_path=config_path).load()
        assert loaded.sessdata == "secret"

    def test_sessdata_falls_back_to_obfuscated_config(self, monkeypatch, tmp_path):
        """SESSDATA should remain backward-compatible when keyring is unavailable."""
        monkeypatch.setattr(config_module, "_save_sessdata_to_keyring", lambda sessdata: False)
        monkeypatch.setattr(config_module, "_load_sessdata_from_keyring", lambda: "")

        config_path = tmp_path / "config.json"
        ConfigManager(config_path=config_path).save(AppSettings(sessdata="secret"))

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert raw["sessdata"] != "secret"

        loaded = ConfigManager(config_path=config_path).load()
        assert loaded.sessdata == "secret"
