# 第二轮重做：简洁，也有温度

2026-11-10，当前开发分支；不新增发行版本、不更改安装位置。本轮在第一轮边框与文案改动上继续调整，允许重排内容与收起低频配置。

## 页面与文案

- 下载入口使用「喜欢的这一集，留在身边。」；解析后欢迎句退场，作品封面和标题成为视觉中心。单个与批量保留两个页签，右侧或下方共用一份下载设置。
- 分 P、输出类型、画质和附件直接展示，音频模式直接显示音质。视频编码、视频音质、显示比例与回退策略位于「高级设置」，收起后保留编码／音质、4:3 或严格匹配摘要。完整配置入口位于高级区。
- 可用宽度 920px 起使用侧栏布局，配置栏基准宽度 336px，并按实际字体和附件标签的最小宽度增宽；窄屏上下排列，固定底栏保留数量、目录和入队按钮。
- 批量页可直接改设置，编辑来源时不因布局重算而自动收起。列表仍区分已选作品与实际任务数，保留跨筛选选择、失效提示和逐项规格确认。
- 设置改为连续表单分组；四像素外侧留白继续透出固定背景，组内沿用阅读材质。直播详情突出时长、大小和速度，录制偏好按需展开；任务以列表、筛选和选择后的详情为主。
- 空状态恢复「收藏，从这里开始。」「等待下一场星光」「留住每一场相遇」。正常保存完成使用「已存好，留着慢慢看。」；附件缺失、规格回退和核验异常显示明确问题。小流的五个时段问候及十二套动作保留。

## 实现与兼容

