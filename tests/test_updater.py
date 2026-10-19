import hashlib
import io
import json
import sqlite3
import stat
import threading
import zipfile
from contextlib import closing
from dataclasses import replace

import httpx
import pytest

from bilibili_downloader import __version__
from bilibili_downloader.core.update_protocol import (
    BUILD_INFO_FILENAME,
    BuildInfo,
    InstallDataInApplicationError,
    RuntimeLease,
    UpdateError,
    atomic_json,
    build_payload,
    ensure_install_data_outside,
    validate_archive,
)
from bilibili_downloader.core.updater import (
    MIRROR_ORIGIN,
    MIRROR_RELEASES_URL,
    RELEASES_URL,
    REPOSITORY,
    ReleaseAsset,
    UpdateCancelled,
    UpdateRelease,
    UpdateService,
)


def zip_bytes(build, *, extra=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        root = build.archive_root + "/"
        resources = root + (build.resource_dir + "/" if build.resource_dir else "")
        archive.writestr(root + build.executable, b"new executable")
        archive.writestr(resources + build.helper, b"helper")
        archive.writestr(
            resources + BUILD_INFO_FILENAME, json.dumps(build_payload(build))
        )
        for name, value in extra:
            archive.writestr(name, value)
    return stream.getvalue()


def installed_root(tmp_path, *, variant="lite", system="Windows"):
    build = BuildInfo(__version__, system, "x86_64", variant)
    root = tmp_path / "installation with spaces" / build.archive_root
    (root / build.resource_dir).mkdir(parents=True)
    (root / build.executable).parent.mkdir(parents=True, exist_ok=True)
    (root / build.executable).write_bytes(b"old executable")
    (root / build.resource_dir / build.helper).write_bytes(b"helper")
    atomic_json(root / build.resource_dir / BUILD_INFO_FILENAME, build_payload(build))
    return root, build


def release_row(tag, **fields):
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "body": "notes",
        "published_at": "2026-10-14T00:00:00Z",
        "assets": [],
        **fields,
    }


def release_fixture(build, content=None):
    content = zip_bytes(build) if content is None else content
    tag = f"v{build.version}"
    filename = f"BilibiliDownloader-{build.platform}-{build.variant}-{tag}.zip"
    prefix = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
    checksum = hashlib.sha256(content).hexdigest()
    checksums = f"{checksum}  {filename}\n".encode()
    release = UpdateRelease(
        build.version,
        tag,
        "2026-10-14",
        "notes",
        (
            ReleaseAsset(filename, prefix + filename, len(content)),
            ReleaseAsset("SHA256SUMS.txt", prefix + "SHA256SUMS.txt", len(checksums)),
        ),
    )

    def handler(request):
        assert (
            "cookie" not in request.headers and "authorization" not in request.headers
        )
        return httpx.Response(
            200,
            content=checksums
            if request.url.path.endswith("SHA256SUMS.txt")
            else content,
        )

    return release, httpx.MockTransport(handler)


@pytest.mark.parametrize(
    "channel,expected", [("stable", "0.9.0"), ("latest", "0.10.0rc10")]
)
def test_channel_and_version_ordering(tmp_path, channel, expected):
    rows = [
        release_row("v0.9.0"),
        release_row("v0.10.0rc2", prerelease=True),
        release_row("v0.10.0rc10"),
        release_row("v0.10.0b3"),
        release_row("v9.0.0", draft=True),
        release_row("unparseable"),
        release_row("v0.7.0"),
        release_row("v0.8.0"),
    ]
    service = UpdateService(
        tmp_path,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=rows)),
    )
    assert service.check(channel).version == expected


def test_pagination_never_follows_remote_link(tmp_path):
    pages = []

    def handler(request):
        if str(request.url) == MIRROR_RELEASES_URL:
            return httpx.Response(503)
        assert str(request.url).startswith(RELEASES_URL)
        pages.append(request.url.params["page"])
        if pages[-1] == "1":
            return httpx.Response(
                200,
                json=[release_row("v0.9.0b1")],
                headers={"Link": '<https://evil.example/leak>; rel="next"'},
            )
        return httpx.Response(200, json=[release_row("v0.9.0")])

    service = UpdateService(tmp_path, transport=httpx.MockTransport(handler))
    assert service.check("stable").version == "0.9.0"
    assert pages == ["1", "2"]


