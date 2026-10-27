# Terminal display bucket integrity audit

Run: 2026-10-25 (UTC), after backfill deployment `d8270f21-92ef-4d60-9412-806212d853a1` logged
`event="done" mode="backfill" files_planned=10134 files_written=9173 tickers=845 seconds=8150.4` at 08:42:38Z.
Read-only: nothing was written to the bucket, the database, Railway or git. Script: `integrity_check.py` (same folder).

## Verdict: ALL MATCH (0 mismatches)

## Totals
- Universe (`IDX_Stock_Universe`, stock + index): 845 tickers (844 stock, 1 index IHSG); 845 manifests; `ref/tickers.json.gz` has 845 rows.
- Files: 9,173 (4,588 price + 4,585 broker). The 10,134 planned minus 9,173 written equals the 961 ticker-years with no rows, which correctly have no file.
- Rows in files, all equal to SQL aggregates: 998,129 price rows, 27,087,188 broker rows.
- Bucket listing: 10,021 keys under `v1/` = 9,173 data files + 845 manifests + 2 ref files + state.json; no unreferenced and no missing keys.
- Row-level comparison (check 4): 90 ticker-years (45 price, 45 broker), 329,665 rows, every column compared exactly. 0 differences.
- Timings: SQL aggregates 762 s; download + integrity of all files 248 s; row-level sample 251 s.

## Checks
1. Coverage (derived from SQL, years 2021-2026): every ticker-year with final Daily price rows has a price file and vice versa; every stock ticker-year with Feature 05 rows has a broker file and vice versa; IHSG has no broker file. Missing: 0. Extra: 0. Manifests missing or outside the universe: 0.
2. Object integrity: every file listed in every manifest was downloaded; sha256, byte size, header (ticker/dataset/year), row count, first and last date all equal the manifest. 0 failures. One transient download error occurred (BCIC broker 2025, "Connection broken" while streaming); a retry downloaded it and it passed all checks and the SQL comparison. Retries were then added to the script.
3. Aggregates vs SQL for every file, tolerance 1e-9 relative (1e-6 absolute at 0):
   - price: count, min/max date, sums of open/high/low/close/volume, count of NULL volume.
   - broker: count, min/max date, sum buy_value/sell_value/buy_lots/sell_lots, distinct broker count, counts per investor_type and per market_board, and the gap list.
   - 0 mismatches. Note on IHSG: its volume is NULL on every row, so SQL `sum(volume)` is NULL while the file-side sum is 0; the NULL counts equal the row counts, so this is not treated as a mismatch.
4. Row-level sample (sorted by date, broker, investor_type, market_board; floats compared as exact float8 values): 45 price and 45 broker ticker-years. Included BBCA, GOTO, BREN, ANTM, MAPI, IHSG (price only), six lowest-volume stocks by broker rows, 2021 and 2026 for the named tickers, plus random ticker-years (seed 20261025).
   Price sample: ABDA 2021/2026, ANTM 2021/2026, ASLI 2025, BAYU 2026, BBCA 2021/2026, BBMD 2023, BIPI 2022, BREN 2025/2026, BSWD 2025/2026, BWPT 2023, BYAN 2021, DATA 2024, DOID 2023, EMMI 2026, GOTO 2023/2026, HRUM 2023, IHSG 2021/2026, JECX 2026, JELI 2026, KBLV 2024, KOBX 2026, KUAS 2023, LINK 2025, MAIN 2021/2024, MAPI 2021/2026, NFCX 2024, OKAS 2025, PGLI 2024, PJAA 2025, TOBA 2023, TOSK 2025, UNIQ 2022, XCIS 2023, XSPI 2021/2026, YULE 2026.
   Broker sample: ABDA 2021/2023/2026, AMAR 2021, ANTM 2021/2022/2026, ARGO 2021, ASLC 2023, ASRM 2024, BABP 2023, BBCA 2021/2024/2026, BBMD 2022, BPFI 2023, BREN 2024/2026, BSWD 2026, CITA 2023, EMMI 2026, GOTO 2025/2026, HAIS 2024, HMSP 2023, HRME 2021, IPTV 2025, JECX 2026, JELI 2026, JSPT 2024, MAPI 2021/2026, MBTO 2024, MCAS 2026, NASA 2024, PBID 2022, PSKT 2024, SFAN 2024, SINI 2022, SMAR 2021, SMGR 2025, SUPA 2026, WGSH 2021, XSPI 2021/2026.
   Gap rows: SQL has zero `source_balance_gap = true` rows for 2021-2026, so no gap ticker-years exist to add to the sample; every file's `gap` list is empty and matches SQL (this is a limitation: the gap path was not exercised with real data).
