"""EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md 13.1 and section 6; ERRORS M259): the route walk.

Derived from app.routes, not from a list of the routes written today:
- every /api route is either in PUBLIC or depends (directly or through another dependency) on the session dependency;
- every /api route that is not a GET depends on the write dependency (session and CSRF), sign-in and hooks excepted;
- every route under /api/v1/hooks/ is registered in app.hooks.HOOK_ROUTES and carries app.hooks.signed for its own
  path and verifier, so the signature is checked before the handler runs (fix round, re-check R1-15: a registry entry
  alone said nothing about the handler);
- every other /api route carries a capability gate (auth.need or auth.admin, found in its dependency tree) or is named
  in PRINCIPAL_ONLY with the reason it needs none (fix round, re-check R1-27, ERRORS M481 "C3 gaps": the walks of
  tests/test_phase3a_gates.py and tests/test_phase3a_monitor_pages.py are scoped by module and path, so a new module, a
  new path family or a new tab, such as 3e's examples or a relay outside /api/terminal/v1/, escaped every walk);
- no route outside /api takes a write method (it would escape the walk);
- track guest (decision 1 of 2026-11-19, "1a"): a route a visitor without an account reaches depends on the visitor
  dependency (auth.visitor, the guest plan's principal) instead of the session one, and is named in GUEST_OPEN with the
  reason; a guest write depends on the visitor-write dependency (the session's CSRF, or a guest's none). This changes
  the rule "every /api route depends on the session" for exactly those routes (the decision: the Terminal opens without
  an account); every other route keeps it.
"""
import dataclasses

from fastapi.routing import APIRoute
from starlette.routing import Mount, Route

from app import hooks
from app.main import create_app
from app.examples import TABS
from conftest import FakeOrc

# EXEC-MU-ACCOUNTS Phase 1 (CONTRACT.md section 4): the sign-in page's own routes (no session yet; 404 with the switch
# off); the webhook is a hook route (signature, below)
PUBLIC = {'/api/v1/auth/sign-in', '/health', '/ready', '/api/v1/auth/config', '/api/v1/auth/register',
          '/api/v1/auth/register/verify', '/api/v1/auth/code/resend', '/api/v1/auth/password/forgot',
          '/api/v1/auth/password/reset'}
READS = {'GET', 'HEAD'}
# (method, path) -> why the route needs no capability: it serves or changes only the account's own sign-in state, or it
# filters what it answers by the principal itself. A route not named here, in PUBLIC or under the hooks prefix carries
# auth.need(<capability>) or auth.admin(); the walk names the entry to add for a new one.
PRINCIPAL_ONLY = {
    ('GET', '/api/v1/auth/session'): 'the session answer itself (who is signed in, the access object)',
    ('POST', '/api/v1/auth/sign-out'): "the account's own sign-out",
    ('POST', '/api/v1/auth/sign-out-all'): "the account's own sessions",
    ('POST', '/api/v1/auth/password/change'): "the account's own password",
    ('POST', '/api/v1/auth/mfa/verify'): "the account's own second factor (a pending session passes it here)",
    ('GET', '/api/v1/catalog/{kind}'): 'answers only the entries the principal holds (catalog.py, CONTRACT 8a)',
    ('GET', '/api/v1/preferences'): "the account's own preferences; a key's tab capability is checked per key (R1-18)",
    ('PUT', '/api/v1/preferences/{key}'): "the account's own preferences; a key's tab capability is checked per key "
                                          '(R1-18)',
    ('GET', '/api/v1/auth/guest'): 'what this request holds without a session (the guest plan) or with one (its session)',
}
# (method, path) -> why a visitor without an account reaches it (track guest; principal.py guest_principal): the
# Terminal's data relay and the catalog the Terminal reads its items from, and the guest answer itself
GUEST_OPEN = {
    ('GET', '/api/terminal/v1/{path:path}'): "the Terminal's data, for what the guest plan grants (terminal.view)",
    ('POST', '/api/terminal/v1/{path:path}'): "the Terminal's data, for what the guest plan grants (terminal.view)",
    ('GET', '/api/v1/catalog/{kind}'): 'the items the Terminal shows the principal (catalog.py, CONTRACT 8a)',
    ('GET', '/api/v1/auth/guest'): "what a visitor holds (the guest plan's access)",
    # 3e, the example mode (user 2026-11-21; ERRORS M527): each tab's example, for what the guest plan grants
    # (<tab>.example, migration 20261121_002); a tab joins with its page (app/examples.py TABS)
    **{('GET', path.format(tab)): f"the {tab} example's files, for what the guest plan grants ({tab}.example)"
       for tab in TABS for path in ('/api/v1/examples/{}/index', '/api/v1/examples/{}/file/{{name}}')},
}


def configured(settings):
    """Every optional feature on, so every route that a configuration can add is in the table."""
    return dataclasses.replace(
        settings, terminal_url='http://terminal.invalid', terminal_proxy_key='t' * 32,
        backtest_worker_url='http://backtest.invalid', backtest_worker_key='b' * 32, backtest_timeout_seconds=60,
        backtest_max_result_bytes=1_000_000, screener_worker_url='http://screener.invalid',
        screener_worker_key='s' * 32, screener_timeout_seconds=60)


def calls(dependant):
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from calls(dependency)


def gates(app):
    """The capability checks of the app: every auth.need(...) and auth.admin(...) dependency built so far."""
    return set(app.state.auth._needs.values())