def test_mirror_discovery_and_asset_validation(tmp_path):
    name = "BilibiliDownloader-Windows-full-v0.9.0.zip"
    original = f"https://github.com/{REPOSITORY}/releases/download/v0.9.0/{name}"
    mirror = f"{MIRROR_ORIGIN}/releases/download/v0.9.0/{name}"
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=[release_row("v0.9.0", assets=[
            {"name": name, "size": 100, "browser_download_url": original, "mirror_download_url": mirror},
            {"name": "SHA256SUMS.txt", "size": 100, "browser_download_url": original.rsplit("/", 1)[0] + "/SHA256SUMS.txt", "mirror_download_url": "https://evil.example/checksums"},
        ])], headers={"Link": '<https://evil.example/>; rel="next"'})

    release = UpdateService(tmp_path, transport=httpx.MockTransport(handler)).check("stable")
    assert calls == [MIRROR_RELEASES_URL]
    assert release.assets[0].url == original
    assert release.assets[0].mirror_download_url == mirror
    assert release.assets[1].mirror_download_url is None


@pytest.mark.parametrize("bad", [httpx.Response(503), httpx.Response(200, json={}), httpx.Response(200, content=b"invalid")])
def test_mirror_metadata_failure_uses_github(tmp_path, bad):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return bad if request.url.host == "dl.1008.si" else httpx.Response(200, json=[release_row("v0.9.0")])

    assert UpdateService(tmp_path, transport=httpx.MockTransport(handler)).check("stable").version == "0.9.0"
    assert calls[0] == MIRROR_RELEASES_URL
    assert calls[1].startswith(RELEASES_URL)


@pytest.mark.parametrize("system,variant", [("Windows", "full"), ("Windows", "lite"), ("macOS", "full"), ("macOS", "lite")])
@pytest.mark.parametrize("failure", [False, True])
def test_mirror_download_and_network_fallback(tmp_path, system, variant, failure):
    name = f"BilibiliDownloader-{system}-{variant}-v0.9.0.zip"
    original = f"https://github.com/{REPOSITORY}/releases/download/v0.9.0/{name}"
    mirror = f"{MIRROR_ORIGIN}/releases/download/v0.9.0/{name}"
    content, calls = b"verified package", []

    def handler(request):
        calls.append(str(request.url))
        assert "cookie" not in request.headers and "authorization" not in request.headers
        if failure and request.url.host == "dl.1008.si":
            raise httpx.ReadTimeout("offline", request=request)
        return httpx.Response(200, content=content)

    service = UpdateService(tmp_path, transport=httpx.MockTransport(handler))
    destination = tmp_path / "package.zip"
    with service._client() as client:
        service._download(client, ReleaseAsset(name, original, len(content), mirror), destination, None)
    assert destination.read_bytes() == content
    assert calls == ([mirror, original] if failure else [mirror])
    assert not list(tmp_path.glob("*.part"))


def test_mirror_integrity_error_never_falls_back(tmp_path):
    installation = installed_root(tmp_path)
    release, _ = release_fixture(replace(installation[1], version="0.9.0"))
    release = replace(release, assets=tuple(replace(a, mirror_download_url=a.url.replace(f"https://github.com/{REPOSITORY}", MIRROR_ORIGIN)) for a in release.assets))
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.url.host == "dl.1008.si"
        if request.url.path.endswith("SHA256SUMS.txt"):
            return httpx.Response(200, content=f"{'0' * 64}  {release.assets[0].name}\n".encode())
        return httpx.Response(200, content=zip_bytes(replace(installation[1], version="0.9.0")))

    service = UpdateService(tmp_path / "data", installation=installation, transport=httpx.MockTransport(handler))
    with pytest.raises(UpdateError, match="SHA-256"):
        service.prepare(release)
    assert len(calls) == 2
    assert (installation[0] / installation[1].executable).read_bytes() == b"old executable"


def test_no_downgrade_and_rc_to_stable(tmp_path):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=[release_row("v0.8.0")])
    )
    assert (
        UpdateService(tmp_path, current_version="0.9.0b1", transport=transport).check(
            "stable"
        )
        is None
    )
    assert (
        UpdateService(tmp_path, current_version="0.8.0rc6", transport=transport)
        .check("stable")
        .version
        == "0.8.0"
    )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={}),
        httpx.Response(200, json=[None]),
        httpx.Response(200, content=b"invalid"),
        httpx.Response(429),
    ],
)
def test_invalid_response_and_rate_limit(tmp_path, response):
    with pytest.raises(UpdateError):
        UpdateService(
            tmp_path, transport=httpx.MockTransport(lambda request: response)
        ).check("latest")


