# Fluent 交互、录制历史与剪贴板验收

2026-10-23，分支 `codex/fluent-design-polish`，基线 `1ebdb63`，实现及测试提交 `4ff35c7`。本轮功能随 `0.8.9b4` 发布，保留已有版本标签；以下代码与截图验收完成于版本更新前，发布安装包的检查单独记录在[构建与发布](BUILDING.md)。

## 实现结果

| 区域 | 结果 |
| --- | --- |
| 下载确认卡 | 单个／批量共用自然宽度路径，修改目录紧随其后，间隔 8px；卡片 72px、按钮 32px 保持稳定；长路径选择、复制与完整提示保留 |
| 整行悬停 | 仅任务中心三个页签启用；跨列、进度、按钮及树形缩进统一中性背景；选中优先；菜单保留所属行；滚动、筛选、删除和刷新后重新命中，不修改模型与选择 |
| 录制历史 | 底部更多／右键按整场移除，仅删除 DB 记录；控制器与仓储检查最新状态，锁与事务保护删除，防止同运行旧快照写回；独立的一次撤销恢复完整记录，不覆盖冲突 ID |
| 剪贴板 | 默认开启，150ms 单次防抖；启动、前台变化与显示恢复时检查当前文本；确认前无网络、无来源替换；支持分享文案和多来源，单个／批量／短链沿用既有异步流程 |
| 设置与文档 | 下载设置增加来源识别开关，遵循草稿、保存及撤销；背景下载预览同步路径动作位置；用户指南说明记录移除范围与确认规则 |

删除仅操作数据库，不删除原始片段、MP4、manifest、目录或直播订阅。目标仍在录制、重连、收尾、等待或执行导出时禁止移除。失败不丢失记录；撤销失败保留快照可重试。下载和历史撤销分别保存，仅本次运行有效。

剪贴板提示为右上方浮层，最大 480px、距两侧至少 16px，不挤压布局、不抢焦点、不自动消失。现有输入变化会同步更新「替换并解析」；确认使用当前展示快照，不重新读取剪贴板。忙碌时保留最新候选但不排队启动；取消离开设置不替换内容。后台、隐藏、最小化、模态窗口、菜单、退出与更新安装期间暂停；图片、文件、直播、选区及超过 64Ki 字符文本不自动识别。

只保存内存中的去重指纹，不持久化或记录剪贴板原文。桌面入口显式启用监控；普通测试和截图默认关闭，专项通过注入可控剪贴板验证。配置增加兼容布尔字段 `clipboard_monitor_enabled=True`，旧配置缺失时默认开启；CLI、业务接口调用方式、数据库结构及窗口状态文件保持兼容。

## 截图与视觉复核

| 场景 | 修改前 | 修改后 |
| --- | --- | --- |
| 下载目录 · 浅色 · 1120 | [查看](images/fluent-v5/download-before.png) | [查看](images/fluent-v5/download-after.png) |
| 任务中心 · 深色 · 900 | [查看](images/fluent-v5/tasks-before.png) | [整行悬停](images/fluent-v5/tasks-hover-dark.png) |
| 历史管理 · 深色 | — | [菜单](images/fluent-v5/history-menu-dark.png) · [移除](images/fluent-v5/history-removed-dark.png) · [撤销](images/fluent-v5/history-restored-dark.png) |
| 剪贴板 · 原生 macOS | — | [浅色](images/fluent-v5/clipboard-light.png) · [深色](images/fluent-v5/clipboard-dark.png) · [批量](images/fluent-v5/clipboard-batch-dark.png) |

截图使用隔离离线数据，窗口记忆关闭，专项注入演示剪贴板，不启动网络解析和录制。矩阵覆盖两套配色、深浅模式、900×640／1120×760／1320×860，以及内置和高对比背景。检查默认、悬停、选中悬停、树形子条目、菜单、移除／撤销、单个／批量确认和解析忙碌状态。可浏览的完整索引与原始日志位于本地 `build/fluent-v5/index.html`。当前包含修改前 213 张、修改后离屏 405 张、本机 Cocoa 原生 403 张、Windows CI 原生 1063 张、macOS CI 原生 1063 张、四档标题栏 336 张及对比别名 8 张，共 3491 张，6998 个本地图片及跳转链接均有效。悬停对比另从 `1ebdb63` 与当前实现分别捕获相同数据、相同状态，展示单格与整行的差异。主页下载、批量、任务和设置截图同步使用本轮 Cocoa 原生捕获。

