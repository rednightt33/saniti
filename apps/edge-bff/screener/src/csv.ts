/* CSV export (report 9.6): a client-side file named <screen-name-slug>-<evaluation_date>.csv; the visible rows in the
   current sort (search and near toggle applied, every page); metadata header lines; per condition its value, status,
   event date and bars ago (and the NA reason or the cell remark); text cells that begin with =, +, - or @ get an
   apostrophe (spreadsheet formula injection); numbers are written as numbers. Pure: no DOM. */
import type { Cell, RunResponse } from './core/contract.ts';
import type { Row } from './state.ts';
import { remarkCsv } from './texts.ts';

export interface CsvCondition { id: string; text: string }
export interface CsvMeta {
  name: string; evaluation_date: string | null; published_at: string | null; price_data_version: string | null;
  registry_version: string | null; screener_registry_version: string | null; definition_hash: string | null;
}

/** one CSV field: numbers as numbers, text quoted, formula-looking text prefixed with an apostrophe */
export function field(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : '';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  let s = String(v);
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) || s !== s.trim() ? `"${s.replace(/"/g, '""')}"` : s;
}
export const line = (cells: unknown[]) => cells.map(field).join(',');

const cellStatus = (c: Cell | undefined) => c ? c.status : '';
const cellValue = (c: Cell | undefined) => c == null ? null : c.value ?? c.lhs ?? null;
const cellNote = (c: Cell | undefined) => !c ? '' : c.status === 'na' ? c.reason || '' : c.remark || '';

export function csvText(rows: Row[], conds: CsvCondition[], meta: CsvMeta): string {
  const out: string[] = [];
  out.push(line(['# Screen', meta.name]));
  out.push(line(['# evaluation_date', meta.evaluation_date]));
  out.push(line(['# published_at', meta.published_at]));
  out.push(line(['# price_data_version', meta.price_data_version]));
  out.push(line(['# registry_version', meta.registry_version]));
  out.push(line(['# screener_registry_version', meta.screener_registry_version]));
  out.push(line(['# definition_hash', meta.definition_hash]));
  out.push(line(['# market cap', 'not available']));
  const head = ['Symbol', 'Name', 'Sector', 'Industry', 'Last', '1D %', 'Avg value 20D (Rp B)', 'Status', 'Met (m/n)', 'Remark'];
  for (const c of conds) head.push(`${c.text} · value`, `${c.text} · status`, `${c.text} · event date`, `${c.text} · bars ago`, `${c.text} · NA reason or remark`);
  out.push(line(head));
  for (const r of rows) {
    const cells: unknown[] = [r.ticker, r.name, r.sector, r.industry, r.last, r.chg_1d_pct, r.adv20_idr == null ? null : Math.round(r.adv20_idr / 1e7) / 100,
      r.status === 'universe' ? 'in universe' : r.status === 'match' ? 'match' : 'near miss', conds.length ? `${r.met}/${conds.length}` : '', remarkCsv(r.remarks)];
    for (const c of conds) {
      const x = r.cells.find(y => y.id === c.id);
      cells.push(cellValue(x), cellStatus(x), x?.event_date ?? null, x?.bars_ago ?? null, cellNote(x));
    }
    out.push(line(cells));
  }
  return out.join('\n') + '\n';
}
export const metaOf = (name: string, run: RunResponse | null, fallback: { evaluation_date: string | null; published_at: string | null; versions: Partial<RunResponse['versions']> | null }): CsvMeta => ({
  name, evaluation_date:run?.data.evaluation_date ?? fallback.evaluation_date, published_at:run?.data.published_at ?? fallback.published_at,
  price_data_version:run?.versions.price_data ?? fallback.versions?.price_data ?? null, registry_version:run?.versions.registry ?? fallback.versions?.registry ?? null,
  screener_registry_version:run?.versions.screener_registry ?? fallback.versions?.screener_registry ?? null, definition_hash:run?.versions.definition_hash ?? null,
});
