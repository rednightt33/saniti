/* FIXTURE ONLY (never in the production bundle; tests/bundle checks it): the reference file `stock_lists`
   (EXEC-SCREENER-STOCK-LISTS) over the fixture's synthetic market, deterministic. The indices follow the prototype's
   sample index flags of data.ts LISTINGS (LQ45, IDX30, IDX80, ISSI; not market data) plus IHSG, whose members include
   IHSG itself (not a stock) and a ticker outside the universe; the groups are sample groups of fixture tickers, one
   stock in several of them (TOWR: DJARUM and SARATOGA; ASII: ASTRA and four indices), SALIM partly outside the
   universe (LSIP, IMAS) and CT-CORP wholly outside it (no stock counted). The definitions are short sample texts in the
   source's language. The worker's own stocklists.ts turns them into the catalog block and the rows' memberships, so the
   page meets what production computes. */
import { LISTINGS } from './data.ts';
import type { StockListDoc, StockListsRef } from '../../../../screener-worker/src/stocklists.ts';

const AS_OF = '2026-10-23T13:31:48.255552+00:00';
const flagged = (k: 'LQ45' | 'IDX30' | 'IDX80' | 'ISSI') => LISTINGS.filter((L: any) => L.idx[k]).map((L: any) => L.tk as string).sort();
const index = (id: number, code: string, definition: string, members: string[]): StockListDoc =>
  ({ key: `INDEX:${id}`, kind: 'INDEX', code, name: code, definition, as_of: AS_OF, members });
const group = (id: number, code: string, name: string, members: string[]): StockListDoc =>
  ({ key: `KONGLO:${id}`, kind: 'KONGLO', code, name, definition: `Grup usaha versi Stockbit (contoh fixture): emiten yang dikaitkan dengan ${name}; bukan bukti kepemilikan atau kendali.`, as_of: AS_OF, members: [...members].sort() });

/** the lists in the publisher's order (indices, then groups, each in the source's order) */
export const FIXTURE_LISTS: StockListDoc[] = [
  index(467, 'IHSG', 'Indeks Harga Saham Gabungan: seluruh saham tercatat (contoh fixture).', ['IHSG', 'XOUT', ...LISTINGS.map((L: any) => L.tk as string)].sort()),
  index(550, 'LQ45', '45 saham likuid dengan kapitalisasi besar (contoh fixture).', flagged('LQ45')),
  index(555, 'IDX30', '30 saham likuid dan berkapitalisasi besar (contoh fixture).', flagged('IDX30')),
  index(560, 'IDX80', '80 saham likuid (contoh fixture).', flagged('IDX80')),
  index(565, 'ISSI', 'Indeks Saham Syariah Indonesia (contoh fixture).', flagged('ISSI')),
  group(9, 'SALIM', 'Salim', ['ICBP', 'INDF', 'SIMP', 'LSIP', 'IMAS']),
  group(59, 'DJARUM', 'Djarum', ['BBCA', 'TOWR']),
  group(61, 'ASTRA', 'Astra', ['ASII', 'UNTR', 'AALI', 'AUTO']),
  group(62, 'SINARMAS', 'Sinarmas', ['INKP', 'TKIM']),
  group(63, 'SARATOGA', 'Saratoga', ['SRTG', 'ADRO', 'MDKA', 'TBIG', 'TOWR']),
  group(64, 'EMTEK', 'Emtek', ['EMTK', 'BUKA', 'SCMA']),
  group(65, 'CT-CORP', 'CT Corp', ['MEGA', 'BBHI']),
];
/** the file as the worker's refresh hands it to the build (its sha256 is a fixed sample) */
export const FIXTURE_STOCK_LISTS: StockListsRef = { sha256: 'f1'.repeat(32), lists: FIXTURE_LISTS };
