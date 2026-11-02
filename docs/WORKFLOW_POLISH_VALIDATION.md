# 新增下载与归档流程体验精修验收

日期：2026-11-02。改前基线为 `61754828a85e1cff099c3425e12e0496cb1ef2c1`，实施分支为 `codex/archive-workflow-acceptance`。这是 `0.8.10b1` 上的未发布增量，不创建 Release。所有测试、截图和性能数据使用临时演示记录，不访问用户账号、媒体或任务数据库。

## 原生前后对比

改前由 `scripts.capture_workflow_baseline` 从 Git 归档基线源码，以同一组离线资料重新运行；改后由 `scripts.capture_docs_screenshots --native --workflow-polish-only` 生成。以下为 macOS Cocoa 逻辑像素截图，保留原主题和小流，未使用网页或设计稿代替应用。

| 用户任务 | 改前 | 改后 |
|---|---|---|
| 确认多 P 下载与规格（900×640） | [旧配置](images/workflow-polish/before/archive-options-light-900.png) | [统一范围、任务数与底栏](images/workflow-polish/after/archive-options-light-900.png) |
| 查找并累加勾选分 P | [旧选择器](images/workflow-polish/before/archive-pages-light.png) | [搜索、查看已选、序号添加](images/workflow-polish/after/archive-pages-light.png) |
| 只补附件并保留已有文件 | [旧弹窗](images/workflow-polish/before/polish-attachments-light.png) | [逐项状态与明确动作](images/workflow-polish/after/polish-attachments-light.png) |
| 查看文件结果并继续处理 | [旧文件详情](images/workflow-polish/before/polish-files-light-900.png) | [媒体／规格／附件及上下文操作](images/workflow-polish/after/polish-files-light-900.png) |
| 看懂命名字段 | [中文菜单](images/workflow-polish/before/naming-fields-light.png) | [中文搜索、用途、示例及占位符](images/workflow-polish/after/naming-fields-light.png) |

补充状态：[批量跨筛选选择](images/workflow-polish/after/archive-batch-dark-900.png)、[筛选外选择](images/workflow-polish/after/polish-filtered-selection-light.png)、[查看已选](images/workflow-polish/after/polish-selection-review-light.png)、[媒体离线](images/workflow-polish/after/polish-attachments-offline-light.png)、[目录映射](images/workflow-polish/after/polish-relocate-light.png)、[完整结果](images/workflow-polish/after/polish-result-details-dark.png)、[网络等待与立即重试](images/workflow-polish/after/polish-retry-dark.png)、[模板预览](images/workflow-polish/after/polish-naming-light.png)、[青蓝深色附件弹窗](images/workflow-polish/after/blue-attachments-dark.png)。

最终源码的完整原生截图矩阵共 **96 张**，位于 `build/workflow-polish/model-native/{star_trail,bilibili_blue}/`：两套配色、深浅模式、900×640／1120×760／1320×860，包含配置、批量、结果、文件及长标题，附加分 P、字段、补全、零选择、离线、目录映射、重试、无匹配与已选视图。GitHub 对应原生附件保留相同矩阵。

## 按用户操作验收

| 操作任务 | 已验证结果与证据 |
|---|---|
| 搜索 A 勾选，再搜索 B 继续勾选 | 批量、分 P、任务、文件保留稳定 ID；选择栏显示筛选外数量，当前结果全选累加。`test_workflow_polish`、`test_archive_workflow`、`test_download_management` |
| 查看已选并返回、清空选择 | 查看已选临时忽略过滤器；返回恢复原条件；清空作用于全部选择。空结果有清除入口，勾选不丢失 |
| 仅查看作品详情 | 真实鼠标点击标题只改变焦点，行首复选框或空格用于勾选；Ctrl/Cmd+A 累加当前结果 |
| 按序号添加 `1–5,8`、非法输入及取消 | 合法范围累加；非法输入就地说明且不修改选择；零选择禁用确认；取消不修改调用方。弹窗范围、摘要任务数与提交页面一致 |
| 后台刷新、主题切换和筛选后处理 | 列表保留勾选、焦点和滚动；操作捕获目标 ID，后续筛选不改变范围；迟到的读取和已关闭窗口不被更新 |
| 下载前核对已有文件 | 后台按 `MediaMatch` 区分复用／补附件／新下载；允许继续编辑和提交；来源或规格变化废弃旧预览，下载服务最终核对 |
| 保存后确认结果 | 媒体、规格、附件分别展示；完整目标／实际规格、路径、逐项附件和诊断进入统一详情；无附件需求显示“未选择附件” |
| 单独补全字幕等附件 | 默认勾选已确认缺少的项目，已有附件保留，字幕单语言／全部语言范围明确；媒体缺失禁用提交；已有媒体字节不变。原归档回归及新弹窗测试 |
| 权限或目录错误后重试 | 登录成功后才重试对应任务；取消登录不重试；更换目录只更新明确选择的任务快照。`test_workflow_polish` |
| 等待、封装和附件处理 | 自动重试显示轮次、倒计时及立即／停止入口；结构化阶段区分实际传输、FFmpeg 封装进度、附件项目，兼容原 CLI 回调 |
| 快速检查、媒体核验与取消 | 各自显示检查范围、进度及摘要；立即呈现取消中，提交已完成缓冲；媒体核验不再显示回收文案 |
| 移动目录后重新定位 | 一个弹窗完成原目录、新目录、后台预览和确认；编辑使预览失效；取消不更改记录；普通主按钮统一更新。另测回收／撤销、暂停／重启与清任务后复用 |
| 中文查找命名字段并替换模板 | 按模板限制字段，中文名称／用途／示例可搜索，插入原光标或选区；常用模板替换可撤销；保存策略与旧任务命名快照不变 |

