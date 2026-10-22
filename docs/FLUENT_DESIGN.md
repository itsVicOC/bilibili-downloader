# Fluent Design 精修规范

本分支采用 Fluent 2 的层级、材质和交互细节，保留 BiliFlow 的粉紫／青蓝配色、小流、工作区导航及功能流程。界面继续使用 PySide6；没有新增 UI 框架、配置迁移或业务接口变更。

## 视觉参数

| 项目 | 规范 |
|---|---|
| 页面／卡片内边距 | 24／16 个逻辑像素 |
| 分组／字段／组内间距 | 16／12／8 |
| 控件／卡片圆角 | 8／12 |
| 普通／主要／紧凑操作高度 | 40／44／32 |
| 下载附加选项高度 | 64，保留格式说明、标题和勾选标记 |
| 正文／说明 | 14／12 个逻辑像素；保留原生中文字体和平台 DPI 换算 |
| 页头／分组标题／弹窗标题 | 18／16／24 个逻辑像素 |

`UiMetrics` 和 `ThemePalette` 是公共样式及自绘控件的共同来源。新增的内部表面参数包括弱边框、控件底色、悬停层、弱选中层、浮层和语义状态底色。品牌色主要用于主要操作、活动状态和选中指示。表格保留列结构，百分比移到细进度条上方，避免文字跨越不同颜色的填充区域。

普通控件使用细边框；主要按钮预留两像素的透明焦点边框。焦点、按下、只读和禁用状态不改变控件的占用尺寸。鼠标点击与自动激活不显示键盘焦点框；键盘焦点仍清晰可见。macOS 的 Tab 遍历遵循系统“完整键盘控制”偏好。

粉色主要操作参考 [B 站官网样式](https://s1.hdslb.com/bfs/static/shanks/laputa-home/assets/index-3f345f9f.css)：日间使用 `Pi5 #FF6699`、悬停 `Pi4 #FF8CB0`、按下 `Pi6 #E84B85`，搭配 `text_white #FFFFFF`；夜间使用官网深色阶 `Pi5 #D44E7D`，悬停与按下分别取 `Pi6 #DC6D94`、`Pi4 #A73E65`。这是用户确认的品牌配色选择，粉色主按钮不计入普通正文 4.5:1 的对比度保证；青蓝主要操作仍保持 4.5:1。

文本选区使用独立的 `text_selection`／`text_selection_text` 参数，不复用导航和表格的弱选中底色。粉色主题日间／夜间为 `#AD1C5B`／`#A73E65`，青蓝为 `#007FAF`，均搭配白字；选区文字对比度至少 4.5:1，底色与输入框至少 2:1。Qt 调色板与输入框、富文本、纯文本及可编辑组合控件共享该规范。

## 材质与布局

保留用户已有的背景图片、分区可见度及模糊参数。玻璃缓存降低饱和度、提高中性色融合比例，并弱化折射边缘与高光；文字和控件不进入模糊缓存。无背景时使用统一实色表面，有背景时页签保留不透明底色，避免底图影响文字。

设置中的默认媒体规格在可用宽度达到 860 个逻辑像素时采用两列，窄窗口回到单列。直播时长列按字体宽度计算，完整显示超过 99 小时的时间。已有的侧栏收窄、下载表单重排、直播详情折叠与背景图库小窗口模式继续生效。原生窗口按钮、快捷键、托盘行为和文件选择器的平台差异保留。

Windows 的 Qt 6.11 扩展标题栏存在透明悬停图层的合成问题：白色半透明像素经非预乘 ARGB 图像传入分层窗口，可能变成亮白块，遮住夜间的浅色图标。应用将 Qt 的原生标题栏图层裁剪到三个窗口按钮，并为其启用不透明中性材质，保留 Qt／Windows 的图标、窗口操作、系统菜单和 Snap 悬停。裁剪区域随窗口尺寸、DPI 和句柄变化更新；尺寸不变时不重复创建 GDI 区域。找不到对应原生图层时保留透明标题栏。依据：[Qt 标题栏绘制](https://github.com/qt/qtbase/blob/v6.11.1/src/plugins/platforms/windows/qwindowswindow.cpp)、[Qt 位图转换](https://github.com/qt/qtbase/blob/v6.11.1/src/gui/image/qpixmap_win.cpp)。

## 微动效

导航选中指示与下载选项状态使用 120ms 过渡，折叠箭头使用 160ms，均采用 OutCubic 缓出。折叠内容、校验定位、页面切换和业务操作立即生效。

动画以 Qt 数值动画驱动局部重绘，不逐帧重设样式表、不增加轮询。重复操作从当前数值转向最终状态；隐藏、禁用或切换主题时结束当前动画。截图工具通过进程内 `uiAnimationsEnabled=False` 关闭过渡，保证截图可重复；此开关不写入用户配置。

## 验证与复现

离屏验证覆盖两套配色、深浅模式和三种尺寸，以及无图、内置图片、自定义图片；正文和状态文字按至少 4.5:1 的对比度检查。已有的下载、直播、登录、草稿、更新、缓存、文件选择器和窗口生命周期回归继续运行。新增测试检查动画快速反转、隐藏／禁用后停止、焦点几何稳定及背景页签的实际绘制颜色。

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
python -m compileall -q bilibili_downloader tests scripts
python -m scripts.capture_docs_screenshots --output-dir build/fluent-design/after/star_trail
python -m scripts.capture_docs_screenshots --color-theme bilibili_blue --output-dir build/fluent-design/after/bilibili_blue
python -m scripts.capture_docs_screenshots --glass-only --output-dir build/fluent-design/after/glass
```

在 macOS／Windows 桌面追加 `--native --physical-pixels` 可生成原生字体和窗口截图。CI 原生验证现包含两套配色的完整页面矩阵。离屏或在 macOS 上模拟 Windows 标志的测试不能证明 Windows 的原生窗口、Snap 或混合 DPI 行为；Windows 原生结果须以对应 CI 和实机记录为准。

本轮测试结果和截图索引记录在工作目录 `build/fluent-design/`；本地复核入口为该目录的 `index.html`。稳定的主要截图同步到 `docs/images/`，供 README 和用户指南引用。

2026-10-22 本地验收：Python 3.11.15／Qt 6.11.2，离屏回归 **996 项通过、4 项平台相关跳过**；原生 Cocoa 专项 **107 项通过、3 项 Windows 平台专项跳过**。Ruff、源码编译和 diff 检查通过。原生窗口另外验证深浅模式下普通、最大化、还原六种合成画面，保留标题元信息、图标与系统窗口按钮；两套配色的原生完整页面矩阵已生成。Windows／Linux 的本次原生实机结果尚未验证，未将上述结果计作对应平台验收。
