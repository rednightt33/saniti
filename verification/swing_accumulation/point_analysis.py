"""Point-behaviour analysis exactly as POINT_BEHAVIOUR_PLAN.md (committed before the data was pulled). Usage: EP_DIR=<dir> python3 point_analysis.py
Needs <dir>/<ticker>_price.pkl and <dir>/<ticker>_series.json (point_series.ts) for every stock in episodes_step1.csv. Writes <dir>/point_results.csv, point_candidates.csv and prints the report.
Tests per episode and series x: A1 = x(2)-x(1), A2 = x(3)-x(2), B1/B2 = Spearman(x, close) over segment 1/2 (>= 10 candles), C = lag k* in [-10,10] maximising |rank corr| of daily changes of x(t) with daily changes of close(t+k)
around point 2 (+-20 candles; k*>0: the indicator leads). Each is turned into a percentile among placebo windows of the same stock (plan section 3), then aggregated (section 4) and calibrated against random pseudo-episodes (section 5)."""
import os, sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent)); from swing_lib import stochastic, zigzag, combine
D = os.environ.get('EP_DIR', '.'); HERE = Path(__file__).resolve().parent; rng = np.random.default_rng(2026)
EP = pd.read_csv(HERE / 'episodes_step1.csv'); TESTS = ['A1', 'A2', 'B1', 'B2', 'C']; MINP = 15; LAGS = list(range(-10, 11)); HALF = 20; REPS = 300

# ---------------- data per stock
data = {}
for tk in sorted(EP.tk.unique()):
    P = pd.read_pickle(os.path.join(D, f'{tk.lower()}_price.pkl')).reset_index(drop=True); S = json.load(open(os.path.join(D, f'{tk.lower()}_series.json')))
    names = sorted(S['series']); X = np.array([[np.nan if v is None else v for v in S['series'][nm]] for nm in names], float)
    h, l, c = P.h.values.astype(float), P.l.values.astype(float), P.c.values.astype(float); di = {d: i for i, d in enumerate(P.d)}
    th = float(EP[EP.tk == tk].th.iloc[0]); o = di.get('2024-01-02', int(np.argmax(np.array(P.d) >= '2024-01-02')))
    Kst, _ = stochastic(h[o:], l[o:], c[o:]); v3, _ = combine(zigzag(h[o:], l[o:], th), Kst, 5); piv = [o + p[0] for p in v3]
    minor = [t for t in range(5, len(P) - 5) if l[t] == l[t - 5:t + 6].min() and all(abs(t - p) > 10 for p in piv) and t >= di.get('2024-03-01', o + 40)]
    data[tk] = dict(P=P, names=names, X=X, h=h, l=l, c=c, di=di, th=th, minor=minor, N=len(P), errors=S['errors'])
names = sorted(n for n in set.intersection(*[set(d['names']) for d in data.values()]) if not n.startswith('F:FL31.'))   # plan section 2: FL31 (insider data, empty here) excluded; FL23 (inventory of named brokers) drops out because its series names differ per stock
for tk, d in data.items():
    idx = [d['names'].index(n) for n in names]; d['X'] = d['X'][idx]; d['names'] = names
print(f'{len(EP)} episode, {EP.tk.nunique()} saham, {len(names)} deret (teknikal {sum(n.startswith("T:") for n in names)}, Flow {sum(n.startswith("F:") for n in names)}); galat indikator:', {tk: d['errors'] for tk, d in data.items() if d['errors']} or 'tidak ada')
EP['d2'] = pd.to_datetime(EP.d2); EP = EP.sort_values('d2').reset_index(drop=True); cl = [0]
for i in range(1, len(EP)): cl.append(cl[-1] if (EP.d2[i] - EP.d2[i - 1]).days <= 21 else cl[-1] + 1)
EP['cluster'] = cl; EP['late'] = EP.d2.dt.year >= 2026


# ---------------- window statistics (vectorised over series)
def ranks(M):
    return pd.DataFrame(M.T).rank(axis=0, method='average').values.T


def spearman(X, s, e):
    """rank correlation of each series with the close over candles s..e; NaN if >10% missing or constant"""
    W = X[:, s:e + 1]; cl = CLOSE[s:e + 1]; ok = ~np.isnan(W).any(axis=1); out = np.full(W.shape[0], np.nan)
    if ok.sum() == 0: return out
    rw = ranks(W[ok]); rc = pd.Series(cl).rank().values; rw = rw - rw.mean(1, keepdims=True); rc = rc - rc.mean(); den = np.sqrt((rw ** 2).sum(1) * (rc ** 2).sum())
    with np.errstate(invalid='ignore', divide='ignore'): out[ok] = (rw * rc).sum(1) / den
    return out


