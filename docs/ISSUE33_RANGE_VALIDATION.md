# #33 海外 CDN 分块下载修复与验证

2026-11-18，针对 `v0.8.12` 后美国用户仍收到 HTTP 403 的反馈，确认 Akamai 媒体请求需要带明确结束位置的 Range。播放接口可以正常返回流地址，但不带 Range 和 `bytes=0-` 均被拒绝；有限范围请求返回 206。

## v0.8.13 修复行为

- 首次下载和续传统一按 4 MiB 的有界范围请求；获知总大小后将最后一块限制到文件末尾，并支持服务端返回更小的块。
- 每块核对 Content-Range 的起点、终点、总大小及实际字节数，拒绝截断、越界、总大小变化和压缩编码。中断保留已下载前缀，其他 CDN 或后续重试从实际文件大小续传。
- 服务端忽略 Range 返回 200 时按完整响应覆盖部分文件；仅当 416 明确证明本地大小等于远端大小时确认完成。
- 保留 HTTPS、域名、端口、逐次重定向和凭据隔离规则。只有整条流完成校验后才报告 100% 并写入完成标记。

## 本地与美国实测

本地完整回归 **1420 项通过、6 项平台专项跳过**，Ruff、编译与差异检查通过，见[本地记录](validation/issue33-ranges/local-tests.json)。新增用例覆盖连续分块、断点与备用 CDN、200/206/416、未知长度的完整响应、异常范围／长度／编码、取消、重定向及完成进度。

[美国 Windows／Linux 验证任务](https://github.com/itsVicOC/bilibili-downloader/actions/runs/44250821937) 两项成功，两个平台各通过 45 项下载器与 Range 回归。Cloudflare 和 Bilibili 的地区查询均确认美国；全部 Bilibili 请求为匿名请求，未读取账号或配置。

| 检查 | 美国 Windows | 美国 Linux |
| --- | --- | --- |
| 原请求的视频／音频响应 | 403／403 | 403／403 |
| 有界 Range 视频／音频 | 完整下载，全部 206 | 完整下载，全部 206 |
| 视频字节数 | 20,872,903 | 20,872,903 |
| 音频字节数 | 1,167,163 | 1,167,163 |
| MP4 合并及完整解码 | 通过，212.39 秒，含视频和音频 | 通过，212.39 秒，含视频和音频 |
| 主动中断后续传 | 从 2,162,688 字节继续，SHA-256 与完整下载一致 | 从 2,162,688 字节继续，SHA-256 与完整下载一致 |

验证使用实际 `StreamDownloader.download()` 和 FFmpeg 合并流程，并完整解码输出，而非仅读取文件头。中断时没有完成标记，续传完成后标记大小与文件一致，进度单调且仅结束时达到 100%。两个平台原始视频、音频的 SHA-256 分别相同；MP4 仅要求音视频与完整解码一致，不要求不同平台 FFmpeg 输出的容器哈希相同。

实际运行的下载器源码已与本地逐字节核对；Windows Git 检出使用 CRLF，其原始源码 SHA-256 与 LF 平台不同，核对同时覆盖两种换行。见[汇总与源码哈希](validation/issue33-ranges/verification.json)、[Windows 报告](validation/issue33-ranges/windows.json)、[Linux 报告](validation/issue33-ranges/linux.json)及[工作流记录](validation/issue33-ranges/workflow.json)。

## 范围与重跑

样本为公开视频 `BV1GJ411x7h7`、CID `137649199` 的 480P AVC 与音频流；报告者截图没有 BV 号，因此没有声称验证了截图原视频、全部画质或所有地区。此次下载专项不涉及真实账号、会员内容、GUI 安装包或直播引擎；本修复纳入 `v0.8.13`，发行构建与公开附件核验另见[构建与发布记录](BUILDING.md)。

临时媒体在完成后删除；仓库和工作流附件仅保留脱敏 JSON／测试结果，不保留 Cookie、带签名的播放 URL 或媒体文件。可使用隔离目录重跑：

```bash
python -m scripts.smoke_cdn_ranges --expect bounded --require-country US --ffmpeg /path/to/ffmpeg --report build/cdn-range-validation.json
```

该命令显式访问公开接口并下载临时样本，不属于常规离线单元测试；不会切换代理或网络出口。

## 连续传输与自动回退

首次请求使用连续 GET，断点请求使用开放式 Range。连续请求收到 `403`，或同一候选的响应体连续两次读取失败后，使用 4 MiB 有界 Range 从实际写入的位置继续。每次请求继续核对媒体长度和偏移。

用同一份 128 MiB 数据比较 `v0.8.13` 和新策略。HTTPX 模拟传输对每个响应头施加 50 ms 延迟，交替运行五轮并取中位数。两组输出的 SHA-256 一致，以下吞吐量为此模拟环境中的结果。

| 策略 | 主体请求次数 | 传输耗时 | 有效吞吐量 |
| --- | ---: | ---: | ---: |
| `v0.8.13` 固定 4 MiB 分块 | 32 | 1.868 秒 | 68.54 MiB/s |
| 连续传输 | 1 | 0.112 秒 | 1146.74 MiB/s |

本次出口分配的普通 CDN 上，公开样本的视频和音频分别通过一次 `200` 下载完成。MP4 合并与完整解码通过。主动中断后从 2,162,688 字节发出开放式 Range，收到一次 `206` 并续传至末尾，SHA-256 与完整下载一致。

普通 CDN 实测的出口没有获得 #33 的 Akamai 流地址。离线合成音视频也覆盖了 `403` 后切换有界 Range、完整解码与续传 SHA-256。

正常线路可使用同一公开样本复跑。脚本记录请求类型、响应状态和范围。

```bash
python -m scripts.smoke_cdn_ranges --expect fast --ffmpeg /path/to/ffmpeg --report build/cdn-fast-validation.json
```

## v0.9.0b4 美国 Akamai 实测

2026-11-20 的 [GitHub Actions 实测](https://github.com/itsVicOC/bilibili-downloader/actions/runs/44732206547) 在 Windows 和 Linux 通过。两个 runner 的 Cloudflare 和 Bilibili 地区查询均确认为美国。实测使用与 `v0.8.13` 相同的公开样本，匿名请求播放接口返回的 `upos-hz-mirrorakam.akamaized.net` 音视频流。

| 检查 | 美国 Windows 和 Linux |
| --- | --- |
| 首次视频／音频传输 | 无 Range 返回 `403`，自动改用有界 Range 后全部返回 `206` |
| 视频／音频大小 | 20,872,903 字节／1,167,163 字节，两端原始流 SHA-256 分别一致 |
| MP4 合并和完整解码 | 通过，212.39 秒，含视频和音频 |
| 中断后续传 | 从 2,162,688 字节发送开放式 Range，收到 `403` 后从同一偏移按有界 Range 续传，SHA-256 与完整视频流一致 |
| 下载器和 Range 回归 | 两端各 62 项通过 |

核对了实测报告内下载器源码的 SHA-256，分别与发布源码的 LF 和 CRLF 内容一致。临时媒体已清理。报告记录请求类型、范围与响应状态，并省略完整流地址和凭据。[Linux 报告](validation/issue33-ranges/beta4-linux.json) · [Windows 报告](validation/issue33-ranges/beta4-windows.json)

```bash
python -m scripts.smoke_cdn_ranges --require-country US --expect bounded --ffmpeg /path/to/ffmpeg --report build/cdn-akamai-us.json
```
