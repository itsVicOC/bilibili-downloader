# BiliFlow 视觉规范与验证

## Windows 标题重复与双平台一致性检查（2026-10-21）

Windows 扩展客户区仍显示小图标和窗口名称，原因是 `QWidget` 在保留窗口按钮时自动补回 `WindowTitleHint`，且 Python 枚举取反在 Windows 上遗漏了高位自定义与关闭按钮标志。主窗口在底层 `QWindow` 创建、显示及窗口状态变化后，用整数掩码保留按钮标志并关闭重复标题绘制。保留侧栏品牌、真实窗口标题、任务栏图标、系统菜单、缩放和窗口按钮；普通弹窗仍保留平台标题栏。实现使用 Qt 公开接口，不替换系统窗口过程，也不清空应用图标。

两端截图还发现 Windows 自动激活首个导航按钮时出现完整焦点外框，macOS 则没有。统一为仅 Tab、反向 Tab、快捷键及键盘操作显示焦点外框；自动激活与鼠标点击继续使用原有选中样式。正文均以 14 个逻辑像素为基准，苹方与微软雅黑 UI 的字形和行高差异保留，由内容布局适配。

Windows 的扩展标题层在仅更新控件调色板时可能保留旧按钮颜色。主题变化后请求原生窗口重绘，使最小化、最大化和关闭按钮立即同步深浅模式；原生截图直接检查按钮与标题栏的对比度，不以控件截图代替。

双平台共用四个工作区、五类设置、账号、下载附加项及背景玻璃组件。验收矩阵包括两套配色、深浅模式、900×640 / 1120×760 / 1320×860、账号四种状态、长昵称、缺失头像、二维码与背景选择。以下差异按平台惯例保留：

| 项目 | Windows | macOS |
|---|---|---|
| 窗口按钮与安全区 | 右侧最小化、最大化、关闭，工具栏右侧避让 | 左侧红黄绿，侧栏顶部避让 |
| 菜单与快捷键 | 无重复横向菜单，Ctrl 快捷键及页面入口 | 系统菜单栏、⌘ 快捷键 |
| 正文字体 | 微软雅黑 UI，完整字形微调 | 苹方，平台默认微调；校正 72 DPI 点数换算 |
| 关闭窗口 | 可选托盘或退出，外观页保留对应字段 | 关闭窗口后后台运行，从 Dock 恢复 |
| 文件选择 | Windows 原生选择器 | Qt 选择器，规避系统面板未出现导致父窗锁住的问题 |

CI 在 Windows / macOS 的 Python 3.12 任务中追加原生标题栏、字体及页面截图检查，上传 `ui-parity-Windows` / `ui-parity-macOS`，保留七天。先扩大托管测试桌面，并校验窗口实际尺寸，避免默认 1024×768 桌面将 1120 / 1320 宽的样本压缩后仍按大窗口记入结果。记录同时保存请求尺寸和实际客户区；Windows 初次展开框架的小幅增量允许单独记录，桌面夹小仍判失败。此显示配置脚本只允许 GitHub Actions 执行，不修改用户电脑显示设置。`chrome` 目录通过桌面合成器捕获目标窗口矩形，包含 Windows 的独立标题绘制层；仅用 `QWidget.grab()` 会漏掉本次问题。截图与配置全部采用离线演示数据。自动检查验证标题隐藏、窗口元信息保留、系统菜单和窗口样式；实际 Snap 悬停、多屏 DPI 切换和 macOS 全屏手势仍需对应系统的交互验收。

## 0.8.6 小流时段动画（2026-10-21）

小流由固定的轻待机扩展为十二套像素动画，按本地清晨、上午、午后、傍晚和深夜选择动作池及文案，前台待机每隔 15～30 秒轮换。隐藏、最小化或转入后台时暂停，恢复后重新判断时段；同一时段续播，跨时段播放新入场动作。完整与迷你布局共用文案，后者按逗号分成两行。

[动画总览与逐套 GIF](MASCOT_DESIGN.md) · [清晨完整卡片](images/mascot/native/xiaoliu-morning-bilibili_blue-light-full.png) · [深夜迷你卡片](images/mascot/native/xiaoliu-night-star_trail-dark-mini.png)。小流专项在两个后端各有 64 张截图；README 和用户指南引用的工作区、设置与弹窗截图随 0.8.6 刷新，均使用离线演示数据。


## 文件选择窗口响应修复（2026-10-21）

目录、图片、工具与导出入口共用有生命周期管理的文件选择器。macOS 使用 Qt Widgets 文件窗口规避系统面板未显示却锁住父窗的路径；Windows 保留原生文件窗口。统一以异步 `open()` 显示，父窗口使用来源控件所属的真实窗口，明确置前；重复点击复用，取消及来源窗口关闭不提交结果。目录和图片选择仍保留设置草稿语义，图片解码继续异步，直播房间切换目录规则时保留新选择的独立目录。

回归从替换静态文件调用改为操作真实文件窗口，检查窗口可见且主事件循环计时器持续运行，覆盖选择、取消、重开、父窗口关闭及一次性结果提交。背景图片窗口附属于背景选择弹窗。两个平台的窗口边框和系统按钮沿用平台结构，文件浏览内容在 macOS 统一使用应用字体与样式。

