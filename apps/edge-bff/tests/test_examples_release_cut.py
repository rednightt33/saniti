"""Lab gap "the stored examples" (FUTURE_PLAN.md "Before the first lab item or tab"; ERRORS M527 records-promotion-3; the
user's go 2026-11-22): a stored example (the Backtest's, the Screener's) is held to the release file the process runs
when it is served (app/examples.py released_view), not only to the release file of its capture. On the made-up examples
the publisher's own builder writes (example_docs), with a release file in which items the example names or lists are put
at the lab stage, one kind at a time:
- a catalog's list keeps what the narrowest principal sees, the index's sha256 and bytes follow the served bytes;
- a preset that reads an item left out, or is itself lab, is left out;
- a file that still names a lab item (the Backtest's request, the Screener's screen) withholds the tab's example;
- under the repository's release file (no lab item) every stored byte is served as stored."""
import gzip
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

import example_docs
from app import releases
from app.main import create_app
from conftest import FakeOrc
from test_examples import RADAR, put
from test_guest import VISITOR, guests  # noqa: F401 - the fixture
from test_principal import db, on, workers  # noqa: F401 - the fixtures
from test_terminal_access import api  # noqa: F401 - the fixture


def with_lab(monkeypatch, tmp_path, lab, stage='lab'):
    """The repository's release file with the (kind, id) pairs of `lab` at the lab stage (or `stage`: 'preview', which the
    stored examples hold back too, EXEC-MU-ACCOUNTS "A preview release stage": a visitor never holds it)."""
    data = json.loads(releases.PATH.read_text())
    found = set()
    for item in data['items']:
        if (item['kind'], item['id']) in lab:
            item['stage'] = stage
            found.add((item['kind'], item['id']))
    assert found == set(lab), f'not in the release file: {set(lab) - found}'
    path = tmp_path / 'releases.json'
    path.write_text(json.dumps(data))
    monkeypatch.setattr(releases, 'CURRENT', releases.load(path))


def served(c, tab):
    """(status, index or error code, {name: doc}) as a visitor reads the tab's example; each file's bytes checked
    against the sha256 and bytes the index gives."""
    r = c.get(f'/api/v1/examples/{tab}/index', headers=VISITOR)
    if r.status_code != 200:
        return r.status_code, r.json()['error']['code'], {}
    index, docs = r.json(), {}
    for name, e in index['files'].items():
        f = c.get(f'/api/v1/examples/{tab}/file/{name}?sha={e["sha256"]}', headers=VISITOR)
        assert f.status_code == 200, (name, f.text)
        docs[name] = f.json()
    return 200, index, docs


@pytest.fixture(scope='module')
def backtest_files():
    return example_docs.backtest_example()


@pytest.fixture(scope='module')
def screener_files():
    return example_docs.screener_example()


@pytest.fixture
def stored_examples(store, backtest_files, screener_files):
    put(store, 'backtest', backtest_files)
    put(store, 'screener', screener_files)
    put(store, 'radar', RADAR)
    yield
    db(store, 'DELETE FROM edge_bff.example_files')


def test_under_the_repository_release_file_every_stored_byte_is_served_as_stored(guests, store, stored_examples):
    stored = {(r['tab'], r['name']): r['sha256'] for r in db(store, 'SELECT tab, name, sha256 FROM edge_bff.example_files')}
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        for tab in ('backtest', 'screener'):
            status, index, _ = served(c, tab)
            assert status == 200, index
            assert {n: e['sha256'] for n, e in index['files'].items()} == {n: s for (t, n), s in stored.items() if t == tab}


@pytest.mark.parametrize('stage', ['lab', 'preview'])
def test_a_flow_indicator_put_at_the_lab_stage_leaves_the_backtest_examples_catalog(guests, store, stored_examples,
                                                                                    backtest_files, monkeypatch, tmp_path, stage):
    shown = [e['id'] for e in backtest_files['backtest-catalog']['flow_indicators'] if isinstance(e, dict) and 'id' in e]
    request = json.dumps(backtest_files.get('backtest-request') or {})
    lab = next(i for i in shown if i not in request)            # one the stored request does not name
    with_lab(monkeypatch, tmp_path, {('flow_indicator', lab)}, stage)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        status, index, docs = served(c, 'backtest')
    assert status == 200, index
    ids = [e.get('id') for e in docs['backtest-catalog']['flow_indicators']]
    assert lab not in ids and len(ids) == len(backtest_files['backtest-catalog']['flow_indicators']) - 1
    assert lab not in json.dumps(docs)
    body = gzip.compress(json.dumps(docs['backtest-catalog'], separators=(',', ':'), ensure_ascii=False).encode(), 6, mtime=0)
    assert index['files']['backtest-catalog']['sha256'] == hashlib.sha256(body).hexdigest()
    for name in set(docs) - {'backtest-catalog'}:
        assert docs[name] == backtest_files[name], name                  # the other files as stored


