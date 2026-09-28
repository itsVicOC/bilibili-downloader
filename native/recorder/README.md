# biliflow-recorder

One process records one stream attempt. Python owns room discovery, authentication,
monitoring, retries and history. This binary owns media downloading, Mesio repair,
segmentation and file close boundaries. See `Cargo.toml` and `Cargo.lock` for the
pinned engine commit and exact dependency versions.

## JSON Lines protocol v1

All messages are UTF-8 JSON followed by a newline. Maximum command/event size is
64 KiB. stdout contains protocol messages only; upstream tracing is not installed.
Signed URLs must never be passed as argv, saved or printed by callers.

`--check` emits `ready` and exits, reporting `name`, adapter `version`, `v`,
`engine_revision`, `formats` and `test_fixtures`. The normal process also emits
`ready` before accepting its one start command:

```json
{"v":1,"command":"start","url":"https://trusted-media-host/path","output_dir":"/absolute/empty/directory","format":"flv","segment_seconds":1800}
{"v":1,"command":"stop"}
```

`format` is `flv`, `ts` or `fmp4`. Headers are fixed to User-Agent and Bilibili live
Referer; there is deliberately no cookie/header injection field. The only
subsequent command is stop. EOF, an oversized or invalid subsequent command also
stops the process. Normal inputs remain open throughout recording.

Events all include `v: 1` and `event`:

| Event | Fields / meaning |
|---|---|
| `ready` | Engine identity and capabilities |
| `started` | Attempt accepted; successful media arrival is indicated by metrics/files |
| `metrics` | Cumulative attempt `bytes`, media `duration` seconds, `speed` bytes/s |
| `segment_finalized` | Closed file `path`, zero-based `sequence`, `bytes`, `duration` |
| `error` | Fixed non-sensitive `code`; never raw upstream errors containing URLs |
| `stopped` | `reason` (`requested`, `eof`, `error`, `interrupted`), optional totals |

Progress uses one coalescing slot. Lifecycle events use a separate reliable
channel; Python drains all final events before acknowledging process exit. The
upstream complete callback precedes file handle destruction, so notifications
are deferred until the next open or writer completion. Empty HLS files produced
after the last split are discarded only after they close. Nonempty unfinished
files are preserved and never marked finalized.

Cancelling the downloader closes pipeline input and allows received media to
drain. A native 8-second watchdog bounds shutdown even when the parent is gone;
Python independently kills a stuck child after 10 seconds. A forced exit does not
invent finalized events or claim an intact recording.

## Media access boundary

Each attempt creates an ephemeral loopback relay protected by an unguessable
route token. Mesio only reads from this relay. It validates every upstream URL,
redirect, playlist variant, initialization resource and segment against the HTTPS
Bilibili media host allowlist. HLS key/session-key encryption is rejected before
the engine sees it. Playlists with ambiguous URI attributes fail closed. No
credentials are sent upstream. Loopback HTTP fixtures require an explicit build
feature that the desktop app and release preparation reject.

FLV filtered/encrypted tags and codecs outside AVC/AAC are rejected before repair.
HTTP 412/429 from the media server cancels the attempt and signals the Python
supervisor to enforce the same five-minute cooldown as API rate limits.

## Build / checks

```bash
cargo build --release --locked --manifest-path native/recorder/Cargo.toml
cargo fmt --manifest-path native/recorder/Cargo.toml -- --check
cargo clippy --locked --manifest-path native/recorder/Cargo.toml -- -D warnings
cargo test --locked --manifest-path native/recorder/Cargo.toml
```

Release uses Rust 1.96.0. On Windows, set `RUSTFLAGS=-C target-feature=+crt-static`;
on macOS set `MACOSX_DEPLOYMENT_TARGET=12.0`. Build from the repository root.

`scripts/prepare_bundled_recorder.py` checks the production binary, adds resolved
Rust dependencies and dependency edges to the full CycloneDX SBOM, hashes the
binary and lockfile, and collects actual dependency license/notice texts. Full
packages include `RECORDER-NOTICE.txt`; lite packages include neither executable
nor Rust runtime dependencies. No changes to upstream source are applied.
