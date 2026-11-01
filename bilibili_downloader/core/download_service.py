"""Shared end-to-end download workflow for GUI and CLI callers."""

import logging
from pathlib import Path
from typing import Callable, Optional

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.danmaku import DanmakuDownloader
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.errors import redact_sensitive_text
from bilibili_downloader.core.metadata import download_cover, write_metadata
from bilibili_downloader.core.models import (
    DownloadItem,
    DownloadOutcome,
    OutputMode,
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
        if item.output_dir and Path(item.output_dir).expanduser().resolve() != self._output_dir:
            self._output_dir = Path(item.output_dir).expanduser().resolve()
            self._downloader = StreamDownloader(self._api_client, str(self._output_dir), ffmpeg_path=self._ffmpeg_path)

        def video_progress(progress: float, text: str) -> None:
            self._raise_if_cancelled()
            progress_callback(progress * 0.88, text)

        self._downloader.media_ready_callback = lambda path: self._record_outcome(item, self._media_outcome(path))
        video_path = self._downloader.download(item, video_progress)
        outcome = self._media_outcome(video_path)
        self._record_outcome(item, outcome)

        if (
            item.output_mode == OutputMode.VIDEO
            and outcome.actual_quality != item.selected_quality.value
        ):
            outcome.warnings.append(
                f"请求画质 {item.selected_quality.label} 不可用，已回退到代码 {outcome.actual_quality}"
            )
        if (
            item.output_mode == OutputMode.VIDEO
            and outcome.actual_video_codec != item.selected_video_codec
        ):
            outcome.warnings.append(
                f"请求的视频编码不可用，实际使用编码代码 {outcome.actual_video_codec}"
            )
        if (
            outcome.actual_audio_quality is not None
            and outcome.actual_audio_quality != item.selected_audio_quality
        ):
            outcome.warnings.append(
                "请求的音频规格不可用，"
                f"实际使用音频代码 {outcome.actual_audio_quality}"
            )

        if item.download_danmaku:
            self._raise_if_cancelled()
            progress_callback(0.90, "正在下载弹幕...")
            danmaku_path = Path(video_path).with_suffix(".ass")
            try:
                report = DanmakuDownloader.download_and_convert(item.video_info.cid, danmaku_path)
                outcome.danmaku_path = str(danmaku_path)
                self._record_outcome(item, outcome)
                if isinstance(report, ConversionReport):
                    outcome.warnings.extend(report.warnings("弹幕"))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Danmaku download failed for %s: %s",
                    item.video_info.content_identity,
                    redact_sensitive_text(exc),
                )
                outcome.warnings.append(f"弹幕下载失败：{exc}")

        if item.download_subtitle or item.download_all_subtitles:
            self._raise_if_cancelled()
            progress_callback(0.95, "正在下载字幕...")
            subtitles = self._select_subtitles(item, outcome)
            for index, subtitle in enumerate(subtitles):
                if item.download_all_subtitles:
                    language = sanitize_filename(
                        subtitle.lan or subtitle.lan_doc or str(index + 1)
                    )
                    subtitle_path = Path(video_path).with_name(
                        f"{Path(video_path).stem}.{language}.srt"
                    )
                else:
                    subtitle_path = Path(video_path).with_suffix(".srt")
                try:
                    report = SubtitleDownloader.download_and_convert(subtitle.url, subtitle_path)
                    outcome.subtitle_paths.append(str(subtitle_path))
                    self._record_outcome(item, outcome)
                    if isinstance(report, ConversionReport):
                        label = subtitle.lan_doc or subtitle.lan or str(index + 1)
                        outcome.warnings.extend(report.warnings(f"字幕 {label}"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Subtitle download failed for %s: %s",
                        item.video_info.content_identity,
                        redact_sensitive_text(exc),
                    )
                    label = subtitle.lan_doc or subtitle.lan or str(index + 1)
                    outcome.warnings.append(f"字幕 {label} 下载失败：{exc}")

        media_path = Path(video_path)
        if item.download_cover and item.video_info.cover_url:
            self._raise_if_cancelled()
            progress_callback(0.97, "正在保存封面...")
            try:
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

        if item.download_metadata:
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

        self._record_outcome(item, outcome)
        self._raise_if_cancelled()
        status = "下载完成（有警告）" if outcome.is_partial else "下载完成"
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
            tracks = item.video_info.subtitle_list
            if not tracks:
                outcome.warnings.append(f"字幕轨道查询失败：{exc}")
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