@pytest.mark.parametrize('stage', ['lab', 'preview'])
def test_an_indicator_the_backtest_example_runs_put_at_the_lab_stage_withholds_the_example(
        guests, store, stored_examples, backtest_files, monkeypatch, tmp_path, stage, caplog):
    request = backtest_files['backtest-request'] if 'backtest-request' in backtest_files else backtest_files['backtest-result']
    named = sorted({i['id'] for i in releases.entries('indicator')} & set(json.dumps(request).replace('"', ' ').split()))
    assert named, 'the example names no indicator of the release file: update this test'
    with_lab(monkeypatch, tmp_path, {('indicator', named[0])}, stage)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        status, code, _ = served(c, 'backtest')
        assert (status, code) == (503, 'EXAMPLE_UNAVAILABLE')
        assert c.get('/api/v1/examples/backtest/file/backtest-result', headers=VISITOR).status_code == 503
        assert served(c, 'radar')[0] == 200                               # a tab that does not read it is not withheld
    assert any('example_withheld' in r.message and named[0] in r.message for r in caplog.records)


@pytest.mark.parametrize('stage', ['lab', 'preview'])
def test_the_screener_example_follows_its_preset_and_its_metrics(guests, store, stored_examples, screener_files,
                                                                monkeypatch, tmp_path, stage):
    catalog = screener_files['screener-catalog']
    shown = screener_files['screener-screen']['preset']
    other = next(p for p in catalog['presets'] if p['id'] != shown and p.get('items'))
    metric = next(it for it in other['items'] if it.get('kind') == 'screener_metric'
                  and it['id'] not in json.dumps(screener_files['screener-screen'])
                  and it['id'] not in json.dumps(screener_files['screener-run']))
    with_lab(monkeypatch, tmp_path, {('screener_metric', metric['id'])}, stage)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        status, index, docs = served(c, 'screener')
    assert status == 200, index
    kept = docs['screener-catalog']
    assert metric['id'] not in {e.get('id') for e in kept.get('metrics', []) + kept.get('fundamentals', [])}
    assert other['id'] not in {p['id'] for p in kept['presets']} and shown in {p['id'] for p in kept['presets']}
    # a name or a synonym that spells the id is free text, not a reference: it neither withholds the example nor is cut
    assert json.dumps(kept).count(f'"{metric["id"]}"') == json.dumps(
        [e for e in kept.get('indicators', []) if metric['id'] in json.dumps(e)]).count(f'"{metric["id"]}"')
    with_lab(monkeypatch, tmp_path, {('screener_preset', shown)}, stage)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        assert served(c, 'screener')[:2] == (503, 'EXAMPLE_UNAVAILABLE')


@pytest.mark.parametrize('stage', ['lab', 'preview'])
def test_a_held_back_preset_the_example_does_not_show_is_cut_and_the_example_still_served(
        guests, store, stored_examples, screener_files, monkeypatch, tmp_path, stage):
    """check of steps 2-3 (2026-11-23, PV-3): examples.released_doc's preset line on its own. A preset at lab or
    preview that the stored screen does not show and no stored file reads is cut from the stored catalog; the example
    is still served (read as lab-only, the line kept a preview preset, which then withheld the whole example)."""
    catalog = screener_files['screener-catalog']
    shown = screener_files['screener-screen']['preset']
    stored = json.dumps({n: d for n, d in screener_files.items() if n != 'screener-catalog'})
    quiet = next(p['id'] for p in catalog['presets'] if p['id'] != shown and f'"{p["id"]}"' not in stored
                 and not any(it.get('id') == p['id'] for q in catalog['presets'] for it in (q.get('items') or [])
                             if isinstance(it, dict)))
    with_lab(monkeypatch, tmp_path, {('screener_preset', quiet)}, stage)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        status, index, docs = served(c, 'screener')
    assert status == 200, index
    kept = [p['id'] for p in docs['screener-catalog']['presets']]
    assert quiet not in kept and shown in kept
    assert len(kept) == len(catalog['presets']) - 1
