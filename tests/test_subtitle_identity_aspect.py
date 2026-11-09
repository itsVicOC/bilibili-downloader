"""Subtitle provenance and lossless display-ratio regressions."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.download_service import DownloadService
from bilibili_downloader.core.ffmpeg import FFmpegManager
from bilibili_downloader.core.library import LibraryRepository
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    OutputMode,
    SubtitleInfo,
    VideoInfo,
)
from bilibili_downloader.core.subtitle_provenance import (
    discovery_verified,
    publish_subtitle,
    subtitle_verified,
)
from bilibili_downloader.gui.dialogs.attachments import companion_status
from tests.test_workspaces import workspace as workspace


@pytest.mark.parametrize("identity", [
    {"bvid": "BVother", "cid": 22}, {"bvid": "BVdemo", "cid": 999}, {},
])
def test_player_response_identity_is_required(monkeypatch, identity):
    client = BilibiliAPIClient()
    client._client.close()
    client._client = httpx.Client(base_url="https://api.bilibili.com", transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"code": 0, "data": {
            **identity, "subtitle": {"subtitles": [{"id_str": "42", "lan": "ai-zh", "subtitle_url": "https://i0.hdslb.com/other"}]},
        }})))
    monkeypatch.setattr(client, "_sign_params", lambda params: params)
    try:
        with pytest.raises(ValueError, match="身份不符"):
            client.get_subtitle_tracks("BVdemo", 22)
    finally:
        client.close()


def test_av_subtitle_identity_and_missing_track_id(monkeypatch):
    client = BilibiliAPIClient()
    client._client.close()
    data = {"aid": 12, "cid": 22, "subtitle": {"subtitles": []}}
    client._client = httpx.Client(base_url="https://api.bilibili.com", transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"code": 0, "data": data})))
    monkeypatch.setattr(client, "_sign_params", lambda params: params)
    try:
        with pytest.raises(ValueError, match="身份不符"):
            client.get_subtitle_tracks("", 22, aid=13)
        data["subtitle"]["subtitles"] = [{"lan": "zh", "subtitle_url": "https://i0.hdslb.com/a"}]
        with pytest.raises(ValueError, match="轨道标识"):
            client.get_subtitle_tracks("", 22, aid=12)
    finally:
        client.close()


@pytest.mark.parametrize("all_languages", [False, True])
def test_legacy_wrong_subtitle_is_refreshed_without_media_transfer(tmp_path, monkeypatch, all_languages):
    media = tmp_path / "game.mp4"
    media.write_bytes(b"unchanged media")
    subtitle = media.with_suffix(".srt")
    subtitle.write_text("wrong legacy captions")
    item = DownloadItem(video_info=VideoInfo(bvid="BVgame", cid=22), download_subtitle=True,
                        download_all_subtitles=all_languages)
    original = DownloadOutcome(video_path=str(media), subtitle_paths=[str(subtitle)],
                               subtitle_languages={"zh-Hans": str(subtitle)}, subtitle_discovery_complete=True,
                               actual_quality=80, actual_video_codec=12, actual_audio_quality=30280)
    library = LibraryRepository(tmp_path / "library.db")
    library.record_download(item, original)
    assert library.match_media(item).missing == ("subtitle",)
    assert companion_status(item, original, "subtitle") == ("待重新获取（旧字幕未核验）", False, True)
    track = SubtitleInfo(track_id="correct-42", lan="zh-Hans", url="https://i0.hdslb.com/correct")
    service = DownloadService(SimpleNamespace(get_subtitle_tracks=lambda *_: [track]), str(tmp_path), library_repository=library)
    monkeypatch.setattr(service._downloader, "download", lambda *_: pytest.fail("must not transfer media"))
    writes = []

    def convert(_url, path):
        writes.append(path)
        path.write_text("correct game captions")

    monkeypatch.setattr("bilibili_downloader.core.download_service.SubtitleDownloader.download_and_convert", convert)
    result = service.download(item, lambda *_: None)
    assert result.reused_media and not result.missing_artifacts
    assert subtitle.read_text() == "correct game captions"
    assert subtitle.with_name("game.srt.unverified.bak").read_text() == "wrong legacy captions"
    assert media.read_bytes() == b"unchanged media"
    assert subtitle_verified(item.video_info, result, subtitle, "correct-42")
    assert discovery_verified(item.video_info, result)
    assert library.match_media(item).state == "saved"
    service.download(item, lambda *_: None)
    assert len(writes) == 1
    subtitle.write_text("modified outside the app")
    assert library.match_media(item).missing == ("subtitle",)


def test_failed_staged_subtitle_never_overwrites_old_file(tmp_path):
    path = tmp_path / "game.srt"
    path.write_text("keep original")

    def fail(_url, staging):
        staging.write_text("partial replacement")
        raise ConnectionError("offline")

    with pytest.raises(ConnectionError):
        publish_subtitle(VideoInfo(bvid="BVdemo", cid=1), SubtitleInfo(track_id="42"), path, fail)
    assert path.read_text() == "keep original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["game.srt"]


def test_proof_cannot_be_used_for_a_different_page(tmp_path):
    info = VideoInfo(bvid="BVdemo", cid=1)
    target = tmp_path / "video.srt"
    track = SubtitleInfo(track_id="42")
    _, proof = publish_subtitle(info, track, target, lambda _url, path: path.write_text("captions"))
    outcome = DownloadOutcome(video_path="video.mp4", subtitle_provenance={str(target): proof})
    assert subtitle_verified(info, outcome, target)
    assert not subtitle_verified(info.model_copy(update={"cid": 2}), outcome, target)
    assert not subtitle_verified(info.model_copy(update={"bvid": "BVother"}), outcome, target)
    assert not subtitle_verified(info, outcome, target, "other-track")


def test_copy_does_not_retrust_a_file_changed_after_verification(tmp_path):
    info = VideoInfo(bvid="BVdemo", cid=1)
    source, target = tmp_path / "source.srt", tmp_path / "copy.srt"
    source.write_text("verified captions")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text("changed after verification")
    target.write_text("keep existing file")
    with pytest.raises(ValueError, match="内容已变化"):
        publish_subtitle(info, SubtitleInfo(track_id="42"), target,
                         lambda _url, path: shutil.copyfile(source, path), expected_sha256=expected)
    assert target.read_text() == "keep existing file"


def test_av_only_provenance_includes_the_requested_aid(tmp_path):
    info = VideoInfo(aid=12, cid=22)
    target = tmp_path / "av.srt"
    _, proof = publish_subtitle(info, SubtitleInfo(track_id="42"), target,
                                lambda _url, path: path.write_text("captions"))
    outcome = DownloadOutcome(video_path="video.mp4", subtitle_provenance={str(target): proof})
    assert subtitle_verified(info, outcome, target)
    assert not subtitle_verified(info.model_copy(update={"aid": 13}), outcome, target)


def test_aspect_option_is_per_task_and_disabled_for_audio(workspace):
    workspace._aspect_combo.setCurrentIndex(1)
    item = workspace._make_download_item(VideoInfo(bvid="BVdemo", cid=1))
    assert item.display_aspect_ratio == "4:3"
    assert item.relative_output_path.name.endswith(".4x3.mp4")
    original = item.model_copy(update={"display_aspect_ratio": "original"})
    assert item.fingerprint != original.fingerprint
    workspace._output_mode_combo.setCurrentIndex(workspace._output_mode_combo.findData(OutputMode.AUDIO))
    assert not workspace._aspect_combo.isEnabled()
    assert workspace._make_download_item(item.video_info).display_aspect_ratio == "original"
    assert DownloadItem.model_validate({"video_info": {"bvid": "old"}}).display_aspect_ratio == "original"


@pytest.mark.parametrize("encoder,codecid", [("libx264", 7), ("libx265", 12)])
def test_lossless_aspect_copy_reuses_original_and_verified_subtitles(tmp_path, monkeypatch, encoder, codecid):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("requires FFmpeg and ffprobe")
    source = tmp_path / "game.mp4"
    cmd = [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:r=2",
           "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1",
           "-c:v", encoder, "-threads", "1", "-c:a", "aac"]
    if encoder == "libx265":
        cmd += ["-x265-params", "pools=1:log-level=error"]
    subprocess.run([*cmd, str(source)], capture_output=True, check=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    item = DownloadItem(video_info=VideoInfo(bvid="BVgame", cid=22, title="game"),
                        selected_video_codec=codecid, output_dir=str(tmp_path))
    outcome = DownloadOutcome(video_path=str(source), actual_quality=80, actual_video_codec=codecid, actual_audio_quality=30280)
    subtitle = source.with_suffix(".srt")
    _, proof = publish_subtitle(item.video_info, SubtitleInfo(track_id="42"), subtitle,
                                lambda _url, path: path.write_text("verified captions"))
    outcome.subtitle_paths = [str(subtitle)]
    outcome.subtitle_languages = {"zh-Hans": str(subtitle)}
    outcome.subtitle_provenance = {str(subtitle): proof}
    cover = tmp_path / "game.jpg"
    cover.write_bytes(b"original cover")
    orphan = tmp_path / "game.4x3.jpg"
    orphan.write_bytes(b"user-owned existing cover")
    outcome.cover_path = str(cover)
    library = LibraryRepository(tmp_path / "library.db")
    library.record_download(item, outcome)
    service = DownloadService(object(), str(tmp_path), ffmpeg_path=ffmpeg, library_repository=library)
    monkeypatch.setattr(service._downloader, "download", lambda *_: pytest.fail("must reuse local media"))
    requested = item.model_copy(update={"display_aspect_ratio": "4:3"})
    result = service.download(requested, lambda *_: None)
    output = Path(result.video_path)
    assert output.name == "game.4x3.mp4"
    assert result.applied_display_aspect_ratio == result.actual_display_aspect_ratio == "4:3"
    assert result.reused_media
    assert orphan.read_bytes() == b"user-owned existing cover"
    assert Path(result.cover_path).read_bytes() == b"original cover"
    assert Path(result.cover_path) != orphan
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert Path(result.subtitle_languages["zh-Hans"]).name == "game.4x3.zh-Hans.srt"
    assert subtitle_verified(item.video_info, result, result.subtitle_languages["zh-Hans"])
    assert library.match_media(requested).state == "saved"
    assert service.download(requested, lambda *_: None).video_path == str(output)
    packets = []
    for path in [source, output]:
        data = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-show_packets",
                                                   "-show_data_hash", "sha256", "-of", "json", str(path)]))
        packets.append([packet["data_hash"] for packet in data["packets"]])
        if path == output:
            video = next(s for s in data["streams"] if s["codec_type"] == "video")
            assert (video["width"], video["height"], video["display_aspect_ratio"]) == (1920, 1080, "4:3")
    assert packets[0] == packets[1]
    # Exercise the new-download path too, with local stand-ins for DASH inputs.
    from bilibili_downloader.core.models import StreamInfo
    fresh_root = tmp_path / "fresh"
    api = SimpleNamespace(get_play_url=lambda **_: {
        "video_streams": [StreamInfo(id=80, codecid=codecid)],
        "audio_streams": [StreamInfo(id=30280)],
    })
    fresh = DownloadService(api, str(fresh_root), ffmpeg_path=ffmpeg)
    monkeypatch.setattr(fresh._downloader, "_download_stream", lambda _stream, path, _progress: shutil.copyfile(source, path))
    fresh_result = fresh.download(requested.model_copy(update={"output_dir": str(fresh_root)}), lambda *_: None)
    assert fresh_result.actual_display_aspect_ratio == "4:3"
    success, _ = FFmpegManager.remux_aspect(source, tmp_path / "cancelled.mp4", ffmpeg, cancel_checker=lambda: True)
    assert not success and not (tmp_path / "cancelled.mp4").exists()
