/* EXEC-IND-PRESETS (user 2026-11-06: "men-save indikator beserta dengan filternya ... Mungkin bisa di-save di bagian
   indicators"; "Q1 A" on the EDGE account, "Q2 A" the full version): named presets of one indicator with its parameters,
   filters and style, added again from the Indicators window on any ticker.

   A preset is a template: changing the indicator on the chart does not change it; "Update from chart" or saving under the
   same name (after a question) does. A parameter the indicator no longer has goes back to its default when the preset is
   added (indicators.ts addPreset, the saved chart's rule); a preset of an indicator the Terminal no longer has, or that this
   ticker cannot draw, says so instead of adding. */
import type { Ctx } from './context';
import { presetsApi, newPresetId, type Preset, type PresetConfig } from '../data/presetsApi';
import { LayoutApiError } from '../data/layoutsApi';
import { askName, confirmBox, say } from '../ui/dialogs';

export interface PresetsSurface {
  list: () => Preset[]; error: () => string; loading: () => boolean; refresh: () => Promise<void>;
  add: (p: Preset) => void; star: (p: Preset) => Promise<void>; rename: (p: Preset) => Promise<void>;
  update: (p: Preset) => Promise<void>; remove: (p: Preset) => Promise<void>;
  /** the preset's indicator: its name, or null when the Terminal no longer has it */
  defName: (p: Preset) => string | null;
  onChange: (() => void) | null;
}

export function initPresets(ctx: Ctx): PresetsSurface | null {
  if (ctx.M.mode !== 'live') return null;
  const { Ind } = ctx;
  let list: Preset[] = [], error = '', loading = false;
  const changed = () => S.onChange?.();
  const refresh = async () => {
    loading = true; changed();
    try { list = (await presetsApi.list()).presets; error = '' } catch (e: any) { error = e?.message || 'Saved presets could not be read.' }
    finally { loading = false; changed() }
  };
  const fail = (e: any, what: string) => say(e?.message || what, true);

  /* save the chart's indicator as a preset: a new name, or the name of one already saved (asked first) */
  Ind.savePreset = async ({ defId, title, config }) => {
    await refresh();
    const name = await askName('Save as preset', title.slice(0, 120), async n => {
      const same = list.find(p => p.name === n);
      if (same) {
        if (!(await confirmBox(`Replace the preset “${n}” with this indicator and its filters?`, 'Replace'))) throw new Error('Choose another name, or Replace.');
        await presetsApi.put(same.preset_id, { name:n, def_id:defId, config:config as PresetConfig, summary:title.slice(0, 300), revision:same.revision });
      } else await presetsApi.put(newPresetId(), { name:n, def_id:defId, config:config as PresetConfig, summary:title.slice(0, 300) });
    });
    if (name) { say(`Saved preset “${name}”`); await refresh() }
  };

  const S: PresetsSurface = {
    list: () => list, error: () => error, loading: () => loading, refresh, onChange: null,
    defName: p => Ind.defName?.(p.def_id) ?? null,
    add: p => {
      const nm = S.defName(p);
      if (!nm) { say(`“${p.name}” is no longer available: its indicator was removed from the Terminal.`, true); return }
      const inst = Ind.addPreset?.(p.def_id, p.config, p.preset_id);
      if (!inst) { say(`“${p.name}” cannot be drawn on this ticker (${nm} needs data this ticker does not have).`, true); return }
      say(`${p.name} added`);
      presetsApi.mark(p.preset_id, { used:true }).then(r => { Object.assign(p, r) }).catch(() => {});
    },
    star: async p => {
      try { Object.assign(p, await presetsApi.mark(p.preset_id, { favorite:!p.favorite })); list.sort((a, b) => Number(b.favorite) - Number(a.favorite) || (a.used_at < b.used_at ? 1 : -1)); changed() }
      catch (e) { if (e instanceof LayoutApiError && e.status === 404) await refresh(); fail(e, 'The star could not be changed. Try again in a minute.') }
    },
    rename: async p => {
      const name = await askName('Rename preset', p.name, async n => { Object.assign(p, await presetsApi.put(p.preset_id, { name:n, def_id:p.def_id, config:p.config, summary:p.summary, revision:p.revision })) }, 'Rename');
      if (name) { say(`Renamed to “${name}”`); changed() }
    },
    update: async p => {
      const on = Ind.onChartOf?.(p.def_id) || [], from = on.find(x => x.presetId === p.preset_id) || on[on.length - 1];
      const nm = S.defName(p) || p.def_id;
      if (!from) { say(`Add ${nm} to the chart and set its filters first, then choose Update from chart.`, true); return }
      if (!(await confirmBox(`Update “${p.name}” with the filters of ${from.title} on the chart?`, 'Update', false))) return;
      try { Object.assign(p, await presetsApi.put(p.preset_id, { name:p.name, def_id:p.def_id, config:from.config, summary:from.title.slice(0, 300), revision:p.revision })); say(`Updated “${p.name}”`); changed() }
      catch (e) { if (e instanceof LayoutApiError && (e.status === 404 || e.status === 409)) await refresh(); fail(e, 'The preset could not be updated. Try again in a minute.') }
    },
    remove: async p => {
      if (!(await confirmBox(`Delete the preset “${p.name}”? Indicators already on the chart stay.`, 'Delete'))) return;
      try { await presetsApi.remove(p.preset_id); list = list.filter(x => x !== p); say('Preset deleted'); changed() }
      catch (e) { if (e instanceof LayoutApiError && e.status === 404) await refresh(); fail(e, 'The preset could not be deleted. Try again in a minute.') }
    }
  };
  return S;
}
