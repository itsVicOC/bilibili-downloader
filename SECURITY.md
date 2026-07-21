# 安全策略

## 支持版本

安全修复只面向最新 GitHub Release 和 `main` 分支。旧版本用户应先升级到最新版再确认问题是否仍然存在。

## 报告漏洞

请不要为未修复漏洞创建公开 Issue。优先使用仓库的 [GitHub Private Vulnerability Reporting](https://github.com/itsVicOC/bilibili-downloader/security/advisories/new) 提交报告。

报告中请包含受影响版本、复现条件、潜在影响和建议修复方式。不要发送真实的 SESSDATA、Cookie、个人下载链接或其他敏感数据；如必须提供验证数据，请先构造无效样例。

维护者会尽量在 7 天内确认收到报告，并在完成影响评估后同步修复计划。修复发布前请勿公开漏洞细节。

## 凭据与本地数据

- SESSDATA 优先写入 macOS Keychain、Windows Credential Locker 或 Linux Secret Service 等系统凭据库。
- 系统凭据库不可用时，本地配置仅进行兼容性混淆，不应视为加密保险箱。请保护当前系统账号和 `~/.bilibili-downloader/config.json`。
- 日志、Issue、截图和终端输出中不得包含有效 Cookie 或带鉴权参数的媒体 URL。
- 仅从本仓库 Release 页面下载构建产物，并在发布页面核对文件名称。
