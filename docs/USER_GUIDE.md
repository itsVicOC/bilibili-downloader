# 用户指南

## 支持范围

BiliFlow 支持单个/多 P 视频、UP 主合集与系列、收藏夹、BV/AV 号、`bilibili.com/video/...` 链接和 b23.tv 短链。合集与收藏夹使用“批量导入”入口，解析后可以筛选作品并自动跳过相同规格的已有任务。

空间合集链接、带 `sid` 的视频合集链接以及公开或当前账号可访问的收藏夹受支持。番剧播放页、课程、稍后再看、直播和动态页面目前不在支持范围内。

可用画质取决于视频本身、账号权限和 Bilibili 返回的流。未登录时通常无法获得会员画质；选择的编码不可用时，应用会回退到实际可用的流。

画质、视频编码或音频规格发生回退时，任务仍会完成，并在任务行和元数据中记录实际规格。字幕、弹幕、封面或元数据等附加项失败不会删除已经成功封装的媒体文件，任务会显示为“部分完成”，可在任务提示中查看具体警告。

## GUI 工作流

### 解析与下载

1. 在首页输入框粘贴 BV/AV 号、完整视频链接或 b23.tv 短链。
2. 点击“开始解析”，等待作品资料卡和可用规格更新。
3. 多 P 视频可选择某一分 P 或全部分 P，再选择画质与编码。需要时勾选“下载弹幕”或“下载字幕”。
4. 点击“加入下载队列”。任务中心会显示下载速度、预计剩余时间、合并、完成和失败状态。
5. 运行中任务可以暂停并保留断点；暂停和失败任务可以继续。完成后可打开文件目录或只清除任务记录。

批量导入接受每行一个视频、合集、系列、收藏夹链接或编号。点击“解析并预览”后可以全选、取消全选或逐项筛选。已有同源作品会被标注，最终按视频分 P、媒体规格、输出相对路径和归档附加项进行精确去重。

“全部暂停”会停止网络传输和 FFmpeg，同时保留断点文件；“全部继续”会重新获取有效流地址后续传。“清除完成”只删除历史记录，不删除媒体文件。“清理缓存”会删除所有未完成断点，必须先暂停全部任务。

### 登录

登录不是普通公开视频下载的必要条件。需要会员画质或账号专属内容时，可打开“登录 B 站账号”：

- 推荐手动填写浏览器中的 `SESSDATA` 值，并在应用内验证。
- 扫码登录依赖 Bilibili 当前接口，接口变化时可能暂时不可用。
- 登录凭据优先保存到系统凭据库，不会上传到项目维护者服务器。

不要把 SESSDATA 发送给他人，也不要粘贴到 Issue、日志或截图中。退出登录可在登录窗口清除凭据。

### 下载设置

- **输出目录**：默认是 `~/Downloads/bilibili`。
- **默认画质**：新解析任务的初始画质。
- **默认输出**：视频 MP4 或仅音频；普通音轨封装为 M4A，Hi-Res FLAC 保持 `.flac`。
- **默认音频**：AAC 64/192kbps、Dolby Atmos 或 Hi-Res FLAC；是否可用取决于视频和账号权限。
- **目录模板**：控制输出目录和文件名，支持 `title`、`author`、`bvid`、`page`、`part`、`part_suffix`、`collection`、`quality`、`codec` 字段。
- **最大并发**：范围 1–8。网络或磁盘较慢时建议 1–3。
- **FFmpeg 路径**：留空时从系统 PATH 自动查找，也可以选择自定义可执行文件。
- **归档附加项**：控制弹幕、首选/全部字幕、封面和 JSON 元数据的默认状态。

例如 `{author}/{collection}/{title}{part_suffix}` 会按 UP 主和合集建立目录。标题等远端字段会逐段清理，不能通过模板写到输出目录之外。没有合集名称时，对应字段会使用 `untitled`，不需要合集目录时可从模板中移除 `{collection}`。

主题不使用单独开关，会跟随 Windows、macOS 或 Linux 桌面环境的日间/夜间设置实时切换。

## CLI

查看命令：

```bash
python -m bilibili_downloader --help
python -m bilibili_downloader download --help
```

只解析视频信息：

```bash
python -m bilibili_downloader test BV1GJ411x7h7
python -m bilibili_downloader test av170001
python -m bilibili_downloader test "https://b23.tv/example"
```

下载：

```bash
python -m bilibili_downloader download BV1GJ411x7h7 \
  --quality 80 \
  --output ./downloads \
  --danmaku \
  --subtitle
```

