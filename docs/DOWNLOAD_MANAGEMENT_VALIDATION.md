# 任务与下载文件易用性验收

日期：2026-11-01。当前证据使用临时离线数据，不读取真实下载记录、不发起 B 站请求，不实际回收用户文件。

## 已验收的交互

- 批量操作优先处理所选任务；无选择时处理当前列表。全部任务入口单独标注，并覆盖隐藏任务。
- 普通记录直接移除并可撤销；停止下载再移除只确认一次。批量停止统一反馈，保留文件和断点。
- 文件页直接提供打开文件、打开文件夹和检查；主文件与附件操作目标独立。
- 空列表、无匹配、加载及加载失败有独立状态；无目标时不启动检查。
- 检查可取消，期间仍可筛选、打开文件；进度按实际文件（含附件）计数。
- 文件记录撤销与任务撤销独立。失败保留重试机会，恢复隐藏记录不复制媒体文件。
- 检查、回收失败只显示短摘要；完整路径和诊断通过详情查看。回收确认保留数量、附件数量及恢复说明，长清单可展开。
- 刷新、窄宽窗口切换保留选择与附件展开状态。紧凑窗口中附件首行完整显示。
- 命名预览优先展示相对路径；完整预计路径可查看和复制，音质变化同步更新扩展名。批量摘要区分作品数与任务数。

## 验证结果

| 检查 | 结果 |
|---|---|
| 全量 pytest，Qt offscreen | 1169 通过、6 跳过；4 条现有 Qt 弃用警告 |
| macOS 原生专项 | 易用性 37 项、issue 复核 8 项通过；包含设置、真实落盘、批量移除和音视频轨校验 |
| 后续交互与布局回归 | 78 通过 |
| Ruff、源码编译、diff 空白检查 | 通过 |
| Windows 原生验收 | 已加入 CI，当前机器未执行 Windows 实机验证 |

macOS 原生环境为 macOS 27.0.1 ARM64、PySide6 6.11.2。本轮全量回归包含响应式选择保留与 issue 专项复核；真实媒体验证使用 FFmpeg/ffprobe 8.1.2。

## 截图复核

运行 `scripts.capture_docs_screenshots --download-management-only`，覆盖两种配色、深浅模式、900×640 / 1120×760 / 1320×860 窗口，以及附件展开、无匹配、部分失败、回收确认和三类命名预览，共 48 个场景。

本地原生证据目录：`build/ui-parity/management-usability-verified/`。截图工具会在每次捕获后隐藏窗口，原生可见性断言在捕获前执行；附件断言检查垂直可见区域，允许文件名正常省略。

复现命令：

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=cocoa .venv/bin/python -m pytest -q tests/test_download_management.py tests/test_issue_regressions.py
.venv/bin/python -m scripts.capture_docs_screenshots --native --download-management-only --output-dir build/ui-parity/management-usability-verified
.venv/bin/ruff check bilibili_downloader tests packaging_hooks scripts
.venv/bin/python -m compileall -q bilibili_downloader tests scripts
```

Windows/macOS CI 沿用原生 UI 矩阵执行同一专项与截图场景；CI 结果与人工使用反馈继续分别记录。

## 两个 issue 的最终复核

- [#30 合集下载时的文件命名问题](https://github.com/itsVicOC/bilibili-downloader/issues/30)：从设置页保存目录、选择媒体格式和多分 P 模板，再将长标题的 110 个分 P 加入队列，检查 110 个实际文件的名称和目录。视频默认模板、音频自定义分层模板均通过，且入队后修改全局目录不改变已有任务的目标。该链路使用离线传输与合并替身验证文件落盘。
- [#31 无法批量删除任务](https://github.com/itsVicOC/bilibili-downloader/issues/31)：经界面「更多 → 移除全部任务」清空 110 条完成记录，验证所有文件与媒体库记录保留；另有真实线程池用例覆盖 110 条运行／等待任务停止后移除及撤销。
- 对报告中提及的「只有音频」补充真实媒体验证：发现旧封装命令会在异常视频输入仅有音轨时成功生成纯音频 MP4。现显式要求输入 0 的视频轨与输入 1 的音轨。缺少任一必需轨道时失败，不产生成功成品，也不登记成功文件；正常视频经 ffprobe 检查具有 video/audio 两类轨道，显式音频模式仍只输出 audio。

结论范围：当前工作区的明确功能诉求已由代码与离线回归覆盖。原报告的实际视频、账号和网络条件尚未复现，不能据此断言其音频现象的原始原因；Windows 发布包实机与报告者复验仍需完成。历史任务保留入队快照，历史文件不会自动改名。本记录不表示修复已随正式版发布。
