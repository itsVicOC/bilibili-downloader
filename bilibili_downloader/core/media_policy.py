"""Shared media matching and user-facing specification descriptions."""

from bilibili_downloader.core.models import (
    AUDIO_CODEC_MAP,
    VIDEO_CODEC_MAP,
    OutputMode,
    VideoQuality,
)

ARTIFACT_LABELS = {"danmaku": "弹幕", "subtitle": "字幕", "cover": "封面", "metadata": "元数据"}


def quality_label(value):
    return next((q.label for q in VideoQuality if q.value == value), "未知画质")


def specification_warnings(item, outcome):
    warnings = []
    if item.output_mode == OutputMode.VIDEO:
        if outcome.actual_quality != item.selected_quality.value:
            warnings.append(f"请求 {item.selected_quality.label}，实际为 {quality_label(outcome.actual_quality)}")
        if outcome.actual_video_codec != item.selected_video_codec:
            warnings.append(
                f"请求 {VIDEO_CODEC_MAP.get(item.selected_video_codec, '未知编码')}，"
                f"实际为 {VIDEO_CODEC_MAP.get(outcome.actual_video_codec, '未知编码')}"
            )
    if outcome.actual_audio_quality is not None and outcome.actual_audio_quality != item.selected_audio_quality:
        warnings.append(
            f"请求 {AUDIO_CODEC_MAP.get(item.selected_audio_quality, '未知音质')}，"
            f"实际为 {AUDIO_CODEC_MAP.get(outcome.actual_audio_quality, '未知音质')}"
        )
    return warnings


def specifications_match(item, outcome):
    # Exact matching is deliberate: HDR, frame rate and bitrate variants are
    # not interchangeable merely because their numeric quality code is higher.
    return outcome.actual_audio_quality is not None and not specification_warnings(item, outcome)


class SpecificationMismatchError(ValueError):
    pass
