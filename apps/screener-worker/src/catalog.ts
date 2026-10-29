/* GET /v1/catalog and GET /v1/universe (report API CONTRACT 8.4; PAGE LOAD SEQUENCE 6c.4-6c.5; MULTI-USER SCALE AND
   COST 6d.2, 6d.4 rule 4): built once per publication (and again when the publication's outcome changes), held as
   JSON and gzip bytes with ETag = "<sha256 of the JSON bytes>", so every page open of every user is bytes from memory
   or a 304. The bytes depend on the publication and the versions only (no clock, no replica, no owner), so two
   replicas at one publication answer the same bytes and the same ETag.
   - limits[]: every worker limit of 8.9 with its value, rule, one right and one wrong example, generated from the value
     (AGENTS.md "Gates and evidence"; edge-bff adds its own, screener.py with_own_limits);
   - indicators[]: registry.ts catalogIndicators at SCREENER_CAP_BUDGET_MS (caps as max);
   - metrics[], fundamentals[], periods: src/core/screener-metrics.json with availability derived at run time from the
     files the publication indexes and this snapshot read (validate.ts availabilityMap; 6.12), never a list kept here;
   - groupings: the reference file's, by the Backtest's rule (snapshot.ts groupingsOf);
   - presets[]: src/core/presets.json (core catalog.ts PRESETS); each with its availability (validate.ts
     presetAvailability: available only when every leg is, never run with a leg removed) and, when available, its match and near counts at
     this publication (computed by the refresh, which keeps each available preset's full result in the result cache, so
     a preset click is a cache hit; 6.7, 6c.4). */
import crypto from 'node:crypto';
import zlib from 'node:zlib';
import type { Availability, CatalogMetric, CatalogPreset, CatalogResponse, Grouping, LimitEntry, Periods, RefreshState, UniverseResponse } from '../../edge-bff/screener/src/core/contract.ts';
import type { MetricDefinition, MetricsCatalog } from '../../edge-bff/screener/src/core/catalog.ts';
import { INDICATORS, capOf, catalogIndicators } from '../../edge-bff/screener/src/core/registry.ts';
import { availabilityMap } from '../../edge-bff/screener/src/core/validate.ts';
import type { Limits } from './config.ts';
import type { IndexEntry, SnapshotDesc } from './snapshot.ts';

/* ---- availability (6.12) --------------------------------------------------------------------------------------- */

/** Availability of every metric of the catalog (validate.ts availabilityMap) against the publication's xsection index
    and `read`, the files the snapshot was built from (the names of its `files`: snapshot.ts PHASE1_FILES, as the
    refresh downloaded them): a file counts only when it is both indexed and read, so a metric over a file the publisher
    writes before this build reads it shows REQUIRES_DATA ("the Screener does not read it yet"), the reason a run with it
    is refused with, never AVAILABLE and then refused at bind. */
export const metricAvailability = (m: MetricsCatalog, index: Record<string, IndexEntry> | null, read: Iterable<string>): Map<string, { availability: Availability; reason: string | null }> =>
  availabilityMap((index ?? {}) as Record<string, { columns?: string[] }>, m, new Set(read));
const isFundamental = (x: MetricDefinition) => /fundamental/i.test(x.group);
/** A catalog entry as the page reads it (contract.ts CatalogMetric plus the additive fields screener-metrics.json
    carries for the page: label, short, synonyms, default_test, ref, fl; the fixture tests/fixture/api.ts has the same
    shape); the internal fields (requires, decision, evidence, unavailable_reason) stay in the worker. */
function catalogMetric(x: MetricDefinition, a: { availability: Availability; reason: string | null }): CatalogMetric {
  const extra: Record<string, unknown> = {};
  for (const k of ['label', 'short', 'synonyms', 'default_test', 'ref', 'fl'] as const) if (x[k] !== undefined) extra[k] = x[k];
  return { id: x.id, group: x.group, kind: x.kind, params: x.params, tests: x.tests, unit: x.unit, formula: x.formula, interpretation: x.interpretation,
    misuse: x.misuse, availability: a.availability, reason: a.reason, applies_to: x.applies_to, ...extra } as CatalogMetric;
}

