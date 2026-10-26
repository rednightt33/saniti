/* GET /v1/catalog (contract.ts Catalog): what the page may offer, built from what is published, never from a list kept
   here: the tickers of terminal-api's reference file (ticker, name, type, sector; the publisher writes it from
   IDX_Stock_Universe, types stock and index; name null where the source has no company name), the universes (every
   published stock, and one per published sector, D-K6), the broker codes of the brokers reference file, IHSG's first
   and last published bar (its price files, checked against their manifest), the limits of the configuration, the
   versions, and whether the flow conditions are on (BACKTEST_FLOW_ENABLED, with the reason while they are off) with
   the date the broker data is published through (load.ts brokerDataThrough over every stock's manifest; asked only
   while flow is on). */
import type { Catalog } from '../../edge-bff/backtest/src/core/contract.ts';
import { INDEX_TICKER } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Config } from './config.ts';
import { brokerDataThrough } from './load.ts';
import type { TerminalClient } from './terminal.ts';
import { stocksOf, universes } from './validate.ts';

export async function buildCatalog(client: TerminalClient, cfg: Pick<Config, 'limits' | 'flow'> & { terminal: Pick<Config['terminal'], 'concurrency'> },
  versions: { engine_version: string; registry_version: string }): Promise<Catalog> {
  const [refs, brokers, ihsg] = await Promise.all([client.reference('tickers'), client.reference('brokers'), client.loadTicker(INDEX_TICKER, ['price'])]);
  const flowThrough = cfg.flow.enabled ? await brokerDataThrough(client, stocksOf(refs), cfg.terminal.concurrency) : null;
  const d = ihsg.prices!.dates;
  return {
    schema_version: 1, engine_version: versions.engine_version, registry_version: versions.registry_version,
    data_through: d[d.length - 1], first_date: d[0],
    tickers: refs.map(r => ({ ticker: r.ticker, name: r.name, type: r.type as string, sector: r.sector })),
    universes: universes(refs).map(u => ({ id: u.id, label: u.label, tickers: u.tickers.length })),
    flow: { available: cfg.flow.enabled, reason: cfg.flow.reason, brokers: brokers.map(b => b.code), data_through: flowThrough },
    limits: cfg.limits,
  };
}
