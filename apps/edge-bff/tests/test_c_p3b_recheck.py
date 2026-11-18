"""EXEC-MU-ACCOUNTS re-check of Phase 3b (checker C-P3B, 2026-11-18; user: "Cek juga fase sebelumnya ... Jangan sampai
fase 3C di bangun dari broken block fase2 sebelumnya"). Failing tests of the verified findings; the fix round makes
them pass (CONTRACT.md 8a "Capability rows", 8b "3b in detail").

- F1: the catalog capability `screener.preset` ("Which ready-made Screener presets the account may open",
  migration 20261117_003 line 211) is read by no route. The Screener catalog leaves a preset out only when one of its
  items is outside the allow (Screeners.catalog_for, presets_held; C2 Phase 3b F1), never by the preset's own grant
  `screener.preset:<id>`, so a plan or override that takes a preset away (or a preset moved to `lab` in releases.json)
  still lists it, with the match and near counts computed for it in the system lane.
- F2: a worker's CAPABILITY_REQUIRED names its own hard-coded family (backtest-worker src/access.ts FAMILY, screener-worker
  src/run.ts CAPABILITY_FAMILY: `backtest.indicator:<id>`, `screener.indicator:<id>`), while edge-bff decides the item
  from app/allow.py FAMILIES. The 3b follow-up (CONTRACT.md 8b, decided O3b-1, built with 3c) moves the indicator and
  Flow grants of both workers to `terminal.indicator` / `terminal.flow_indicator` and its migration deletes the four
  `backtest.*`/`screener.*` rows; neither the follow-up text nor "Worker refusal" changes the workers' families, so the
  refusal would name a capability that no longer exists (display_name falls back to "This part of EDGE") and that no
  admin can grant. The first block holds the two in step; the second is the decided target the follow-up builds.
"""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import allow
from app.main import create_app
from conftest import FakeOrc
from test_phase3a_gates import override, paid_user
from test_principal import on, sign_in, workers  # noqa: F401 - the fixtures

ROOT = Path(__file__).resolve().parents[3]


def worker_families():
    """{worker: {kind: family}} as each worker writes details.capability (its source, the code that is deployed)."""
    def parse(path, name):
        text = (ROOT / path).read_text(encoding='utf-8')
        found = re.search(r'export const ' + name + r'\b[^=]*=\s*(?:Object\.freeze\()?\{(.*?)\}', text, re.S)
        assert found, f'{name} not found in {path}'
        return dict(re.findall(r"(\w+):\s*'([a-z_.]+)'", found.group(1)))
    return {'backtest': parse('apps/backtest-worker/src/access.ts', 'FAMILY'),
            'screener': parse('apps/screener-worker/src/run.ts', 'CAPABILITY_FAMILY')}


def test_f2_a_worker_refusal_names_the_family_edge_bff_decides_the_item_by():
    families = worker_families()
    for worker in ('backtest', 'screener'):
        assert set(families[worker]) == set(allow.KINDS), (worker, families[worker])
        for kind in allow.KINDS:
            assert families[worker][kind] == allow.FAMILIES[worker][kind], (
                f'the {worker} worker names {families[worker][kind]}:<id> in CAPABILITY_REQUIRED, but edge-bff decides '
                f'its {kind} items by {allow.FAMILIES[worker][kind]}')
    # O3b-1 (user 2026-11-18, CONTRACT.md 8b "3b follow-up"): the Terminal's grants decide both workers' indicator and
    # Flow items, so the refusal must name the Terminal family once the follow-up lands (both sides together)
    for worker in ('backtest', 'screener'):
        assert families[worker]['indicator'] == 'terminal.indicator', (worker, families[worker]['indicator'])
        assert families[worker]['flow_indicator'] == 'terminal.flow_indicator', (worker, families[worker]['flow_indicator'])


def flow(metric):
    return {'universe': {'security_types': ['stock']}, 'logic': 'all', 'conditions': [{'id': 'a', 'enabled': True, 'test': {
        'kind': 'value', 'metric': {'kind': 'flow', 'metric': metric, 'params': {}}, 'op': 'gt', 'value': 0}}]}


def test_f1_a_preset_the_plan_does_not_hold_is_not_listed_in_the_screener_catalog(on, store, workers):
    """A paid account whose `screener.preset` grant is narrowed to `brk52` (an override, CONTRACT.md 8a) holds every
    item of both presets (FL11 is released), so only the preset grant can tell them apart. The catalog must not list
    the preset `golden` the account does not hold, nor its counts."""
    _, sc = workers
    sc.metrics = [{'id': 'FL11', 'group': 'Flow', 'kind': 'flow'}]
    items = [{'kind': 'flow_indicator', 'id': 'FL11'}]
    sc.presets = [{'id': 'brk52', 'definition': flow('FL11'), 'items': items, 'availability': 'AVAILABLE',
                   'match_count': 12, 'near_count': 3},
                  {'id': 'golden', 'definition': flow('FL11'), 'items': items, 'availability': 'AVAILABLE',
                   'match_count': 7, 'near_count': 2}]
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'screener.preset', '{"ids": ["brk52"]}')
        c.headers_for = sign_in(c, 'alice', 'alice-password')
        cat = c.get('/api/v1/screener/catalog')
        assert cat.status_code == 200, cat.text
        listed = [p['id'] for p in cat.json()['presets']]
        assert 'brk52' in listed
        assert 'golden' not in listed, (
            'the Screener catalog lists a preset whose capability screener.preset:golden the account does not hold '
            f'(listed: {listed}); no route reads screener.preset')
