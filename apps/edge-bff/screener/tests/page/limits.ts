/* The catalog's limits[] as the page tests use them: GET /api/v1/screener/catalog limits[] as the worker generates it
   (apps/screener-worker/src/catalog.ts limitEntries at WORKER_VALUES; the refresh caps are left out: they fail a
   refresh, never a request) followed by edge-bff's own (app/screener.py own_limits, copied in
   tests/fixture/edge-bff-limits.json). A copy, so a page test reads the words a user meets; tests/page/plain-words.test.ts
   fails when the worker part differs from limitEntries at these values, and apps/edge-bff/tests/test_screener.py when
   the JSON differs from own_limits(). After a change of the generated words, regenerate the copy from them. */
import type { LimitEntry } from '../../src/core/contract.ts';
import edgeBff from '../fixture/edge-bff-limits.json' with { type: 'json' };

export const L = (name: string, value: number, unit: string, rule: string, example_ok: string, example_refused: string): LimitEntry => ({ name, value, unit, rule, example_ok, example_refused });

/** the worker's environment values this copy was generated at (apps/screener-worker/src/config.ts Limits) */
export const WORKER_VALUES = {
  max_cpu_ms: 20000, cap_budget_ms: 2000, deadline_ms: 20000, max_conditions: 20, max_metric_filters: 8, within_max: 130, max_counts: 50,
  max_response_bytes: 2097152, queue: 4, owner_inflight: 2, owner_cpu_ms: 60000, previous_grace_s: 600,
  max_file_bytes: 67108864, max_inflated_bytes: 268435456, max_refresh_bytes: 134217728, max_request_bytes: 131072,
};
/** the limits that fail a refresh and never a request (not in WORKER_LIMITS) */
export const REFRESH_CAPS: readonly string[] = ['max_file_bytes', 'max_inflated_bytes', 'max_refresh_bytes'];

export const WORKER_LIMITS: LimitEntry[] = [
  L('max_conditions', 20, 'conditions', 'at most 20 enabled conditions in one screen', 'a screen with 20 enabled conditions', 'a screen with 21 enabled conditions (switch one off or remove it)'),
  L('max_metric_filters', 8, 'filters', 'at most 8 universe metric filters in one screen', '8 metric filters', '9 metric filters (remove one)'),
  L('within_max', 130, 'sessions', '"within" is a whole number of sessions from 1 to 130', 'within 130 sessions', 'within 131 sessions (use 130 or fewer)'),
  L('cap_budget_ms', 2000, 'ms', 'a length parameter is at most its cap (the highest value its field allows): the longest length whose computation over the whole market takes at most 2000 ms on one processor core', 'Hull Moving Average Length 252', 'Hull Moving Average Length 253 (use 252 or less)'),
  L('compute_budget', 20000, 'ms', "a screen's predicted worst-case compute is at most 20000 ms; a costlier screen is refused before it runs, naming its costliest condition", 'a screen of indicators at their default parameters (computed in advance for every stock)', 'a screen whose custom conditions are predicted at 20001 ms (use fewer custom conditions or shorter lengths)'),
  L('deadline_ms', 20000, 'ms', 'a screen is answered within 20000 ms, waiting included, or stopped', 'a screen answered after 20000 ms', 'a screen still running after 20000 ms (use fewer custom conditions or shorter lengths)'),
  L('owner_inflight', 2, 'requests', 'at most 2 requests of one user compute at once on one server; the next ones wait their turn', '2 requests computing at once', 'request 3 waits until one of them ends (it is not refused)'),
  L('owner_cpu_budget', 60000, 'ms per minute', "one user's requests use at most 60000 ms of compute per minute on one server; a request that would pass it is refused with the seconds to wait", 'requests using 60000 ms within one minute', 'a request that would bring the minute to 60001 ms (wait the seconds named, or use fewer custom conditions)'),
  L('previous_grace_s', 600, 's', 'after new data is published, a page still showing the previous data is served on it for 600 s', 'a screen pinned to the previous data 600 s after the new data arrived', 'a screen pinned to the previous data 601 s after (the page loads the new data and runs the screen again)'),
  L('queue', 4, 'requests', 'at most 4 requests wait to be computed on one server, all users together', 'a request arriving while 3 wait', 'a request arriving while 4 wait (retry in a few seconds)'),
  L('max_counts', 50, 'saved screens', 'counts for at most 50 saved screens per request', '50 saved screens', '51 saved screens (ask for the rest in a second request)'),
  L('max_response_bytes', 2097152, 'bytes', 'an answer is at most 2097152 bytes of JSON', 'an answer of 2097152 bytes', 'an answer of 2097153 bytes (narrow the universe or add a condition)'),
];
export const EDGE_BFF_LIMITS: LimitEntry[] = edgeBff as LimitEntry[];
export const LIMITS: LimitEntry[] = [...WORKER_LIMITS, ...EDGE_BFF_LIMITS];
