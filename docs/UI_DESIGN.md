# BiliFlow 视觉规范与验证

本轮将点播下载、直播录制、任务与设置统一为「星轨收藏工作台」。星轨与淡紫渐变集中在输入卡和空状态；表单、任务列表使用纯色表面。保留 BiliFlow 图标与吉祥物线索，功能入口使用统一的 SVG 线性图标。

## 页面与操作

| 入口 | 内容 | 主要操作 |
|---|---|---|
| 视频下载 / 单个解析 | 链接输入、作品资料、输出规格与归档附加项 | 开始解析、加入下载队列 |
| 视频下载 / 批量导入 | 来源输入、解析预览、作品勾选 | 解析并预览、加入下载队列 |
| 直播录制 | 房间监控列表与选中房间详情 | 添加并监控、立即开始 / 停止本场、自动监控 |
| 任务中心 / 下载队列 | 状态筛选、下载进度、行操作与完整详情 | 暂停、继续、重试、打开、删除记录 |
| 任务中心 / 当前录制 | 准备、排队、录制、重连、收尾与异常房间 | 停止本场、查看房间 |
| 任务中心 / 录制历史 | 本地时间的场次、封口片段、缺口与警告 | 打开目录 / 文件、导出 MP4 |
| 设置 / 下载 | 保存目录、目录模板、默认规格、附加项与并发 | 保存设置、撤销修改 |
| 设置 / 直播 | 新房间默认目录、分段、并发与保留空间 | 保存设置、撤销修改 |
| 设置 / 工具与存储 | FFmpeg、录制引擎及后台检测、下载缓存 | 选择路径、检查、清理缓存 |

侧栏常规宽度 208px，窗口小于 1120px 时收为 72px；最小窗口仍为 900×640。下载内容宽度不足 900px 时作品资料与输出规格上下排列；直播内容宽度不足 1000px 或页面高度不足 700px 时详情移至列表下方。上下布局使用一个主体滚动区，房间表格随内容展开，避免嵌套滚动。较小窗口需要纵向滚动查看完整表单，下载、直播和设置的主要操作固定在主体滚动区外。

页面实例持续保留，切换不会重建工作台。输入、解析结果、页签、筛选、选择与滚动位置保留；加入下载队列后仍停留在当前页。修改来源会使旧解析结果失效，提交前需重新解析。

## 主题资源

颜色与尺寸集中在 `gui/resources/styles.py`，通过单一生成式 QSS 应用。系统深浅主题同步更新 QPalette、SVG 图标与绘制组件。字体沿用平台中文字体；基准字号为标题 20pt、区块 12pt、正文 10pt、辅助 9pt，macOS 保留原有 1.15 倍字号修正，并以 96 逻辑 DPI 为预览基准补偿 Cocoa 的 72 DPI。Retina 的 2× 像素缩放由 Qt 处理，不再乘到字号上。Windows / Linux 保留系统点数字号与文字缩放行为。全局 QSS 明确指定所选字体族，确保加粗标题、表单和列表也使用同一中文字体。

### 原生显示差异分析与复核（2026-09-28）

用户提供的实机截图暴露了此前仅用 offscreen 检查的不足。原生 Cocoa 下，同样的 `11.5pt` 正文换算为 12 个逻辑像素，96 DPI offscreen 下为 15 个；原生加粗标题还回退到 `.AppleSystemUIFont`，而离线环境使用 `PingFang SC`。现在同时修正 DPI 换算与字体族，两个环境的正文都解析为 15px、页头为 31px，并均使用 `PingFang SC`。

