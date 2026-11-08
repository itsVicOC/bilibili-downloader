# Fluent 第二轮精修验收

2026-10-23，开发分支 `codex/fluent-design-polish`。本记录汇总第二轮界面与背景复核，纳入 `v0.8.9b2` 预发布版；既有 `v0.8.9b1` 标签保留。用户复现基准为 **Windows 11、100%、单屏**。

## 实现与兼容范围

- Windows 主窗口按钮由应用统一绘制，与页头共用底色；热区为 46×32 逻辑像素，图标为 DPI 对齐的矢量线条。保留原生窗口身份、系统菜单、拖动和缩放，关闭继续进入原有生命周期流程。
- 更新说明使用 Qt Markdown 文档与只读阅读控件，保留标题、列表、引用、代码、表格和链接；支持选择、复制、换行及滚动，主题变化保留选区与阅读位置。
- 共用控件采用中性悬停／按下层，减弱卡片及表格分隔，规格标签按内容宽度居中；页签仅在键盘操作时显示焦点框。
- 十二景中四张修正手部，ID 与路径不变；[逐张检查和对比](BACKGROUND_HAND_REVIEW.md)包含实际提示词。
- API、CLI、配置、账号、任务数据库和更新协议保持兼容。背景可见度、模糊与已有选择保持原值，玻璃仍共用工作区模糊缓存。

## 本机验证

环境：macOS arm64，Python 3.11.15，Qt 6.11.2。离线演示与测试使用临时配置、数据库和录制数据。

| 检查 | 结果 |
| --- | --- |
| 完整离屏 pytest | 1031 通过、5 项平台相关跳过 |
| Cocoa 原生界面与生命周期 | 122 通过 |
| Ruff、编译与 diff | 通过 |
| 十二景资源 | 12 张与缩略图完整，共 7.75 MiB，引用兼容检查通过 |

生命周期子进程测试在等待退出时继续处理父 GUI 事件，覆盖 Cocoa 的激活交接；没有放宽退出时限或删除生命周期场景。

## Windows 原生验证

CI 将标题栏独立为 **100%／125%／150%／200%** 四档 Qt 缩放（`QT_SCALE_FACTOR`），完整页面矩阵在标准缩放运行。原生专项读取桌面合成截图并使用真实鼠标输入，检查三枚按钮的默认、悬停、按下、拖出取消，以及系统菜单、普通／最大化／还原、边缘缩放、最小化、重新显示及关闭委托。热区边界另覆盖负坐标与当前 DPI 的换算。

Windows 按钮专项在四档缩放下分别 **29 项全部通过**，覆盖两套配色 × 深浅模式。代码验证提交为 `4336dd6`，见 [CI 运行与原始 artifact](https://github.com/itsVicOC/bilibili-downloader/actions/runs/39890275455)。该运行 **15／15 个任务全部通过**：Linux／Windows／macOS 全量 pytest、Ruff 与编译，Windows／macOS 原生页面与弹窗矩阵，四档窗口按钮专项，以及三平台录制引擎与两平台更新器回归。

Windows Python 3.12 的原生共用控件／Markdown／焦点专项为 **59 项通过**；完整离屏回归为 **1022 项通过、14 项按条件跳过**。原生窗口操作另由上述四档专项实际执行，未用离屏跳过结果替代。

对四档缩放 × 四种配色状态 × 三种窗口状态 × 三枚按钮的 **144 张悬停合成截图**另做像素复核：按实际对比度提取图标边界，中心偏差最大为 **1 个物理像素**。热区分别为 46×32、57／58×40、69×48、92×64 物理像素，分数缩放下共享边界无间隙。普通窗口与还原后的原生几何一致，最大化时 Qt 与 Win32 状态均为最大化，客户区位于工作区内。

标题栏桌面截图：[修改前](images/fluent-v2/windows-caption-before-dark.png) · [100%](images/fluent-v2/windows-caption-100-dark.png) · [125%](images/fluent-v2/windows-caption-125-dark.png) · [150%](images/fluent-v2/windows-caption-150-dark.png) · [200%](images/fluent-v2/windows-caption-200-dark.png)。以上为原生桌面截图的页头裁切，未修改按钮、颜色或字体；完整图保留在 artifact 与本地索引中。

GitHub 托管环境为 **Windows Server 2025（10.0.26100）**，不等同于用户的 Windows 11 实机。Qt 缩放矩阵验证绘制与输入的物理像素换算，不替代 Windows 系统显示缩放设置的实机矩阵。`HTMAXBUTTON` 命中和悬停截图不等于实际 Snap 布局浮层已验收；**Windows 11 实机、系统 DPI 切换、Snap 浮层、混合 DPI 多屏移动仍未计作通过**。

## 截图与复现

两套配色 × 深浅模式 × `900×640`、`1120×760`、`1320×860` 的原生全页面及关键弹窗保存在 `build/fluent-v2/`。完整本地浏览入口为 `build/fluent-v2/index.html`，按平台、配色、尺寸或状态筛选，收录完整矩阵与局部对比；主要截图同步到 `docs/images/`。Windows 完整矩阵下载于 `windows-ui-final/`，按钮专项下载于 `windows-final/`，原始证据同时保存在对应 CI artifact。

截图中的账号、任务、路径与更新版本为离线演示数据；更新弹窗显示的 `0.9.0b1` 用于演示可更新状态，不代表发布了该版本。像素复核数据保存在 `build/fluent-v2/windows-final/glyph-geometry.json`。

## 萤光小舞台补修

2026-10-23，用户补充指出 `live-watercolor-firefly.png` 左手六指。已用内置 imagegen 重绘为一根拇指与四根自然展开的手指，放大复核并保留[前后对比](images/fluent-v2/live-watercolor-firefly-hands.jpg)。原图仍为 1672×941，运行时背景、缩略图、十二景总览及原生／离屏文档预览同步更新，其余十一张背景未修改；当前资源总量为 8,130,355 字节（7.75 MiB）。

本次资产补修运行 `tests/test_builtin_backgrounds.py`：**20 项通过**；原生 Cocoa 与离屏图库截图工具均成功完成两套配色、深浅模式及三种尺寸检查。新预览位于 `build/fluent-v2/firefly-native/` 与 `firefly-offscreen/`，局部对比已加入本地索引。上方全量 pytest 与 CI 记录对应补修前的代码验证，本次没有重新执行整轮 CI。

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check bilibili_downloader tests packaging_hooks scripts
python -m compileall -q bilibili_downloader tests scripts
python -m scripts.capture_docs_screenshots --native --physical-pixels --color-theme star_trail --output-dir build/fluent-v2/native-full-final/star_trail
python -m scripts.capture_docs_screenshots --native --physical-pixels --color-theme bilibili_blue --output-dir build/fluent-v2/native-full-final/bilibili_blue
```

规范见 [Fluent Design](FLUENT_DESIGN.md)。本记录描述开发分支，已发布 beta 的历史验证保留在[第一轮可读性记录](UI_READABILITY_VALIDATION.md)。
