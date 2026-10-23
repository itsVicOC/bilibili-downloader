# Fluent 全界面精修与窗口记忆验收

2026-10-23，分支 `codex/fluent-design-polish`，基线 `5419b3c`，实现提交 `89fb072`，Windows 状态适配修复 `70e00f6`，最终窗口跨屏记录 `1d31318`。精修验收时保留 `0.8.9b2` 版本号，未发布安装包；以下记录对应这一阶段。

发布归属：本轮与[第三轮精修](FLUENT_V3_VALIDATION.md)一并纳入 `v0.8.9b3` 发布源码，已有标签保留。安装包验证另见[构建与发布](BUILDING.md)。

## 实现与复核

| 区域 | 本轮结果 |
| --- | --- |
| 高度响应式 | 低于 800px 进入紧凑模式，达到 824px 恢复舒适模式；边距／卡片内边距／分组间距从 24／16／16 改为 16／12／12；字号、控件和底栏高度不缩小 |
| 下载与批量 | 紧凑封面 128×72，规格标签同行；去掉正文重复目录，底部目录支持选择、复制和修改入口；字段、字幕依赖与业务流程保留 |
| 任务与直播 | 详情突出状态、规格和路径，录制指标统一排列；移除记录的撤销同时保留在更多菜单；普通反馈进入固定状态栏，错误和警告留在原区域 |
| 五类设置 | 共享紧凑边距，工具路径合并分组，检测结果仍按工具隔离；保存栏和草稿语义保留 |
| 背景预览 | 更新横向摘要、双列规格和紧凑附加内容；预览与实际控件使用相同密度和宽度判断，不启动业务服务 |
| 弹窗 | 独立弹窗按父窗口屏幕定位，排除嵌入式设置／批量页和原生文件选择器；长诊断使用 Qt 原生可展开滚动详情，支持选择与复制 |
| 窗口记忆 | 主窗口大小、位置和最大化状态独立保存，显示器变化后限制在可用工作区；托盘和更新退出均保存，不写入设置草稿 |

普通长度下载信息在 1120×760 下完整显示规格、四项附加内容、字幕子选项和确认区。900×640 首屏显示四项核心规格与固定操作，其余由一个外层区域纵向滚动。重排保留控件实例、焦点、选区和草稿。

| 场景 | 修改前 | 修改后 |
| --- | --- | --- |
| 下载 · 浅色 · 1120×760 | [查看](images/fluent-v4/download-before.png) | [查看](images/fluent-v4/download-after.png) |
| 设置 · 深色 · 900×640 | [查看](images/fluent-v4/settings-before.png) | [查看](images/fluent-v4/settings-after.png) |
| 任务 · 深色 · 900×640 | [查看](images/fluent-v4/tasks-before.png) | [查看](images/fluent-v4/tasks-after.png) |
| 背景预览 · macOS 原生 | [查看](images/fluent-v4/gallery-before.png) | [查看](images/fluent-v4/gallery-after.png) |

主要文档截图使用 macOS Cocoa 原生捕获；前后对比使用同一离屏后端。完整本地索引为 `build/fluent-v4/index.html`，包含全部页面、关键弹窗、两套配色、深浅模式、三种尺寸、无图／内置／高对比图片，以及音频、长内容、失败、草稿和任务筛选状态。截图使用隔离的离线演示数据，窗口记忆在捕获中显式关闭。当前本地矩阵共 3658 张：修改前 725 张、修改后离屏 861 张、Cocoa 原生 865 张（含四组长诊断）、Windows 原生 871 张、四档窗口按钮 336 张；7332 个本地图片和跳转链接全部有效。

Windows CI 实际截图：[下载页](images/fluent-v4/windows-download-light-1120.png) · [设置页](images/fluent-v4/windows-settings-dark-900.png) · [任务中心](images/fluent-v4/windows-tasks-dark-900.png)。两平台各 120 张主页面截图保持请求尺寸，各 60 个新增状态检查均无意外横向滚动。新增[长诊断原生截图](images/fluent-v4/long-diagnostic-dark.png)展示有界阅读与操作可达。

## 窗口状态规则与验证

`ui-state.json` 位于用户数据目录，格式版本 1，保存正常窗口 Qt 几何、逻辑坐标矩形、屏幕标识、可用工作区和最大化状态。使用 500ms 单次计时器合并写入并原子替换；进入托盘、正常退出、更新重启和应用退出前刷新。

