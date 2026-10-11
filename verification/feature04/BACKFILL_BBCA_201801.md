# Feature04 bounded backfill: BBCA January 2018

Executed 2026-10-11, lucid-patience / dev / primary Postgres.
User requested one ticker, one month, starting from the oldest available source data.
Authorization words are retained in `DATABASE_CHANGELOG.md`.

- Target: `public."Feature04_Technical_Indicator"`, existing 42-column schema.
- Output range: 2018-01-01 through 2018-01-31, BBCA only, Daily.
- Source: existing `public."Price_Stock_Indonesia_IDX"`, earliest BBCA date 2018-01-02.
- Dry-run read 22 observations and produced 22 output rows, calculated chronologically.
- First write committed 22 rows, actual coverage 2018-01-02 through 2018-01-31.
- All feature, identity and version columns matched recalculation. The separate calculated_at
  metadata was verified for preservation on rerun; it is not compared with a new calculation time.
- Identical rerun changed 0 rows and preserved every stored value and timestamp.
- Independent pgweb readback confirmed 22 records, 22 distinct keys, and no outside-scope rows.
- Before/after fingerprints matched for all 2,113 BBCA source rows and all unrelated target rows.
- Ephemeral private execution sandbox was destroyed; terminal DESTROYED observed.

| Indicator group | Available rows | First available date |
|---|---:|---|
| EMA12 | 11 | 2018-01-17 |
| RSI14, ATR14 | 8 each | 2018-01-22 |
| SMA20, Bollinger upper/middle/lower | 3 each | 2018-01-29 |
| SMA50, EMA26, MACD line/signal/histogram | 0 | Not enough initial observations |

Warmup NULLs are retained. No earlier synthetic history, forward filling, later-price seed,
additional ticker/month, full backfill, training, schedule or service deployment was used.
TradingView numerical parity and point-in-time training eligibility remain NOT VERIFIED.

Aggregate execution manifests, fingerprints and per-column availability:
`backfill_bbca_201801.json`. This evidence contains no row-by-row price/feature mirror or credentials.
