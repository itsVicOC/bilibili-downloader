<p align="center">
  <a href="https://1008.si/">
    <img src="bilibili_downloader/gui/assets/app_icon.png" alt="BiliFlow 软件图标" width="128" height="128">
  </a>
</p>

<h1 align="center">BiliFlow</h1>

<p align="center">
  B 站视频下载 · 直播录制 · 本地归档<br>
  用一个桌面工作台，整理你有权保存的影音内容。
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="https://1008.si/">官方网站</a> ·
  <a href="https://github.com/itsVicOC/bilibili-downloader/releases/latest">下载正式版</a> ·
  <a href="docs/README.md">使用文档</a> ·
  <a href="CHANGELOG.md">更新日志</a> ·
  <a href="https://github.com/itsVicOC/bilibili-downloader/issues">反馈与建议</a>
</p>

<p align="center">
  <a href="https://1008.si/"><img src="https://img.shields.io/badge/Website-1008.si-8B5CF6" alt="官方网站：1008.si"></a>
  <a href="https://github.com/itsVicOC/bilibili-downloader/releases/latest"><img src="https://img.shields.io/github/v/release/itsVicOC/bilibili-downloader" alt="最新正式版"></a>
  <a href="https://github.com/itsVicOC/bilibili-downloader/releases"><img src="https://img.shields.io/github/downloads/itsVicOC/bilibili-downloader/total" alt="GitHub Release 累计下载量"></a>
  <a href="https://github.com/itsVicOC/bilibili-downloader/actions/workflows/ci.yml"><img src="https://github.com/itsVicOC/bilibili-downloader/actions/workflows/ci.yml/badge.svg" alt="CI 状态"></a>
  <a href="docs/BUILDING.md"><img src="https://img.shields.io/badge/Python-3.11%20--%203.12-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11–3.12"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/itsVicOC/bilibili-downloader" alt="MIT License"></a>
</p>

**BiliFlow**（仓库名 `bilibili-downloader`）是一款开源的 B 站桌面下载与直播录制工具，同时提供 **GUI 与 CLI**。从单个视频、多 P、番剧到合集、系列和收藏夹，你可以筛选批量任务、暂停后继续下载，并将视频或音频与字幕、弹幕、封面、元数据一起整理到本地。

支持 Windows、macOS 和 Linux；Windows 与 Apple Silicon Mac 提供预构建包，Linux 可从源码运行。项目代码采用 MIT License。

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/biliflow-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/images/biliflow-light.png">
    <img src="docs/images/biliflow-dark.png" alt="BiliFlow 视频下载工作台，支持跟随系统的深浅主题" width="960">
  </picture>
</p>