/* ---- limits (8.9; the gate rule: the rule, how to pass it, one right and one wrong example, from the value) ------ */
/* The words are shown as they are: Method & sources lists every entry, and the page words each refusal of a limit from
   its rule, unit and the fix in the closing parenthesis of example_refused (screener texts.ts fixOf). So they are plain
   words, with no limit, code, variable or decision name and no "replica" (one server); the page test
   tests/page/plain-words.test.ts walks them at the dev values. */
export function limitEntries(l: Limits): LimitEntry[] {
  const e = (name: string, value: number, unit: string, rule: string, ok: string, refused: string): LimitEntry => ({ name, value, unit, rule, example_ok: ok, example_refused: refused });
  const requests = (n: number) => `${n} request${n === 1 ? '' : 's'}`;
  // a length parameter whose cap the budget sets, for the cap_budget_ms example (the first one the registry has)
  // (named as the card shows it: the indicator's name and the parameter's label)
  let capped: { name: string; key: string; cap: number } | null = null;
  for (const r of INDICATORS) for (const p of r.params) { const c = capOf(p, l.cap_budget_ms); if (!capped && c !== undefined) capped = { name: r.name, key: p.label || p.key, cap: p.max !== undefined ? Math.min(p.max, c) : c } }
  return [
    e('max_conditions', l.max_conditions, 'conditions', `at most ${l.max_conditions} enabled conditions in one screen`,
      `a screen with ${l.max_conditions} enabled conditions`, `a screen with ${l.max_conditions + 1} enabled conditions (switch one off or remove it)`),
    e('max_metric_filters', l.max_metric_filters, 'filters', `at most ${l.max_metric_filters} universe metric filters in one screen`,
      `${l.max_metric_filters} metric filters`, `${l.max_metric_filters + 1} metric filters (remove one)`),
    e('within_max', l.within_max, 'sessions', `"within" is a whole number of sessions from 1 to ${l.within_max}`,
      `within ${l.within_max} sessions`, `within ${l.within_max + 1} sessions (use ${l.within_max} or fewer)`),
    e('cap_budget_ms', l.cap_budget_ms, 'ms', `a length parameter is at most its cap (the highest value its field allows): the longest length whose computation over the whole market takes at most ${l.cap_budget_ms} ms on one processor core`,
      capped ? `${capped.name} ${capped.key} ${capped.cap}` : 'a length at its highest allowed value', capped ? `${capped.name} ${capped.key} ${capped.cap + 1} (use ${capped.cap} or less)` : 'a length above its highest allowed value (use a shorter one)'),
    e('compute_budget', l.max_cpu_ms, 'ms', `a screen's predicted worst-case compute is at most ${l.max_cpu_ms} ms; a costlier screen is refused before it runs, naming its costliest condition`,
      'a screen of indicators at their default parameters (computed in advance for every stock)', `a screen whose custom conditions are predicted at ${l.max_cpu_ms + 1} ms (use fewer custom conditions or shorter lengths)`),
    e('deadline_ms', l.deadline_ms, 'ms', `a screen is answered within ${l.deadline_ms} ms, waiting included, or stopped`,
      `a screen answered after ${l.deadline_ms} ms`, `a screen still running after ${l.deadline_ms} ms (use fewer custom conditions or shorter lengths)`),
    e('owner_inflight', l.owner_inflight, 'requests', `at most ${requests(l.owner_inflight)} of one user ${l.owner_inflight === 1 ? 'computes' : 'compute'} at once on one server; the next ones wait their turn`,
      `${requests(l.owner_inflight)} computing at once`, `request ${l.owner_inflight + 1} waits until ${l.owner_inflight === 1 ? 'it ends' : 'one of them ends'} (it is not refused)`),
    e('owner_cpu_budget', l.owner_cpu_ms, 'ms per minute', `one user's requests use at most ${l.owner_cpu_ms} ms of compute per minute on one server; a request that would pass it is refused with the seconds to wait`,
      `requests using ${l.owner_cpu_ms} ms within one minute`, `a request that would bring the minute to ${l.owner_cpu_ms + 1} ms (wait the seconds named, or use fewer custom conditions)`),
    e('previous_grace_s', l.previous_grace_s, 's', `after new data is published, a page still showing the previous data is served on it for ${l.previous_grace_s} s`,
      `a screen pinned to the previous data ${l.previous_grace_s} s after the new data arrived`, `a screen pinned to the previous data ${l.previous_grace_s + 1} s after (the page loads the new data and runs the screen again)`),
    e('queue', l.queue, 'requests', `at most ${requests(l.queue)} ${l.queue === 1 ? 'waits' : 'wait'} to be computed on one server, all users together`,
      `a request arriving while ${Math.max(0, l.queue - 1)} wait`, `a request arriving while ${l.queue} wait (retry in a few seconds)`),
    e('max_counts', l.max_counts, 'saved screens', `counts for at most ${l.max_counts} saved screens per request`,
      `${l.max_counts} saved screens`, `${l.max_counts + 1} saved screens (ask for the rest in a second request)`),
    e('max_response_bytes', l.max_response_bytes, 'bytes', `an answer is at most ${l.max_response_bytes} bytes of JSON`,
      `an answer of ${l.max_response_bytes} bytes`, `an answer of ${l.max_response_bytes + 1} bytes (narrow the universe or add a condition)`),
    e('max_file_bytes', l.max_file_bytes, 'bytes', `a published market-wide data file is at most ${l.max_file_bytes} bytes compressed; a larger one fails the data refresh and the previous data keeps serving`,
      `a file of ${l.max_file_bytes} bytes`, `a file of ${l.max_file_bytes + 1} bytes (an operator raises the limit)`),
    e('max_inflated_bytes', l.max_inflated_bytes, 'bytes', `a published data file is at most ${l.max_inflated_bytes} bytes uncompressed; a larger one fails the data refresh`,
      `a file of ${l.max_inflated_bytes} bytes uncompressed`, `a file of ${l.max_inflated_bytes + 1} bytes uncompressed (an operator raises the limit)`),
    e('max_refresh_bytes', l.max_refresh_bytes, 'bytes', `one data refresh downloads at most ${l.max_refresh_bytes} bytes; more fails it`,
      `a refresh of ${l.max_refresh_bytes} bytes`, `a refresh of ${l.max_refresh_bytes + 1} bytes (an operator raises the limit)`),
  ];
}

