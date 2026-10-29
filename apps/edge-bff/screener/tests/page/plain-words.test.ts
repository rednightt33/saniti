/* Every user-visible string of the catalog is plain words (AGENTS.md "Gates and evidence" (d); ERRORS: catalog and
   server text written for developers but shown to users carried decision ids (P11), flow ids (FL09), plan ids
   (EXEC-MCAP), registry ids (I37), NA codes, wire names (market_board, value2) and "on a replica"). Walks what the page
   shows, built by the real generators: the worker's catalog (apps/screener-worker/src/catalog.ts catalogDoc and
   limitEntries, at the dev values of the deploy runbook and at every value a limit can reasonably take), edge-bff's
   own limits (the copy tests/fixture/edge-bff-limits.json, which apps/edge-bff/tests/test_screener.py checks against
   own_limits()), the metrics of screener-metrics.json as entriesOf turns them into the adder's, browser's and cards'
   words (label, short name, description, reason, parameters, test labels), their misuse warnings, the availability
   reasons at three publications, the registry's indicators (description, parameter and output labels, disabled
   reasons), the presets (name, why, the reason naming their unavailable legs, the legs as the page lists them), and the
   page's own fixed texts (texts.ts T, the n/a and remark wording). Fails on any INTERNAL name (tests/page/plain-words.ts,
   the pattern refusals.test.ts uses), naming where it is. */
import { describe, expect, it } from 'vitest';
import type { CatalogResponse, CatalogPreset, LimitEntry, RowRemark } from '../../src/core/contract.ts';
import { CELL_REMARKS, NA_REASONS } from '../../src/core/contract.ts';
import ts from 'typescript';
import { METRICS_CATALOG, resolveCatalogParams } from '../../src/core/catalog.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { resolveScreenerParams, SBY_ID } from '../../src/core/registry.ts';
import { availabilityMap, presetAvailability, presetDefinitions } from '../../src/core/validate.ts';
import { entriesOf, optionText } from '../../src/entries.ts';
import { newCard } from '../../src/forms.ts';
import { ctx } from '../../src/state.ts';
import { cellRemarkText, chipNoBreak, chipTraded, errorText, methodText, naText, remarkTitle, T } from '../../src/texts.ts';
import { legNames } from '../../src/presets-ui.ts';
import { EDGE_BFF_LIMITS, REFRESH_CAPS, WORKER_LIMITS, WORKER_VALUES } from './limits.ts';
import { internalNames } from './plain-words.ts';

type Limits = typeof WORKER_VALUES;
interface WorkerCatalog {
  limitEntries(l: Limits): LimitEntry[];
  catalogDoc(c: Record<string, unknown>): { json: Uint8Array };
}
// the worker's module, imported by path so the page's type check does not compile the worker (it needs Node's types)
const WORKER_CATALOG = new URL('../../../../screener-worker/src/catalog.ts', import.meta.url).pathname;
const worker = await import(/* @vite-ignore */ WORKER_CATALOG) as WorkerCatalog;

/** the worker's values on dev (DEPLOY_RUNBOOK step "railway variable set": compute, admission, definition and answer
    limits; the file caps at the local run's sizes) */
const DEV: Limits = {
  max_cpu_ms: 4500, cap_budget_ms: 4500, deadline_ms: 20000, queue: 4, owner_inflight: 1, owner_cpu_ms: 30000, previous_grace_s: 600,
  max_conditions: 20, max_metric_filters: 8, within_max: 130, max_counts: 50, max_response_bytes: 4194304, max_request_bytes: 131072,
  max_file_bytes: 24000000, max_inflated_bytes: 150000000, max_refresh_bytes: 24000000,
};
const SMALLEST: Limits = Object.fromEntries(Object.keys(DEV).map(k => [k, 1])) as Limits;
const VERSIONS = { price_data: 'p'.repeat(64), registry: 'r'.repeat(16), screener_registry: 's'.repeat(16), screener_engine: 'e'.repeat(16) };
const DATA = { evaluation_date: '2026-10-28', price_through: '2026-10-28', flow_through: null, published_at: '2026-10-28T12:00:00Z' };

