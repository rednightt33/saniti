/* datafile.ts on files in the publisher's format (tests/fake-terminal.mjs builds them as publisher.py does): the
   manifest check, the price and broker decoding against the Terminal's own reading code (edge-bff/terminal/src/data/
   worker.ts priceRows, brokerData), the strict checks on top of it, the corporate actions, asOf and data_version. */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { test } from 'node:test';
import zlib from 'node:zlib';
import {
  DataError, INDEX_TICKER, PRICE_ACTION_TYPES, asOf, brokerGaps, brokerRows, corporateActions, dataVersion, decodeColumnar, inflateVerified, priceSeries,
} from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { priceRows } from '../../edge-bff/terminal/src/data/worker.ts';
import { EVENT_COLUMNS, brokerArchive, brokerDoc, encode, eventsDoc, priceDoc, pricePack } from './fake-terminal.mjs';

const code = (c: string) => (e: unknown) => { assert.ok(e instanceof DataError, String(e)); assert.equal((e as DataError).code, c, (e as Error).message); return true };
const decode = async (doc: object): Promise<Columnar> => { const { body, sha256 } = encode(doc); return inflateVerified(new Uint8Array(body), { sha256, bytes: body.length }) };
const gz = (text: string) => new Uint8Array(zlib.gzipSync(Buffer.from(text)));
const entry = (b: Uint8Array) => ({ sha256: crypto.createHash('sha256').update(b).digest('hex'), bytes: b.length });

test('inflateVerified: a publisher file decodes; a size or sha256 mismatch, a body that is not gzip JSON, another schema_version or ragged columns are DATA_INTEGRITY', async () => {
  const doc = priceDoc('BBCA', 2026, [['2026-01-02', 105, 106, 101, 102, 900]]), { body, sha256 } = encode(doc), raw = new Uint8Array(body);
  assert.deepEqual(await inflateVerified(raw, { sha256, bytes: raw.length }), JSON.parse(JSON.stringify(doc)));
  await assert.rejects(inflateVerified(raw, { sha256, bytes: raw.length + 1 }), code('DATA_INTEGRITY'));
  await assert.rejects(inflateVerified(raw, { sha256: sha256.replace(/^./, c => c === '0' ? '1' : '0'), bytes: raw.length }), code('DATA_INTEGRITY'));
  const flipped = raw.slice(); flipped[raw.length - 9] ^= 1;                       // same size, other bytes
  await assert.rejects(inflateVerified(flipped, { sha256, bytes: raw.length }), code('DATA_INTEGRITY'));
  const plain = new TextEncoder().encode(JSON.stringify(doc));                       // not gzip, even with its own hash
  await assert.rejects(inflateVerified(plain, entry(plain)), code('DATA_INTEGRITY'));
  for (const text of ['{"columns":["d"],"d":[1', '[1,2]', '{"schema_version":2,"columns":["d"],"d":[]}', '{"columns":["d","o"],"d":[1,2],"o":[1]}', '{"columns":["d","o"],"d":[1]}', '{"d":[1]}']) {
    const b = gz(text);
    await assert.rejects(inflateVerified(b, entry(b)), code('DATA_INTEGRITY'), text);
  }
  assert.deepEqual(await decodeColumnar(gz('{"columns":["a"],"a":[]}')), { columns: ['a'], a: [] });   // no schema_version: accepted
});

/* the price pack and yearly files as the Terminal reads them, in any file order */
const BARS: [string, number | null, number | null, number | null, number | null, number | null][] = [
  ['2025-12-29', 100, 110, 95, 105, 1000], ['2025-12-30', 105, 107, 104, 106, 0],
  ['2026-01-02', 106, 109, 103, 108, 2000], ['2026-01-05', null, 109, 103, 108, 50], ['2026-01-06', 108, 112, 107, 111, 3000],
];
test('priceSeries gives the bars the Terminal draws (priceRows): files merged by date, rows without four prices dropped and counted', async () => {
  const docs = [await decode(priceDoc('BBCA', 2026, BARS.slice(2))), await decode(priceDoc('BBCA', 2025, BARS.slice(0, 2)))];
  const s = priceSeries('BBCA', docs), terminal = priceRows(docs);
  assert.deepEqual(s.dates, terminal.map(r => r.d));
  assert.deepEqual([s.bars.O, s.bars.H, s.bars.L, s.bars.C, s.bars.V], ['o', 'h', 'l', 'c', 'v'].map(k => terminal.map(r => (r as any)[k])));
  assert.equal(s.dropped, 1);
  assert.equal(s.bars.T, s.dates);
  assert.deepEqual(s.dates, ['2025-12-29', '2025-12-30', '2026-01-02', '2026-01-06']);
  const pack = priceSeries('BBCA', [await decode(pricePack('BBCA', BARS))]);
  assert.deepEqual(pack, s);                                                          // the pack equals its yearly files
});

