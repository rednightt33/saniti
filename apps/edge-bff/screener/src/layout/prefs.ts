/* EXEC-SCREENER-V21 layout: what the three-panel layout remembers per browser (pane widths, collapsed panes, the
   folded filter bar, the Indicators window's place and size, popover sizes, column order) and the hooks the page's
   renderers call so the layout follows a re-render without observing the document. Everything is a convenience kept
   through storage.ts `store` (try/catch: a blocked storage only loses it). */
import { store } from '../storage.ts';

/** wide layout: three panes with draggable borders (the reference switches at 900 px; below it the page stacks) */
export const wide = () => innerWidth > 900;

export const LKEYS = { panes:'scr.panes', win:'scr.ibwin', pops:'scr.popsize', order:'scr.colorder' } as const;

export interface PanePrefs { lw: number | null; rw: number | null; lcol: boolean; ucol: boolean }
export const panes: PanePrefs = { lw:null, rw:null, lcol:false, ucol:false, ...sanePanes(store.get<Partial<PanePrefs>>(LKEYS.panes, {})) };
function sanePanes(p: Partial<PanePrefs>): Partial<PanePrefs> {
  const n = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : null;
  return { lw:n(p.lw), rw:n(p.rw), lcol:p.lcol === true, ucol:p.ucol === true };
}
export const savePanes = () => store.set(LKEYS.panes, panes);

/** Re-render hooks: the page's renderers call these at their end; the layout modules fill them (layout/index.ts). */
export const layoutHooks = {
  /** after the builder card is drawn (rails count, condition rows) */
  afterConds: () => {},
  /** after the table is drawn (pinned columns, order, density, header editor, chart pane auto pick) */
  afterResults: () => {},
  /** after the filter bar is drawn (rail, summary line) */
  afterUniverse: () => {},
  /** after the preview pane is drawn (rail label, Stock vs IHSG hover) */
  afterDetails: () => {},
  /** the builder's header toggle on a wide screen: collapse the pane to its rail; false when not handled */
  collapseBuilder: (): boolean => false,
  /** open the More filters dialog at a group (quick filters); false when not handled */
  openFiltersAt: (_group: string): boolean => false,
};