本轮全量离屏回归 886 项通过、1 项跳过，Cocoa 原生专项 135 项通过。macOS 27.0.1 / Qt 6.11.2 打包程序中实际点击目录选择与取消、打开图片文件窗口、选入项目测试图片并完成预览，再取消背景选择，确认设置保持已保存状态；当前运行包来自 `dist/local-picker-fix-20261021`。旧版偶发面板不显示未稳定复现，保留排查范围说明，未把正常等待选择的线程样本判为系统死锁。

## 目录一致性与背景窗口精简（2026-10-21）

下载与直播设置的目录统一采用只读路径框和「选择…」按钮，可选中复制完整路径；两处共用创建策略、尺寸、底色及焦点样式。取消选择保持原值，更改后保留为草稿，工具的可执行文件路径仍可编辑。

玻璃模糊只在外观页调节，背景选择窗口使用当前模糊草稿进行预览。选择窗口移除重复标题、页面用途、全局模糊说明和第二个滑块；保留图片名称、筛选结果数量、深浅预览、可见度与就近的「重置」，底部仅提示「选用后需保存设置」。画风及推荐信息保留在图库卡片上，自定义图片保留格式、大小限制及错误反馈。释放出的空间用于放大预览，小窗口继续切换浏览与预览。

验收覆盖两套配色、深浅模式及三种尺寸的目录实际底色和高度、选择与取消、草稿与保存；背景窗口检查可见度分模式重置、选用和取消、恢复主题默认不会修改模糊草稿，以及小窗口预览、滑块、操作区互不遮挡。

本轮全量离屏回归 876 项通过、1 项跳过，Cocoa 原生专项合计 170 项通过。预览颜色采样测试补齐 Retina 像素密度换算后，四种配色 / 模式组合在两个后端均通过；原生专项排除下文已记录的两项前台激活 / 全屏环境限制。Ruff、编译及 diff 检查通过，本地包通过签名、冻结程序入口与压缩包完整性校验。

最新原生截图：[下载目录](images/appearance-controls/settings-light.png)、[直播目录](images/appearance-controls/live-settings-light.png)、[精简背景选择](images/appearance-controls/gallery-light.png)、[小窗口预览](images/appearance-controls/gallery-small.png)。

## 账号居中、精简设置与玻璃调节（2026-10-21）

侧栏账号将头像和昵称作为一组居中，窄侧栏仍仅显示居中的头像；保留长昵称省略、完整身份提示与原有账号入口。回归按实际绘制像素检查整组位置，覆盖两套配色及深浅模式。

移除独立「通用」分类及所有窗口行为说明，不迁移这些说明到其他页面。设置为下载、直播、外观、工具与存储、关于与更新五类，首次进入下载，本次运行继续保留所选分类。Windows 的关闭方式仅作为外观页中的可选字段保留，关闭、托盘及退出逻辑继续兼容。

新增 `appearance.glass_blur`，取值为 0–40 个逻辑像素，默认 18；旧配置、无效类型及越界值恢复默认。外观页提供带示例的滑块，背景选择窗口使用当前值预览实际图片。四个工作区共用此值，深浅模式也保持一致；调节只模糊背景，文字、焦点与控件独立绘制，最低值仍保留文字对比度保护。

拖动实时更新预览，四个背景选择器在下次打开时使用同一模糊草稿。保存成功后应用并记忆，撤销恢复已保存值，保存失败保留草稿及原界面。即时保存深浅模式不会提交或清除模糊草稿，符合其余外观选项的保存语义。

验收截图：[外观滑块](images/appearance-controls/blur-light.png)、[背景选择](images/appearance-controls/gallery-light.png)、[小窗口](images/appearance-controls/gallery-small.png)、[居中账号与五个分类](images/appearance-controls/settings-light.png)。[渲染记录](images/appearance-controls/rendering-profile.json)包含 Qt、后端及原始像素信息。

本轮全量离屏测试 862 项通过、1 项跳过，原生界面专项 127 项通过；编译、Ruff 和 diff 检查通过。原生测试进程被 macOS 保持为 ApplicationInactive，快捷键前台派发和系统全屏转换两项检查未通过，单独复查也受同一限制；这两项不计入通过数。新增的账号像素居中、五类导航、滑块同步、取消、保存失败、撤销及持久化检查均在原生后端通过。

## 背景玻璃与输入卡修复（2026-10-21）

下载空状态的标题、输入框、说明与批量入口不再共用固定 120px 高度，改为按布局和文字换行计算自然高度；三种尺寸下完整显示，不与固定底栏冲突。解析后隐藏引导时，输入卡恢复紧凑高度。

