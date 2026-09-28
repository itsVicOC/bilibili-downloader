"""Live API, durable history, and scheduler behavior without external services."""

import io
import json
import queue
import sqlite3
import sys
import threading
import time
from concurrent.futures import Future
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from bilibili_downloader.api.client import BilibiliAPIError
from bilibili_downloader.api.live import BilibiliLiveClient, LiveAccessError
from bilibili_downloader.api.wbi import WBIKeyCache
from bilibili_downloader.core.live_models import (
    LiveRoom,
    LiveSettings,
    LiveState,
    LiveStream,
    LiveSubscription,
    RecordingSession,
)
from bilibili_downloader.core.live_repository import LiveRepository, utc_now
from bilibili_downloader.core.live_service import LiveService
from bilibili_downloader.core.recorder import (
    ENGINE_REVISION,
    MesioBackend,
    check_recorder,
)
from bilibili_downloader.core.task_repository import TaskDatabaseVersionError


def nav_payload(img_key="a" * 32, sub_key="b" * 32):
    return {
        "code": -101,
        "data": {
            "wbi_img": {
                "img_url": f"https://i0.hdslb.com/bfs/wbi/{img_key}.png",
                "sub_url": f"https://i0.hdslb.com/bfs/wbi/{sub_key}.png",
            }
        },
    }


@pytest.fixture(autouse=True)
def fresh_live_wbi_keys(monkeypatch):
    monkeypatch.setattr("bilibili_downloader.api.live._WBI_KEYS", WBIKeyCache())


@pytest.mark.parametrize(
    "value",
    [
        "3",
        "https://live.bilibili.com/3?broadcast_type=0",
        "https://live.bilibili.com/blanc/3",
    ],
)
def test_live_room_inputs(value):
    assert BilibiliLiveClient.parse_room_id(value) == 3


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "BV123",
        "https://live.bilibili.com.evil.test/3",
        "https://u:p@live.bilibili.com/3",
        "https://live.bilibili.com:9000/3",
    ],
)
def test_live_rejects_other_inputs(value):
    with pytest.raises(ValueError):
        BilibiliLiveClient.parse_room_id(value)


