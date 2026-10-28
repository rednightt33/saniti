"""Local stand-in for EDGE + terminal-api, for checking the Terminal's added assets in a browser.
Serves the built page at /terminal-app/ and answers the routes live.ts calls with synthetic columnar files of the same
shape as the rack's. Usage: python mock_server.py <dist dir> <port>"""
import datetime as dt
import json
import math
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DIST = Path(sys.argv[1]); PORT = int(sys.argv[2])
TICKERS = [('MAPI', 'Mitra Adiperkasa Tbk', 'stock', 'Consumer Cyclicals'), ('BBCA', 'PT Bank Central Asia Tbk', 'stock', 'Financials'),
           ('BBRI', 'PT Bank Rakyat Indonesia (Persero) Tbk', 'stock', 'Financials'), ('IHSG', 'Composite Index', 'index', None),
           ('GOTO', 'GoTo Gojek Tokopedia Tbk', 'stock', 'Technology')]
BROKERS = [('YP', 'Local'), ('PD', 'Local'), ('CC', 'Local'), ('AK', 'Foreign'), ('ZP', 'Foreign'), ('KZ', 'Foreign'), ('RX', 'Foreign'), ('DX', 'Local')]
start = dt.date(2025, 1, 2)
DAYS = [start + dt.timedelta(days=k) for k in range(560)]
DAYS = [d.isoformat() for d in DAYS if d.weekday() < 5][:380]
BROKER_THROUGH = DAYS[-2]                     # the broker data stops a session before the price


def price_doc(ticker):
    rnd = random.Random(ticker); base = {'MAPI': 1400, 'BBCA': 9000, 'BBRI': 4200, 'IHSG': 7100, 'GOTO': 60}[ticker]
    days = DAYS[30:] if ticker == 'GOTO' else DAYS             # GOTO starts later; BBRI skips some sessions
    if ticker == 'BBRI': days = [d for k, d in enumerate(DAYS) if k % 17]
    d, o, h, l, c, v = [], [], [], [], [], []
    p = base
    for k, day in enumerate(days):
        op = p; p = max(1, p * (1 + rnd.gauss(0.0004, 0.015)) + math.sin(k / 15) * base * .002)
        d.append(day); o.append(round(op, 2)); c.append(round(p, 2)); h.append(round(max(op, p) * 1.01, 2)); l.append(round(min(op, p) * .99, 2)); v.append(rnd.randint(1e6, 9e6))
    return {'columns': ['d', 'o', 'h', 'l', 'c', 'v'], 'd': d, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v}


def broker_doc(ticker, year):
    rnd = random.Random(ticker + year); cols = {k: [] for k in ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl']}
    scale = {'MAPI': 2e9, 'BBCA': 40e9, 'BBRI': 20e9, 'GOTO': 1e9}[ticker]
    for day in DAYS:
        if not day.startswith(year) or day > BROKER_THROUGH: continue
        for b, kind in BROKERS:
            for inv in ('Foreign', 'Domestic'):
                for board in ('Regular', 'Nego'):
                    if board == 'Nego' and rnd.random() > .05: continue
                    bv, sv = rnd.random() * scale, rnd.random() * scale
                    if ticker == 'BBCA' and inv == 'Foreign': bv *= 1.3
                    for k, val in zip(cols, [day, b, inv, board, round(bv), round(sv), round(bv / 9000 / 100), round(sv / 9000 / 100)]):
                        cols[k].append(val)
    return {'columns': list(cols), **cols}


def ref(name):
    if name == 'tickers':
        return {'columns': ['ticker', 'name', 'type', 'sector'], 'ticker': [t[0] for t in TICKERS], 'name': [t[1] for t in TICKERS],
                'type': [t[2] for t in TICKERS], 'sector': [t[3] for t in TICKERS]}
    if name == 'brokers':
        return {'columns': ['code', 'type'], 'code': [b for b, _ in BROKERS], 'type': [k for _, k in BROKERS]}
    return {'columns': ['ticker', 'sha256'], 'ticker': [], 'sha256': []}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header('content-type', ctype); self.send_header('content-length', str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/terminal-app/': return self.send(200, (DIST / 'index.html').read_bytes(), 'text/html')
        if p.startswith('/terminal-app/assets/'):
            f = DIST / 'assets' / p.rsplit('/', 1)[1]
            return self.send(200, f.read_bytes(), 'text/javascript' if f.suffix == '.js' else 'text/css') if f.is_file() else self.send(404, {})
        if p == '/api/v1/auth/session': return self.send(200, {'csrf_token': 't'})
        if p.startswith('/api/terminal/v1/reference/'): return self.send(200, {'url': f'http://127.0.0.1:{PORT}/mock/ref/' + p.rsplit('/', 1)[1]})
        if p.startswith('/mock/ref/'): return self.send(200, ref(p.rsplit('/', 1)[1]))
        if p.startswith('/mock/price/'): return self.send(200, price_doc(p.rsplit('/', 1)[1]))
        if p.startswith('/mock/broker/'):
            _, _, _, t, y = p.split('/'); return self.send(200, broker_doc(t, y))
        return self.send(404, {'error': 'NOT_FOUND'})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('content-length') or 0)) or b'{}')
        if self.path.startswith('/api/terminal/v1/bundle'):
            t = body['ticker']; base = f'http://127.0.0.1:{PORT}/mock'
            years = sorted({d[:4] for d in DAYS})
            out = {'datasets': {
                'price': {'files': [{'url': f'{base}/price/{t}', 'pack': 'all'}], 'data_through': DAYS[-1]},
                'broker': {'files': [] if t == 'IHSG' else [{'url': f'{base}/broker/{t}/{y}', 'year': y} for y in years], 'data_through': None if t == 'IHSG' else BROKER_THROUGH},
                'events': {'files': []}}}
            return self.send(200, {'ticker': t, 'datasets': {k: v for k, v in out['datasets'].items() if k in body['datasets']}})
        return self.send(404, {})


ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
