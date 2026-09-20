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

    def test_auth_bundle_saved_to_keyring_when_available(self, monkeypatch, tmp_path):
        """The filtered bundle should stay out of JSON when keyring succeeds."""
        saved = {}
        monkeypatch.setattr(
            config_module,
            "_save_auth_cookie_bundle",
            lambda bundle: saved.setdefault("bundle", bundle) is not None,
        )
        monkeypatch.setattr(
            config_module,
            "_load_auth_cookie_bundle",
            lambda: saved.get("bundle"),
        )

        config_path = tmp_path / "config.json"
        ConfigManager(config_path=config_path).save(AppSettings(sessdata="secret"))

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert raw["sessdata"] == ""

        loaded = ConfigManager(config_path=config_path).load()
        assert loaded.sessdata == "secret"
        assert saved["bundle"].cookies == {"SESSDATA": "secret"}

    def test_sessdata_is_session_only_when_keyring_unavailable(self, monkeypatch, tmp_path):
        """New secrets must not fall back to the JSON config."""
        monkeypatch.setattr(config_module, "_save_auth_cookie_bundle", lambda bundle: False)
        monkeypatch.setattr(config_module, "_load_auth_cookie_bundle", lambda: None)
        monkeypatch.setattr(config_module, "_load_sessdata_from_keyring", lambda: "")

        config_path = tmp_path / "config.json"
        manager = ConfigManager(config_path=config_path)
        manager.save(AppSettings(sessdata="secret"))

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert raw["sessdata"] == ""
        assert manager.auth_cookies == {"SESSDATA": "secret"}
        assert manager.credentials_persistent is False

        loaded = ConfigManager(config_path=config_path).load()
        assert loaded.sessdata == ""

    def test_default_path_migrates_legacy_config(self, monkeypatch, tmp_path):
        legacy_path = tmp_path / "legacy" / "config.json"
        target_path = tmp_path / "native" / "config.json"
        legacy_path.parent.mkdir()
        legacy_path.write_text(
            json.dumps({"output_dir": "/migrated", "max_concurrent_downloads": 2}),
            encoding="utf-8",
        )
        monkeypatch.setattr(config_module, "LEGACY_CONFIG_PATH", legacy_path)
        monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", target_path)
        monkeypatch.setattr(config_module, "_load_sessdata_from_keyring", lambda: "")

        loaded = ConfigManager().load()

        assert loaded.output_dir == "/migrated"
        assert target_path.is_file()
        assert legacy_path.is_file()

    def test_legacy_sessdata_migration_is_session_only_when_keyring_fails(
        self, monkeypatch, tmp_path
    ):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"sessdata": "legacy-secret"}), encoding="utf-8"
        )
        monkeypatch.setattr(config_module, "_load_auth_cookie_bundle", lambda: None)
        monkeypatch.setattr(config_module, "_load_sessdata_from_keyring", lambda: "")
        monkeypatch.setattr(
            config_module, "_save_auth_cookie_bundle", lambda _bundle: False
        )

        manager = ConfigManager(config_path=config_path)
        settings = manager.load()

        assert settings.sessdata == "legacy-secret"
        assert manager.auth_cookies == {"SESSDATA": "legacy-secret"}
        assert manager.credentials_persistent is False

        manager.save(settings)
        assert json.loads(config_path.read_text(encoding="utf-8"))["sessdata"] == ""

    def test_invalid_model_config_is_backed_up(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({"max_concurrent_downloads": 100}), encoding="utf-8"
        )

        loaded = ConfigManager(config_path=config_path).load()

        assert loaded.max_concurrent_downloads == 3
        assert config_path.with_suffix(".json.bak").is_file()