def play_payload():
    def entry(protocol, fmt, codec, quality):
        return {
            "protocol_name": protocol,
            "format": [
                {
                    "format_name": fmt,
                    "codec": [
                        {
                            "codec_name": codec,
                            "current_qn": quality,
                            "base_url": "/stream.flv",
                            "url_info": [
                                {
                                    "host": "https://a.bilivideo.com",
                                    "extra": "?sign=secret",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    return {
        "code": 0,
        "data": {
            "live_status": 1,
            "playurl_info": {
                "playurl": {
                    "g_qn_desc": [
                        {"qn": 10000, "desc": "原画"},
                        {"qn": 400, "desc": "蓝光"},
                    ],
                    "stream": [
                        entry("http_hls", "ts", "avc", 10000),
                        entry("http_stream", "flv", "avc", 10000),
                        entry("http_stream", "flv", "hevc", 20000),
                    ],
                }
            },
        },
    }


def test_live_quality_selection_and_cookie_boundary():
    seen = []

    def respond(request):
        if request.url.path.endswith("/nav"):
            return httpx.Response(200, json=nav_payload())
        seen.append(request)
        payload = play_payload()
        payload["data"]["all_special_types"] = [50]
        return httpx.Response(200, json=payload)

    client = BilibiliLiveClient(
        {"SESSDATA": "secret", "bad": "discard"}, httpx.MockTransport(respond)
    )
    try:
        streams = client.get_streams(3, 20000)
    finally:
        client.close()
    assert [s.format for s in streams] == ["flv", "ts"]
    assert streams[0].quality == 10000
    assert streams[0].warning
    assert "secret" not in repr(streams[0])
    assert seen[0].url.host == "api.live.bilibili.com"
    assert seen[0].headers["cookie"] == "SESSDATA=secret"
    assert "w_rid" in seen[0].url.params and "wts" in seen[0].url.params
    assert seen[0].url.params["codec"] == "0"


def test_short_id_is_normalized(monkeypatch):
    monkeypatch.setattr(
        "bilibili_downloader.api.live.resolve_short_url",
        lambda _: "https://live.bilibili.com/3",
    )

    def respond(request):
        if request.url.path.endswith("/nav"):
            return httpx.Response(200, json=nav_payload())
        data = (
            {"room_id": 23058, "short_id": 3, "uid": 1, "live_status": 0}
            if request.url.path.endswith("room_init")
            else {
                "room_info": {"title": "Title"},
                "anchor_info": {"base_info": {"uname": "Author"}},
            }
        )
        return httpx.Response(200, json={"code": 0, "data": data})

    client = BilibiliLiveClient(transport=httpx.MockTransport(respond))
    try:
        room = client.resolve_room("https://b23.tv/abc")
        assert room.room_id == 23058 and room.short_id == 3 and room.author == "Author"
    finally:
        client.close()


def test_anonymous_room_resolution_and_play_info_are_wbi_signed(monkeypatch):
    monkeypatch.setattr("bilibili_downloader.api.wbi.time.time", lambda: 1700000000)
    seen = []

    def respond(request):
        seen.append(request)
        assert "cookie" not in request.headers
        if request.url.path.endswith("/nav"):
            return httpx.Response(200, json=nav_payload())
        if request.url.path.endswith("room_init"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"room_id": 21414905, "uid": 123, "live_status": 1},
                },
            )
        assert request.url.params["wts"] == "1700000000"
        assert request.url.params["web_location"] == "444.8"
        assert len(request.url.params["w_rid"]) == 32
        if request.url.path.endswith("getInfoByRoom"):
            assert request.url.params["w_rid"] == "da0af1fda46e1290f260466755dc8bba"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "room_info": {"title": "公开直播间"},
                        "anchor_info": {"base_info": {"uname": "主播"}},
                    },
                },
            )
        payload = play_payload()
        payload["data"]["all_special_types"] = [50]
        return httpx.Response(200, json=payload)

    with_client = BilibiliLiveClient(transport=httpx.MockTransport(respond))
    try:
        room = with_client.resolve_room("21414905")
        assert room.room_id == 21414905 and room.author == "主播"
        assert with_client.get_streams(room.room_id)
    finally:
        with_client.close()
    assert sum(request.url.path.endswith("/nav") for request in seen) == 1


def test_live_clients_reuse_public_wbi_keys_and_refresh_rotation(monkeypatch):
    monkeypatch.setattr("bilibili_downloader.api.wbi.time.time", lambda: 1700000000)
    nav_count = 0
    signatures = []

    def respond(request):
        nonlocal nav_count
        if request.url.path.endswith("/nav"):
            nav_count += 1
            return httpx.Response(
                200, json=nav_payload("a" * 32 if nav_count == 1 else "c" * 32)
            )
        signatures.append(request.url.params["w_rid"])
        return httpx.Response(
            200,
            json={"code": -352, "message": "-352"}
            if len(signatures) == 1
            else play_payload(),
        )

    for _ in range(2):
        client = BilibiliLiveClient(transport=httpx.MockTransport(respond))
        try:
            assert client.get_streams(21414905)
        finally:
            client.close()
    assert nav_count == 2 and len(signatures) == 3
    assert signatures[0] != signatures[1]
    assert signatures[1] == signatures[2]


@pytest.mark.parametrize("code,attempts", [(-352, 2), (-412, 1), (-101, 1), (-403, 1)])
def test_live_signed_request_retries_only_one_signature_rejection(code, attempts):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=nav_payload()
            if request.url.path.endswith("/nav")
            else {"code": code, "message": "rejected"},
        )

    client = BilibiliLiveClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(BilibiliAPIError) as error:
            client.get_streams(21414905)
        assert error.value.code == code
    finally:
        client.close()
    assert len(seen) == 2 * attempts


def test_live_http_rate_limit_does_not_refresh_keys_or_retry():
    seen = []

    def respond(request):
        seen.append(request)
        return (
            httpx.Response(200, json=nav_payload())
            if request.url.path.endswith("/nav")
            else httpx.Response(429)
        )

    client = BilibiliLiveClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            client.get_streams(21414905)
    finally:
        client.close()
    assert len(seen) == 2


def test_invalid_nav_keys_are_not_cached():
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path.endswith("/nav"):
            return httpx.Response(
                200,
                json={"code": -101, "data": {}} if len(calls) == 1 else nav_payload(),
            )
        return httpx.Response(200, json=play_payload())

    client = BilibiliLiveClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RuntimeError, match="WBI"):
            client.get_streams(21414905)
        assert client.get_streams(21414905)
    finally:
        client.close()
    assert len(calls) == 3


