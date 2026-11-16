"""EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md 13.1 and section 6; ERRORS M259): the route walk.

Derived from app.routes, not from a list of the routes written today:
- every /api route is either in PUBLIC or depends (directly or through another dependency) on the session dependency;
- every /api route that is not a GET depends on the write dependency (session and CSRF), sign-in and hooks excepted;
- every route under /api/v1/hooks/ is registered in app.hooks.HOOK_ROUTES with its signature verifier;
- no route outside /api takes a write method (it would escape the walk).
"""
import dataclasses

from fastapi.routing import APIRoute
from starlette.routing import Mount, Route

from app import hooks
from app.main import create_app
from conftest import FakeOrc

PUBLIC = {'/api/v1/auth/sign-in', '/health', '/ready'}
READS = {'GET', 'HEAD'}


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


def problems(app, registry=None):
    registry = hooks.HOOK_ROUTES if registry is None else registry
    session, write = app.state.session_dependency, app.state.write_dependency
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
            if not callable(registry.get(route.path)):
                found.append(f'{route.path}: a hook route without a signature verifier in HOOK_ROUTES')
            continue
        if route.path in PUBLIC:
            continue
        if session not in used:
            found.append(f'{route.path} {sorted(methods)}: no session dependency')
        if methods - READS and write not in used:
            found.append(f'{route.path} {sorted(methods)}: a write without the write (CSRF) dependency')
    return found


def test_every_api_route_carries_the_session_and_every_write_carries_csrf(settings, store):
    app = create_app(configured(settings), store, FakeOrc())
    assert problems(app) == []
    paths = {route.path for route in app.routes}
    assert PUBLIC <= paths, PUBLIC - paths                       # the public list names no route that has gone
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

    found = problems(app)
    assert any('/api/v1/example/session-only' in f and 'CSRF' in f for f in found), found
    assert any('/api/v1/example/open' in f and 'no session' in f for f in found), found
    assert any('/api/v1/hooks/example' in f for f in found), found
    assert not any('/api/v1/hooks/example' in f for f in problems(app, {'/api/v1/hooks/example': lambda h, b: False}))
    app.router.routes.append(Route('/upload', lambda r: None, methods=['POST']))
    assert any('/upload' in f for f in problems(app))


def test_every_registered_hook_is_a_route(settings, store):
    """The registry names no hook that is not served (Phase 0 has none: HOOK_ROUTES is empty)."""
    app = create_app(configured(settings), store, FakeOrc())
    assert set(hooks.HOOK_ROUTES) <= {r.path for r in app.routes if hooks.is_hook_path(r.path)}
