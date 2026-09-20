# 安全策略

## 支持版本

安全修复只面向最新 GitHub Release 和 `main` 分支。旧版本用户应先升级到最新版再确认问题是否仍然存在。

## 报告漏洞

请不要为未修复漏洞创建公开 Issue。优先使用仓库的 [GitHub Private Vulnerability Reporting](https://github.com/itsVicOC/bilibili-downloader/security/advisories/new) 提交报告。

报告中请包含受影响版本、复现条件、潜在影响和建议修复方式。不要发送真实的 SESSDATA、Cookie、个人下载链接或其他敏感数据；如必须提供验证数据，请先构造无效样例。

维护者会尽量在 7 天内确认收到报告，并在完成影响评估后同步修复计划。修复发布前请勿公开漏洞细节。

## 凭据与本地数据

- 应用只保留 `SESSDATA`、`DedeUserID`、`DedeUserID__ckMd5`、`bili_jct`、`sid`、`b_nut`、`buvid3`、`buvid4`、`buvid_fp` 和 `_uuid`；其他 Cookie 在解析后立即丢弃。
- 白名单 Cookie 以版本化 `auth-cookie-bundle-v1` 记录写入 macOS Keychain、Windows Credential Locker 或 Linux Secret Service 等系统凭据库。
- 系统凭据库不可用时，Cookie 仅保留在当前进程内存中，不写入配置、任务数据库、元数据或错误报告；界面会提示重启后需重新登录。
- 旧配置或旧凭据库中的 SESSDATA 会尝试迁入新记录。迁入失败时仅用于当前会话，并从后续配置保存中移除。
- 日志脱敏覆盖全部白名单 Cookie、PGC 播放 URL 及签名查询参数。Cookie 只发送给受信任的 Bilibili API/网页域名，不发送给媒体 CDN。
- 日志、Issue、截图和终端输出中不得包含有效 Cookie 或带鉴权参数的媒体 URL。
- 仅从本仓库 Release 页面下载构建产物，并在发布页面核对文件名称。
