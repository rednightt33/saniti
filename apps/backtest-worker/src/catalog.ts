/* GET /v1/catalog (contract.ts Catalog): what the page may offer, built from what is published, never from a list kept
   here: the tickers of terminal-api's reference file (ticker, name, type, sector; the publisher writes it from
   IDX_Stock_Universe, types stock and index), the universes (every published stock, and one per published sector,
   D-K6), the broker codes of the brokers reference file, IHSG's first and last published bar (its price files,
   checked against their manifest), the limits of the configuration, the versions, and whether the flow conditions
   are on (BACKTEST_FLOW_ENABLED, with the reason while they are off). */
import type { Catalog } from '../../edge-bff/backtest/src/core/contract.ts';
import { INDEX_TICKER } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Config } from './config.ts';
import type { TerminalClient } from './terminal.ts';
import { universes } from './validate.ts';

export async function buildCatalog(client: TerminalClient, cfg: Pick<Config, 'limits' | 'flow'>, versions: { engine_version: string; registry_version: string }): Promise<Catalog> {
  const [refs, brokers, ihsg] = await Promise.all([client.reference('tickers'), client.reference('brokers'), client.loadTicker(INDEX_TICKER, ['price'])]);
  const d = ihsg.prices!.dates;
  return {
    schema_version: 1, engine_version: versions.engine_version, registry_version: versions.registry_version,
    data_through: d[d.length - 1], first_date: d[0],
    // name as published; the reference file may hold null where the source has no company name
    tickers: refs.map(r => ({ ticker: r.ticker, name: r.name as string, type: r.type as string, sector: r.sector })),
    universes: universes(refs).map(u => ({ id: u.id, label: u.label, tickers: u.tickers.length })),
    flow: { available: cfg.flow.enabled, reason: cfg.flow.reason, brokers: brokers.map(b => b.code) },
    limits: cfg.limits,
  };
}
