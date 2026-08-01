# 构建与发布

## 开发环境

- Python 3.10–3.12
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
tests/            # 单元与回归测试
```

## 验证

```bash
python -m compileall -q bilibili_downloader tests scripts
pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
git diff --check
```

CI 在 Ubuntu 和 Windows 上使用 Python 3.10、3.11、3.12 运行测试，并在 macOS/Python 3.12 做冒烟验证。GUI 测试使用 `QT_QPA_PLATFORM=offscreen`；Ubuntu runner 会先安装 PySide6 需要的 `libegl1` 与 `libgl1`，独立任务使用 `pip-audit` 检查已安装依赖。

`constraints.txt` 固定经过验证的直接运行与开发依赖。修改依赖时，应在三类系统的 CI 通过后同步更新约束版本；平台专属传递依赖由 pip 解析器管理。

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
```

- macOS：生成 `dist/BilibiliDownloader.app` 和目录构建。
- Windows：生成 `dist/BilibiliDownloader/BilibiliDownloader.exe`。
- 视觉素材会收集到冻结应用中；运行时路径统一由 `gui/resources/paths.py` 解析。
- spec 根据平台选择 `app_icon.icns`、`app_icon.ico` 或 `app_icon.png`。
- `packaging_hooks/hook-keyring.py` 只收集目标系统的凭据库后端，避免携带其他平台实现。

Release 的 full 变体还会从锁定的 FFmpeg 7.1 提交构建最小 LGPL 可执行文件。下载脚本会先核对源码 SHA-256，构建仅启用本地文件协议、MOV/MP4 输入以及 MP4、M4A、FLAC 输出，不包含网络协议、编码器、解码器、GPL 或 nonfree 组件；macOS 编译和链接部署目标固定为 12.0：

```bash
python scripts/prepare_bundled_ffmpeg.py download-source \
  --output /tmp/FFmpeg-7.1-source.tar.gz
bash scripts/build_bundled_ffmpeg.sh \
  /tmp/FFmpeg-7.1-source.tar.gz /tmp/biliflow-ffmpeg
```

`prepare_bundled_ffmpeg.py prepare` 会验证版本、构建参数和 LGPL 声明，再生成构建通知及 full/lite SBOM。不要用未经该检查的预编译 FFmpeg 替换发布输入。

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

### 无发布演练

每次修改发布工作流或依赖后，先从 `main` 手动运行 Release workflow。`publish` 默认值必须保持为 `false`：

```bash
gh workflow run release.yml --ref main -f publish=false
gh run list --workflow release.yml --event workflow_dispatch --limit 1
gh run watch <run-id> --exit-status
```

该模式会在 GitHub 托管的 macOS 与 Windows runner 上完成测试、PyInstaller 构建、冻结 CLI 冒烟、SBOM 生成、artifact 上传/下载、SHA-256 生成和统一验证，但不会创建 GitHub Release。下载运行产生的 `BilibiliDownloader-release-dry-run-<run-number>` artifact 后可重复执行同一验证器：

```bash
python scripts/verify_release_bundle.py <解压目录> \
  --release-id dry-run-<run-number>
```

验证器要求两个平台各有 full/lite ZIP 和对应 CycloneDX SBOM。full 必须包含 FFmpeg、构建通知与 LGPL 文件，lite 必须不含 FFmpeg；固定提交的 FFmpeg 源码归档也必须存在。验证器会逐项核对 `SHA256SUMS.txt`，任何一项缺失、路径不安全或摘要不匹配都会阻止后续发布。

### 候选版与正式版

版本号遵循语义化版本。发布前必须同步更新：

- `bilibili_downloader/__init__.py` 中的 `__version__`；项目元数据、应用包与“关于”窗口均从这里读取。
- `CHANGELOG.md` 顶部版本、日期与变更。
- README 中受支持平台或安装方式发生的变化。

候选版使用 Python 兼容的 `X.Y.ZrcN` 版本与 `vX.Y.ZrcN` 标签。Release workflow 会把包含 `rc` 的标签自动标记为 GitHub prerelease。候选版验证完成后，再把版本和 Changelog 更新为 `X.Y.Z` 并发布正式标签。

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
- 每个平台和变体对应的 `*.cdx.json` CycloneDX 依赖清单
- `FFmpeg-7.1-source.tar.gz` 对应源码归档
- `SHA256SUMS.txt` 完整性校验文件

发布任务从 `CHANGELOG.md` 提取最上方版本作为 Release 正文。工作流默认只有读取仓库内容的权限，只有真正的 publish job 获得 `contents: write`。手动运行时从分支选择 `publish=true` 会被拒绝；只能在 tag ref 上显式发布。任一平台构建或验证失败时不会创建不完整 Release；应修复后发布新补丁版本，不覆盖已公开的版本资产。

发布完成后应确认 Release 不是草稿或预发布版本，四个 full/lite 安装包、四个 SBOM、FFmpeg 源码归档与 `SHA256SUMS.txt` 均存在，并从校验文件抽查至少一个安装包。最后在干净环境中启动应用，确认“关于”窗口版本与标签一致。

默认 macOS/Windows 构建没有商业代码签名。macOS Release 工作流支持可选的 Developer ID 签名与 Apple 公证；在受保护的 GitHub Environment 中配置以下 Secrets 后会自动启用：

- `MACOS_CERTIFICATE`：Developer ID Application `.p12` 的 Base64 内容。
- `MACOS_CERTIFICATE_PASSWORD`：`.p12` 密码。
- `MACOS_SIGNING_IDENTITY`：完整的 Developer ID Application 身份名称。
- `APPLE_ID`、`APPLE_APP_PASSWORD`、`APPLE_TEAM_ID`：`notarytool` 公证凭据。

未配置 `MACOS_CERTIFICATE` 时该步骤会跳过，保持未签名发布行为。Windows Authenticode 仍需维护者提供独立代码签名证书。所有凭据必须存放在 GitHub Secrets 中，不得提交到仓库。

CI 与 Release workflow 中的第三方 Action 固定到完整提交 SHA，行尾注释记录对应主版本。Dependabot 的 `github-actions` 更新器负责提交 SHA 升级；不要手动改回浮动主版本标签。