test('priceSeries: an index keeps its null volume; the index is IHSG', async () => {
  const s = priceSeries(INDEX_TICKER, [await decode(pricePack(INDEX_TICKER, [['2026-01-02', 7000, 7100, 6950, 7050, null], ['2026-01-05', 7050, 7080, 7000, 7010, null]]))]);
  assert.deepEqual(s.bars.V, [null, null]);
  assert.equal(INDEX_TICKER, 'IHSG');
});

test('priceSeries: a date twice (in a file or across files), dates out of order, a bad date or volume, a missing column or another ticker are DATA_INTEGRITY; no bar is DATA_MISSING', async () => {
  const one = async (rows: typeof BARS, ticker = 'BBCA', year = 2026) => decode(priceDoc(ticker, year, rows));
  const noVolume = priceDoc('BBCA', 2026, [BARS[0]]) as any; noVolume.columns = ['d', 'o', 'h', 'l', 'c']; delete noVolume.v;
  const integrity: [string, Columnar[]][] = [
    ['a date twice in a file', [await one([BARS[2], BARS[2]])]],
    ['dates out of order in a file', [await one([BARS[4], BARS[2]])]],
    ['two files with a date in common', [await one(BARS.slice(0, 3)), await one(BARS.slice(2))]],
    ['not a date', [await one([['2026-02-30', 1, 1, 1, 1, 1]])]],
    ['a volume that is not a number', [await one([['2026-01-02', 1, 1, 1, 1, '5' as unknown as number]])]],
    ['no volume column', [noVolume]],
    ['a file of another ticker', [await one(BARS, 'BBRI')]],
    ['a broker file', [await decode(brokerDoc('BBCA', 2026, []))]],
  ];
  for (const [what, docs] of integrity) assert.throws(() => priceSeries('BBCA', docs), code('DATA_INTEGRITY'), what);
  assert.throws(() => priceSeries('BBCA', []), code('DATA_MISSING'));
  const noBar = await one([['2026-01-02', null, 1, 1, 1, 1]]);
  assert.throws(() => priceSeries('BBCA', [noBar]), code('DATA_MISSING'));
});

/* broker rows in the publisher's order (date, broker, investor, board), gap flag last */
const BROKER: [string, string, string, string, number, number, number, number, boolean][] = [
  ['2024-12-30', 'AK', 'Foreign', 'Regular', 500, 100, 5, 1, false], ['2024-12-30', 'YP', 'Domestic', 'Tunai', 0, 400, 0, 4, true],
  ['2025-01-02', 'AK', 'Domestic', 'Nego', 1000, 0, 10, 0, false], ['2025-01-02', 'AK', 'Foreign', 'Regular', 250.5, 50, 2.5, 0.5, false],
];
test('brokerRows reads the broker archive and the yearly files as one date-ordered list; brokerGaps reads the gap markers', async () => {
  const docs = [await decode(brokerDoc('BBCA', 2025, BROKER.slice(2))), await decode(brokerArchive('BBCA', BROKER.slice(0, 2), [2016, 2024]))];
  const rows = brokerRows(docs);
  assert.deepEqual(rows, BROKER.map(([d, b, i, m, bv, sv, bl, sl]) => ({ d, b, i, m, bv, sv, bl, sl })));
  assert.deepEqual(brokerGaps(docs), [{ d: '2024-12-30', m: 'Tunai' }]);
  assert.deepEqual(brokerRows([await decode(brokerDoc('BBCA', 2025, []))]), []);
});

test('brokerRows: a row twice (a stale archive overlapping a yearly file), dates out of order, values outside Feature 05 or files of two tickers are DATA_INTEGRITY', async () => {
  const doc = async (rows: typeof BROKER, ticker = 'BBCA', year: number | null = 2025) => decode(brokerDoc(ticker, year, rows));
  const overlap = [await doc(BROKER), await doc(BROKER.slice(3))], twice = [await doc([BROKER[3], BROKER[3]])], unsorted = [await doc([BROKER[2], BROKER[0]])];
  const twoTickers = [await doc(BROKER.slice(0, 1)), await doc(BROKER.slice(2), 'BBRI')], price = [await decode(priceDoc('BBCA', 2025, []))];
  for (const docs of [overlap, twice, unsorted, twoTickers, price]) assert.throws(() => brokerRows(docs), code('DATA_INTEGRITY'));
  for (const bad of [['2025-01-02', 'AK', 'FOREIGN', 'Regular'], ['2025-01-02', 'AK', 'Foreign', 'Cash'], ['2025-01-02', '', 'Foreign', 'Regular'], ['2025/01/02', 'AK', 'Foreign', 'Regular']])
    assert.throws(() => brokerRows([brokerDoc('BBCA', 2025, [[...bad, 1, 1, 1, 1, false] as any]) as unknown as Columnar]), code('DATA_INTEGRITY'), JSON.stringify(bad));
  for (const v of [-1, null, Infinity]) assert.throws(() => brokerRows([brokerDoc('BBCA', 2025, [['2025-01-02', 'AK', 'Foreign', 'Regular', v as number, 1, 1, 1, false]]) as unknown as Columnar]), code('DATA_INTEGRITY'));
  assert.throws(() => brokerGaps([{ ...brokerDoc('BBCA', 2025, []), gap: [['2025-01-02']] } as unknown as Columnar]), code('DATA_INTEGRITY'));
});

