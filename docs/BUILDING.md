# 构建与发布

## 开发环境

- Python 3.10–3.12
- FFmpeg（真实下载与合并验证需要）
- macOS、Windows 或 Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
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
git diff --check
```

CI 在 Ubuntu 和 Windows 上使用 Python 3.10、3.11、3.12 运行测试。GUI 测试使用 `QT_QPA_PLATFORM=offscreen`。

## 本地打包

```bash
pyinstaller --noconfirm --clean BilibiliDownloader.spec
```

- macOS：生成 `dist/BilibiliDownloader.app` 和目录构建。
- Windows：生成 `dist/BilibiliDownloader/BilibiliDownloader.exe`。
- 视觉素材会收集到冻结应用中；运行时路径统一由 `gui/resources/paths.py` 解析。
- spec 根据平台选择 `app_icon.icns`、`app_icon.ico` 或 `app_icon.png`。

重新生成应用图标：

```bash
python scripts/build_app_icons.py
```

脚本以 `app_icon_source.png` 为输入，生成运行时 PNG、macOS ICNS 和 Windows ICO。修改来源素材前必须核对许可证并更新 `THIRD_PARTY_NOTICES.md`。

## 发布流程

版本号遵循语义化版本。发布前必须同步更新：

- `pyproject.toml` 中的项目版本。
- “关于”窗口中的版本。
- `CHANGELOG.md` 顶部版本、日期与变更。
- README 中受支持平台或安装方式发生的变化。

验证并提交后推送版本标签：

```bash
git tag -a v0.3.0 -m "BiliFlow v0.3.0"
git push origin main
git push origin v0.3.0
```

`.github/workflows/release.yml` 会在 macOS 与 Windows runner 上重新执行测试和 PyInstaller 构建，然后上传：

- `BilibiliDownloader-macOS-v0.3.0.zip`
- `BilibiliDownloader-Windows-v0.3.0.zip`

发布任务从 `CHANGELOG.md` 提取最上方版本作为 Release 正文。任一平台构建失败时不会创建不完整 Release；应修复后删除远端标签并重新发布新补丁版本，不覆盖已公开的版本资产。

当前 macOS/Windows 构建没有商业代码签名或 Apple 公证。引入签名后应使用 GitHub Environments 管理证书与密钥，不得把凭据提交到仓库。