启用内置图库或自定义图片后，输入卡、资料卡、设置卡、列表外层及底部操作区改为液态玻璃风格。参考 [Apple 材质指南](https://developer.apple.com/design/human-interface-guidelines/materials)，使用与工作区固定背景对应的采样、18px 背景模糊、色彩保留、窄边缘折射和高光。实现由 Qt 绘制，不调用苹果原生 Liquid Glass 控件；没有背景图片时沿用原有实色卡片。输入框、选择状态及表格数据保留清晰表面。

玻璃只处理背景图，文字、图标和焦点仍由 Qt 独立绘制。小字使用适合玻璃底色的前景色，背景亮度受对比度约束；每个工作区共用一份模糊缓存，滚动、选项勾选和更新文字不重新模糊，换图、尺寸、配色、模式或可见度变化时重建。外观预览使用同一材质函数。

回归：835 项通过、1 项跳过，macOS Cocoa 专项 102 项通过；包含输入卡完整文字区域与重叠检查、黑白及高饱和背景的对比度、内置 / 自定义背景、缓存重用和无图回退。截图矩阵覆盖两套配色、深浅模式、两种图片来源、三种尺寸及空状态 / 已解析 / 直播，共 72 组。

原生 Retina 示例：[下载空状态](images/glass/download-empty-light.png)、[已解析](images/glass/download-resolved-light.png)、[直播](images/glass/live-light.png)、[深色自定义背景](images/glass/custom-dark.png)。[渲染环境](images/glass/rendering-profile.json)记录原始像素与后端；这些示例使用离线演示数据。

## 全界面体检落地（2026-10-21）

延续现有配色、小流、贯顶侧栏、56px 页头和固定底部操作区，集中修复空间分配、内容裁切与小窗口可达性。参考 [Linear 的界面整理](https://linear.app/now/behind-the-latest-design-refresh)、[Raycast 设置分组](https://manual.raycast.com/settings)、[HandBrake 队列流程](https://handbrake.fr/docs/en/latest/advanced/queue.html)和 [OBS 录制控制](https://obsproject.com/kb/quick-start-guide)，采用以下规则：

| 区域 | 当前规则 |
|---|---|
| 下载资料与规格 | 资料卡按内容自然高度显示，封面约 176×99px；规格在有足够宽度时采用两列，下载附加项固定 76px 完整高度，空间不足时由页面滚动 |
| 下载状态 | 输入引导合并到链接卡；来源修改或解析失败后禁止提交旧结果，资料及底栏明确说明失效状态 |
| 二维码登录 | 扫码视图移除内部滚动，220×220px 二维码完整可见；返回当前账号移入底部，生成、过期及错误共用状态区域 |
| 直播 | 页面宽度至少 880px 时列表和详情并排；更窄时详情可展开，房间表格和详情由外层统一滚动，操作栏固定 |
| 任务与失败详情 | 名称、状态与进度、规格、路径、异常原因分层；完整诊断可打开复制。导入失败表格优先给原因分配宽度，允许换行，每项可复制链接 |
| 设置 | 枚举控件最大 320px，数字控件最大 184px；路径保留宽度。命名模板默认折叠并显示示例，验证失败自动展开；保留草稿、保存与撤销语义 |
| 外观与背景 | 即时保存模式独立分组；配色及背景明确保存后生效。卡片和链接输入区使用统一阅读底色，卡片内文字不再逐段添加底色 |
| 背景选择 | 宽窗口同时显示图库与预览，宽度不足 900px 时切换浏览与预览；切换不丢失选择，选用后仍需保存设置 |
| 工具与更新 | FFmpeg、录制引擎各自显示路径、检测操作和结果；更新卡放在简介前，检查操作位于卡片顶部；更新弹窗突出立即更新，延后操作为「稍后提醒」 |

共享间距采用 8 / 12 / 16 / 24px，卡片内边距为 16px；正文保持约 14px，次要按钮使用常规字重。普通帮助使用辅助文字，需要处理的异常使用提示条。工作区预览同步采用紧凑资料卡、附加项及独立的模式分组。

回归检查除可见、可点击外，还检查卡片完整文字区域和实际高度、二维码完整可见区域、窄窗口详情与固定操作、模板验证定位、检测结果隔离以及背景上文字对比度和阅读底色一致性。截图覆盖星河 / 晴海、日间 / 夜间、900×640 / 1120×760 / 1320×860，以及内置和自定义图片；截图使用离线演示数据。

本轮截图：[900px 下载卡片](images/ui-refresh/options-dark.png)、[1120px 直播](images/ui-refresh/live-light-1120.png)、[任务摘要](images/ui-refresh/task-detail-light.png)、[高级命名模板](images/ui-refresh/naming-light.png)、[工具检测](images/ui-refresh/tools-light.png)、[失败详情](images/ui-refresh/failure-details-light.png)、[小窗口浏览](images/ui-refresh/gallery-browse-small.png)、[小窗口预览](images/ui-refresh/gallery-preview-small.png)、[原生二维码](images/ui-refresh/native-switch-light.png)。原生缩放及字体环境见[渲染记录](images/ui-refresh/rendering-profile.json)。

macOS 使用 Cocoa 原生 Qt 和 Retina 原始像素截图验证；窗口拖动、按钮避让及全屏回归沿用专项检查。Windows 的缩放、贴靠、最大化悬停菜单及混合 DPI 多屏仍需实机复核。此处记录优先于下方历史版本的横幅和局部文字底色说明。

本轮离屏全量回归为 817 项通过、1 项跳过，Cocoa 原生专项为 84 项通过；Python 编译、Ruff 和 diff 检查通过。截图生成时也断言四张卡片的文字高度和完整可见区域，以及扫码视图的二维码完整区域。原生截图保留 2× 像素；演示二维码仅用于布局验收，不包含登录授权。

## 界面与账号体验整理（2026-10-20）

当前界面沿用 Qt Widgets。主窗口页头延伸至原生标题栏区域；macOS 保留红黄绿按钮与系统菜单，Windows 移除重复的窗口内菜单栏，快捷键与页面入口继续使用共享动作。原生标题栏能力按 Qt 版本检测，旧版本回退系统窗口结构。

页头参考 [Linear 的界面整理](https://linear.app/now/how-we-redesigned-the-linear-ui)，采用 56px 单行工具栏与 16px 中等字重的页面名称，标题和正文左边缘对齐。侧栏直接贯通窗口顶部，页头只属于右侧工作区，侧栏上方不再留单独的矩形或横向分隔线；macOS 侧栏顶部为红黄绿按钮保留空间。页头不再绘制渐变、星轨或可见副标题；说明保留为无障碍描述。右侧操作避让原生窗口按钮。页头和侧栏空白区域支持拖动及双击最大化，按钮独立处理点击。外观设置中的工作区预览使用相同的结构。

侧栏依次显示视频下载、直播录制、任务中心和分隔后的设置；小流位于弹性区域，深浅模式与账号固定在底部。设置分类为通用、下载、直播、外观、工具与存储、关于与更新。首次打开通用，后续保留本次访问的分类；关于、更新及工具入口使用稳定分类标识定位，不依赖页签下标。窗口关闭偏好移至通用。

侧栏及外观页均支持跟随系统、日间、夜间，选择后立即保存并同步；配色和背景仍需保存设置。即时提交只更新 `appearance.mode`，保留其他草稿，撤销草稿不撤销已提交模式。旧配置默认跟随系统；手动模式忽略系统切换，返回自动时读取当前状态。

弹幕、字幕、封面、元数据使用共享可勾选卡片，支持整卡点击、键盘焦点与空格操作；两列布局空间不足时变为一列。全部字幕是字幕选项的从属项。文字按平台字体直接绘制：Windows 优先微软雅黑 UI 并使用完整字形微调，macOS 优先苹方并保留平台微调策略；高 DPI 由 Qt 处理。

已登录账号打开独立概览弹窗，参考 [Raycast 的身份与信息分区](https://manual.raycast.com/settings)：64px 圆形头像与 20px 昵称居中，下方使用居中的 240px 紧凑信息面板，按 UID、会员信息、登录状态分行，标签和值就近排列，不再铺满弹窗宽度。概览内部不重复显示窗口标题。账号头像保留源像素，不放大侧栏缩略图；长昵称省略并保留完整提示，UID 可选择复制。正常状态省去重复说明，其余状态在列表下显示辅助说明。退出入口低强调置左，关闭与切换账号成组置右，授权说明使用弱化文字。切换账号默认扫码，返回或取消保留原凭据，旧异步响应不会提交；网络失败保留已知身份并显示状态待确认。未知会员信息不会显示成普通会员。退出仍需现有确认。

最新离屏示例：[下载工作台](images/ui-refresh/download-light.png)、[窄窗口直播](images/ui-refresh/live-dark-900.png)、[任务中心](images/ui-refresh/tasks-light.png)、[下载选项](images/ui-refresh/options-dark.png)、[外观设置](images/ui-refresh/appearance-light.png)、[关于与更新](images/ui-refresh/about-light.png)、[当前账号](images/ui-refresh/account-light.png)、[网络异常](images/ui-refresh/account-unknown-light.png)、[长昵称与缺失头像](images/ui-refresh/account-long-name-dark.png)。原生 Retina 示例：[下载选项](images/ui-refresh/native-options-light.png)、[账号概览](images/ui-refresh/native-account-light.png)，原始分辨率及字体环境见[渲染记录](images/ui-refresh/rendering-profile.json)。下方历史验收记录及截图保留对应迭代背景。

生成本轮独立演示截图：

```bash
python scripts/capture_docs_screenshots.py --ui-refresh-only --output-dir /tmp/biliflow-ui-review
python scripts/capture_docs_screenshots.py --native --physical-pixels --ui-refresh-only --output-dir /tmp/biliflow-ui-native
```

离屏全量测试与 macOS Cocoa 专项回归覆盖本轮交互，包括标题随侧栏变化对齐、页头操作、拖动请求和双击最大化、账号概览与登录视图往返、原生窗口按钮和全屏往返。截图矩阵覆盖两套配色、深浅模式、三种尺寸及四个工作区，并包含图片背景与异常账号状态。原生 Qt 控件截图不包含系统合成的窗口按钮。Windows 发布工作流已配置 100% / 125% / 150% / 200% 字体缩放及本轮界面截图；贴靠、最大化悬停菜单、混合 DPI 多屏和系统窗口按钮仍需 Windows 桌面实机复核，不以 macOS 或离屏截图代替。


早期版本将点播下载、直播录制、任务与设置统一为「星轨收藏工作台」，曾在顶部工作区横幅使用星轨与主题渐变；当前页头已改为上述紧凑纯色布局。保留 BiliFlow 图标与吉祥物线索，功能入口使用统一的 SVG 线性图标。

## 像素看板娘「小流」

侧栏收藏卡使用原创蓝白像素少女「小流」，正常显示 80×80px，空间不足时改为 40×40px 横排迷你布局。十二套动画包含轻待机、挥手、伸展、踮脚、小跳、加油、翻书、喝饮料、轻舞、看星星、打哈欠与抱膝打盹；按本地时间分清晨、上午、午后、傍晚和深夜，前台待机每隔 15～30 秒轮换动作。辅助文案同步时段，迷你布局自动换行；后台、最小化与隐藏时暂停计时，恢复后重新判断时段。详见[设计、素材与生成记录](MASCOT_DESIGN.md)。

## 主题与背景（Issue #22）

新增[小流十二景内置背景图库](BUILTIN_BACKGROUNDS.md)，覆盖四个工作区、三种画风。选择窗口采用左侧大预览、右侧图库，来源为「小流」「自定义图片」，支持页面与画风筛选、拖放导入、原图和深浅效果预览。两类图片共用轻透明卡片及局部阅读底色，输入和操作栏保留实色，像素作品使用最近邻绘制。详见[本轮优化与对比](BACKGROUND_EXPERIENCE.md)。现有背景引用和默认外观继续保留。

新增「星河」「晴海」两套配色，各含系统跟随的深浅模式。「星河」沿用粉紫星空；「晴海」依据 B 站当前 `b-style` 色板，采用白色 / 中性炭灰表面、灰色次级控件和青蓝强调。横幅与侧栏收藏卡片增加局部天空渐变，横幅用柔粉微光与波纹补充层次；选中导航渐变淡出，页签保留浅色底与下划线。输入边框为 1px，主按钮使用可读的深蓝白字，品牌强调色与主按钮颜色分开。显示名更新后仍使用原有主题标识，兼容已有选择。详见[色板调研与取舍](BLUE_THEME_RESEARCH.md)。

侧栏账号入口在登录后显示用户名和 28px 圆形头像；宽度不足时省略用户名，窄侧栏仅显示头像，完整身份信息保留在工具提示与无障碍名称中。头像后台下载并缩小，使用独立无 Cookie 请求；加载失败显示默认账号图标，过期的登录响应与头像响应不会覆盖当前账号。

「设置 → 外观」使用独立草稿；四个工作区可分别导入背景。图像固定在主内容视口内，居中等比裁切，自动加遮罩，内容卡片和表格保留底色。图片副本与配置在保存成功后应用，切换配色或背景不会重建页面或直播服务。

运行 `python scripts/capture_docs_screenshots.py --appearance-only` 生成 68 张离线演示截图，覆盖两套配色、深浅模式、三种尺寸、四个工作区，以及小窗口背景设置、主题卡键盘焦点、下拉和登录弹窗；另包含蓝白默认主题的下载与设置页。背景由脚本绘制，不使用真实用户图片。代表截图：

| 场景 | 粉紫 | 蓝白 |
|---|---|---|
| 浅色下载页 1120px | [查看](images/biliflow-appearance-star_trail-download-light-1120.png) | [查看](images/biliflow-appearance-bilibili_blue-download-light-1120.png) |
| 深色直播页 1320px | [查看](images/biliflow-appearance-star_trail-live-dark-1320.png) | [查看](images/biliflow-appearance-bilibili_blue-live-dark-1320.png) |
| 深色外观设置 900px | [查看](images/biliflow-appearance-star_trail-settings-dark-900.png) | [查看](images/biliflow-appearance-bilibili_blue-settings-dark-900.png) |
| 浅色背景设置下方 900px | [查看](images/biliflow-appearance-star_trail-backgrounds-light-900.png) | [查看](images/biliflow-appearance-bilibili_blue-backgrounds-light-900.png) |

晴海默认外观：[浅色下载](images/biliflow-appearance-bilibili_blue-default-download-light-1120.png)、[深色下载](images/biliflow-appearance-bilibili_blue-default-download-dark-1120.png)、[浅色设置](images/biliflow-appearance-bilibili_blue-default-settings-light-900.png)、[深色设置](images/biliflow-appearance-bilibili_blue-default-settings-dark-900.png)。

布局回归覆盖两套配色 × 深浅模式 × 三种尺寸，外观页和下拉均无横向溢出。2026-10-18 完成 macOS offscreen 与原生 Cocoa 两组各 64 张截图检查。原生代表截图：[蓝白浅色设置 900px](images/native/appearance/biliflow-appearance-bilibili_blue-default-settings-light-900.png)、[蓝白深色下载 1120px](images/native/appearance/biliflow-appearance-bilibili_blue-default-download-dark-1120.png)、[粉紫深色设置 900px](images/native/appearance/biliflow-appearance-star_trail-settings-dark-900.png)、[粉紫浅色下载 1120px](images/native/appearance/biliflow-appearance-star_trail-download-light-1120.png)。原有 Windows 原生检查记录不代表本功能已完成 Windows 实机验证。

主题与背景基础功能交付时，全量 498 项 Python 测试、编译与静态检查通过，包含纯黑 / 纯白图片上的正文和辅助文字对比度检查。macOS 应用及独立更新程序完成本地打包验证；冻结更新程序在 full/lite 临时安装夹具中通过安装、重启及启动失败回滚，并验证背景图片和配置一起恢复。

## 显示修复（2026-10-19）

- 下载队列状态与表头统一居中，使用样式内容区域和字体度量定位；长状态最多两行，超出省略，完整内容保留在工具提示中。共享绘制组件继续遵循其他列的对齐设置。
- 设置编辑器仅在嵌入模式使用透明页面底层，五个页签与其他工作区共用固定背景、居中裁切和可见度遮罩。内容卡片、输入框和保存栏保留主题底色，独立设置窗口仍使用纯色底层。
- 已新增 ASS 字段结构与顶底定位、状态布局与工具提示、完整设置页面的背景透出与滚动检查；覆盖两套配色、深浅模式、0% / 50% / 100% 可见度及图片缺失和损坏回退。
- macOS offscreen 完成 100% / 125% / 150% 缩放检查，生成 227 张离线演示截图并复核代表页面。同步更新[任务中心](images/biliflow-tasks.png)与上表中的设置、背景设置代表截图。Windows 原生界面与 PotPlayer 播放效果尚需实机验收。

## 交互优化（2026-10-18）

- 下载页解析前展示紧凑引导；解析后展开资料和规格，固定操作栏显示画质、编码、分 P 与保存目录，修改入口定位到输出表单。批量导入同步显示媒体规格和各作品全部分 P 的范围。
- 错放的收藏夹、合集、番剧季度和直播链接提供带入原链接的跳转按钮；b23.tv 的展开和分类继续在后台完成。
- 批量元数据导入按来源、分页和作品显示进度；协作取消在当前请求结束后生效，保留已读取作品。成功作品、跳过作品、来源失败和重复分别统计；失败详情支持复制链接和重试合并，已有勾选与失效保护保持有效。
- 直播固定操作栏显示当前房间名称，悬停和无障碍名称提供房间 ID，避免详情滚出视野后失去操作目标。
- 任务范围默认当前筛选，可显式切换到所有任务；动作显示影响数量。移除仅针对记录，并提供本次运行内最近一次操作的撤销；数据库写入失败时保持界面记录。
- 作品列优先分配宽度，规格使用两行短标签，状态独立展示两行；完整规格、路径及警告保留于工具提示和选中详情。
- 登录默认扫码，Cookie 作为备用；已有凭据先展示账号管理，切换账号后才展开登录表单。
- 主题通过两张可键盘选择的预览卡比较；宽窗口将四个背景配置排为两列。点击缩略图与「选择背景…」打开同一选择窗口，共用实际工作区的裁切、遮罩及阅读底色函数，深浅切换不改变全局主题或保存草稿。
- 输入框默认 1px 边框，焦点 2px，总高度不变；只读字段采用次级表面。选中导航的图标和文字共用强调色，渐变继续集中于横幅和品牌区域。

本轮交互优化完成 544 项 Python 测试及编译、Ruff、diff 检查，并使用 macOS offscreen 与原生 Cocoa 各 223 张演示截图复核深浅色、三种窗口尺寸及弹窗。原生抽样图保存在 `images/native/ux/`；Windows 高 DPI 仍需独立实机验收。

交互演示截图包括[批量进度](images/biliflow-ux-batch-progress-light.png)、[失败详情](images/biliflow-ux-failure-details-light.png)、[账号管理](images/biliflow-ux-account-light.png)与[背景效果预览](images/biliflow-ux-background-preview-light.png)。截图均使用演示数据；对应逻辑的自动测试覆盖取消、重试合并、范围、撤销、保存失败与草稿隔离。

2026-10-19：背景预览增加 0–100% 可见度滑块，每区分别保存浅色、深色数值，旧配置继续使用原有自动遮罩。调节实时绘制；「应用到草稿」后仍需保存设置，取消不修改草稿。恢复默认按当前预览模式生效。实际工作区和预览共用裁切、遮罩绘制，卡片和表格继续保持实体底色；新导入图片使用处理后的完整图像预览，避免放大缩略图。

可见度调节交付通过 552 项 Python 测试；覆盖两套主题、深浅模式下预览与实际绘制一致性，以及字段回退、独立合并、取消、撤销、保存失败与重试。更新了 offscreen 和 macOS 原生演示预览截图。

批量导入页进一步收敛为「单行来源摘要 → 作品清单 → 固定操作卡」。解析完成后各尺寸均自动折叠来源，编辑时保留勾选；清单使用 44px 行高、左对齐表头和随内容隐藏的重复来源列，部分失败入口与统计合并在清单底部。修改规格移至操作卡，粉色主按钮去掉深色常驻描边，其余操作使用轻量文字按钮。内嵌页面底色透明，让背景自然出现在卡片间隙，卡片本身仍保留实体底色。演示截图使用 130 项作品与 28 项失效内容，覆盖两套配色 × 深浅色 × 三种尺寸 × 默认/自定义背景。

批量页打磨通过 555 项 Python 测试及编译、Ruff、diff 检查，offscreen 与 macOS 原生各生成 25 张演示截图（24 组外观组合及来源编辑态）。[原生浅色宽窗口](images/native/ux/biliflow-batch-refined-star_trail-background-light-1320.png)、[原生小窗口](images/native/ux/biliflow-batch-refined-star_trail-background-light-900.png)、[晴海深色](images/native/ux/biliflow-batch-refined-bilibili_blue-background-dark-1320.png)。取消、全部失败和进度状态也同步更新截图。

页头层次调整：将解析卡内的主题装饰移至四个工作区共用的顶部横幅，晴海使用青蓝渐变、柔粉微光与波纹，星河使用粉紫渐变与细星轨。装饰集中在右侧，左侧标题区保持干净；链接输入卡改为实体纯色与细边框。背景效果预览共用同一页头绘制；深浅色下正文、辅助文字在页头采样位置均达到 4.5:1 对比度。

本次页头调整通过 561 项 Python 测试，编译、Ruff、diff 检查通过，更新了 offscreen 与 macOS 原生各 223 张界面截图。[晴海浅色页头与纯色输入卡](images/native/appearance/biliflow-appearance-bilibili_blue-download-light-1320.png)。

单个解析与批量导入底部统一使用同一输出确认卡：72px 高、14px 圆角、16px 横向内边距，实体表面保护背景上的文字；左侧为状态、规格和目录，右侧为 32px 次要操作与 44px 主按钮。两页主按钮最小宽度和右侧位置一致，悬停、键盘焦点与禁用样式共用；模式切换统一使用顶部页签。解析前的修改规格入口可用，重新解析后保留仍可用的选择。几何回归覆盖两套主题、深浅色及三种窗口尺寸，比较两页底栏位置、尺寸和按钮尺寸；演示截图覆盖单个/批量的解析前后四种状态。

底栏统一通过 562 项 Python 测试及编译、Ruff、diff 检查。运行 `python scripts/capture_docs_screenshots.py --actions-only` 可生成 48 张状态组合截图和 2 张底栏细节图；offscreen 与 macOS 原生均完成检查。细节对比：[单个解析](images/native/output/biliflow-output-single-bar-light.png)、[批量导入](images/native/output/biliflow-output-batch-bar-light.png)。

## 页面与操作

2026-10-19 收尾复核：下载、直播和设置共用 72px 高的实体底部操作卡，主操作统一靠右，状态与目标保留在左侧。页签和任务筛选工具栏具有局部实体底色，演示背景使用浅色 80% / 深色 65% 可见度检查可读性，不改变用户的背景设置。两套主题共用主按钮的普通、悬停、按下、禁用及键盘焦点样式，2px 焦点边框固定占位，鼠标点击不显示键盘焦点描边。

主题卡的实线边框和「✓ 已选」表示选择，独立虚线外圈表示键盘焦点；Tab 移动焦点不更改草稿选择，空格进行选择，无障碍说明同步提供状态。任务行「移除记录」默认采用轻量文字样式，悬停与键盘焦点显示危险色；停止录制等操作仍保持原有语义。作品封面上限调整为 260×146，删去重复解释文案，为标题和作者留出更多空间。窗口、侧栏与关于页统一使用「星轨收藏站」，背景预览确认文案为「使用此效果」，仍需返回设置保存。

本轮通过 566 项 Python 测试，包含两套主题、深浅模式及三种尺寸下的工作区与底栏几何检查，以及主按钮键盘操作和实际焦点像素检查。编译、Ruff 与 diff 检查通过，macOS offscreen 与原生 Cocoa 各生成 277 张演示截图，完成代表场景视觉复核；本地 macOS 应用打包、签名结构及 ZIP 完整性检查通过。macOS 原生演示截图：[直播底栏](images/native/final/biliflow-appearance-bilibili_blue-live-light-900.png)、[任务筛选与记录操作](images/native/final/biliflow-appearance-star_trail-tasks-dark-900.png)、[主题选择与键盘焦点](images/native/final/biliflow-appearance-bilibili_blue-theme-focus-light.png)。

所有工作区共用一个不可拖动、不可浮动的顶部工具栏，集中显示工作区标题、说明和页头动作。macOS 使用系统标题栏融合能力，Windows 保留原生窗口行为并移除重复菜单栏；页内仍保留页签、筛选、主要操作与反馈。设置、关于、退出使用明确的系统菜单角色。来源聚焦和工作区切换分别支持 Cmd/Ctrl+L、Cmd/Ctrl+1–4；多行 Enter 与中文输入法提交沿用 Qt 原有行为。

窗口关闭与应用退出分别处理：macOS 关闭后保留 Dock 入口，Windows 默认明确选择后台运行或退出，并可记住。关闭提示采用具体动作按钮、默认后台运行、低强调危险色退出及取消入口；配色、字体和间距沿用现有组件。完整依据见[交互调研](WINDOW_LIFECYCLE_RESEARCH.md)，提示框可查看[星河浅色](images/lifecycle/1/biliflow-close-active-star_trail-light.png)、[星河深色](images/lifecycle/1/biliflow-close-active-star_trail-dark.png)、[晴海浅色](images/lifecycle/1/biliflow-close-active-bilibili_blue-light.png)、[晴海深色](images/lifecycle/1/biliflow-close-active-bilibili_blue-dark.png)。

任务批量操作在没有对应任务时禁用。工具检测过程防重复提交，结果显示于设置页。字段标签关联对应控件或其焦点代理；设置保存失败保留草稿并定位首个错误。

| 入口 | 内容 | 主要操作 |
|---|---|---|
| 视频下载 / 单个解析 | 链接输入、作品资料、输出规格与归档附加项 | 开始解析、加入下载队列 |
| 视频下载 / 批量导入 | 来源输入、解析预览、作品勾选 | 解析并预览、加入下载队列 |
| 直播录制 | 房间监控列表与选中房间详情 | 添加并监控、立即开始 / 停止本场、自动监控 |
| 任务中心 / 下载队列 | 状态筛选、下载进度、行操作与完整详情 | 暂停、继续、重试、打开、移除记录 |
| 任务中心 / 当前录制 | 准备、排队、录制、重连、收尾与异常房间 | 停止本场、查看房间 |
| 任务中心 / 录制历史 | 本地时间的场次、封口片段、缺口与警告 | 打开目录 / 文件、导出 MP4 |
| 设置 / 下载 | 保存目录、目录模板、默认规格、附加项与并发 | 保存设置、撤销修改 |
| 设置 / 直播 | 新房间默认目录、分段、并发与保留空间 | 保存设置、撤销修改 |
| 设置 / 工具与存储 | FFmpeg、录制引擎及后台检测、下载缓存 | 选择路径、检查、清理缓存 |

侧栏常规宽度 208px，窗口小于 1120px 时收为 72px；最小窗口仍为 900×640。下载内容宽度不足 900px 时作品资料与输出规格上下排列；直播内容宽度不足 1000px 或页面高度不足 700px 时详情移至列表下方。上下布局使用一个主体滚动区，房间表格随内容展开，避免嵌套滚动。较小窗口需要纵向滚动查看完整表单，下载、直播和设置的主要操作固定在主体滚动区外。

页面实例持续保留，切换不会重建工作台。输入、解析结果、页签、筛选、选择与滚动位置保留；加入下载队列后仍停留在当前页。修改来源会使旧解析结果失效，提交前需重新解析。

## 主题资源

颜色与尺寸集中在 `gui/resources/styles.py`，通过单一生成式 QSS 应用。系统深浅主题同步更新 QPalette、SVG 图标与绘制组件。字体沿用平台中文字体。基准为正文 14px、辅助 12px、区块 16px、页头与弹窗标题 24px（均为 100% 缩放下的逻辑像素）。QSS 使用对应的 10.5/9/12/18pt；Cocoa 的 72 DPI 按 96/DPI 换算，移除仅 macOS 的额外 1.15 倍放大，使两端具有一致的字号层级。Retina 像素缩放由 Qt 处理；Windows / Linux 保留系统点数字号与用户文字缩放。全局明确指定字体族，避免加粗文字回退。

### 原生显示差异分析与复核（2026-09-28）

2026-10-17 更新：下方原生字体与下拉基准已重新生成，正文为 14px、页头为 24px；原生系统菜单、Cmd+L／Cmd+3 和全屏布局已在隔离的冻结演示应用中操作验证。[窗口外壳截图](images/native/biliflow-shell-light-1320.png) 使用 2× Retina 原始尺寸，包含系统标题栏及融合工具栏；其左上角的紫色标记来自截图会话的系统指示，不属于应用设计。演示应用不读取生产配置、不启动真实下载或录制。Windows 原生缩放与安装验收结果单独记录，不以 macOS 或 offscreen 结果代替。

用户提供的实机截图暴露了此前仅用 offscreen 检查的不足。原生 Cocoa 下，同样的 `11.5pt` 正文换算为 12 个逻辑像素，96 DPI offscreen 下为 15 个；原生加粗标题还回退到 `.AppleSystemUIFont`，而离线环境使用 `PingFang SC`。当时通过 DPI 换算与字体族修正，使原生与离线渲染一致。本轮进一步统一两端字号基准，目标正文 14px、页头 24px；下方历史截图将随本轮原生复核更新。

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

### Windows 原生缩放复核（2026-10-17）

发布演练 `dry-run-34` 使用 Windows 原生后端分别在 100%、150%、200% 下运行字体与下拉检查。三种缩放均使用 `Microsoft YaHei UI`，正文 14 个逻辑像素；每种缩放的深浅主题和三种尺寸均满足浮层在可用屏幕内且不遮挡输入框。以下图片按逻辑尺寸导出，原始 DPR 与六组数据保存在对应记录中。

| 缩放 | 浅色 1320px 工作区 | 深色 900px 下拉 | 渲染记录 |
|---|---|---|---|
| 100% | [查看](images/native/windows/1/biliflow-platform-download-light-1320.png) | [查看](images/native/windows/1/biliflow-platform-dropdown-dark-900.png) | [JSON](images/native/windows/1/rendering-profile.json) |
| 150% | [查看](images/native/windows/1.5/biliflow-platform-download-light-1320.png) | [查看](images/native/windows/1.5/biliflow-platform-dropdown-dark-900.png) | [JSON](images/native/windows/1.5/rendering-profile.json) |
| 200% | [查看](images/native/windows/2/biliflow-platform-download-light-1320.png) | [查看](images/native/windows/2/biliflow-platform-dropdown-dark-900.png) | [JSON](images/native/windows/2/rendering-profile.json) |

Windows 构建机桌面的物理分辨率有限，较大逻辑窗口可能超出可用屏幕；菜单仍按所在屏幕约束定位。这里验证 Qt 原生字体和控件布局，系统边框、文件选择器及真实多屏切换仍需 Windows 桌面复核。

运行 `python scripts/capture_docs_screenshots.py` 可重新生成；`--updates-only` 只更新设置页签和更新弹窗。脚本使用临时配置、临时数据库、模拟直播服务和离线作品；不启动下载、直播拉流或真实 MP4 导出。以下 60 张截图覆盖每个工作区页签与三种尺寸。

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
| 软件更新 | [查看](images/biliflow-updates-dark-900.png) | [查看](images/biliflow-updates-light-900.png) | [查看](images/biliflow-updates-dark-1120.png) | [查看](images/biliflow-updates-light-1120.png) | [查看](images/biliflow-updates-dark-1320.png) | [查看](images/biliflow-updates-light-1320.png) |

更新选择弹窗提供可滚动的纯文本说明和三种操作：[深色](images/biliflow-dialog-update.png)、[浅色](images/biliflow-dialog-update-light.png)。软件更新页支持后台检查状态、下载进度、取消下载、稍后安装和手动安装入口；沿用现有卡片、按钮和主题。

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
