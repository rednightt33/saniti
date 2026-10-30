"""EXEC-PUBLISHER-SPEED latency rehearsal: the publisher's daily run on a synthetic 845-ticker universe (8 price years,
2 broker years each; every ticker's 2026 price year changed, as on 2026-10-29) against an in-memory bucket where every
request (put, get, listing page, delete batch) waits LATENCY seconds, the latency measured from a US host to the bucket
on 2026-10-29 (0.54 s). Database statements are in memory (no wait); on dev they add about 6 ms per year file and 27 ms
per pack, in order on one connection. delete_replaced's wait is recorded, not slept. Usage: latency_rehearsal.py
THREADS LATENCY [SWEEP] (SWEEP 1: the 19:00 WIB run, with the full cleanup; 0, the default: the 07:30 WIB run)"""
import datetime as dt, json, sys, time, threading
ROOT = __import__('pathlib').Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'apps/terminal-publisher')); sys.path.insert(0, str(ROOT / 'apps/terminal-publisher/tests'))
import publisher as pub
from test_publisher import FakeBucket, FakeConn, fake_get
pub.fetch = fake_get(stockbit=())                    # no network: the logo sources answer 'offline'

THREADS, LATENCY = int(sys.argv[1]), float(sys.argv[2])
SWEEP = len(sys.argv) > 3 and sys.argv[3] == '1'
WAITED = []
pub.wait = WAITED.append                             # the wait after state.json is not slept
N = 845
class LatencyBucket(FakeBucket):
    def __init__(self):
        super().__init__(); self.calls = {'put': 0, 'get': 0, 'list': 0, 'delete': 0}; self.lock = threading.Lock()
    def _wait(self, kind):
        with self.lock: self.calls[kind] += 1
        time.sleep(LATENCY)
    def put(self, key, body, ctype):
        self._wait('put'); super().put(key, body, ctype)
    def get_json(self, key):
        self._wait('get'); return super().get_json(key)
    def get_raw(self, key):
        self._wait('get'); return super().get_raw(key)
    def list(self, deadline=None, prefix=''):
        keys = [k for k in self.objects if k.startswith(prefix)]
        for _ in range(max(1, -(-len(keys) // pub.LIST_PAGE_KEYS))): self._wait('list')
        return super().list(deadline, prefix)
    def delete(self, keys):
        for _ in range(max(1, -(-len(keys) // 1000))): self._wait('delete')
        return super().delete(keys)

tickers = [f'T{i:03d}' for i in range(N)]
days = ['2019-06-03', '2020-06-01', '2021-06-01', '2022-06-01', '2023-06-01', '2024-06-03', '2025-06-02', '2026-06-01']
prices = [(t, d, 10.0, 11.0, 9.0, 10.0 + i % 7, 100.0) for i, t in enumerate(tickers) for d in days]
brokers = [(t, d, 'AK', 'Foreign', 'Regular', 5.0, 0.0, 0.05, 0.0, False) for t in tickers for d in ('2025-06-02', '2026-06-01')]
universe = [(t, f'Company {t}', 'stock', 'Finance', 'Banks') for t in tickers]
conn = FakeConn(prices, brokers, universe, events=[], actions=[])
bucket = LatencyBucket()
today = dt.date(2026, 10, 29)
# the starting bucket: a backfill without latency (not timed), finished two hours before the timed daily run
saved = LATENCY; LATENCY = 0
pub.Publisher(conn, bucket, today=today, threads=16, clock=lambda: bucket.clock).run('backfill')
pub.Publisher(conn, bucket, today=today, threads=16, clock=lambda: bucket.clock).run('logos')   # a fresh logo index, as on dev
LATENCY = saved
bucket.calls = {k: 0 for k in bucket.calls}
bucket.clock += dt.timedelta(hours=2)
conn.prices = prices + [(t, '2026-10-29', 10.0, 11.0, 9.0, 10.5, 100.0) for t in tickers[:828]]
t0 = time.monotonic()
p = pub.Publisher(conn, bucket, today=today, threads=THREADS, clock=lambda: bucket.clock)
p.run('daily', sweep=SWEEP)
print(json.dumps({'threads': THREADS, 'latency': LATENCY, 'sweep': SWEEP, 'seconds': round(time.monotonic() - t0, 1),
                  'to_state_json': round(sum(p.phases.values()), 1), 'written': p.written, 'phases': p.phases,
                  'replaced': len(p.replaced), 'waited': WAITED, 'requests': bucket.calls}))
