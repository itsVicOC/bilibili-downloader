"""Release discovery, verified downloads and staging for desktop updates."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from packaging.version import InvalidVersion, Version

from bilibili_downloader import __version__
from bilibili_downloader.core.models import UpdateChannel
from bilibili_downloader.core.update_protocol import (
    BuildInfo,
    InstallDataInApplicationError,
    RuntimeLease,
    UpdateError,
    atomic_json,
    ensure_install_data_outside,
    installed_build,
    sha256,
    subprocess_environment,
    validate_archive,
)

REPOSITORY = "itsVicOC/bilibili-downloader"
RELEASES_URL = f"https://api.github.com/repos/{REPOSITORY}/releases"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
ASSET_HOSTS = {"github.com", "release-assets.githubusercontent.com"}
MIRROR_ORIGIN = "https://dl.1008.si"
MIRROR_RELEASES_URL = f"{MIRROR_ORIGIN}/releases/index.json"


class UpdateCancelled(UpdateError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int
    mirror_download_url: str | None = None


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    tag: str
    published_at: str
    notes: str
    assets: tuple[ReleaseAsset, ...]

    @property
    def page_url(self):
        return f"{RELEASES_PAGE}/tag/{quote(self.tag, safe='')}"


@dataclass(frozen=True)
class PreparedUpdate:
    release: UpdateRelease
    build: BuildInfo
    archive: Path
    checksum: str
    target: Path
    staged: Path | None = None
    reason: str = ""

    @property
    def installable(self):
        return self.staged is not None and not self.reason


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise UpdateCancelled("更新已取消")


def _asset_url(url: str, *, mirror_url: str | None = None) -> str:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise UpdateError("更新下载地址无效") from exc
    if (
        parsed.scheme != "https"
        or (parsed.hostname not in ASSET_HOSTS and url != mirror_url)
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise UpdateError("更新下载地址不属于可信的下载服务")
    return url


def _mirror_url(asset: ReleaseAsset) -> str | None:
    prefix = f"https://github.com/{REPOSITORY}/releases/download/"
    if not asset.url.startswith(prefix):
        return None
    remainder = asset.url[len(prefix):]
    if remainder.count("/") != 1:
        return None
    tag, filename = remainder.split("/")
    if (not re.fullmatch(r"v?\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", tag)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", asset.name)
            or ".." in asset.name or filename != quote(asset.name, safe="")):
        return None
    expected = f"{MIRROR_ORIGIN}/releases/download/{tag}/{filename}"
    return expected if asset.mirror_download_url == expected else None


class UpdateService:
    def __init__(
        self,
        data_dir: Path,
        *,
        current_version=__version__,
        transport=None,
        installation=None,
    ):
        self.data_dir = Path(data_dir).resolve()
        self.cache_dir = self.data_dir / "updates"
        self.current_version = Version(current_version)
        self.transport = transport
        self.installation = (
            installation if installation is not None else installed_build()
        )
        try:
            if (
                self.installation
                and Version(self.installation[1].version) != self.current_version
            ):
                self.installation = None
        except InvalidVersion:
            self.installation = None

    def _client(self):
        # This client intentionally has no Bilibili cookies or Authorization header.
        return httpx.Client(
            transport=self.transport,
            timeout=httpx.Timeout(10, connect=5),
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"BiliFlow/{self.current_version}",
            },
            follow_redirects=False,
        )

    def check(
        self, channel: UpdateChannel | str, cancel: threading.Event | None = None
    ) -> UpdateRelease | None:
        channel = UpdateChannel(channel)
        try:
            return self._check_source(channel, cancel, MIRROR_RELEASES_URL)
        except (httpx.HTTPError, UpdateError, ValueError):
            _cancelled(cancel)
            return self._check_source(channel, cancel, RELEASES_URL)

    def _check_source(
        self, channel: UpdateChannel, cancel, source: str
    ) -> UpdateRelease | None:
        channel = UpdateChannel(channel)
        candidates = []
        deadline = time.monotonic() + 30
        with self._client() as client:
            page = 1
            while True:
                _cancelled(cancel)
                if time.monotonic() > deadline:
                    raise UpdateError("检查更新超时，请稍后重试")
                response = client.get(
                    source,
                    params={"per_page": 100, "page": page} if source == RELEASES_URL else None,
                    timeout=httpx.Timeout(10, connect=5) if source == RELEASES_URL else httpx.Timeout(5, connect=3),
                )
                if response.status_code in (403, 429):
                    raise UpdateError("GitHub 请求受到限制，请稍后重试")
                response.raise_for_status()
                try:
                    rows = response.json()
                except ValueError as exc:
                    raise UpdateError("GitHub 返回了无效的版本信息") from exc
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) for row in rows
                ):
                    raise UpdateError("GitHub 返回了无效的版本列表")
                for row in rows:
                    tag = row.get("tag_name")
                    if row.get("draft") or not isinstance(tag, str):
                        continue
                    try:
                        version = Version(tag)
                    except InvalidVersion:
                        continue
                    if version <= self.current_version:
                        continue
                    if channel == UpdateChannel.STABLE and (
                        row.get("prerelease") or version.is_prerelease
                    ):
                        continue
                    assets = []
                    prefix = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/"
                    for asset in (
                        row.get("assets", [])
                        if isinstance(row.get("assets", []), list)
                        else []
                    ):
                        if not isinstance(asset, dict):
                            continue
                        name, url, size = (
                            asset.get("name"),
                            asset.get("browser_download_url"),
                            asset.get("size"),
                        )
                        if (
                            isinstance(name, str)
                            and name
                            and "/" not in name
                            and "\\" not in name
                            and isinstance(url, str)
                            and url == prefix + quote(name, safe="")
                            and type(size) is int
                            and size >= 0
                            and asset.get("state", "uploaded") == "uploaded"
                        ):
                            candidate = ReleaseAsset(name, url, size, asset.get("mirror_download_url") if source == MIRROR_RELEASES_URL else None)
                            assets.append(replace(candidate, mirror_download_url=_mirror_url(candidate)))
                    candidates.append(
                        (
                            version,
                            UpdateRelease(
                                str(version),
                                tag,
                                str(row.get("published_at") or ""),
                                str(row.get("body") or ""),
                                tuple(assets),
                            ),
                        )
                    )
                # Link URLs are not followed: pagination stays on our fixed repository.
                if source != RELEASES_URL or not response.links.get("next"):
                    break
                page += 1
        _cancelled(cancel)
        return max(candidates, key=lambda pair: pair[0])[1] if candidates else None

    def _download(
        self, client, asset, destination, cancel, progress=None, *, maximum=None
    ):
        mirror = _mirror_url(asset)
        if mirror:
            try:
                return self._download_url(client, asset, mirror, destination, cancel, progress, maximum=maximum, mirror_url=mirror)
            except httpx.HTTPError:
                _cancelled(cancel)
                # Retry from byte zero with a fresh partial file. Integrity errors
                # and cancellation deliberately do not trigger source fallback.
        return self._download_url(client, asset, asset.url, destination, cancel, progress, maximum=maximum)

    def _download_url(
        self, client, asset, url, destination, cancel, progress=None, *, maximum=None, mirror_url=None
    ):
        partial = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
        url = _asset_url(url, mirror_url=mirror_url)
        try:
            for _attempt in range(6):
                _cancelled(cancel)
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        url = _asset_url(str(response.url.join(location)), mirror_url=mirror_url)
                        continue
                    response.raise_for_status()
                    received = 0
                    with partial.open("wb") as output:
                        for chunk in response.iter_bytes(1024 * 256):
                            _cancelled(cancel)
                            received += len(chunk)
                            if received > (maximum or asset.size):
                                raise UpdateError("更新下载大小与发布信息不匹配")
                            output.write(chunk)
                            if progress and asset.size:
                                progress(min(99, int(received * 100 / asset.size)))
                    if received != asset.size:
                        raise UpdateError("更新下载不完整，请重试")
                    os.replace(partial, destination)
                    return
            raise UpdateError("更新下载重定向次数过多")
        finally:
            partial.unlink(missing_ok=True)

    def prepare(
        self, release: UpdateRelease, cancel=None, progress=None
    ) -> PreparedUpdate:
        if not self.installation:
            raise UpdateError("当前运行方式不支持自动安装，请从版本页面下载并手动安装")
        target, current = self.installation
        build = replace(current, version=release.version)
        filename = (
            f"BilibiliDownloader-{build.platform}-{build.variant}-{release.tag}.zip"
        )
        matching = [asset for asset in release.assets if asset.name == filename]
        checksums = [
            asset for asset in release.assets if asset.name == "SHA256SUMS.txt"
        ]
        if len(matching) != 1 or len(checksums) != 1:
            raise UpdateError("此版本缺少匹配的更新包或 SHA-256 校验文件，请手动安装")
        asset = matching[0]
        if (
            not 0 < asset.size <= 2 * 1024**3
            or not 0 < checksums[0].size <= 1024 * 1024
        ):
            raise UpdateError("更新包或校验文件大小异常")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.cache_dir.chmod(0o700)
        if shutil.disk_usage(self.cache_dir).free < asset.size + 100 * 1024**2:
            raise UpdateError("下载更新所需磁盘空间不足")
        archive = self.cache_dir / filename
        checksum_file = self.cache_dir / f"checksums-{uuid.uuid4().hex}.txt"
        downloaded = False
        try:
            with self._client() as client:
                self._download(
                    client, checksums[0], checksum_file, cancel, maximum=1024 * 1024
                )
                expected = self._checksum_entry(checksum_file, filename)
                if not archive.is_file() or sha256(archive) != expected:
                    self._download(client, asset, archive, cancel, progress)
                    downloaded = True
            _cancelled(cancel)
            if sha256(archive) != expected:
                raise UpdateError("更新包 SHA-256 校验失败，请重新下载")
            expanded = validate_archive(archive, build)
            prepared = PreparedUpdate(release, build, archive, expected, target)
            try:
                prepared = self.stage(prepared, cancel, expanded=expanded)
            except InstallDataInApplicationError as exc:
                prepared = replace(prepared, reason=str(exc))
            except OSError as exc:
                prepared = replace(
                    prepared, reason=f"安装目录不可写或空间不足，请手动安装：{exc}"
                )
            self._save_prepared(prepared)
            if progress:
                progress(100)
            return prepared
        except Exception:
            if downloaded:
                archive.unlink(missing_ok=True)
            raise
        finally:
            checksum_file.unlink(missing_ok=True)

    @staticmethod
    def _checksum_entry(path: Path, filename: str) -> str:
        values = {}
        for line in path.read_text("utf-8").splitlines():
            match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?([^/\\]+)", line)
            if not match or match[2] in values:
                raise UpdateError("SHA-256 校验文件格式无效或包含重复记录")
            values[match[2]] = match[1].lower()
        if filename not in values:
            raise UpdateError("SHA-256 校验文件缺少当前更新包")
        return values[filename]

    def stage(
        self, prepared: PreparedUpdate, cancel=None, *, expanded=None
    ) -> PreparedUpdate:
        _cancelled(cancel)
        if sha256(prepared.archive) != prepared.checksum:
            raise UpdateError("已下载更新包的校验失败，请重新下载")
        expanded = (
            expanded
            if expanded is not None
            else validate_archive(prepared.archive, prepared.build)
        )
        target = prepared.target.resolve()
        if self.installation is None or target != self.installation[0].resolve():
            raise UpdateError("应用安装位置已变化，请重新检查更新")
        ensure_install_data_outside(target, self.data_dir, prepared.build)
        if shutil.disk_usage(target.parent).free < expanded + 100 * 1024**2:
            raise OSError("安装更新所需磁盘空间不足")
        staging = target.parent / f".{target.name}.update-{uuid.uuid4().hex}"
        staging.mkdir(mode=0o700)
        try:
            if prepared.build.platform == "macOS":
                environment = clean_subprocess_environment()
                process = subprocess.Popen(
                    ["/usr/bin/ditto", "-x", "-k", str(prepared.archive), str(staging)],
                    env=environment,
                )
                while process.poll() is None:
                    if cancel is not None and cancel.wait(0.1):
                        process.terminate()
                        process.wait(timeout=10)
                        raise UpdateCancelled("更新已取消")
                    if cancel is None:
                        time.sleep(0.1)
                if process.returncode != 0:
                    raise UpdateError("更新包解压失败")
            else:
                with zipfile.ZipFile(prepared.archive) as archive:
                    for entry in archive.infolist():
                        _cancelled(cancel)
                        archive.extract(entry, staging)
            _cancelled(cancel)
            root = staging / prepared.build.archive_root
            if prepared.build.read_from(root) != prepared.build:
                raise UpdateError("解包后的构建信息不匹配")
            # The helper repeats validation before replacement; this is only staging.
            result = replace(prepared, staged=root, reason="")
            self._save_prepared(result)
            return result
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _save_prepared(self, prepared):
        previous = None
        try:
            previous = json.loads(
                (self.cache_dir / "prepared.json").read_text("utf-8")
            ).get("staged")
        except (OSError, ValueError, AttributeError):
            pass
        atomic_json(
            self.cache_dir / "prepared.json",
            {
                "release": asdict(prepared.release),
                "build": asdict(prepared.build),
                "archive": str(prepared.archive),
                "checksum": prepared.checksum,
                "target": str(prepared.target),
                "staged": str(prepared.staged) if prepared.staged else None,
                "reason": prepared.reason,
            },
        )
        if isinstance(previous, str) and (
            prepared.staged is None or str(prepared.staged) != previous
        ):
            try:
                old = Path(previous)
                if (
                    old.name == prepared.build.archive_root
                    and old.parent.parent.resolve() == prepared.target.parent.resolve()
                    and re.fullmatch(
                        re.escape(f".{prepared.target.name}.update-") + r"[a-f0-9]{32}",
                        old.parent.name,
                    )
                ):
                    shutil.rmtree(old.parent, ignore_errors=True)
            except (OSError, ValueError):
                pass  # An obsolete cache entry must not invalidate the new package.

    def load_prepared(self) -> PreparedUpdate | None:
        try:
            value = json.loads((self.cache_dir / "prepared.json").read_text("utf-8"))
            release = UpdateRelease(
                **{
                    **value["release"],
                    "assets": tuple(
                        ReleaseAsset(**asset) for asset in value["release"]["assets"]
                    ),
                }
            )
            build = BuildInfo.parse(value["build"])
            archive = Path(value["archive"]).resolve()
            target = Path(value["target"]).resolve()
            if (
                not self.installation
                or target != self.installation[0].resolve()
                or archive.parent != self.cache_dir.resolve()
                or not archive.is_file()
                or Version(release.version) <= self.current_version
                or build != replace(self.installation[1], version=release.version)
                or not re.fullmatch(r"[a-f0-9]{64}", value["checksum"])
            ):
                return None
            # Re-extract from the checksummed ZIP on install; never trust an old staging directory.
            return PreparedUpdate(
                release,
                build,
                archive,
                value["checksum"],
                target,
                reason=value.get("reason", ""),
            )
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def launch_helper(self, prepared: PreparedUpdate, *, protected_paths=()):
        if not prepared.installable:
            raise UpdateError(prepared.reason or "更新包尚未准备完成")
        transaction_dir = self.cache_dir / uuid.uuid4().hex
        transaction_dir.mkdir(mode=0o700)
        current_root, current = self.installation
        helper = transaction_dir / current.helper
        shutil.copy2(current_root / current.resource_dir / current.helper, helper)
        helper.chmod(0o700)
        transaction = transaction_dir / "transaction.json"
        atomic_json(
            transaction,
            {
                "protocol": 1,
                "token": uuid.uuid4().hex,
                "parent_pid": os.getpid(),
                "target": str(prepared.target.resolve()),
                "staged": str(prepared.staged.resolve()),
                "archive": str(prepared.archive.resolve()),
                "checksum": prepared.checksum,
                "data_dir": str(self.data_dir),
                "build": asdict(prepared.build),
                "protected_paths": list(protected_paths),
            },
        )
        kwargs = (
            {"start_new_session": True}
            if os.name != "nt"
            else {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            }
        )
        environment = clean_subprocess_environment()
        # Windows' DLL search directory is inherited by child processes.
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            import ctypes

            ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            process = subprocess.Popen(
                [str(helper), "--transaction", str(transaction)],
                cwd=transaction_dir,
                env=environment,
                **kwargs,
            )
        finally:
            if sys.platform == "win32" and getattr(sys, "frozen", False):
                ctypes.windll.kernel32.SetDllDirectoryW(getattr(sys, "_MEIPASS", None))
        return process, transaction

    def install_mutex(self):
        return RuntimeLease(self.cache_dir / "install.lock", exclusive=True)


def clean_subprocess_environment():
    return subprocess_environment()
