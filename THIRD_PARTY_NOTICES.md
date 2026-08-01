# Third-Party Notices

项目代码使用 MIT License。以下文件来自公共素材库，继续受各自许可证约束。

## FFmpeg

Release 中名称带 `full` 的 macOS 与 Windows 包包含独立的 FFmpeg 7.1 可执行程序，用于本地无损合并或封装下载流。名称带 `lite` 的包不包含 FFmpeg。

- 上游项目：[FFmpeg](https://ffmpeg.org/)
- 固定提交：`b08d7969c550a804a59511c7b83f2dd8cc0499b8`（`n7.1`）
- 许可证：LGPL 2.1 or later
- 对应源码：每个 Release 中的 `FFmpeg-7.1-source.tar.gz`

发布构建禁用 GPL、nonfree、外部库、网络协议、编码器与解码器，只启用本项目需要的本地 MOV/MP4 读取和 MP4/M4A/FLAC 封装。每个 full 包内的 `FFMPEG-NOTICE.txt`、`COPYING.LGPLv2.1` 和 `FFMPEG-LICENSE.md` 分别记录实际构建信息、许可证全文和上游许可说明。FFmpeg 是由 BiliFlow 作为子进程调用的独立程序，不适用本项目的 MIT License。

## Microsoft Fluent Emoji

应用图标主体：

- `bilibili_downloader/gui/assets/app_icon_source.png`
- 派生文件：`app_icon.png`、`app_icon.icns`、`app_icon.ico`
- 素材：Clapper board, 3D
- 来源：[microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji/blob/main/assets/Clapper%20board/3D/clapper_board_3d.png)
- 许可证：[MIT License](https://github.com/microsoft/fluentui-emoji/blob/main/LICENSE)

派生图标由 `scripts/build_app_icons.py` 添加 BiliFlow 品牌底板和角标后生成。

## OpenMoji

界面装饰图标：

| 本地文件 | OpenMoji 素材 | 来源 |
|---|---|---|
| `alien.png` | Alien Monster | [U+1F47E](https://openmoji.org/library/emoji-1F47E/) |
| `artist_palette.png` | Artist Palette | [U+1F3A8](https://openmoji.org/library/emoji-1F3A8/) |
| `clapper.png` | Clapper Board | [U+1F3AC](https://openmoji.org/library/emoji-1F3AC/) |
| `sparkle.png` | Sparkles | [U+2728](https://openmoji.org/library/emoji-2728/) |

OpenMoji 由 OpenMoji 项目及其贡献者创作，使用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 许可。本仓库保存为光栅化 PNG，并按相同许可证提供这些派生文件。

## Unsplash

- `bilibili_downloader/gui/assets/nebula.jpg`
- 用途：主界面 HeroPanel 的城堡背景。
- 来源：Unsplash 公共图片库。
- 许可证：[Unsplash License](https://unsplash.com/license)

该文件的既有下载元数据未保留具体作品页与摄影师字段，因此这里不虚构作者归属。Unsplash License 不要求署名；后续替换该素材时必须记录原始作品页、作者和下载日期。

## Trademarks

Bilibili、哔哩哔哩及其相关标识属于各自权利人。本项目与 Bilibili 无隶属、授权或背书关系，仓库中的名称仅用于说明工具兼容的服务。
