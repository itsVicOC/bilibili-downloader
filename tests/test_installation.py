import json
from pathlib import Path

import pytest

from bilibili_downloader.core.installation import (
    INSTALL_ID,
    INSTALL_MARKER,
    PAYLOAD_MANIFEST,
    macos_installation_notice,
    remove_managed_files,
    write_payload_manifest,
)
from bilibili_downloader.core.update_protocol import atomic_json
from scripts.package_installers import installer_filename


def managed_root(tmp_path):
    root = tmp_path / "BilibiliDownloader"
    root.mkdir()
    (tmp_path / INSTALL_MARKER).write_text(INSTALL_ID)
    return root


def test_uninstall_removes_new_update_files_but_preserves_user_media(tmp_path):
    root = managed_root(tmp_path)
    (root / "introduced.dll").write_bytes(b"program")
    changed = root / "modified.txt"
    changed.write_bytes(b"original")
    write_payload_manifest(root)
    changed.write_bytes(b"user-modified")
    (root / "saved.mp4").write_bytes(b"media")
    (tmp_path / "config.json").write_text("user config")
    remove_managed_files(root)
    assert not (root / "introduced.dll").exists()
    assert changed.read_bytes() == b"user-modified"
    assert (root / "saved.mp4").read_bytes() == b"media"
    assert (tmp_path / "config.json").read_text() == "user config"


@pytest.mark.parametrize("name", ["../user.mp4", "/tmp/user.mp4", r"..\user.mp4", "C:/user.mp4"])
def test_uninstall_rejects_manifest_escape_before_deleting_files(tmp_path, name):
    root = managed_root(tmp_path)
    owned = root / "owned.dll"
    owned.write_bytes(b"program")
    write_payload_manifest(root)
    payload = json.loads((root / PAYLOAD_MANIFEST).read_text())
    payload["files"][name] = "0" * 64
    atomic_json(root / PAYLOAD_MANIFEST, payload)
    with pytest.raises(ValueError, match="Unsafe"):
        remove_managed_files(root)
    assert owned.exists()


def test_uninstall_rejects_symlink_to_user_directory(tmp_path):
    root = managed_root(tmp_path)
    outside = tmp_path / "media"
    outside.mkdir()
    (outside / "user.mp4").write_bytes(b"keep")
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links unavailable")
    atomic_json(root / PAYLOAD_MANIFEST, {"protocol": 1, "files": {"linked/user.mp4": "0" * 64}})
    with pytest.raises(ValueError, match="symbolic"):
        remove_managed_files(root)
    assert (outside / "user.mp4").read_bytes() == b"keep"


def test_uninstall_requires_installation_marker(tmp_path):
    root = tmp_path / "BilibiliDownloader"
    root.mkdir()
    write_payload_manifest(root)
    with pytest.raises((OSError, ValueError)):
        remove_managed_files(root)


def test_dmg_and_translocation_notice_only_for_temporary_install_locations():
    assert macos_installation_notice(Path("/Volumes/BiliFlow/BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader"))
    assert macos_installation_notice(Path("/private/var/AppTranslocation/id/d/BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader"))
    assert not macos_installation_notice(Path("/Applications/BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader"))


def test_installer_filenames_keep_update_zip_namespace_and_reject_paths():
    assert installer_filename("Windows", "v0.8.1b1") == "BilibiliDownloader-Windows-full-v0.8.1b1-setup.exe"
    assert installer_filename("macOS", "dry-run-42").endswith("-full-dry-run-42.dmg")
    with pytest.raises(ValueError):
        installer_filename("macOS", "../escape")
