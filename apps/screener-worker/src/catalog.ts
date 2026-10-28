/* GET /v1/catalog and GET /v1/universe (report API CONTRACT 8.4; PAGE LOAD SEQUENCE 6c.4-6c.5; MULTI-USER SCALE AND
   COST 6d.2, 6d.4 rule 4): built once per publication (and again when the publication's outcome changes), held as
   JSON and gzip bytes with ETag = "<sha256 of the JSON bytes>", so every page open of every user is bytes from memory
   or a 304. The bytes depend on the publication and the versions only (no clock, no replica, no owner), so two
   replicas at one publication answer the same bytes and the same ETag.
   - limits[]: every worker limit of 8.9 with its value, rule, one right and one wrong example, generated from the value
     (AGENTS.md "Gates and evidence"; edge-bff adds its own, screener.py with_own_limits);
   - indicators[]: registry.ts catalogIndicators at SCREENER_CAP_BUDGET_MS (caps as max);
   - metrics[], fundamentals[], periods: src/core/screener-metrics.json with availability derived at run time from the
     files the publication indexes (validate.ts availabilityOf; 6.12), never a list kept here;
   - groupings: the reference file's, by the Backtest's rule (snapshot.ts groupingsOf);
   - presets[]: src/core/presets.json; each with its availability and, when available, its match and near counts at
     this publication (computed by the refresh, which keeps each available preset's full result in the result cache, so
     a preset click is a cache hit; 6.7, 6c.4). */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
import type {
  Availability, CatalogMetric, CatalogPreset, CatalogResponse, Definition, Grouping, LimitEntry, MetricRef, Periods, RefreshState, UniverseResponse,
} from '../../edge-bff/screener/src/core/contract.ts';
import { INDICATORS, capOf, catalogIndicators } from '../../edge-bff/screener/src/core/registry.ts';
import type { MetricDefinition, MetricsCatalog } from '../../edge-bff/screener/src/core/validate.ts';
import { availabilityOf } from '../../edge-bff/screener/src/core/validate.ts';
import type { Limits } from './config.ts';
import type { IndexEntry, SnapshotDesc } from './snapshot.ts';

const CORE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../edge-bff/screener/src/core');
export const METRICS_FILE = path.join(CORE, 'screener-metrics.json');
export const PRESETS_FILE = path.join(CORE, 'presets.json');

/** A preset as presets.json holds it (report 6.12, 7.1): id, category, name, why, its definition, and for a preset
    shipped disabled (fundamental or flow legs, P11 / Phase 2) its availability, reason and unavailable legs. */
export interface PresetDef { id: string; category: string; name: string; why: string; definition: Definition; availability?: Availability; reason?: string | null; unavailable_legs?: string[] }

/** screener-metrics.json, or null when the file is not there (main() refuses to start without it). */
export function loadMetrics(file = METRICS_FILE): MetricsCatalog | null {
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, 'utf8')) as MetricsCatalog;
}
/** presets.json (a list, or {presets: [...]}), or null when the file is not there. */
export function loadPresets(file = PRESETS_FILE): PresetDef[] | null {
  if (!fs.existsSync(file)) return null;
  const doc = JSON.parse(fs.readFileSync(file, 'utf8')) as PresetDef[] | { presets: PresetDef[] };
  return Array.isArray(doc) ? doc : doc.presets;
}

/** Every metric reference a definition reads (the presets' configurations are pre-warmed, 6.7). */
export function definitionRefs(d: Definition | undefined): MetricRef[] {
  const out: MetricRef[] = [];
  const add = (s: unknown) => { if (s && typeof s === 'object' && 'kind' in (s as object)) out.push(s as MetricRef) };
  for (const c of d?.conditions ?? []) {
    const t = c?.test as Record<string, any> | undefined;
    if (!t) continue;
    if (t.kind === 'value') add(t.metric);
    else if (t.kind === 'state') { add(t.lhs); add(t.rhs) }
    else if (t.kind === 'event') { add(t.signal?.lhs); add(t.signal?.rhs) }
  }
  for (const t of d?.universe?.metric_filters ?? []) add(t?.metric);
  return out;
}

/* ---- availability (6.12) --------------------------------------------------------------------------------------- */

