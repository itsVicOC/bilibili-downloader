"""Shared end-to-end download workflow for GUI and CLI callers."""

import logging
import shutil
from contextlib import nullcontext
from pathlib import Path
from typing import Callable, Optional

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.danmaku import DanmakuDownloader
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.media_policy import specification_warnings
from bilibili_downloader.core.metadata import download_cover, write_metadata
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    SubtitleInfo,
)
from bilibili_downloader.core.subtitle import SubtitleDownloader
from bilibili_downloader.core.subtitle_provenance import (
    SUBTITLE_PROTOCOL_VERSION,
    publish_subtitle,
    subtitle_identity,
    subtitle_path_key,
    subtitle_proof,
    subtitle_verified,
)
from bilibili_downloader.core.timed_text import ConversionReport
from bilibili_downloader.utils.validators import sanitize_filename

logger = logging.getLogger(__name__)


class DownloadService:
    """Download video and requested companion files as one observable task."""

    def __init__(
        self,
        api_client: BilibiliAPIClient,
        output_dir: str,
        ffmpeg_path: Optional[str] = None,
        library_repository=None,
        outcome_callback=None,
        phase_callback=None,
    ):
        self._api_client = api_client
        self._ffmpeg_path = ffmpeg_path
        self._output_dir = Path(output_dir).expanduser().resolve()
        self._downloader = StreamDownloader(
            api_client,
            output_dir,
            ffmpeg_path=ffmpeg_path,
        )
        self._cancelled = False
        self._library = library_repository
        self._outcome_callback = outcome_callback
        self.phase_callback = phase_callback

    def cancel(self) -> None:
        self._cancelled = True
        self._downloader.cancel()

    @property
    def transfer_metrics(self):
        return self._downloader.transfer_metrics

    def download(
        self,
        item: DownloadItem,
        progress_callback: Callable[[float, str], None],
    ) -> DownloadOutcome:
        self._cancelled = False
        guard = self._library.media_lock(item, self._raise_if_cancelled) if self._library is not None else nullcontext()
        with guard:
            return self._download_impl(item, progress_callback)

    def _download_impl(self, item, progress_callback):
        if item.output_mode.value == "audio" and item.display_aspect_ratio != "original":
            raise ValueError("显示比例仅适用于视频输出")
        if item.output_dir and Path(item.output_dir).expanduser().resolve() != self._output_dir:
            self._output_dir = Path(item.output_dir).expanduser().resolve()
            self._downloader = StreamDownloader(self._api_client, str(self._output_dir), ffmpeg_path=self._ffmpeg_path)

        self._downloader.phase_callback = self.phase_callback

        def video_progress(progress: float, text: str) -> None:
            self._raise_if_cancelled()
            progress_callback(progress * 0.88, text)

        match = None
        lookup_warning = None
        if self._library is not None and not item.force_new:
            try:
                match = self._library.match_media(item)
            except Exception as exc:  # Preserve downloads when the inventory is unavailable.
                logger.warning("Media lookup failed: %s", redact_sensitive_text(exc))
                lookup_warning = "文件记录暂不可用，本次未能检查已有媒体。"
        aspect_source = None
        if (self._library is not None and not item.force_new and item.output_mode.value == "video"
                and item.display_aspect_ratio == "4:3" and (match is None or match.outcome is None)):
            original = item.model_copy(update={"display_aspect_ratio": "original"})
            candidate = self._library.match_media(original)
            if candidate.outcome is not None:
                aspect_source = candidate.outcome
        if item.reuse_media_path and (match is None or match.outcome is None) and aspect_source is None:
            raise ValueError("已有媒体无法访问或未通过核验，请重新定位或检查文件；未重新下载媒体。")
        if match is not None and match.outcome is not None:
            outcome = match.outcome.model_copy(deep=True)
            video_path = outcome.video_path
            outcome.reused_media = True
            outcome.warnings = []
            outcome.missing_artifacts = []
            needed = set(match.missing)
            progress_callback(0.88, "已复用已有媒体，正在检查附件…")
        elif aspect_source is not None:
            outcome = self._aspect_copy(item, aspect_source, progress_callback)
            video_path = outcome.video_path
            needed = {"subtitle", "metadata"} | {
                kind for kind in ("danmaku", "cover") if not getattr(outcome, f"{kind}_path")
            }
        else:
            self._downloader.media_ready_callback = lambda path: self._record_outcome(item, self._media_outcome(path))
            video_path = self._downloader.download(item, video_progress)
            outcome = self._media_outcome(video_path)
            if item.output_mode.value == "video" and item.display_aspect_ratio == "4:3":
                self._verify_aspect(outcome)
            needed = {"danmaku", "subtitle", "cover", "metadata"}
        outcome.spec_warnings = specification_warnings(item, outcome)
        outcome.warnings.extend(outcome.spec_warnings)
        if lookup_warning:
            outcome.warnings.append(lookup_warning)
        self._record_outcome(item, outcome)

        requested = [kind for kind in ("danmaku", "subtitle", "cover", "metadata")
                     if kind in needed and (getattr(item, f"download_{kind}") or kind == "subtitle" and item.download_all_subtitles)]
        done = 0
        def companion_phase(kind):
            nonlocal done
            from bilibili_downloader.core.media_policy import ARTIFACT_LABELS
            from bilibili_downloader.core.progress import DownloadPhase
            if self.phase_callback:
                self.phase_callback(DownloadPhase("attachments", f"补全{ARTIFACT_LABELS[kind]}", None, done, len(requested)))
            done += 1

        if item.download_danmaku and "danmaku" in needed:
            companion_phase("danmaku")
            self._raise_if_cancelled()
            progress_callback(0.90, "正在下载弹幕...")
            danmaku_path = Path(video_path).with_suffix(".ass")
            try:
                report = DanmakuDownloader.download_and_convert(item.video_info.cid, danmaku_path)
                outcome.danmaku_path = str(danmaku_path)
                if isinstance(report, ConversionReport):
                    outcome.artifact_warnings["danmaku"] = report.warnings("弹幕")
                self._record_outcome(item, outcome)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Danmaku download failed for %s: %s",
                    item.video_info.content_identity,
                    redact_sensitive_text(exc),
                )
                outcome.warnings.append(f"弹幕下载失败：{exc}")
                outcome.missing_artifacts.append("danmaku")

        if (item.download_subtitle or item.download_all_subtitles) and "subtitle" in needed:
            companion_phase("subtitle")
            self._raise_if_cancelled()
            progress_callback(0.95, "正在下载字幕...")
            subtitles = self._select_subtitles(item, outcome)
            outcome.subtitle_discovery_complete = bool(subtitles) and item.download_all_subtitles
            selection_discovered = (
                not item.download_all_subtitles
                and item.selected_subtitle_lan == "zh-en"
                and outcome.subtitle_discovery_languages is not None
            )
            if not subtitles and not selection_discovered and "subtitle" not in outcome.missing_artifacts:
                outcome.missing_artifacts.append("subtitle")
            for index, subtitle in enumerate(subtitles):
                existing = outcome.subtitle_languages.get(subtitle.lan)
                if existing and subtitle_verified(item.video_info, outcome, existing, subtitle.track_id):
                    continue
                if existing and Path(existing).parent == Path(video_path).parent:
                    subtitle_path = Path(existing)
                elif item.download_all_subtitles or item.selected_subtitle_lan == "zh-en":
                    language = sanitize_filename(
                        subtitle.lan or subtitle.lan_doc or str(index + 1)
                    )
                    subtitle_path = Path(video_path).with_name(
                        f"{Path(video_path).stem}.{language}.srt"
                    )
                else:
                    subtitle_path = Path(video_path).with_suffix(".srt")
                    if outcome.subtitle_paths and str(subtitle_path) in outcome.subtitle_paths:
                        subtitle_path = Path(video_path).with_name(f"{Path(video_path).stem}.{sanitize_filename(subtitle.lan or str(index + 1))}.srt")
                try:
                    report, proof = publish_subtitle(
                        item.video_info, subtitle, subtitle_path, SubtitleDownloader.download_and_convert,
                    )
                    if str(subtitle_path) not in outcome.subtitle_paths:
                        outcome.subtitle_paths.append(str(subtitle_path))
                    outcome.subtitle_languages[subtitle.lan] = str(subtitle_path)
                    outcome.subtitle_provenance[subtitle_path_key(subtitle_path)] = proof
                    if isinstance(report, ConversionReport):
                        label = subtitle.lan_doc or subtitle.lan or str(index + 1)
                        outcome.artifact_warnings[f"subtitle:{subtitle.lan}"] = report.warnings(f"字幕 {label}")
                    self._record_outcome(item, outcome)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Subtitle download failed for %s: %s",
                        item.video_info.content_identity,
                        redact_sensitive_text(exc),
                    )
                    label = subtitle.lan_doc or subtitle.lan or str(index + 1)
                    outcome.warnings.append(f"字幕 {label} 下载失败：{redact_sensitive_text(exc)}")
                    outcome.subtitle_discovery_complete = False
                    if "subtitle" not in outcome.missing_artifacts:
                        outcome.missing_artifacts.append("subtitle")

        media_path = Path(video_path)
        if item.download_cover and "cover" in needed:
            companion_phase("cover")
            self._raise_if_cancelled()
            progress_callback(0.97, "正在保存封面...")
            try:
                if not item.video_info.cover_url:
                    raise ValueError("没有可用的封面地址")
                outcome.cover_path = str(
                    download_cover(item.video_info.cover_url, media_path)
                )
                self._record_outcome(item, outcome)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Cover download failed for %s: %s",
                    item.video_info.content_identity,
                    redact_sensitive_text(exc),
                )
                outcome.warnings.append(f"封面保存失败：{exc}")
                outcome.missing_artifacts.append("cover")

        if item.download_metadata and "metadata" in needed:
            companion_phase("metadata")
            self._raise_if_cancelled()
            progress_callback(0.99, "正在写入元数据...")
            try:
                outcome.metadata_path = str(write_metadata(item, outcome, media_path))
                self._record_outcome(item, outcome)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Metadata write failed for %s: %s",
                    item.video_info.content_identity,
                    redact_sensitive_text(exc),
                )
                outcome.warnings.append(f"元数据保存失败：{exc}")
                outcome.missing_artifacts.append("metadata")

        outcome.warnings = list(dict.fromkeys([
            *outcome.warnings,
            *(warning for warnings in outcome.artifact_warnings.values() for warning in warnings),
        ]))
        self._record_outcome(item, outcome)
        self._raise_if_cancelled()
        status = outcome.result_label
        progress_callback(1.0, status)
        return outcome

    def _media_outcome(self, path):
        video, audio = self._downloader.last_video_stream, self._downloader.last_audio_stream
        return DownloadOutcome(video_path=path, actual_quality=video.id if video else None,
                               actual_video_codec=video.codecid if video else None,
                               actual_audio_quality=audio.id if audio else None)

    def _verify_aspect(self, outcome):
        from bilibili_downloader.core.ffmpeg import FFmpegManager
        from bilibili_downloader.core.models import OutputMode
        verification = FFmpegManager.inspect_media(Path(outcome.video_path), OutputMode.VIDEO, self._ffmpeg_path)
        if not verification.get("valid") or verification.get("display_aspect_ratio") != "4:3":
            raise ValueError("无法确认输出为 4:3，原始媒体已保留；请检查 FFmpeg 后重试。")
        outcome.applied_display_aspect_ratio = "4:3"
        outcome.actual_display_aspect_ratio = "4:3"
        outcome.media_verification = verification

    def _aspect_copy(self, item, original, progress_callback):
        from bilibili_downloader.core.downloader import _reserved_output_path
        from bilibili_downloader.core.ffmpeg import FFmpegManager
        progress_callback(0.82, "正在从已有媒体无损另存 4:3…")
        with _reserved_output_path(self._output_dir / item.relative_output_path) as destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            success, message = FFmpegManager.remux_aspect(
                Path(original.video_path), destination, custom_path=self._ffmpeg_path,
                cancel_checker=lambda: self._cancelled,
            )
            if not success:
                raise RuntimeError(f"4:3 另存失败：{message}")
            outcome = original.model_copy(deep=True)
            outcome.video_path = str(destination)
            outcome.media_signature = None
            outcome.warnings = []
            outcome.missing_artifacts = []
            outcome.reused_media = True
            outcome.subtitle_paths = []
            outcome.subtitle_languages = {}
            outcome.subtitle_provenance = {}
            outcome.subtitle_discovery_complete = False
            outcome.subtitle_discovery_languages = None
            outcome.subtitle_discovery_identity = ""
            outcome.subtitle_discovery_version = 0
            outcome.artifact_warnings = {}
            outcome.metadata_path = None
            self._verify_aspect(outcome)
            self._record_outcome(item, outcome)
            # Copy only verified attachments, with the new media's basename.
            for language, source in original.subtitle_languages.items():
                if subtitle_verified(item.video_info, original, source):
                    target = destination.with_name(f"{destination.stem}.{sanitize_filename(language)}.srt")
                    proof = subtitle_proof(original, source)
                    track = SubtitleInfo(track_id=proof.track_id)
                    _, copied_proof = publish_subtitle(
                        item.video_info, track, target, lambda _url, path: shutil.copyfile(source, path),
                        expected_sha256=proof.sha256,
                    )
                    outcome.subtitle_paths.append(str(target))
                    outcome.subtitle_languages[language] = str(target)
                    outcome.subtitle_provenance[subtitle_path_key(target)] = copied_proof
            for kind in ("danmaku", "cover"):
                source = getattr(original, f"{kind}_path")
                if source and Path(source).is_file():
                    target = destination.with_suffix(Path(source).suffix)
                    with _reserved_output_path(target) as target:
                        shutil.copyfile(source, target)
                    setattr(outcome, f"{kind}_path", str(target))
                else:
                    setattr(outcome, f"{kind}_path", None)
            return outcome

    def _record_outcome(self, item, outcome):
        if self._library is not None:
            try:
                self._library.record_download(item, outcome)
            except Exception as exc:  # noqa: BLE001
                warning = "文件已保存，文件记录暂未更新，可稍后恢复。"
                if warning not in outcome.warnings:
                    outcome.warnings.append(warning)
                logger.warning("Library registration failed: %s", redact_sensitive_text(exc))
        if self._outcome_callback is not None:
            self._outcome_callback(outcome.model_copy(deep=True))

    def _select_subtitles(
        self,
        item: DownloadItem,
        outcome: DownloadOutcome,
    ) -> list[SubtitleInfo]:
        tracks = []
        outcome.subtitle_discovery_languages = None
        outcome.subtitle_discovery_identity = ""
        outcome.subtitle_discovery_version = 0
        try:
            if item.video_info.bvid:
                tracks = self._api_client.get_subtitle_tracks(
                    item.video_info.bvid,
                    item.video_info.cid,
                )
            else:
                tracks = self._api_client.get_subtitle_tracks(
                    "",
                    item.video_info.cid,
                    aid=item.video_info.aid,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Subtitle discovery failed for %s: %s",
                item.video_info.content_identity,
                redact_sensitive_text(exc),
            )
            # Metadata tracks are not bound to the selected page and must not
            # replace a failed, page-specific subtitle lookup.
            outcome.warnings.append(f"字幕轨道查询失败：{redact_sensitive_text(exc)}")
            return []

        outcome.subtitle_discovery_languages = list(dict.fromkeys(track.lan for track in tracks))
        outcome.subtitle_discovery_identity = subtitle_identity(item.video_info)
        outcome.subtitle_discovery_version = SUBTITLE_PROTOCOL_VERSION
        logger.info("Subtitle discovery page=%s cid=%s tracks=%s protocol=%s",
                    item.video_info.content_identity, item.video_info.cid,
                    [(track.lan, track.track_id) for track in tracks], SUBTITLE_PROTOCOL_VERSION)
        if not tracks:
            outcome.warnings.append("该分 P 没有可下载的字幕")
            return []

        if item.download_all_subtitles:
            unique = {}
            for track in tracks:
                identity = track.lan or track.url
                unique.setdefault(identity, track)
            return list(unique.values())

        if item.selected_subtitle_lan == "zh-en":
            selected = {
                track.lan: track for track in tracks
                if track.lan.removeprefix("ai-").split("-")[0] in {"zh", "en"}
            }
            if not selected:
                outcome.warnings.append("该分 P 没有可下载的中文或英文字幕（含 AI 字幕）")
            return list(selected.values())

        for track in tracks:
            if track.lan == item.selected_subtitle_lan:
                return [track]

        selected = tracks[0]
        if item.selected_subtitle_lan:
            outcome.warnings.append(
                f"未找到 {item.selected_subtitle_lan} 字幕，已使用 {selected.lan_doc or selected.lan}"
            )
        return [selected]

    def _raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise RuntimeError("Download cancelled by user")