| 参数 | 说明 |
|---|---|
| `source` | BV/AV 号、视频/合集/系列/收藏夹 URL 或 b23.tv 短链 |
| `-q, --quality` | Bilibili 画质代码，默认 `80` |
| `-o, --output` | 输出目录；省略时读取应用设置 |
| `-d, --danmaku` | 下载弹幕并转换为 ASS |
| `-s, --subtitle` | 下载字幕并转换为 SRT |
| `-c, --codec` | 视频编码：`7` AVC、`12` HEVC、`13` AV1 |
| `-p, --page` | 分 P 序号或 `all`；默认 `1` |
| `--subtitle-language` | 首选字幕语言代码；默认 `zh-Hans` |
| `--all-subtitles` | 下载该分 P 的全部可用字幕语言 |
| `--audio-only` | 只保存音轨并无损封装为 M4A；Hi-Res 音轨保存为 FLAC |
| `--audio-quality` | 音频代码，例如 `30280` AAC 192kbps、`30251` Hi-Res FLAC |
| `--cover` | 保存经过格式和大小校验的封面 |
| `--metadata` | 保存包含来源、作品和实际规格的 `.info.json` |
| `--path-template` | 覆盖本次下载的相对目录模板 |

画质代码：

| 代码 | 画质 | 代码 | 画质 |
|---:|---|---:|---|
| 6 | 240P | 16 | 360P |
| 32 | 480P | 64 | 720P |
| 80 | 1080P | 112 | 1080P+ |
| 116 | 1080P60 | 120 | 4K |
| 125 | HDR | 126 | Dolby Vision |
| 127 | 8K | | |

## 文件与配置

| 数据 | 默认位置 |
|---|---|
| macOS 配置 | `~/Library/Application Support/BiliFlow/config.json` |
| Windows 配置 | `%APPDATA%\\BiliFlow\\config.json` |
| Linux 配置 | `$XDG_CONFIG_HOME/biliflow/config.json`，未设置时使用 `~/.config/biliflow/config.json` |
| 损坏配置备份 | 与配置同目录的 `config.json.bak` |
| 持久任务数据库 | 与配置同目录的 `tasks.sqlite3` |
| 视频输出 | `~/Downloads/bilibili` |
| 登录凭据 | 系统凭据库；不可用时回退到配置文件 |

旧版 `~/.bilibili-downloader/config.json` 会在首次启动时复制到当前平台的原生配置目录，原文件会保留。

任务状态保存在 `tasks.sqlite3`。运行中退出或异常终止后，任务会在下次启动时显示为“已暂停”，无需重新粘贴链接即可继续。

应用在输出目录的 `.biliflow-parts/` 中保存媒体断点并支持 HTTP Range 续传。成功封装后会清理对应中间文件；暂停、网络中断或异常退出后，继续相同任务会复用已有数据。该目录可能占用较大空间，可在任务中心暂停全部任务后使用“清理缓存”。

同一媒体流可能包含多个 CDN 候选地址。BiliFlow 只连接受信任域名上的标准 HTTPS 目标；主地址不符合安全边界或暂时不可用时会自动尝试备用 CDN，不需要手动更换链接。

文件名会移除当前操作系统不允许的字符。多 P 视频会在标题后追加分 P 序号和名称，避免互相覆盖。

## 升级与校验

- 从旧版本升级时可以直接替换应用；配置和登录凭据保存在应用包之外，不会随替换被删除。
- 首次启动新版本前，建议保留配置文件和未完成下载目录的备份。不要跨设备公开复制包含凭据的配置。
- 任务数据库需要迁移时会先创建 `tasks.sqlite3.bak`。完整性检查确认损坏的数据库会被隔离并在状态栏提示文件名；来自更新版本的数据库不会被旧版应用降级修改。
- Release 提供 `SHA256SUMS.txt`。macOS/Linux 可运行 `shasum -a 256 <安装包>`，Windows PowerShell 可运行 `Get-FileHash <安装包> -Algorithm SHA256`，并与校验文件中的对应记录比较。
- 跨大版本升级后若界面或设置异常，先退出应用并按“文件与配置”中的路径备份、移走 `config.json`，再重新启动生成默认配置。

## 限制与合规

- Bilibili 接口和鉴权规则可能变化，扫码登录、合集分页及部分画质可能因此失效。
- DRM、付费课程和平台未提供可下载流的内容无法下载。
- 本工具不会绕过账号权限。请仅下载你拥有权限的内容，并遵守法律、服务条款与版权要求。
