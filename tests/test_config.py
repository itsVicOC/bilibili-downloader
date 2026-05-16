"""Tests for ConfigManager."""

import json
from pathlib import Path

from src.core.models import AppSettings
from src.utils.config import ConfigManager


class TestConfigManager:
    def test_load_defaults_when_no_file(self, tmp_path):
        """Should return default settings when no config file exists."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(config_path=config_path)
        settings = manager.load()
        assert isinstance(settings, AppSettings)
        assert settings.output_dir == "./downloads"
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

    def test_update_sets_field(self, tmp_path):
        """Update should modify and persist a specific field."""
        config_path = tmp_path / "config.json"
        manager = ConfigManager(config_path=config_path)

        result = manager.update(output_dir="/new/dir")
        assert result.output_dir == "/new/dir"

        # Should be persisted
        loaded = manager.load()
        assert loaded.output_dir == "/new/dir"
