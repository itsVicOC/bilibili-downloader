# 窗口关闭与后台运行交互调研

调研日期：2026-10-20。检查了软件公开实现、官方帮助与视觉示例；以下引用不表示已在本机安装或实测其他软件。

| 参考 | 观察 | BiliFlow 的处理 |
| --- | --- | --- |
| [Apple：退出 Mac 上的 App](https://support.apple.com/en-euro/guide/mac-help/mchl834d18c2/27/mac/27) | 关闭窗口后应用仍在 Dock；菜单与 Command-Q 用于退出 | 红色按钮 / ⌘W 隐藏主窗口，Dock 恢复；明确退出走收尾 |
| [qBittorrent 窗口实现](https://github.com/qbittorrent/qBittorrent/blob/master/src/gui/mainwindow.cpp)、[设置界面](https://github.com/qbittorrent/qBittorrent/blob/master/src/gui/optionsdialog.ui) | macOS 关闭与明确退出分离；其他平台判断托盘可用性；关闭到托盘和有任务时退出确认是不同偏好 | Windows 默认询问，可记住选择；记住退出仍保留活动任务确认 |
| [Teams 官方帮助](https://support.microsoft.com/en-us/teams/notifications-settings/take-quick-actions-in-microsoft-teams) | 可通过托盘右键菜单明确退出；官方截图按任务分组显示快捷入口 | 托盘保留少量直接入口，退出放在分隔线后 |
| [Motrix 更新记录](https://github.com/agalwood/Motrix/blob/main/docs/release-notes/2.0.0-beta.19.md) | 曾修复托盘关闭策略阻止更新交接的问题 | 更新重启显式进入退出流程，不受托盘偏好影响 |
| [Windows 对话框指南](https://learn.microsoft.com/en-us/windows/win32/uxguide/win-dialog-box)、[命令链接指南](https://learn.microsoft.com/en-us/windows/win32/uxguide/ctrl-command-links) | 用具体动词区分选择；默认安全动作；有明确取消入口；简单选择优先普通按钮 | 使用三个动作按钮与简短后果说明，Enter 默认后台运行，Esc 取消；记住选择默认关闭 |

Windows 指南为旧版系统编写，因此只借鉴交互、文字与布局原则，不照搬其窗口皮肤。视觉检查包括 Teams 官方帮助截图、Windows 官方对话框示例与项目已有设置页；BiliFlow 延续原生窗口边框、24 逻辑像素内边距、现有标题字体与星河 / 晴海深浅主题。后台运行为主色动作，退出为低强调危险动作，取消为次要动作；键盘焦点明确显示。

技术依据：[Qt 托盘 API](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html) 提供可用性检测、恢复信号和上下文菜单；[Qt Cocoa 应用委托](https://github.com/qt/qtbase/blob/6.11/src/plugins/platforms/cocoa/qcocoaapplicationdelegate.mm) 将 Dock 重新打开请求传递为强制应用激活事件，包括应用已经处于激活状态时。实现通过应用级事件过滤统一恢复和退出，不增加原生桥接依赖。

验证包含独立生命周期测试、原有桌面与更新回归、两套主题和不同缩放下的离屏截图。离屏测试不能证明真实 Dock / Windows 通知区域行为；平台原生实测结果应与自动化结果分别记录。

## 本次验证记录

- 生命周期测试覆盖后台线程保留、设置草稿、偏好持久化与失败、托盘不可用、退出确认、异步收尾、更新重启，以及真实事件循环中的子进程退出。
- macOS Cocoa 后端通过 8 项检查，其中 4 项使用真实子进程验证窗口隐藏后通过明确退出 / 更新重启结束。窗口关闭由 Qt 调用触发，Dock 重新打开使用应用激活事件模拟；未宣称人工点击 Dock 的验收。
- `images/lifecycle/1`、`1.5`、`2` 各含 28 张离屏截图，分别使用 DPR 1 / 1.5 / 2；`native-macos` 包含 28 张 Cocoa 原生后端截图。每组的 `rendering-profile.json` 记录后端、缩放、DPI 和 Qt 版本；图片统一为逻辑像素，便于对比。
- Windows 分支通过注入平台和托盘替身验证，100% / 150% / 200% 缩放截图在 macOS 离屏后端生成。本机没有 Windows 桌面，真实通知区域、Explorer 重启后的图标恢复、托盘点击与 Alt+F4 尚需 Windows 机器验收。

可复现命令：`QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_lifecycle.py`；截图使用 `python scripts/capture_docs_screenshots.py --lifecycle-only --output-dir docs/images/lifecycle/1`，通过 `QT_SCALE_FACTOR=1.5` 或 `2` 改变缩放，macOS 可添加 `--native` 检查 Cocoa 渲染。
