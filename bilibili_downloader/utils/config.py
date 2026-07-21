"""Settings persistence for the application."""

import base64
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from bilibili_downloader.core.models import AppSettings

logger = logging.getLogger(__name__)
LEGACY_CONFIG_PATH = Path.home() / ".bilibili-downloader" / "config.json"


def _default_config_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "BiliFlow" / "config.json"
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / "BiliFlow" / "config.json"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "biliflow" / "config.json"


DEFAULT_CONFIG_PATH = _default_config_path()
KEYRING_SERVICE = "bilibili-downloader"
KEYRING_ACCOUNT = "sessdata"


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


def _get_keyring():
    try:
        import keyring
    except ImportError:
        return None
    return keyring


def _load_sessdata_from_keyring() -> str:
    keyring = _get_keyring()
    if keyring is None:
        return ""
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT) or ""
    except Exception as e:  # noqa: BLE001
        logger.debug("Keyring read failed: %s", e)
        return ""


def _save_sessdata_to_keyring(sessdata: str) -> bool:
    keyring = _get_keyring()
    if keyring is None:
        return False
    try:
        if sessdata:
            keyring.set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, sessdata)
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
            except Exception:  # noqa: BLE001
                pass
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("Keyring write failed: %s", e)
        return False


class ConfigManager:
    """Load and save application settings to JSON."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._uses_default_path = config_path is None
        self._settings: Optional[AppSettings] = None

    def load(self) -> AppSettings:
        """Load settings from disk, or return defaults."""
        if self._settings is not None:
            return self._settings

        self._migrate_legacy_config()

        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                data = _deobfuscate(data)
                self._settings = AppSettings(**data)
                if not self._settings.sessdata:
                    self._settings.sessdata = _load_sessdata_from_keyring()
                return self._settings
            except (json.JSONDecodeError, OSError, ValueError) as e:
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

        self._settings = AppSettings(sessdata=_load_sessdata_from_keyring())
        return self._settings

    def save(self, settings: AppSettings) -> None:
        """Save settings to disk."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._config_path.parent.chmod(0o700)
        except OSError:
            logger.debug("Failed to restrict config directory: %s", self._config_path.parent)
        data = settings.model_dump()
        sessdata = data.pop("sessdata", "")
        if sessdata:
            if _save_sessdata_to_keyring(sessdata):
                data["sessdata"] = ""
            else:
                data["sessdata"] = sessdata
                data = _obfuscate(data)
        else:
            _save_sessdata_to_keyring("")
            data["sessdata"] = ""
        serialized = json.dumps(data, indent=2, ensure_ascii=False)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._config_path.parent,
                prefix=f".{self._config_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_file.write(serialized)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_path = Path(temp_file.name)
            try:
                temp_path.chmod(0o600)
            except OSError:
                logger.debug("Failed to chmod temporary config file: %s", temp_path)
            os.replace(temp_path, self._config_path)
            self._settings = settings
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _migrate_legacy_config(self) -> None:
        if (
            not self._uses_default_path
            or self._config_path.exists()
            or not LEGACY_CONFIG_PATH.is_file()
        ):
            return
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LEGACY_CONFIG_PATH, self._config_path)
            self._config_path.chmod(0o600)
            logger.info("Migrated legacy config to %s", self._config_path)
        except OSError as exc:
            logger.warning("Failed to migrate legacy config: %s", exc)

    def update(self, **kwargs) -> AppSettings:
        """Update specific settings fields and save."""
        settings = self.load()
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        self.save(settings)
        return settings
