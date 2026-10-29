"""EXEC-SCREENER Phase 1, deploy runbook steps 5 and 6: check terminal-api's /state and POST /xsection from the private
network, as the screener-worker will call them. Runs as one job on orc-test-runner (run_terminal_check.sh), with
TERMINAL_PROXY_KEY set there only for the run as the reference ${{terminal-api.TERMINAL_PROXY_KEY}}. Standard library
only. The key, presigned URLs and file contents are never printed: only status codes, field names, sha256 values, sizes
and counts.

params.json:
  {"base": "http://terminal-api.railway.internal:8080",
   "expect": "absent" | "present",     absent: right after the terminal-api deploy, before a publication with xsection
                                        files (`xsection` is a /state field whose value is null); present: after the
                                        publisher run (every file of the index granted, downloaded and verified)
   "names": ["price", "actions"],      the files that must be in the index when expect = present
   "manifest_ticker": "BBCA"}          an unchanged route read with the same key (no quota)

Prints OUT {json} per check, ERR {json} for a failed check, then VERDICT PASS|FAIL and JOB_DONE TERMINAL_CHECK."""
import gzip
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

p = json.load(open('params.json'))
BASE = p['base'].rstrip('/')
API = BASE + '/api/terminal/v1'
KEY = os.environ.get('TERMINAL_PROXY_KEY', '')
STATE_FIELDS = {'finished_at', 'price_through', 'broker_through', 'broker_behind_sessions', 'xsection'}
INDEX_FIELDS = {'key', 'sha256', 'bytes', 'rows', 'as_of'}
failed = []


def call(method, url, body=None, key=True, timeout=60):
    headers = {'User-Agent': 'screener-deploy-check'}
    if key:
        headers['x-terminal-proxy-key'] = KEY
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, type(e).__name__.encode()


def out(q, **kw):
    print('OUT ' + json.dumps({'q': q, **kw}, default=str), flush=True)


def err(q, why='unexpected answer', **kw):
    failed.append(q)
    print('ERR ' + json.dumps({'q': q, 'error': why, **kw}, default=str), flush=True)


def code_of(raw):
    """terminal-api answers an error as {"error": <code>, "message": ...} (main.py error, http_error)."""
    try:
        d = json.loads(raw)
        return d.get('error') if isinstance(d, dict) else None
    except ValueError:
        return None


if not KEY:
    err('key', 'TERMINAL_PROXY_KEY is not set for this run')

s, raw = call('GET', BASE + '/ready', key=False)
(out if s == 200 else err)('ready', **({'status': s} if s == 200 else {'why': f'status {s}'}))

s, raw = call('GET', API + '/state', key=False)
ok = s == 401 and code_of(raw) == 'not_signed_in'
(out if ok else err)('state_without_key_refused', status=s, code=code_of(raw))

state = {}
s, raw = call('GET', API + '/state')
if s != 200:
    err('state', f'status {s}', code=code_of(raw))
else:
    state = json.loads(raw)
    index = state.get('xsection')
    summary = {'fields': sorted(state), 'finished_at': state.get('finished_at'),
               'price_through': state.get('price_through'), 'broker_through': state.get('broker_through'),
               'broker_behind_sessions': state.get('broker_behind_sessions'),
               'xsection': ({n: {k: (v[:16] if k == 'sha256' else v) for k, v in f.items() if k != 'key'}
                             for n, f in index.items()} if isinstance(index, dict) else index)}
    if set(state) != STATE_FIELDS:
        err('state', 'the answer does not carry exactly the expected fields', **summary)
    elif p['expect'] == 'absent' and index not in (None, {}):
        err('state', 'xsection index present before a publication wrote it', **summary)
    elif p['expect'] == 'present' and not (isinstance(index, dict) and set(p['names']) <= set(index)
                                           and all(set(f) == INDEX_FIELDS for f in index.values())):
        err('state', 'xsection index missing a file or a field', **summary)
    else:
        out('state', **summary)

# a subscriber without the gateway key is refused 403 gateway_only (main.py gateway), whatever its session
s, raw = call('POST', API + '/xsection', {'names': ['price']}, key=False)
ok = s == 403 and code_of(raw) == 'gateway_only'
(out if ok else err)('xsection_without_key_refused', status=s, code=code_of(raw))

# a name the index does not hold is refused before any grant (no quota, no audit row)
s, raw = call('POST', API + '/xsection', {'names': ['not_published']})
ok = s == 404 and code_of(raw) == 'xsection_not_published'
(out if ok else err)('xsection_unknown_name_refused', status=s, code=code_of(raw))

if p['expect'] == 'present' and isinstance(state.get('xsection'), dict):
    index = state['xsection']
    s, raw = call('POST', API + '/xsection', {'names': p['names']})
    if s != 200:
        err('xsection_grant', f'status {s}', code=code_of(raw))
    else:
        answer = json.loads(raw)
        if answer.get('finished_at') != state.get('finished_at'):
            out('xsection_grant_note', note='granted for another publication than /state named (a run ended between '
                                            'the two calls); compare against the grant', granted=answer.get('finished_at'))
        for f in answer.get('files', []):
            name, url = f.get('name'), f.get('url') or ''
            host = urllib.parse.urlsplit(url).netloc
            st, body = call('GET', url, key=False, timeout=300)
            if st != 200:
                err(f'xsection_file_{name}', f'download status {st}', host=host)
                continue
            sha = hashlib.sha256(body).hexdigest()
            if sha != f.get('sha256') or len(body) != f.get('bytes') or f.get('sha256') != index.get(name, {}).get('sha256'):
                err(f'xsection_file_{name}', 'sha256 or size differs from the grant or the /state index', host=host,
                    bytes=len(body), sha256=sha[:16])
                continue
            doc = json.loads(gzip.decompress(body))
            shape = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in doc.items()
                     if not isinstance(v, (str, int, float)) or k in ('schema_version', 'name', 'as_of', 'generated_at')}
            out(f'xsection_file_{name}', host=host, bytes=len(body), inflated=len(gzip.decompress(body)),
                sha256=sha[:16], rows=f.get('rows'), as_of=f.get('as_of'), shape=shape)

s, raw = call('GET', f"{API}/manifest/{p.get('manifest_ticker', 'BBCA')}")
(out if s == 200 else err)('manifest_unchanged_route', **({'status': s} if s == 200 else {'why': f'status {s}'}))

print('VERDICT', 'PASS' if not failed else 'FAIL ' + ','.join(failed), flush=True)
print('JOB_DONE TERMINAL_CHECK', flush=True)
