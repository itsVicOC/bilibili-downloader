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
python -m compileall -q bilibili_downloader tests
pytest -q
ruff check bilibili_downloader tests packaging_hooks
git diff --check
```

CI 在 Ubuntu 和 Windows 上使用 Python 3.10、3.11、3.12 运行测试，并在 macOS/Python 3.12 做冒烟验证。GUI 测试使用 `QT_QPA_PLATFORM=offscreen`；Ubuntu runner 会先安装 PySide6 需要的 `libegl1` 与 `libgl1`，独立任务使用 `pip-audit` 检查已安装依赖。

`constraints.txt` 固定经过验证的直接运行与开发依赖。修改依赖时，应在三类系统的 CI 通过后同步更新约束版本；平台专属传递依赖由 pip 解析器管理。

## 本地打包

```bash
pyinstaller --noconfirm --clean BilibiliDownloader.spec
```

- macOS：生成 `dist/BilibiliDownloader.app` 和目录构建。
- Windows：生成 `dist/BilibiliDownloader/BilibiliDownloader.exe`。
- 视觉素材会收集到冻结应用中；运行时路径统一由 `gui/resources/paths.py` 解析。
- spec 根据平台选择 `app_icon.icns`、`app_icon.ico` 或 `app_icon.png`。
- `packaging_hooks/hook-keyring.py` 只收集目标系统的凭据库后端，避免携带其他平台实现。

重新生成应用图标：

```bash
python scripts/build_app_icons.py
```

脚本以 `app_icon_source.png` 为输入，生成运行时 PNG、macOS ICNS 和 Windows ICO。修改来源素材前必须核对许可证并更新 `THIRD_PARTY_NOTICES.md`。

## 发布流程

版本号遵循语义化版本。发布前必须同步更新：

- `bilibili_downloader/__init__.py` 中的 `__version__`；项目元数据、应用包与“关于”窗口均从这里读取。
- `CHANGELOG.md` 顶部版本、日期与变更。
- README 中受支持平台或安装方式发生的变化。

验证并提交后推送版本标签：

```bash
git tag -a vX.Y.Z -m "BiliFlow vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

标签中的 `X.Y.Z` 必须与 `bilibili_downloader.__version__` 完全一致。标签应创建在已推送且通过本地验证的发布提交上。

`.github/workflows/release.yml` 会在 macOS 与 Windows runner 上重新执行测试和 PyInstaller 构建，然后上传：

- `BilibiliDownloader-macOS-vX.Y.Z.zip`
- `BilibiliDownloader-Windows-vX.Y.Z.zip`
- 每个平台对应的 `*.cdx.json` CycloneDX 依赖清单
- `SHA256SUMS.txt` 完整性校验文件

发布任务从 `CHANGELOG.md` 提取最上方版本作为 Release 正文。任一平台构建失败时不会创建不完整 Release；应修复后删除远端标签并重新发布新补丁版本，不覆盖已公开的版本资产。

发布完成后应确认 Release 不是草稿或预发布版本，两个平台压缩包、两个 SBOM 与 `SHA256SUMS.txt` 均存在，并从校验文件抽查至少一个安装包。最后在干净环境中启动应用，确认“关于”窗口版本与标签一致。

默认 macOS/Windows 构建没有商业代码签名。macOS Release 工作流支持可选的 Developer ID 签名与 Apple 公证；在受保护的 GitHub Environment 中配置以下 Secrets 后会自动启用：

- `MACOS_CERTIFICATE`：Developer ID Application `.p12` 的 Base64 内容。
- `MACOS_CERTIFICATE_PASSWORD`：`.p12` 密码。
- `MACOS_SIGNING_IDENTITY`：完整的 Developer ID Application 身份名称。
- `APPLE_ID`、`APPLE_APP_PASSWORD`、`APPLE_TEAM_ID`：`notarytool` 公证凭据。

未配置 `MACOS_CERTIFICATE` 时该步骤会跳过，保持未签名发布行为。Windows Authenticode 仍需维护者提供独立代码签名证书。所有凭据必须存放在 GitHub Secrets 中，不得提交到仓库。
