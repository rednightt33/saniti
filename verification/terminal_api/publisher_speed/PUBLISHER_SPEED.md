# Publisher speed (EXEC-PUBLISHER-SPEED, go 2026-10-29)

The user approved this work on 2026-10-29 ("Okay, jalankan ... it's a go"). It covers ERRORS M301, about the cleanup
on the publish path and requests made one at a time, and M303, about failures that raise no alert.

This file holds the evidence: the run before the change, the measurements behind the design, and the local
rehearsal. The dev run after the deploy is added at the end.

## 1. The run before the change (19:00 WIB, 2026-10-29, deployment `0d33d8ac`)

Read with `railway logs --json`. Times are UTC.

| Step | From | To | Took |
|---|---|---|---|
| Price stamps, one SQL statement over 6,218 ticker-years | 12:04:41 | 12:04:53 | 12 s |
| 845 manifests read from the bucket, one at a time | 12:04:53 | 12:13:36 | 8.7 min |
| Cleanup: listing of the whole bucket | 12:13:36 | 12:32:37 | 19 min, then failed |
| 828 price files (2026 only) | 12:32:37 | about 12:41 | about 8 min |
| 828 price packs | about 12:41 | 12:51:15 | about 10 min |
| Two xsection files | 12:51:15 | 12:51:56 | 41 s |
| 828 manifests, then refs and `state.json` | 12:51:56 | 13:00:00 | 8 min |

The run wrote 1,658 files, 27.68 MB, in 3,314.5 s.

- **Database:** about 1 minute in all (`EXPLAIN ANALYZE`: 6 ms per year file, 27 ms per pack).
- **Only the current year was rewritten:** of 6,218 ticker-years, only the 828 of 2026 were written again.
- **The cleanup listing:** it stopped on two `ReadTimeoutError` (12:20:01, 12:26:25), each after about 6 minutes
  without an answer, and ended with `gc_failed` `ConnectionClosedError`.

## 2. What the bucket costs (read-only, from a US host, 2026-10-29 about 14:30 UTC)

Measured with `bucket_probe.py`; the output is in `bucket_probe_20261029.txt`.

| Request | Time |
|---|---|
| One GET of a manifest | 0.53-0.57 s |
| 64 GETs, 8 threads | 5.76 s |
| 64 GETs, 16 threads | 2.95 s |
| 64 GETs, 32 threads | 2.08 s |
| Listing page of 1,000 keys (`price/`) | 0.40-0.50 s |
| Listing of all 7,872 `price/` keys | 3.6 s |

Two conclusions follow:

- **The bucket is not slow.** The cost is the number of requests made one after another, at about 0.55 s each
  between `sfo` and `sin`.
- **The 19-minute cleanup came from requests that hung.** It was not the size of the listing: the client waited 60 s
  per attempt, with 5 attempts, before giving up.

## 3. The change (`apps/terminal-publisher/publisher.py`)

1. **Parallel requests, barriers kept.** The manifests are read and the objects are put through
   `TERMINAL_BUCKET_THREADS` threads (default 16, `Uploads`, `load_manifests`).
   - The barriers keep the order readers rely on: data files, packs and xsection files come before the manifests,
     and every manifest comes before `state.json`.
   - A failed put stops the run before any manifest or `state.json` names the object.
   - The xsection files and reference copies are put at once, so a failure stays that file's failure (exit 3), as
     before.
   - Database statements stay on one connection, in order.
2. **Bucket client limits.** The connect timeout is 10 s and the read timeout 30 s per socket operation, with 3
   attempts. A hung request is asked again sooner.
3. **Cleanup after `state.json`.** The cleanup runs after `state.json` (`collect_garbage(indexes, before)`).
   - It uses the baseline taken before the run's first write (`cleanup_baseline`) and protects what either the
     previous or the new publication names.
   - It deletes the objects the old cleanup deleted at the start of the same run, at its end instead.
   - The baseline is given up after 60 s, and the cleanup is then skipped.
   - A failed or slow listing no longer delays the publication.