def lead(X, centre):
    """k* of the cross-correlation of daily changes of x(t) with daily changes of close(t+k) over centre-20..centre+20"""
    s, e = centre - HALF, centre + HALF
    if s < 1 or e >= X.shape[1]: return np.full(X.shape[0], np.nan)
    W = X[:, s - 1:e + 1]; ok = ~np.isnan(W).any(axis=1); out = np.full(X.shape[0], np.nan)
    if ok.sum() == 0: return out
    dx = np.diff(W[ok], axis=1); dp = np.diff(CLOSE[s - 1:e + 1]); rx = ranks(dx); rp = pd.Series(dp).rank().values; n = len(dp); best = np.full(ok.sum(), -1.0); kk = np.zeros(ok.sum())
    for k in LAGS:
        a, b = (0, n - k) if k >= 0 else (-k, n)                                    # pairs (x at t, close change at t+k)
        xa = rx[:, a:b]; pa = rp[a + k:b + k]
        if xa.shape[1] < 10: continue
        xa = xa - xa.mean(1, keepdims=True); pa = pa - pa.mean(); den = np.sqrt((xa ** 2).sum(1) * (pa ** 2).sum())
        with np.errstate(invalid='ignore', divide='ignore'): cr = np.abs((xa * pa).sum(1) / den)
        cr = np.nan_to_num(cr, nan=-1.0); upd = cr > best; best[upd] = cr[upd]; kk[upd] = k
    res = kk.copy(); res[best < 0] = np.nan; out[ok] = res; return out


def pct_of(obs, plc):
    """mid-rank percentile of obs (S,) among plc (W,S); NaN unless >= MINP valid placebo values"""
    n = (~np.isnan(plc)).sum(0); lt = np.nansum(plc < obs[None, :], axis=0); eq = np.nansum(plc == obs[None, :], axis=0)
    with np.errstate(invalid='ignore', divide='ignore'): p = 100 * (lt + 0.5 * eq) / n
    p[(n < MINP) | np.isnan(obs)] = np.nan; return p


# ---------------- per episode: observed + placebo
obs = {T: [] for T in TESTS}; pct = {T: [] for T in TESTS}; plc_all = {T: [] for T in TESTS}; nplc = {T: [] for T in TESTS}
for e in EP.itertuples():
    d = data[e.tk]; X = d['X']; CLOSE = d['c']; i1, i2, i3 = d['di'][e.d1], d['di'][e.d2], d['di'][e.d3]; m1, m2 = i2 - i1, i3 - i2; th = d['th']
    ok = [t for t in d['minor'] if not (i1 - 5 <= t <= i3 + 5)]                       # placebo anchors away from this episode
    o_A1 = X[:, i2] - X[:, i1]; o_A2 = X[:, i3] - X[:, i2]; o_B1 = spearman(X, i1, i2); o_B2 = spearman(X, i2, i3) if m2 + 1 >= 10 else np.full(len(names), np.nan); o_C = lead(X, i2)
    for T, o in (('A1', o_A1), ('A2', o_A2), ('B1', o_B1), ('B2', o_B2), ('C', o_C)): obs[T].append(o)
    pl = {T: [] for T in TESTS}
    for t in ok:
        if t - m1 >= 0 and d['c'][t] / d['c'][t - m1] - 1 <= -th / 3 and not (t - m1 <= i3 and t >= i1):
            pl['A1'].append(X[:, t] - X[:, t - m1])
            if m1 + 1 >= 10: pl['B1'].append(spearman(X, t - m1, t))
        if t + m2 < d['N'] and d['c'][t + m2] / d['c'][t] - 1 >= th / 3 and not (t <= i3 and t + m2 >= i1):
            pl['A2'].append(X[:, t + m2] - X[:, t])
            if m2 + 1 >= 10: pl['B2'].append(spearman(X, t, t + m2))
        pl['C'].append(lead(X, t))
    for T in TESTS:
        M = np.array(pl[T]) if pl[T] else np.empty((0, len(names))); plc_all[T].append(M); nplc[T].append(len(M)); pct[T].append(pct_of(obs[T][-1], M) if len(M) else np.full(len(names), np.nan))
print('jendela pembanding per episode (median [min; maks]):', {T: f'{int(np.median(nplc[T]))} [{min(nplc[T])}; {max(nplc[T])}]' for T in TESTS})


