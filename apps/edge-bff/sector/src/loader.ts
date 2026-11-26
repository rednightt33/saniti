/* EXEC-SECTOR-ANALYSIS S4: the order the page reads the sector files in (CONTRACT 5 "Downloads"): the index, then
   sector-meta and sector-series together, then the day file of the newest date of meta.dates that the index lists;
   sector-stocks-<index> is never read here (a card asks for it when it shows a sector's stocks). */
import { FILE, SectorError } from './api.ts';
import type { Day, Meta, SectorApi, SectorIndex, Series } from './types.ts';
import { W } from './words.ts';

/** the dates of the date picker: meta.dates (the 20 newest, oldest first) that have a day file in the index */
export const dayDates = (meta: Meta, index: SectorIndex) => meta.dates.filter(d => !!index.files[FILE.day(d)]);
/** the stock file of a sector, by its index ticker (CONTRACT 3.4 as amended: lowercased), or null */
export const stocksFile = (meta: Meta, sector: string) => { const ix = meta.sectors.find(s => s.name === sector)?.index; return ix ? FILE.stocks(ix) : null };

export interface Opened { index: SectorIndex; meta: Meta; series: Series; day: Day | null }
export async function open(api: SectorApi, date?: string): Promise<Opened> {
  const index = await api.index();
  const need = <T>(name: string): Promise<T> => {
    const e = index.files?.[name];
    if (!e) return Promise.reject(new SectorError('SECTOR_FILE_NOT_PUBLISHED', W.err.notPublished, 404));
    return api.file<T>(name, e.sha256);
  };
  const [meta, series] = await Promise.all([need<Meta>(FILE.meta), need<Series>(FILE.series)]);
  const ds = dayDates(meta, index);
  if (!ds.length) return { index, meta, series, day: null };
  const day = await need<Day>(FILE.day(date && ds.includes(date) ? date : ds[ds.length - 1]));
  return { index, meta, series, day };
}