/** Availability of every metric of screener-metrics.json against the publication's xsection index. */
export function metricAvailability(m: MetricsCatalog | null, index: Record<string, IndexEntry> | null): Map<string, { availability: Availability; reason: string | null }> {
  const out = new Map<string, { availability: Availability; reason: string | null }>();
  for (const x of m?.metrics ?? []) out.set(x.id, availabilityOf(x, (index ?? {}) as Record<string, { columns?: string[] }>));
  return out;
}
const isFundamental = (x: MetricDefinition) => /fundamental/i.test(x.group);
function catalogMetric(x: MetricDefinition, a: { availability: Availability; reason: string | null }): CatalogMetric {
  return { id: x.id, group: x.group, kind: x.kind, params: x.params, tests: x.tests, unit: x.unit, formula: x.formula, interpretation: x.interpretation,
    misuse: x.misuse, availability: a.availability, reason: a.reason, applies_to: x.applies_to };
}

/* ---- limits (8.9; the gate rule: the rule, how to pass it, one right and one wrong example, from the value) ------ */
export function limitEntries(l: Limits): LimitEntry[] {
  const e = (name: string, value: number, unit: string, rule: string, ok: string, refused: string): LimitEntry => ({ name, value, unit, rule, example_ok: ok, example_refused: refused });
  // a length parameter whose cap the budget sets, for the cap_budget_ms example (the first one the registry has)
  let capped: { name: string; key: string; cap: number } | null = null;
  for (const r of INDICATORS) for (const p of r.params) { const c = capOf(p, l.cap_budget_ms); if (!capped && c !== undefined) capped = { name: r.name, key: p.key, cap: p.max !== undefined ? Math.min(p.max, c) : c } }
  return [
    e('max_conditions', l.max_conditions, 'conditions', `at most ${l.max_conditions} enabled conditions in one screen`,
      `a screen with ${l.max_conditions} enabled conditions`, `a screen with ${l.max_conditions + 1} enabled conditions (switch one off or remove it)`),
    e('max_metric_filters', l.max_metric_filters, 'filters', `at most ${l.max_metric_filters} universe metric filters in one screen`,
      `${l.max_metric_filters} metric filters`, `${l.max_metric_filters + 1} metric filters (remove one)`),
    e('within_max', l.within_max, 'sessions', `"within" is a whole number of sessions from 1 to ${l.within_max}`,
      `within ${l.within_max} sessions`, `within ${l.within_max + 1} sessions (use ${l.within_max} or fewer)`),
    e('cap_budget_ms', l.cap_budget_ms, 'ms', `a length parameter is at most its cap (the catalog's max), the longest whose computation over the whole market fits ${l.cap_budget_ms} ms on one thread`,
      capped ? `${capped.name} ${capped.key} ${capped.cap}` : 'a length at its catalog max', capped ? `${capped.name} ${capped.key} ${capped.cap + 1} (use ${capped.cap} or less)` : 'a length above its catalog max'),
    e('compute_budget', l.max_cpu_ms, 'ms', `a screen's predicted worst-case compute is at most ${l.max_cpu_ms} ms; a costlier screen is refused before it runs, naming its costliest condition`,
      'a screen of default indicators (read from the snapshot)', `a screen whose custom conditions are predicted at ${l.max_cpu_ms + 1} ms (use fewer custom conditions or shorter lengths)`),
    e('deadline_ms', l.deadline_ms, 'ms', `a screen is answered within ${l.deadline_ms} ms, waiting included, or stopped with TIMEOUT`,
      `a screen answered after ${l.deadline_ms} ms`, `a screen still running after ${l.deadline_ms} ms (use fewer custom conditions or shorter lengths)`),
    e('owner_inflight', l.owner_inflight, 'requests', `at most ${l.owner_inflight} requests of one user compute at once on a replica; the next ones wait their turn`,
      `${l.owner_inflight} requests computing at once`, `request ${l.owner_inflight + 1} waits until one of them ends (it is not refused)`),
    e('owner_cpu_budget', l.owner_cpu_ms, 'ms per minute', `one user's requests use at most ${l.owner_cpu_ms} ms of compute per minute on a replica (P33); a request that would pass it is refused with the seconds to wait`,
      `requests using ${l.owner_cpu_ms} ms within one minute`, `a request that would bring the minute to ${l.owner_cpu_ms + 1} ms (wait the seconds named, or use fewer custom conditions)`),
    e('previous_grace_s', l.previous_grace_s, 's', `after new data is published, a page still showing the previous data is served on it for ${l.previous_grace_s} s`,
      `a screen pinned to the previous data ${l.previous_grace_s} s after the new data arrived`, `a screen pinned to the previous data ${l.previous_grace_s + 1} s after (DATA_VERSION_CHANGED: the page re-reads the catalog and runs again)`),
    e('queue', l.queue, 'requests', `at most ${l.queue} requests wait for a compute thread on a replica, every user together`,
      `a request arriving while ${Math.max(0, l.queue - 1)} wait`, `a request arriving while ${l.queue} wait (BUSY: retry in a few seconds)`),
    e('max_counts', l.max_counts, 'definitions', `counts for at most ${l.max_counts} saved screens per request`,
      `${l.max_counts} saved screens`, `${l.max_counts + 1} saved screens (ask for the rest in a second request)`),
    e('max_response_bytes', l.max_response_bytes, 'bytes', `an answer is at most ${l.max_response_bytes} bytes of JSON`,
      `an answer of ${l.max_response_bytes} bytes`, `an answer of ${l.max_response_bytes + 1} bytes (narrow the universe or add a condition)`),
    e('max_file_bytes', l.max_file_bytes, 'bytes', `a published cross-sectional file is at most ${l.max_file_bytes} bytes (gzip); a larger one fails the refresh and the previous data keeps serving`,
      `a file of ${l.max_file_bytes} bytes`, `a file of ${l.max_file_bytes + 1} bytes (an operator raises SCREENER_MAX_FILE_BYTES)`),
    e('max_inflated_bytes', l.max_inflated_bytes, 'bytes', `a published file inflates to at most ${l.max_inflated_bytes} bytes; a larger one fails the refresh`,
      `a file inflating to ${l.max_inflated_bytes} bytes`, `a file inflating to ${l.max_inflated_bytes + 1} bytes (an operator raises SCREENER_MAX_INFLATED_BYTES)`),
    e('max_refresh_bytes', l.max_refresh_bytes, 'bytes', `one refresh downloads at most ${l.max_refresh_bytes} bytes; more fails the refresh`,
      `a refresh of ${l.max_refresh_bytes} bytes`, `a refresh of ${l.max_refresh_bytes + 1} bytes (an operator raises SCREENER_MAX_REFRESH_BYTES)`),
  ];
}

