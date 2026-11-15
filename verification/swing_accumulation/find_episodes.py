"""Step 1 of the point-behaviour study (user 2026-11-15): find episodes (point 1 -> point 2 -> point 3) on the most liquid stocks. Read-only, PRICE table only (no broker data).
Usage: python3 find_episodes.py [episodes_wanted=30] [per_stock=2] [top_k=40]
Rules (stated before the data is read):
  Universe  IDX_Stock_Universe: Security Type 'stock', Is Common Stock 'Yes', last close >= 50; ranked by ADV60 = mean(close x volume) of the last 60 daily candles (final candles only), needs >= 55 candles in the last ~80 days.
  Points    V3 (swing_lib.py): price ZigZag theta = 5 x median daily range (high-low)/close rounded to 5%, clipped 15..50%, confirmed only on a later candle; kept only if Stochastic 14,3,3 slow is <= 30 (low) / >= 70 (high)
            within +-5 candles; consecutive same-kind points merged to the more extreme. Window = 2024-01-02 .. last final candle (so MA50 is defined from March 2024).
  Episode   H(k) -> L(k+1) -> H(k+2) with point 3 CONFIRMED (not provisional) and, at point 1, the swing-high price > SMA50 of closes that day and, at point 2, the swing-low price < SMA50 of closes that day (user: 'MA50 utama, MA20 pembanding').
            Sensitivity columns: the same with SMA20, with EMA50, and with the close instead of the swing price.
  Choice    Walk down the liquidity ranking; a stock with >= 2 episodes contributes its EARLIEST and its LATEST (neutral rule, spreads regimes; no selection on depth or outcome), a stock with 1 contributes 1,
            stop when the wanted number is reached. Point prices are the pivot high/low; dates are trading days. Hindsight: V3 points are known only afterwards."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'terminal_api')); import pgq
sys.path.insert(0, str(Path(__file__).resolve().parent)); from swing_lib import stochastic, zigzag, combine
WANT = int(sys.argv[1]) if len(sys.argv) > 1 else 30; PER = int(sys.argv[2]) if len(sys.argv) > 2 else 2; TOPK = int(sys.argv[3]) if len(sys.argv) > 3 else 40
SINCE_LIQ = '2026-07-15'; SINCE = '2024-01-02'; WIN = 5
u = pgq.q('select "Ticker" t, "Company Name" nm, "Security Type" st, "Is Common Stock" cs, "Sector" sec from public."IDX_Stock_Universe"'); U = pd.DataFrame(u['rows'], columns=u['columns']); U = U[(U.st == 'stock') & (U.cs == 'Yes')]
q = pgq.q(f"""SELECT ticker t, date::text d, close c, volume v FROM public."Price_Stock_Indonesia_IDX" WHERE timeframe='Daily' AND is_final AND date >= date '{SINCE_LIQ}' ORDER BY ticker, date""")
if 'error' in q: sys.exit('query refused: ' + q['error'])
Q = pd.DataFrame(q['rows'], columns=q['columns']); Q['c'] = pd.to_numeric(Q.c); Q['v'] = pd.to_numeric(Q.v); latest = Q.d.max(); rows = []
for t, g in Q[Q.t.isin(set(U.t))].groupby('t'):
    if len(g) < 55 or g.d.max() < latest or g.c.iloc[-1] < 50: continue
    rows.append((t, float((g.c * g.v).tail(60).mean()), float(g.c.iloc[-1])))
R = pd.DataFrame(rows, columns=['t', 'adv60', 'close']).merge(U[['t', 'nm', 'sec']], on='t').sort_values('adv60', ascending=False).reset_index(drop=True); R['rank'] = R.index + 1
print(f'data terakhir {latest} | saham yang memenuhi syarat likuiditas: {len(R)} | {TOPK} teratas menurut ADV60 (Rp miliar): ' + ', '.join(f'{r.t} {r.adv60 / 1e9:.0f}' for r in R.head(TOPK).itertuples()))


def sma(x, n): return pd.Series(x).rolling(n).mean().values
def ema(x, n): return pd.Series(x).ewm(span=n, adjust=False, min_periods=n).mean().values


allrows = []; per_stock = []
for r in R.head(TOPK).itertuples():
    p = pgq.q(f"""SELECT date::text d, open o, high h, low l, close c, volume v FROM public."Price_Stock_Indonesia_IDX" WHERE ticker='{r.t}' AND timeframe='Daily' AND is_final AND date >= date '{SINCE}' ORDER BY date""")
    P = pd.DataFrame(p['rows'], columns=p['columns'])
    for c in 'ohlcv': P[c] = pd.to_numeric(P[c])
    h, l, c = P.h.values, P.l.values, P.c.values; n = len(P); dates = P.d.tolist(); th = float(np.clip(round(5 * np.median((h - l) / c) / 0.05) * 0.05, 0.15, 0.50))
    K, _ = stochastic(h, l, c); v3, _ = combine(zigzag(h, l, th), K, WIN); m50, m20, e50 = sma(c, 50), sma(c, 20), ema(c, 50); eps = []
    for k in range(len(v3) - 2):
        (i1, t1, p1, _), (i2, t2, p2, _), (i3, t3, p3, ci3) = v3[k], v3[k + 1], v3[k + 2]
        if not (t1 == 'H' and t2 == 'L' and t3 == 'H') or ci3 is None or np.isnan(m50[i1]) or np.isnan(m50[i2]): continue
        ok50 = p1 > m50[i1] and p2 < m50[i2]
        eps.append(dict(tk=r.t, rank=r.rank, adv60=r.adv60 / 1e9, th=th, n_candles=n, d1=dates[i1], p1=p1, d2=dates[i2], p2=p2, d3=dates[i3], p3=p3, drop=100 * (p2 / p1 - 1), rally=100 * (p3 / p2 - 1), days12=i2 - i1, days23=i3 - i2,
                        sma50_1=m50[i1], sma50_2=m50[i2], ok_sma50=ok50, ok_sma20=bool(p1 > m20[i1] and p2 < m20[i2]), ok_ema50=bool(p1 > e50[i1] and p2 < e50[i2]) if not np.isnan(e50[i1]) else False, ok_sma50_close=bool(c[i1] > m50[i1] and c[i2] < m50[i2]), conf3=dates[ci3]))
    good = [e for e in eps if e['ok_sma50']]; per_stock.append((r.t, r.rank, len(v3), len(eps), len(good)))
    allrows += [dict(e, available=len(good), chosen=False) for e in good]
S = pd.DataFrame(per_stock, columns=['ticker', 'peringkat', 'titik V3', 'episode H-L-H terkonfirmasi', 'lolos MA50'])
print('\nPer saham (peringkat likuiditas): titik V3, episode H→L→H, episode yang lolos syarat MA50 (① di atas, ② di bawah)\n' + S.to_string(index=False))
E = pd.DataFrame(allrows); chosen = []
for tk in [r.t for r in R.head(TOPK).itertuples()]:
    g = E[E.tk == tk].sort_values('d1') if len(E) else E
    if not len(g): continue
    pick = [g.index[0]] if len(g) == 1 or PER == 1 else [g.index[0], g.index[-1]]
    for ix in pick:
        if len(chosen) < WANT: chosen.append(ix)
E.loc[chosen, 'chosen'] = True; C = E.loc[chosen].reset_index(drop=True)
pd.set_option('display.width', 280); pd.set_option('display.max_columns', 40)
print(f'\n== {len(C)} episode terpilih dari {C.tk.nunique()} saham ({int((C.groupby("tk").size() == 2).sum())} saham dengan 2 episode, {int((C.groupby("tk").size() == 1).sum())} dengan 1)\n')
print(C[['tk', 'rank', 'adv60', 'th', 'd1', 'p1', 'd2', 'p2', 'd3', 'p3', 'drop', 'rally', 'days12', 'days23']].round(1).to_string(index=False))
print('\nSensitivitas pada episode terpilih: lolos juga dengan SMA20 %d, EMA50 %d, SMA50 dengan close (bukan harga pivot) %d dari %d' % (C.ok_sma20.sum(), C.ok_ema50.sum(), C.ok_sma50_close.sum(), len(C)))
tot_eps = int(S['episode H-L-H terkonfirmasi'].sum()); tot_ok = int(S['lolos MA50'].sum()); print(f'Semua {TOPK} saham teratas: {tot_eps} episode H→L→H terkonfirmasi, {tot_ok} lolos syarat MA50 ({100 * tot_ok / max(tot_eps, 1):.0f}%)')
out = Path('/tmp/claude-0/-home-user-saniti/661feb26-8ff9-5ae6-92ba-c2f161c079d5/scratchpad/episodes_step1.csv'); C.to_csv(out, index=False); E.to_csv(out.with_name('episodes_step1_all_candidates.csv'), index=False); print('csv:', out)
