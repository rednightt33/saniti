# Backtest flow data check (2026-10-26, ~18:15 UTC)

Question: may the backtest's flow conditions (foreign net, broker net, top-5) be enabled? Rule from the user's prompt:
only when the storage dataset and its units are verified. Script: `flow_data_check.py` (same folder); raw output:
`flow_data_check.json`. Read-only: terminal-api `/bundle` with `packs: true` and the gateway key (the same path and
identity the backtest worker uses), pgweb read-only role for SQL.

## Verdict: files equal SQL for every ticker-year checked; units are IDR

- Tickers: BBCA, MAPI, GOTO, BREN, ANTM, TLKM + 6 random stocks (seed 20261026): BINA, WGSH, DGIK, SEMA, BMSR, ZATA;
  every published year of each (2016-2026 where the ticker has data), 1,162,017 broker rows from the broker archive
  pack plus the two yearly files.
- Every file's sha256 and byte size equal the `/bundle` answer. Rows sorted by (date, broker, investor, board) with no
  duplicate key. Investor values only `Domestic`/`Foreign`, boards only `Regular`/`Nego`/`Tunai`.
- Per ticker-year, file vs `Feature_05_Foreign_Domestic_Broker_Detail` (up to the file's `data_through`): row count
  equal; sums of buy value, sell value, buy lots, sell lots and foreign net (buy − sell where investor = Foreign) equal
  within `sum(|x|) × 2^-53` (file values are float8 copies of the SQL values; SQL summed as numeric, the file side with
  `math.fsum`, so only the float8 rounding of each term can differ). 0 mismatches.
- Units: per trading day, Σ buy value of all rows ÷ (close × volume) has median 1.00–1.11 (p05 0.93–0.99) per ticker,
  and Σ buy lots × 100 ÷ volume has median 1.00–1.11: `bv`/`sv` are rupiah, `bl`/`sl` lots of 100 shares. The p95 above
  1 (up to ~10 on GOTO) comes from days with large negotiated trades, which are in the broker data and not in the
  regular-market volume of the price file.
- Freshness: broker `data_through` 2026-10-23 = SQL `max(trade_date)`; price `data_through` 2026-10-26. The broker data
  can end before the price data, so a flow run whose period ends after the broker `data_through` must be refused
  explicitly (the worker checks it).
- Coverage notes: broker rows start in 2016 for older tickers while prices start in 2018 (≈476 broker days without a
  price bar, outside any backtest bar); 2 days without prices for every stock (17–18 Sep 2026, ERRORS M238); price days
  without any broker row: 0 for 10 tickers, 3 for DGIK, 1 for BMSR.
- Download through the gateway from this sandbox: 4.3–7.3 s per ticker for price + broker packs (observation).
