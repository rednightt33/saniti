"""The user, 2026-11-20 (EXEC option A): the footer's Privacy and Terms links show only once their texts exist. The
addresses are settings (EDGE_PRIVACY_URL, EDGE_TERMS_URL: an https address or a path of this site); /api/v1/auth/config
names them (null when unset), and the page draws a link only for an address it was given. Before, both links led
nowhere (#privacy, #terms) on every public page (the live checker after the switch-on, visitor F4)."""
import dataclasses
import socket

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from conftest import FakeOrc
from test_auth_pages import page  # noqa: F401 (fixture)
from test_auth_pages_live import serve
from test_beta_live_site import live_of


def live(settings, **change):
    return dataclasses.replace(live_of(settings), guests_enabled=True, prelaunch_enabled=True, **change)


def test_the_config_names_the_addresses_only_once_set(settings, store):
    with TestClient(create_app(live(settings), store, FakeOrc())) as c:
        assert c.get('/api/v1/auth/config').json()['legal'] == {'privacy': None, 'terms': None}
    on = live(settings, privacy_url='/privacy', terms_url='https://edgefinance.id/terms')
    with TestClient(create_app(on, store, FakeOrc())) as c:
        assert c.get('/api/v1/auth/config').json()['legal'] == {'privacy': '/privacy',
                                                               'terms': 'https://edgefinance.id/terms'}


@pytest.mark.parametrize('value', ['http://edgefinance.id/privacy', '//evil.example/privacy', 'javascript:alert(1)',
                                   'https://a.example/"><script>', 'privacy.html'])
def test_an_address_that_is_not_https_or_a_path_of_this_site_is_refused_at_start(settings, value):
    with pytest.raises(ValueError, match='EDGE_PRIVACY_URL'):
        dataclasses.replace(settings, privacy_url=value).validate()


@pytest.mark.parametrize('change, shown', [({}, []), ({'privacy_url': '/privacy'}, ['Privacy']),
                                           ({'privacy_url': '/privacy', 'terms_url': 'https://edgefinance.id/terms'},
                                            ['Privacy', 'Terms'])])
def test_the_footer_draws_a_link_only_for_an_address_it_was_given(settings, store, page, change, shown):
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    on = live(settings, origin=f'http://127.0.0.1:{port}', **change)
    server, thread = serve(on, store, port, sock)
    try:
        page.goto(on.origin + '/login')
        page.locator('.auth-footer').wait_for()
        page.wait_for_timeout(300)
        links = page.locator('.auth-footer a')
        assert links.all_inner_texts() == shown
        assert '#privacy' not in page.content() and '#terms' not in page.content()
        if shown:
            assert links.first.evaluate('a => [new URL(a.href).origin, new URL(a.href).pathname]') == [on.origin, '/privacy']
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()
