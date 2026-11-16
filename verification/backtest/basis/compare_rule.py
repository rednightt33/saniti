"""EXEC-BACKTEST-REVAMP Stage C2 (user 2026-11-16 "A", ERRORS M459 item 1): the publisher's basis decision of each action
under two versions of publisher.py broker_basis (the one before, given as a file, and the one in the repository), on the
files fetch.py wrote (each action alone, with the broker date after its window). Prints the (type, before, now) counts
and every action whose status changed, with its terms factor and observed jump.
  python3 compare_rule.py OUTDIR OLD_PUBLISHER.py   (run from apps/terminal-publisher, its requirements installed)"""
import collections
import glob
import importlib.util
import json
import sys
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


out_dir, old_path = sys.argv[1], sys.argv[2]
old = load('old_publisher', old_path)
new = load('new_publisher', str(Path(__file__).resolve().parents[3] / 'apps' / 'terminal-publisher' / 'publisher.py'))
through = '2026-11-14'
counts, changed = collections.Counter(), []
for f in sorted(glob.glob(f'{out_dir}/basis_*_*_*.json')):
    typ = f.split('basis_')[1].rsplit('_', 2)[0]
    for e in json.load(open(f)):
        days = []
        for d, v, c, h, l in e.get('days', []):
            try:
                days.append((d, float(v), float(h), float(l), float(c)))
            except (TypeError, ValueError):
                pass
        num = lambda x: None if x in (None, '') else float(x)
        a = (e['ex'], typ, num(e['old']), num(e['new']), num(e.get('px')))
        ro, rn = old.broker_basis([a], days, through), new.broker_basis([a], days, through)
        if not ro or not rn:
            continue
        counts[(typ, ro[0][3], rn[0][3])] += 1
        if ro[0][3] != rn[0][3]:
            changed.append((e['t'], e['ex'], typ, ro[0][3], rn[0][3], ro[0][5], rn[0][6]))
for k, v in sorted(counts.items()):
    print(k, v)
print('changed', len(changed), 'of', sum(counts.values()))
for c in changed:
    print(c)