组件外观参考 [shadcn/ui 的语义主题设计](https://ui.shadcn.com/docs/theming)，通过现有 `ThemePalette`、共享 QSS 和 Qt 绘制组件统一实现：安静的表面、均匀边框、品牌色主操作、淡色选中状态，以及明确的错误与键盘焦点。

`DownloadConfiguration` 组织同一组真实控件，主窗口、批量入队与完整配置继续读取原有取值链路。视频／音频切换仅移动同一个音质控件，折叠与布局状态只存在本次窗口会话，不新增配置字段，也不改业务 API、任务数据、录制和下载服务。

`SourceTabs` 根据当前页的尺寸与宽高关系计算布局，避免隐藏的批量结果为单个空状态保留大片空白。附件行根据实际字体计算所需宽度；高级字段支持展开、标记错误、聚焦和滚动定位。隐藏的字段从网格排列中移除，保留原控件与值；键盘顺序覆盖编码、音质、比例和回退策略。

单个与批量入队共用配置校验，先检查当前输出模式所需的普通和高级字段，再进入确认与入队。校验失败时自动展开、滚动并聚焦实际下拉框；修改后清除错误，重新解析成功后同步清除旧提示。音频模式忽略未启用的视频画质、编码和比例。

`ActionBarStack` 只按当前操作栏计算高度，避免 Cocoa 下隐藏操作栏的旧尺寸造成底栏偏移。键盘顺序跟随可见且可用的控件，覆盖高级展开按钮、配置复核和固定底栏，不依赖系统是否允许 Tab 访问全部按钮。

设置草稿、取消、撤销、保存失败与离开提示保持原有语义。背景绘制继续共用缓存和可读性保护，外观预览同步反映共享设置、作品区与连续表单。

## 实际文案示例

| 场景 | 当前文案 |
| --- | --- |
| 下载入口 | 喜欢的这一集，留在身边。 |
| 下载队列为空 | 收藏，从这里开始。 |
| 尚未添加直播间 | 等待下一场星光 |
| 录制历史为空 | 留住每一场相遇 |
| 媒体成功保存 | 已存好，留着慢慢看。 |
| 两个任务入队 | 加入队列（2 项） |
| 附件缺失 | 媒体已保存，N 项附件待补全。 |
| 高级字段未选 | 请选择视频编码；列表为空时请重新解析。 |

## 视觉对照

[打开前后对照与关键状态](images/ui-warm/index.html)。对照使用相同离线演示数据、Qt offscreen 后端和窗口尺寸；原生 Cocoa／Retina 示例另列。主要文档截图同步为当前开发界面，历史验证目录继续保留。

对照包含 7 组前后页面与 13 个关键示例，补充展示选中任务后的详情和隐藏高级字段的错误定位。[渲染记录](images/ui-warm/rendering-profile.json)保存来源、实际尺寸、字体、DPI、设备像素比与后端，便于区分设计变化和平台差异。

本轮复核覆盖两套配色、深浅模式、三种窗口尺寸、内置与自定义背景，以及空状态、预配置、解析后、展开高级项和音频模式。检查了欢迎句、共享配置摘要、大封面、批量列表、错误状态、长标题／路径、固定底栏及背景可读性。

Windows 原生窗口、字体、分数缩放、Snap 与混合 DPI 仍需对应平台验证；本机的 offscreen 和 Cocoa 结果不替代 Windows 验收。原生 Qt 控件截图不包含系统合成的窗口按钮。

## 最终验证结果

以下来自最终版本的完整运行；新增的 21 项交互回归已包含在总数中。

| 检查 | 实际结果 |
| --- | --- |
| 完整 offscreen 回归 | 1367 项通过，6 项跳过；330.30 秒 |
| macOS Cocoa 原生专项 | 204 项通过；117.59 秒 |
| 共享配置与错误恢复 | 单个／批量、视频／音频切换、隐藏字段定位、修正后重试、重新解析清除旧错误均通过 |
| 工作区截图 | offscreen／Cocoa 各 307 张，覆盖两套配色、深浅模式及三种尺寸；12 组温暖状态检查均无横向溢出 |
| 背景材质 | offscreen 72 张矩阵截图，另有 5 张示例；覆盖内置与自定义背景 |
| 长内容与异常状态 | 60 张截图，实际尺寸符合请求，无横向溢出；另检查 125%／150% 字体与固定底栏 |
| 重点状态示例 | offscreen／Cocoa 分别复现任务详情和入队校验失败，确认实际控件聚焦、自动展开和主操作可见 |
| Ruff、compileall、git diff --check | 全部通过 |

本机系统为 macOS 27.0.1（26A434），Qt 6.11.2、PingFang SC；Cocoa 为 72 逻辑 DPI、Retina 2×，offscreen 为 96 DPI、1×。正文为 14 个逻辑像素。测试仍有既有 `QApplication.setActiveWindow` 弃用提示，没有待处理失败。

[结构化验证记录](images/ui-warm/validation.json)保存最终结果、命令与平台范围；原始日志位于 `build/ui-warm/pytest-final-complete.log` 和 `build/ui-warm/pytest-native-final-complete.log`。

## 复现

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=cocoa .venv/bin/python -m pytest -q tests/test_warm_workspaces.py tests/test_workspaces.py tests/test_ui_refresh.py tests/test_ui_feedback.py tests/test_fluent_refinement.py tests/test_fluent_design.py
.venv/bin/ruff check bilibili_downloader tests packaging_hooks scripts
.venv/bin/python -m compileall -q bilibili_downloader tests scripts
git diff --check
.venv/bin/python -m scripts.capture_docs_screenshots --warm-only --output-dir build/ui-warm/final/ui
.venv/bin/python -m scripts.capture_docs_screenshots --warm-details-only --output-dir build/ui-warm/final/details
.venv/bin/python -m scripts.capture_docs_screenshots --glass-only --output-dir build/ui-warm/final/glass
.venv/bin/python -m scripts.capture_docs_screenshots --refinement-only --output-dir build/ui-warm/final/refinement
.venv/bin/python -m scripts.capture_docs_screenshots --warm-only --native --physical-pixels --output-dir build/ui-warm/native/final
.venv/bin/python -m scripts.capture_docs_screenshots --warm-details-only --native --physical-pixels --output-dir build/ui-warm/native/details
```

原生命令需要 macOS 桌面会话与 WindowServer 访问权限。所有截图使用临时演示配置、任务库、媒体和二维码，不读取真实账号凭据或用户下载记录。「调整前」保存在第一轮完成后的截图中，不用修改后的代码重新生成。
