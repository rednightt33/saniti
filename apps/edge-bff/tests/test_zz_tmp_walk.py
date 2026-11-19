from fastapi.routing import APIRoute
from app.main import create_app
from conftest import FakeOrc
from test_route_table import configured

OUT = '/tmp/claude-0/-home-user-saniti/f3bec3b8-f6e3-5a54-b257-4a56b384bdc8/scratchpad/fx_records/probe/walk.txt'


def calls(d):
    for x in d.dependencies:
        yield x.call
        yield from calls(x)


def test_walk(settings, store):
    app = create_app(configured(settings), store, FakeOrc())
    needs = {check: key for key, check in app.state.auth._needs.items()}
    sess, wr = app.state.session_dependency, app.state.write_dependency
    out = []
    for r in app.routes:
        methods = sorted(getattr(r, 'methods', None) or [])
        if not isinstance(r, APIRoute):
            out.append(f'NONAPI {r.path} {methods}')
            continue
        used = list(calls(r.dependant))
        held = sorted({str(needs[c]) for c in used if c in needs})
        names = [getattr(c, '__name__', str(c)) for c in used]
        out.append(f"{','.join(methods):12} {r.path:60} {r.endpoint.__module__:18} "
                   f"{'S' if sess in used else '-'}{'W' if wr in used else '-'} {held} {names}")
    open(OUT, 'w').write('\n'.join(out))
