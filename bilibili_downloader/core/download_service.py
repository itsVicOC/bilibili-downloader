"""Shared end-to-end download workflow for GUI and CLI callers."""

import logging
from pathlib import Path
from typing import Callable, Optional

from bilibili_downloader.api.client import BilibiliAPIClient
from bilibili_downloader.core.danmaku import DanmakuDownloader
from bilibili_downloader.core.downloader import StreamDownloader
from bilibili_downloader.core.models import DownloadItem, DownloadOutcome, SubtitleInfo
from bilibili_downloader.core.subtitle import SubtitleDownloader

logger = logging.getLogger(__name__)


class DownloadService:
    """Download video and requested companion files as one observable task."""

    def __init__(
        self,
        api_client: BilibiliAPIClient,
        output_dir: str,
        ffmpeg_path: Optional[str] = None,
    ):
        self._api_client = api_client
        self._downloader = StreamDownloader(
            api_client,
            output_dir,
            ffmpeg_path=ffmpeg_path,
        )
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self._downloader.cancel()

    def download(
        self,
        item: DownloadItem,
        progress_callback: Callable[[float, str], None],
    ) -> DownloadOutcome:
        self._cancelled = False

        def video_progress(progress: float, text: str) -> None:
            self._raise_if_cancelled()
            progress_callback(progress * 0.88, text)

        video_path = self._downloader.download(item, video_progress)
        outcome = DownloadOutcome(
            video_path=video_path,
            actual_quality=(
                self._downloader.last_video_stream.id
                if self._downloader.last_video_stream else None
            ),
            actual_video_codec=(
                self._downloader.last_video_stream.codecid
                if self._downloader.last_video_stream else None
            ),
        )

        if outcome.actual_quality != item.selected_quality.value:
            outcome.warnings.append(
                f"请求画质 {item.selected_quality.label} 不可用，已回退到代码 {outcome.actual_quality}"
            )
        if outcome.actual_video_codec != item.selected_video_codec:
            outcome.warnings.append(
                f"请求的视频编码不可用，实际使用编码代码 {outcome.actual_video_codec}"
            )

        if item.download_danmaku:
            self._raise_if_cancelled()
            progress_callback(0.90, "正在下载弹幕...")
            danmaku_path = Path(video_path).with_suffix(".ass")
            try:
                DanmakuDownloader.download_and_convert(item.video_info.cid, danmaku_path)
                outcome.danmaku_path = str(danmaku_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Danmaku download failed for %s: %s", item.video_info.bvid, exc)
                outcome.warnings.append(f"弹幕下载失败：{exc}")

        if item.download_subtitle:
            self._raise_if_cancelled()
            progress_callback(0.95, "正在下载字幕...")
            subtitle = self._select_subtitle(item, outcome)
            if subtitle is not None:
                subtitle_path = Path(video_path).with_suffix(".srt")
                try:
                    SubtitleDownloader.download_and_convert(subtitle.url, subtitle_path)
                    outcome.subtitle_paths.append(str(subtitle_path))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Subtitle download failed for %s: %s", item.video_info.bvid, exc)
                    outcome.warnings.append(f"字幕下载失败：{exc}")

        self._raise_if_cancelled()
        status = "下载完成（有警告）" if outcome.is_partial else "下载完成"
        progress_callback(1.0, status)
        return outcome

    def _select_subtitle(
        self,
        item: DownloadItem,
        outcome: DownloadOutcome,
    ) -> Optional[SubtitleInfo]:
        tracks = []
        try:
            tracks = self._api_client.get_subtitle_tracks(
                item.video_info.bvid,
                item.video_info.cid,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Subtitle discovery failed for %s: %s", item.video_info.bvid, exc)
            tracks = item.video_info.subtitle_list
            if not tracks:
                outcome.warnings.append(f"字幕轨道查询失败：{exc}")
                return None

        if not tracks:
            outcome.warnings.append("该分 P 没有可下载的字幕")
            return None

        for track in tracks:
            if track.lan == item.selected_subtitle_lan:
                return track

        selected = tracks[0]
        if item.selected_subtitle_lan:
            outcome.warnings.append(
                f"未找到 {item.selected_subtitle_lan} 字幕，已使用 {selected.lan_doc or selected.lan}"
            )
        return selected

    def _raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise RuntimeError("Download cancelled by user")
