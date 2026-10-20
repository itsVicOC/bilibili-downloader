"""Stable, GUI-independent identities for the bundled Xiao Liu collection."""

from dataclasses import dataclass

WORKSPACE_TITLES = {
    "download": "视频下载",
    "live": "直播录制",
    "tasks": "任务中心",
    "settings": "设置",
}
STYLE_TITLES = {"anime": "日系插画", "pixel": "复古像素", "watercolor": "轻绘水彩"}


@dataclass(frozen=True)
class BuiltinBackground:
    id: str
    title: str
    workspace: str
    style: str
    description: str

    @property
    def reference(self):
        return f"builtin:{self.id}"

    @property
    def image(self):
        extension = "png" if self.style == "pixel" else "webp"
        return f"backgrounds/{self.id}.{extension}"

    @property
    def thumbnail(self):
        return f"backgrounds/{self.id}-thumb.png"


BUILTIN_BACKGROUNDS = (
    BuiltinBackground(
        "download-anime-cloud",
        "云上收藏室",
        "download",
        "anime",
        "晴空、漂浮胶片与云端珍藏",
    ),
    BuiltinBackground(
        "download-pixel-station",
        "星轨驿站",
        "download",
        "pixel",
        "复古列车、收藏箱与流星",
    ),
    BuiltinBackground(
        "download-watercolor-sea",
        "海风信笺",
        "download",
        "watercolor",
        "海风、明信片与蓝白裙装",
    ),
    BuiltinBackground(
        "live-anime-neon", "霓虹开播", "live", "anime", "青紫演播室与温柔舞台灯"
    ),
    BuiltinBackground(
        "live-pixel-radio", "午夜电台", "live", "pixel", "像素录音室与城市夜景"
    ),
    BuiltinBackground(
        "live-watercolor-firefly",
        "萤光小舞台",
        "live",
        "watercolor",
        "森林露台、萤火与轻音乐",
    ),
    BuiltinBackground(
        "tasks-anime-orbit", "星轨调度", "tasks", "anime", "光轨、有序收藏匣与星际调度"
    ),
    BuiltinBackground(
        "tasks-pixel-cargo",
        "银河货运站",
        "tasks",
        "pixel",
        "太空港、运输机器人与星际包裹",
    ),
    BuiltinBackground(
        "tasks-watercolor-letters",
        "星笺归档",
        "tasks",
        "watercolor",
        "漂浮纸笺、星图与整齐书架",
    ),
    BuiltinBackground(
        "settings-anime-workshop",
        "午后工坊",
        "settings",
        "anime",
        "暖阳、调色盘与创作工具",
    ),
    BuiltinBackground(
        "settings-pixel-cottage",
        "像素小屋",
        "settings",
        "pixel",
        "温暖桌面、盆栽与复古电脑",
    ),
    BuiltinBackground(
        "settings-watercolor-journal",
        "薄荷手帐",
        "settings",
        "watercolor",
        "植物、画具与柔和纸张纹理",
    ),
)
_BY_REFERENCE = {entry.reference: entry for entry in BUILTIN_BACKGROUNDS}


def builtin_background(reference):
    return _BY_REFERENCE.get(reference) if isinstance(reference, str) else None
