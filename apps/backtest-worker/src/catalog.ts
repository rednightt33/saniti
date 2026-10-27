/* GET /v1/catalog (contract.ts Catalog): what the page may offer, built from what is published, never from a list kept
   here: the tickers of terminal-api's reference file (ticker, name, type, and the value of every other column as its
   groups; the publisher writes it from IDX_Stock_Universe, types stock and index; name null where the source has no
   company name), the groupings the portfolio picker filters by (groupingsOf: every column of that file other than
   ticker, name and type, PF6), the broker codes of the brokers reference file, IHSG's first and last published bar
   (its price files, checked against their manifest), the limits of the configuration, the versions, and whether the
   flow conditions are on (BACKTEST_FLOW_ENABLED, with the reason while they are off) with the date the broker data is
   published through (load.ts brokerDataThrough over every stock's manifest; asked only while flow is on). */
import type { Catalog, Grouping } from '../../edge-bff/backtest/src/core/contract.ts';
import { INDEX_TICKER } from '../../edge-bff/backtest/src/core/datafile.ts';
import { byTicker } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Config } from './config.ts';
import { brokerDataThrough } from './load.ts';
import type { Publication, TerminalClient, TickerReference } from './terminal.ts';
import { stocksOf } from './validate.ts';

/** The portfolio picker's filters (PF6, 2026-10-27): one per grouping column, in the file's column order; per value the
    number of published stocks that have it, in value order (byTicker), and the stocks without a value (unclassified:
    terminal.ts classification) counted apart, never as a value. An index is not tradable, so only stocks count. */
export function groupingsOf(ref: TickerReference): Grouping[] {
  const stocks = ref.tickers.filter(r => r.type === 'stock');
  return ref.groupings.map(key => {
    const counts = new Map<string, number>();
    let unclassified = 0;
    for (const r of stocks) {
      const v = r.groups[key];
      if (v === null) unclassified++;
      else counts.set(v, (counts.get(v) ?? 0) + 1);
    }
    return { key, values: [...counts.keys()].sort(byTicker).map(value => ({ value, tickers: counts.get(value) as number })), unclassified };
  });
}

/* EXEC-BACKTEST-LOAD (user 2026-10-27, K1, in place of D-L3's "the worker keeps no date"): `publication` is the run the
   files belong to (terminal-api /state). With it, the broker date is that run's (state.json broker_through: the newest
   Feature 05 date of the run, the date the run wrote into the manifests it touched), read once instead of every
   stock's manifest; without it, every stock's manifest as before. */
export async function buildCatalog(client: TerminalClient, cfg: Pick<Config, 'limits' | 'flow'> & { terminal: Pick<Config['terminal'], 'concurrency'> },
  versions: { engine_version: string; registry_version: string }, publication: Publication | null = null): Promise<Catalog> {
  const [ref, brokers, ihsg] = await Promise.all([client.reference('tickers'), client.reference('brokers'), client.loadTicker(INDEX_TICKER, ['price'])]);
  const flowThrough = !cfg.flow.enabled ? null
    : publication?.broker_through ?? await brokerDataThrough(client, stocksOf(ref.tickers), cfg.terminal.concurrency);
  const d = ihsg.prices!.dates;
  return {
    schema_version: 1, engine_version: versions.engine_version, registry_version: versions.registry_version,
    data_through: d[d.length - 1], first_date: d[0],
    tickers: ref.tickers.map(r => ({ ticker: r.ticker, name: r.name, type: r.type as string, groups: { ...r.groups } })),
    groupings: groupingsOf(ref),
    flow: { available: cfg.flow.enabled, reason: cfg.flow.reason, brokers: brokers.map(b => b.code), data_through: flowThrough },
    limits: cfg.limits,
  };
}

/** EXEC-BACKTEST-LOAD (user 2026-10-27: "Agar waktu loading bisa sama. Seperti bagian terminal."; K1): what is derived
    from the published files (the catalog, the reference lists) is kept until the publisher finishes another run
    (terminal-api /state finished_at), checked at most every `checkMs`; one build at a time, its callers share it.
    Without a publication (terminal-api cannot say) nothing is kept and every call builds, as before. */
export class ByPublication<T> {
  private value: T | null = null;
  private version: string | null = null;
  private checked = -Infinity;
  private building: Promise<T> | null = null;
  private readonly source: Pick<TerminalClient, 'publication'>;
  private readonly build: (p: Publication | null) => Promise<T>;
  private readonly checkMs: number;
  private readonly now: () => number;
  constructor(source: Pick<TerminalClient, 'publication'>, build: (p: Publication | null) => Promise<T>, checkMs = 60_000, now: () => number = Date.now) {
    this.source = source; this.build = build; this.checkMs = checkMs; this.now = now;
  }
  get(): Promise<T> {
    if (this.value !== null && this.now() - this.checked < this.checkMs) return Promise.resolve(this.value);
    return this.building ??= (async () => {
      const p = await this.source.publication();
      this.checked = this.now();
      if (p && this.value !== null && p.finished_at === this.version) return this.value;
      const v = await this.build(p);
      this.value = p ? v : null; this.version = p ? p.finished_at : null;
      return v;
    })().finally(() => { this.building = null });
  }
}