def problems(app, registry=None):
    registry = hooks.HOOK_ROUTES if registry is None else registry
    session, write = app.state.session_dependency, app.state.write_dependency
    visitor, visitor_write = app.state.visitor_dependency, app.state.visitor_write_dependency
    gated = gates(app)
    found = []
    for route in app.routes:
        if isinstance(route, Mount):
            found.append(f'{route.path}: a mount escapes the route walk')
            continue
        methods = set(getattr(route, 'methods', None) or ())
        if not route.path.startswith('/api/'):
            if methods - READS:
                found.append(f'{route.path}: a write method outside /api')
            continue
        if not isinstance(route, APIRoute):
            found.append(f'{route.path}: not a FastAPI route, its dependencies cannot be checked')
            continue
        used = set(calls(route.dependant))
        if hooks.is_hook_path(route.path):
            verify = registry.get(route.path)
            if not callable(verify):
                found.append(f'{route.path}: a hook route without a signature verifier in HOOK_ROUTES')
            elif not any(getattr(c, 'hook_path', None) == route.path and getattr(c, 'verifier', None) is verify
                         for c in used):
                found.append(f"{route.path}: a hook route that does not carry hooks.signed('{route.path}', <secret>) "
                             'as a dependency, so nothing verifies its signature before the handler runs')
            continue
        if route.path in PUBLIC:
            continue
        guest = visitor in used
        for method in sorted(methods):
            if guest and (method, route.path) not in GUEST_OPEN:
                found.append(f'{method} {route.path}: a visitor without an account reaches it (auth.visitor) but '
                             f"GUEST_OPEN does not name it; add GUEST_OPEN[('{method}', '{route.path}')] = '<why>' or "
                             'depend on auth.principal')
        if session not in used and not guest:
            found.append(f'{route.path} {sorted(methods)}: no session dependency')
        if methods - READS and write not in used and not (guest and visitor_write in used):
            found.append(f'{route.path} {sorted(methods)}: a write without the write (CSRF) dependency')
        if not used & gated:
            for method in sorted(methods):
                if (method, route.path) not in PRINCIPAL_ONLY:
                    found.append(f'{method} {route.path} ({route.endpoint.__module__}): no capability gate; carry '
                                 "auth.need('<tab>.view or the run/save capability'"
                                 f"{', write=True' if method not in READS else ''}) or auth.admin(), or, when it "
                                 "serves only the account's own state, add "
                                 f"PRINCIPAL_ONLY[('{method}', '{route.path}')] = '<why it needs no capability>'")
    return found


def test_every_api_route_carries_the_session_and_every_write_carries_csrf(settings, store):
    app = create_app(configured(settings), store, FakeOrc())
    assert problems(app) == []
    paths = {route.path for route in app.routes}
    assert PUBLIC <= paths, PUBLIC - paths                       # the public list names no route that has gone
    # every GUEST_OPEN entry is a route that really admits visitors (no stale entry widens the list)
    visitor = app.state.visitor_dependency
    admitted = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) and visitor in set(calls(r.dependant))
                for m in r.methods}
    assert admitted == set(GUEST_OPEN), admitted ^ set(GUEST_OPEN)
    api = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith('/api/')]
    assert len(api) > 40 and any(set(r.methods) - READS for r in api)   # the walk really covers the table


def test_the_walk_refuses_what_it_must(settings, store):
    """The checker itself: a write on session only (the manual POST before M259), a route without a session, and a hook
    route missing from the registry are each reported."""
    app = create_app(configured(settings), store, FakeOrc())
    session = app.state.session_dependency
    from fastapi import Depends

    @app.post('/api/v1/example/session-only')
    async def session_only(_=Depends(session)):
        return {}

    @app.get('/api/v1/example/open')
    async def open_route():
        return {}

    @app.post('/api/v1/hooks/example')
    async def unregistered_hook():
        return {}

    registry = {'/api/v1/hooks/example-signed': lambda h, b, s: False}

    @app.post('/api/v1/hooks/example-signed')
    async def signed_hook(raw=Depends(hooks.signed('/api/v1/hooks/example-signed', 'secret', registry))):
        return {}

    found = problems(app)
    assert any('/api/v1/example/session-only' in f and 'CSRF' in f for f in found), found
    assert any('/api/v1/example/open' in f and 'no session' in f for f in found), found
    assert any('/api/v1/example/session-only' in f and 'no capability gate' in f for f in found), found
    assert any('/api/v1/hooks/example' in f for f in found), found
    # re-check R1-15 (changed with the fix): a registry entry alone no longer passes; the route must carry
    # hooks.signed for its own path and verifier
    with_entry = problems(app, {**registry, '/api/v1/hooks/example': lambda h, b, s: False})
    assert any("/api/v1/hooks/example:" in f and 'hooks.signed' in f for f in with_entry), with_entry
    assert not any('/api/v1/hooks/example-signed' in f for f in problems(app, registry))
    app.router.routes.append(Route('/upload', lambda r: None, methods=['POST']))
    assert any('/upload' in f for f in problems(app))


def test_every_registered_hook_is_a_route(settings, store):
    """The registry names no hook that is not served (Phase 0 has none: HOOK_ROUTES is empty)."""
    app = create_app(configured(settings), store, FakeOrc())
    assert set(hooks.HOOK_ROUTES) <= {r.path for r in app.routes if hooks.is_hook_path(r.path)}