4. **Alerts (M303).**
   - telegram-monitor sends a message (source `Terminal_Publisher_Health`) for a failed run, a run still going
     after 30 minutes, a run that published without a cross-sectional or reference file, and a run time whose
     publication a check tick does not find.
   - The cron gains the check times, 30 minutes after each run time: `0,30 0,1,12 * * *`.

## 4. Local rehearsal (`latency_rehearsal.py 16 0.54`, output `latency_rehearsal_16_054.txt`)

The rehearsal is the daily run on a synthetic 845-ticker universe. Every ticker's 2026 file has changed, as on
2026-10-29. Every bucket request (put, get, listing page, delete batch) waits 0.54 s. Database statements run in
memory, with no wait.

| Step | Seconds |
|---|---|
| Plan, including 845 manifests read | 30.3 |
| 828 price files | 26.1 |
| 828 packs | 28.0 |
| xsection | 2.2 |
| 828 manifests | 28.7 |
| refs | 2.7 |
| `state.json` | 0.5 |
| **Total** | **125.1** |

- **Requests:** 2,505 puts, 848 gets and 16 listing pages. At 0.54 s each, one at a time, they would take about 30
  minutes.
- **Cleanup:** it ran after the publication and took 6.5 s (11,806 objects listed).
- **Expected on dev (INFERENCE):** the rehearsal's 2 minutes, plus about 30 s of database statements, plus the
  xsection build measured on dev (41 s): about 3-4 minutes to `state.json`. It is checked by the dev run below.

## 5. Independent review (2026-10-29, before the PR)

A separate review agent, given the code and the readers' rules rather than our conclusions, found three bugs. Each fix
has a test that fails when the fix is removed.

| Finding | Fix |
|---|---|
| A barrier could let a failed put through. `Future.set_exception` wakes the waiter before the done callback that recorded the error runs; reproduced at 21 of 5,000 with a tiny switch interval. | `Uploads.wait` keeps what `future.exception()` returns. |
| A `Publisher` used again after a failed run kept in-memory manifest entries for puts that never happened. Production makes one per process. | A failed run drops its in-memory manifests and changes. |
| The `slow` alert could fire during the cleanup, after the publication was already out. | `slow_alert` skips it in the cleanup step. |

Further points from the review:

- **Baseline listing:** it could still hold the publication on a hung page, so it now runs in a thread joined for at
  most 60 s.
- **Failure step:** the alert now names the step of the put that failed.
- **Fewer manifest reads:** a logos or broker-range run no longer reads every manifest.
- **Test timing:** one timing assertion was removed.
- **Wording:** the documentation now says "at the start of the same run".

The review found the cleanup rule sound in every scenario tried:

- daily sequences;
- manual runs minutes apart;
- a run that crashed, with or without manifests;
- tickers leaving or joining the universe;
- content returning to an old key;
- logos, backfill, packs and events runs before a daily run.

## 6. Dev run after the deploy (2026-10-29, manual run, deployment `f1092ec4`)

The deploys are listed in RAILWAY_CHANGELOG 2026-10-29. The run's own log is `dev_run_20261029_1521.jsonl`.

| Step | Seconds | Before (19:00 WIB run) |
|---|---|---|
| 845 manifests read | 34.8 | 8.7 minutes |
| Plan in all (DB stamps, baseline, manifests) | 48.1 | about 9 minutes |
| Files and packs | 0 (nothing had changed) | about 18 minutes |
| xsection (same bytes) | 35.1 | 41 |
| refs | 2.6 | in the 8 minutes with the manifests |
| `state.json` at | 86.3 s after the start | 55 minutes after the start |

- **Not yet measured:** no data file changed, so the parallel write path has not run on dev yet. The first scheduled
  daily runs measure it: 07:30 WIB (new broker data, if Stockbit has loaded it) and 19:00 WIB (new prices).
- **Checks after the run:**
  - terminal-api check `present` VERDICT PASS (`verification/screener/jobs/terminal_check_pub_speed_20261029.log`);
  - Backtest E2E single passed;
  - the Screener serves the new publication, and its four test screens return rows identical to before.