**快速导航：** [项目亮点](#项目亮点) · [下载与安装](#下载与安装) · [五分钟上手](#五分钟上手) · [界面预览](#界面预览) · [支持范围](#支持范围) · [从源码运行](#从源码运行) · [常见问题](#常见问题) · [文档](#文档) · [参与和支持](#参与和支持)

> BiliFlow 不会绕过会员、付费、地区、DRM 或账号权限。账号可观看不等于拥有永久复制、传播或商业使用权；使用前请阅读[版权与合规说明](docs/COPYRIGHT.md)。

## 项目亮点

| 能力 | 说明 |
|---|---|
| 多来源解析 | 支持 BV、AV、`ep/ss/md`、Bilibili 完整 URL、b23.tv 短链、UP 主合集/系列与收藏夹 |
| 完整媒体规格 | 支持 240P–8K、HDR、Dolby Vision，以及 AVC、HEVC、AV1；自动选择匹配音轨 |
| 本地归档 | 输出 MP4、M4A 或 Hi-Res FLAC，可同时保存 ASS 弹幕、SRT 字幕、封面与 JSON 元数据 |
| 可恢复任务中心 | 下载队列、当前录制与录制历史集中展示；按筛选或全部任务批量操作、撤销记录移除，异常退出后可继续断点下载 |
| 直播录制 | 应用内监控、自动/手动录制、分段与重连、单场直播合并 MP4、目录跟随及独立设置；详见[使用指南](docs/LIVE_RECORDING.md) |
| 批量与多 P | 支持多 P 单选/全选、批量预览筛选、进度与取消、失败项重试、来源分页、精确去重和 1–8 路并发 |
| 安全登录 | 默认扫码登录，保留 Cookie 备用入口；侧栏显示用户名与头像，登录后直接管理账号；凭据优先写入系统凭据库 |
| 跨平台界面 | PySide6 桌面界面，支持 900×640 响应式布局，支持手动日间、夜间及实时跟随系统 |
| 主题与背景 | 「星河」粉紫 /「晴海」青蓝预览卡；十二张小流背景或自定义图片，四区独立选择，支持大预览、筛选、拖放与深浅可见度调节 |
| 小流陪伴 | 十二套像素动画随本地早晚五个时段变化，前台待机每隔 15～30 秒轮换动作与时段文案；[查看动作预览](docs/MASCOT_DESIGN.md) |
| 检查与安装更新 | 启动自动检查或手动检查，正式版/含 beta 通道；官方 macOS/Windows 包支持校验、安装、重启和启动失败恢复 |

自动更新从 `v0.8.1b1` 起提供，目前属于 beta 功能。请先手动安装包含该功能的版本；正式版与预发布版状态以 [Releases](https://github.com/itsVicOC/bilibili-downloader/releases) 为准。

`v0.8.3` 为软件更新接入[官方镜像](https://1008.si/download/)，优先加速查询和下载，网络失败时自动尝试 GitHub。v0.8.2 及更早版本可从官网加速下载本版后手动安装；后续更新走镜像。

`v0.8.8` 正式版修复 Windows 11 点击下载页空白后偶发出现旧原生标题栏，以及最大化 / 还原失效的问题；新增真实 Windows 鼠标输入、窗口激活与状态检查。`v0.8.7` 用户可在「设置 → 关于与更新」检查升级。此前的小流时段动画、背景玻璃及设置优化继续保留。[查看更新日志](CHANGELOG.md#v088---2026-10-21) · [小流动画预览](docs/MASCOT_DESIGN.md)。

下载、直播与设置采用统一底部操作卡；页签和任务工具栏保留清晰底色，支持键盘焦点提示。主题卡分别标识选中与焦点，任务记录移除使用轻量操作。

`v0.8.9b3`（0.8.9 beta 3）基于 `codex/fluent-design-polish` 分支完成新一轮 [Fluent Design 精修](docs/FLUENT_DESIGN.md)：横向作品摘要、响应式规格和附加内容、矮窗口紧凑布局、统一设置与任务操作，并自动记住主窗口大小、位置和最大化状态。保留粉紫／青蓝、小流、粉底白字、Markdown 更新说明及 Windows 自绘窗口按钮。试用请查看 [beta 3 预发布版](https://github.com/itsVicOC/bilibili-downloader/releases/tag/v0.8.9b3)；自动更新需选择包含预发布版的通道。稳定版仍为 `v0.8.8`。[更新日志](CHANGELOG.md#v089b3---2026-10-23) · [第三轮验收](docs/FLUENT_V3_VALIDATION.md) · [第四轮验收与窗口记忆](docs/FLUENT_V4_VALIDATION.md)。

开发分支在 beta 3 之后新增目录按钮邻近布局、任务整行悬停、录制历史整场移除与撤销，以及默认开启、需确认的前台剪贴板识别。尚未发布新版安装包，详见[第五轮交互验收](docs/FLUENT_V5_VALIDATION.md)。

## 下载与安装

访问 **[BiliFlow 官网 · 1008.si](https://1008.si/)** 了解项目，或直接从 **[GitHub Releases 下载最新正式版](https://github.com/itsVicOC/bilibili-downloader/releases/latest)**。想体验 beta 功能，可查看[全部版本](https://github.com/itsVicOC/bilibili-downloader/releases)；预发布版会带有 `Pre-release` 标记。

**首次使用推荐 `full` 包**：内置从固定源码构建的最小 LGPL FFmpeg 和配套直播录制引擎，无需安装 Python。`lite` 包体积更小，需要自行安装 FFmpeg；使用直播功能时还需配置配套录制引擎。

从 `v0.8.0` 起，正式版支持直播录制。引擎路径在「设置 → 工具与存储」中配置，使用方法见[直播录制指南](docs/LIVE_RECORDING.md)。

| 系统 | 下载文件 | 说明 |
|---|---|---|
| macOS 12+（Apple Silicon） | `BilibiliDownloader-macOS-full-<version>.dmg` | 从 v0.8.1 提供；拖入 Applications 后打开 |
| Windows 10/11（x64） | `BilibiliDownloader-Windows-full-<version>-setup.exe` | 从 v0.8.1 提供；当前用户安装，无需管理员权限 |
| macOS 12+（Apple Silicon） | `BilibiliDownloader-macOS-full-<version>.zip` | 保留；解压后将应用移入应用程序文件夹 |
| macOS 12+（Apple Silicon） | `BilibiliDownloader-macOS-lite-<version>.zip` | 需要自行安装 FFmpeg |
| Windows 10/11（x64） | `BilibiliDownloader-Windows-full-<version>.zip` | 保留便携包；完整解压后运行 |
| Windows 10/11（x64） | `BilibiliDownloader-Windows-lite-<version>.zip` | 需要自行安装 FFmpeg |
| Linux | 暂无预构建包 | 按“从源码运行”操作 |

EXE/DMG 从 `v0.8.1` 正式版开始提供。Windows 默认安装到 `%LOCALAPPDATA%\Programs\BiliFlow`，在系统应用列表中卸载；卸载保留配置、任务记录和用户媒体。macOS 请先将应用拖入 Applications，再启动。应用内自动更新继续使用对应的 full/lite ZIP。

lite 包、源码运行和 Linux 环境可使用以下方式安装 FFmpeg：

- macOS：`brew install ffmpeg`
- Windows：`winget install Gyan.FFmpeg`
- Ubuntu / Debian：`sudo apt install ffmpeg`

如果 FFmpeg 不在系统 PATH 中，可以在「设置 → 工具与存储」中直接选择并检查可执行文件。自定义路径优先于 full 包内置版本，因此 full 包也可以切换到其他 FFmpeg 构建。

<details>
<summary>校验安装包完整性</summary>

每个 Release 都提供 `SHA256SUMS.txt`。将命令输出与其中的对应记录比较：

```bash
# macOS / Linux
shasum -a 256 BilibiliDownloader-macOS-full-vX.Y.Z.zip
```

```powershell
# Windows PowerShell
Get-FileHash .\BilibiliDownloader-Windows-full-vX.Y.Z.zip -Algorithm SHA256
```

Release 还包含 FFmpeg 固定源码归档、各安装包的 CycloneDX SBOM 和统一校验文件。full 包内的 `FFMPEG-NOTICE.txt` 记录实际二进制摘要、构建参数与许可证。

</details>

> macOS 发布包默认未进行 Apple 公证；如果某个 Release 已签名并公证，会在该版本发布说明中明确标注。未公证版本首次打开被拦截时，请在“系统设置 → 隐私与安全性”中确认打开，并确保安装包来自本仓库 Release 页面。

## 五分钟上手

1. 启动 BiliFlow；使用 lite 包或源码运行时，先确认 FFmpeg 可用。
2. 在首页粘贴 BV/AV/ep 号、视频或番剧单集 URL、b23.tv 短链，然后点击“开始解析”。
3. 选择分 P、画质、编码、视频/音频输出和需要的归档附加项。
4. 点击“加入下载队列”，在任务中心查看进度或执行暂停、继续与打开文件。
5. 对于合集、收藏夹或番剧 `ss/md` 页面，打开“批量导入”，先解析预览，再筛选要加入的作品。
6. 第一次真正创建下载任务时阅读版权提示；确认后才会建立任务和媒体临时文件。

部分高画质、会员内容或账号专属视频需要登录。BiliFlow 只使用当前账号已经拥有的播放权限；接口只返回试看、地区受限、DRM 或无完整未加密流时会停止。

更完整的界面说明、任务状态、目录模板和配置位置见[用户指南](docs/USER_GUIDE.md)。遇到启动、解析、FFmpeg 或登录问题时查看[故障排查](docs/TROUBLESHOOTING.md)。

**想录制直播？** 在「直播录制」页添加房间号或直播间 URL 并开启监控；在任务中心查看当前录制、历史片段并导出 MP4。自动监控需要保持应用运行，退出、睡眠或断网期间的内容无法补录。详细步骤见[直播录制指南](docs/LIVE_RECORDING.md)。

**关闭窗口后继续运行：** macOS 点击红色关闭按钮或按 `⌘W` 仅关闭窗口，点击 Dock 图标可恢复；`⌘Q` 或应用菜单可彻底退出。Windows 点击关闭按钮时可选择最小化到系统托盘或彻底退出，并可记住选择；在「设置 → 外观 → 窗口」修改。托盘图标可恢复窗口，右键菜单可退出。关闭窗口或进入托盘后下载、直播监控、录制和导出继续运行；真正退出时会确认正在运行的任务并完成收尾。

## 界面预览

小流会按本地时间切换清晨、上午、午后、傍晚和深夜状态；前台待机每隔 15～30 秒轮换动作，隐藏、最小化或转入后台时暂停。

![小流十二套动画预览](docs/images/mascot/actions/xiaoliu-actions.gif)

视频下载与直播录制使用统一工作台；加入下载队列后保留当前页，任务中心集中展示下载队列、当前录制和录制历史。侧栏主导航下方的设置统一管理下载、直播、外观、工具与存储、关于与更新。侧栏底部保留深浅模式和账号入口；已登录时打开账号概览，可切换或退出账号。

![BiliFlow 任务中心](docs/images/biliflow-tasks.png)

<table>
  <tr>
    <td width="50%"><img src="docs/images/biliflow-batch.png" alt="BiliFlow 批量导入预览"></td>
    <td width="50%"><img src="docs/images/biliflow-settings.png" alt="BiliFlow 下载设置"></td>
  </tr>
  <tr>
    <td align="center">批量导入：来源摘要、作品清单与输出确认</td>
    <td align="center">下载设置：目录模板、规格与附加内容</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/biliflow-light.png" alt="BiliFlow 日间主界面"></td>
    <td width="50%"><img src="docs/images/biliflow-login.png" alt="BiliFlow 登录界面"></td>
  </tr>
  <tr>
    <td align="center">跟随系统的日间主题</td>
    <td align="center">登录说明与敏感信息保护</td>
  </tr>
</table>

截图中的作品、任务和账号状态均为离线演示数据，不包含真实 Cookie、下载地址或媒体内容。

![BiliFlow 直播工作台](docs/images/biliflow-live.png)

完整深浅主题、900×640／1120×760／1320×860 布局及关键状态见[视觉规范与验证](docs/UI_DESIGN.md)。

## 支持范围

| 来源 | 单个解析 | 批量导入 | 备注 |
|---|:---:|:---:|---|
| BV、AV、普通视频 URL | ✓ | ✓ | 支持多 P |
| 番剧 `ep` 单集 | ✓ | ✓ | 必须拥有完整播放权限 |
| 番剧 `ss/md` 季度或媒体页 | — | ✓ | 默认选择正片，PV/花絮/特别篇可手动加入 |
| UP 主合集与系列 | — | ✓ | 支持分页读取和筛选 |
| 收藏夹 | — | ✓ | 私密或账号专属内容需要登录 |
| b23.tv 短链 | ✓ | ✓ | 需要联网展开短链 |

点播解析不接受直播链接，请使用独立的直播录制工作台。国际站、课程、稍后再看、动态、DRM、地区代理解析，以及任何付费、会员或账号权限绕过均不受支持。实际可用画质、编码、音轨和字幕由作品本身、当前账号权限及 Bilibili 接口响应共同决定。

## 从源码运行

需要 Python 3.11–3.12 与 FFmpeg；最低版本调整为 3.11，以使用 Pillow 13 的安全修复。预构建应用内置 Python，无需用户单独升级：

```bash
git clone https://github.com/itsVicOC/bilibili-downloader.git
cd bilibili-downloader
python -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints.txt -e ".[dev]"
python -m bilibili_downloader
```

Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1` 激活环境。

<details>
<summary>从源码启用直播录制</summary>

源码运行还需要构建配套 Rust / Mesio 录制引擎。安装 Rust 工具链后运行：

```bash
cargo build --release --locked --manifest-path native/recorder/Cargo.toml
```

应用会自动检测 `native/recorder/target/release/biliflow-recorder`（Windows 为 `.exe`）。已验证的工具链版本、依赖与完整流程见[直播录制开发说明](docs/LIVE_RECORDING.md#开发与验证)。

</details>

### CLI 示例

```bash
# 只解析元数据
python -m bilibili_downloader test BV1GJ411x7h7

# 下载 1080P 视频，并保存弹幕与字幕
python -m bilibili_downloader download BV1GJ411x7h7 \
  --quality 80 --danmaku --subtitle

# 仅保存音频
python -m bilibili_downloader download BV1GJ411x7h7 --audio-only

# 下载当前账号可完整播放的番剧单集
python -m bilibili_downloader download ep123 --quality 80

# 整季默认只下载正片；需要附加章节时显式开启
python -m bilibili_downloader download \
  "https://www.bilibili.com/bangumi/play/ss123" \
  --include-extras

# 下载整个可访问合集，同时保存归档信息
python -m bilibili_downloader download \
  "https://space.bilibili.com/123/lists/456?type=season" \
  --quality 80 \
  --output ./downloads \
  --danmaku \
  --subtitle \
  --cover \
  --metadata \
  --path-template "{author}/{title}{part_suffix}" \
  --page all \
  --codec 12
```

运行 `python -m bilibili_downloader --help` 或阅读[用户指南的 CLI 章节](docs/USER_GUIDE.md#cli)查看全部参数。

`ep123`、`ss123` 和合集 URL 中的数字是格式示例，请替换为实际来源。CLI 首次交互下载会要求确认版权提示；非交互环境需显式传入 `--acknowledge-copyright`。

## 常见问题

<details>
<summary>full 和 lite 怎么选？需要安装 Python 吗？</summary>

预构建包无需安装 Python。首次使用推荐 full，已包含 FFmpeg 与直播录制引擎；lite 适合希望自行管理这些工具的用户。只有从源码运行才需要 Python 环境。

</details>

<details>
<summary>不登录能用吗？为什么没有 4K、HDR 或 8K？</summary>

无需登录即可解析和下载可完整播放的公开视频。高画质、会员或账号专属内容取决于作品本身和当前账号权限；BiliFlow 只显示接口实际返回的规格，不会解锁账号未获授权的内容。详见[画质排查](docs/TROUBLESHOOTING.md#看不到高画质或指定编码)。

</details>

<details>
<summary>下载中断后要重新开始吗？</summary>

任务和断点会保存在本地。重新启动应用后，在任务中心继续已暂停的任务即可；请保留任务数据库和输出目录中的 `.biliflow-parts/`，清理缓存会删除未完成的断点。

</details>

<details>
<summary>支持 Intel Mac、Linux 或手机吗？</summary>

当前预构建包面向 Apple Silicon Mac 和 Windows x64。Linux 和 Intel Mac 可尝试从源码运行；Intel Mac 暂无预构建包，兼容性请自行验证。本项目目前不提供 Android 或 iOS 客户端。

</details>

<details>
<summary>软件打不开或 FFmpeg 找不到怎么办？</summary>

先确认完整解压了正确的安装包。full 包可核对 Release 校验文件；lite 或源码运行可在「设置 → 工具与存储」选择 FFmpeg 可执行文件。macOS 首次打开和 Windows 安全提示的处理方式见[故障排查](docs/TROUBLESHOOTING.md)。

</details>

## 文档

| 文档 | 适合谁 | 内容 |
|---|---|---|
| [文档中心](docs/README.md) | 所有人 | 按安装、使用、排障、开发和发布组织全部文档 |
| [用户指南](docs/USER_GUIDE.md) | 使用者 | GUI、CLI、登录、任务、配置与数据存储 |
| [直播录制](docs/LIVE_RECORDING.md) | 使用者、开发者 | 房间监控、录制历史、引擎配置与验收范围 |
| [视觉规范与验证](docs/UI_DESIGN.md) | 使用者、开发者 | 深浅主题、响应式布局、关键状态与截图索引 |
| [故障排查](docs/TROUBLESHOOTING.md) | 使用者 | 启动、解析、画质、FFmpeg、登录与任务恢复 |
| [版权与合规说明](docs/COPYRIGHT.md) | 所有人 | 授权边界、禁止用途与权利人反馈 |
| [构建与发布](docs/BUILDING.md) | 开发者 | 开发环境、测试、截图、打包和 Release 流程 |
| [贡献指南](CONTRIBUTING.md) | 贡献者 | Issue、分支、代码质量与提交要求 |
| [安全策略](SECURITY.md) | 研究者 | 漏洞报告渠道与凭据处理边界 |
| [第三方素材](THIRD_PARTY_NOTICES.md) | 发行维护者 | 图片、图标、FFmpeg 来源和许可证 |
| [更新日志](CHANGELOG.md) | 所有人 | 各版本新增、修改和修复内容 |

## 开发验证

```bash
python -m compileall -q bilibili_downloader tests scripts
pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
git diff --check
```

涉及打包、资源路径或依赖变化时，再运行：

```bash
pyinstaller --noconfirm --clean BilibiliDownloader.spec
```

项目结构、文档截图生成方式与完整发布流程见[构建与发布](docs/BUILDING.md)。

## 参与和支持

如果 BiliFlow 对你有帮助，欢迎在 [GitHub](https://github.com/itsVicOC/bilibili-downloader) 点亮 Star，或分享[官网](https://1008.si/)和本仓库，让更多需要桌面下载与归档工具的人找到它。

- **报告问题或建议功能**：先查看[故障排查](docs/TROUBLESHOOTING.md)和[已有 Issues](https://github.com/itsVicOC/bilibili-downloader/issues)，再[提交 Issue](https://github.com/itsVicOC/bilibili-downloader/issues/new)。请附版本、系统和复现步骤，移除 Cookie、签名播放 URL 与个人信息。
- **改进代码、文档或翻译**：阅读[贡献指南](CONTRIBUTING.md)，欢迎通过 Pull Request 参与；中英文 README 的功能、安装说明和链接应同步维护。
- **报告安全漏洞**：使用[安全策略](SECURITY.md)中的私密报告渠道。

感谢 [PySide6 / Qt](https://doc.qt.io/qtforpython-6/)、[FFmpeg](https://ffmpeg.org/)、[Mesio / rust-srec](https://github.com/hua0512/rust-srec) 及其他开源依赖的贡献者。图标、素材与第三方许可证见[第三方声明](THIRD_PARTY_NOTICES.md)。

## 隐私与免责声明

- 应用不会把登录凭据发送到项目维护者、自建服务器或媒体 CDN；Cookie 只发送给受信任的 Bilibili API/网页域名。
- 登录输入只保留白名单字段，并优先存储在系统凭据库。凭据库不可用时仅在当前进程内存中保留，重启后需要重新登录。
- 日志、任务数据库、元数据和文档截图不应包含有效 Cookie 或带签名的播放 URL。
- 本项目与哔哩哔哩（Bilibili）无隶属、授权、合作或背书关系。
- 请优先使用官方客户端提供的缓存能力，并遵守当地法律、平台服务条款和权利人许可。

## License

项目代码使用 [MIT License](LICENSE)。界面素材和发行包内 FFmpeg 继续适用各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
