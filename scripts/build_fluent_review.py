#!/usr/bin/env python3
"""Build an offline review index from unmodified UI captures and a concept image."""

import argparse
from html import escape
from pathlib import Path
from urllib.parse import quote


def build(root: Path) -> tuple[Path, int]:
    root = root.resolve()
    pictures = sorted(root.rglob("*.png"))
    comparisons = []
    for title, name in (
        ("单个下载 · 浅色 · 1320", "biliflow-download-light-1320.png"),
        ("设置 · 深色 · 900", "biliflow-settings-dark-900.png"),
        ("任务中心 · 深色 · 900", "biliflow-tasks-dark-900.png"),
    ):
        pair = []
        for phase, label in (("before", "精修前"), ("after", "精修后")):
            path = root / phase / "star_trail" / name
            if path.exists():
                url = quote(path.relative_to(root).as_posix())
                pair.append(f'<figure><figcaption>{label} · 离屏</figcaption><a href="{url}"><img src="{url}" alt="{label}" loading="lazy"></a></figure>')
        comparisons.append(f'<h3>{title}</h3><div class="pair">{"".join(pair)}</div>')
    groups = {}
    for path in pictures:
        relative = path.relative_to(root).as_posix()
        group = str(path.relative_to(root).parent)
        url = quote(relative)
        caption = escape(relative)
        groups.setdefault(group, []).append(
            f'<figure data-name="{caption}"><a href="{url}"><img src="{url}" loading="lazy" alt="{caption}"></a><figcaption>{caption}</figcaption></figure>'
        )
    gallery = "".join(f'<details><summary>{escape(name)} · {len(items)} 张</summary><div class="grid">{"".join(items)}</div></details>' for name, items in groups.items())
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>BiliFlow 第三轮 Fluent 精修复核</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif;background:light-dark(#f7f5fb,#14131b);color:light-dark(#292430,#f4f1f7)}
body{max-width:1600px;margin:auto;padding:24px}h1{font-size:26px}p{line-height:1.7}a{color:inherit}img{display:block;width:100%;height:auto;border-radius:8px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
figure{margin:0;padding:12px;background:light-dark(#fff,#201e2a);border-radius:12px;min-width:0}figcaption{font-size:12px;overflow-wrap:anywhere;padding:8px 0}
details{margin:16px 0}summary{padding:14px;cursor:pointer;font-weight:600}input{font:inherit;width:min(680px,90%);padding:12px;border:1px solid #81798c;border-radius:8px}button{font:inherit;padding:10px;margin:8px;border-radius:8px;cursor:pointer}
@media(max-width:800px){.pair{grid-template-columns:1fr}body{padding:12px}}
</style><h1>BiliFlow 第三轮 Fluent Design 精修</h1>
<p>所有界面图片均来自隔离的离线演示数据，保留原始捕获内容。前后对比使用相同离屏后端；native 为 macOS 原生物理像素，windows 为 Windows CI 原生截图。概念图仅用于对照方向。</p>
__COMPARISONS__<h2>完整截图索引 · __COUNT__ 张</h2>
<p><input id="search" placeholder="筛选：download、settings、900、dark、glass、refinement…"><button id="expand">展开全部</button></p>
__GALLERY__<script>
document.querySelector('#search').addEventListener('input',event=>{const text=event.target.value.toLowerCase();document.querySelectorAll('details').forEach(group=>{let count=0;group.querySelectorAll('figure').forEach(item=>{const match=item.dataset.name.toLowerCase().includes(text);item.hidden=!match;if(match)count++});group.hidden=!count;if(text&&count)group.open=true})});
document.querySelector('#expand').addEventListener('click',()=>document.querySelectorAll('details:not([hidden])').forEach(group=>group.open=true));
</script></html>"""
    page = page.replace("__COMPARISONS__", "".join(comparisons)).replace("__COUNT__", str(len(pictures))).replace("__GALLERY__", gallery)
    target = root / "index.html"
    target.write_text(page, encoding="utf-8")
    return target, len(pictures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("build/fluent-v3"))
    path, count = build(parser.parse_args().root)
    print(f"{path}: {count} images")


if __name__ == "__main__":
    main()
