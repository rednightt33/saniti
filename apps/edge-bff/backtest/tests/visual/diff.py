"""Pixel comparison of the 1:1 check (compare.mjs output): for every viewport and step, the number and share of pixels
that differ between the reference (ref/) and the TypeScript page (ts/), a diff image (diff-<step>.png, differing pixels
red), and a text/markup/storage comparison (diff-<step>.txt lists each differing panel with both versions). A channel
difference of at most NOISE (canvas anti-aliasing) is counted separately as noise, not as a difference. Card ids are
random on both pages: they are numbered in order of appearance before the markup is compared.
Usage: python3 diff.py [out dir]   (default: $BACKTEST_VISUAL_OUT, else backtest-visual in the temporary directory, as compare.mjs)"""
import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

NOISE = 2
out = Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get('BACKTEST_VISUAL_OUT', os.path.join(tempfile.gettempdir(), 'backtest-visual')))
ID = re.compile(r'(?:data-(?:id|c|cid|del|h|ws|won|wdup|wdel|wsel)="|id="cf-|"id":")([a-z0-9]{1,8})"')


def ids(side):
    """the card ids of one snapshot in order of appearance -> c1, c2, ..."""
    seen = {}
    for v in side['html'].values():
        for m in ID.finditer(v):
            seen.setdefault(m.group(1), f'c{len(seen) + 1}')
    return seen


def norm(s, table):
    return re.sub(r'\b(' + '|'.join(map(re.escape, table)) + r')\b', lambda m: table[m.group(1)], s) if s and table else s


rows, worst = [], 0.0
for vp in sorted((p for p in out.iterdir() if p.is_dir()), key=lambda p: -int(p.name.split('x')[0])):
    for ref in sorted((vp / 'ref').glob('*.png')):
        ts = vp / 'ts' / ref.name
        a = np.asarray(Image.open(ref).convert('RGB'), dtype=np.int16)
        b = np.asarray(Image.open(ts).convert('RGB'), dtype=np.int16) if ts.exists() else None
        if b is None or a.shape != b.shape:
            rows.append((vp.name, ref.stem, 'size', a.shape, None if b is None else b.shape, [], [])); worst = 1.0; continue
        d = np.abs(a - b).max(axis=2)
        noise = int(((d > 0) & (d <= NOISE)).sum())
        d = np.where(d > NOISE, d, 0)
        share = float((d > 0).mean())
        worst = max(worst, share)
        if share:
            img = np.where(d[..., None] > 0, [255, 0, 0], (a * .25 + 191).astype(np.int16)).astype(np.uint8)
            Image.fromarray(img).save(vp / f'diff-{ref.stem}.png')
        tj = [json.loads((vp / s / f'{ref.stem}.json').read_text()) for s in ('ref', 'ts')]
        tabs = [ids(s) for s in tj]
        report, text_diff = [], []
        for kind in ('text', 'html', 'storage'):
            for k in tj[0][kind]:
                x, y = (norm(tj[i][kind].get(k), tabs[i]) for i in (0, 1))
                if x != y:
                    text_diff.append(('' if kind == 'text' else kind + ':') + k)
                    report.append(f'== {kind} {k}\n' + '\n'.join(difflib.unified_diff((x or '').split('\n'), (y or '').split('\n'), 'ref', 'ts', n=1, lineterm='')))
        txt = vp / f'diff-{ref.stem}.txt'
        if report:
            txt.write_text('\n'.join(report))
        else:
            txt.unlink(missing_ok=True)
        rows.append((vp.name, ref.stem, f'{share:.6%}', int((d > 0).sum()), f'noise {noise}', text_diff))
for r in rows:
    print(*r, sep=' | ')
print('worst pixel share:', f'{worst:.6%}')
