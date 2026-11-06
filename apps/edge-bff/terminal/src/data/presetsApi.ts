/* EXEC-IND-PRESETS (user 2026-11-06: "men-save indikator beserta dengan filternya"; "Q1 A" on the EDGE account): the
   owner's indicator presets on edge-bff (apps/edge-bff/app/presets.py, /api/v1/terminal/presets; table
   edge_bff.indicator_presets). The same session, CSRF and messages as the saved layouts (layoutsApi.savedClient). */
import { savedClient } from './layoutsApi';

export interface PresetConfig { params: Record<string, unknown>; style?: Record<string, unknown>; on?: boolean; fold?: boolean }
export interface Preset { preset_id: string; name: string; def_id: string; config: PresetConfig; summary: string; favorite: boolean;
  revision: number; created_at: string; updated_at: string; used_at: string }

const call = savedClient('/api/v1/terminal/presets', 'preset');
export const newPresetId = () => 'ipr_' + [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');
export const presetsApi = {
  list: () => call<{ presets: Preset[]; limit: number }>('GET', ''),
  put: (id: string, body: { name: string; def_id: string; config: PresetConfig; summary: string; revision?: number }) => call<Preset>('PUT', `/${id}`, body),
  mark: (id: string, body: { favorite?: boolean; used?: true }) => call<Preset>('PATCH', `/${id}`, body),
  remove: (id: string) => call<void>('DELETE', `/${id}`)
};