/** what the page shows, by where it shows it: [place, text] */
type Shown = [string, string | null | undefined];
const limitTexts = (where: string, ls: readonly LimitEntry[]): Shown[] =>
  ls.flatMap(l => (['unit', 'rule', 'example_ok', 'example_refused'] as const).map((k): Shown => [`${where} ${l.name}.${k}`, l[k]]));
/** the catalog GET /catalog answers on a publication with this xsection index, through the worker's own catalogDoc */
function catalogAt(index: Record<string, { columns?: string[] }>, limits: Limits = DEV): CatalogResponse {
  const availability = availabilityMap(index, METRICS_CATALOG);
  const presets: CatalogPreset[] = presetDefinitions().map(p => {
    const a = presetAvailability(p, availability, METRICS_CATALOG);
    return { id: p.id, category: p.category, name: p.name, why: p.why, definition: p.definition, ...(p.view ? { view: p.view } : {}),
      availability: a.availability, reason: a.reason, match_count: null, near_count: null, unavailable_legs: a.unavailable_legs };
  });
  const doc = worker.catalogDoc({ desc: { versions: VERSIONS, data: DATA }, refresh: 'ready', limits, metrics: METRICS_CATALOG, availability, groupings: [], presets });
  return JSON.parse(new TextDecoder().decode(doc.json)) as CatalogResponse;
}
/** every string the page shows from one catalog answer */
function shownIn(cat: CatalogResponse): Shown[] {
  const out: Shown[] = limitTexts('limit', cat.limits);
  const entries = entriesOf(cat);
  ctx.byKey = new Map(entries.map(e => [e.key, e]));
  for (const e of entries) {
    const w = `${e.kind} ${e.key}`;
    out.push([`${w} label`, e.label], [`${w} short`, e.short], [`${w} description`, e.desc], [`${w} reason`, e.reason], [`${w} history`, e.history]);
    for (const p of e.params) { out.push([`${w} parameter ${p.key} label`, p.label]); for (const o of p.options || []) out.push([`${w} parameter ${p.key} option`, optionText(p, o)]) }
    for (const o of e.opts) out.push([`${w} test ${o.key} label`, o.label], [`${w} test ${o.key} disabled reason`, o.disabled]);
  }
  for (const m of [...cat.metrics, ...cat.fundamentals]) out.push([`metric ${m.id} misuse`, m.misuse], [`metric ${m.id} interpretation`, m.interpretation]);
  for (const i of cat.indicators) {
    out.push([`indicator ${i.id} name`, i.name], [`indicator ${i.id} description`, i.description], [`indicator ${i.id} short`, i.short]);
    for (const o of i.outputs) { out.push([`indicator ${i.id} output ${o.key} label`, o.label]); for (const d of o.disabled_tests) out.push([`indicator ${i.id} output ${o.key} disabled`, d.reason]) }
  }
  for (const p of cat.presets) {
    out.push([`preset ${p.id} name`, p.name], [`preset ${p.id} why`, p.why], [`preset ${p.id} category`, p.category], [`preset ${p.id} reason`, p.reason]);
    for (const n of legNames(p)) out.push([`preset ${p.id} unavailable leg`, n]);
  }
  return out;
}
/** the price-source options of the registry's indicators (hl2, hlc3, ohlc4: the standard names the Terminal and the
    usual charting tools show for (H+L)/2, (H+L+C)/3 and (O+H+L+C)/4), words of the trade rather than of the code */
const SOURCE_TERMS = new Set(['hl2', 'hlc3', 'ohlc4']);
const offending = (shown: Shown[]) => shown.filter(([, s]) => s && !SOURCE_TERMS.has(s) && internalNames(s).length).map(([w, s]) => `${w}: ${internalNames(s!).join(', ')} in "${s}"`);