@pytest.mark.parametrize(
    "change",
    [
        {"encrypted": True},
        {"is_locked": True},
        {"is_hidden": True},
        {"is_sp": 1},
        {"special_type": 1},
        {"all_special_types": [1]},
        {"all_special_types": [50, 1]},
    ],
)
def test_live_access_failures(change):
    with pytest.raises(LiveAccessError):
        BilibiliLiveClient._check_access(change)


@pytest.mark.parametrize("features", [[], [50], [3, 50]])
def test_public_room_features_are_not_access_restrictions(features):
    BilibiliLiveClient._check_access({"all_special_types": features})


def test_repository_recovers_sessions_and_does_not_store_credentials(tmp_path):
    repository = LiveRepository(tmp_path / "live.sqlite3")
    room = LiveRoom(
        room_id=1, title="test SESSDATA=hidden https://a.bilivideo.com/a?sign=secret"
    )
    repository.save_subscription(LiveSubscription(room=room, output_dir=str(tmp_path)))
    session = RecordingSession(
        id="one", room=room, directory=str(tmp_path), started_at=utc_now()
    )
    repository.save_session(session)
    assert repository.recover_interrupted()[0].status == "interrupted"
    assert repository.sessions()[0].warnings
    contents = (tmp_path / "manifest.json").read_text(encoding="utf-8")
    assert "hidden" not in contents and "sign=secret" not in contents
    with closing(sqlite3.connect(repository.path)) as db, db:
        assert (
            "secret"
            not in db.execute("SELECT payload FROM subscriptions").fetchone()[0]
        )


def test_repository_preserves_newer_database_and_quarantines_corruption(tmp_path):
    path = tmp_path / "live.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA user_version=9")
    with pytest.raises(TaskDatabaseVersionError):
        LiveRepository(path)
    with closing(sqlite3.connect(path)) as db, db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 9
    path.unlink()
    path.write_bytes(b"broken database")
    repository = LiveRepository(path)
    assert repository.recovered_database_path.read_bytes() == b"broken database"
    assert repository.sessions() == []


