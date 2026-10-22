# 构建与发布

## 开发环境

- Python 3.11–3.12
- FFmpeg（真实下载与合并验证需要）
- macOS、Windows 或 Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e ".[dev]"
```

Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1`。

## 项目结构

```text
bilibili_downloader/
├── api/          # API 客户端、WBI 签名与登录
├── core/         # 解析、下载、FFmpeg、弹幕、字幕与数据模型
├── gui/          # PySide6 窗口、对话框、控件、线程与视觉资源
└── utils/        # 配置和输入验证
scripts/          # 可复现的资源构建脚本
native/recorder/  # Rust / Mesio 直播适配程序与 Cargo.lock
tests/            # 单元与回归测试
```

## 验证

```bash
python -m compileall -q bilibili_downloader tests scripts
pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
git diff --check
```

CI 在 Ubuntu 和 Windows 上使用 Python 3.11、3.12 运行测试，并在 macOS/Python 3.12 做冒烟验证。GUI 测试使用 `QT_QPA_PLATFORM=offscreen`；Ubuntu runner 会先安装 PySide6 需要的 `libegl1` 与 `libgl1`，独立任务使用 `pip-audit` 检查已安装依赖。

Windows 与 macOS 的 Python 3.12 任务另使用原生后端检查标题栏和字体，并生成两套配色、深浅模式、三种尺寸的页面、账号与背景截图。`ui-parity-Windows` / `ui-parity-macOS` 附件保留七天。标题栏专项可在对应桌面运行 `python -m scripts.capture_docs_screenshots --native --physical-pixels --chrome-only --output-dir build/ui-parity/chrome`；它捕获目标窗口的合成画面，能够发现控件截图遗漏的 Windows 标题绘制层。原生截图需要可用桌面和截屏权限，不能用离屏结果代替。

源码最低版本为 Python 3.11，以使用包含安全修复的 Pillow 13；同时要求 certifi 2026.10.19 或更高版本。安装依赖时使用约束文件。预构建应用内置 Python，用户无需单独安装或升级 Python。

`constraints.txt` 固定经过验证的直接运行与开发依赖。修改依赖时，应在三类系统的 CI 通过后同步更新约束版本；平台专属传递依赖由 pip 解析器管理。

### 弹幕实际渲染验证

单元测试覆盖导出字段、Unicode 字素、时间量化、轨道分配和失败保护。还可使用本机已有的 libass 直接验证实际像素：

```bash
python scripts/verify_timed_text_rendering.py \
  --libass /path/to/libass.so \
  --output-dir /tmp/biliflow-ass-check
```

macOS 使用对应的 dylib，Windows 使用 DLL；如该库还依赖同目录动态库，需要先配置操作系统的动态库搜索路径。脚本不下载渲染器、不修改应用设置，检查字面字符、颜色、正反向运动、长文本完整进出、大字号以及顶底位置，并输出 ASS/PNG 演示文件。该检查不能替代 Windows PotPlayer 的实机验收。

## 文档与截图

README 和用户指南中的软件截图由离线脚本生成，不依赖 Bilibili 接口，也不会读取本机配置、系统凭据库或下载任务。GUI 样式、布局、可见文案发生变化后，在仓库根目录运行：

```bash
python scripts/capture_docs_screenshots.py
```

Fluent 精修的完整矩阵支持 `--color-theme star_trail`（默认）和 `--color-theme bilibili_blue`，使用不同的 `--output-dir` 保存结果。原生后端追加 `--native --physical-pixels`；CI 在 Windows／macOS 上分别保存两套配色的全部页面和弹窗截图。截图进程关闭界面过渡动画，业务逻辑和用户配置不受影响。参数及复核说明见 [Fluent Design 精修规范](FLUENT_DESIGN.md)。