/* ---- documents -------------------------------------------------------------------------------------------------- */
export interface Doc { json: Buffer; gzip: Buffer; etag: string }
export function doc(value: unknown): Doc {
  const json = Buffer.from(JSON.stringify(value));
  return { json, gzip: zlib.gzipSync(json, { level: 9 }), etag: `"${crypto.createHash('sha256').update(json).digest('hex')}"` };
}

export interface CatalogInput {
  desc: SnapshotDesc; refresh: RefreshState; limits: Limits; metrics: MetricsCatalog;
  availability: Map<string, { availability: Availability; reason: string | null }>;
  groupings: Grouping[]; presets: CatalogPreset[];
}
export function catalogDoc(c: CatalogInput): Doc {
  const metrics: CatalogMetric[] = [], fundamentals: CatalogMetric[] = [];
  for (const x of c.metrics.metrics) {
    const a = c.availability.get(x.id) ?? { availability: 'REQUIRES_DATA' as Availability, reason: 'Not evaluated.' };
    (isFundamental(x) ? fundamentals : metrics).push(catalogMetric(x, a));
  }
  const body: CatalogResponse = {
    versions: { ...c.desc.versions }, data: { ...c.desc.data, refresh: c.refresh },
    limits: limitEntries(c.limits),
    indicators: catalogIndicators({ capBudgetMs: c.limits.cap_budget_ms }),
    metrics, fundamentals, periods: c.metrics.periods as Periods, groupings: c.groupings, presets: c.presets,
  };
  return doc(body);
}
export function universeDoc(desc: SnapshotDesc): Doc {
  const body: UniverseResponse = { versions: { ...desc.versions }, data: { ...desc.data }, rows: desc.rows };
  return doc(body);
}
