"""Package the offline detail audit into a browsable, dependency-free review."""

import argparse
import gzip
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

TITLES = {
    'input': '输入框', 'multiline': '文本区', 'readonly': '只读路径', 'password': '密码输入',
    'combo': '下拉框', 'checkbox': '复选框', 'card': '附件卡片', 'primary': '主按钮',
    'secondary': '次按钮', 'danger': '危险按钮', 'stepper': '数字框', 'slider': '滑块',
    'dialog-pages': '分 P 选择', 'dialog-attachments': '附件补全',
    'dialog-attachments-unavailable': '附件不可用', 'dialog-result': '保存结果',
    'dialog-naming-fields': '命名字段', 'dialog-relocate': '目录迁移',
    'dialog-room-settings': '直播间设置', 'dialog-account': '账号',
    'dialog-account-expired': '账号过期', 'dialog-login-cookie': 'Cookie 登录',
    'dialog-login-qr': '二维码登录', 'dialog-login-qr-expired': '二维码过期',
    'dialog-update': '更新', 'dialog-close': '关闭窗口', 'dialog-close-no-tray': '无托盘时关闭',
    'dialog-background-gallery': '背景图库', 'dialog-file-operation': '文件操作',
    'dialog-settings-download': '下载设置', 'dialog-settings-live': '直播设置',
    'dialog-settings-appearance': '外观设置', 'dialog-settings-tools': '工具设置',
    'dialog-settings-about': '关于', 'dialog-media-copy': '另存媒体',
    'dialog-output-review': '下载配置复核', 'dialog-copyright': '版权确认',
    'dialog-batch': '独立批量导入', 'dialog-source-errors': '来源解析详情',
    'dialog-file-open-file': '选择文件', 'dialog-file-save-file': '保存文件',
    'dialog-file-directory': '选择目录',
}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def put(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def clean(value):
    content = json.dumps(value, ensure_ascii=False)
    content = re.sub(r'/private/var/folders/[^" ]+/T/[^" ]*?biliflow[^" /]*', '~/BiliFlow-demo', content)
    content = re.sub(r'/var/folders/[^" ]+/T/[^" ]*?biliflow[^" /]*', '~/BiliFlow-demo', content)
    return json.loads(content)


def catalog(after, native):
    registry = read_json(after / 'instance-checks.json')
    entries, known = [], set()
    messages = {r['id']: r for r in read_json(after / 'message-entries.json')}
    for suffix in ('', '-font125', '-font150'):
        for row in read_json(after / f'component-checks{suffix}.json'):
            kind = row['id'].split(':')[0]
            entries.append({**row, 'title': TITLES[kind], 'category': '组件', 'size': [], 'key': kind})
            known.add(row['image'])
    for row in registry['cases']:
        if row['image'] in known:
            continue
        known.add(row['image'])
        name = row['name']
        entry = messages.get(name)
        category = '弹窗' if row['dialog'] else '工作区'
        if name.startswith('detail-background'):
            category = '背景'
        title = TITLES.get(name, entry['title'] if entry else name)
        extra = ''
        if entry:
            extra = f"{entry['source']}:{entry['line']} · {entry['entry']}"
            if entry['dynamic_sample']:
                extra += ' · 动态内容采用离线示例'
        entries.append({**row, 'category': category, 'title': title, 'key': name, 'state': '', 'note': extra})
    for path in sorted(after.glob('floating-*.png')):
        theme = 'star_trail' if 'star_trail' in path.name else 'bilibili_blue'
        entries.append({'image': path.name, 'title': '菜单' if 'menu' in path.name else '下拉弹层',
                        'category': '浮层', 'theme': theme, 'mode': 'dark' if '-dark-' in path.name else 'light',
                        'font_scale': 1, 'size': [], 'key': path.stem, 'state': ''})
        known.add(path.name)
    for path in sorted(after.glob('*.png')):
        if path.name not in known:
            entries.append({'image': path.name, 'title': path.stem, 'category': '补充', 'theme': '',
                            'mode': '', 'font_scale': 1, 'size': [], 'key': path.stem, 'state': ''})
    for row in entries:
        row['after'] = 'images/after/' + row['image']
        if (native / row['image']).exists():
            row['native'] = 'images/native/' + row['image']
    return entries, registry


PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>BiliFlow 全界面细节验收</title>
<style>
:root{color-scheme:light dark;font:14px/1.6 system-ui,sans-serif;background:light-dark(#f6f4f7,#17151d);color:light-dark(#282331,#ede8f3)}
body{margin:0 auto;max-width:1550px;padding:24px}h1{font-size:26px;margin:0}p{max-width:1000px}.muted{opacity:.7}
a{color:light-dark(#8b245e,#ef99c4)}button,select,input{font:inherit;color:inherit;background:light-dark(#fff,#25212d);border:1px solid #8d8496;border-radius:8px;padding:8px 12px;min-height:40px;box-sizing:border-box}button{cursor:pointer}button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid #b9478e;outline-offset:3px}button:disabled{opacity:.4;cursor:default}
nav,.filters,.pager{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:16px 0}.filters{position:sticky;top:0;background:light-dark(#f6f4f7ef,#17151def);padding:12px 0;z-index:2;backdrop-filter:blur(12px)}input{flex:1;min-width:220px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px}article{min-width:0;border:1px solid #8d849650;border-radius:12px;overflow:hidden;background:light-dark(#fff,#221e2b)}article header{padding:12px 16px}h2{margin:0;font-size:16px}small{display:block;overflow-wrap:anywhere}.pictures{display:flex;align-items:start;gap:8px;padding:0 12px 12px}.pictures figure{min-width:0;flex:1;margin:0}.pictures img{width:100%;height:auto;display:block;border-radius:4px}.pictures figcaption{font-size:12px;opacity:.7}.empty{padding:24px}.count{margin:8px 0}.check{max-height:65vh;overflow:auto;border:1px solid #8d849650;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;border-bottom:1px solid #8d849640;padding:8px;vertical-align:top;overflow-wrap:anywhere}th{position:sticky;top:0;background:light-dark(#ece8f0,#312b3b)}td:first-child{max-width:320px}details{margin:20px 0}summary{cursor:pointer;font-size:16px;font-weight:600}code{font-size:12px}footer{margin:24px 0}
</style>
<h1>BiliFlow · 全界面细节精修</h1>
<p>统一控件与弹窗，保留作品、星河／晴海、小流和温暖短句。此页使用临时离线数据；相同文件名的前后对照来自真实旧版和本轮截图。Cocoa／Retina 单独展示，不与 offscreen 做像素比较。</p>
<nav><a href="validation.json">验证记录</a><a href="dialog-index.json">弹窗索引</a><a href="instance-summary.json">逐实例清单</a><a href="instance-checks.json.gz">完整状态记录（gzip）</a></nav>
<p class="muted">__SCOPE__ 动态消息模板用演示值展开；截图覆盖不代表每条业务分支均已触发。几何记录可定位裁切风险，仍需结合实际绘制与交互回归。系统窗口装饰不在 QWidget 截图内，Windows 原生尚未验证。</p>
<div class="filters"><input id="query" aria-label="搜索截图" placeholder="搜索页面、组件、状态或来源"><select id="category" aria-label="类别"><option value="">全部类别</option></select><select id="theme" aria-label="配色"><option value="">全部配色</option><option value="star_trail">星河</option><option value="bilibili_blue">晴海</option></select><select id="mode" aria-label="深浅"><option value="">深浅模式</option><option value="light">浅色</option><option value="dark">深色</option></select><select id="font" aria-label="字体"><option value="">所有字体</option><option value="1">100%</option><option value="1.25">125%</option><option value="1.5">150%</option></select><select id="view" aria-label="对照方式"><option value="after">本轮</option><option value="compare">前后对照</option><option value="native">macOS 原生</option></select></div>
<div class="count" id="count" role="status"></div><div class="grid" id="gallery"></div><div class="pager"><button id="prev">上一页</button><span id="page"></span><button id="next">下一页</button></div>
<details><summary>完整交互控件清单（__CONTROLS__ 条路径）</summary><p>每条路径汇总普通／禁用、焦点策略与尺寸状态，列出截图定位；Qt 内部编辑器按所属组件合并。滚动区内局部不可见项单独标记。</p><input id="cq" aria-label="搜索控件" placeholder="搜索控件标签、类型或实例路径"><div class="check"><table><thead><tr><th>实例／标签</th><th>类型／规则</th><th>记录与结果</th></tr></thead><tbody id="controls"></tbody></table></div></details>
<footer>完整复现命令和平台边界见 <a href="__DOC__">全界面精修记录</a>。所有图片可点击查看原始尺寸。</footer>
<script id="data" type="application/json">__DATA__</script><script id="checks" type="application/json">__CHECKS__</script>
<script>
const data=JSON.parse(document.getElementById('data').textContent), checks=JSON.parse(document.getElementById('checks').textContent), $=id=>document.getElementById(id);let page=0;const batch=18;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
for(const c of [...new Set(data.map(r=>r.category))])$('category').add(new Option(c,c));
function draw(){const query=$('query').value.toLowerCase(),view=$('view').value;const rows=data.filter(r=>(!$('category').value||r.category===$('category').value)&&(!$('theme').value||r.theme===$('theme').value)&&(!$('mode').value||r.mode===$('mode').value)&&(!$('font').value||String(r.font_scale)===$('font').value)&&JSON.stringify(r).toLowerCase().includes(query)&&(view!=='compare'||r.before)&&(view!=='native'||r.native));const pages=Math.max(1,Math.ceil(rows.length/batch));page=Math.min(page,pages-1);$('count').textContent=`${rows.length} 张匹配 · 本页 ${Math.min(batch,Math.max(0,rows.length-page*batch))} 张`;
$('gallery').innerHTML=rows.slice(page*batch,(page+1)*batch).map(r=>{const images=view==='compare'?[['调整前',r.before],['本轮',r.after]]:[[view==='native'?'macOS Cocoa':'本轮',view==='native'?r.native:r.after]];return `<article><header><h2>${esc(r.title)} ${esc(r.state)}</h2><small>${esc(r.theme)} · ${esc(r.mode)} · ${Math.round((r.font_scale||1)*100)}% ${esc((r.size||[]).join(' × '))}</small><small>${esc(r.note||r.image)}</small></header><div class="pictures">${images.map(([t,src])=>`<figure><a href="${esc(src)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(src)}" alt="${esc(r.title+' '+r.state+' '+t)}"></a><figcaption>${t}</figcaption></figure>`).join('')}</div></article>`}).join('')||'<p class="empty">没有匹配截图。</p>';$('page').textContent=`${page+1} / ${pages}`;$('prev').disabled=page===0;$('next').disabled=page===pages-1;}
for(const id of ['query','category','theme','mode','font','view'])$(id).addEventListener('input',()=>{page=0;draw()});$('prev').onclick=()=>{page--;draw()};$('next').onclick=()=>{page++;draw()};
function drawControls(){const q=$('cq').value.toLowerCase();$('controls').innerHTML=checks.filter(c=>JSON.stringify(c).toLowerCase().includes(q)).map(c=>`<tr><td>${esc(c.label)}<br><code>${esc(c.id)}</code><br>${esc(c.example)}</td><td>${esc(c.class)}<br>${esc(c.rule)}</td><td>${c.state_count} 条记录；可见 ${c.visible_count}；禁用 ${c.disabled_count}；滚动区外裁切 ${c.outside_clipped}<br>焦点策略 ${esc(c.focus_policies.join(' / '))}</td></tr>`).join('')}$('cq').addEventListener('input',drawControls);draw();drawControls();
</script></html>'''


def summarize(registry):
    result = []
    for row in registry['controls']:
        states = row['states']
        result.append({k: row[k] for k in ('id', 'class', 'label', 'rule')} | {
            'state_count': len(states), 'visible_count': sum(s['visible'] for s in states),
            'disabled_count': sum(not s['enabled'] for s in states),
            'outside_clipped': sum(s['clipped'] and not s['scrollable'] for s in states),
            'focus_policies': sorted({s['focus_policy'] for s in states}),
            'example': next((s['case'] for s in states if s['visible']), states[0]['case']),
        })
    return clean(result)


def test_result(log):
    if not log.exists():
        return {'status': '未提供测试日志'}
    lines = [line for line in log.read_text(errors='replace').splitlines()
             if re.search(r'\d+ passed.* in [\d.]+s', line)]
    if not lines:
        return {'status': '日志中无完整测试结果', 'log': str(log)}
    line = lines[-1]
    result = {kind: int(count) for count, kind in re.findall(r'(\d+) (passed|failed|skipped|warnings?|errors?)', line)}
    result.update(seconds=float(re.search(r'in ([\d.]+)s', line)[1]), log=str(log))
    return result


def validation(after, native, summary, rows):
    profiles = {}
    for label, folder in [('offscreen', after), ('macOS', native)]:
        if not (folder / 'instance-checks.json').exists():
            continue
        reg = read_json(folder / 'instance-checks.json')
        components = [row for suffix in ('', '-font125', '-font150')
                      for row in read_json(folder / f'component-checks{suffix}.json')]
        sizes = {}
        for row in components:
            group = (row['theme'], row['mode'], row['font_scale'], row['id'].split(':')[0])
            sizes.setdefault(group, set()).add(tuple(row['size']))
        assert all(len(values) == 1 for values in sizes.values()), (label, 'component state geometry changed')
        popups = read_json(folder / 'popup-checks.json')
        warm = read_json(folder / 'warm-checks.json')
        long = read_json(folder / 'refinement-checks.json')
        fonts = read_json(folder / 'font-workspace-checks.json')
        outside = sum(s['clipped'] and not s['scrollable'] for c in reg['controls'] for s in c['states'])
        assert not outside, (label, 'clipped visible controls outside scroll areas', outside)
        assert all(r['focused'] for r in components if r['state'] == 'focus'), label
        assert all(r['within_screen'] and r['horizontal_scroll'] == 0 for r in popups), label
        assert all(r['actual_size'] == r['size'] and r['horizontal_scroll'] == 0 for r in warm), label
        assert all(r['actual_size'] == r['requested_size'] and r['horizontal_scroll'] == 0 for r in long), label
        assert all(r['size'] == [900, 640] and not r['horizontal_scroll'] for r in fonts), label
        profiles[label] = {'rendering': read_json(folder / 'rendering-profile.json'),
                           'screenshots': len(list(folder.glob('*.png'))),
                           'cases': len(reg['cases']), 'controls': len(reg['controls']),
                           'components': len(components), 'popups': len(popups),
                           'outside_scroll_clipping': outside, 'warm_checks': len(warm),
                           'long_content_checks': len(long), 'font_workspace_checks': len(fonts),
                           'component_state_geometry': 'stable', 'advanced_error': read_json(folder / 'checks.json')}
    return {'date': '2026-11-10', 'profiles': profiles,
            'tests': {'offscreen': test_result(after.parent.parent / 'pytest-delivery.log'),
                      'macOS': test_result(native.parent.parent / 'pytest-native-delivery.log')},
            'static_checks': read_json(after.parent.parent / 'static-checks.json')
            if (after.parent.parent / 'static-checks.json').exists() else '未提供静态检查记录',
            'catalog': {'images': len(rows), 'comparisons': sum(bool(r.get('before')) for r in rows),
                        'controls': len(summary)},
            'Windows_native': '未验证：无对应桌面环境',
            'notes': ['消息模板中的动态参数为离线演示值，真实业务入口由行为回归另行验证。',
                      'QWidget 截图不包含系统合成的窗口装饰；浮层合成为逻辑像素。',
                      '正文标签与容器随所属页面绘制检查，不计入交互控件路径数量。']}


def package(output, rows, registry, summary, after, native, before, *, curated=False):
    output.mkdir(parents=True, exist_ok=True)
    messages = read_json(after / 'message-entries.json')
    index = []
    for name in sorted({r['name'] for r in registry['cases'] if r['dialog'] and r['name'].startswith(('dialog-', 'message-'))}):
        cases = [r for r in registry['cases'] if r['name'] == name]
        index.append({'id': name, 'title': TITLES.get(name, next((m['title'] for m in messages if m['id'] == name), name)),
                      'cases': len(cases), 'example': cases[0]['image'],
                      'entry': next((m for m in messages if m['id'] == name), None)})
    for filename, data in [('dialog-index.json', index), ('instance-summary.json', summary)]:
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    with gzip.open(output / 'instance-checks.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(clean(registry), stream, ensure_ascii=False, separators=(',', ':'))
    for row in rows:
        put(after / row['image'], output / row['after'])
        if row.get('before'):
            put(before[row['image']], output / row['before'])
        if row.get('native'):
            put(native / row['image'], output / row['native'])
    payload = json.dumps(rows, ensure_ascii=False).replace('<', '\\u003c')
    checks = json.dumps(summary, ensure_ascii=False).replace('<', '\\u003c')
    scope = ('此文档保留代表页面、全部 50 类弹窗／消息状态和重点组件，完整矩阵由脚本生成至 build/ui-detail/review。' if curated else
             '此完整图册包含所有截图、全部弹窗／消息状态及逐实例检查记录。')
    page = PAGE.replace('__DATA__', payload).replace('__CHECKS__', checks).replace('__CONTROLS__', str(len(summary)))
    page = page.replace('__SCOPE__', scope).replace('__DOC__', '../../UI_DETAIL_POLISH.md' if curated else '../../../docs/UI_DETAIL_POLISH.md')
    (output / 'index.html').write_text(page, encoding='utf-8')
    for filename in ('rendering-profile.json', 'component-checks.json', 'component-checks-font125.json',
                     'component-checks-font150.json', 'popup-checks.json', 'message-entries.json',
                     'warm-checks.json', 'refinement-checks.json', 'font-workspace-checks.json', 'checks.json'):
        put(after / filename, output / filename)
    if (native / 'rendering-profile.json').exists():
        put(native / 'rendering-profile.json', output / 'rendering-profile-native.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, default=Path('build/ui-detail/before'))
    parser.add_argument('--after', type=Path, default=Path('build/ui-detail/delivery/offscreen'))
    parser.add_argument('--native', type=Path, default=Path('build/ui-detail/delivery/native'))
    parser.add_argument('--output', type=Path, default=Path('build/ui-detail/review'))
    parser.add_argument('--doc-output', type=Path, default=Path('docs/images/ui-detail'))
    args = parser.parse_args()
    rows, registry = catalog(args.after, args.native)
    before = {p.name: p for folder in ('components', 'ui') for p in (args.before / folder).glob('*.png')}
    for row in rows:
        if row['image'] in before:
            row['before'] = 'images/before/' + row['image']
    featured = ['ui-star_trail-download-dark-1320.png', 'ui-star_trail-download-light-900.png',
                'ui-star_trail-batch-dark-1320.png', 'ui-star_trail-live-dark-1320.png',
                'queue-selected.png', 'advanced-error.png']
    categories = ['工作区', '组件', '浮层', '弹窗', '背景', '补充']
    rows.sort(key=lambda r: (0, featured.index(r['image'])) if r['image'] in featured else
              (1, categories.index(r['category'])))
    summary = summarize(registry)
    results = validation(args.after, args.native, summary, rows)
    package(args.output, rows, registry, summary, args.after, args.native, before)
    wanted = {
        'ui-star_trail-download-dark-1320.png', 'ui-star_trail-download-light-900.png',
        'ui-star_trail-settings-appearance-light-900.png', 'ui-star_trail-batch-dark-1320.png',
        'ui-star_trail-live-dark-1320.png', 'queue-selected.png', 'advanced-error.png',
        'detail-background-bilibili_blue-light-custom-download-900.png',
        'detail-background-star_trail-dark-builtin-live-1320.png',
        'detail-background-star_trail-light-custom-tasks-900.png',
        'detail-background-bilibili_blue-dark-builtin-settings-900.png',
        'detail-star_trail-light-900-dialog-settings-appearance-font150.png',
        'detail-star_trail-light-900-dialog-background-gallery-font150.png',
        'detail-star_trail-light-900-dialog-copyright-font150.png',
        'detail-star_trail-light-900-dialog-login-qr-font150.png',
        'detail-star_trail-light-900-message-main_window-request_quit-2837-font150.png',
    }
    curated = [r for r in rows if r['image'] in wanted or
               r['key'].startswith('font-workspace-') and r['theme'] == 'star_trail' and r['mode'] == 'light' or
               r['image'].startswith('detail-star_trail-light-900-') and r.get('dialog') and r.get('font_scale', 1) == 1 or
               r['category'] == '组件' and r['theme'] == 'star_trail' and r['mode'] == 'light' and
               r['font_scale'] == 1 and r['state'] in ('normal', 'focus', 'error', 'checked', 'partial') or
               r['category'] == '浮层']
    package(args.doc_output, curated, registry, summary, args.after, args.native, before, curated=True)
    for folder in (args.output, args.doc_output):
        (folder / 'validation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    # Small visual comparison, from identical backend/theme/data; original images remain linked.
    names = ['component-star_trail-checkbox-light-focus.png', 'component-star_trail-input-light-focus.png',
             'ui-star_trail-download-light-900.png']
    canvas = Image.new('RGB', (1440, 1080), '#efedf2')
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 12), 'BEFORE                                                 AFTER', fill='#282331')
    y = 40
    for name in names:
        for x, source in [(20, before.get(name)), (730, args.after / name)]:
            if source and source.exists():
                image = Image.open(source).convert('RGB')
                image.thumbnail((690, 220 if name.startswith('component') else 600))
                canvas.paste(image, (x, y))
        y += 180 if name.startswith('component') else 600
    canvas.save(args.doc_output / 'comparison.png')
    print(json.dumps({'images': len(rows), 'curated_images': len(curated), 'before_after': sum(bool(r.get('before')) for r in rows),
                      'native': sum(bool(r.get('native')) for r in rows), 'controls': len(summary),
                      'categories': dict(Counter(r['category'] for r in rows))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
