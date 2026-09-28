"""Inspect the production recorder and add Rust provenance to a full SBOM.

Run after a locked Cargo build, on the same host/target as that build. License
texts are read from the resolved dependency sources, not fetched from HEAD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import quote

ENGINE_REVISION = "1897d736a4560f267700d7c4c1cf02dffc3c4c56"
ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_binary(binary: Path) -> dict:
    result = subprocess.run(
        [str(binary.resolve()), "--check"], capture_output=True, check=True, timeout=10
    )
    info = json.loads(result.stdout)
    if (
        not isinstance(info, dict)
        or info.get("name") != "biliflow-recorder"
        or info.get("v") != 1
        or info.get("engine_revision") != ENGINE_REVISION
        or info.get("test_fixtures") is not False
        or not isinstance(info.get("formats"), list)
        or not {"flv", "ts", "fmp4"}.issubset(info.get("formats", []))
    ):
        raise ValueError("Recorder is not the pinned production build")
    return info


def cargo_metadata(manifest: Path) -> dict:
    rustc = subprocess.run(
        ["rustc", "-vV"], capture_output=True, text=True, check=True
    ).stdout
    host = next(
        line.removeprefix("host: ")
        for line in rustc.splitlines()
        if line.startswith("host: ")
    )
    result = subprocess.run(
        [
            "cargo",
            "metadata",
            "--locked",
            "--format-version",
            "1",
            "--filter-platform",
            host,
            "--manifest-path",
            str(manifest),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def license_texts(package: dict) -> list[tuple[str, str]]:
    if package["name"] == "biliflow-recorder":
        return [("LICENSE", (ROOT / "LICENSE").read_text(encoding="utf-8"))]
    root = Path(package["manifest_path"]).parent
    paths = {
        p
        for pattern in ("LICENSE*", "LICENCE*", "COPYING*", "NOTICE*")
        for p in root.rglob(pattern)
        if p.is_file() and "target" not in p.parts
    }
    if package.get("license_file"):
        paths.add(root / package["license_file"])
    # This published crate omitted its repository's license text. The vendored
    # copy is from the exact .cargo_vcs_info commit; see licenses/README.md.
    if not paths and (package["name"], package["version"]) == ("alloc-stdlib", "0.2.4"):
        paths.add(ROOT / "native/recorder/licenses/alloc-stdlib-0.2.4-LICENSE")
    # Workspace crates inherit Mesio's MIT license from its repository root.
    if not paths and ENGINE_REVISION in (package.get("source") or ""):
        for parent in root.parents:
            if (parent / "LICENSE").is_file():
                paths.add(parent / "LICENSE")
                break
    if not paths:
        raise ValueError(
            f"No license text found for {package['name']} {package['version']}"
        )
    result = []
    for path in sorted(paths):
        try:
            label = str(path.relative_to(root))
        except ValueError:
            label = path.name
        result.append((label, path.read_text(encoding="utf-8", errors="replace")))
    return result


def prepare(binary: Path, sbom: Path, notice: Path, manifest: Path) -> None:
    info = inspect_binary(binary)
    metadata = cargo_metadata(manifest)
    resolved = {node["id"] for node in metadata["resolve"]["nodes"]}
    packages = sorted(
        (p for p in metadata["packages"] if p["id"] in resolved),
        key=lambda p: (p["name"], p["version"]),
    )
    components = []
    references = {}
    texts = [
        "BiliFlow recorder and Rust dependency notices",
        "",
        f"Engine source: https://github.com/hua0512/rust-srec/tree/{ENGINE_REVISION}",
        "Engine baseline: mesio-v0.6.0 (mesio-engine crate 0.5.0)",
        f"Recorder SHA-256: {sha256(binary)}",
        f"Cargo.lock SHA-256: {sha256(manifest.with_name('Cargo.lock'))}",
        "Build: cargo build --release --locked (no test-fixtures feature)",
        "",
    ]
    for package in packages:
        name, version = package["name"], package["version"]
        source = package.get("source") or "BiliFlow source tree"
        reference = (
            f"rust:{name}@{version}:{hashlib.sha256(source.encode()).hexdigest()[:12]}"
        )
        references[package["id"]] = reference
        component = {
            "type": "application" if name == "biliflow-recorder" else "library",
            "name": name,
            "version": version,
            "bom-ref": reference,
            "properties": [{"name": "biliflow:source", "value": source}],
        }
        if source.startswith("registry+"):
            component["purl"] = f"pkg:cargo/{quote(name)}@{quote(version)}"
            checksum = Path(package["manifest_path"]).parent / ".cargo-checksum.json"
            if checksum.is_file():
                value = json.loads(checksum.read_text())["package"]
                if value:
                    component["hashes"] = [{"alg": "SHA-256", "content": value}]
        if name == "biliflow-recorder":
            component["hashes"] = [{"alg": "SHA-256", "content": sha256(binary)}]
            component["properties"].extend(
                [
                    {"name": "biliflow:mesio-revision", "value": ENGINE_REVISION},
                    {"name": "biliflow:protocol", "value": str(info["v"])},
                    {
                        "name": "biliflow:lock-sha256",
                        "value": sha256(manifest.with_name("Cargo.lock")),
                    },
                ]
            )
        if package.get("license"):
            component["licenses"] = [
                {"expression": package["license"].replace("/", " OR ")}
            ]
        components.append(component)
        texts.extend(
            [
                f"=== {name} {version} ===",
                f"Source: {source}",
                f"License: {package.get('license', 'see text')}",
            ]
        )
        for label, text in license_texts(package):
            texts.extend([f"--- {label} ---", text, ""])
    payload = json.loads(sbom.read_text(encoding="utf-8"))
    existing = payload.setdefault("components", [])
    existing[:] = [c for c in existing if not c.get("bom-ref", "").startswith("rust:")]
    existing.extend(components)
    dependencies = payload.setdefault("dependencies", [])
    dependencies[:] = [
        d for d in dependencies if not d.get("ref", "").startswith("rust:")
    ]
    dependencies.extend(
        {
            "ref": references[n["id"]],
            "dependsOn": [references[d] for d in n["dependencies"] if d in references],
        }
        for n in metadata["resolve"]["nodes"]
    )
    notice.parent.mkdir(parents=True, exist_ok=True)
    notice.write_text("\n".join(texts), encoding="utf-8")
    sbom.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument(
        "--sbom", required=True, type=Path, help="Full variant SBOM to augment"
    )
    parser.add_argument("--notice", required=True, type=Path)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "native/recorder/Cargo.toml"
    )
    args = parser.parse_args()
    prepare(args.binary, args.sbom, args.notice, args.manifest)


if __name__ == "__main__":
    main()
