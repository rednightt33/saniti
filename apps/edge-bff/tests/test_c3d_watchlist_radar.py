"""EXEC-MU-ACCOUNTS Phase 3d (ERRORS M476; CONTRACT.md 8b "3d"): the Radar's screens are a file of their own,
watchlist-radar, which edge-bff serves only with radar.view (a file <family>-<page> carries that page's content,
app/pages.py carried). Without radar.view the Watchlist index does not list it and its bytes answer 403
CAPABILITY_REQUIRED (capability radar.view) before the shared caches and before any terminal-api call; with it both files
are served. The base file is the Watchlist's own and needs watchlist.view alone. A switch-off owner ('*') reads both."""
import gzip
import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import pages
from app.main import create_app
from conftest import FakeOrc
from test_phase3a_gates import override
from test_principal import make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_radar import acknowledge
from test_watchlist_page import configured

STOCKS = gzip.compress(json.dumps({'schema': 1, 'ticker': ['AAAA']}).encode(), mtime=0)
RADAR = gzip.compress(json.dumps({'schema': 1, 'radar_date': '2026-11-09', 'radar': {'AAAA': ['S7']}}).encode(), mtime=0)
FILES = {'watchlist-stocks': STOCKS, 'watchlist-radar': RADAR}
SHA = {n: hashlib.sha256(b).hexdigest() for n, b in FILES.items()}


class TwoFiles:
    """terminal-api's GET/POST /watchlist with the two files of a Phase 3d publication, and the bucket's GET."""
    calls = []

    def __init__(self, timeout):
        pass

    async def aclose(self):
        pass

    def stream(self, method, url):
        TwoFiles.calls.append((method, url))
        body = FILES[url.rsplit('/', 1)[-1]]

        class Answer:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def aiter_bytes(self):
                yield body
        return Answer()

    async def request(self, method, url, params=None, content=None, headers=None):
        TwoFiles.calls.append((method, url))
        if url.endswith('/api/terminal/v1/watchlist') and method == 'GET':
            return acknowledge(httpx.Response(200, json={'finished_at': '2026-11-20T10:00:00Z', 'files': {
                n: {'sha256': SHA[n], 'bytes': len(b), 'rows': 1, 'as_of': '2026-11-13'} for n, b in FILES.items()}}),
                headers)
        if url.endswith('/api/terminal/v1/watchlist') and method == 'POST':
            name = json.loads(content)['names'][0]
            return acknowledge(httpx.Response(200, json={'files': [{'name': name, 'url': f'https://bucket.example/{name}',
                                                                    'sha256': SHA[name], 'bytes': len(FILES[name])}]}),
                               headers)
        return httpx.Response(404, json={'error': 'not_found'})


@pytest.fixture
def terminal(monkeypatch):
    TwoFiles.calls = []
    monkeypatch.setattr(pages.httpx, 'AsyncClient', TwoFiles)


def watcher(store, name, radar):
    user = make_user(store, name, name + '-password')
    override(store, user['user_id'], 'watchlist.view', 'true')
    override(store, user['user_id'], 'radar.view', 'true' if radar else 'false')
    return user


def test_without_radar_view_the_radar_file_is_neither_listed_nor_served(on, store, terminal):
    watcher(store, 'nora', radar=False)
    with TestClient(create_app(configured(on), store, FakeOrc())) as c:
        h = sign_in(c, 'nora', 'nora-password')
        index = c.get('/api/v1/watchlist/index', headers=h)
        assert index.status_code == 200 and set(index.json()['files']) == {'watchlist-stocks'}
        base = c.get('/api/v1/watchlist/file/watchlist-stocks', headers=h)
        assert base.status_code == 200 and json.loads(base.content)['ticker'] == ['AAAA']
        before = list(TwoFiles.calls)
        for sha in ('', SHA['watchlist-radar']):
            r = c.get('/api/v1/watchlist/file/watchlist-radar' + (f'?sha={sha}' if sha else ''), headers=h)
            error = r.json()['error']
            assert r.status_code == 403 and error['code'] == 'CAPABILITY_REQUIRED', r.text
            assert error['details']['capability'] == 'radar.view'
        assert TwoFiles.calls == before                    # refused before the caches and before terminal-api


def test_with_radar_view_both_files_are_served(on, store, terminal):
    watcher(store, 'rafi', radar=True)
    with TestClient(create_app(configured(on), store, FakeOrc())) as c:
        h = sign_in(c, 'rafi', 'rafi-password')
        index = c.get('/api/v1/watchlist/index', headers=h).json()
        assert set(index['files']) == {'watchlist-stocks', 'watchlist-radar'}
        r = c.get(f"/api/v1/watchlist/file/watchlist-radar?sha={SHA['watchlist-radar']}", headers=h)
        assert r.status_code == 200 and json.loads(r.content)['radar'] == {'AAAA': ['S7']}


def test_the_carried_page_is_read_from_the_name_against_the_families():
    files = pages.PageFiles.__new__(pages.PageFiles)
    files.family = 'watchlist'
    pages.FAMILIES.update({'radar', 'overview', 'watchlist'})
    assert files.carried('watchlist-radar') == 'radar'
    assert files.carried('watchlist-overview') == 'overview'       # the same rule for any other page's content
    assert files.carried('watchlist-stocks') is None                # not a page: the Watchlist's own file
    assert files.carried('watchlist-watchlist') is None and files.carried('radar-days') is None