脚本会更新 `docs/images/` 中九个工作区页签的深浅主题 × 三种尺寸截图，以及登录、房间设置、空状态、解析失败、直播重连与收尾、导出状态等截图。完整索引见[视觉规范与验证](UI_DESIGN.md)。小流动作与五个时段的专项截图可使用 `python scripts/capture_docs_screenshots.py --mascot-only --output-dir docs/images/mascot/offscreen`；macOS 原生后端追加 `--native` 并将输出目录改为 `docs/images/mascot/native`。任务、作品、路径与账号状态均为演示数据；不得改为真实 Cookie、账号标识、带签名播放 URL、个人目录或受版权保护的媒体内容。

提交截图前应人工检查：

- 日间和夜间主界面没有裁切、重叠或意外滚动条。
- 任务中心的状态、进度条和操作按钮完整可见。
- 对话框截图背景不透明，正文和输入框在 GitHub 日间/夜间页面中均可辨认。
- README 与用户指南引用的文件名、说明文字和实际界面一致。
- PNG 尺寸没有非预期变化；主界面基准为 1320×860。

### 发布候选端到端验证

涉及下载、网络边界、FFmpeg 或归档附加项时，发布前还应使用一个无需登录且有权下载的短视频完成真实验证。不要在脚本、命令历史或日志中写入真实 Cookie，也不要把线上网络测试加入常规单元测试。

```bash
python -m bilibili_downloader test <公开BV号>
python -m bilibili_downloader download <公开BV号> \
  --quality 16 \
  --audio-quality 30216 \
  --danmaku \
  --subtitle \
  --cover \
  --metadata \
  --output <临时输出目录>
python -m bilibili_downloader download <公开BV号> \
  --audio-only \
  --audio-quality 30216 \
  --output <另一个临时输出目录>
```

验收时确认视频 MP4 与仅音频 M4A 均可被 FFmpeg 完整解码；封面能够被图片解析器打开；元数据是有效 JSON；弹幕/字幕结果与源视频能力一致；成功后对应 `.biliflow-parts/` 缓存已清理。至少中断并继续一次下载，确认已完成的流不会重复传输。线上未提供所选规格或字幕产生的明确回退警告不视为失败。

## 本地打包

```bash
pyinstaller --noconfirm --clean BilibiliDownloader.spec
pyinstaller --noconfirm --clean BiliFlowUpdater.spec
```

- macOS：生成 `dist/BilibiliDownloader.app` 和目录构建。
- Windows：生成 `dist/BilibiliDownloader/BilibiliDownloader.exe`。
- 视觉素材会收集到冻结应用中；运行时路径统一由 `gui/resources/paths.py` 解析。
- spec 根据平台选择 `app_icon.icns`、`app_icon.ico` 或 `app_icon.png`。
- `packaging_hooks/hook-keyring.py` 只收集目标系统的凭据库后端，避免携带其他平台实现。

### 原生安装包（full）

先按 Release 流程生成 `dist/variants/full`，嵌入 FFmpeg、录制引擎、许可证、独立更新程序与构建描述，再生成安装包。Windows 目录还包含 `biliflow-payload.json`：它记录受管理程序文件的 SHA-256，供更新后的卸载清理使用，不包含用户配置或媒体。

```bash
python -m scripts.package_installers \
  --root dist/variants/full/BilibiliDownloader.app \
  --platform macOS --release-id vX.Y.Z
```

Windows 在本机使用相同命令，将 root 改为 `dist/variants/full/BilibiliDownloader`、platform 改为 `Windows`，并通过 `--compiler <ISCC.exe>` 指定 Inno Setup 6.7.3。流水线从官方固定版本下载编译器并核对 SHA-256，中文翻译随仓库保存。安装默认无需提权，程序位于 `%LOCALAPPDATA%\Programs\BiliFlow\BilibiliDownloader`，卸载程序和维护工具位于父目录的 `uninst`，因此 ZIP 更新不会替换卸载组件。应用和独立更新程序持有运行标识；安装及卸载持有安装标识，防止同时替换程序。

