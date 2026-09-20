# BiliFlow 文档中心

这里汇总 BiliFlow 的使用、排障、合规、开发和发布资料。第一次使用建议先阅读项目首页的[下载与安装](../README.md#下载与安装)，再按下面的路线继续。

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

## 文档地图

| 文档 | 主要内容 | 目标读者 |
|---|---|---|
| [README](../README.md) | 项目概览、截图、安装、五分钟上手 | 所有人 |
| [用户指南](USER_GUIDE.md) | GUI、CLI、任务状态、登录、目录模板与本地数据 | 使用者 |
| [故障排查](TROUBLESHOOTING.md) | 启动、解析、画质、FFmpeg、网络、登录与恢复 | 使用者、支持人员 |
| [版权与合规说明](COPYRIGHT.md) | 支持边界、禁止用途与权利人反馈 | 所有人 |
| [构建与发布](BUILDING.md) | 环境、测试、文档截图、打包、签名与 Release | 维护者 |
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
