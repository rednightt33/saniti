/* EXEC-MU-ACCOUNTS 3e, the example mode (ERRORS M527): the Screener example's run, the node part of the capture job
   (capture_job.py screener_extra runs it before its READ ONLY build): terminal-api's publication for the screener-worker,
   cut at the example's date, served to the worker itself by the fake terminal, and the worker's catalog, universe and run
   of the example's preset for the context given (apps/screener-worker/tests/example-capture.ts). Writes the answer as
   JSON to the file named; prints counts and dates only (no value of the data).

   node --experimental-strip-types --no-warnings=ExperimentalWarning --import ../backtest-worker/loader/register.mjs \
     <this file> <spec.json> <out.json>          (from apps/screener-worker, so its loader resolves the worker's imports)
   spec.json: {"as_of": "2026-10-30", "preset": "brk52", "context": {"allow": {...}, "rights": []}}
   environment: TERMINAL_URL and TERMINAL_PROXY_KEY (terminal-api, the screener-worker's), and every limit of
   apps/screener-worker/src/config.ts as the screener-worker has it (the keys, the URL and the file origin are the fake's) */
import fs from 'node:fs';
import { cutPublication, readPublication, screenOn } from '../../../apps/screener-worker/tests/example-capture.ts';
import { setLogSink } from '../../../apps/screener-worker/src/log.ts';

declare const process: { argv: string[]; env: Record<string, string | undefined>; stdout: { write(s: string): boolean } };
const out = (o: Record<string, unknown>) => process.stdout.write('OUT ' + JSON.stringify(o) + '\n');

// the worker's own log: its refresh summary and any failure, as OUT lines (counts, sizes, dates and reasons: no data value)
setLogSink(line => {
  let e: Record<string, unknown>;
  try { e = JSON.parse(line) } catch { return }
  if (e.event === 'refresh' || e.level === 'error' || String(e.event).toLowerCase().includes('fail'))
    out({ step: 'worker_log', event: e.event, level: e.level, tickers: e.tickers, stocks: e.stocks, bars: e.bars, no_price: e.no_price,
          broker_days: e.broker_days, reason: e.reason ?? e.error, catalog_bytes: e.catalog_bytes, ms: e.ms, rss: e.rss });
});
const [specPath, outPath] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const env = Object.fromEntries(Object.entries(process.env).filter(([k, v]) => k.startsWith('SCREENER_') && v !== undefined)) as Record<string, string>;
const full = await readPublication(process.env.TERMINAL_URL!, process.env.TERMINAL_PROXY_KEY!);
out({ step: 'screener_read', price_through: full.price_through, broker_through: full.broker_through,
      tickers: Object.keys(full.prices).length, rows: Object.values(full.prices).reduce((n, r) => n + r.length, 0),
      actions: full.actions.length, broker_days: Object.keys(full.broker ?? {}).length, ref: full.ref.length, ref_columns: full.refColumns });
const cut = cutPublication(full, spec.as_of);
const after = full.actions.filter(r => (r[1] as string) > spec.as_of);
out({ step: 'screener_cut', tickers: Object.keys(cut.prices).length, rows: Object.values(cut.prices).reduce((n, r) => n + r.length, 0),
      actions: cut.actions.length, broker_days: Object.keys(cut.broker ?? {}).length, broker_through: cut.broker_through, ref: cut.ref.length,
      // the share-basis question: actions dated after the example's date, by type (their tickers' earlier prices are the
      // publication's, as the Backtest's chart: ERRORS M527)
      actions_after: Object.entries(after.reduce((m: Record<string, number>, r) => { m[r[2] as string] = (m[r[2] as string] ?? 0) + 1; return m }, {})),
      tickers_with_actions_after: new Set(after.map(r => r[0])).size });
const example = await screenOn(cut, env, spec.preset, spec.context);
fs.writeFileSync(outPath, JSON.stringify(example));
out({ step: 'screener_run', evaluation_date: example.run?.data?.evaluation_date, match_count: example.run?.match_count,
      near_count: example.run?.near_count, rows: example.run?.rows?.length,
      rows_by_status: (example.run?.rows ?? []).reduce((m: Record<string, number>, r: { status?: string }) => { m[String(r.status)] = (m[String(r.status)] ?? 0) + 1; return m }, {}),
      presets: example.catalog?.presets?.length, universe: example.universe?.rows?.length,
      // every preset's own counts on the date (the worker's catalog): ids and counts only
      preset_counts: (example.catalog?.presets ?? []).map((x: { id: string; match_count?: number | null; near_count?: number | null }) => [x.id, x.match_count ?? null, x.near_count ?? null]) });
