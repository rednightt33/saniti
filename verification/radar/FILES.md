# Radar files: the contract between terminal-publisher and the Radar page (EXEC-RADAR R5-R7)

The publisher (`apps/terminal-publisher/radar.py`) writes gzip JSON files of the family `radar/`, content-keyed
(`v1/radar/<name>.<first 16 hex of sha256>.json.gz`) and indexed in `state.json` `radar` ({name: {key, sha256, bytes,
rows, as_of}}) with `radar_stamp`. terminal-api never shows that index on `/state`; `GET /api/terminal/v1/radar` lists it
and `POST /api/terminal/v1/radar {names}` presigns, both for the EDGE gateway key only (403 for a subscriber session and
every service key). edge-bff relays them to the owner's EDGE session: `GET /api/v1/radar/index` and
`GET /api/v1/radar/file/<name>?sha=<sha256>` (the bytes, `Content-Encoding: gzip`, checked against the sha; cached for
good when the URL names the current sha, 409 `RADAR_FILE_REPLACED` when it names an older one).

The publisher computes no indicator and the page evaluates no rule: hit, near, left, the met conditions, the run of days,
the sort value and the outlier note are rows of `Feature_07_Radar_Result` (migration `20261114_001`). Every list is
ordered by the publisher, so equal tables give equal bytes. Dates are `YYYY-MM-DD`; money is rupiah (IDR), not billions.

## When the files change

In the modes `daily` and `backfill` the files are rebuilt when `radar.stamp` changes (the newest gate row's
`calculated_at` and the gate row count: every `refresh_feature_07_day` rewrites its gate row; the newest final IHSG price
date; the rule version; the final closes from the newest result date on; the stock lists' membership), or when the
index in state.json is not whole (an unusable entry, an object missing from the bucket). Older price corrections are not
watched: the manual mode `radar` republishes after one. While the first fill runs (advisory lock
`feature_07_radar_backfill`) nothing is built. The manual mode `radar` rebuilds them whatever the stamp. Every other mode carries the index
forward. A failure keeps the previous index (logged `radar_failed` with the step and the error class only); the rest
of the publication goes on. The cleanup (`collect_garbage`, `delete_replaced`) treats `radar` like `xsection` and `ref`.

## The files

| Name | Holds | Size (rehearsal, 250 dates) |
|---|---|---|
| `radar-meta` | `filters` (id, position, column, column_label, variant, default_variant, name, question, warning, sort_label, own_levels), `rules` (filter, cond, level, label, threshold, threshold2, status), `names` (every universe ticker's company name), `lists` (key, kind INDEX/KONGLO, code, name, members: the current members of every stock list), `levels`, `gates` | 7 KB |
| `radar-days` | `dates` (the 250 newest result dates, oldest first), `gate` (universe_n, broad_cut, liquid_cut, broad_n, liquid_n per date), `counts` {filter: {"level/gate": hits per date}}, `ihsg` (close per date), `broker_through`, `prices_through`, `boards` (the dates with a board file) | 12 KB |
| `radar-board-YYYY-MM-DD` | one of the 20 newest result dates: `stocks` (ticker, close, chg_1d in percent, spark: up to 20 closes ending on the date), `rows` (filter, stock index, level, gate, status, met, cond_n, run_day, left_reason, strong, sort_value, flag), `measures` (columns and one value list per stock: the Feature 07 measures the page's own columns show) | 76 KB |
| `radar-f-<filter>` | one filter (lower-case id: s1, s2, s3, s6, s6d_ratio, s6d_rank, s6d_both, s7, s8) over every result date: `dates`, `stocks` (ticker, close on every date), `hits` (date index, stock index, level, gate, run_day), `left` (date index, stock index, level, gate, left_reason) | 64-258 KB |

All 31 files: 2.9 MB in the rehearsal of 2026-11-14 (built in 3 s). `met` is a bitmask (1 = A, 2 = B, 4 = C, 8 = D);
S8 is stored at level `standard` only (its own levels: `strong` true = Strong, false = Watch). `near` is every condition
but one met (S8: one of A and B missing, C met). A stock that left and is
one condition short is a `left` row with its `met` (ERRORS M430). `left_reason` is the first condition no longer met,
`gate` or `no_data`.

## The page

`apps/edge-bff/radar` (Vite, TypeScript; the R10 design `verification/radar/index-r10.html`, user D7) reads
`radar-meta`, `radar-days` and the newest board at start, another board when a date is picked, and a filter file when
its detail opens. Its tests: `tests/model.test.ts` (what it picks from the rows), `tests/bundle.test.mjs` (no fixture in
the production bundle); the look check runs on the fixture build (`npm run build:fixture` after
`tests/fixture/save.py`, which saves a rehearsal database's files and is never committed).
