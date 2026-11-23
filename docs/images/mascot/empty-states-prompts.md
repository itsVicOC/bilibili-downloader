# 小流空态插画生成记录

素材使用内置 ImageGen 逐张生成。角色参考 [小流放大图](xiaoliu-preview.png)。各图按实际透明区域裁切、最近邻缩放并置于 96×54 RGBA 画布。运行素材位于 `bilibili_downloader/gui/assets/xiaoliu_state_*.png`。

## 共享提示词

Create a new static pixel-art illustration for the BiliFlow desktop app. Reference image is the canonical Xiao Liu character only. Preserve her short bright blue bob with white tips, small gold star clip on the viewer's left, cyan side ribbon on the viewer's right, short white-and-blue jacket, navy skirt, dark short boots, and two-head chibi proportions. Authentic early handheld-game pixel art, chunky square pixel clusters and a restrained 24-color opaque palette plus transparent pixels. Deep navy outline, flat deliberate highlights, no gradients, no antialias, no smooth vector lines. Frame a single full figure with the primary prop in a centered wide composition approximately 16:9, both large and closely grouped, with some clear breathing room all around. Plan the cluster as if painted on a 96 by 54 logical-pixel canvas. Everything outside the figure and prop must be genuinely transparent. No floor, shadow, colored background, frame, captions, lettering, signature, extra characters, or watermark. Output a single finished illustration.

## 场景提示词

### `download_source`

One character and one object, isolated on true transparency. Xiao Liu stands on the left in an energetic welcome pose, reaches her right hand towards the right edge, and offers exactly two interlocking chain links floating above her hand. Make the two diagonal interlocking cyan and gold ovals unusually large with clear inner holes, about one third the full character's height. Composition stops immediately after the links, leaving the right margin blank transparent. Draw only the girl and the chain links. No interface, form field, outline box, white horizontal bar, words, icons beyond the two links, or other decoration.

### `live_empty`

Xiao Liu wears over-ear radio headphones behind the signature star hair clip. She reaches down to tune a compact teal tabletop radio with a raised aerial alongside her, visibly listening to an incoming signal. One tiny pixel signal mark near the aerial.

### `downloads_empty`

Xiao Liu stands in a breezy welcoming pose with one hand up in a wave, leaning on the edge of a low, open, visibly empty blue download inbox tray beside her. The tray has a single tiny down-arrow silhouette.

### `downloads_filtered`

Xiao Liu leans right inspecting a large, distinctly funnel-shaped teal filter, held up in her right hand. The funnel is a bold, single geometric prop: wide flat-topped cone narrowing into a straight stem, with light cyan highlights and dark outline. In the other hand show a cream checklist at a slight angle with precisely three dark square marks. Move the funnel and checklist to opposite sides, both away from the face and clearly distinguishable. No floating question marks, stars, typography or interface elements.

### `recordings_empty`

Xiao Liu in a focused pose standing to one side of a clearly recognizable turquoise and cobalt video camera on a short, light blue tripod. Her hand gently adjusts the camera. To work on a near-black theme the camera has bright cyan surface panels, a large pale lens ring and a visibly light blue tripod with a navy outline. Show the full character and bright camera, no red alarm, no stage or backdrop.

### `recording_history_empty`

Xiao Liu sits with her legs folded sideways, carefully flipping an open archive notebook in her lap. A short curled film leader beside the book signals archived recording sessions.

### `files_empty`

Xiao Liu hugs an oversized open pastel gold file folder to her chest with both hands. The folder is visibly empty from the opening at top. Show her taking a small step as if carrying it to storage.

### `files_filtered`

Xiao Liu bends forward and looks with one large magnifying glass at a small blank file tag on the lower right. The round teal-rimmed glass should make the pose easy to read.

### `files_loading`

Xiao Liu sits with her chin supported in one hand, watching a teal-and-gold hourglass standing beside her. The hourglass must have a single clear hourglass silhouette and small grains in the lower bulb.

### `files_error`

Xiao Liu crouches gently, reaching for the two unplugged but matching ends of a blue data cable on the ground. Make both connectors clearly separate, near her hands. A quiet, helpful mood, no warning signs.

### `batch_filtered`

Xiao Liu looks across three BIG distinctly separate small rectangular video cards fanned out between her hands at chest level, not obscuring her face. Each rectangular card has an obvious large light play triangle: pastel teal card on left angled, blue center card straight, light lilac card tilted to right. Flat empty color fields within all cards, uncluttered; keep three clearly separate silhouettes and color areas. No text, sparkles, tiny buttons or background.

### `parts_filtered`

Xiao Liu extends both arms and compares two separate long rectangular vertical film strips, one strip in each hand well away from her body. Each strip is mostly gold or light turquoise outlined in navy and shows two large rectangular empty frame cutouts separated by a crisp crossbar and a few perforations on the edges. They read clearly as film strips at 54 pixels tall. Her head tilts thoughtfully. No text, question marks, floating ornaments, or other symbols.

### `naming_filtered`

Xiao Liu leans over one blank cream-colored label tag with a bold round hole, holding a short gold pencil near it. Show the action clearly and leave the tag blank.
