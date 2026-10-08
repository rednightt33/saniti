"""EXEC-X (user decision 2026-10-08): the page is edited as one HTML file and its API wiring is not locked to the view.
- every page script is served by name, and nothing outside static/ is;
- the preview tool round-trips: build, then import, changes nothing; a file it did not build is refused;
- EdgeView.toView is the view contract: for every saved dev response it returns the same parts, every choice carries an
  action the page knows, and no Orc field name reaches a label unworded."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'tests' / 'fixtures' / 'orc_responses.json').read_text())
PARTS = {'version', 'status', 'meta', 'evidence', 'claims', 'answer', 'clarification', 'pause', 'plan', 'findings', 'lists',
         'methodology', 'artifacts'}
ACTIONS = {'route', 'message', 'input', 'plan'}


def test_page_scripts_are_served_by_name_and_nothing_else(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for name in [p.name for p in (ROOT / 'static').glob('*.js')]:
            r = c.get('/' + name)
            assert r.status_code == 200 and r.headers['content-type'].startswith('text/javascript'), name
        for bad in ('/missing.js', '/..%2Fapp%2Fmain.js', '/Edge-View.js', '/edge_view.js'):
            assert c.get(bad).status_code == 404, bad
        page = c.get('/').text
        assert all(c.get(f'/{name}').status_code == 200 for name in __import__('re').findall(r'<script src="/([^"]+)"', page))


def run_preview(*args):
    return subprocess.run([sys.executable, str(ROOT / 'preview' / 'edge_preview.py'), *args], capture_output=True, text=True)


def test_preview_round_trip_changes_nothing_and_refuses_other_files(tmp_path):
    built = tmp_path / 'preview.html'
    result = run_preview('build', str(built))
    assert result.returncode == 0, result.stderr
    text = built.read_text()
    assert 'data-edge-preview="mock"' in text and '<script src="/' not in text
    result = run_preview('import', str(built))
    assert result.returncode == 0 and 'no change' in result.stdout, result.stdout + result.stderr
    plain = tmp_path / 'plain.html'
    plain.write_text((ROOT / 'static' / 'index.html').read_text())
    refused = run_preview('import', str(plain))
    assert refused.returncode != 0 and 'nothing written' in (refused.stderr + refused.stdout)


@pytest.fixture(scope='module')
def views():
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        page.set_content('<!doctype html><title>contract</title>')
        for name in ('edge-labels.js', 'edge-view.js'):
            page.add_script_tag(content=(ROOT / 'static' / name).read_text())
        out = page.evaluate('''(fixtures) => {
            const index = EdgeView.planIndex(Object.values(fixtures));
            return Object.fromEntries(Object.entries(fixtures).map(([name, envelope]) =>
                [name, {view: EdgeView.toView(envelope, {planIndex: index}), sources: EdgeView.sources(envelope)}]));
        }''', FIXTURES)
        browser.close()
        return out


def choices(view):
    for part in (view['clarification'], view['pause'], view['plan']):
        yield from (part or {}).get('choices', [])


def test_every_saved_response_maps_to_the_same_parts(views):
    for name, out in views.items():
        assert set(out['view']) == PARTS, name
        assert out['view']['version'] == 1
        assert {'label', 'tone', 'code'} <= set(out['view']['status']), name


def test_every_choice_carries_an_action_the_page_runs(views):
    seen = set()
    for name, out in views.items():
        for choice in choices(out['view']):
            assert choice['label'] and choice['action']['type'] in ACTIONS, (name, choice)
            seen.add(choice['action']['type'])
            if choice['action']['type'] == 'plan':
                assert choice['action']['planId'], name
    assert {'plan', 'message', 'input'} <= seen  # plan replies and both kinds of pause choice occur in real responses


def test_labels_are_worded_not_field_names(views):
    """A label equal to an Orc field name (snake_case) means a wording is missing from edge-labels.js."""
    labels = []
    for out in views.values():
        plan = out['view']['plan']
        if plan:
            labels += [f['label'] for f in plan['summary']] + [f['label'] for i in plan['items'] for f in i['facts']]
        for finding in (out['view']['findings'] or {}).get('items', []):
            labels += [p['label'] for p in finding['parts']] + [m['label'] for m in finding['metrics']]
    assert labels and not [label for label in labels if '_' in label]


def test_every_artifact_field_the_view_reads_is_one_orc_sends(views):
    """M128 (a): the view read `filename`, Orc sends `file_name`; the real export response is a fixture now, so the
    Download button shows the file's name, never its id."""
    files = views['export_xlsx']['view']['artifacts']
    assert files == [{'id': 'exp_db23d46bca770b9a7557dca4', 'label': 'bbri_foreign_flow_daily.xlsx'}]
    for out in views.values():
        for file in out['view']['artifacts']:
            assert file['label'] != file['id']


def test_the_data_record_summary_shows_only_parts_worded_for_the_reader(views):
    """P4: version, next_alias, seq and the other bookkeeping of the record stay in Detail teknis."""
    for name, out in views.items():
        record = out['sources']['record']
        if record:
            assert set(record['summary']) <= {'Tabel hasil', 'Data yang dibaca', 'Temuan riset'}, name
            assert record['raw']  # the whole record is still there for the technical view
