# 下载与归档流程验收

> 本文保留前轮验收结果。后续以 `6175482` 为基线的交互精修已改为跨筛选保留勾选，并将命名菜单升级为可搜索字段面板；当前用法与结果见[流程精修验收](WORKFLOW_POLISH_VALIDATION.md)。

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
| 一千条任务数据库读取 | 10.3 ms |
| 一千条任务列表填充 | 191.1 ms |
| 一千条任务搜索 | 20.9 ms |
| 一万条文件列表加载与填充 | 413.8 ms |
| 一万条文件搜索 | 78.5 ms |
| 索引匹配已有媒体 | 1.0 ms |
| 一万条文件后台快速检查（含完成刷新） | 5264.4 ms |
| 后台检查期间最大界面心跳间隔 | 441.5 ms |

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

## GitHub 自动验收

验收基线为 [`d94268c`](https://github.com/itsVicOC/bilibili-downloader/commit/d94268cc8c99d88841933e25fd03d593d1c08494)，位于独立 `codex/archive-workflow-acceptance` 分支。推送触发跨平台 CI；Release 工作流以 `publish=false` 执行，构建标识为 `dry-run-55`，不创建版本标签或发布 Release。

| 检查 | 运行与结果 |
|---|---|
| 跨平台 CI | [15/15 项通过](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41416061006)：Ubuntu／Windows Python 3.11、3.12，macOS Python 3.12，三平台录制引擎、双平台冻结更新器、Windows 四档缩放与依赖审计 |
| macOS 完整包 | [原生构建与安装验证](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41416128007/job/125180386497)通过；1189 项测试通过、20 项条件跳过，安装 fixture FFmpeg 后原生下载归档专项 79 项通过 |
| Windows 完整包 | [原生构建与安装验证](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41416128007/job/125180386791)通过；1188 项测试通过、21 项条件跳过，安装 fixture FFmpeg 后原生下载归档专项 79 项通过 |
| 双平台发布包汇总 | [未发布打包运行](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41416128007)成功；4 个 ZIP／2956 个文件、4 份 SBOM／733 个组件、2 个安装器和 8563 个 FFmpeg 源码文件验证通过，发布步骤按预期跳过 |

CI 与打包任务均包含归档专项、中文字段截图和一千任务／一万文件记录基准。冻结更新测试验证 full/lite 安装重启及启动失败回滚，并核对媒体库和待登记记录的保留及恢复。macOS 已完成 DMG 校验、挂载、复制安装、逐文件对比 ZIP、签名完整性及冻结 CLI 检查；本次使用 ad-hoc 签名，未执行 Apple 公证。Windows 已完成中文及空格路径下 EXE 安装、逐文件对比 ZIP、冻结 CLI、重复安装、运行锁阻止覆盖、更新后卸载和保留用户媒体检查。

[完整测试包附件](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41416128007/artifacts/13129652006)包含双平台 full/lite ZIP、full EXE／DMG、SBOM、`SHA256SUMS.txt` 和两份 `*.verification.json` 安装报告。汇总验证核对包内容、FFmpeg／录制引擎依赖、SBOM 摘要、安装报告与对应 ZIP／安装器摘要，以及校验清单。

`dry-run-55` 的 `BiliFlow-Windows-management-ui-dry-run-55` 和 `BiliFlow-macOS-management-ui-dry-run-55` 附件内均包含 `archive-benchmark.json` 及归档、中文命名字段原生截图。以下基准使用 Python 3.12.10、Qt offscreen 和临时一字节媒体；截图另由原生 windows/cocoa 后端生成。

| 场景 | Windows Server 2025 托管机 | macOS 26.6.2 ARM64 托管机 |
|---|---:|---:|
| 一千条任务数据库读取 | 35.0 ms | 16.3 ms |
| 一千条任务列表填充 | 763.9 ms | 239.5 ms |
| 一千条任务搜索 | 70.7 ms | 29.1 ms |
| 一万条文件列表加载与填充 | 1523.4 ms | 709.0 ms |
| 一万条文件搜索 | 231.5 ms | 110.2 ms |
| 索引匹配已有媒体 | 2.8 ms | 1.2 ms |
| 一万条文件后台快速检查 | 148768.7 ms | 7380.3 ms |
| 后台检查期间最大界面心跳间隔 | 183.5 ms | 611.3 ms |

托管机硬件和文件系统配置不同，平台性能对比仍需同条件对测。Windows 本次整批后台检查约 149 秒，总耗时仍有优化空间；本轮提供规模基线与响应数据，跨机型耗时门槛待定义。CI 工作区截图与基准附件保留 7 天，打包、界面和安装验证报告附件保留 14 天。

首轮 [CI](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41396311357) 发现 Windows 路径大小写导致的断言差异；同时修复字幕语言映射及重定位时的路径标准化，并补充全部字幕重复导入不重复传输的检查。

首轮 Windows 打包任务还暴露批量停止测试的固定十秒等待过早到期；测试替身改为等待取消事件，并在退出时确保释放线程。仍要求 110 个真实线程池任务停止后整批移除、在主线程处理回调、撤销后全部保持暂停状态。

后续 [Windows 原生运行](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41411948250)的专项与截图均已完成，但规模基准清理临时目录时失败：SQLite 的事务上下文不会自动关闭连接。基准脚本显式关闭建档连接，并在临时目录清理成功后才写出结果。同步修正命名字段截图的滚动定位，确保深浅模式都显示「插入字段」按钮；应用行为不受这两项采集脚本修订影响。本地跟踪确认基准退出前所有 SQLite 连接均已关闭，修复后的完整 CI 与 `publish=false` 打包验收均已通过。

## 尚未完成的发布验收

- Windows 用户设备上的安装、启动、旧版本升级及恢复演练；GitHub Windows 原生桌面检查与用户设备验收分开记录。
- macOS 用户设备上的 full/lite 安装、旧版本升级及权限交互演练；GitHub 托管环境的 DMG 安装和冻结更新器检查已通过，商业签名及 Apple 公证仍未完成。
- 双路真实直播至少 8 小时，以及真实断网、地址过期、系统睡眠、进程强退和物理磁盘满。继续按 [直播实测清单](LIVE_RECORDING.md#专项实测记录清单)记录文件可读性、缺口、内存和界面响应；现有模拟故障回归不能替代这些实测。

上述项目保留为待验收，不因本轮自动化、原生专项或打包通过而标记完成。

## 命名字段中文说明补充

「插入字段」菜单显示中文名称与原占位符，悬停显示用途和示例；「查看命名字段」列出全部字段的中文解释。三类模板菜单合计 35 个可选项，已逐项检查替换选中文字时插入的仍是原占位符。相关对话框、工作区与下载管理回归 112 项通过，深浅模式和 900×640 窗口截图已复核；截图见 `docs/images/archive/naming-fields-*.png` 和 `naming-help-*.png`。
