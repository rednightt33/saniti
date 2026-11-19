"""EXEC-MU-ACCOUNTS Phase 0, ERRORS M473: every browser storage key of the shell and the six pages is classed in the
storage registry of apps/edge-bff/shared/edge-session.ts (`browser` or `user`), so sign-out and a change of user clear
every key of an account. The test reads the code, not a browser:

- each localStorage / sessionStorage call, each `store.get|set|remove|del` of the pages' storage wrappers and each
  IndexedDB open names its key as a literal, a template or "literal" + value (a prefix), or a constant of the code;
- every string literal of the pages in the `ml.` and `scr.` namespaces (the keys kept in lists, such as LAYOUT_KEYS);
- a call whose key is a value the code builds elsewhere is listed in DYNAMIC with the keys it reaches.

A key found that no registry entry covers fails the test, and so does a registry entry the code no longer uses. The
shell's copy static/edge-session.js must be the build of that source (shared/build-shell.mjs).
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / 'shared' / 'edge-session.ts'
APPS = ('terminal', 'backtest', 'screener', 'radar', 'overview', 'watchlist')
SHELL = ('static/index.html', 'static/edge-client.js', 'static/edge-view.js', 'static/edge-labels.js', 'static/edge-docx.js')

ENTRY = re.compile(r"\{ key:'((?:[^'\\]|\\.)*)', match:'(exact|prefix)', area:'(local|session|idb)', kind:'(browser|user)',")

# calls whose key is a value made elsewhere: (file, argument text) -> the keys it reaches, each also found by the scan
DYNAMIC = {
    ('static/index.html', 'key'): ['edge-pins-height', 'edge-pins-open', 'edge-flow-open', 'edge-side-attach:', 'edge-sources-open:'],
    ('terminal/src/ui/fullscreen.ts', 'k'): ['ml.stats.collapsed', 'ml.broker.collapsed', 'ml.flow.collapsed'],
    ('terminal/src/ui/reorder.ts', 'key'): ['ml.stats.order', 'ml.broker.order'],
    ('terminal/src/app/layouts.ts', 'k'): ['ml.ind.v1', 'ml.tf', 'ml.legend.hidden'],
    ('terminal/src/app/indMenu.ts', 'k'): ['ml.ind.box', 'ml.ind.navw'],
    ('terminal/src/app/drawings.ts', 'key'): ['ml.draw.shape', 'ml.draw.measure'],
    ('terminal/src/app/drawings.ts', 'g.key'): ['ml.draw.shape', 'ml.draw.measure'],
    ('terminal/src/app/drawings.ts', 'repo.key(symbol'): ['ml.drawings.'],
    ('terminal/src/app/drawings.ts', '`${repo.key(symbol'): ['ml.drawings.'],
    ('terminal/src/data/drawingsApi.ts', 'local'): ['ml.drawings.'],
    ('terminal/src/data/rack.ts', 'sha'): [],          # the IndexedDB object store of 'terminal-files', not a storage key
    ('terminal/src/data/drawingsApi.ts', "s === 'chart' ?"): ['ml.drawings.'],
    # the legacy keys the shell removes on load
    ('static/edge-client.js', 'k'): ['edge-auth-monitor-conversations', 'edge-session', 'edge-active-run', 'edge-research-context'],
    # the pages' storage wrappers: their keys are their callers', which the scan reads (store.get/set/remove/del)
    ('terminal/src/app/context.ts', 'k'): [],
    ('screener/src/storage.ts', 'k'): [],
}

CALL = re.compile(r"\b(localStorage|sessionStorage)\.(?:getItem|setItem|removeItem)\(\s*([^,)]+)"
                  r"|\b(?:store|storage)\.(?:get|set|remove|del)(?:<[^>()]*>)?\(\s*([^,)]+)"
                  r"|\b(?:indexedDB|factory)\.(?:open|deleteDatabase)\(\s*([^,)]+)")
NAMESPACE = re.compile(r"""['"`]((?:ml|scr)\.[A-Za-z][A-Za-z0-9._:-]*)""")


def registry():
    entries = ENTRY.findall(SHARED.read_text())
    assert entries, 'no registry entries read from shared/edge-session.ts'
    return entries


def sources():
    files = [ROOT / p for p in SHELL] + [SHARED]
    for app in APPS:
        files += sorted((ROOT / app / 'src').rglob('*.ts'))
    return {str(f.relative_to(ROOT)): f.read_text() for f in files}


def area_of(store, file):
    if store == 'sessionStorage':
        return 'session'
    return 'local'


def constant(name, text, everything):
    """the value of a constant: `NAME = 'x'` (or a template, a prefix), or `OBJ = {..., prop:'x'}` for OBJ.prop"""
    if '.' in name:
        obj, prop = name.split('.', 1)
        pat = re.compile(r'\b' + re.escape(obj) + r"\s*=\s*\{[^}]*\b" + re.escape(prop) + r"\s*:\s*(['\"`])([^'\"`$]*)")
    else:
        pat = re.compile(r'\b' + re.escape(name) + r"\s*=\s*(['\"`])([^'\"`$]*)(\$\{)?")
    for body in [text] + list(everything.values()):
        m = pat.search(body)
        if m:
            return m.group(2)
    return None


def keys_found():
    files = sources()
    found, unresolved = [], []
    for name, text in files.items():
        for m in CALL.finditer(text):
            store, arg = m.group(1), (m.group(2) or m.group(3) or m.group(4)).strip()
            area = 'idb' if m.group(4) else area_of(store, name)
            lit = re.match(r"""^(['"`])([^'"`$]*)(.)?""", arg)
            if lit and lit.group(2):
                found.append((name, lit.group(2), area))
                continue
            dyn = next((v for (f, a), v in DYNAMIC.items() if f == name and (arg == a or (len(a) > 3 and arg.startswith(a)))), None)
            if dyn is not None:
                found += [(name, k, None) for k in dyn]          # any area: the listed keys name their own
                continue
            ident = re.match(r'^([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)$', arg)
            value = constant(ident.group(1), text, files) if ident else None
            if value:
                found.append((name, value, area))
            else:
                unresolved.append(f'{name}: {m.group(0)}')
        if name.endswith('.ts'):
            found += [(name, k, 'local') for k in NAMESPACE.findall(text)]
        if name == 'static/index.html':       # the shell's stored()/keep() helpers of the Monitor page
            found += [(name, k, 'local') for k in re.findall(r'\b(?:stored|keep)\("([^"]+)"', text)]
    return found, unresolved


def covered(key, area, entries):
    for k, match, a, _ in entries:
        if area is not None and a != area:
            continue
        if key == k or (match == 'prefix' and key.startswith(k)) or k.startswith(key):   # a literal naming a key family
            return True
    return False


def test_every_storage_key_is_classified():
    entries = registry()
    found, unresolved = keys_found()
    assert not unresolved, 'storage calls whose key the test cannot read; add them to DYNAMIC:\n' + '\n'.join(unresolved)
    missing = sorted({f'{f}: {k} ({a})' for f, k, a in found if not covered(k, a, entries)})
    assert not missing, ('storage keys not classed in shared/edge-session.ts STORAGE (add each as browser or user, M473):\n'
                         + '\n'.join(missing))


def test_every_registry_entry_is_used():
    files = sources()
    every = '\n'.join(t for n, t in files.items() if n != 'shared/edge-session.ts') + files['shared/edge-session.ts'].split('STORAGE')[0]
    shared_rest = files['shared/edge-session.ts'].split('export function classify')[1]
    stale = [k for k, *_ in registry() if k not in every and k not in shared_rest]
    assert not stale, f'registry entries no code uses (remove them): {stale}'


def test_user_keys_named_by_the_contract_are_user():
    kinds = {(k, a): kind for k, _, a, kind in registry()}
    for key, area in [('edge-side-attach:', 'session'), ('edge-model-choice', 'local'), ('ml.layout.', 'local'),
                      ('ml.symbol', 'local'), ('ml.drawings.', 'local'), ('scr.last', 'local'), ('scr.boot', 'local'),
                      ('edge.watchlist.view', 'local'), ('terminal-files', 'idb')]:
        assert kinds.get((key, area)) == 'user', key
    for key in ('edge-auth-monitor-theme', 'edge-monitor-width', 'ml.stats.', 'scr.panes'):
        assert kinds.get((key, 'local')) == 'browser', key


FLAGS = re.compile(r"\{ key:'((?:[^'\\]|\\.)*)', match:'(exact|prefix)', area:'(local|session|idb)', kind:'(browser|user)', ((?:sync|cache):true, )?(?:cap:'[a-z][a-z0-9_.]*', )?where:")
# re-check R1-18: a sync entry's capability (cap), the view of the tab whose data it holds
CAP = re.compile(r"\{ key:'((?:[^'\\]|\\.)*)', match:'exact', area:'local', kind:'user', sync:true, (?:cap:'([a-z][a-z0-9_.]*)', )?where:")
# contract 4b (EXEC-MU-ACCOUNTS Phase 1): the account preferences copied to the server (GET/PUT /api/v1/preferences)
SYNCED = {'edge-model-choice', 'ml.symbol', 'ml.tf', 'ml.fi.metric', 'ml.chart.style', 'ml.chart.mode', 'ml.vol.on',
          'ml.vol.removed', 'ml.ind.v1', 'ml.ind.filters', 'ml.ind.favs', 'ml.legend.hidden', 'ml.events.v1',
          'ml.flow.filters', 'ml.flow.cum', 'ml.assets.v1', 'ml.my', 'scr.last', 'scr.extraCols', 'edge.watchlist.view'}


def test_every_user_key_is_sync_or_cache():
    """contract 4b: a `user` key with no server copy is either `sync` (a preference or saved item copied to the account)
    or `cache` (the account holds the original elsewhere, or it is transient); a `browser` key is neither. Only an exact
    localStorage key can be synced (the server keeps one value per key)."""
    text = SHARED.read_text()
    rows = FLAGS.findall(text)
    assert len(rows) == len(registry()), 'a registry line is not in the form { key, match, area, kind, sync|cache, where, what }'
    wrong = [k for k, match, area, kind, flag in rows if (kind == 'user') != bool(flag)
             or (flag.startswith('sync') and (match != 'exact' or area != 'local'))]
    assert not wrong, f'user keys need exactly one of sync:true or cache:true, browser keys none: {wrong}'
    synced = {k for k, _, _, _, flag in rows if flag.startswith('sync')}
    assert synced == SYNCED, synced ^ SYNCED


def test_the_scan_sees_an_unclassified_key():
    entries = registry()
    assert not covered('ml.newthing', 'local', entries)
    assert covered('ml.drawings.flow.BBRI', 'local', entries)
    assert covered('edge-side-attach:conv_1', 'session', entries)


def test_shell_copy_is_the_build_of_the_shared_module():
    first = (ROOT / 'static' / 'edge-session.js').read_text().split('\n', 1)[0]
    sha = hashlib.sha256(SHARED.read_bytes()).hexdigest()
    assert f'sha256={sha}' in first, 'static/edge-session.js is not built from shared/edge-session.ts: run node shared/build-shell.mjs'


def test_shell_loads_the_session_module_before_its_client():
    html = (ROOT / 'static' / 'index.html').read_text()
    assert html.index('<script src="/edge-session.js"></script>') < html.index('<script src="/edge-client.js"></script>')
    client = (ROOT / 'static' / 'edge-client.js').read_text()
    assert 'clearUserState({signOut:true})' in client and 'noteLogin(' in client


def test_the_server_reads_each_sync_key_with_the_capability_the_registry_names():
    """Re-check R1-18 (CONTRACT.md 8b D5: reads need <tab>.view): catalog/storage_sync.json, which app/preferences.py
    reads, is the registry's sync keys with their `cap` (shared/build-shell.mjs writes both from shared/edge-session.ts;
    run it after editing the registry). A key of one tab names that tab's view capability; only a key every tab reads
    (its `where` names several tabs) names none."""
    import json
    written = json.loads((ROOT / 'catalog' / 'storage_sync.json').read_text())['keys']
    declared = {k: cap or None for k, cap in CAP.findall(SHARED.read_text())}
    assert written == declared, ('catalog/storage_sync.json is not the registry of shared/edge-session.ts: run '
                                 'node shared/build-shell.mjs')
    assert set(declared) == SYNCED
    shared = {k for k, cap in declared.items() if cap is None}
    assert shared == {'ml.symbol'}, f'sync keys with no tab capability (only a key every tab shares has none): {shared}'
    assert all(cap.endswith('.view') for cap in declared.values() if cap), declared


def test_a_browser_key_family_never_names_a_ticker_or_symbol():
    """Re-check R1-20: a `browser` prefix survives sign-out and a change of user, so its suffix must not carry account
    content. A key built from a ticker or a symbol (a template or a concatenation onto the prefix) names what the
    account looks at, and belongs to a `user` family (shared/edge-session.ts STORAGE)."""
    browser = [k for k, match, _, kind in registry() if match == 'prefix' and kind == 'browser']
    built = re.compile(r"""`(?P<t>[^`]*)`|['"](?P<p>[^'"]+)['"]\s*\+\s*(?P<v>[A-Za-z_][A-Za-z0-9_.()]*)""")
    found = []
    for name, text in sources().items():
        for m in built.finditer(text):
            if m.group('t') is not None:
                key, values = m.group('t'), re.findall(r'\$\{([^}]*)\}', m.group('t'))
            else:
                key, values = m.group('p'), [m.group('v')]
            if values and any(key.startswith(p) for p in browser) and any(re.search(r'ticker|symbol|\bsym\b', v, re.I) for v in values):
                found.append(f'{name}: {key}')
    assert not found, 'browser-class keys that name a ticker or symbol (class the family user):\n' + '\n'.join(found)