# ---------------- aggregation and criteria
def flags(PC):
    """PC: (episodes, series) percentiles -> boolean (series,) candidate flags and the medians"""
    med = np.nanmedian(PC, axis=0); nvalid = (~np.isnan(PC)).sum(0); side = np.sign(med - 50); good = (np.abs(med - 50) >= 20) & (nvalid >= 20)
    cm = np.array([np.nanmean(PC[EP.cluster.values == k], axis=0) for k in sorted(EP.cluster.unique())]); cvalid = ~np.isnan(cm)
    agree = np.array([(((np.sign(cm[:, j] - 50) == side[j]) & cvalid[:, j]).sum() / max(cvalid[:, j].sum(), 1)) for j in range(PC.shape[1])])
    lm = EP.late.values; early = np.nanmedian(PC[~lm], axis=0); late = np.nanmedian(PC[lm], axis=0)
    halves = (np.sign(early - 50) == side) & (np.sign(late - 50) == side) & (np.abs(early - 50) >= 10) & (np.abs(late - 50) >= 10)
    return good & (agree >= 0.75) & halves, med, nvalid, agree, early, late


res = {}; nflag = {}
with np.errstate(all='ignore'):
    for T in TESTS:
        PC = np.array(pct[T]); f, med, nv, ag, ea, la = flags(PC); res[T] = dict(flag=f, med=med, nvalid=nv, agree=ag, early=ea, late=la); nflag[T] = int(f.sum())
    # null calibration: leave-one-out percentiles of the placebo windows, one random window per episode
    loo = {T: [] for T in TESTS}
    for T in TESTS:
        for M in plc_all[T]:
            if len(M) >= MINP + 1:
                rk = ranks(M.T).T if False else pd.DataFrame(M).rank(axis=0, method='average').values; nn = (~np.isnan(M)).sum(0)
                L = 100 * (rk - 1) / np.maximum(nn - 1, 1)[None, :]; L[:, nn < MINP + 1] = np.nan; L[np.isnan(M)] = np.nan; loo[T].append(L)
            else: loo[T].append(None)
    null = {T: [] for T in TESTS}
    for _ in range(REPS):
        for T in TESTS:
            PC = np.array([L[rng.integers(0, len(L))] if L is not None else np.full(len(names), np.nan) for L in loo[T]]); null[T].append(int(flags(PC)[0].sum()))
print('\n== Kalibrasi nol (300 pseudo-episode acak): jumlah deret yang lolos kriteria per ukuran')
cal = pd.DataFrame({T: [nflag[T], np.mean(null[T]), np.percentile(null[T], 95), nflag[T] - np.mean(null[T])] for T in TESTS}, index=['nyata', 'rata-rata nol', 'P95 nol', 'selisih nyata − rata-rata nol']).round(1); print(cal.to_string())

# ---------------- tiers and output
rows = []
for j, nm in enumerate(names):
    r = dict(series=nm)
    for T in TESTS: r.update({f'{T}_med': res[T]['med'][j], f'{T}_n': res[T]['nvalid'][j], f'{T}_agree': res[T]['agree'][j], f'{T}_early': res[T]['early'][j], f'{T}_late': res[T]['late'][j], f'{T}_flag': bool(res[T]['flag'][j])})
    seg1 = sum(r[f'{T}_flag'] for T in ('A1', 'B1', 'C')); seg2 = sum(r[f'{T}_flag'] for T in ('A2', 'B2'))
    r['tier'] = 1 if seg1 >= 2 or seg2 >= 2 else (2 if any(r[f'{T}_flag'] for T in TESTS) else 0); rows.append(r)
R = pd.DataFrame(rows); R.to_csv(os.path.join(D, 'point_results.csv'), index=False); C = R[R.tier > 0].copy()
C['n_flags'] = C[[f'{T}_flag' for T in TESTS]].sum(1); C = C.sort_values(['tier', 'n_flags'], ascending=[True, False]); C.to_csv(os.path.join(D, 'point_candidates.csv'), index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200)
print(f'\n== Kandidat: Tingkat 1 = {int((C.tier == 1).sum())}, Tingkat 2 = {int((C.tier == 2).sum())} dari {len(R)} deret')
show = lambda df: df[['series'] + [f'{T}_med' for T in TESTS] + ['n_flags']].round(0)
print('\nTingkat 1 (lolos >= 2 ukuran pada segmen yang sama): median persentil per ukuran (50 = biasa)'); print(show(C[C.tier == 1]).to_string(index=False))
print('\nTingkat 2 (lolos 1 ukuran), 40 teratas menurut jarak dari 50:'); t2 = C[C.tier == 2].copy(); t2['dev'] = t2[[f'{T}_med' for T in TESTS]].sub(50).abs().max(axis=1); print(show(t2.sort_values('dev', ascending=False).head(40)).to_string(index=False))