class ImmediateExecutor:
    def submit(self, action, *args):
        future = Future()
        try:
            future.set_result(action(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, **_kwargs):
        pass


class FakeBackend:
    def __init__(self, _path):
        self.pending = []
        self.exit_code = None
        self.stopping = False

    def start(self, stream, directory, segment_seconds):
        self.stream = stream
        self.directory = directory

    def stop(self):
        self.stopping = True

    def poll(self):
        return self.exit_code

    def events(self):
        events, self.pending = self.pending, []
        return events

    def kill(self):
        self.exit_code = -9


@pytest.fixture
def service(tmp_path):
    repository = LiveRepository(tmp_path / "live.sqlite3")
    clock = [100.0]
    client_state = {"status": 1, "live_time": "123", "failure": None, "calls": 0}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def get_status(self, room_id):
            client_state["calls"] += 1
            if client_state["failure"]:
                raise client_state["failure"]
            return LiveRoom(
                room_id=room_id,
                live_status=client_state["status"],
                live_time=client_state["live_time"],
            )

        def get_streams(self, *_args):
            return [
                LiveStream(
                    url="https://a.bilivideo.com/a?sign=secret",
                    format="flv",
                    quality=10000,
                )
            ]

        def resolve_room(self, _source):
            return self.get_status(1)

        def refresh_metadata(self, room):
            return room

        def close(self):
            pass

    subscription = LiveSubscription(
        room=LiveRoom(room_id=1, author="test"), output_dir=str(tmp_path / "recordings")
    )
    repository.save_subscription(subscription)
    value = LiveService(
        repository,
        LiveSettings(),
        backend_factory=FakeBackend,
        client_factory=Client,
        clock=lambda: clock[0],
        disk_usage=lambda _: SimpleNamespace(free=10 * 1024**3),
    )
    value._pool.shutdown(wait=True)
    value._pool = ImmediateExecutor()
    value.test_clock, value.client_state = clock, client_state
    yield value
    value.shutdown()


def connect(service):
    service.tick()
    service.tick()
    return service._rooms[1]


def test_automatic_recording_normalizes_and_deduplicates(service):
    runtime = connect(service)
    assert runtime.state == LiveState.RECORDING
    assert runtime.backend is not None
    service.command("add", source="https://live.bilibili.com/1")
    service.tick()
    assert len(service.repository.subscriptions()) == 1
    assert "已在列表中" in service.messages()[0]
    assert "sign=secret" not in Path(
        runtime.session.directory, "manifest.json"
    ).read_text(encoding="utf-8")


def test_stop_current_does_not_restart_until_new_broadcast(service):
    runtime = connect(service)
    service.command("stop", room_id=1)
    service.tick()
    assert runtime.backend.stopping
    runtime.backend.exit_code = 0
    service.tick()
    assert runtime.subscription.enabled
    assert runtime.session is None
    service.test_clock[0] += 100
    service.tick()
    service.tick()
    assert runtime.backend is None
    service.client_state["live_time"] = "456"
    service.test_clock[0] += 100
    service.tick()
    service.tick()
    assert runtime.backend is not None


def test_stop_while_start_query_is_pending_does_not_start_later(service):
    service.tick()
    service.command("stop", room_id=1)
    service.tick()
    runtime = service._rooms[1]
    assert runtime.backend is None
    assert runtime.subscription.enabled
    assert (
        runtime.subscription.skipped_broadcast
        == runtime.subscription.room.broadcast_key
    )


def test_disconnect_refreshes_url_and_records_gap(service):
    runtime = connect(service)
    old_backend = runtime.backend
    old_backend.exit_code = 1
    service.tick()
    assert runtime.state == LiveState.RECONNECTING
    assert runtime.next_check == 102
    service.test_clock[0] += 2
    service.tick()
    service.tick()
    assert runtime.backend is not old_backend
    runtime.backend.pending.append(
        {"event": "metrics", "bytes": 100, "duration": 1, "speed": 100}
    )
    service.tick()
    assert runtime.session.gaps


def test_offline_needs_two_checks_before_ending(service):
    runtime = connect(service)
    runtime.backend.exit_code = 0
    service.tick()
    service.client_state["status"] = 0
    service.test_clock[0] += 2
    service.tick()
    service.tick()
    assert runtime.session is not None
    service.test_clock[0] += 10
    service.tick()
    service.tick()
    assert runtime.session is None
    assert service.repository.sessions()[0].status == "completed"


def test_disk_full_stops_and_requires_user_action(service):
    runtime = connect(service)
    service._disk_usage = lambda _: SimpleNamespace(free=0)
    service.test_clock[0] += 5
    service.tick()
    assert runtime.blocked and runtime.backend.stopping
    runtime.backend.exit_code = 0
    service.tick()
    assert runtime.backend is None
    service.test_clock[0] += 1000
    service.tick()
    assert runtime.backend is None


@pytest.mark.parametrize("code", [-352, -412])
def test_rate_limit_cools_down(service, code):
    service.client_state["failure"] = BilibiliAPIError(code, "rate limited")
    service.tick()
    service.tick()
    runtime = service._rooms[1]
    assert runtime.next_check >= 400
    assert not runtime.blocked
    service.test_clock[0] = 399
    service.tick()
    assert service.client_state["calls"] == 1


def test_failed_room_addition_shows_actionable_redacted_error(service, monkeypatch):
    def resolve(_source):
        raise BilibiliAPIError(
            -352, "SESSDATA=secret https://a.bilivideo.com/a?sign=secret"
        )

    monkeypatch.setattr(service, "_resolve", resolve)
    service.command("add", source="21414905")
    service.tick()
    messages = service.messages()
    assert len(messages) == 1
    assert "风控或限流" in messages[0] and "建议" in messages[0]
    assert "secret" not in messages[0] and "api error" not in messages[0].lower()


def test_media_server_rate_limit_also_cools_down(service):
    runtime = connect(service)
    runtime.backend.pending.append({"event": "error", "code": "rate_limited"})
    runtime.backend.exit_code = 1
    service.tick()
    assert runtime.cooldown_until == 400
    count = service.client_state["calls"]
    service.test_clock[0] = 399
    service.command("enable", room_id=1)
    service.tick()
    assert service.client_state["calls"] == count and runtime.backend is None


def test_finalized_event_is_saved_before_process_exit(service):
    runtime = connect(service)
    path = runtime.backend.directory / "part_0.flv"
    path.write_bytes(b"fixture")
    runtime.backend.pending.append(
        {"event": "segment_finalized", "path": str(path), "bytes": 7, "duration": 2}
    )
    runtime.backend.exit_code = 0
    service.tick()
    assert service.repository.sessions()[0].segments[0].path == str(path)


def test_recorder_checks_reject_test_engine_and_wrong_protocol(tmp_path, monkeypatch):
    info = {
        "name": "biliflow-recorder",
        "v": 1,
        "engine_revision": ENGINE_REVISION,
        "formats": ["flv", "ts", "fmp4"],
        "test_fixtures": True,
    }
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps(info).encode()
        ),
    )
    with pytest.raises(ValueError, match="不匹配"):
        check_recorder(tmp_path / "engine")
    check_recorder(tmp_path / "engine", allow_test_engine=True)
    info["v"] = 9
    with pytest.raises(ValueError):
        check_recorder(tmp_path / "engine", allow_test_engine=True)