/* ---- documents -------------------------------------------------------------------------------------------------- */
export interface Doc { json: Buffer; gzip: Buffer; etag: string }
export function doc(value: unknown): Doc {
  const json = Buffer.from(JSON.stringify(value));
  return { json, gzip: zlib.gzipSync(json, { level: 9 }), etag: `"${crypto.createHash('sha256').update(json).digest('hex')}"` };
}

export interface CatalogInput {
  desc: SnapshotDesc; refresh: RefreshState; limits: Limits; metrics: MetricsCatalog | null;
  availability: Map<string, { availability: Availability; reason: string | null }>;
  groupings: Grouping[]; presets: CatalogPreset[];
}
export function catalogDoc(c: CatalogInput): Doc {
  const metrics: CatalogMetric[] = [], fundamentals: CatalogMetric[] = [];
  for (const x of c.metrics?.metrics ?? []) {
    const a = c.availability.get(x.id) ?? { availability: 'REQUIRES_DATA' as Availability, reason: 'Not evaluated.' };
    (isFundamental(x) ? fundamentals : metrics).push(catalogMetric(x, a));
  }
  const body: CatalogResponse = {
    versions: { ...c.desc.versions }, data: { ...c.desc.data, refresh: c.refresh },
    limits: limitEntries(c.limits),
    indicators: catalogIndicators({ capBudgetMs: c.limits.cap_budget_ms }),
    metrics, fundamentals, periods: (c.metrics?.periods ?? null) as Periods, groupings: c.groupings, presets: c.presets,
  };
  return doc(body);
}
export function universeDoc(desc: SnapshotDesc): Doc {
  const body: UniverseResponse = { versions: { ...desc.versions }, data: { ...desc.data }, rows: desc.rows };
  return doc(body);
}
