"""Settings persistence for the application."""

import base64
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from bilibili_downloader.core.models import AppSettings

logger = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path.home() / ".bilibili-downloader" / "config.json"


def _obfuscate(data: dict) -> dict:
    """Base64-encode sessdata before saving to JSON."""
    if data.get("sessdata"):
        data = dict(data)
        data["sessdata"] = base64.b64encode(data["sessdata"].encode()).decode()
    return data


def _deobfuscate(data: dict) -> dict:
    """Base64-decode sessdata after loading from JSON."""
    if data.get("sessdata"):
        data = dict(data)
        try:
            decoded = base64.b64decode(data["sessdata"].encode()).decode()
            data["sessdata"] = decoded
        except Exception:
            pass  # Leave as-is if not valid base64 (e.g. plaintext legacy config)
    return data


class ConfigManager:
    """Load and save application settings to JSON."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._settings: Optional[AppSettings] = None

    def load(self) -> AppSettings:
        """Load settings from disk, or return defaults."""
        if self._settings is not None:
            return self._settings

        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                data = _deobfuscate(data)
                self._settings = AppSettings(**data)
                return self._settings
            except (json.JSONDecodeError, ValueError) as e:
                # Backup corrupted config before falling back to defaults
                backup = self._config_path.with_suffix(".json.bak")
                try:
                    shutil.copy2(self._config_path, backup)
                    logger.warning(
                        "Corrupted config at %s, backed up to %s. Error: %s",
                        self._config_path, backup, e,
                    )
                except OSError:
                    logger.warning(
                        "Corrupted config at %s, failed to backup. Error: %s",
                        self._config_path, e,
                    )

        self._settings = AppSettings()
        return self._settings

    def save(self, settings: AppSettings) -> None:
        """Save settings to disk."""
        self._settings = settings
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = settings.model_dump()
        data = _obfuscate(data)
        self._config_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def update(self, **kwargs) -> AppSettings:
        """Update specific settings fields and save."""
        settings = self.load()
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        self.save(settings)
        return settings
