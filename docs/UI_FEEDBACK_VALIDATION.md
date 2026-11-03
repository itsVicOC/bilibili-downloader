# 提示、悬停与布局精修验收

日期：2026-11-03。基线为已发布的 `v0.8.10b2`（`6cd1b46494d32d8a9d37a2d5590ad62307c955a6`），实施分支为 `codex/ui-feedback-boundaries`。本轮 GUI 增量纳入 `v0.8.10b3`，以下保留各阶段源码与验收结果；beta 2 已发布安装包和标签保持原内容。所有测试和截图使用临时演示数据，不读取用户账号或媒体。

## 原生前后对比

改前从 beta 2 的 Git 归档源码运行；改后使用当前源码，通过 macOS Cocoa 原生 Qt 窗口截图。页面保留原配色、字号、导航与小流。

| 用户操作 | 改前 | 改后 |
|---|---|---|
| 在 420px 操作区确认大量任务 | [被最小宽度撑开的底栏](images/ui-feedback/before/feedback-output-light-420.png) | [统计与操作分行，次要动作进入更多](images/ui-feedback/after/feedback-output-light-420.png) |
| 放大字体后确认任务 | [150% 字体](images/ui-feedback/before/feedback-output-light-font150.png) | [完整任务数、路径及主操作](images/ui-feedback/after/feedback-output-light-font150.png) |
| 悬停下拉选项 | [额外描边](images/ui-feedback/before/feedback-hover-light.png) | [仅改变底色](images/ui-feedback/after/feedback-hover-light.png) |
| 使用方向键切换选项 | [旧焦点反馈](images/ui-feedback/before/feedback-keyboard-light.png) | [仅当前键盘项显示内缩焦点框](images/ui-feedback/after/feedback-keyboard-light.png) |
| 检查跨筛选批量选择 | [重复统计及路径](images/ui-feedback/before/archive-batch-light-900.png) | [集中统计，底栏显示实际任务数](images/ui-feedback/after/archive-batch-light-900.png) |
| 打开附件补全 | [重复保护说明](images/ui-feedback/before/polish-attachments-light.png) | [保留逐项状态与一处保护说明](images/ui-feedback/after/polish-attachments-light.png) |
| 查看文件结果并继续处理 | [重复规格说明](images/ui-feedback/before/polish-files-light-900.png) | [三类结果及上下文操作](images/ui-feedback/after/polish-files-light-900.png) |

补充：[完整行键盘焦点](images/ui-feedback/after/feedback-row-keyboard-light.png)、[窄栏选择统计与选择操作](images/ui-feedback/after/feedback-selection-light-420.png)、[青蓝深色下载配置](images/ui-feedback/after/blue-options-dark-900.png)、[青蓝深色实际悬停](images/ui-feedback/after/blue-hover-dark.png)、[媒体不可访问错误](images/ui-feedback/after/polish-attachments-offline-light.png)。完整矩阵在 GitHub 原生截图附件中保留。

同一源码的 Windows 原生样本：[150% 字体与万条数量](images/ui-feedback/after/windows-feedback-output-light-font150.png)、[青蓝深色悬停](images/ui-feedback/after/windows-feedback-hover-dark.png)、[整行键盘焦点](images/ui-feedback/after/windows-feedback-row-keyboard-light.png)。已复核中文文字、按钮完整性及悬停／焦点分离；几何原始记录见[粉紫](validation/ui-feedback/windows-star-trail-geometry.json)与[青蓝](validation/ui-feedback/windows-blue-geometry.json)。

## 操作与边界