正常尺寸与最大化状态分别记录；最小化和隐藏不覆盖正常几何，也不会让下次启动隐藏。退出全屏时保留此前正常／最大化记录。初始显示前恢复，最大化沿用现有 Win32 原生路径。原屏幕缺失时按旧位置交集选择屏幕，无交集使用主屏幕；处理负坐标与任务栏／Dock。常规最小尺寸为 900×640，可用工作区更小时按窗框扣除后降低有效最小尺寸。

新增 20 项检查覆盖跨进程普通／最大化恢复、原生主窗口最大化及还原、最小化／隐藏、负坐标与失去屏幕、960×540 模拟工作区、损坏记录、原子写入失败、草稿隔离、更新回滚保留、布局临界值、反馈不挤压内容、嵌入式页面边距和长诊断可达性。Windows 同时检查 Win32 的 IsZoomed／IsIconic 与 Qt 标志，避免原生最大化先改变尺寸时，将过渡几何写成正常尺寸。最大化窗口跨屏移动时仍更新屏幕标识，保留原正常尺寸；这一数据规则有隔离回归测试，尚不等同于混合 DPI 多屏实机验收。普通测试不启用生产窗口记录；实际持久化测试使用临时文件。

## 测试与平台记录

本机 macOS arm64，Python 3.11.15，Qt 6.11.2。

| 检查 | 结果 |
| --- | --- |
| 完整离屏 pytest | 1061 通过，5 项平台相关跳过 |
| Cocoa 原生窗口、布局、焦点、Markdown 和生命周期专项 | 120 通过，1 项模拟负坐标桌面检查跳过；该场景在离屏后端通过 |
| Ruff、编译、diff 检查 | 通过 |
| macOS CI Python 3.12 | 原生专项 87 通过、1 项模拟桌面跳过；全量 1053 通过、13 项平台相关跳过 |
| Windows CI Python 3.12 | 原生专项 87 通过、1 项模拟桌面跳过；全量 1052 通过、14 项平台相关跳过 |
| Windows 100%／125%／150%／200% Qt 缩放 | 四档原生窗口按钮与真实鼠标输入检查通过，336 张桌面截图 |
| 完整 CI | [39926874047](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39926874047)，15／15 项全部通过，代码提交 `1d31318` |

合成键盘测试显式激活 Qt 测试窗口，避免用户前台应用影响断言；当前 Qt 对这一测试辅助接口产生 4 条弃用警告，运行时代码未使用它。Cocoa 测试需访问原生输入和剪贴板服务，沙盒内服务连接失败的运行不计入结果；最终原生记录来自允许访问桌面服务后的运行。

保留原有正文、说明、状态及文本选区对比度检查。用户确认的粉底白字配色不变，粉色主按钮的对比度例外与[第三轮记录](FLUENT_V3_VALIDATION.md#对比度性能与平台边界)一致，不作为普通文字 4.5:1 达标项。共享玻璃缓存、动画收敛和滚动回归继续执行；窗口记忆使用单次计时器，停止后不轮询。

十二景原图与运行时资源未修改：24 个背景／缩略图文件合计 8,130,355 字节（7.75 MiB），保留所有 ID 和路径。公共 API、CLI、业务设置和数据库结构未修改；窗口文件不参与业务数据回滚。

Windows CI 的原生窗口、鼠标输入及四档 Qt 缩放与用户实机分别记录。Windows 11、100%、单屏实机，实际 Snap 浮层、系统 DPI 切换和混合 DPI 多屏尚未获得本轮实际验证，不标记为通过。Linux 仅执行离屏自动验证，Wayland 原生绝对位置恢复未实际验证。

## 复现与截图索引

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests scripts packaging_hooks
python -m compileall -q bilibili_downloader tests scripts
python -m scripts.capture_docs_screenshots --output-dir build/fluent-v4/after/star_trail
python -m scripts.capture_docs_screenshots --color-theme bilibili_blue --output-dir build/fluent-v4/after/bilibili_blue
python -m scripts.capture_docs_screenshots --refinement-only --output-dir build/fluent-v4/after/refinement
python -m scripts.build_fluent_review --root build/fluent-v4 --title 'BiliFlow 第四轮 Fluent 精修与窗口记忆'
```

原生捕获追加 `--native --physical-pixels`；完整补充矩阵使用 `--glass-only`、`--appearance-controls-only` 和 `--ui-refresh-only`。窗口专项为 `tests/test_window_state.py` 与 `tests/test_fluent_window_polish.py`。完整结果和日志保存在 `build/fluent-v4/`。
