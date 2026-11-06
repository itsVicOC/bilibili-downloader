"""Shared end-to-end download workflow for GUI and CLI callers."""

import logging
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
        if item.reuse_media_path and (match is None or match.outcome is None):
            raise ValueError("已有媒体无法访问或未通过核验，请重新定位或检查文件；未重新下载媒体。")
        if match is not None and match.outcome is not None:
            outcome = match.outcome.model_copy(deep=True)
            video_path = outcome.video_path
            outcome.reused_media = True
            outcome.warnings = []
            outcome.missing_artifacts = []
            needed = set(match.missing)
            progress_callback(0.88, "已复用已有媒体，正在检查附件…")
        else:
            self._downloader.media_ready_callback = lambda path: self._record_outcome(item, self._media_outcome(path))
            video_path = self._downloader.download(item, video_progress)
            outcome = self._media_outcome(video_path)
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
            if not subtitles:
                outcome.missing_artifacts.append("subtitle")
            for index, subtitle in enumerate(subtitles):
                from bilibili_downloader.core.library import readable_file
                if subtitle.lan in outcome.subtitle_languages and readable_file(outcome.subtitle_languages[subtitle.lan]):
                    continue
                if item.download_all_subtitles or item.selected_subtitle_lan == "zh-en":
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
                    report = SubtitleDownloader.download_and_convert(subtitle.url, subtitle_path)
                    if str(subtitle_path) not in outcome.subtitle_paths:
                        outcome.subtitle_paths.append(str(subtitle_path))
                    outcome.subtitle_languages[subtitle.lan] = str(subtitle_path)
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
                    outcome.warnings.append(f"字幕 {label} 下载失败：{exc}")
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
            languages = {lan.removeprefix("ai-").split("-")[0] for lan in selected}
            for code, label in (("zh", "中文"), ("en", "英文")):
                if code not in languages:
                    outcome.warnings.append(f"该分 P 没有可下载的{label}字幕（含 AI 字幕）")
                    if "subtitle" not in outcome.missing_artifacts:
                        outcome.missing_artifacts.append("subtitle")
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