| 场景 | 实现与验证 |
|---|---|
| 只保留必要反馈 | 下载、批量、分 P、附件、文件详情及设置删除重复教学与成功说明；错误、风险、处理中、取消、路径及范围仍在原区域显示。命名字段继续显示中文名称、用途、示例；详细诊断从完整详情读取 |
| 解析部分失败、核对失败或取消 | 未解析按钮带数量并打开逐项原因；后台核对失败显示可继续提交的说明；取消保留已解析结果。不用勾选成功提示覆盖未解决问题 |
| 鼠标与键盘切换 | 下拉悬停只有填充，已保存选项保留勾号；各列表移除逐格焦点框，方向键／Tab 使用整行内缩框。指针移回后不改变选择或当前项；导航激活标记保留 |
| 空间不足 | 「完整配置」「打开文件夹」等低频动作先收纳；选择栏使用「选择操作」。QAction 与按钮共用文本、启用状态及单一回调路径，原有更多菜单项继续保留 |
| 主操作、取消与停止 | 提交、保存、取消检查、停止等待及弹窗取消保持可见；仍不足时分行。移入菜单的按钮退出 Tab 序列，原按钮焦点回到更多；弹窗结束返回触发入口 |
| 动态变化 | 在 420／560／780px 操作区反复调整宽度，修改文字、万条数量、显隐、启用状态及实际主题字体度量；保留完整按钮文字与点击区域。长路径可复制完整值 |
| 屏幕与弹窗 | 主窗口通常保持 900×640 基线；可用区域更小时调整最小尺寸与位置。弹窗外框受可用区域约束，正文滚动、确认区固定；覆盖 800×560 与 720×480 模拟工作区。Cocoa 将达到 maximumSize 的普通弹窗报告为最大化，仍需修正其位置 |
| 操作范围与数据 | 跨搜索保留选择、筛选外数量、查看已选返回、固定操作目标及取消规则沿用原回归；没有公共服务接口、数据库迁移或路径／命名快照变更 |

## 本地与 GitHub 验证

原生截图、原生测试、完整离屏回归与性能基准独立执行。每个平台的页面矩阵有 96 张，为两套配色 × 深浅模式 × 三种窗口尺寸（900×640、1120×760、1320×860），补充分 P、字段、离线、错误、空结果、等待与完整详情。操作区另有 56 张截图，覆盖三种宽度及 150% 字体；测试确认真实字体度量增加。GitHub 双平台共保留本轮矩阵 304 张，其他通用场景未计入。Cocoa 几何原始记录见[粉紫](validation/ui-feedback/star-trail-geometry.json)、[青蓝](validation/ui-feedback/blue-geometry.json)及[改前基线](validation/ui-feedback/baseline-geometry.json)。

- 新增 `tests/test_ui_feedback.py`，验证共享操作栏、菜单单次触发、焦点转移、完整统计、控件边界及屏幕适配；下拉说明在切换选项后继续保留。
- 最终验收提交 `d670dc0` 的完整离屏回归为 **1,300 项通过、6 项平台专项跳过**（266.72 秒）；9 条 Qt 测试弃用警告。Cocoa 原生专项 **120 项通过**，含新增 53 项提示、悬停与边界测试及原有操作栏检查；最终源码重新生成完整原生截图矩阵。Ruff、编译与 `git diff --check` 通过。原始[本地验证摘要](validation/ui-feedback/local-tests.json)保留命令与源码信息。
- 首轮 GitHub 验收发现截图脚本按控件遍历顺序取到空菜单，以及 Linux 字体下测试没有实际触发收纳。`ea178f9` 改为定位可见且有内容的菜单，以长文案明确触发收纳并确认原按钮确实获得焦点；原有完整文字、边界、单次触发及焦点返回断言继续保留。旧运行停止，最终记录采用修正后同一源码的结果。
- 原生截图进一步要求鼠标实际从其他行移入，验证悬停填充像素及整行命中状态，覆盖两套配色和深浅模式；Windows 旧操作栏测试改为核对可见控件，不再将隐藏的备用菜单按钮当作屏幕溢出。隐藏控件的焦点转移与菜单行为继续由新专项验证。
- 原生自动化使用 QTest 及匹配的 Qt 视图输入事件。Cocoa／Windows runner 有时只移动光标而不投递鼠标移动，测试会等待窗口显示与实际命中行；截图继续校验真实绘制的底色，不直接设置悬停或焦点绘制状态。此类自动化不替代物理鼠标和键盘的实机验收。
- 空闲复核发现操作栏无条件通知父布局会产生重复排版。`d670dc0` 只在尺寸提示改变时通知父布局；同一孤立场景先等待 200ms，再采样 500ms，额外布局从 10,080 次降为 0 次。新增测试同时验证空闲稳定和改变文案／宽度后继续正确收纳，已有字体与边界断言全部保留。
- 沿用千条任务、万条文件记录的三轮配对基准与原响应门槛：搜索／选择 P95 ≤300ms，后台稳态心跳 ≤250ms，初次加载及结束刷新 ≤2s，取消 ≤1s。结果以本轮 GitHub 同一源码的报告为准。

