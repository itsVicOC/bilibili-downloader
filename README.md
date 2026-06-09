# Bilibili Downloader

一款桌面端 B 站视频下载工具，支持 GUI 和 CLI 双模式。它可以解析 BV 号、AV 号、B 站视频链接和 b23.tv 短链，支持画质选择、弹幕、字幕、登录态保存和音视频自动合并。

## 下载

推荐普通用户直接从 [GitHub Releases](https://github.com/itsVicOC/bilibili-downloader/releases) 下载预构建包：

- macOS：下载 `BilibiliDownloader-macOS-<version>.zip`
- Windows：下载 `BilibiliDownloader-Windows-<version>.zip`

应用依赖 FFmpeg 进行音视频合并。如果系统中没有 FFmpeg，请先安装：

- Windows：`winget install Gyan.FFmpeg`，或从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载
- macOS：`brew install ffmpeg`
- Linux：`sudo apt install ffmpeg`

## 功能特性

- **双模式运行**：提供 PySide6 桌面 GUI，也支持命令行下载。
- **多格式输入**：支持 BV 号、AV 号、完整 B 站视频链接和 b23.tv 短链。
- **画质选择**：支持 240P 到 8K，以及 HEVC/H.265、AVC/H.264、AV1 编码切换。
- **附加内容**：可同时下载弹幕并转换为 ASS，也可下载字幕并转换为 SRT。
- **批量下载**：粘贴多行链接后统一解析并加入下载队列。
- **登录支持**：支持 Cookie / SESSDATA 登录，优先使用系统凭据库存储登录态。
- **可靠下载**：支持备用下载 URL 重试、临时文件续传和取消任务时终止 FFmpeg。
- **现代 GUI**：重新设计主窗口、视频信息面板、下载列表和设置/登录/批量对话框。

## 从源码运行

### 环境要求

- Python >= 3.10
- FFmpeg

### 安装依赖

```bash
git clone https://github.com/itsVicOC/bilibili-downloader.git
cd bilibili-downloader

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

Windows PowerShell 激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

### GUI 模式

```bash
python -m bilibili_downloader
```

安装为可执行命令后也可以使用：

```bash
bilibili-downloader
```

### CLI 模式

```bash
# 获取视频信息
python -m bilibili_downloader test BV1GJ411x7h7
python -m bilibili_downloader test av170001
python -m bilibili_downloader test "https://www.bilibili.com/video/BV1GJ411x7h7"

# 下载视频
python -m bilibili_downloader download BV1GJ411x7h7 \
    --quality 80 \
    --output ./downloads \
    --danmaku \
    --subtitle
```

CLI 参数：

| 参数 | 说明 |
|---|---|
| `source` | BV 号、AV 号、B 站视频链接或 b23.tv 短链 |
| `-q, --quality` | 画质代码，默认 `80`，表示 1080P |
| `-o, --output` | 输出目录，未指定时使用设置中的下载目录 |
| `-d, --danmaku` | 同时下载弹幕并保存为 ASS |
| `-s, --subtitle` | 同时下载字幕并保存为 SRT |

## 项目结构

```text
bilibili_downloader/
├── api/          # Bilibili API 客户端、WBI 签名、登录
├── core/         # 下载器、FFmpeg 合并、批量解析、弹幕/字幕处理、数据模型
├── gui/          # PySide6 界面：主窗口、对话框、控件、工作线程
└── utils/        # 配置管理、输入解析、URL/BV/AV 验证

tests/            # 测试套件
```

## 开发

运行测试：

```bash
pytest
```

构建本机应用：

```bash
pip install -e ".[dev]"
pyinstaller --noconfirm --clean BilibiliDownloader.spec
```

构建结果位于 `dist/BilibiliDownloader`。在 macOS 上，spec 也会额外生成 `dist/BilibiliDownloader.app`。

## 发布

项目使用 GitHub Actions 自动发布。推送 `v*` tag 后，流水线会在 macOS 和 Windows runner 上分别构建压缩包，并上传到同一个 GitHub Release。

```bash
git tag v0.2.0
git push origin main
git push origin v0.2.0
```

发布产物命名：

- `BilibiliDownloader-macOS-v0.2.0.zip`
- `BilibiliDownloader-Windows-v0.2.0.zip`

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT
