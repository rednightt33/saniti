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
