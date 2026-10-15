"""Validate the installer handshake before allowing background work."""

import json
import os
from pathlib import Path

from packaging.version import Version

from bilibili_downloader import __version__
from bilibili_downloader.core.update_protocol import (
    BuildInfo,
    UpdateError,
    installed_build,
)


def startup_transaction(data_dir: Path):
    path = os.environ.pop("BILIFLOW_UPDATE_TRANSACTION", "")
    token = os.environ.pop("BILIFLOW_UPDATE_TOKEN", "")
    if not path:
        return None
    try:
        path = Path(path).resolve()
        value = json.loads(path.read_text("utf-8"))
        installation = installed_build()
        if (
            path.name != "transaction.json"
            or path.parent.parent != data_dir.resolve() / "updates"
            or value["token"] != token
            or value["protocol"] != 1
            or Path(value["data_dir"]).resolve() != data_dir.resolve()
            or not installation
            or installation[0] != Path(value["target"]).resolve()
            or installation[1] != BuildInfo.parse(value["build"])
            or Version(installation[1].version) != Version(__version__)
        ):
            raise UpdateError("新版启动的更新事务验证失败")
        return path, value
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UpdateError("无法确认新版启动，请等待更新程序恢复旧版") from exc


def startup_failure(data_dir: Path):
    path = os.environ.pop("BILIFLOW_UPDATE_FAILURE", "")
    if not path:
        return ""
    try:
        path = Path(path).resolve()
        if (
            path.name != "status.json"
            or path.parent.parent != data_dir.resolve() / "updates"
        ):
            return ""
        status = json.loads(path.read_text("utf-8"))
        return (
            status.get("message", "")
            if status.get("state") in ("failed", "rollback_failed")
            else ""
        )
    except (OSError, ValueError):
        return ""