新增回归见 `tests/test_workflow_polish.py`（38 项，含 15 个字段插入参数）；更新旧测试以反映已确认的跨筛选保留规则。数据库结构、原媒体签名及复用规则保持兼容，选择状态仅存当前会话。

## 本地验证

- macOS 原生 Cocoa 用户流程、主题和文件模型测试：**158 项通过**；另以 Qt 官方模型检查器验证行数据、勾选状态、模型重置和选择交集。完整两配色截图在该原生测试后独立生成。
- 完整离屏回归：**1,240 项通过、6 项平台专项跳过**；5 条 Qt 弃用警告。此后文件右键菜单范围修复通过 74 项定向回归；最终源码以 GitHub 全量结果为准。
- Ruff、编译与 `git diff --check` 通过。
- 原生 Tab／Space／Enter、焦点返回、弹窗边界、取消、长标题与两套深浅主题已覆盖自动化及截图；Cocoa 下补充验证 Qt 输入法预编辑、中文提交、Enter 不误提交和取消后的入口焦点返回，组合输入不影响隐藏勾选；真实中文输入法候选窗、系统缩放／混合 DPI、用户设备上的手动键盘与可用性检查继续单独记录。

## 配对性能基准

同一台机器交替运行基线和改后各三次；每轮使用 1,000 个任务、10,000 条文件记录及临时一字节媒体，仅反映数据库／文件系统调用／界面开销，不代表真实视频吞吐。检查在锁外执行，最多 500 个资产分批读取，每 100 项或 250ms 提交；旧路径／状态／签名不匹配的结果不覆盖新记录，取消保留已检查结果。

本地 macOS Python 3.11.15 优化后工作区三轮配对结果（`933be36` 加文件右键菜单修复，原始 JSON 记录工作区未提交标记）：

| 指标 | 中位结果 | 三轮中最大值／门槛 |
|---|---:|---:|
| 万条快速检查 | 基线 5,913.5ms → 463.9ms，降低 92.16% | Windows 降低至少 50% 待 runner 实测 |
| 文件搜索 P95 | 23.4ms | 23.6ms／300ms |
| 文件勾选／清空 P95 | 7.6ms | 8.2ms／300ms |
| 后台稳态心跳最大间隔 | 21.3ms | 21.5ms／250ms |
| 初次加载 | 483.8ms | 492.7ms／2,000ms |
| 结束刷新 | 40.9ms | 43.0ms／2,000ms |
| 取消反馈／结束 | 0.0ms／14.4ms | 0.1ms／14.6ms（保留已完成）／1,000ms |

稳态心跳只计算后台检查运行中，初次加载与结束刷新另设门槛；原始全程心跳仍输出供诊断。自动门槛逐轮检查上述时延，不以三轮中位数掩盖最慢轮；Windows 检查改进幅度按三轮中位数比较。原始 JSON 在 `build/workflow-polish/paired-optimized/`；GitHub 独立性能矩阵使用 Windows／macOS Python 3.12 同 runner 三次配对并上传全部 JSON。

复现：

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
python -m scripts.capture_workflow_baseline --native --output-dir build/workflow-polish/before-native
python -m scripts.capture_docs_screenshots --native --workflow-polish-only --color-theme star_trail --output-dir build/workflow-polish/native/star_trail
python -m scripts.capture_docs_screenshots --native --workflow-polish-only --color-theme bilibili_blue --output-dir build/workflow-polish/native/bilibili_blue
python -m scripts.benchmark_workflow_polish --output-dir build/workflow-polish/performance
```

## GitHub 与发布包

首轮源码为 `b92845e`；[CI 首轮](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41452080330)暴露 macOS 在系统仅文本 Tab 模式下跳过新规格策略的问题，已补应用内正反向路径与该模式回归，分 P 首屏布局及全部字段示例同步完善。首轮 macOS 性能虽降低快速检查耗时约 82%，但全选、初次加载、稳态心跳与取消结束超出门槛。进一步采用选择状态直接绘制复选框、每 500 个资产读取检查及返回已提交文件补丁，检查完成后更新对应行，避免整库解码和重建；保留原门槛。优化后的三轮本地配对结果见上表，全部门槛通过；仍须双平台 runner 三轮复验。文件右键菜单另测不改变已有勾选，并明确批量维护数量。第二轮复验源码为 [`0a90d35`](https://github.com/itsVicOC/bilibili-downloader/commit/0a90d35a88f9a349b68453b0f2c12906a80d453b)；[对应 CI](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41454485409)再次发现单轮初次加载 2,304.7ms 超过 2 秒，因此文件表改为行数据模型，按需提供显示／辅助功能数据，消除六万单元格对象分配；当前本机单轮首次加载 247.8ms、搜索 P95 8.6ms、结束刷新 15.5ms。Windows 原基线单轮约 5 分钟，20 分钟步骤只能完成两轮；执行上限调整为 40 分钟、作业 50 分钟，三轮配对及原有性能门槛不变。下一轮最终源码与结果完成后补录。原生测试、截图、性能为独立步骤；正式验收不得沿用前轮绿色状态冒充本轮结果。构建 full/lite、安装、升级恢复、备份回滚和工具链继续沿用既有工作流。

用户设备的全新安装／跨版本升级、长时双路直播（至少八小时）、真实断网／磁盘满／拔盘／休眠／强退与混合 DPI 仍需单独实测，托管 runner 和合成测试不能替代。所有自动化通过后，本轮也不将这些物理设备项目标记完成。