最终 CI 的 Windows 实图：[下载目录](images/fluent-v5/windows-download-light-1120.png) · [整行悬停](images/fluent-v5/windows-tasks-hover-dark-1120.png) · [历史移除](images/fluent-v5/windows-history-menu-light-900.png) · [剪贴板确认](images/fluent-v5/windows-clipboard-dark-900.png)。两平台各 12 组主页面配置和 12 组交互配置均完成，主页面实际尺寸与请求尺寸一致。人工复核代表性页面和关键状态，其余截图与几何／交互断言一同交付。CI 使用 Qt 6.11.1，本机使用 Qt 6.11.2；Cocoa 为 72 逻辑 DPI／2 倍像素，Windows 主矩阵为 96 逻辑 DPI／1 倍像素。

## 测试与平台范围

本机 macOS arm64，Python 3.11.15，Qt 6.11.2。

| 检查 | 结果 |
| --- | --- |
| 完整离屏 pytest | 1124 通过，6 项平台相关跳过；4 条既有 Qt 测试辅助接口弃用警告 |
| 新增功能专项 | 来源提取、前台读取限制、确认路由、设置草稿、整行绘制、目录选区、历史事务与撤销；63 项通过 |
| Cocoa 原生回归 | 最终代码 126 通过，1 项模拟桌面相关跳过，4 条既有弃用警告 |
| Ruff、编译、diff | 通过 |
| Windows CI Python 3.12 | 原生专项 128 通过、1 跳过；全量 1115 通过、15 项平台相关跳过 |
| macOS CI Python 3.12 | 原生专项 128 通过、1 跳过；全量 1116 通过、14 项平台相关跳过 |
| Linux CI Python 3.11／3.12 | 两版全量均 1116 通过、14 项平台相关跳过 |
| Windows 100%／125%／150%／200% Qt 缩放 | 原生窗口按钮、鼠标输入与几何检查通过，336 张截图 |
| 完整 CI | [39966881345](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39966881345)，最终 15／15 项通过，代码 `4ff35c7` |

最终运行中 Linux 录制器的 FFmpeg 依赖安装遇到下载停滞，保留其他 14 项结果后单独换 runner 重跑该作业；第二次通过。原生录制器、更新器及依赖审计均通过，此处为功能代码 CI，beta 4 安装包另由标签发布流水线构建与验证。

原生剪贴板检查使用真实平台剪贴板，保存并恢复全部原 MIME 格式，验证启动前文本、主窗口激活、隐藏后复制并恢复、确认仅启动一次。注入测试另外断言后台零读取、确认前零解析、输入不变、忽略去重、短链路由、设置草稿与空闲后不持续读取。原生菜单通过 `aboutToShow/aboutToHide` 暂停和恢复，覆盖 Cocoa 没有 `activePopupWidget` 的情况，并有独立信号检查。尚未将原生跨应用切换、系统级托盘点击、Windows 11 用户实机、实际 Snap、系统 DPI 和混合 DPI 多屏标记通过。

原生输入测试串行运行，宿主显式激活并等待焦点后再进行选择与鼠标检查；保留真实选区像素和整行颜色断言。Qt 用例结束后释放 Python 包装器并排空延迟删除，避免跨用例样式遍历受到遗留对象影响；超长文本使用短测试 ID，遵守 Windows 环境变量长度上限。删除竞争测试使用第二个数据库连接，确认状态读取到删除提交期间阻止其他写入；仓储通过 `BEGIN IMMEDIATE` 在读取前取得写事务。

原有下载、批量取消与重试、任务范围和撤销、登录、Markdown 更新、窗口记忆与退出回归继续执行。两套配色的深浅模式中，新悬停底色上的正文、说明、活动及三类语义文字最低对比度为 5.03:1；选区、玻璃共享缓存及动画收敛检查保留。已确认粉色主按钮配色例外沿用[第三轮记录](FLUENT_V3_VALIDATION.md#对比度性能与平台边界)。本轮没有修改背景素材和窗口按钮绘制规则。

## 复现

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests scripts packaging_hooks
python -m compileall -q bilibili_downloader tests scripts
python -m scripts.capture_docs_screenshots --ui-refresh-only --output-dir build/fluent-v5/after/ui-refresh
python -m scripts.capture_docs_screenshots --interactions-only --output-dir build/fluent-v5/after/interactions
python -m scripts.build_fluent_review --root build/fluent-v5 --title 'BiliFlow Fluent 交互与剪贴板复核'
```

原生截图追加 `--native --physical-pixels`。`tests/test_clipboard_native.py` 仅在 Cocoa／Windows 桌面执行，普通测试始终隔离剪贴板；Windows／macOS CI 已加入原生专项与交互矩阵。
