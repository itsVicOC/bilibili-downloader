# Bilibili Downloader

一款桌面端 B 站视频下载工具，支持 GUI 和 CLI 双模式。

## 功能特性

- **双模式运行**：PySide6 桌面 GUI + 命令行 CLI
- **画质选择**：从 240P 到 8K，支持 HEVC/H.265、AVC/H.264、AV1 编码切换
- **附加下载**：弹幕（ASS 格式）和字幕（SRT 格式）
- **批量下载**：支持多链接顺序队列下载
- **登录支持**：Cookie / SESSDATA 登录，获取更高画质权限
- **FFmpeg 自动合并**：音视频分离下载后自动合并为 MP4
- **深色主题**：哔哩蓝主色调的完整 QSS 样式表

## 安装

### 环境要求

- Python >= 3.10
- FFmpeg（用于音视频合并）

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/itsVicOC/bilibili-downloader.git
cd bilibili-downloader

# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"
```

### FFmpeg 安装

- **Windows**: `winget install Gyan.FFmpeg` 或从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

## 使用

### GUI 模式（默认）

```bash
python -m bilibili_downloader
# 或安装后
bilibili-downloader
```

### CLI 模式

```bash
# 测试：获取视频信息
python -m bilibili_downloader test BV1GJ411x7h7

# 下载视频
python -m bilibili_downloader download BV1GJ411x7h7 \
    --quality 80 \
    --output ./downloads \
    --danmaku \
    --subtitle

# 查看帮助
python -m bilibili_downloader --help
python -m bilibili_downloader download --help
```

### CLI 参数

| 参数 | 说明 |
|---|---|
| `bvid` | BV 号（如 `BV1GJ411x7h7`，也可省略 `BV` 前缀） |
| `-q, --quality` | 画质代码（默认 80=1080P） |
| `-o, --output` | 输出目录 |
| `-d, --danmaku` | 同时下载弹幕 |
| `-s, --subtitle` | 同时下载字幕 |

## 项目结构

```
bilibili_downloader/
├── api/          # Bilibili API 客户端、WBI 签名、登录
├── core/         # 下载器、FFmpeg 合并、弹幕/字幕处理、数据模型
├── gui/          # PySide6 界面：主窗口、对话框、控件、工作线程
└── utils/        # 配置管理、URL/BV 验证

tests/            # 测试套件
```

## 开发

### 运行测试

```bash
pytest
```

### 打包

```bash
pip install -e ".[dev]"
pyinstaller --onefile --windowed bilibili_downloader/__main__.py
```

## License

MIT