def test_live_export_checks_demuxer_and_keeps_original(tmp_path, monkeypatch):
    from bilibili_downloader.core.ffmpeg import FFmpegManager

    source = tmp_path / "source.flv"
    source.write_bytes(b"recording")
    monkeypatch.setattr(FFmpegManager, "find_executable", lambda _: tmp_path / "ffmpeg")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout=b" D mov QuickTime\n", stderr=b""
        ),
    )
    ok, error = FFmpegManager.remux_live(source, tmp_path / "out.mp4")
    assert not ok and "flv" in error
    assert source.read_bytes() == b"recording"


def test_metrics_include_current_segment_without_double_counting(service):
    runtime = connect(service)
    runtime.backend.pending = [
        {"event": "metrics", "bytes": 120, "duration": 4, "speed": 30},
        {"event": "segment_finalized", "path": "part.flv", "bytes": 100, "duration": 3},
    ]
    service.tick()
    row = service.snapshot()[0]
    assert row["size"] == 120 and row["duration"] == 4


def test_concurrency_queue_uses_freed_slot(service):
    for room_id in (2, 3):
        subscription = service._rooms[1].subscription.model_copy(deep=True)
        subscription.room.room_id = room_id
        service._rooms[room_id] = type(service._rooms[1])(subscription)
    runtime = connect(service)
    assert sum(r.backend is not None for r in service._rooms.values()) == 2
    assert service._rooms[3].state == LiveState.QUEUED
    service.command("disable", room_id=1)
    service.tick()
    runtime.backend.exit_code = 0
    service.test_clock[0] += 10
    service.tick()
    service.tick()
    assert service._rooms[3].backend is not None
    assert not runtime.subscription.enabled


def test_round_play_and_invalid_login_do_not_record(service):
    service.client_state["status"] = 2
    runtime = connect(service)
    assert runtime.backend is None
    service.client_state["failure"] = BilibiliAPIError(-101, "登录失效")
    service.test_clock[0] += 10
    service.tick()
    service.tick()
    assert runtime.blocked and runtime.backend is None


def test_disabling_an_idle_room_updates_its_visible_state(service):
    service.client_state["status"] = 0
    runtime = connect(service)
    service.command("disable", room_id=1)
    service.tick()
    assert runtime.state == LiveState.DISABLED
    assert not runtime.subscription.enabled