浮层探测中，380×40 的选择框在原生样式下生成了宽 362px、向左偏 7px 且覆盖选择框的菜单。Qt 使用样式的 `SC_ComboBoxListBoxPopup` 子控件区域定位浮层（见 [Qt 实现](https://github.com/qt/qtbase/blob/6.11/src/widgets/widgets/qcombobox.cpp#L2726)）。共享组件现在按完整输入框和所在屏幕的可用区域重新定位，宽度 380px，留出 4px 间距；原有 Qt 键盘、鼠标、模型与取消流程继续使用。

以下为真实 macOS Cocoa、72 DPI、Retina 2× 渲染后按逻辑尺寸导出的截图，不使用生产账号、配置或录制服务。对应的 [渲染记录](images/native/rendering-profile.json) 包含字体解析、浮层位置、屏幕边界与遮挡检查。页签也已显式左对齐。

| 尺寸 | 深色工作台 | 浅色工作台 | 深色长菜单 | 浅色长菜单 |
|---|---|---|---|---|
| 900×640 | [查看](images/native/biliflow-platform-download-dark-900.png) | [查看](images/native/biliflow-platform-download-light-900.png) | [查看](images/native/biliflow-platform-dropdown-dark-900.png) | [查看](images/native/biliflow-platform-dropdown-light-900.png) |
| 1120×760 | [查看](images/native/biliflow-platform-download-dark-1120.png) | [查看](images/native/biliflow-platform-download-light-1120.png) | [查看](images/native/biliflow-platform-dropdown-dark-1120.png) | [查看](images/native/biliflow-platform-dropdown-light-1120.png) |
| 1320×860 | [查看](images/native/biliflow-platform-download-dark-1320.png) | [查看](images/native/biliflow-platform-download-light-1320.png) | [查看](images/native/biliflow-platform-dropdown-dark-1320.png) | [查看](images/native/biliflow-platform-dropdown-light-1320.png) |

可使用 `python scripts/capture_docs_screenshots.py --native --checks-only --output-dir docs/images/native` 重新生成原生检查。普通离线截图仍使用默认命令。原生检查额外覆盖字体族、实际像素字号、鼠标选择与关闭动画；屏幕边界回归覆盖上翻、空间不足及负坐标副屏。355 项 Python 测试通过，字体、浮层与布局的 32 项测试另在原生 macOS 环境通过；本机 Qt 版本为 6.11.2，具体环境以渲染记录为准。

| 语义 | 深色 | 浅色 |
|---|---|---|
| 页面 | `#14131B` | `#F7F5FB` |
| 卡片 | `#201E2A` | `#FFFFFF` |
| 次级表面 | `#292635` | `#F0EDF6` |
| 正文 | `#F4F1F7` | `#292430` |
| 辅助文字 | `#B7B0C3` | `#706679` |
| 分隔线 | `#393445` | `#E3DDEA` |
| 输入边界 | `#81798C` | `#8B8098` |
| 品牌填充 | `#FF79B3` | `#EF5F9D` |
| 进行中文字 | `#FF9AC5` | `#A93668` |

浅色主题使用较深的粉色状态文字，确保小字号可读；按钮和下载进度仍使用品牌填充。完成为绿色、需要关注为琥珀色、失败为红色、等待与暂停为中性色，状态同时提供文字。录制只显示状态、时长、大小和速度。

共享组件位于 `gui/widgets/components.py`：页头、卡片、外置字段标签与错误、状态标签、提示、星轨空状态、图标按钮和数字步进器。

| 组件 | 规则 |
|---|---|
| 页面与卡片 | 页面边距 24px、模块间距 20px、卡片内边距 20px、圆角 14px |
| 输入与按钮 | 输入与普通按钮 40px、主按钮 44px、表格按钮 32px、圆角 8px |
| 焦点 | 固定占位的 2px 描边，不改变布局尺寸 |
| 列表 | 表头 40px、默认行高 56px；多行录制内容按字体高度适当增加 |
| 长内容 | 表格省略与完整提示；选中任务 / 场次可在详情区域读取全部错误和警告；路径可选择复制 |
| 提示 | 信息、成功、警告与错误共用布局，语义图标与文字同时出现 |

测试检查正文及语义文字对比度不低于 4.5:1，交互边界和焦点不低于 3:1。进度文字按填充和未填充区域分别绘制，避免白字落在浅粉进度上。

## 下拉选择与菜单

下载规格、直播画质、任务筛选和设置共用 `gui/widgets/combo_box.py` 的下拉组件。选择框保持 40px 高度与 2px 固定焦点边界；箭头随深浅主题、禁用及展开状态更新。展开列表使用 10px 圆角、6px 内边距和至少 40px 的选项行，当前项以淡粉背景、粉色文字与勾选标记展示；悬停和键盘移动使用局部描边，不改变已选值。

最多同时展示 8 项，更多选项纵向滚动。长标题右侧省略，展开项及选择框均提供完整文字提示，避免长文本撑宽窗口。菜单和输入框等宽对齐并保留 4px 间距，优先下方展开；所在屏幕的可用区域不足时上翻或缩短列表，避开系统菜单栏和 Dock，确保当前项仍可见。保留 Qt 的鼠标选择、键盘上下选择、Enter 提交和 Esc 取消；禁用选项无法选择。取消、点击外部或切页关闭浮层后，箭头恢复收起状态。

「更多」及中文输入框右键菜单共用圆角表面、主题箭头、选中颜色、禁用文字和分隔线。菜单按钮给箭头单独留出空间，避免与文案重叠。

离线截图工具捕获真实弹出浮层，并使用保持原 DPI 的大尺寸虚拟屏幕，避免默认 800×800 屏幕将菜单移动到错误位置。下面的尺寸指主窗口；截图会完整保留可能伸出主窗口的浮层。

| 场景 | 深色 900×640 | 浅色 900×640 | 深色 1120×760 | 浅色 1120×760 | 深色 1320×860 | 浅色 1320×860 |
|---|---|---|---|---|---|---|
| 下载画质 | [查看](images/biliflow-dropdown-download-dark-900.png) | [查看](images/biliflow-dropdown-download-light-900.png) | [查看](images/biliflow-dropdown-download-dark-1120.png) | [查看](images/biliflow-dropdown-download-light-1120.png) | [查看](images/biliflow-dropdown-download-dark-1320.png) | [查看](images/biliflow-dropdown-download-light-1320.png) |
| 直播画质 | [查看](images/biliflow-dropdown-live-dark-900.png) | [查看](images/biliflow-dropdown-live-light-900.png) | [查看](images/biliflow-dropdown-live-dark-1120.png) | [查看](images/biliflow-dropdown-live-light-1120.png) | [查看](images/biliflow-dropdown-live-dark-1320.png) | [查看](images/biliflow-dropdown-live-light-1320.png) |
| 任务筛选 | [查看](images/biliflow-dropdown-tasks-dark-900.png) | [查看](images/biliflow-dropdown-tasks-light-900.png) | [查看](images/biliflow-dropdown-tasks-dark-1120.png) | [查看](images/biliflow-dropdown-tasks-light-1120.png) | [查看](images/biliflow-dropdown-tasks-dark-1320.png) | [查看](images/biliflow-dropdown-tasks-light-1320.png) |
| 默认规格 | [查看](images/biliflow-dropdown-settings-dark-900.png) | [查看](images/biliflow-dropdown-settings-light-900.png) | [查看](images/biliflow-dropdown-settings-dark-1120.png) | [查看](images/biliflow-dropdown-settings-light-1120.png) | [查看](images/biliflow-dropdown-settings-dark-1320.png) | [查看](images/biliflow-dropdown-settings-light-1320.png) |
| 更多操作 | [查看](images/biliflow-dropdown-more-dark-900.png) | [查看](images/biliflow-dropdown-more-light-900.png) | [查看](images/biliflow-dropdown-more-dark-1120.png) | [查看](images/biliflow-dropdown-more-light-1120.png) | [查看](images/biliflow-dropdown-more-dark-1320.png) | [查看](images/biliflow-dropdown-more-light-1320.png) |

## 运行状态与兼容性

`LiveUiController` 集中持有一份直播服务、数据库、实例锁、刷新计时器和导出任务。直播页与任务中心订阅同一快照；服务消息只消费一次，再同步展示。下载继续使用原有稳定任务 ID 和工作线程映射。房间与历史通过房间 ID、场次 ID、片段路径保留选择与展开状态。

录制、重连和收尾期间禁止移除房间、修改目录与分段；收尾期间禁止重复停止。停止本场保留下次自动录制，关闭监控同时停止本场。导出期间禁止重复提交，保留源片段；完成后提供打开位置入口。

设置编辑使用独立草稿。保存先校验字段，再将本页实际修改的字段合并到最新设置，保留登录、版权确认和其他模块的更新。撤销不影响运行配置。已有非整分钟分段与非整 GiB 保留空间在未改动时保留原始数值。

本次只调整 GUI 路由、组件与状态通知；外部 API、CLI、录制协议、数据库结构和已有数据格式保持兼容。原生文件选择窗口保留系统样式；登录初始方式、Cookie 隐藏、220px 二维码、过期刷新和版权确认条件延续现有行为。

## 全页面截图矩阵

运行 `python scripts/capture_docs_screenshots.py` 可重新生成。脚本使用临时配置、临时数据库、模拟直播服务和离线作品；不启动下载、直播拉流或真实 MP4 导出。以下 54 张截图覆盖每个工作区页签与三种尺寸。

| 页面 | 深色 900×640 | 浅色 900×640 | 深色 1120×760 | 浅色 1120×760 | 深色 1320×860 | 浅色 1320×860 |
|---|---|---|---|---|---|---|
| 单个解析 | [查看](images/biliflow-download-dark-900.png) | [查看](images/biliflow-download-light-900.png) | [查看](images/biliflow-download-dark-1120.png) | [查看](images/biliflow-download-light-1120.png) | [查看](images/biliflow-download-dark-1320.png) | [查看](images/biliflow-download-light-1320.png) |
| 批量导入 | [查看](images/biliflow-batch-dark-900.png) | [查看](images/biliflow-batch-light-900.png) | [查看](images/biliflow-batch-dark-1120.png) | [查看](images/biliflow-batch-light-1120.png) | [查看](images/biliflow-batch-dark-1320.png) | [查看](images/biliflow-batch-light-1320.png) |
| 直播录制 | [查看](images/biliflow-live-dark-900.png) | [查看](images/biliflow-live-light-900.png) | [查看](images/biliflow-live-dark-1120.png) | [查看](images/biliflow-live-light-1120.png) | [查看](images/biliflow-live-dark-1320.png) | [查看](images/biliflow-live-light-1320.png) |
| 下载队列 | [查看](images/biliflow-tasks-dark-900.png) | [查看](images/biliflow-tasks-light-900.png) | [查看](images/biliflow-tasks-dark-1120.png) | [查看](images/biliflow-tasks-light-1120.png) | [查看](images/biliflow-tasks-dark-1320.png) | [查看](images/biliflow-tasks-light-1320.png) |
| 当前录制 | [查看](images/biliflow-recording-dark-900.png) | [查看](images/biliflow-recording-light-900.png) | [查看](images/biliflow-recording-dark-1120.png) | [查看](images/biliflow-recording-light-1120.png) | [查看](images/biliflow-recording-dark-1320.png) | [查看](images/biliflow-recording-light-1320.png) |
| 录制历史 | [查看](images/biliflow-history-dark-900.png) | [查看](images/biliflow-history-light-900.png) | [查看](images/biliflow-history-dark-1120.png) | [查看](images/biliflow-history-light-1120.png) | [查看](images/biliflow-history-dark-1320.png) | [查看](images/biliflow-history-light-1320.png) |
| 下载设置 | [查看](images/biliflow-settings-dark-900.png) | [查看](images/biliflow-settings-light-900.png) | [查看](images/biliflow-settings-dark-1120.png) | [查看](images/biliflow-settings-light-1120.png) | [查看](images/biliflow-settings-dark-1320.png) | [查看](images/biliflow-settings-light-1320.png) |
| 直播设置 | [查看](images/biliflow-live-settings-dark-900.png) | [查看](images/biliflow-live-settings-light-900.png) | [查看](images/biliflow-live-settings-dark-1120.png) | [查看](images/biliflow-live-settings-light-1120.png) | [查看](images/biliflow-live-settings-dark-1320.png) | [查看](images/biliflow-live-settings-light-1320.png) |
| 工具与存储 | [查看](images/biliflow-tools-dark-900.png) | [查看](images/biliflow-tools-light-900.png) | [查看](images/biliflow-tools-dark-1120.png) | [查看](images/biliflow-tools-light-1120.png) | [查看](images/biliflow-tools-dark-1320.png) | [查看](images/biliflow-tools-light-1320.png) |

## 关键状态与弹窗

| 状态 | 截图 |
|---|---|
| 下载 / 直播 / 任务空状态 | [下载](images/biliflow-state-download-empty.png)、[直播](images/biliflow-state-live-empty.png)、[任务](images/biliflow-state-tasks-empty.png) |
| 解析与音频模式 | [解析中](images/biliflow-state-parsing.png)、[解析失败](images/biliflow-state-parse-error.png)、[音频](images/biliflow-state-audio.png) |
| 批量部分失败与失效预览 | [部分失败](images/biliflow-state-batch-partial.png)、[来源修改](images/biliflow-state-batch-stale.png) |
| 等待、排队与准备录制 | [等待](images/biliflow-state-live-waiting.png)、[排队](images/biliflow-state-live-queued.png)、[准备](images/biliflow-state-live-preparing.png) |
| 直播重连、收尾与异常 | [重连](images/biliflow-state-live-reconnecting.png)、[收尾](images/biliflow-state-live-finalizing.png)、[异常](images/biliflow-state-live-error.png) |
| 历史缺口与导出 | [缺口与警告](images/biliflow-state-history-warning.png)、[处理中](images/biliflow-state-exporting.png)、[导出完成](images/biliflow-state-export-done.png) |
| 设置错误 | [字段校验](images/biliflow-state-settings-invalid.png) |
| 小窗口下方内容 | [输出规格](images/biliflow-state-download-specs-small.png)、[房间详情](images/biliflow-state-live-details-small.png)、[下载默认值](images/biliflow-state-settings-download-small.png)、[直播并发与空间](images/biliflow-state-settings-live-small.png)、[缓存工具](images/biliflow-state-settings-tools-small.png) |
| 登录与房间设置 | [手动登录](images/biliflow-login.png)、[扫码登录](images/biliflow-login-qr.png)、[过期刷新](images/biliflow-state-login-expired.png)、[房间设置](images/biliflow-room-settings.png) |
| 辅助提示与确认 | [版权](images/biliflow-dialog-copyright.png)、[设置离开](images/biliflow-dialog-settings-leave.png)、[退出](images/biliflow-dialog-quit.png)、[缓存](images/biliflow-dialog-cache.png)、[错误](images/biliflow-dialog-error.png)、[关于](images/biliflow-dialog-about.png) |
| 浅色辅助弹窗 | [版权](images/biliflow-dialog-copyright-light.png)、[设置离开](images/biliflow-dialog-settings-leave-light.png)、[退出](images/biliflow-dialog-quit-light.png)、[缓存](images/biliflow-dialog-cache-light.png)、[错误](images/biliflow-dialog-error-light.png)、[关于](images/biliflow-dialog-about-light.png) |

## 验证范围

布局回归覆盖两种主题、三种窗口尺寸、所有导航与页签，检查固定操作可见、主体无横向滚动。行为回归覆盖页面状态保留、单一直播服务、稳定 ID、批量失效与去重、设置草稿合并和离开提示、直播状态限制、历史展开与导出防重复。已有下载恢复、账号、版权、API、CLI 与录制测试一并执行。

全页面 GUI 渲染在 macOS 的 PySide6 offscreen 和原生 Cocoa 环境完成。字体与长下拉列表另在真实 macOS Cocoa、72 DPI、Retina 2× 环境验证三种尺寸和深浅主题，并逐图检查；其余原生截图复看下载、直播、任务、设置及辅助弹窗的代表状态。Windows / Linux 原生窗口边框、平台字体替代、系统文件选择器及不同 DPI 的实际显示仍需对应平台检查；这些差异不由离线截图确认。直播原生引擎和真实长时录制的既有发布验收范围见[直播录制](LIVE_RECORDING.md#发布验收状态2026-09-28)。
