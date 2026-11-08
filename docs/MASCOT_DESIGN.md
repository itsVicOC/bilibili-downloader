# 小流 · BiliFlow 像素看板娘

小流采用蓝发白色发梢、星形发饰、青色流带与蓝白短外套。角色参考 2233 娘的蓝白二次元气质，以独立的发型、服装和星轨饰品形成 BiliFlow 的形象。

![十二套动画总览](images/mascot/actions/xiaoliu-actions.gif)

## 按时间陪伴

小流按电脑本地时间（含当前系统时区）切换以下动作池。首次显示播放池中的第一个动作，之后在池内洗牌轮换；一轮全部播放后重新洗牌，池内有多套有效动作时避免连续重复。

| 时段 | 动作池 | 文案 |
|---|---|---|
| 清晨 05:00–09:00 | 伸懒腰、挥手、踮脚张望 | 早安，元气出发 |
| 上午 09:00–12:00 | 加油、小跳、翻书 | 专注收藏，一起加油 |
| 午后 12:00–18:00 | 喝饮料、伸懒腰、翻书 | 午后时光，慢慢来吧 |
| 傍晚 18:00–23:00 | 看星星、碎步轻舞、挥手 | 星光亮起，陪你收藏 |
| 深夜 23:00–05:00 | 打哈欠、抱膝打盹、看星星 | 夜深啦，记得休息 |

完整动作结束后回到轻待机，累计前台可见的待机时间，随机等待 15～30 秒开始下一套。常规动作 2.56 秒，打盹 6 秒。跨时段先完成当前动作，再更新动作池和文案；在待机中切换时段则开始新的入场动作。

隐藏、最小化和应用进入后台时停止计时，保存当前帧与等待时间。恢复时重新判断时段：同一时段续播，时段已变则播放新时段的入场动作。计时使用单调时钟，系统日期和时区只影响时段；不会补播离开期间的动作。

| 动画 | 单套预览 | 动画 | 单套预览 |
|---|---|---|---|
| 轻待机 | [GIF](images/mascot/actions/xiaoliu-idle.gif) | 挥手 | [GIF](images/mascot/actions/xiaoliu-wave.gif) |
| 伸懒腰 | [GIF](images/mascot/actions/xiaoliu-stretch.gif) | 踮脚张望 | [GIF](images/mascot/actions/xiaoliu-tiptoe.gif) |
| 小跳 | [GIF](images/mascot/actions/xiaoliu-hop.gif) | 加油 | [GIF](images/mascot/actions/xiaoliu-cheer.gif) |
| 翻书 | [GIF](images/mascot/actions/xiaoliu-read.gif) | 喝饮料 | [GIF](images/mascot/actions/xiaoliu-sip.gif) |
| 碎步轻舞 | [GIF](images/mascot/actions/xiaoliu-dance.gif) | 看星星 | [GIF](images/mascot/actions/xiaoliu-stargaze.gif) |
| 打哈欠 | [GIF](images/mascot/actions/xiaoliu-yawn.gif) | 抱膝打盹 | [GIF](images/mascot/actions/xiaoliu-doze.gif) |

[静态动作总览](images/mascot/actions/xiaoliu-actions.png)。总览 GIF 统一以 400ms/帧展示姿态；各套 GIF 使用应用实际时序。

## 素材与运行方式

- 静态首帧：`bilibili_downloader/gui/assets/xiaoliu.png`，40×40 RGBA PNG。
- 待机精灵图：`bilibili_downloader/gui/assets/xiaoliu_idle.png`，240×40，横排六帧；所有帧共用 24 色以内的色板，透明度仅为 0 或 255。
- 显示尺寸：正常 80×80px；侧栏可用高度不足时以 40×40px 角色配两行文案显示；窗口宽度小于 1120px 时收藏卡随侧栏一起收起。
- 轻待机时序：1600、650、80、120、80、1470ms，共四秒；身体固定，眼睛、发梢与飘带变化。十一套全身动作各有独立的 320×40 横排八帧精灵图，首尾共用原有中立姿态，准备、主要动作和回落逐帧播放。
- 绘制采用最近邻缩放，全部动画共用原有像素色板和二值透明度。损坏、尺寸错误或缺失的动作跳过，动作库不可用时继续原有待机；待机也不可用时显示独立静态图。全部精灵图沿用 `asset_path()` 和现有打包目录，源码、wheel 与冻结程序完全离线加载。

## 预览与复现

2026-10-21 验证：全量 963 项测试通过、1 项跳过；动画调度与组件专项合计 90 项通过，其中组件的 64 项另在原生 Cocoa 后端通过。Ruff、编译和 diff 检查通过。PyInstaller 构建成功，冻结目录与 macOS `.app` 中十二张图集均核对 SHA-256 与源码一致；运行图集合计约 49KB。

offscreen 与原生后端各导出 64 张截图，覆盖两套主题、深浅模式、四组窗口尺寸及五个时段的完整/迷你卡片。原生验证为 Qt 6.11.2、72 DPI、Retina 2×。例如：[原生深夜迷你卡片](images/mascot/native/xiaoliu-night-star_trail-dark-mini.png)、[原生清晨完整卡片](images/mascot/native/xiaoliu-morning-bilibili_blue-light-full.png)。

