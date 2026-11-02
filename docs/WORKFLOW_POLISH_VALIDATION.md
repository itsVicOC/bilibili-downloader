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

补充状态：[分 P 无匹配](images/workflow-polish/after/parts-empty-light.png)、[批量跨筛选选择](images/workflow-polish/after/archive-batch-dark-900.png)、[筛选外选择](images/workflow-polish/after/polish-filtered-selection-light.png)、[查看已选](images/workflow-polish/after/polish-selection-review-light.png)、[媒体离线](images/workflow-polish/after/polish-attachments-offline-light.png)、[目录映射](images/workflow-polish/after/polish-relocate-light.png)、[完整结果](images/workflow-polish/after/polish-result-details-dark.png)、[网络等待与立即重试](images/workflow-polish/after/polish-retry-dark.png)、[模板预览](images/workflow-polish/after/polish-naming-light.png)、[青蓝深色附件弹窗](images/workflow-polish/after/blue-attachments-dark.png)。

最终源码的完整原生截图矩阵共 **96 张**，位于 `build/workflow-polish/accepted-native/{star_trail,bilibili_blue}/`：两套配色、深浅模式、900×640／1120×760／1320×860，包含配置、批量、结果、文件及长标题，附加分 P、字段、补全、零选择、离线、目录映射、重试、无匹配与已选视图。GitHub 对应原生附件保留相同矩阵。

Windows runner 的同一源码原生画面另见[粉紫浅色 900×640 下载配置](images/workflow-polish/after/windows-download-light-900.png)和[青蓝深色 1320×860 批量清单](images/workflow-polish/after/windows-batch-blue-dark-1320.png)；另有[中文命名字段](images/workflow-polish/after/windows-naming-fields-light.png)与[附件补全](images/workflow-polish/after/windows-attachments-blue-dark.png)。已复核中文字形、窄窗口固定确认栏与跨筛选勾选入口。

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

新增回归见 `tests/test_workflow_polish.py`（42 项，含 15 个字段插入参数）；更新旧测试以反映已确认的跨筛选保留规则。数据库结构、原媒体签名及复用规则保持兼容，选择状态仅存当前会话。

## 本地验证

- macOS 原生用户流程、主题、焦点及模型专项分阶段通过；最后的任务勾选专项为 **96 项通过、1 项平台跳过**。另以 Qt 官方模型检查器验证行数据、勾选状态、模型重置和选择交集。两套配色截图独立生成并复核。
- 最终 `3eb0a3b` 完整离屏回归：**1,246 项通过、6 项平台专项跳过**；5 条 Qt 测试弃用警告。批量缓存、emoji 选区、媒体状态一致性和分段退出探针均包含在该轮回归内。
- Ruff、编译与 `git diff --check` 通过。
- 原生 Tab／Space／Enter、焦点返回、弹窗边界、取消、长标题与两套深浅主题已覆盖自动化及截图；Cocoa 下补充验证 Qt 输入法预编辑、中文提交、Enter 不误提交和取消后的入口焦点返回，组合输入不影响隐藏勾选；真实中文输入法候选窗、系统缩放／混合 DPI、用户设备上的手动键盘与可用性检查继续单独记录。

## 配对性能基准