macOS 使用系统 `hdiutil`，无需额外打包依赖。DMG 在应用签名完成后生成；配置 Developer ID 时，在临时签名钥匙串销毁前完成 DMG 签名、公证和票据装订。无证书构建仍验证应用 ad-hoc 签名，不宣称完成公证。

原生校验必须在对应平台运行：

```bash
python -m scripts.verify_native_installer \
  --directory . --platform macOS --release-id vX.Y.Z
```

校验器将安装/复制得到的文件与同次构建的 full ZIP 按路径、摘要和符号链接目标逐项比较，运行冻结 CLI，并生成绑定 ZIP 与安装包 SHA-256 的 `*.verification.json`。Windows 还测试覆盖安装、运行中拦截、目录替换后的卸载与用户媒体保留；脚本会实际写入临时目录和当前用户的卸载注册表，只能在没有既有 BiliFlow 安装的干净测试账号中运行。macOS 检查镜像、Applications 链接、拖拽等效复制和应用签名。验证器不启动真实下载、录制或 GUI，也不读取账号。

GUI 的原生验收单独执行：macOS 检查系统菜单、红黄绿按钮、融合工具栏、全屏和 Retina；Windows 检查 100%/125%/150%/200% 缩放、窗口按钮、快捷键和文件选择器。发布演练另外上传 `BiliFlow-Windows-visuals-<release-id>`，其中三个缩放目录保存原生 Windows 后端的字体、下拉截图及渲染记录。Qt 控件截图用于布局比较；包含系统标题栏的截图应使用只捕获目标窗口的工具另行保存，避免带入其他应用或桌面内容。原生安装验证报告不代表 GUI 人工验收通过。

独立更新程序只依赖 Python 标准库，不包含 Qt。Release 流水线通过 `python -m scripts.prepare_update_bundle` 为每个 full/lite 变体加入 `biliflow-updater`（Windows 为 `.exe`）和 `biliflow-build.json`；构建信息包含规范化版本、平台、架构、变体和更新协议。macOS 必须在嵌入这些文件之后签名。直接用应用 spec 构建的目录没有发行描述文件，自动安装会转为手动安装。

使用 Developer ID 时，导入证书后通过 `MACOS_UPDATER_SIGNING_IDENTITY` 重新构建更新程序，使单文件程序内嵌的 Python 库也使用同一身份签名，再嵌入应用并公证。仅对更新程序外层执行 `codesign` 无法替代内嵌库的签名。无证书时沿用 ad-hoc 签名。

发布流水线运行 `python -m scripts.smoke_updater --helper <更新程序路径> --platform macOS|Windows`，在临时目录用冻结夹具验证 full/lite 的替换、重启和启动失败回滚；夹具不会进入发布包，也不会读取真实配置、凭据或媒体。可在本地运行同一命令验证实际平台。

更新协议使用用户配置目录下 `updates/<事务 ID>/transaction.json`、启动确认和提交文件。主程序确认新版窗口及数据库初始化成功之前，不启动下载或直播后台服务；独立更新程序等待最多 60 秒，失败时恢复旧程序及配置、SQLite 数据快照。程序生命周期使用共享锁，安装使用独占锁；不要删除运行中的锁文件。

Release 的 full 变体还会从锁定的 FFmpeg 7.1 提交构建最小 LGPL 可执行文件。下载脚本会先核对源码 SHA-256。构建启用本地文件协议、MOV/MP4、FLV、MPEG-TS 输入和 MP4、M4A、FLAC 输出，包含 H.264/AAC parser、AAC 解码器（用于 MPEG-TS 音频参数探测）及转封装所需 bitstream filters；导出始终使用 `-c copy`，不启用网络协议、编码器、GPL 或 nonfree 组件。macOS 编译和链接部署目标固定为 12.0：

