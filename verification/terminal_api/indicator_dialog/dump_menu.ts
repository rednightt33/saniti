import { menuItems, unitText } from '../../../apps/edge-bff/terminal/src/app/indMenu';
import ind from '../../../apps/edge-bff/terminal/src/data/indRegistry.json';
import flow from '../../../apps/edge-bff/terminal/src/data/flowRegistry.json';
import { writeFileSync } from 'fs';
const items = menuItems(ind as any, flow as any);
const byId: Record<string, any> = {}; (ind as any[]).forEach(r => byId[r.id] = { params: (r.params || []).map((p: any) => [p.label, p.def]) });
(flow as any).indicators.forEach((r: any) => byId[r.id] = { params: (r.params || []).filter((p: any) => p.kind !== 'fixed').map((p: any) => {
  let v = p.default; if (Array.isArray(v)) v = v.length === (p.options || []).length ? 'All' : v.join(', ');
  if (p.options && !Array.isArray(p.default)) { const o = p.options.find((x: any) => Array.isArray(x) ? x[0] === v : x === v); if (Array.isArray(o)) v = o[1] }
  if (v === 'top3_net_buy_20') v = 'Top 3 net buyers'; if (typeof v === 'boolean') v = v ? 'On' : 'Off';
  return [p.label, v] }) });
const out = items.map(i => ({ ...i, unit: unitText(i.unit), params: (byId[i.id]?.params || []).filter((p: any) => p[1] !== undefined && p[1] !== '' && p[1] !== '-') }));
writeFileSync(process.argv[2], JSON.stringify({ items: out, families: (flow as any).families }));
console.log(out.length, out.slice(0, 2), out.find(o => o.id === 'FL23'));
