# 贡献指南

感谢你改进 BiliFlow。提交代码前请先确认改动范围清晰、可验证，并且不会包含账号凭据、下载内容或个人配置。

## 开始开发

```bash
git clone https://github.com/itsVicOC/bilibili-downloader.git
cd bilibili-downloader
python -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints.txt -e ".[dev]"
pytest -q
```

Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1` 激活虚拟环境。

## 提交 Issue

Bug 报告应包含：

- 操作系统、CPU 架构、Python 版本与应用版本。
- 可以复现问题的最短步骤。
- 实际行为与预期行为。
- 完整错误信息；日志中请删除 SESSDATA、Cookie、下载 URL 和个人路径。
- FFmpeg 相关问题请附 `ffmpeg -version` 输出。

功能建议请说明目标使用场景，不要只描述界面控件。

安全漏洞不要提交公开 Issue，请按 [SECURITY.md](SECURITY.md) 私下报告。

## Pull Request

1. 从 `main` 创建用途单一的分支。
2. 延续现有模块边界和 PySide6 组件风格，避免无关重构。
3. 行为修改必须添加或更新测试；网络测试应使用 mock，不依赖线上内容长期可用。
4. GUI 改动至少检查日间、夜间两种系统主题和 900×640 最小窗口。
5. 新增第三方素材时，同时更新 `THIRD_PARTY_NOTICES.md`，写明文件、作者、原始 URL 和许可证。
6. 提交前运行完整验证命令。

```bash
python -m compileall -q bilibili_downloader tests
pytest -q
ruff check bilibili_downloader tests packaging_hooks
git diff --check
```

涉及打包、资源路径或依赖变化时还应运行：

```bash
pyinstaller --noconfirm --clean BilibiliDownloader.spec
```

提交信息建议使用 `feat:`、`fix:`、`docs:`、`test:`、`refactor:` 或 `chore:` 前缀。PR 描述需要说明行为变化、验证结果和潜在兼容性影响。

## 代码约定

- 支持 Python 3.10+，不要使用更高版本独占语法。
- 后台网络与下载操作不得阻塞 Qt 主线程。
- 不在日志、异常、截图或测试夹具中记录有效 Cookie。
- 文件写入应尽可能采用临时文件和原子替换，下载中间文件必须支持安全恢复或清理。
- 用户可见错误需要给出可执行的下一步，而不是只显示内部异常类型。

提交代码即表示你同意按本仓库 MIT License 授权你的贡献。
