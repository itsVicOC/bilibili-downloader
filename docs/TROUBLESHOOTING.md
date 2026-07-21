# 故障排查

## 应用无法启动

### macOS 提示无法验证开发者

当前 Release 未进行 Apple 公证。在“系统设置 → 隐私与安全性”中找到拦截提示并选择“仍要打开”。请确认安装包来自本仓库 Release 页面。

### Windows Defender 或 SmartScreen 提示未知应用

预构建包尚未购买商业代码签名证书。核对 Release 来源和文件名后，可通过“更多信息”选择运行。不要从第三方下载站获取重新打包版本。

### 源码启动提示 `PySide6 not installed`

确认已激活虚拟环境并安装项目依赖：

```bash
python -m pip install -c constraints.txt -e ".[dev]"
python -m bilibili_downloader
```

## FFmpeg 不可用或合并失败

先检查：

```bash
ffmpeg -version
```

如果终端可用但应用仍找不到，请在“下载设置”中选择 FFmpeg 可执行文件。Windows 应选择 `ffmpeg.exe`，不要选择安装目录。

合并失败时确认输出目录可写、磁盘空间充足，并避免其他程序占用同名目标文件。HEVC 或 AV1 下载不要求系统播放器能解码，但播放时需要对应解码支持；兼容性优先可选择 AVC/H.264。

## 无法解析链接

- 确认输入是 BV 号、AV 号、视频详情页 URL 或 b23.tv 短链。
- 合集、番剧、课程、直播和动态页面目前不支持，请粘贴其中单个视频的链接。
- b23.tv 需要联网展开；代理、DNS 或公司网络可能阻止跳转。
- 浏览器能打开但应用失败时，稍后重试并确认系统时间准确。

## 看不到高画质或指定编码

应用只显示接口实际返回的流。1080P+、4K、HDR、Dolby Vision 和 8K 通常要求登录、会员权限、视频本身提供对应规格，且不一定同时提供 AVC、HEVC、AV1。

重新登录并解析后仍不存在，表示当前账号或视频没有该规格。应用不会绕过平台权限。

## 登录失败

- 手动登录只填写 `SESSDATA` 的值，不要粘贴整段 Cookie 请求头。
- SESSDATA 可能过期，退出网页账号后旧值也可能失效。
- 扫码接口可能因 Bilibili API 变化临时不可用，可改用手动方式。
- Linux 无 Secret Service 时会回退到本地配置。安装并解锁系统密钥环可恢复安全存储。

切勿在公开 Issue 中提供真实 Cookie。

## 下载中断或速度异常

- 重试会优先复用可续传临时文件，并在主链接失败后尝试备用 CDN。
- CDN 是否支持 Range、链接是否过期以及网络代理均会影响续传。
- 将并发数降低到 1–3，排除带宽、磁盘或服务器限速。
- 输出目录位于网络盘或同步盘时，先改到本地磁盘验证。

## 字幕或弹幕缺失

字幕和弹幕必须由对应视频实际提供。部分字幕轨需要登录权限；弹幕关闭、视频无字幕或接口未返回轨道时不会生成文件。

## 配置损坏

应用会把无法解析的配置备份为同目录的 `config.json.bak` 并恢复默认设置。配置目录在 macOS 为 `~/Library/Application Support/BiliFlow`，Windows 为 `%APPDATA%\\BiliFlow`，Linux 为 `$XDG_CONFIG_HOME/biliflow`（默认 `~/.config/biliflow`）。若问题持续，关闭应用后移动 `config.json`，再重新启动配置。

报告仍未解决的问题时，请按 [CONTRIBUTING.md](../CONTRIBUTING.md) 提供环境、复现步骤和已脱敏日志。
