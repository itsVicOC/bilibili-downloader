# 提示、悬停与布局精修验收

日期：2026-11-03。基线为已发布的 `v0.8.10b2`（`6cd1b46494d32d8a9d37a2d5590ad62307c955a6`），实施分支为 `codex/ui-feedback-boundaries`。本轮为尚未发布的 GUI 增量，版本号保持 `0.8.10b2`；没有修改已发布安装包、标签或 Release。所有测试和截图使用临时演示数据，不读取用户账号或媒体。

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

补充：[完整行键盘焦点](images/ui-feedback/after/feedback-row-keyboard-light.png)、[窄栏选择统计与选择操作](images/ui-feedback/after/feedback-selection-light-420.png)、[青蓝深色下载配置](images/ui-feedback/after/blue-options-dark-900.png)、[媒体不可访问错误](images/ui-feedback/after/polish-attachments-offline-light.png)。完整矩阵在 GitHub 原生截图附件中保留。

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

原生截图、原生测试、完整离屏回归与性能基准独立执行。完整页面矩阵共 96 张，为两套配色 × 深浅模式 × 三种窗口尺寸（900×640、1120×760、1320×860），补充分 P、字段、离线、错误、空结果、等待与完整详情。操作区另有 56 张截图，覆盖三种宽度及 150% 字体；测试确认真实字体度量增加。几何原始记录见[粉紫](validation/ui-feedback/star-trail-geometry.json)、[青蓝](validation/ui-feedback/blue-geometry.json)及[改前基线](validation/ui-feedback/baseline-geometry.json)。

- 新增 `tests/test_ui_feedback.py`，验证共享操作栏、菜单单次触发、焦点转移、完整统计、控件边界及屏幕适配；下拉说明在切换选项后继续保留。
- 最终 Cocoa 原生专项通过 **108 项**，含新增 52 项提示、悬停与边界测试；最终完整回归和 CI／双平台 `publish=false` 打包结果将随最终源码提交回填。
- 沿用千条任务、万条文件记录的三轮配对基准与原响应门槛：搜索／选择 P95 ≤300ms，后台稳态心跳 ≤250ms，初次加载及结束刷新 ≤2s，取消 ≤1s。结果以本轮 GitHub 同一源码的报告为准。

复现命令：

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests scripts packaging_hooks
QT_QPA_PLATFORM=cocoa python -m pytest -q tests/test_ui_feedback.py tests/test_combo_box.py tests/test_workflow_polish.py
python -m scripts.capture_ui_feedback --native --color-theme star_trail --output-dir build/ui-feedback/pressure-after/star_trail
python -m scripts.capture_docs_screenshots --native --physical-pixels --workflow-polish-only --color-theme star_trail --output-dir build/ui-feedback/after-native/star_trail
python -m scripts.benchmark_workflow_polish --output-dir build/ui-feedback/performance
```

Windows 原生测试使用 `QT_QPA_PLATFORM=windows`。对照截图使用 `scripts.capture_ui_feedback --source-root <已归档 beta2 源码> --record-baseline`；该模式记录旧布局的溢出，不把旧行为作为新实现的通过标准。`geometry.json` 只有完整执行后才标记 `complete: true`，记录按钮／文字边界与源码信息。

## 继续单独记录的实机项目

用户设备上的真实中文输入法候选窗、混合 DPI／系统缩放、小屏幕人工操作和辅助技术体验，以及长时双路直播、拔盘、磁盘满与物理网络故障仍需实测。此处没有将自动化截图或合成性能数据表述为上述设备验收已通过。发布安排另行决定。
