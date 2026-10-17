"""Build native full installers from the already prepared PyInstaller payload."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.version import Version

from bilibili_downloader.core.installation import PAYLOAD_MANIFEST
from bilibili_downloader.core.update_protocol import BuildInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def installer_filename(system: str, release_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", release_id):
        raise ValueError("Unsafe release id")
    suffix = "-setup.exe" if system == "Windows" else ".dmg"
    return f"BilibiliDownloader-{system}-full-{release_id}{suffix}"


def build_installer(root: Path, system: str, release_id: str, output: Path, compiler=None):
    root, output = root.resolve(), output.resolve()
    info = BuildInfo("", system, "", "full").read_from(root)
    if info.platform != system or info.variant != "full":
        raise ValueError("Installer requires a matching full payload")
    if {"darwin": "macOS", "win32": "Windows"}.get(sys.platform) != system:
        raise ValueError("Build installers on their native platform")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / installer_filename(system, release_id)
    if destination.exists():
        destination.unlink()
    if system == "macOS":
        with tempfile.TemporaryDirectory(prefix="biliflow-dmg-") as temporary:
            source = Path(temporary) / "volume"
            source.mkdir()
            subprocess.run(["/usr/bin/ditto", str(root), str(source / root.name)], check=True)
            (source / "Applications").symlink_to("/Applications")
            (source / "安装说明.txt").write_text(
                "将 BiliFlow 应用拖入 Applications 文件夹，然后从应用程序中打开。\n"
                "更新前请退出正在运行的 BiliFlow；配置、任务与下载文件保存在应用之外。\n"
                "Drag BiliFlow into Applications, then launch it from Applications.\n",
                encoding="utf-8",
            )
            subprocess.run([
                "/usr/bin/hdiutil", "create", "-volname", "BiliFlow",
                "-srcfolder", str(source), "-format", "UDZO", "-fs", "HFS+",
                "-o", str(destination),
            ], check=True)
    elif system == "Windows":
        if not (root / PAYLOAD_MANIFEST).is_file():
            raise ValueError("Windows payload must be prepared with prepare_update_bundle")
        compiler = compiler or shutil.which("ISCC.exe")
        if not compiler:
            raise ValueError("Inno Setup 6.7.3 ISCC.exe is required")
        version = Version(info.version)
        numeric = ".".join(str(v) for v in (*version.release, 0, 0, 0, 0)[:4])
        subprocess.run([
            str(compiler), f"/DSourceDir={root}", f"/DOutputDir={output}",
            f"/DReleaseId={release_id}", f"/DAppVersion={info.version}",
            f"/DNumericVersion={numeric}",
            str(PROJECT_ROOT / "packaging/windows/BiliFlow.iss"),
        ], check=True)
    else:
        raise ValueError("Unsupported installer platform")
    if not destination.is_file():
        raise ValueError("Installer was not created")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--platform", choices=("macOS", "Windows"), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd())
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args()
    print(build_installer(args.root, args.platform, args.release_id, args.output_dir, args.compiler))


if __name__ == "__main__":
    main()
