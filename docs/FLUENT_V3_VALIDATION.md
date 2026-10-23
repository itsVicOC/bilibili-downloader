# Fluent 第三轮精修验收

2026-10-23，开发分支 `codex/fluent-design-polish`。本轮基于 `98725fe` 保存修改前截图，代码提交为 `913bd8a`；不修改 `0.8.9b2` 版本号和已有发布标签。效果图用于确认方向，实际界面保留完整字段及小窗口滚动。

发布归属：本轮与[第四轮精修](FLUENT_V4_VALIDATION.md)已随 `v0.8.9b3` 发布；安装包验证见[构建与发布](BUILDING.md#089-beta-3-发布检查2026-10-23)。下文保留各轮原始验收范围。

## 实现与前后对比

| 区域 | 本轮实现 |
| --- | --- |
| 单个下载 | 约 68px 已解析来源区、横向作品摘要、两行标题、按实际可用宽度重排的规格与附加内容；仅音频、分 P、字幕依赖和结果失效保护保留 |
| 附加内容 | 下载与设置共用 40px 紧凑行，显式勾选和格式标签；字幕子选项缩进排列 |
| 设置 | 14px 字段标签、固定 56px 保存栏；草稿、撤销、字段定位、保存失败及即时主题切换语义保留 |
| 任务中心 | 轻表头和行分隔、低频操作进入更多菜单、作用范围与数量保留、工具栏可换行；录制与历史数字列对齐 |
| 全界面 | 普通内容、控件、确认区和浮层分别使用共享参数；账号、登录、背景图库、直播设置、详情、错误、更新与关闭弹窗同步应用 |

先前使用内置 imagegen 生成的[概念图](images/fluent-v3/concept.png)用于布局参考；以下为未修改内容的实际 Qt 截图。前后两列均为离屏后端，原生截图另行保存。

| 场景 | 精修前 | 精修后 |
| --- | --- | --- |
| 下载 · 浅色 · 1320×860 | [查看](images/fluent-v3/download-before.png) | [查看](images/fluent-v3/download-after.png) |
| 设置 · 深色 · 900×640 | [查看](images/fluent-v3/settings-before.png) | [查看](images/fluent-v3/settings-after.png) |
| 任务 · 深色 · 900×640 | [查看](images/fluent-v3/tasks-before.png) | [查看](images/fluent-v3/tasks-after.png) |

完整本地索引为 `build/fluent-v3/index.html`，可筛选主题、模式、尺寸、背景和状态。`before/` 与 `after/` 为离屏，`native/` 为 macOS Cocoa 原生物理像素，`windows/` 为本轮 Windows CI 原生证据。截图中的账号、任务、路径及更新版本均为隔离演示数据。

当前索引共 3248 张图片，包含修改前 454 张、修改后离屏 725 张、macOS 原生 861 张、Windows 原生 871 张、四档标题栏 336 张及概念图 1 张。Windows 实际截图：[下载页](images/fluent-v3/windows-download-light-1320.png) · [设置页](images/fluent-v3/windows-settings-dark-900.png) · [任务中心](images/fluent-v3/windows-tasks-dark-900.png)。两平台的 12 组主题／模式／尺寸检查及各 60 个新增状态均保持请求尺寸，新增状态未出现横向滚动。

## 本机与自动验证

环境：macOS arm64，Python 3.11.15，Qt 6.11.2。

| 检查 | 结果 |
| --- | --- |
| 完整离屏 pytest | 1041 通过，5 项平台相关跳过 |
| Cocoa 原生布局、焦点、Markdown 与生命周期专项 | 114 通过 |
| macOS CI Python 3.12 | 原生专项 69 通过；全量 1033 通过、13 项按条件跳过 |
| Windows CI Python 3.12 | 原生专项 69 通过；全量 1032 通过、14 项按条件跳过 |
| Ruff、编译与 diff | 通过 |
| 新布局专项 | 10 项，覆盖完整可见、重排保值、两行 Unicode 标题、音频模式、键盘顺序、保存栏、任务 ID、操作范围与换行 |

标准窗口检查全部下载控件完整可见；900×640 保留单一外层纵向滚动与固定操作区。矩阵覆盖两套配色 × 深浅模式 × 三种尺寸，以及无图、内置背景、自定义背景、长内容、失败、未保存草稿和任务筛选。已有空状态、批量部分失败、登录、背景、保存失败、更新和生命周期测试继续执行。

[CI 39912318295](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39912318295) 对同一代码提交执行全平台测试、原生页面及新增状态截图，以及 Windows 100%／125%／150%／200% Qt 缩放窗口按钮专项，**15／15 项全部通过**。包含双平台冻结更新器、三平台录制引擎与依赖审计；平台相关跳过项与对应原生验证分别记录。

## 对比度、性能与平台边界

普通正文、辅助说明和状态文字继续检查 4.5:1，新增表头表面纳入对比度测试。用户已确认的粉底白字保持原值，以下为默认／悬停／按下的计算值，未作为普通正文合规通过项：

| 配色 | 默认 | 悬停 | 按下 |
| --- | --- | --- | --- |
| 星河浅色 | 2.76:1 | 2.18:1 | 3.64:1 |
| 星河深色 | 4.05:1 | 3.15:1 | 5.97:1 |
| 晴海浅／深色 | 4.51:1 | 5.08:1 | 5.99:1 |

保留共享玻璃缓存及现有动画生命周期测试；重排不重新创建业务控件，不新增轮询或逐帧样式更新。十二景原图、运行时背景、缩略图与引用未修改，运行时 24 个资源文件仍为 8,130,355 字节（7.75 MiB）。

Windows 的托管原生结果与用户实机分别记录。Windows 11、100%、单屏实机，实际 Snap 浮层、系统 DPI 切换及混合 DPI 多屏仍未计为通过；macOS 原生窗口、字体和生命周期使用 Cocoa 实际运行。此次未生成或发布新安装包。

## 复现

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
python -m compileall -q bilibili_downloader tests scripts
python -m scripts.capture_docs_screenshots --output-dir build/fluent-v3/after/star_trail
python -m scripts.capture_docs_screenshots --color-theme bilibili_blue --output-dir build/fluent-v3/after/bilibili_blue
python -m scripts.capture_docs_screenshots --refinement-only --output-dir build/fluent-v3/after/refinement
python -m scripts.capture_docs_screenshots --native --physical-pixels --output-dir build/fluent-v3/native/star_trail
python -m scripts.build_fluent_review --root build/fluent-v3
```

完整视觉规范见 [Fluent Design](FLUENT_DESIGN.md)，上一轮已发布 beta 的记录见[第二轮验收](FLUENT_V2_VALIDATION.md)。
