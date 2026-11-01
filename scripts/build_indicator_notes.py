#!/usr/bin/env python3
"""EXEC-IND-CARDS IC2 (user go 2026-11-01): the formula and the specification notes of every Terminal indicator, for its
card (apps/edge-bff/terminal/src/data/indNotes.json). Nothing is typed here: the technical indicators come from their
one source, scripts/terminal_indicator_spec.py (the T1 specification), and the Flow indicators from the formula table of
verification/terminal_api/flow_indicators/FORMULAS.md (the contract of calc/flow.ts). The card adds the Terminal's
defaults and the cautions that follow from each indicator's parameters at run time (app/indCard.ts).

  python3 scripts/build_indicator_notes.py            # writes the file
  python3 scripts/build_indicator_notes.py --check    # fails if the file differs from its sources
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import terminal_indicator_spec as spec  # noqa: E402

OUT = ROOT / 'apps/edge-bff/terminal/src/data/indNotes.json'
FORMULAS = ROOT / 'verification/terminal_api/flow_indicators/FORMULAS.md'
ROW = re.compile(r'^\| (FL\d\d) \| ([^|]+) \| ([^|]+) \| (.+) \|$')


def flow_rows():
    """FORMULAS.md section 3: | Id | Name | Output(s) | Formula |; backticks dropped (the card shows plain text)."""
    out = {}
    for line in FORMULAS.read_text().splitlines():
        m = ROW.match(line.strip())
        if m:
            out[m.group(1)] = {'formula': m.group(4).replace('`', '').strip(), 'outputs': m.group(3).strip(),
                               'source': 'verification/terminal_api/flow_indicators/FORMULAS.md'}
    return out


def build():
    technical = {r['iid']: {'formula': r['formula'], 'outputs': r['outputs'], 'inputs': r['inputs'],
                            'notes': [r['notes']] if r['notes'] else [], 'engine': r['source'],
                            'source': 'verification/terminal_api/INDICATOR_SPEC.md'} for r in spec.rows()}
    return {'generated_by': 'scripts/build_indicator_notes.py', 'common_technical': spec.COMMON,
            'technical': technical, 'flow': flow_rows()}


def main(argv):
    text = json.dumps(build(), ensure_ascii=False, indent=1) + '\n'
    if '--check' in argv:
        if not OUT.exists() or OUT.read_text() != text:
            print(f'{OUT.relative_to(ROOT)} differs from its sources: run scripts/build_indicator_notes.py')
            return 1
        return 0
    OUT.write_text(text)
    print(f'{OUT.relative_to(ROOT)}: {len(build()["technical"])} technical, {len(build()["flow"])} flow')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
