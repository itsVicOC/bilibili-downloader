# 下载与归档流程验收

日期：2026-11-02。基于 `0.8.10b1` 的未发布工作区增量，未创建 Release。所有数据、媒体和截图均为本地临时演示数据；未读取用户账号或下载记录。

## 已实现与验证

| 检查 | 结果 |
|---|---|
| 完整 pytest（Qt offscreen） | 1203 通过、6 项平台条件跳过；4 条既有 Qt 弃用警告 |
| macOS Cocoa 原生专项 | 79 通过，覆盖归档流程、原下载管理和 issue 回归 |
| Ruff、源码编译、diff 空白检查 | 通过 |
| 真实 FFmpeg | 现场生成测试媒体，封装进度、轨道与时长解析通过；损坏媒体被识别 |
| macOS ARM64 应用构建 | PyInstaller 构建通过，冻结程序下载帮助包含新参数，ad-hoc 签名完整性校验通过 |
| macOS 冻结更新器 | full/lite 安装重启、启动失败回滚共四种场景通过；包含媒体库及待登记记录保留检查 |
| 界面截图 | 深浅模式，900×640、1120×760、1320×860；离屏与原生各 20 张演示截图 |

原生环境：macOS 27.0.1 ARM64，Python 3.11.15；原生测试需要访问 WindowServer。沙盒内首次尝试因没有屏幕而中止，取得窗口服务访问后专项通过，不将前一次中止算作产品功能失败或通过。

行为验证包括：

- 清除任务、重启仓储及隐藏文件记录后，同规格媒体仍可复用；实际规格未知、较低画质、文件丢失或文件变化不会被当作满足目标。
- 补全元数据或弹幕时，媒体流下载替身不得被调用，主媒体 SHA-256 保持不变；附件失败可单独重试。相同内容的并发请求只传输一次媒体。
- 单语言扩展为全部字幕时保留已有语言；删除其中一个字幕文件后可识别并补回。保留已有附件的转换警告。
- 严格匹配失败发生于媒体传输前；重启队列继续显示实际规格和规格回退状态。
- 队列搜索、批量搜索和分 P 范围选择只提交可见条目；异步文件核对期间改变来源或规格不会套用过期结果。
- 网络重试保存计数及下次时间，暂停可取消等待，最多三轮；权限和网络的嵌套异常仍能正确分类。
- 目录重定位先预览，再以单个事务更新媒体及附件；目标不可读取时不修改记录。单文件重定位同步附件语言映射和结果路径。
- 缺少工具或磁盘暂不可访问不会被记录为媒体损坏；轨道或时长不可解析时标记异常。
- 新持久字段采用有默认值的任务／结果 JSON，不增加数据库列；旧字段和输出快照继续兼容。现有媒体库、待入库结果备份与更新回滚回归通过。

媒体核验只解析轨道及可用时长，不执行全片逐帧解码，不能证明内容真实性。文件变化检测使用已登记的文件属性签名；旧记录仍须具备已知实际规格，不能用原请求规格补造实际规格。

## 规模基准

运行 `python -m scripts.benchmark_archive`；原始输出位于 `build/archive-benchmark.json`。使用临时一字节媒体，测量数据库和界面开销，不代表真实视频磁盘吞吐、网络速度或所有机器的性能。

| 场景 | 本机测量 |
|---|---:|
| 一千条任务数据库读取 | 10.9 ms |
| 一千条任务列表填充 | 189.2 ms |
| 一千条任务搜索 | 21.3 ms |
| 一万条文件列表加载与填充 | 457.9 ms |
| 一万条文件搜索 | 99.5 ms |
| 索引匹配已有媒体 | 0.5 ms |
| 一万条文件后台快速检查（含完成刷新） | 1989.3 ms |
| 后台检查期间最大界面心跳间隔 | 483.7 ms |

附件查询由逐资产读取改为成批读取；界面恢复任务时批量更新，后台检查最多每 50 ms 推送一次常规进度。基准保留启动填充及完成刷新开销，不把单次搜索耗时作为完整操作耗时。

## 复现

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=cocoa .venv/bin/python -m pytest -q tests/test_archive_workflow.py tests/test_download_management.py tests/test_issue_regressions.py
.venv/bin/ruff check bilibili_downloader tests scripts packaging_hooks
.venv/bin/python -m compileall -q bilibili_downloader tests scripts
.venv/bin/python -m scripts.benchmark_archive
.venv/bin/python -m scripts.capture_docs_screenshots --archive-only --output-dir docs/images/archive
.venv/bin/python -m scripts.capture_docs_screenshots --native --archive-only --output-dir build/ui-parity/archive-native
PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache" .venv/bin/pyinstaller --noconfirm BilibiliDownloader.spec
dist/BilibiliDownloader.app/Contents/MacOS/BilibiliDownloader download --help
codesign --verify --deep --strict dist/BilibiliDownloader.app
git diff --check
```

GitHub 验收使用独立 `codex/archive-workflow-acceptance` 分支：推送触发跨平台 CI，Release 工作流以 `publish=false` 执行打包、安装器、更新及回滚验证，不创建版本标签或发布 Release。CI 与打包任务均包含归档专项、中文字段截图和一千任务／一万文件记录基准；冻结更新测试额外核对媒体库和待登记记录的保留及回滚。运行链接与最终结果在验收结束后补充。

## 尚未完成的发布验收

- Windows 发布包实机安装、升级、启动与回滚；本机无法执行 Windows 实机验收。
- macOS full/lite 安装包的实际安装与跨版本升级演练；本轮仅验证本地应用构建、冻结 CLI 和签名完整性，不等于安装器或 Apple 公证验收。
- 双路真实直播至少 8 小时，以及真实断网、地址过期、系统睡眠、进程强退和物理磁盘满。继续按 [直播实测清单](LIVE_RECORDING.md#专项实测记录清单)记录文件可读性、缺口、内存和界面响应；现有模拟故障回归不能替代这些实测。

上述项目保留为待验收，不因本轮自动化、原生专项或打包通过而标记完成。

## 命名字段中文说明补充

「插入字段」菜单显示中文名称与原占位符，悬停显示用途和示例；「查看命名字段」列出全部字段的中文解释。三类模板菜单合计 35 个可选项，已逐项检查替换选中文字时插入的仍是原占位符。相关对话框、工作区与下载管理回归 112 项通过，深浅模式和 900×640 窗口截图已复核；截图见 `docs/images/archive/naming-fields-*.png` 和 `naming-help-*.png`。
