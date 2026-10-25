"""Pixel comparison of the 1:1 check (compare.mjs output): for every viewport and step, the share of pixels that
differ between the reference (ref/) and the TypeScript page (ts/), plus a diff image and a text/markup/storage
comparison. A channel difference of at most NOISE (canvas anti-aliasing, measured 1-2 of 255 on a few pixels between
identical runs) is counted separately as noise, not as a difference.
Usage: python3 diff.py <out dir>"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

NOISE = 2
out = Path(sys.argv[1])
rows, worst = [], 0.0
for vp in sorted(p for p in out.iterdir() if p.is_dir()):
    for ref in sorted((vp / 'ref').glob('*.png')):
        ts = vp / 'ts' / ref.name
        a = np.asarray(Image.open(ref).convert('RGB'), dtype=np.int16)
        b = np.asarray(Image.open(ts).convert('RGB'), dtype=np.int16) if ts.exists() else None
        if b is None or a.shape != b.shape:
            rows.append((vp.name, ref.stem, 'size', a.shape, None if b is None else b.shape)); worst = 1.0; continue
        d = np.abs(a - b).max(axis=2)
        noise = int(((d > 0) & (d <= NOISE)).sum())
        d = np.where(d > NOISE, d, 0)
        share = float((d > 0).mean())
        worst = max(worst, share)
        if share:
            img = np.where(d[..., None] > 0, [255, 0, 0], (a * .25 + 191).astype(np.int16)).astype(np.uint8)
            Image.fromarray(img).save(vp / f'diff-{ref.stem}.png')
        tj = json.loads((vp / 'ref' / f'{ref.stem}.json').read_text()), json.loads((vp / 'ts' / f'{ref.stem}.json').read_text())
        text_diff = [k for k in tj[0]['text'] if tj[0]['text'][k] != tj[1]['text'][k]]
        text_diff += ['html:' + k for k in tj[0]['html'] if tj[0]['html'][k] != tj[1]['html'][k]]
        for side in tj:                               # drawing ids are made from the clock: compare drawings without them
            side['storage'] = {k: re.sub(r'"id":"dw_[^"]*"', '"id":"…"', v) for k, v in side['storage'].items()}
        store_diff = sorted(set(tj[0]['storage']) ^ set(tj[1]['storage'])) + [k for k in tj[0]['storage'] if k in tj[1]['storage'] and tj[0]['storage'][k] != tj[1]['storage'][k]]
        rows.append((vp.name, ref.stem, f'{share:.6%}', int((d > 0).sum()), f'noise {noise}', text_diff, store_diff))
for r in rows:
    print(*r, sep=' | ')
print('worst pixel share:', f'{worst:.6%}')