def test_network_timeout_propagates(tmp_path):
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(httpx.ReadTimeout):
        UpdateService(tmp_path, transport=httpx.MockTransport(handler)).check("stable")


@pytest.mark.parametrize("variant", ["full", "lite"])
def test_verified_download_stage_and_pending_reload(tmp_path, variant):
    installation = installed_root(tmp_path, variant=variant)
    build = replace(installation[1], version="0.9.0b1")
    release, transport = release_fixture(build)
    service = UpdateService(
        tmp_path / "data", installation=installation, transport=transport
    )
    progress = []
    prepared = service.prepare(release, progress=progress.append)
    assert prepared.installable
    assert prepared.build.variant == variant
    assert (prepared.staged / build.executable).read_bytes() == b"new executable"
    assert (installation[0] / build.executable).read_bytes() == b"old executable"
    assert progress[-1] == 100
    pending = service.load_prepared()
    assert pending.release == release and pending.staged is None
    assert service.stage(pending).installable
    assert not prepared.staged.parent.exists()


def test_checksum_mismatch_preserves_old_program(tmp_path):
    installation = installed_root(tmp_path)
    build = replace(installation[1], version="0.9.0")
    release, _transport = release_fixture(build)
    archive_asset = release.assets[0]
    checksum_bytes = f"{'0' * 64}  {archive_asset.name}\n".encode()
    release = replace(
        release,
        assets=(archive_asset, replace(release.assets[1], size=len(checksum_bytes))),
    )
    service = UpdateService(
        tmp_path / "data",
        installation=installation,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=checksum_bytes
                if request.url.path.endswith("SHA256SUMS.txt")
                else zip_bytes(build),
            )
        ),
    )
    with pytest.raises(UpdateError, match="SHA-256"):
        service.prepare(release)
    assert (installation[0] / build.executable).read_bytes() == b"old executable"
    assert not list(service.cache_dir.glob("*.zip"))
    assert not list(service.cache_dir.glob("*.part"))


def test_download_cancellation(tmp_path):
    installation = installed_root(tmp_path)
    release, transport = release_fixture(replace(installation[1], version="0.9.0"))
    event = threading.Event()
    event.set()
    service = UpdateService(
        tmp_path / "data", installation=installation, transport=transport
    )
    with pytest.raises(UpdateCancelled):
        service.prepare(release, event)
    assert not (service.cache_dir / "prepared.json").exists()


def test_unwritable_installation_keeps_download_for_manual_install(
    tmp_path, monkeypatch
):
    installation = installed_root(tmp_path)
    release, transport = release_fixture(replace(installation[1], version="0.9.0"))
    service = UpdateService(
        tmp_path / "data", installation=installation, transport=transport
    )

    def denied(*_args, **_kwargs):
        raise PermissionError("read only")

    monkeypatch.setattr(service, "stage", denied)
    prepared = service.prepare(release)
    assert "手动安装" in prepared.reason and not prepared.installable
    assert prepared.archive.is_file()
    assert service.load_prepared().reason


def test_untrusted_redirect_rejected(tmp_path):
    installation = installed_root(tmp_path)
    release, _transport = release_fixture(replace(installation[1], version="0.9.0"))
    service = UpdateService(
        tmp_path / "data",
        installation=installation,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                302, headers={"Location": "https://evil.example/package.zip"}
            )
        ),
    )
    with pytest.raises(UpdateError, match="可信"):
        service.prepare(release)


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "BilibiliDownloader/../outside",
        "BilibiliDownloader/C:drive",
        "BilibiliDownloader/CON",
        "BilibiliDownloader/file.",
    ],
)
def test_unsafe_zip_paths(tmp_path, name):
    build = BuildInfo("0.9.0", "Windows", "x86_64", "lite")
    archive = tmp_path / "update.zip"
    archive.write_bytes(zip_bytes(build, extra=[(name, b"unsafe")]))
    with pytest.raises(UpdateError):
        validate_archive(archive, build)