test('corporateActions keeps the price-affecting corporate actions of the events file (ex date), not dividends, meetings or insiders', async () => {
  const ev = (d: string, family: string, type: string, role = 'EX_DATE') => EVENT_COLUMNS.map(c => ({ d, role, family, type } as Record<string, unknown>)[c] ?? null);
  const doc = await decode(eventsDoc('BBCA', [
    ev('2021-03-01', 'CORPORATE_ACTION', 'DIVIDEND'), ev('2021-10-13', 'CORPORATE_ACTION', 'STOCK_SPLIT'), ev('2022-01-04', 'INSIDER', 'INSIDER_TRANSACTION', 'TRANSACTION_DATE'),
    ev('2022-05-10', 'CORPORATE_ACTION', 'RUPS', 'MEETING_DATE'), ev('2023-02-01', 'CORPORATE_ACTION', 'RIGHT_ISSUE'), ev('2023-06-01', 'CORPORATE_ACTION', 'BONUS_SHARE'),
    ev('2024-01-02', 'CORPORATE_ACTION', 'REVERSE_SPLIT'), ev('2024-02-02', 'CORPORATE_ACTION', 'STOCK_DIVIDEND'), ev('2024-03-01', 'CORPORATE_ACTION', 'WARRANT', 'TRADING_START'),
    ev('2024-04-01', 'CORPORATE_ACTION', 'TENDER_OFFER', 'OFFER_START'), ev('2024-05-01', 'CORPORATE_ACTION', 'PUBLIC_EXPOSE', 'EXPOSE_DATE'),
  ]));
  assert.deepEqual(corporateActions([doc]), [
    { date: '2021-10-13', type: 'STOCK_SPLIT' }, { date: '2023-02-01', type: 'RIGHT_ISSUE' }, { date: '2023-06-01', type: 'BONUS_SHARE' },
    { date: '2024-01-02', type: 'REVERSE_SPLIT' }, { date: '2024-02-02', type: 'STOCK_DIVIDEND' },
  ]);
  assert.deepEqual([...PRICE_ACTION_TYPES].sort(), ['BONUS_SHARE', 'REVERSE_SPLIT', 'RIGHT_ISSUE', 'STOCK_DIVIDEND', 'STOCK_SPLIT']);
  assert.deepEqual(corporateActions([]), []);
  const price = await decode(priceDoc('BBCA', 2025, []));
  assert.throws(() => corporateActions([price]), code('DATA_INTEGRITY'));
});

test('asOf: the last value on or before each calendar day, null before the first (the Terminal alignTo)', () => {
  const dates = ['2026-01-02', '2026-01-05', '2026-01-07'], values = [10, 11, 12];
  assert.deepEqual(asOf(dates, values, ['2025-12-31', '2026-01-02', '2026-01-03', '2026-01-05', '2026-01-06', '2026-01-07', '2026-02-01']), [null, 10, 10, 11, 11, 12, 12]);
  assert.deepEqual(asOf(dates, [1, null, 3], ['2026-01-06']), [null]);              // a null value is not skipped over
  assert.deepEqual(asOf([], [], ['2026-01-02']), [null]);
  assert.throws(() => asOf(dates, [1], dates), RangeError);
});

test('dataVersion: sha256 of the sorted distinct lines ticker \\t dataset \\t sha256, joined with a newline', async () => {
  const a = { ticker: 'BBCA', dataset: 'price', sha256: 'a'.repeat(64) }, b = { ticker: 'BBCA', dataset: 'broker', sha256: 'b'.repeat(64) }, c = { ticker: 'IHSG', dataset: 'price', sha256: 'c'.repeat(64) };
  const expect = crypto.createHash('sha256').update(`BBCA\tbroker\t${'b'.repeat(64)}\nBBCA\tprice\t${'a'.repeat(64)}\nIHSG\tprice\t${'c'.repeat(64)}`).digest('hex');
  assert.equal(await dataVersion([c, a, b]), expect);
  assert.equal(await dataVersion([a, b, c, a]), expect);
  await assert.rejects(dataVersion([{ ...a, ticker: 'BB\tCA' }]), TypeError);
});
