# 文案与组件精修验证

2026-11-09，当前开发分支。此记录不新增发行版本，也不代表已发布安装包。

本页保留第一轮验证。后续页面布局、分组和温暖文案已按[第二轮重做](UI_WARM_REDESIGN.md)调整，当前界面以该记录为准。

## 改动与兼容

- 下载、批量导入、直播、任务、设置、账号与辅助弹窗只缩短措辞；原有提示位置、操作范围、数量、生效时机及文件保留规则继续展示。工具提示和无障碍描述同步更新，完整技术诊断、日志及更新说明保留。
- 输入框、下拉和数字控件采用均匀细边框，错误色在悬停和聚焦时保持；次要按钮使用轻描边。卡片内容、表头、菜单和选中状态使用更克制的底色，主按钮继续使用品牌色。
- 使用现有 `ThemePalette`、QSS 与 Qt 绘制组件，不引入 React、Tailwind 或 WebView。公共业务接口、配置字段、主题标识、任务数据和下载行为保持兼容。
- 入队按钮根据实际字体预留常用数量文案宽度；大数量仍由既有响应式操作栏处理，保留主操作与溢出菜单。背景玻璃缓存、可读性规则和动效时长沿用既有实现。

## 截图与人工复核

[打开前后对照](images/ui-concise/index.html)：8 组同条件对照，覆盖下载、批量、设置、直播、任务和 Cookie 登录；另有内置／自定义背景、长标题与路径、解析失败和 Cocoa 原生示例。README 与用户指南引用的 7 张主要截图已更新。

前后对照使用同一 offscreen 后端、同一演示数据和窗口尺寸，避免把平台字体差异误认为样式变化。原生示例单独列出：macOS、Qt 6.11.2、Cocoa、72 DPI、Retina 2×、PingFang SC，正文为 14 个逻辑像素；完整参数和来源见[渲染记录](images/ui-concise/rendering-profile.json)。

本次人工复核了星河浅色宽窗口、晴海深色最小窗口、直播设置、长标题与路径，以及内置图片背景的空状态。确认文字、勾选项、固定底栏和操作按钮可辨识；普通控件与图片背景上的阅读表面保持一致。完整矩阵覆盖星河／晴海 × 深浅模式 × 900×640／1120×760／1320×860；长内容与异常状态另有 60 张截图，内置／自定义背景另有 72 张截图。

原生 Qt 截图由 `QWidget.grab()` 生成，不包含系统合成的 macOS 窗口按钮。本轮没有 Windows 桌面环境，Windows 字体、分数缩放、Snap 与混合 DPI 行为仍需对应平台验证；不以 macOS 或 offscreen 结果替代。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 完整 offscreen 回归 | 1346 项通过，6 项跳过，含 1 项文案断言更新后的复跑 |
| Cocoa 原生专项 | 168 项通过，含同一项文案断言更新后的复跑 |
| 工作区底栏与字体放大检查 | 48 项通过，覆盖三种尺寸、两套配色和深浅模式，以及大数量和 125%／150% 字体 |
| 控件绘制与校验状态 | 检查四边实际像素一致、聚焦／悬停时错误色保留，以及几何尺寸稳定 |
| 截图矩阵 | offscreen／Cocoa 各 12 组工作区组合；60 组长内容／异常状态无横向滚动，实际尺寸符合请求 |
| Ruff、compileall、git diff --check | 全部通过 |

测试日志保存在 `build/ui-concise/`。全量回归末项仍使用执行前载入的旧无障碍文案断言，更新为「已选，保存设置后应用」后，`pytest --lf` 复跑通过；原生专项的对应单项也已复跑通过。以上数字按完整运行与复跑结果合计，未将原始失败日志记为一次全绿运行。其余检查没有待处理失败；日志中的 Qt `setActiveWindow` 弃用提示来自既有测试调用。

## 复现

在仓库根目录使用项目虚拟环境：

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=cocoa .venv/bin/python -m pytest -q tests/test_fluent_design.py tests/test_workspaces.py tests/test_ui_refresh.py tests/test_ui_feedback.py
.venv/bin/ruff check bilibili_downloader tests packaging_hooks scripts
.venv/bin/python -m compileall -q bilibili_downloader tests scripts
git diff --check
.venv/bin/python -m scripts.capture_docs_screenshots --ui-refresh-only --output-dir build/ui-concise/after/ui
.venv/bin/python -m scripts.capture_docs_screenshots --glass-only --output-dir build/ui-concise/after/glass
.venv/bin/python -m scripts.capture_docs_screenshots --refinement-only --output-dir build/ui-concise/after/refinement
.venv/bin/python -m scripts.capture_docs_screenshots --ui-refresh-only --native --physical-pixels --output-dir build/ui-concise/native/ui
```

原生命令需要可连接 WindowServer 的 macOS 桌面会话。截图只使用离线演示数据、临时配置与临时任务库，不读取真实 Cookie 或用户下载记录。前后对照中的「调整前」来自改动前的相同截图脚本，已随文档保存，不以修改后的代码重新生成。