def test_safe_mac_symlink_and_escaping_link(tmp_path):
    build = BuildInfo("0.9.0", "macOS", "arm64", "full")
    root = build.archive_root
    link = zipfile.ZipInfo(f"{root}/Contents/Resources/tool-link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o755) << 16
    archive = tmp_path / "update.zip"
    archive.write_bytes(zip_bytes(build, extra=[(link, b"biliflow-updater")]))
    validate_archive(archive, build)
    archive.write_bytes(zip_bytes(build, extra=[(link, b"../../../../outside")]))
    with pytest.raises(UpdateError, match="越出"):
        validate_archive(archive, build)


@pytest.mark.parametrize(
    "changed", [{"architecture": "arm64"}, {"variant": "full"}, {"version": "0.8.0"}]
)
def test_build_descriptor_mismatch(tmp_path, changed):
    expected = BuildInfo("0.9.0", "Windows", "x86_64", "lite")
    archive = tmp_path / "update.zip"
    archive.write_bytes(zip_bytes(replace(expected, **changed)))
    with pytest.raises(UpdateError, match="不匹配"):
        validate_archive(archive, expected)


def test_runtime_shared_and_exclusive_locks(tmp_path):
    first = RuntimeLease(tmp_path / "runtime.lock")
    second = RuntimeLease(tmp_path / "runtime.lock")
    updater = RuntimeLease(tmp_path / "runtime.lock", exclusive=True)
    assert first.acquire() and second.acquire()
    assert not updater.acquire()
    first.release()
    assert not updater.acquire()
    second.release()
    assert updater.acquire()
    assert not first.acquire()
    updater.release()
    assert first.acquire()
    first.release()


def test_missing_assets_or_source_installation_requires_manual_install(tmp_path):
    release = UpdateRelease("0.9.0", "v0.9.0", "", "", ())
    with pytest.raises(UpdateError, match="手动安装"):
        UpdateService(tmp_path).prepare(release)
    with pytest.raises(UpdateError, match="缺少"):
        UpdateService(tmp_path / "data", installation=installed_root(tmp_path)).prepare(
            release
        )


def test_cached_package_tampering_rejected_on_install(tmp_path):
    installation = installed_root(tmp_path)
    release, transport = release_fixture(replace(installation[1], version="0.9.0"))
    service = UpdateService(
        tmp_path / "data", installation=installation, transport=transport
    )
    prepared = service.prepare(release)
    prepared.archive.write_bytes(b"tampered")
    with pytest.raises(UpdateError, match="校验"):
        service.stage(prepared)


def test_duplicate_checksum_entries(tmp_path):
    path = tmp_path / "checksums"
    path.write_text(("0" * 64 + "  package.zip\n") * 2)
    with pytest.raises(UpdateError, match="重复"):
        UpdateService._checksum_entry(path, "package.zip")


def test_portable_install_with_downloads_inside_program_keeps_package_and_media(
    tmp_path,
):
    installation = installed_root(tmp_path)
    root, current = installation
    media = root / "downloads" / "saved.mp4"
    media.parent.mkdir()
    media.write_bytes(b"keep media")
    data = tmp_path / "data"
    atomic_json(data / "config.json", {"output_dir": str(media.parent)})
    release, transport = release_fixture(replace(current, version="0.9.0"))
    prepared = UpdateService(
        data, installation=installation, transport=transport
    ).prepare(release)
    assert not prepared.installable and "程序目录内" in prepared.reason
    assert prepared.archive.is_file() and media.read_bytes() == b"keep media"


def test_recorded_media_inside_installation_is_protected_after_output_setting_changes(
    tmp_path,
):
    root, build = installed_root(tmp_path)
    media = root / "old-recording.flv"
    media.write_bytes(b"recording")
    data = tmp_path / "data"
    data.mkdir()
    with closing(sqlite3.connect(data / "live.sqlite3")) as db, db:
        db.execute("CREATE TABLE sessions (payload TEXT)")
        db.execute(
            "INSERT INTO sessions VALUES (?)",
            (json.dumps({"segments": [{"path": str(media)}]}),),
        )
    with pytest.raises(InstallDataInApplicationError):
        ensure_install_data_outside(root, data, build)


def test_full_bundled_tool_paths_are_allowed_but_lite_custom_tools_are_protected(
    tmp_path,
):
    root, build = installed_root(tmp_path, variant="full")
    data = tmp_path / "data"
    atomic_json(data / "config.json", {"ffmpeg_path": str(root / "ffmpeg.exe")})
    ensure_install_data_outside(root, data, build)
    with pytest.raises(InstallDataInApplicationError):
        ensure_install_data_outside(root, data, replace(build, variant="lite"))


def test_old_download_cache_in_install_directory_prevents_replacement(tmp_path):
    root, build = installed_root(tmp_path)
    (root / "archive" / ".biliflow-parts").mkdir(parents=True)
    with pytest.raises(InstallDataInApplicationError, match="断点缓存"):
        ensure_install_data_outside(root, tmp_path / "data", build)