```bash
python scripts/prepare_bundled_ffmpeg.py download-source \
  --output /tmp/FFmpeg-7.1-source.tar.gz
bash scripts/build_bundled_ffmpeg.sh \
  /tmp/FFmpeg-7.1-source.tar.gz /tmp/biliflow-ffmpeg
```

`prepare_bundled_ffmpeg.py prepare` 会验证版本、构建参数和 LGPL 声明，再生成构建通知及 full/lite SBOM。不要用未经该检查的预编译 FFmpeg 替换发布输入。

full 构建还包含 `biliflow-recorder`。使用 Rust 1.96.0 和 `cargo build --release --locked --manifest-path native/recorder/Cargo.toml` 构建；Windows 设置 `RUSTFLAGS=-C target-feature=+crt-static`，macOS 设置 `MACOSX_DEPLOYMENT_TARGET=12.0`。源码与所有 crate 版本已固定。运行 `scripts/prepare_bundled_recorder.py` 为 full SBOM 添加 Rust 依赖图、二进制/锁文件摘要，并从实际依赖源收集 `RECORDER-NOTICE.txt`。具体命令和验收状态见[直播录制](LIVE_RECORDING.md)。

原生 CI 在 macOS、Windows、Linux 上运行协议策略测试和生成媒体测试；Release 工作流用刚编译的最小 FFmpeg 再次检查 FLV/HLS 导出。夹具构建的 `test-fixtures` 特性只用于本机 HTTP 样本，禁止分发，准备包时会拒绝此类二进制。正式发布前必须完成直播文档列出的双平台实机和双路 8 小时门槛。

构建后至少验证冻结 CLI 和包版本。macOS 还应验证应用包签名结构：

```bash
dist/BilibiliDownloader/BilibiliDownloader --help
codesign --verify --deep --strict dist/BilibiliDownloader.app
plutil -extract CFBundleShortVersionString raw \
  dist/BilibiliDownloader.app/Contents/Info.plist
```

Windows 使用 `dist\BilibiliDownloader\BilibiliDownloader.exe --help`。本地无 Developer ID 时 PyInstaller 生成的是 ad-hoc 签名，只能验证包完整性，不能替代正式签名与 Apple 公证。

重新生成应用图标：

```bash
python scripts/build_app_icons.py
```

脚本以 `app_icon_source.png` 为输入，生成运行时 PNG、macOS ICNS 和 Windows ICO。修改来源素材前必须核对许可证并更新 `THIRD_PARTY_NOTICES.md`。

## 发布流程

### 0.8.8 发布检查（2026-10-21）

