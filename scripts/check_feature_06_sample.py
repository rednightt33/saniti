#!/usr/bin/env python3
"""EXEC-F05-F06: recalculate every Feature 06 field for one ticker from Feature 05 in pandas, independently of the SQL
in refresh_feature_06, and compare it with the stored rows.

Usage:
  DATABASE_URL=... python scripts/check_feature_06_sample.py --ticker BBCA [--from 2026-01-01]
Prints one line per field with the number of compared rows, mismatches and the largest difference, then PASS or
FAIL. Floats match within a relative tolerance of 1e-6; NULL must match NULL.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import numpy as np
import pandas as pd

TOL = 1e-6


def expected(f05: pd.DataFrame) -> pd.DataFrame:
    """f05 columns: trade_date, market_board, investor_type, buy_value, sell_value, buy_lots, sell_lots, buy_freq,
    sell_freq, source_balance_gap (one ticker, full history)."""
    f05 = f05.copy()
    for c in ["buy_value", "sell_value", "buy_lots", "sell_lots", "buy_freq", "sell_freq"]:
        f05[c] = pd.to_numeric(f05[c]).astype(float)
    sessions = np.sort(f05.trade_date.unique())
    boards = sorted(f05.market_board.unique())
    has_freq = f05.buy_freq.notna().any()
    rows = []
    for board in boards:
        b = f05[f05.market_board == board]
        g = {}
        for it, p in (("Foreign", "f"), ("Domestic", "d")):
            x = b[b.investor_type == it].groupby("trade_date")
            g[p] = x.agg(buy=("buy_value", "sum"), sell=("sell_value", "sum"), bl=("buy_lots", "sum"),
                         sl=("sell_lots", "sum"),
                         bfreq=("buy_freq", lambda s: s.sum() if s.notna().any() else np.nan),
                         sfreq=("sell_freq", lambda s: s.sum() if s.notna().any() else np.nan))
        act = b.groupby("trade_date").agg(gap=("source_balance_gap", "any"),
                                          freq_rows=("buy_freq", lambda s: s.notna().sum()))
        d = pd.DataFrame(index=pd.Index(sessions, name="trade_date"))
        d["active"] = d.index.isin(act.index)
        d["gap"] = act.gap.reindex(d.index).fillna(False).astype(bool)
        freq_rows = act.freq_rows.reindex(d.index)
        for p in ("f", "d"):
            gg = g[p].reindex(d.index)
            for c in ("buy", "sell", "bl", "sl"):
                d[p + c] = gg[c].fillna(0.0)
            for c in ("bfreq", "sfreq"):
                v = gg[c]
                v = np.where(~d.active, 0.0 if has_freq else np.nan,
                             np.where(freq_rows > 0, v.fillna(0.0), v))
                d[p + c] = v
        d["s"] = np.arange(1, len(d) + 1)
        d["board"] = board
        rows.append(d)
    return pd.concat(rows), boards


def roll(series: pd.Series, n: int, s: pd.Series) -> pd.Series:
    out = series.rolling(n, min_periods=n).sum()
    return out.where(s >= n)


def midrank(cur: float, hist: np.ndarray) -> float:
    return 100.0 * ((hist < cur).sum() + 0.5 * (hist == cur).sum()) / len(hist)


def baseline(x: pd.Series, size: int):
    z, pc = [], []
    vals = x.to_numpy()
    for i in range(len(vals)):
        if i < size:
            z.append(np.nan); pc.append(np.nan); continue
        h = vals[i - size:i]
        if np.isnan(h).any() or np.isnan(vals[i]):
            z.append(np.nan); pc.append(np.nan); continue
        sd = h.std(ddof=1)
        z.append((vals[i] - h.mean()) / sd if sd > 0 else np.nan)
        pc.append(midrank(vals[i], h))
    return pd.Series(z, index=x.index), pd.Series(pc, index=x.index)


def div(a, b):
    a = pd.Series(a); b = pd.Series(b)
    return (a / b).where(b != 0)


def compute(f05: pd.DataFrame) -> pd.DataFrame:
    dense, boards = expected(f05)
    out = []
    for board in boards:
        d = dense[dense.board == board].copy()
        s = d.s
        FB, FS, DB, DS = d.fbuy, d.fsell, d.dbuy, d.dsell
        F, D, T = FB - FS, DB - DS, FB + DB
        BF, SF, DBF, DSF = d.fbfreq, d.fsfreq, d.dbfreq, d.dsfreq
        e = pd.DataFrame(index=d.index)
        e["active"], e["source_balance_gap"] = d.active, d.gap
        e["foreign_buy_1d"], e["foreign_sell_1d"], e["foreign_net_1d"] = FB, FS, F
        e["domestic_buy_1d"], e["domestic_sell_1d"], e["domestic_net_1d"] = DB, DS, D
        e["foreign_cumulative_net"], e["domestic_cumulative_net"] = F.cumsum(), D.cumsum()
        fN = {n: roll(F, n, s) for n in (5, 10, 20, 40, 60)}
        for n in (5, 10, 20, 40, 60):
            e[f"foreign_net_{n}d"] = fN[n]
        for n in (5, 10, 20, 60):
            e[f"domestic_net_{n}d"] = roll(D, n, s)
        e["foreign_net_turnover_ratio_1d"] = 100 * div(F, T)
        e["foreign_net_turnover_ratio_5d"] = 100 * div(fN[5], roll(T, 5, s))
        e["foreign_net_turnover_ratio_20d"] = 100 * div(fN[20], roll(T, 20, s))
        e["foreign_buy_share_1d"], e["foreign_sell_share_1d"] = 100 * div(FB, T), 100 * div(FS, T)
        for n in (5, 10, 20, 40):
            e[f"foreign_buy_days_{n}d"] = roll((F > 0).astype(float), n, s)
            e[f"foreign_sell_days_{n}d"] = roll((F < 0).astype(float), n, s)
        for n in (5, 10, 20, 40, 60):
            e[f"foreign_net_zscore_{n}d_base252d"], e[f"foreign_net_percentile_{n}d_base252d"] = baseline(fN[n], 252)
        for n in (5, 10, 20):
            e[f"foreign_net_zscore_{n}d_base60d"], e[f"foreign_net_percentile_{n}d_base60d"] = baseline(fN[n], 60)
        e["foreign_flow_vs_prev_20d"] = (fN[20] - F.shift(20).rolling(20, min_periods=20).sum()).where(s >= 40)
        e["foreign_flow_vs_prev_40d"] = (fN[40] - F.shift(40).rolling(40, min_periods=40).sum()).where(s >= 80)
        R = div(F, T).where(T > 0)
        def strength(n):
            num = R.rolling(n, min_periods=1).sum().where(s >= n)
            den = R.abs().rolling(n, min_periods=1).sum().where(s >= n)
            return (100 * num / den).where(den > 0)
        st20 = strength(20)
        e["foreign_strength_20d"], e["foreign_strength_50d"] = st20, strength(50)
        e["foreign_strength_momentum_5d"] = st20 - st20.shift(5)
        e["foreign_buy_freq_1d"], e["foreign_sell_freq_1d"] = BF, SF
        e["domestic_buy_freq_1d"], e["domestic_sell_freq_1d"] = DBF, DSF
        for p, B, S, VB, VS, LB, LS in (("foreign", BF, SF, FB, FS, d.fbl, d.fsl),
                                         ("domestic", DBF, DSF, DB, DS, d.dbl, d.dsl)):
            e[f"{p}_freq_imbalance_1d"] = 100 * div(B - S, B + S)
            e[f"{p}_freq_imbalance_20d"] = 100 * div(roll(B, 20, s) - roll(S, 20, s), roll(B, 20, s) + roll(S, 20, s))
            e[f"{p}_buy_freq_share_1d"] = 100 * div(B, BF + DBF)
            e[f"{p}_sell_freq_share_1d"] = 100 * div(S, SF + DSF)
            e[f"{p}_avg_buy_value_per_freq_1d"] = div(VB, B)
            e[f"{p}_avg_sell_value_per_freq_1d"] = div(VS, S)
            e[f"{p}_buy_sell_ticket_ratio_1d"] = div(div(VB, B), div(VS, S)).where((B > 0) & (S > 0) & (VS > 0))
            e[f"{p}_avg_buy_lots_per_freq_1d"] = div(LB, B)
            e[f"{p}_avg_sell_lots_per_freq_1d"] = div(LS, S)
        c5 = lambda v: v.rolling(5, min_periods=5).sum().where(s >= 25)
        p20 = lambda v: v.shift(5).rolling(20, min_periods=20).sum().where(s >= 25)
        for side, Fq, Dq, Fv, Dv in (("buy", BF, DBF, FB, DB), ("sell", SF, DSF, FS, DS)):
            cur_tot, prev_tot = c5(Fq) + c5(Dq), p20(Fq) + p20(Dq)
            e[f"domestic_{side}_freq_share_change_5d_vs_prev20d"] = 100 * div(c5(Dq), cur_tot) - 100 * div(p20(Dq), prev_tot)
            e[f"foreign_{side}_freq_share_change_5d_vs_prev20d"] = 100 * div(c5(Fq), cur_tot) - 100 * div(p20(Fq), prev_tot)
            e[f"domestic_{side}_value_per_freq_change_5d_vs_prev20d"] = 100 * (div(div(c5(Dv), c5(Dq)), div(p20(Dv), p20(Dq))) - 1)
            e[f"foreign_{side}_value_per_freq_change_5d_vs_prev20d"] = 100 * (div(div(c5(Fv), c5(Fq)), div(p20(Fv), p20(Fq))) - 1)
        nf = BF - SF
        e["foreign_value_freq_sign_mismatch_1d"] = np.where(BF.isna() | SF.isna() | (F == 0) | (nf == 0), np.nan,
                                                            (np.sign(F) != np.sign(nf)).astype(float))
        e["market_board"] = board
        out.append(e)
    res = pd.concat(out).reset_index()
    return res[res.active].drop(columns="active")


def compare(exp: pd.DataFrame, got: pd.DataFrame, since=None) -> bool:
    key = ["trade_date", "market_board"]
    exp = exp.copy(); got = got.copy()
    exp["trade_date"] = pd.to_datetime(exp.trade_date); got["trade_date"] = pd.to_datetime(got.trade_date)
    if since is not None:
        exp = exp[exp.trade_date >= pd.Timestamp(since)]
    m = exp.merge(got, on=key, how="outer", suffixes=("_e", "_g"), indicator=True)
    ok = True
    if (m._merge != "both").any():
        print(f"ROWS: expected-only {(m._merge == 'left_only').sum()}, stored-only {(m._merge == 'right_only').sum()}")
        ok = False
    m = m[m._merge == "both"]
    fields = [c for c in exp.columns if c not in key]
    for c in fields:
        e = pd.to_numeric(m[c + "_e"].astype(float), errors="coerce")
        g = pd.to_numeric(m[c + "_g"].astype(float), errors="coerce")
        both_null = e.isna() & g.isna()
        diff = (e - g).abs()
        rel = diff / np.maximum(e.abs(), 1.0)
        bad = ~both_null & ((e.isna() != g.isna()) | (rel > TOL))
        if bad.any():
            ok = False
            print(f"FAIL {c}: {bad.sum()} of {len(m)}; largest diff {diff[bad].max()}; "
                  f"first {m.loc[bad, key].iloc[0].tolist()} expected {e[bad].iloc[0]} stored {g[bad].iloc[0]}")
    print(f"compared {len(m)} rows x {len(fields)} fields: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> None:
    import psycopg
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--from", dest="since")
    a = ap.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        f05 = pd.read_sql("SELECT trade_date, market_board, investor_type, buy_value, sell_value, buy_lots, "
                          "sell_lots, buy_freq, sell_freq, source_balance_gap FROM "
                          "feature_05_foreign_domestic_broker_detail WHERE ticker = %s", c, params=(a.ticker,))
        got = pd.read_sql("SELECT * FROM feature_06_foreign_domestic WHERE ticker = %s", c, params=(a.ticker,))
    got = got.drop(columns=["ticker", "calculated_at"])
    sys.exit(0 if compare(compute(f05), got, a.since) else 1)


if __name__ == "__main__":
    main()