[角色放大图](images/mascot/xiaoliu-preview.png) · [精灵图放大图](images/mascot/xiaoliu-atlas.png) · [动画 GIF](images/mascot/xiaoliu-idle.gif)

离线演示截图覆盖星河、晴海的深浅模式，以及 900×640、1120×640、1120×760、1320×860 四组尺寸。演示使用隔离的临时配置与模拟服务。

- [晴海浅色完整角色](images/mascot/offscreen/biliflow-mascot-bilibili_blue-light-1120x760.png)
- [晴海深色迷你角色](images/mascot/offscreen/biliflow-mascot-bilibili_blue-dark-1120x640.png)
- [星河深色完整角色](images/mascot/offscreen/biliflow-mascot-star_trail-dark-1320x860.png)
- [原生 Retina 浅色完整角色](images/mascot/native/biliflow-mascot-bilibili_blue-light-1120x760.png)
- [原生 Retina 深色迷你角色](images/mascot/native/biliflow-mascot-bilibili_blue-dark-1120x640.png)

2026-10-20 验证：168 项相关测试通过（角色、工作区、布局、主题、外观及冻结资源路径），其中角色的 13 项测试另在原生 Cocoa 后端通过。offscreen 与原生后端各导出 16 张窗口截图、8 张卡片截图；原生环境为 Qt 6.11.2、72 DPI、Retina 2×，见[渲染记录](images/mascot/native/rendering-profile.json)。另检查 1×、1.5×、2× 绘制的像素边缘。

```sh
python scripts/build_mascot_assets.py
python scripts/build_mascot_assets.py --actions
python scripts/capture_docs_screenshots.py --mascot-only --output-dir docs/images/mascot/offscreen
python scripts/capture_docs_screenshots.py --native --mascot-only --output-dir docs/images/mascot/native
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_mascot_animation.py tests/test_pixel_mascot.py tests/test_workspaces.py tests/test_visual_layout.py tests/test_theme.py tests/test_appearance.py
```

构建脚本将选定的原始生成稿按统一裁切框、脚底基线和最近邻采样导出到 40×40 网格；共享身体底帧，只从生成稿提取眼部、发梢和流带区域，避免跨帧抖动。源稿错误镜像的最后一格未用于运行素材。

## 全身动作生成记录

十一张动作源稿均通过内置 **image_gen** 逐套生成，参考原有小流像素放大图，要求透明背景、2×2 四格连续姿态与固定人物身份；经过人工查看后导出。完整提示词与原稿保存在 [actions/originals/](images/mascot/actions/originals)，每套为同名 `.txt` 和 `.png`（wave、stretch、tiptoe、hop、cheer、read、sip、dance、stargaze、yawn、doze）。

构建脚本仅负责四格提取、同套统一比例、落地基线对齐、40×40 最近邻采样、原有共享色板映射与打包；动作的手臂、腿部、表情和道具均来自生成稿。打盹保留较短的坐姿，小跳第二姿态保留离地高度；所有动作首尾回到原有静态帧。旧版待机素材与源稿继续保留。

播放调度位于 `mascot_animation.py`，与 Qt 绘制分离，可注入本地时间、单调时钟和随机源进行无等待测试。截图脚本冻结时间与动作，避免运行时段影响文档截图。

## 原待机生成记录

生成方式为内置 `image_gen`，请求透明背景；[选定原始生成稿](images/mascot/xiaoliu-imagegen.png) 保留在项目中。以下为所选稿的最终提示词，输入图为同一角色的初稿：

```text
Edit target: the supplied Xiao Liu sprite sheet. Keep her recognizable blue bob, white tips, small star hairclip, cyan side ribbon, blue-white jacket and navy skirt. REDRAW and EXTREMELY SIMPLIFY this into authentic tiny 1990s handheld-game PIXEL ART. The current drawing has far too much detail and soft shading. Each character must use ONLY A 40x40 PIXEL GRID, with visibly LARGE square pixel clusters when enlarged. One eye is only 2 by 3 logical pixels, a hand only 2 by 2, face about 12 pixels wide. Use no more than 20 entirely flat solid colors across the whole sprite sheet, fully opaque pixels or fully transparent pixels ONLY. No antialiasing, no fine lines, no smooth curves, no tiny texture, no gradients, no realistic shading. 2-head chibi proportions. Output a WIDE SHORT single strip of EXACTLY SIX EQUAL SQUARE CELLS in a 6:1 aspect ratio, total logical resolution 240x40, enlarged as nearest-neighbor pixels. The head, face, star clip on image LEFT, side ribbon on image RIGHT, body and feet must be at identical coordinates in ALL SIX FRAMES. Do NOT mirror any frame (the current last frame is wrong). Frame 0 eyes open ribbon centered; frame 1 eyes open ribbon 1 pixel right; frame 2 eyes half closed ribbon right; frame 3 eyes closed smiling ribbon right; frame 4 eyes open ribbon centered identical to frame 0; frame 5 eyes open ribbon 1 pixel left. Body completely still. Six characters must be the exact same size and all fully fit inside their own square cell with 2 logical pixels transparent margin. True transparent background. No shadows or floor or labels or grid lines or checkerboard. Crisp low-resolution professionally designed game sprite, NOT a high-resolution anime illustration.
```

运行素材经过网格与色板导出，以实际 PNG 为准；原始生成稿的画布尺寸和颜色数量不直接作为运行约定。