- **Still open, the cleanup listing from the publisher (ERRORS M301):**
  - After `state.json`, the whole-bucket listing hung three times (`ReadTimeoutError`) and the cleanup ended
    `gc_failed` at 15:32:08, 8.7 minutes after the publication. Nothing was deleted, and nothing was delayed.
  - The same listing from the sandbox, at the same time and again later, took 10.9 and 11.8 s for 21 pages
    (`list_probe_20261029.txt`).
  - The 19:00 WIB run's cleanup, before the change, failed the same way.
  - So the hang depends on the path from the publisher's container, not on the bucket alone. The cause is SUSPECTED,
    not verified.
  - Checks that would tell:
    - log every listing page's time and size, so the page that hangs is known;
    - list per family prefix with smaller pages (`MaxKeys`);
    - run the same listing from another `sfo` service.

## 7. Deleting what a run replaced, after the switch (user 2026-10-29: "Ok setuju"; not yet deployed)

The user's idea (2026-10-29): "ketika file di storage sudah fully updated, maka langsung di-switch aja storage akan
langsung menggunakan file baru dan proses penghapusan file lama langsung dijalankan". The refined proposal was
approved with "Ok setuju": a 10-minute wait, deletion by name without a listing, and the full listing only as a daily
safety net.

### 7.1 Root cause and class

- **Verified (code, section 6):** every run's deletion depended on one listing of the whole bucket (`collect_garbage`).
  When one page hung, nothing was deleted, though the run already knew which objects it had replaced.
- **Class:** housekeeping that needs a listing of the whole store to decide what one run already knows. It affects
  every family under content keys: data files, packs, xsection, refs, and the flow, macro and cross-asset files
  planned.
- **SUSPECTED, not verified:** why the listing hangs from the publisher's container. The per-folder logs below are
  the check.

### 7.2 The change (`apps/terminal-publisher/publisher.py`)

1. **`delete_replaced`, every mode that publishes.**
   - After `state.json` the run waits `TERMINAL_DELETE_AFTER_SECONDS` (600; never below `MIN_DELETE_AFTER_SECONDS`,
     300), then deletes `replaced_keys` in one batch per 1,000 keys.
   - `replaced_keys` holds the keys a manifest named when this run read it (`keep_manifest`, `loaded_named`) and no
     longer names, and the keys the previous `state.json` xsection and refs indexes named and the new ones do not.
   - Every key the new publication names (any manifest the run holds, either index) is taken out.
   - The keys are derived from the manifests and indexes, so a new family is covered without a code change.
2. **The wait covers a reader of the previous publication.**
   - terminal-api's manifest and `state.json` cache: 60 s (`manifest_cache_seconds`).
   - A presigned URL's lifetime: `terminal.quota` `url_ttl_seconds`, 120 s by the migration. Neither the publisher's
     login nor pgweb can read the live value: "permission denied for schema terminal" (checked 2026-10-29).
   - The download started on that URL.
   - terminal-api grants only keys of the current publication (`/files` and `/bundle` from the manifest, `/xsection`
     and `/reference` from `state.json`). The screener-worker downloads right after its grant and caches by sha256
     (`apps/screener-worker/src/refresh.ts` rule 4).
3. **Another run during the wait (`still_current`, added from inspection).**
   - Before deleting, the run reads `state.json` again.
   - If another run published during the wait, it deletes nothing (`replaced_skipped`) and skips its full cleanup,
     because that run's manifests may name one of these keys again (content that returned).
4. **The full cleanup (`collect_garbage`) as the daily safety net.**
   - It runs only in the daily run at `TERMINAL_SWEEP_WIB` (19:00, `sweep_due`; never a manual run).
   - It is given up after `SWEEP_SECONDS` (300; `gc_failed` with step `sweep`).
   - The new mode `cleanup` runs it alone, without the database.
