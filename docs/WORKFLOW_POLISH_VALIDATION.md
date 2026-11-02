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

完整截图矩阵在 `build/workflow-polish/native/{star_trail,bilibili_blue}/`：两套配色、深浅模式、900×640／1120×760／1320×860，包含配置、批量、结果、文件及长标题，附加分 P、字段、补全、零选择、离线、目录映射、重试、无匹配与已选视图。GitHub 对应原生附件保留相同矩阵。

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

新增回归见 `tests/test_workflow_polish.py`（35 项，含 15 个字段插入参数）；更新旧测试以反映已确认的跨筛选保留规则。数据库结构、原媒体签名及复用规则保持兼容，选择状态仅存当前会话。

## 本地验证

- macOS 原生 Cocoa 用户流程测试：**117 项通过**。源于最后一次两配色截图后的独立原生测试步骤。
- 完整离屏回归：**1,237 项通过、6 项平台专项跳过**；4 条已有 Qt 弃用警告。该轮包含空结果恢复交互；之后另作目录预览错误保留、批量配置摘要的定向回归，最终源码以 GitHub 全量结果为准。
- Ruff、编译与 `git diff --check` 通过。
- 原生 Tab／Space／Enter、焦点返回、弹窗边界、取消、长标题与两套深浅主题已覆盖自动化及截图；真实中文输入法候选窗、系统缩放／混合 DPI、用户设备上的手动键盘与可用性检查继续单独记录。

## 配对性能基准

同一台机器交替运行基线和改后各三次；每轮使用 1,000 个任务、10,000 条文件记录及临时一字节媒体，仅反映数据库／文件系统调用／界面开销，不代表真实视频吞吐。检查在锁外执行，最多 500 个资产分批读取，每 100 项或 250ms 提交；旧路径／状态／签名不匹配的结果不覆盖新记录，取消保留已检查结果。

本地 macOS Python 3.11.15 工作区（提交前）初次三轮结果：

| 指标 | 中位结果 | 三轮中最大值／门槛 |
|---|---:|---:|
| 万条快速检查 | 基线 5,458.8ms → 892.4ms，降低 83.65% | Windows 降低至少 50% 待 runner 实测 |
| 文件搜索 P95 | 31.9ms | 38.4ms／300ms |
| 文件勾选／清空 P95 | 114.0ms | 132.1ms／300ms |
| 后台稳态心跳最大间隔 | 81.4ms | 82.7ms／250ms |
| 初次加载 | 656.7ms | 665.7ms／2,000ms |
| 结束刷新 | 311.2ms | 342.8ms／2,000ms |
| 取消反馈／结束 | 0.0ms／511.6ms | 0.0ms／524.2ms（保留已完成）／1,000ms |

稳态心跳只计算后台检查运行中，初次加载与结束刷新另设门槛；原始全程心跳仍输出供诊断。自动门槛逐轮检查上述时延，不以三轮中位数掩盖最慢轮；Windows 检查改进幅度按三轮中位数比较。原始 JSON 在 `build/workflow-polish/paired-local/`；GitHub 独立性能矩阵使用 Windows／macOS Python 3.12 同 runner 三次配对并上传全部 JSON。

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

本轮待推送后补录精确源码 SHA、CI、Windows/macOS 配对性能及 `publish=false` 打包链接。原生测试、截图、性能为独立步骤；正式验收不得沿用前轮绿色状态冒充本轮结果。构建 full/lite、安装、升级恢复、备份回滚和工具链继续沿用既有工作流。

用户设备的全新安装／跨版本升级、长时双路直播（至少八小时）、真实断网／磁盘满／拔盘／休眠／强退与混合 DPI 仍需单独实测，托管 runner 和合成测试不能替代。所有自动化通过后，本轮也不将这些物理设备项目标记完成。