def test_sleep_detection_uses_wall_clock_when_monotonic_pauses(service):
    runtime = connect(service)
    service._wall_clock = lambda: service._last_wall_tick + 3600
    service.tick()
    assert runtime.backend.stopping and runtime.gap_start


def test_forced_exit_is_not_reported_as_clean_stop(service):
    runtime = connect(service)
    service.command("stop", room_id=1)
    service.tick()
    runtime.backend.exit_code = -9
    service.tick()
    session = service.repository.sessions()[0]
    assert session.status == "interrupted" and session.warnings


def test_corrupt_history_row_does_not_hide_valid_rows(tmp_path):
    repository = LiveRepository(tmp_path / "live.sqlite3")
    repository.save_subscription(
        LiveSubscription(room=LiveRoom(room_id=1), output_dir=str(tmp_path))
    )
    with closing(sqlite3.connect(repository.path)) as db, db:
        db.execute("INSERT INTO subscriptions VALUES (2, 'not json')")
    assert len(repository.subscriptions()) == 1
    assert repository.invalid_records


def test_backend_drains_final_segment_before_exit_and_uses_stdin(tmp_path, monkeypatch):
    import subprocess

    script = tmp_path / "fake_recorder.py"
    script.write_text("""import json, sys
from pathlib import Path
start = json.loads(sys.stdin.readline())
assert start['url'].endswith('?sign=ephemeral')
assert len(sys.argv) == 1
sys.stdin.readline()
path = Path(start['output_dir']) / 'part.flv'
path.write_bytes(b'media')
print(json.dumps({'v':1, 'event':'segment_finalized', 'path':str(path), 'bytes':5, 'duration':1}), flush=True)
print(json.dumps({'v':1, 'event':'stopped', 'reason':'requested'}), flush=True)
""")
    popen = subprocess.Popen
    monkeypatch.setattr(
        "bilibili_downloader.core.recorder.find_recorder", lambda _: script
    )
    monkeypatch.setattr(
        "bilibili_downloader.core.recorder.check_recorder", lambda *a, **kw: {}
    )
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda args, **kw: popen([sys.executable, str(script)], **kw),
    )
    backend = MesioBackend()
    backend.start(
        LiveStream(
            url="https://a.bilivideo.com/a?sign=ephemeral", format="flv", quality=400
        ),
        tmp_path,
        1800,
    )
    backend.stop()
    deadline = time.monotonic() + 5
    while backend.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    try:
        assert backend.poll() == 0
        events = backend.events()
        assert [e["event"] for e in events] == ["segment_finalized", "stopped"]
        assert Path(events[0]["path"]).read_bytes() == b"media"
        backend._stopping_at = None
        backend.stop()  # A late policy error can arrive after poll closed stdin.
    finally:
        backend.kill()


@pytest.mark.parametrize(
    "line",
    [
        b"[]\n",
        b'{"v":1,"event":"metrics","bytes":NaN}\n',
        b'{"v":1,"event":"error","code":[]}\n',
    ],
)
def test_invalid_engine_events_stop_without_echoing_payload(line):
    backend = MesioBackend.__new__(MesioBackend)
    killed = []
    backend._process = SimpleNamespace(
        stdout=io.BytesIO(line), kill=lambda: killed.append(True)
    )
    backend._events = queue.Queue()
    backend._lock = threading.Lock()
    backend._metrics = None
    backend._read()
    assert killed
    assert backend.events() == [{"event": "error", "code": "recorder_protocol_error"}]


def test_manifest_failure_does_not_discard_later_finalized_events(service, monkeypatch):
    runtime = connect(service)
    runtime.backend.pending = [
        {"event": "segment_finalized", "path": "one.flv", "bytes": 100, "duration": 1},
        {"event": "segment_finalized", "path": "two.flv", "bytes": 200, "duration": 2},
    ]

    def fail(_session):
        raise OSError("output disk unavailable")

    monkeypatch.setattr(service.repository, "save_session", fail)
    service.tick()
    assert [s.path for s in runtime.session.segments] == ["one.flv", "two.flv"]
    assert runtime.blocked and runtime.backend.stopping