5. **Diagnosable listing.**
   - The listing goes per folder: first `manifest/` and `state.json`, then each family, 8 at a time.
   - Pages are `LIST_PAGE_KEYS` (200) keys; the server's default is 1,000.
   - Each folder logs one `listed` line (pages, keys, seconds, slowest page), and each page over 5 s logs
     `list_page_slow`.
   - A retried request names itself (`bucket_retry` `request`, for example `list price/ page 12`).

### 7.3 Rehearsal (`latency_rehearsal.py 16 0.54 [0|1]`)

The synthetic daily run of section 4 is repeated on the new code. Every request waits 0.54 s; the wait is recorded,
not slept.

| Run | To `state.json` | Replaced and deleted | Full cleanup |
|---|---|---|---|
| 07:30 WIB, no full cleanup (`latency_rehearsal_16_054_0730.txt`) | 117.3 s | 1,657 objects, 2 delete requests, 1.1 s, after the 600 s wait | none; 2 listing requests in all (the `xsection/` and `ref/` checks) |
| 19:00 WIB, with the full cleanup (`latency_rehearsal_16_054_1900.txt`) | 120.6 s | 1,657 objects, 1.1 s | 10,149 objects listed in 64 pages of 200, 21.7 s; 0 deleted (nothing left over) |

- **Before this change:** the cleanup of section 4 deleted 0 objects in this rehearsal. It protected the previous
  publication, so what a run replaced stayed until the next run.
- **Now:** the same 1,657 objects go 10 minutes after the switch.
- **On dev (INFERENCE):** a daily run ends about 10 minutes later than its `state.json`. The 19:00 WIB run ends at
  most 5 minutes after that. The check tick 30 minutes after the run time still finds the run finished.

### 7.4 Tests and mutation check

- **Tests:** `apps/terminal-publisher/tests/test_publisher.py`, 120 passed, three runs in a row. The new tests cover:
  - the wait and its floor;
  - `replaced_keys` never returns a key the new publication names;
  - a run stopped during the wait deletes nothing, and the cleanup outside a run takes what it left;
  - a newer publication during the wait;
  - a run outside the sweep time deletes by name and never lists the bucket;
  - a run that replaced nothing does not wait;
  - `sweep_due`, and `main` passing it to the run;
  - mode `cleanup` without a database;
  - listing pages and logs;
  - the retry's request name;
  - a `Publisher` used again after a failed run.
- **Mutation check:** `mutate_delete_replaced.py`, output `mutate_delete_replaced_20261029.txt`. It applies 22
  mutations of the new rules to a copy of the publisher. Each one fails at least one test, and the unmutated copy
  passes. Among the mutations:
  - no wait, or the deletion before the wait;
  - no floor;
  - named keys not protected;
  - the index part or the manifest part dropped;
  - the held-manifest guard and the reset after a failure, each alone and both together;
  - `still_current` dropped, in the deletion or in the sweep;
  - `sweep_due` ignoring the mode, a manual run or the time;
  - `main` ignoring `sweep_due`;
  - mode `cleanup` doing nothing;
  - `MaxKeys` and the listing logs dropped;
  - the indexed folders not listed.

### 7.5 What it covers and what it does not

- **Covers:**
  - what any run replaces, at every run, without a listing;
  - the objects a crashed or stopped run left, at the next 19:00 WIB full cleanup or by mode `cleanup`.
- **Does not cover:**
  - why a listing hangs from the publisher's container (the logs will show which folder and page);
  - a second run that is between its manifests and its `state.json` at the moment of the deletion and names a deleted
    key again. Scheduled runs never overlap, because Railway does not start a cron tick while a run goes on; manual
    runs follow M229, away from the run times.
  - a `url_ttl_seconds` raised above about 500 s. `TERMINAL_DELETE_AFTER_SECONDS` must then be raised with it.
- **Deploy (dev, after the 07:30 WIB run of 2026-10-30 is checked):** CLI upload of the publisher (M229 option A),
  one measured run, then the checks of section 6: terminal-api `present`, Backtest E2E, the Screener, and a count of
  objects no publication names (`garbage_probe.py`, read-only).
