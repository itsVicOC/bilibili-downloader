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

from bilibili_downloader.api.auth import AuthCookieBundle, filter_auth_cookies
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
KEYRING_ACCOUNT = "auth-cookie-bundle-v1"
LEGACY_KEYRING_ACCOUNT = "sessdata"


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
        return keyring.get_password(KEYRING_SERVICE, LEGACY_KEYRING_ACCOUNT) or ""
    except Exception as e:  # noqa: BLE001
        logger.debug("Keyring read failed: %s", e)
        return ""


def _load_auth_cookie_bundle() -> AuthCookieBundle | None:
    keyring = _get_keyring()
    if keyring is None:
        return None
    try:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        return AuthCookieBundle.model_validate_json(raw) if raw else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Authentication bundle read failed: %s", exc)
        return None


def _save_auth_cookie_bundle(bundle: AuthCookieBundle) -> bool:
    keyring = _get_keyring()
    if keyring is None:
        return False
    try:
        if bundle.cookies:
            serialized = bundle.model_dump_json()
            keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_ACCOUNT,
                serialized,
            )
            stored = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
            if not stored:
                return False
            verified = AuthCookieBundle.model_validate_json(stored)
            return verified.cookies == bundle.cookies
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
            except Exception:  # noqa: BLE001
                pass
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("Authentication bundle write failed: %s", exc)
        return False


def _delete_legacy_keyring_secret() -> None:
    keyring = _get_keyring()
    if keyring is None:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, LEGACY_KEYRING_ACCOUNT)
    except Exception:  # noqa: BLE001
        pass


class ConfigManager:
    """Load and save application settings to JSON."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._uses_default_path = config_path is None
        self._settings: Optional[AppSettings] = None
        self._auth_cookies: dict[str, str] = {}
        self._credentials_persistent = False

    @property
    def data_dir(self) -> Path:
        return self._config_path.parent

    @property
    def task_database_path(self) -> Path:
        return self.data_dir / "tasks.sqlite3"

    @property
    def auth_cookies(self) -> dict[str, str]:
        return dict(self._auth_cookies)

    @property
    def credentials_persistent(self) -> bool:
        return self._credentials_persistent

    def save_auth_cookies(self, cookies: dict[str, str]) -> bool:
        """Keep a filtered bundle in memory and persist only to the keyring."""
        self._auth_cookies = filter_auth_cookies(cookies)
        bundle = AuthCookieBundle(cookies=self._auth_cookies)
        self._credentials_persistent = _save_auth_cookie_bundle(bundle)
        if self._settings is not None:
            self._settings.sessdata = self._auth_cookies.get("SESSDATA", "")
        return self._credentials_persistent

    def clear_auth_cookies(self) -> bool:
        self._auth_cookies = {}
        self._credentials_persistent = _save_auth_cookie_bundle(AuthCookieBundle())
        _delete_legacy_keyring_secret()
        if self._settings is not None:
            self._settings.sessdata = ""
        return self._credentials_persistent

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
                self._load_and_migrate_credentials(self._settings)
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

        self._settings = AppSettings()
        self._load_and_migrate_credentials(self._settings)
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
        if sessdata and not self._auth_cookies:
            self.save_auth_cookies({"SESSDATA": sessdata})
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

    def _load_and_migrate_credentials(self, settings: AppSettings) -> None:
        bundle = _load_auth_cookie_bundle()
        if bundle and bundle.is_authenticated:
            self._auth_cookies = bundle.cookies
            self._credentials_persistent = True
            settings.sessdata = bundle.cookies.get("SESSDATA", "")
            return

        legacy_sessdata = settings.sessdata or _load_sessdata_from_keyring()
        settings.sessdata = ""
        if not legacy_sessdata:
            return
        self._auth_cookies = {"SESSDATA": legacy_sessdata}
        settings.sessdata = legacy_sessdata
        self._credentials_persistent = _save_auth_cookie_bundle(
            AuthCookieBundle(cookies=self._auth_cookies)
        )
        if self._credentials_persistent:
            _delete_legacy_keyring_secret()
            try:
                self.save(settings)
            except OSError as exc:
                logger.warning("Unable to remove migrated secret from config: %s", exc)

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
