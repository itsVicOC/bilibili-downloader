from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import prepare_bundled_ffmpeg


def _version_output() -> str:
    return "\n".join(
        [
            "ffmpeg version 7.1 Copyright (c) the FFmpeg developers",
            f"configuration: {' '.join(prepare_bundled_ffmpeg.CONFIGURE_ARGS)}",
        ]
    )


def test_validate_binary_output_accepts_minimal_lgpl_build() -> None:
    prepare_bundled_ffmpeg.validate_binary_output(
        _version_output(),
        "GNU Lesser General Public\nLicense version 2.1 or later",
    )


def test_validate_binary_output_accepts_quoted_configure_lists() -> None:
    version = _version_output().replace(
        "--enable-decoder=h264,hevc,libdav1d", "--enable-decoder='h264,hevc,libdav1d'",
    )
    prepare_bundled_ffmpeg.validate_binary_output(version, "GNU Lesser General Public License")


@pytest.mark.parametrize("forbidden", ["--enable-gpl", "--enable-nonfree"])
def test_validate_binary_output_rejects_non_lgpl_build(forbidden: str) -> None:
    with pytest.raises(ValueError, match="GPL or nonfree"):
        prepare_bundled_ffmpeg.validate_binary_output(
            f"{_version_output()} {forbidden}",
            "GNU Lesser General Public License version 2.1 or later",
        )


def test_validate_macos_binary_output_requires_macos_12_target() -> None:
    with pytest.raises(ValueError, match="deployment target"):
        prepare_bundled_ffmpeg.validate_macos_binary_output(_version_output())

    prepare_bundled_ffmpeg.validate_macos_binary_output(
        f"{_version_output()} {' '.join(prepare_bundled_ffmpeg.MACOS_CONFIGURE_ARGS)}"
    )


def test_validate_windows_binary_output_requires_native_threads() -> None:
    with pytest.raises(ValueError, match="self-contained threading"):
        prepare_bundled_ffmpeg.validate_windows_binary_output(_version_output())

    prepare_bundled_ffmpeg.validate_windows_binary_output(
        f"{_version_output()} {' '.join(prepare_bundled_ffmpeg.WINDOWS_CONFIGURE_ARGS)}"
    )


def test_prepare_release_metadata_adds_ffmpeg_only_to_full_sbom(
    tmp_path: Path, monkeypatch
) -> None:
    binary = tmp_path / "ffmpeg"
    binary.write_bytes(b"ffmpeg-binary")
    base_sbom = tmp_path / "base.cdx.json"
    base_sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"type": "library", "name": "BiliFlow"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        prepare_bundled_ffmpeg,
        "inspect_binary",
        lambda _binary: (
            _version_output(),
            "GNU Lesser General Public License version 2.1 or later",
        ),
    )
    lite_sbom = tmp_path / "lite.cdx.json"
    full_sbom = tmp_path / "full.cdx.json"
    notice = tmp_path / "FFMPEG-NOTICE.txt"
    dav1d_license = tmp_path / "DAV1D-LICENSE.txt"
    dav1d_license.write_text("dav1d BSD license text", encoding="utf-8")

    prepare_bundled_ffmpeg.prepare_release_metadata(
        binary, base_sbom, lite_sbom, full_sbom, notice, dav1d_license
    )

    lite_components = json.loads(lite_sbom.read_text())["components"]
    full_components = json.loads(full_sbom.read_text())["components"]
    assert [component["name"] for component in lite_components] == ["BiliFlow"]
    assert [component["name"] for component in full_components] == [
        "BiliFlow",
        "FFmpeg",
        "dav1d",
    ]
    assert full_components[1]["hashes"][0]["content"] == (
        prepare_bundled_ffmpeg.sha256(binary)
    )
    assert json.loads(full_sbom.read_text())["dependencies"] == [{
        "ref": full_components[1]["bom-ref"], "dependsOn": [full_components[2]["bom-ref"]],
    }]
    assert prepare_bundled_ffmpeg.FFMPEG_SOURCE_SHA256 in notice.read_text()
    assert "dav1d BSD license text" in notice.read_text()