- 版本与正式标签统一为 `0.8.8` / `v0.8.8`；更新日志、中英文 README 与文档中心同步。本版修复 Windows 11 激活时旧标题栏重现，以及最大化 / 还原按钮点击失效。
- 修复 PR #26 的提交 `08a0576` 已通过 [CI 39590612933](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39590612933) 全部 11 项检查；Windows 原生界面专项 14 项通过，Windows Python 3.12 全量 970 项通过、13 项跳过。本地全量 979 项通过、4 项跳过，Ruff、编译和 diff 检查通过。
- Windows 深浅模式均通过真实 Win32 鼠标点击，检查空白处点击、激活、最大化、还原与重新显示，核对桌面合成截图、Qt / Win32 窗口状态及还原尺寸。DPI 命中计算覆盖 100% / 150% 和负坐标显示器；实际 Snap 悬停菜单及混合 DPI 切换仍需实机复核。
- 沿用标签发布流程：双平台构建、冻结更新与回滚、原生安装器、SBOM 和统一附件校验全部通过后创建正式 Release，发布后核对 14 个附件及安装包摘要。使用新补丁版本供 v0.8.7 用户检查升级，保留已有版本附件。
- 发布提交 `3d19aaa` 的 [CI 39592756560](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39592756560) 全部 11 项检查通过；[Release 39592788751](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39592788751) 的 5 个任务全部成功。[v0.8.8](https://github.com/itsVicOC/bilibili-downloader/releases/tag/v0.8.8) 已公开并标为 Latest，非草稿、非预发布版，14 个附件齐全；公开 SHA-256 清单的 13 个载荷摘要均与 GitHub digest 一致，两份原生安装验证报告绑定的安装器与 ZIP 摘要一致。
- 官方镜像同步成功，公网 `latest.json` 指向 v0.8.8；六个 EXE / DMG / ZIP 下载目标的 HEAD 请求均为 200，大小与发布元信息一致，官网首页与下载页均为 200。实际更新查询确认 v0.8.7 可发现 v0.8.8，v0.8.8 不会再次提示同版本更新；验收仅读取元信息、校验清单与报告，不在本机下载或运行安装器。

### 0.8.7 发布检查（2026-10-21）

- 版本与正式标签统一为 `0.8.7` / `v0.8.7`；更新日志、中英文 README 与文档中心同步。本版修复 Windows 重复标题、模式切换后的窗口按钮颜色及两端启动焦点，不改变媒体业务、任务库或配置结构。
- 发布前本地全量 971 项测试通过、2 项跳过，Ruff、编译和 diff 检查通过；源代码提交 `09b069d` 的 [CI 39579967071](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39579967071) 共 11 项检查通过。
- 双平台原生截图覆盖两套配色、深浅模式及三种窗口尺寸，记录实际客户区大小；Windows 标题栏使用桌面合成截图检查重复标识和按钮对比度。Snap 悬停、多屏 DPI 切换等人工验证范围见视觉文档。
- 沿用标签发布流程，双平台构建、原生安装器和统一附件校验全部通过后创建正式 Release；发布后复核 14 个附件、稳定版状态及安装包摘要。

### 0.8.6 发布检查（2026-10-21）

- 版本由 `bilibili_downloader.__version__` 统一提供，正式标签为 `v0.8.6`；更新日志包含小流动画、桌面界面整理、文件选择器与依赖安全修复，中英文 README、文档中心、用户指南与截图同步。
- 本地全量 963 项测试通过、1 项跳过；动画与调度专项 90 项通过，原生 Cocoa 组件测试 64 项通过。编译、Ruff 和 diff 检查通过；两种后端各有 64 张小流截图，覆盖五个时段和完整 / 迷你布局。
- 十二套动画精灵图、GIF、生成原稿与提示词随源码保存；运行时图集沿用现有资源目录，源码与冻结程序无需联网。PyInstaller 构建及冻结资源摘要核对通过。
- 推送 `v0.8.6` 后，沿用下方标签发布流程，由双平台构建、原生安装器与统一附件校验通过后发布正式 Release；正式版版本号不含 beta / rc 标记。


### 0.8.2 发布检查（2026-10-19）

- 版本由 `bilibili_downloader.__version__` 统一提供，正式标签为 `v0.8.2`；中英文 README、更新日志、用户指南和外观截图已同步。
- 本地通过 566 项 Python 测试、编译、Ruff 与 diff 检查；macOS offscreen 与原生 Cocoa 各生成 277 张演示截图，复核范围见[视觉规范](UI_DESIGN.md)。
- 使用 `v0.8.1` 标签导出的旧代码在临时目录创建真实任务库，再由本版打开；检查 schema、原始行、状态和备份保持一致，并验证记录移除/撤销及 schema 校验失败时保留原库。旧配置自动补全外观默认值。
- 发布提交为 `3be4258`；[CI 39189925900](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39189925900) 的 13 项检查与 [Release 39189955990](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39189955990) 的 5 个任务全部通过。双平台完成媒体样本、内置 MP4 导出、冻结更新程序与背景目录回滚、原生安装器、SBOM 和统一产物校验；Windows 原生字体与下拉另通过 100%/125%/150%/200% 缩放检查。
- [v0.8.2 Release](https://github.com/itsVicOC/bilibili-downloader/releases/tag/v0.8.2) 已公开并标为 Latest，非草稿、非预发布版，14 个附件齐全。下载后独立核对 macOS full DMG 及两份原生安装验证报告，SHA-256 均与清单一致；清单包含全部 13 个载荷附件的摘要。

### 本轮验证记录（2026-10-17）

源代码提交 `604d089` 的[发布演练 dry-run-35](https://github.com/itsVicOC/bilibili-downloader/actions/runs/38996475166) 已通过；`publish=false`，没有创建 Release。

- macOS、Windows 各通过 457 项 Python 测试；本地 Ruff、编译与空白检查通过。
- 两端冻结更新程序完成 full/lite 替换、重启和失败回滚验证，媒体样本与 MP4 导出验证通过。
- macOS DMG 挂载、Applications 入口、复制、签名结构、载荷与 ZIP 对比、冻结 CLI 均通过。
- Windows EXE 首次安装、覆盖安装、运行中拦截、目录替换后的卸载及用户媒体保留通过；卸载器延迟自清理也已纳入等待。
- 两个平台的安装包、ZIP、SBOM、原生验证报告、FFmpeg 源码与 SHA-256 清单通过统一校验。
- Windows 原生后端的 100%/125%/150%/200% 字体与下拉检查、macOS Retina 菜单/快捷键/全屏复核见[视觉规范](UI_DESIGN.md)。Windows 系统边框、文件选择器及实际多屏切换仍需桌面人工复核。

### 无发布演练

每次修改发布工作流或依赖后，先从 `main` 手动运行 Release workflow。`publish` 默认值必须保持为 `false`：

```bash
gh workflow run release.yml --ref main -f publish=false
gh run list --workflow release.yml --event workflow_dispatch --limit 1
gh run watch <run-id> --exit-status
```

该模式会在 GitHub 托管的 macOS 与 Windows runner 上完成测试、PyInstaller 构建、冻结 CLI 冒烟、SBOM 生成、artifact 上传/下载、SHA-256 生成和统一验证，但不会创建 GitHub Release。下载运行产生的 `BilibiliDownloader-release-dry-run-<run-number>` artifact 后可重复执行同一验证器：

```bash
python -m scripts.verify_release_bundle <解压目录> \
  --release-id dry-run-<run-number>
```

验证器要求两个平台各有 full/lite ZIP、对应 CycloneDX SBOM、full 原生安装包和原生验证报告。full 必须包含 FFmpeg、构建通知与 LGPL 文件，lite 必须不含 FFmpeg；固定提交的 FFmpeg 源码归档也必须存在。验证器会逐项核对 `SHA256SUMS.txt`，任何一项缺失、路径不安全或摘要不匹配都会阻止后续发布。

### 候选版与正式版

版本号遵循语义化版本。发布前必须同步更新：

- `bilibili_downloader/__init__.py` 中的 `__version__`；项目元数据、应用包与“关于”窗口均从这里读取。
- `CHANGELOG.md` 顶部版本、日期与变更。
- README 中受支持平台或安装方式发生的变化。

候选版使用 Python 兼容的 `X.Y.ZbN`、`X.Y.ZrcN` 版本与对应 `v` 标签。Release workflow 通过 `packaging.version.Version.is_prerelease` 标记预发布版，包含 beta、rc 等形式。候选版验证完成后，再把版本和 Changelog 更新为 `X.Y.Z` 并发布正式标签。

`v0.7.0` 应先发布 `v0.7.0rc1`。候选版除常规 full/lite 包验证外，还要使用不提交到仓库的测试账号完成两项手工冒烟：一个免费完整单集，以及一个该账号已经获得完整播放权限的会员或已购单集。确认解析、权限判断、DASH 合并和附加项正常后立即删除测试产物；不得保存或上传媒体、Cookie、签名播放 URL、页面初始状态或包含账号标识的日志。另用无权限或试看剧集确认应用在创建 `.biliflow-parts` 媒体文件前拒绝下载。

验证并提交后推送版本标签：

```bash
git tag -a vX.Y.Z -m "BiliFlow vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

标签中的 `X.Y.Z` 必须与 `bilibili_downloader.__version__` 完全一致。标签应创建在已推送且通过本地验证的发布提交上。

涉及 `core/task_repository.py` 时，还必须用上一公开版本创建的真实任务库做一次升级验证。确认升级前备份的 `PRAGMA user_version` 和表结构未变化、升级后任务数量与状态一致、迁移失败不会隔离或覆盖可读的原库。不要用生产任务库作为唯一测试副本。

`.github/workflows/release.yml` 会在 macOS 与 Windows runner 上重新执行测试和 PyInstaller 构建，并对冻结后的命令行程序执行 `--help` 冒烟检查。构建产物会先汇总并通过 `scripts/verify_release_bundle.py`，只有验证成功后才允许发布：

- `BilibiliDownloader-macOS-{full,lite}-vX.Y.Z.zip`
- `BilibiliDownloader-Windows-{full,lite}-vX.Y.Z.zip`
- `BilibiliDownloader-macOS-full-vX.Y.Z.dmg`
- `BilibiliDownloader-Windows-full-vX.Y.Z-setup.exe`
- 两份绑定原生安装验证结果的 `*.verification.json`
- 每个平台和变体对应的 `*.cdx.json` CycloneDX 依赖清单
- `FFmpeg-7.1-source.tar.gz` 对应源码归档
- `SHA256SUMS.txt` 完整性校验文件

发布任务从 `CHANGELOG.md` 提取最上方版本作为 Release 正文。工作流默认只有读取仓库内容的权限，只有真正的 publish job 获得 `contents: write`。手动运行时从分支选择 `publish=true` 会被拒绝；只能在 tag ref 上显式发布。任一平台构建或验证失败时不会创建不完整 Release；应修复后发布新补丁版本，不覆盖已公开的版本资产。

发布完成后应确认 Release 不是草稿，正式版未标为预发布、beta/rc 版已标为预发布，四个 full/lite ZIP、两个原生安装包、两份原生验证报告、四个 SBOM、FFmpeg 源码归档与 `SHA256SUMS.txt` 均存在，并从校验文件抽查至少一个安装包。最后在干净环境中启动应用，确认“关于”窗口版本与标签一致。

默认 macOS/Windows 构建没有商业代码签名。macOS Release 工作流支持可选的 Developer ID 签名与 Apple 公证；在受保护的 GitHub Environment 中配置以下 Secrets 后会自动启用：

- `MACOS_CERTIFICATE`：Developer ID Application `.p12` 的 Base64 内容。
- `MACOS_CERTIFICATE_PASSWORD`：`.p12` 密码。
- `MACOS_SIGNING_IDENTITY`：完整的 Developer ID Application 身份名称。
- `APPLE_ID`、`APPLE_APP_PASSWORD`、`APPLE_TEAM_ID`：`notarytool` 公证凭据。

未配置 `MACOS_CERTIFICATE` 时该步骤会跳过，保持未签名发布行为。Windows Authenticode 仍需维护者提供独立代码签名证书。所有凭据必须存放在 GitHub Secrets 中，不得提交到仓库。

CI 与 Release workflow 中的第三方 Action 固定到完整提交 SHA，行尾注释记录对应主版本。Dependabot 的 `github-actions` 更新器负责提交 SHA 升级；不要手动改回浮动主版本标签。

### 本轮界面验收

`--ui-refresh-only` 使用隔离配置、数据库及离线账号，覆盖两套配色、深浅模式、三种尺寸、五类设置和账号状态。`--physical-pixels` 保留原生像素，供字体检查使用。主窗口标题栏需另在目标系统检查拖动、缩放、窗口按钮、全屏与贴靠；截图成功不代表这些系统交互均已验收。
