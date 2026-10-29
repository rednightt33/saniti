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
   - It deletes the same objects the old cleanup deleted at the start of the next daily run, a few minutes later.
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

## 5. Dev run after the deploy

(Added after the deploy.)