5. Ordering and types: dates ascending in every file; broker rows sorted by (date, broker, investor, board) with no duplicate keys; investor values only Foreign/Domestic and boards only Regular/Nego/Tunai in all files and in SQL; fractional lots present in 2,365 broker files and SQL agrees (2,365 ticker-years with fractional lots, same set by per-file presence test).
6. Freshness: `state.json` price_through = 2026-10-23 and broker_through = 2026-08-31, last_mode = backfill; equal to SQL max(date) of final Daily prices and max(trade_date) of Feature 05. Every manifest's `data_through` (845 price, 844 broker) equals the same values. 0 differences.

## Caveats
- The SQL aggregates were taken from 06:38 to 06:52Z, before the backfill finished; the freshness maxima were taken at the start of that run and still equal the manifests. No concurrent file or manifest change was observed (only one retry, for the transient BCIC download error).
- pgweb cache `~/.pgweb_auth` was deleted at the end.

## Parent-agent note (2026-10-25)

Cross-check of "zero source_balance_gap rows in 2021-2026": Feature 06 has 4 such rows since 2021
(UNVRBQCG6A 2025-11-07, AMRTDRCZ5A 2025-11-14, BRMSYUCN6A 2026-03-26, MAPADRCU6A 2026-07-27, all Regular). All four
are warrant symbols, which the publisher does not publish (stock and index tickers only), so the statement holds for
every published file. The gap path itself remains exercised only by the unit test (`tests/test_publisher.py`) and by
history requests before 2021.

## Since EXEC-SCREENER (2026-10-28): state.json and the bucket listing

The audit above predates packs, logos and the cross-sectional files. A later audit of the bucket counts, besides the
data files, manifests, packs, reference files, logos and `state.json`:
- **`state.json` `xsection`** = `{name: {key, sha256, bytes, rows, as_of}}`, the index of the run's cross-sectional
  files (Phase 1: `price` and `actions`), written by `apps/terminal-publisher/publisher.py` after the files it names.
  `key` is `v1/xsection/<name>.<first 16 hex of sha256>.json.gz`; `as_of` is the newest date of the `price` file and the
  newest `ingestion_time` of `idx_event_annotation` for `actions`. A mode that does not rebuild a file (`logos`,
  `broker-range`; `events` for `price`) carries its entry forward unchanged.
- **Keys under `v1/xsection/`**: the objects the current index names, plus those an earlier index named until the
  first daily run an hour or more after the run that replaced them: the publisher's `collect_garbage` (ERRORS M250, the
  same cleanup as for data files and packs) deletes a key of that form that the `state.json` index does not name, never
  another key, and nothing newer than `state.json` (an orphan of a crashed run stays until a later run finishes).
  `integrity_check.py` counts the indexed keys as referenced. Each object's bytes and sha256 equal its index entry.
- **Content checks**: the publisher's `verify` mode checks each indexed xsection file: bytes and sha256; each ticker's
  slice of `price` encodes to the ticker's published price pack (manifest `packs.price.sha256`) and has the rows,
  first and last date and sum of closes of SQL, and every published ticker with final daily rows is in it; the
  `actions` rows equal what the publisher's statement returns now.
