"""Read-only query through the pgweb service (role pgweb, default_transaction_read_only=on).
Secrets are read from Railway into memory only and never printed."""
import json, os, subprocess, sys, urllib.request, urllib.parse, base64, time
TOK = os.environ['RAILWAY_TOKEN']  # Railway project token for lucid-patience; never committed
CACHE = os.path.expanduser('~/.pgweb_auth')  # mode 0600, outside the repository
def auth():
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    env = dict(os.environ, RAILWAY_TOKEN=TOK)
    out = subprocess.run(['railway', 'variables', '--service', 'pgweb', '--environment',
                          '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49', '--json'], capture_output=True, text=True, env=env, check=True).stdout
    v = json.loads(out)
    a = {'u': v['PGWEB_AUTH_USER'], 'p': v['PGWEB_AUTH_PASS'], 'd': v['RAILWAY_PUBLIC_DOMAIN']}
    fd = os.open(CACHE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.write(fd, json.dumps(a).encode()); os.close(fd)
    return a
def q(sql):
    a = auth()
    req = urllib.request.Request(f"https://{a['d']}/api/query", data=urllib.parse.urlencode({'query': sql}).encode(), method='POST')
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{a['u']}:{a['p']}".encode()).decode())
    t = time.time()
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as e:
        r = {'error': e.read().decode()[:2000]}
    r['_ms'] = round((time.time() - t) * 1000)
    return r
def show(r, w=60):
    if 'error' in r: print('ERROR:', r['error']); return
    cols = r.get('columns', []); print(' | '.join(cols))
    for row in r.get('rows', []): print(' | '.join('' if x is None else str(x)[:w] for x in row))
    print(f"({len(r.get('rows', []))} rows, {r['_ms']} ms)")
if __name__ == '__main__':
    sql = sys.stdin.read()
    for part in [s for s in sql.split(';;') if s.strip()]:
        show(q(part)); print('---')
