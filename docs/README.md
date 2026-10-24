# BiliFlow 文档中心

这里汇总 BiliFlow 的使用、排障、合规、开发和发布资料。第一次使用建议先阅读项目首页的[下载与安装](../README.md#下载与安装)，再按下面的路线继续。

项目入口：[官方网站 · 1008.si](https://1008.si/) · [中文 README](../README.md) · [English README](../README.en.md)。详细指南目前以简体中文为主。

`v0.8.9` 正式版汇总四个 beta 阶段的 Fluent 精修、窗口记忆、目录邻近操作、任务整行悬停、录制历史移除与撤销和前台剪贴板识别。用户已确认 Windows／macOS 实机验证完成；功能说明与截图见[第五轮验收](FLUENT_V5_VALIDATION.md)，安装包见 [0.8.9 正式版](https://github.com/itsVicOC/bilibili-downloader/releases/tag/v0.8.9)。

`v0.8.9b3`（0.8.9 beta 3）基于 `codex/fluent-design-polish` 分支，包含第三、四轮 Fluent 精修、矮窗口紧凑布局和主窗口大小／位置／最大化状态记忆。截图、前后对比及验证范围见[第三轮验收](FLUENT_V3_VALIDATION.md)和[第四轮验收](FLUENT_V4_VALIDATION.md)，安装包见 [beta 3 预发布版](https://github.com/itsVicOC/bilibili-downloader/releases/tag/v0.8.9b3)。

`v0.8.9b2`（0.8.9 beta 2）基于 `codex/fluent-design-polish` 分支提供第二轮 Fluent 精修。Windows 自绘按钮、Markdown 更新说明、背景手部与截图记录见[第二轮验收](FLUENT_V2_VALIDATION.md)和[背景手部复核](BACKGROUND_HAND_REVIEW.md)。

`v0.8.9b1`（0.8.9 beta1）的界面规范见 [Fluent Design 精修](FLUENT_DESIGN.md)，包含设计参数、动效规则与视觉验证方法；粉底白字、文本选区及 Windows 标题栏悬停的结果见[可读性验收记录](UI_READABILITY_VALIDATION.md)。

本次文档对应 `v0.8.9` 正式版。窗口激活、最大化与还原及双平台界面检查见[视觉规范与验证](UI_DESIGN.md)，小流的十二套动画与时段规则见[小流设计与预览](MASCOT_DESIGN.md)，五类设置、模式与背景玻璃模糊见[用户指南](USER_GUIDE.md)，版本变化和验证范围见[更新日志](../CHANGELOG.md#v089---2026-10-24)。

## 推荐阅读路线

### 我想使用 BiliFlow

1. 从 [GitHub Releases](https://github.com/itsVicOC/bilibili-downloader/releases/latest) 选择适合系统的 full 或 lite 安装包。
2. 阅读[用户指南](USER_GUIDE.md)，完成解析、规格选择、批量导入和任务管理。
3. 启动、FFmpeg、登录或下载异常时查阅[故障排查](TROUBLESHOOTING.md)。
4. 下载前确认[版权与合规说明](COPYRIGHT.md)中的使用边界。

### 我想参与开发

1. 按[贡献指南](../CONTRIBUTING.md)准备分支、测试和 PR。
2. 按[构建与发布](BUILDING.md)配置开发环境并运行完整验证。
3. 涉及凭据、网络边界或漏洞时遵循[安全策略](../SECURITY.md)。
4. 新增或替换素材时同步检查[第三方素材](../THIRD_PARTY_NOTICES.md)。
5. 后续功能与验收安排见[迭代计划](ROADMAP.md)，其中内容为拟实施范围。

## 文档地图

| 文档 | 主要内容 | 目标读者 |
|---|---|---|
| [README](../README.md) | 项目概览、截图、安装、五分钟上手 | 所有人 |
| [English README](../README.en.md) | 英文项目介绍、安装、快速上手与常见问题 | 英文读者 |
| [用户指南](USER_GUIDE.md) | GUI、CLI、任务状态、登录、目录模板与本地数据 | 使用者 |
| [直播录制](LIVE_RECORDING.md) | 房间监控、录制历史、原生引擎和发布验收状态 | 使用者、维护者 |
| [小流设计与预览](MASCOT_DESIGN.md) | 十二套动画、五个时段、完整 / 迷你布局及素材记录 | 使用者、维护者 |
| [内置背景图库](BUILTIN_BACKGROUNDS.md) | 十二景作品、画风、页面推荐与背景选择 | 使用者 |
| [视觉规范与验证](UI_DESIGN.md) | 统一组件、页面导航、主题与尺寸截图、关键状态及验证范围 | 使用者、维护者 |
| [故障排查](TROUBLESHOOTING.md) | 启动、解析、画质、FFmpeg、网络、登录与恢复 | 使用者、支持人员 |
| [版权与合规说明](COPYRIGHT.md) | 支持边界、禁止用途与权利人反馈 | 所有人 |
| [构建与发布](BUILDING.md) | 环境、测试、文档截图、打包、签名与 Release | 维护者 |
| [迭代计划](ROADMAP.md) | 产品目标、分阶段交付、依赖、发布门槛与试用指标 | 维护者、贡献者 |
| [贡献指南](../CONTRIBUTING.md) | Issue、代码约定、测试与 PR 清单 | 贡献者 |
| [安全策略](../SECURITY.md) | 私密漏洞报告、凭据与本地数据边界 | 研究者、维护者 |
| [第三方素材](../THIRD_PARTY_NOTICES.md) | FFmpeg、图标、图片与许可证 | 维护者 |
| [更新日志](../CHANGELOG.md) | 版本新增、修改、修复与安全变化 | 所有人 |

## 常用入口

- GUI：`python -m bilibili_downloader`
- 查看 CLI 帮助：`python -m bilibili_downloader --help`
- 检查来源解析：`python -m bilibili_downloader test <来源>`
- 查看下载参数：`python -m bilibili_downloader download --help`
- 运行测试：`pytest -q`
- 重新生成文档截图：`python scripts/capture_docs_screenshots.py`

## 文档约定

- 命令默认从仓库根目录执行；Windows 专用命令会明确标注 PowerShell。
- `BV1...`、`ep123`、`ss123`、账号名与任务内容可能是演示占位符，不代表可下载的真实作品。
- 文档和截图不得包含有效 Cookie、带签名的播放 URL、个人目录、账号标识或受版权保护的媒体内容。
- Bilibili 接口和授权规则可能变化；文档描述的是当前仓库版本的行为，版本差异以[更新日志](../CHANGELOG.md)为准。