复现命令：

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests scripts packaging_hooks
QT_QPA_PLATFORM=cocoa python -m pytest -q tests/test_ui_feedback.py tests/test_combo_box.py tests/test_workflow_polish.py tests/test_fluent_refinement.py
python -m scripts.capture_ui_feedback --native --color-theme star_trail --output-dir build/ui-feedback/pressure-after/star_trail
python -m scripts.capture_docs_screenshots --native --physical-pixels --workflow-polish-only --color-theme star_trail --output-dir build/ui-feedback/after-native/star_trail
python -m scripts.benchmark_workflow_polish --output-dir build/ui-feedback/performance
```

Windows 原生测试使用 `QT_QPA_PLATFORM=windows`。对照截图使用 `scripts.capture_ui_feedback --source-root <已归档 beta2 源码> --record-baseline`；该模式记录旧布局的溢出，不把旧行为作为新实现的通过标准。`geometry.json` 只有完整执行后才标记 `complete: true`，记录按钮／文字边界与源码信息。

## 配对性能结果

性能基线沿用归档优化前的 `6175482`，界面截图基线为已发布 beta 2。基准在每个平台同一 runner 上交替执行改前／改后各三次，使用 1,000 条任务、10,000 条文件记录与一字节临时媒体，持续验证既有归档性能门槛。它衡量数据库、文件系统及界面开销，不代表实际影音下载吞吐。

以下响应取三轮最慢值（单位 ms），检查耗时取中位数。最终源码为 `d670dc0`，两平台工作区均干净。

| 指标 | macOS | Windows | 门槛 |
|---|---:|---:|---:|
| 队列搜索 P95 | 131.7 | 123.8 | 300 |
| 队列选择 P95 | 31.6 | 24.6 | 300 |
| 批量搜索 P95 | 50.1 | 26.3 | 300 |
| 批量选择 P95 | 100.8 | 69.8 | 300 |
| 文件搜索 P95 | 30.8 | 27.0 | 300 |
| 文件选择 P95 | 40.3 | 27.4 | 300 |
| 队列初次加载 | 755.5 | 843.5 | 2,000 |
| 批量初次加载 | 466.2 | 657.8 | 2,000 |
| 文件初次加载 | 793.0 | 778.1 | 2,000 |
| 后台稳态心跳最大间隔 | 71.4 | 59.2 | 250 |
| 检查结束刷新 | 30.8 | 34.6 | 2,000 |
| 取消反馈 | 0.2 | 0.2 | 100 |
| 取消结束 | 59.5 | 15.9 | 1,000 |

macOS 万条快速检查中位耗时为 18.66 → 1.71 秒，降低 90.83%。Windows 万条快速检查中位耗时为 232.45 → 5.59 秒，降低 97.59%。

最终 [macOS](validation/ui-feedback/performance/macos/summary.json) 与 [Windows](validation/ui-feedback/performance/windows/summary.json) 报告及六份分轮原始数据已归档，所有门槛通过。

早期提交 `b934c8e` 曾出现单轮取消结束 1,753ms 的长尾；[原报告](validation/ui-feedback/performance/prior-macos-b934/summary.json)保留。本机三轮复核为 14.1／14.3／14.1ms，未复现该长尾；[本机报告](validation/ui-feedback/performance/local/summary.json)仅作复核，包含文档修改导致的工作区脏标记。补充修复空闲布局循环后，最终 `d670dc0` 重新执行两平台完整三轮基准，门槛保持不变；原始长尾记录继续供后续实机核对。

## GitHub 与打包验收

最终源码为 [`d670dc0a0573d47f1b0c928b5d78d93d46d2574f`](https://github.com/itsVicOC/bilibili-downloader/commit/d670dc0a0573d47f1b0c928b5d78d93d46d2574f)，分支为 `codex/ui-feedback-boundaries`。[最终 CI](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41569073936) **17/17 项全部成功**，覆盖 Windows／macOS／Linux、Python 3.11／3.12、原生交互与截图、四档 Windows 标题栏缩放、更新器／录制器与独立三轮配对性能基准。原始[任务摘要](validation/ui-feedback/github/ci.json)与[原生／性能附件标识](validation/ui-feedback/github/ci-artifacts.json)已归档。

[双平台 `publish=false` 打包验收](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41569374432)同一源码已成功：Windows／macOS 构建、原生交互与截图、冻结应用、完整安装、升级与失败回滚，以及汇总包校验通过；发布步骤按预期跳过。构建标识为 `dry-run-69`。原始[任务摘要](validation/ui-feedback/github/package.json)与[产物标识及摘要](validation/ui-feedback/github/package-artifacts.json)已归档。

安装验证比对实际安装内容与 ZIP，验证配置、任务库、媒体库和待恢复记录的保留；full／lite 工具链、CLI 启动、录制器样例和安装更新路径沿用既有发布门槛。原生测试、截图与性能分步执行，最终报告采用 `d670dc0` 的通过结果。早期未通过或停止的运行不计入最终通过。

上述为 beta 3 准备前的开发验收，当时未创建 Release／标签、包版本仍为 `0.8.10b2`。后续 beta 3 发布状态单独记录于[构建与发布](BUILDING.md)。

## 弹窗居中补充修复

基于 `f328777` 修复嵌入页面使用局部坐标定位弹窗的问题。每次显示时改用所属顶层窗口的全局外框（含系统标题栏）计算中心，再限制到该窗口所在屏幕的可用区域；重新打开使用主窗口当前位置，打开后仍可自行拖动。嵌入页面和其他窗口不受影响，系统原生文件选择器继续由系统管理。

- 本地完整回归 1,314 项通过、6 项平台专项跳过，Ruff、编译与差异检查通过。macOS Cocoa 原生回归 85 项通过、1 项虚拟屏幕专项跳过。新增定位测试覆盖普通／流程／消息／长诊断／文件选择弹窗、嵌套弹窗、主窗口移动及缩放后重开、手动拖动、负坐标多屏和小工作区。
- 实际设置页在 900×640 和 1120×760、深浅主题下打开及重新打开「命名字段」，四次原生外框中心偏移均为 0px。[浅色首次打开](images/ui-feedback/dialog-placement/dialog-placement-light-opened.png)、[深色移动后重开](images/ui-feedback/dialog-placement/dialog-placement-dark-reopened.png)、[坐标记录](validation/ui-feedback/dialog-placement-macos.json)已归档。
- 复现截图：`python scripts/capture_docs_screenshots.py --native --dialog-placement-only --output-dir build/dialog-placement`。Windows／macOS CI 已加入新增原生测试和该截图场景；以上历史 CI 与打包结果对应前一轮源码，不代表此补充修复的通过结果。
- 弹窗修复提交 `af45d12` 的[跨平台 CI](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41575862175) **17/17 项通过**，包含 Windows／macOS 原生定位测试与截图、完整回归和三轮性能基准。

## 继续单独记录的实机项目

用户设备上的真实中文输入法候选窗、混合 DPI／系统缩放、小屏幕人工操作和辅助技术体验，以及长时双路直播、拔盘、磁盘满与物理网络故障仍需实测。此处没有将自动化截图或合成性能数据表述为上述设备验收已通过。发布安排另行决定。