[最终源码 `3eb0a3b`](https://github.com/itsVicOC/bilibili-downloader/commit/3eb0a3b7f1de72f6b0c5a46ff00e5f20164b1a82)在 GitHub 的 Windows／macOS 独立性能矩阵中均通过。每个平台在同一 runner 内交替执行 `6175482` 基线和最终源码各三次，使用 1,000 个任务、10,000 条文件记录及临时一字节媒体，测量数据库／文件系统调用／界面开销，不代表真实视频吞吐或所有设备的表现。

检查每批读取最多 500 个资产，在数据库锁外访问文件系统，每 100 项或 250ms 批量提交；路径／状态校验阻止旧结果覆盖更新记录，取消保留已完成结果。文件表使用行数据模型，任务勾选直接向 Qt 提供会话状态；搜索与路径预览缓存按来源／配置失效，避免重复创建任务或遍历更新单元格。没有新增持久字段。

搜索和选择计时包括四轮立即事件处理，以将布局／重绘计入当前操作；在清空搜索、切换工作区后完成阶段边界事件派发，避免遗留布局错计到下一操作。按单个可见工作区测量。以下时延取三轮中最慢值；检查耗时和降低比例取三轮中位数。稳态心跳只计后台检查运行中，初次加载和结束刷新分别约束；原始全程心跳仍保留。旧 Windows 基线单轮耗时较长，配对步骤上限为 40 分钟，响应门槛保持原值。

| 指标 | macOS runner | Windows runner | 门槛 |
|---|---:|---:|---:|
| 万条检查中位耗时 | 15,366.9 → 1,609.1ms | 227,247.3 → 5,914.6ms | Windows 降低至少 50% |
| 检查耗时降低 | 89.53% | 97.40% | — |
| 队列搜索 P95 | 139.7ms | 123.9ms | 300ms |
| 队列勾选／清空 P95 | 34.1ms | 22.0ms | 300ms |
| 批量搜索 P95 | 22.8ms | 24.5ms | 300ms |
| 批量勾选／清空 P95 | 71.9ms | 49.3ms | 300ms |
| 文件搜索 P95 | 41.4ms | 25.2ms | 300ms |
| 文件勾选／清空 P95 | 48.1ms | 28.6ms | 300ms |
| 队列初次加载 | 878.0ms | 902.2ms | 2,000ms |
| 批量初次加载 | 537.0ms | 686.9ms | 2,000ms |
| 文件初次加载 | 913.1ms | 899.4ms | 2,000ms |
| 后台稳态心跳最大间隔 | 76.3ms | 45.2ms | 250ms |
| 检查结束刷新 | 44.5ms | 57.5ms | 2,000ms |
| 取消反馈 | 0.3ms | 0.2ms | 100ms |
| 取消结束 | 42.5ms | 32.8ms | 1,000ms |

[macOS 原始数据](validation/workflow-polish/performance/macos/summary.json)与 [Windows 原始数据](validation/workflow-polish/performance/windows/summary.json)已长期归档到仓库，同目录分别保留六份改前／改后 JSON。报告均记录最终源码 SHA、三轮次数、干净工作区及每项门槛通过。

复现：

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
python -m scripts.capture_workflow_baseline --native --output-dir build/workflow-polish/before-native
python -m scripts.capture_docs_screenshots --native --workflow-polish-only --color-theme star_trail --output-dir build/workflow-polish/accepted-native/star_trail
python -m scripts.capture_docs_screenshots --native --workflow-polish-only --color-theme bilibili_blue --output-dir build/workflow-polish/accepted-native/bilibili_blue
python -m scripts.benchmark_workflow_polish --output-dir build/workflow-polish/performance
```

## GitHub 与发布包

验收源码为 [`3eb0a3b7f1de72f6b0c5a46ff00e5f20164b1a82`](https://github.com/itsVicOC/bilibili-downloader/commit/3eb0a3b7f1de72f6b0c5a46ff00e5f20164b1a82)，分支为 `codex/archive-workflow-acceptance`。最终 [CI](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41467767003) **17/17 项全部成功**，原始任务摘要已[归档](validation/workflow-polish/github/ci.json)。Windows Python 3.12 完整回归为 1,231 项通过、21 项跳过；原生专项独立通过。[publish=false 打包](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41467887182)也已成功：双平台构建、安装验证及汇总包校验通过，发布步骤跳过。任务及产物摘要已[归档](validation/workflow-polish/github/package.json)。构建标识为 `dry-run-61`，不创建标签或发布 Release。

原生测试、截图和性能为独立步骤。Windows 与 macOS 分别检查 full/lite 构建、工具链、安装、升级和恢复。退出探针分开等待启动就绪与退出完成，使用文件接收子进程日志避免管道阻塞；保留原有三秒退出看门狗和收尾断言。最终记录只采用上述同一源码的结果，旧的取消或失败运行不计为通过。

安装验证比对实际安装内容与 ZIP 并运行 CLI；升级／回滚使用真实冻结更新程序和临时冻结应用资料，覆盖配置、任务库、媒体库与待入库记录恢复。原生交互验证单独运行源码界面。Windows 另验证中文及空格路径安装／重装、运行锁阻止覆盖、更新后的卸载及用户媒体保留；macOS 验证 DMG 挂载、Applications 入口、复制、签名、内容一致性及 CLI。两平台 full／lite 的安装重启与启动失败回滚均通过，汇总包再次校验 SBOM、SHA-256 和安装验证报告。本次 macOS 使用 ad-hoc 签名并通过严格签名校验，未进行 Apple 公证；这些包用于本轮验收。

[下载已校验的汇总验收包](https://github.com/itsVicOC/bilibili-downloader/actions/runs/41467887182/artifacts/13157720799)，包含 Windows／macOS full、lite ZIP，Windows full 安装程序、macOS full DMG、校验清单、SBOM、安装验证报告及 FFmpeg 源码。GitHub 构建附件保留 14 天；性能原始数据和代表截图已存入仓库。验收后的补录提交仅更新文档、截图与数据，保留上述已验收源码。

用户设备的全新安装／跨版本升级、长时双路直播（至少八小时）、真实断网／磁盘满／拔盘／休眠／强退，以及真实中文输入法候选窗、系统缩放／混合 DPI 和手动可用性仍需单独实测；托管 runner 和合成测试不能替代，自动化通过也不将这些物理设备项目标记完成。
