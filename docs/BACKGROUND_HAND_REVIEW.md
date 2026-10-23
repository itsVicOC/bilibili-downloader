# 小流十二景手部复核

2026-10-23，开发分支 `codex/fluent-design-polish`。逐张放大原图，按掌部、拇指连接、其余四指、关节和握持关系检查；合理遮挡不要求五指全部可见，像素画保留简化手形。

| 背景 | 处理与复核 |
| --- | --- |
| 云上收藏室 `download-anime-cloud` | 修正上下握胶片手部的拇指连接与重叠指形，消除多指错觉；[前后对比](images/fluent-v2/download-anime-cloud-hands.jpg) |
| 星轨驿站 `download-pixel-station` | 手部为简化像素轮廓，无新增分叉，保留原图 |
| 海风信笺 `download-watercolor-sea` | 托腮与持卡手有合理遮挡，保留原图 |
| 霓虹开播 `live-anime-neon` | 托腮握拳轮廓正常，另一手被衣物与身体遮挡，保留原图 |
| 午夜电台 `live-pixel-radio` | 托腮与桌面手为简化像素形，保留原图 |
| 萤光小舞台 `live-watercolor-firefly` | 持麦与掌心朝上手形按拇指、伸展指和弯曲指区分，保留原图 |
| 星轨调度 `tasks-anime-orbit` | 去掉伸展手多余的指形分叉，整理持盒手的遮挡关系；[前后对比](images/fluent-v2/tasks-anime-orbit-hands.jpg) |
| 银河货运站 `tasks-pixel-cargo` | 握终端与搭箱手保持简化轮廓，保留原图 |
| 星笺归档 `tasks-watercolor-letters` | 持信与托信手形有合理遮挡，保留原图 |
| 午后工坊 `settings-anime-workshop` | 整理握笔手弯曲指节与拇指连接、托调色盘手的指形；[前后对比](images/fluent-v2/settings-anime-workshop-hands.jpg) |
| 像素小屋 `settings-pixel-cottage` | 握水壶手为简化像素形，保留原图 |
| 薄荷手帐 `settings-watercolor-journal` | 握笔手与平放手的结构、遮挡合理，保留原图 |

三张修改图使用内置 `image_gen` 编辑，原图宽高仍为 1672×941。已复核人物身份、服装、构图、光照和画风，背景与缩略图由 `scripts/build_background_assets.py` 统一导出。其余九张原图及对应运行时资源保持不变。

运行时插画为 2560×1440 WebP，像素画为 640×360 PNG，缩略图为 320×180 PNG；全十二景及缩略图合计 **7.84 MiB**，低于 12 MiB 预算。全部 `builtin:` 引用和资源路径保持兼容。修改前原图可从 `v0.8.9b1` 标签取得，原图现存于 `docs/images/backgrounds/originals/`，运行时文件位于 `bilibili_downloader/gui/assets/backgrounds/`。

## 实际编辑提示词

每次只提供对应原图作为编辑目标，`transparent_background=false`。以下为三次调用的提示词，未使用 CLI 或外部图片接口。

### 星轨调度

```text
Edit target: the attached BiliFlow wallpaper, tasks-anime-orbit. Use case: precise-object-edit. Correct ONLY the anatomy of the girl's outstretched hand at the left of her body (approximately x=43%-54%, y=24%-37% of the image). It currently has an extra finger/ambiguous finger branches. Redraw this small hand naturally in the SAME pose with exactly ONE thumb and FOUR fingers, clean distinct joints, elegant relaxed fingers, no extra protrusions. Also ensure the small hand supporting the box on the right has a natural five-digit structure with reasonable occlusion. Preserve everything outside these hand regions as closely as possible: exact girl's identity, face, hair, clothes, cuffs, body pose, blue/gold fantasy anime style, floating boxes, architecture, lighting, palette and composition. Do not redraw the character or background, do not change the gesture or box position. Preserve the original landscape aspect ratio and full framing. No new objects, no text, no watermark. High fidelity local repair; this is a production wallpaper correction, not a redesign.
```

### 云上收藏室

```text
Use case: precise-object-edit. Edit this existing BiliFlow wallpaper, download-anime-cloud, with a VERY SMALL hand-anatomy repair. Correct only the two hands holding the blue film strip, especially the lower hand near x=75%-81%, y=56%-67% whose overlapping digit contours suggest an extra finger. Each hand must have exactly ONE thumb and FOUR fingers, naturally bent around the film, with clear thumb connections, plausible joints and sensible occlusion, no sixth finger, no fused or forked fingers. Keep the original hand positions and the same delicate grip. Preserve the entire rest of the image as closely as possible: same face and identity, blue hair, star clip, ribbons, sleeves, clothing, film strip placement, floating castles, flowers, blue-white-gold anime illustration style, original colors and lighting. Do NOT redraw the scene or change the composition. Preserve exactly the input width and height, full landscape framing, no crop. No extra objects, text, or watermark.
```

### 午后工坊

```text
Use case: precise-object-edit. Locally repair ONLY the two hands of the girl in this existing BiliFlow wallpaper, settings-anime-workshop. The hand holding the brush (x=57%-67%, y=41%-56%) has confusing curled finger/thumb contours that can read as six fingers: make it a natural delicate artist's grip, exactly ONE thumb and FOUR fingers with plausible occlusion, clean joints and no fused/forked/extra digits. Keep the brush direction and both hand positions unchanged. The hand holding the palette (x=74%-82%, y=61%-73%) should likewise have a clearly plausible five-digit structure and natural palette grip. Preserve all other pixels and scene details as closely as possible: same face, blue hair, ribbons, star ornament, clothing and sleeve edges, body pose, brush, palette, flowers, workshop, sunlight, colors, textures, framing, and delicate anime illustration style. This is a hand-only retouch, not a redesign. Maintain EXACT original image width and height and landscape framing; no crop, no text, no watermark, no new objects.
```
