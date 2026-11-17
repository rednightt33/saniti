"""EDGE multi-user Phase 2 (EXEC-MU-ACCOUNTS; CONTRACT.md section 8a "Release catalog"): the release stage of an item.

MINIMAL STAND-IN written by builder B1 so the principal's item grants can be tested; builder B2's full module replaces
this file at integration with the same interface:
- `stage_of(kind, item_id) -> 'lab' | 'released'`: the stage in apps/edge-bff/catalog/releases.json; an id missing
  from the file (or no file) is 'lab';
- `KIND_OF_FAMILY`: a capability family (`<tab>.<item kind>`) -> the release kind its ids belong to.
"""
import json
from pathlib import Path

RELEASES = Path(__file__).resolve().parents[1] / 'catalog' / 'releases.json'
LAB, RELEASED = 'lab', 'released'

KIND_OF_FAMILY = {
    'terminal.indicator': 'indicator', 'backtest.indicator': 'indicator', 'screener.indicator': 'indicator',
    'terminal.flow_indicator': 'flow_indicator', 'backtest.flow_indicator': 'flow_indicator',
    'screener.flow_indicator': 'flow_indicator',
    'backtest.candle_pattern': 'candle_pattern', 'screener.candle_pattern': 'candle_pattern',
    'screener.metric': 'screener_metric', 'screener.preset': 'screener_preset',
}


def _load(path=RELEASES):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    items = data.get('items') if isinstance(data, dict) else None
    return {(x['kind'], x['id']): x['stage'] for x in items or ()
            if isinstance(x, dict) and x.get('stage') in (LAB, RELEASED)
            and isinstance(x.get('kind'), str) and isinstance(x.get('id'), str)}


_STAGES = _load()


def stage_of(kind, item_id):
    return _STAGES.get((kind, item_id), LAB)
