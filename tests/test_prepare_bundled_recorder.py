import json
from types import SimpleNamespace

import pytest

from scripts import prepare_bundled_recorder as recorder


def test_recorder_distribution_rejects_fixture_build_and_unpinned_engine(
    tmp_path, monkeypatch
):
    payload = {
        "name": "biliflow-recorder",
        "v": 1,
        "engine_revision": recorder.ENGINE_REVISION,
        "formats": ["flv", "ts", "fmp4"],
        "test_fixtures": False,
    }
    monkeypatch.setattr(
        recorder.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload).encode()),
    )
    assert recorder.inspect_binary(tmp_path / "binary")["v"] == 1
    payload["test_fixtures"] = True
    with pytest.raises(ValueError, match="production"):
        recorder.inspect_binary(tmp_path / "binary")
    payload["test_fixtures"] = False
    payload["engine_revision"] = "wrong"
    with pytest.raises(ValueError, match="pinned"):
        recorder.inspect_binary(tmp_path / "binary")


def test_recorder_sbom_has_binary_hash_lock_and_source_licenses(tmp_path, monkeypatch):
    root = tmp_path / "engine"
    root.mkdir()
    manifest = root / "Cargo.toml"
    manifest.write_text("manifest")
    manifest.with_name("Cargo.lock").write_text("pinned dependency graph")
    binary = root / "recorder"
    binary.write_bytes(b"production recorder")
    packages = [
        {
            "id": "root",
            "name": "biliflow-recorder",
            "version": "0.1.0",
            "source": None,
            "license": "MIT",
            "manifest_path": str(manifest),
        }
    ]
    metadata = {
        "packages": packages,
        "resolve": {"nodes": [{"id": "root", "dependencies": []}]},
    }
    monkeypatch.setattr(recorder, "cargo_metadata", lambda _: metadata)
    monkeypatch.setattr(recorder, "inspect_binary", lambda _: {"v": 1})
    sbom = root / "full.cdx.json"
    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "components": [{"name": "FFmpeg"}],
            }
        )
    )
    notice = root / "RECORDER-NOTICE.txt"
    recorder.prepare(binary, sbom, notice, manifest)
    recorder.prepare(binary, sbom, notice, manifest)
    components = json.loads(sbom.read_text())["components"]
    assert len(components) == 2
    assert components[1]["hashes"][0]["content"] == recorder.sha256(binary)
    assert recorder.ENGINE_REVISION in notice.read_text()
    assert "Permission is hereby granted" in notice.read_text()
    assert str(tmp_path) not in sbom.read_text()