describe('the catalog a user reads is plain words', () => {
  it('the limits[] copy the page tests use is what the generators produce', () => {
    // the worker's part at the copy's values (refresh caps out); edge-bff's part is checked by test_screener.py
    expect(worker.limitEntries(WORKER_VALUES).filter(l => !REFRESH_CAPS.includes(l.name))).toEqual(WORKER_LIMITS);
    expect(EDGE_BFF_LIMITS.map(l => l.name)).toEqual(['saved_items', 'watchlist', 'saved_definition_bytes', 'request_bytes', 'inflight_per_page']);
  });
  it('every limit (Method & sources, every refusal of a limit): the worker\'s at the dev values and at 1, edge-bff\'s', () => {
    const dev = worker.limitEntries(DEV);
    expect(dev.length).toBe(15);
    expect(offending([...limitTexts('worker (dev)', dev), ...limitTexts('worker (all 1)', worker.limitEntries(SMALLEST)), ...limitTexts('edge-bff', EDGE_BFF_LIMITS)])).toEqual([]);
    // a refusal reads "this one needs N <unit>": a unit is a plural noun phrase, never a name
    for (const l of [...dev, ...EDGE_BFF_LIMITS]) expect(l.unit, l.name).toMatch(/^[a-z][a-z ]*$/);
  });
  it('on a Phase 1 publication (no cross-sectional file): metrics, fundamentals, indicators, presets and their reasons', () => {
    const cat = catalogAt({});
    const shown = shownIn(cat);
    expect(shown.length).toBeGreaterThan(1000);
    // the walk reaches what the page shows from the catalog: unavailable reasons, every preset, every indicator
    expect(shown.filter(([w, s]) => / reason$/.test(w) && s).length).toBeGreaterThan(70);
    expect(new Set(shown.filter(([w]) => w.startsWith('preset ')).map(([w]) => w.split(' ')[1])).size).toBe(presetDefinitions().length);
    expect(new Set(shown.filter(([w]) => w.startsWith('indicator ')).map(([w]) => w.split(' ')[1])).size).toBe(53);
    expect(offending(shown)).toEqual([]);
    // the cases that used to show a wire value: a pattern's "Line" options (indicator ids), Keltner's bands style, and
    // a preset's unavailable legs (condition ids, metric_filters[0])
    const line = shown.filter(([w]) => w === 'metric new_high parameter of option').map(([, s]) => s);
    expect(line).toEqual([...['I40', 'I41', 'I44', 'I50', 'I51'].map(id => cat.indicators.find(i => i.id === id)!.name), 'close', 'volume']);
    expect(shown.filter(([w]) => w === 'indicator I11 parameter bands_style option').map(([, s]) => s)).toEqual(['ATR', 'TR', 'HL range']);
    expect(legNames(cat.presets.find(p => p.id === 'magic')!)).toEqual(['condition 1 (Magic Formula rank)', 'universe filter 1 (Market cap)']);
    // the metrics' descriptions are their interpretation (entriesOf falls back to the formula only without one)
    for (const m of METRICS_CATALOG.metrics) expect(m.interpretation.trim(), m.id).not.toBe('');
  });
  it('on publications that carry the files, without some columns and complete: the reasons stay plain', () => {
    const files = [...new Set(METRICS_CATALOG.metrics.flatMap(m => m.requires ? [m.requires.file] : []))];
    const partial = Object.fromEntries(files.map(f => [f, { columns: ['d'] }]));
    const full = Object.fromEntries(files.map(f => [f, {}]));
    const reasons = (cat: CatalogResponse) => shownIn(cat).filter(([w]) => / reason$/.test(w));
    const p = reasons(catalogAt(partial));
    expect(p.some(([, s]) => /columns it needs (are|is) missing/.test(s || ''))).toBe(true);
    expect(offending(p)).toEqual([]);
    expect(offending(reasons(catalogAt(full)))).toEqual([]);
  });
  it("the page's own fixed words: T, the n/a and remark wording, the method text and the chips", () => {
    const remarks: RowRemark[] = [{ code: 'STALE', last_bar_date: '2026-10-20' },
      { code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: '2026-10-01', ratio_old: 1, ratio_new: 5, close_ratio: 0.2 }];
    const shown: Shown[] = [
      ...Object.entries(T).map(([k, v]): Shown => [`T.${k}`, v]),
      ...NA_REASONS.map((r): Shown => [`n/a ${r}`, naText(r)]), ['n/a of a future reason', naText('SOME_NEW_REASON')],
      ...remarks.map((r): Shown => [`remark ${r.code}`, remarkTitle(r)]),
      ...CELL_REMARKS.map((c): Shown => [`cell remark ${c}`, cellRemarkText(c, remarks)]),
      ['method', methodText('2026-10-28')], ['chip traded', chipTraded(null)], ['chip no break', chipNoBreak],
    ];
    expect(offending(shown)).toEqual([]);
  });
  it('the pattern catches each class the catalog used to show (so the walk above can fail)', () => {
    for (const s of ['wait for a source (P11)', 'use bandar (FL09)', 'waits for EXEC-MCAP', 'registry RVOL (I37) includes it', 'no value (NA INSUFFICIENT_HISTORY)',
      'market_board is the trading board', 'aligned to the ticker\'s dates (asOf)', 'between is value <= x <= value2', 'on a replica', 'preview a ticker of GET universe',
      'or stopped with TIMEOUT', '(BUSY: retry)', 'it defaults to Regular (D7)', 'row remark STALE', 'use fpct to compare stocks', 'combine with fstreak'])
      expect(internalNames(s), s).not.toEqual([]);
    for (const s of ['Market cap waits for its shares-outstanding data.', 'Relative Volume includes today', 'IHSG, LQ45, IDX30 and ADV20 over 20 sessions', 'P/E below 15', 'Phase 2',
      'the last close of a breakout', 'read it with Bandar balance', 'the bandar thresholds', 'its length cap', 'a payout below 85%'])
      expect(internalNames(s), s).toEqual([]);
  });
  it("a refusal of an option names the options as the card's select shows them, never their wire values", () => {
    // the core's own refusals of an option that is not offered (a saved screen or preset of an older catalog): a
    // pattern's "Line" (catalog.ts resolveCatalogParams) and an indicator's enum (registry.ts resolveScreenerParams)
    const entries = entriesOf(catalogAt({}));
    ctx.byKey = new Map(entries.map(e => [e.key, e]));
    const cards = [newCard(ctx.byKey.get('new_high')!, []), newCard(ctx.byKey.get('I11')!, ['x'])];
    const refusal = (f: () => unknown) => { try { f(); return null } catch (e) { return e as ScreenerError } };
    const line = refusal(() => resolveCatalogParams(METRICS_CATALOG.metrics.find(m => m.id === 'new_high')!.params, { of: 'I99.zzz' }, 'definition.conditions[0].test.pattern.params'))!;
    const style = refusal(() => resolveScreenerParams(SBY_ID.I11, { bands_style: 'RANGE' }, 'definition.conditions[1].test.metric.params', { capBudgetMs: 4500 }))!;
    expect([line.code, line.field, style.code, style.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.pattern.params.of', 'INVALID_CONDITION', 'definition.conditions[1].test.metric.params.bands_style']);
    const shown = (e: ScreenerError) => errorText(e.code, { field: e.field, details: e.details ?? null, server: e.message, cards, filters: [] });
    const obv = ctx.byKey.get('I40')!.label;
    expect(shown(line)).toContain(`use one of ${obv}, `);
    expect(shown(style)).toContain('use one of ATR, TR, HL range');
    expect(offending([['line refusal', shown(line)], ['bands style refusal', shown(style)]])).toEqual([]);
  });
  it("the page modules' own sentences (tooltips, notes, labels) name no decision, plan, flow or Feature id and no part of the service", () => {
    // every string and template literal of the page's modules (src/*.ts, src/api/*.ts; not src/core, whose user-visible
    // words are walked above) that holds a space, so a sentence rather than a key; icons.ts is SVG path data
    const sources = import.meta.glob(['../../src/*.ts', '../../src/api/*.ts', '!../../src/icons.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
    expect(Object.keys(sources).length).toBeGreaterThan(15);
    const NAMED = /\b(?:P|D|M|U|FL)\d+\b|\bF\d\d\b|\bEXEC-[A-Z]|\bTEMPORARY\b|\breplicas?\b|\bregistry\b|\bdata layer\b|\bworker\b|\bsnapshot\b|\bedge-bff\b/;
    const found: string[] = [];
    for (const [file, text] of Object.entries(sources)) {
      const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
      const visit = (n: ts.Node) => {
        if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) && n.text.includes(' ')) {
          const m = NAMED.exec(n.text);
          if (m) found.push(`${file.replace('../../', '')}:${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1}: ${m[0]} in "${n.text.slice(0, 120)}"`);
        }
        ts.forEachChild(n, visit);
      };
      visit(sf);
    }
    expect(found).toEqual([]);
  });
});
