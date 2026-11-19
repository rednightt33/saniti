/* Track guest (EXEC-MU-ACCOUNTS, decision 1 of 2026-11-19: "user tetap bisa search ticker, tapi ketika dia klik ticker
   selain bbca maka akan keluar pop up box to login (jika belum login) dan jika sudah login maka akan keluar pop up box (to
   upgrade plan)"; verification/edge_multiuser/fix_round/guest.md): a ticker, an indicator or a feature the principal does
   not hold (MarketData.locks, read from the server's access and catalog in live.ts) opens a box. EDGE's shell draws it
   (static/edge-app.js LockedDialog: its words are static/edge-labels.js EdgeLabels.locked, its look the design system's
   dialog): it knows whether the visitor is signed in (sign in or register) or not (upgrade), so the Terminal only says
   what was asked. Opened alone, outside EDGE, the Terminal goes to EDGE's Terminal page, where the box is. */

export interface LockedItem { kind: 'ticker' | 'indicator' | 'flow_indicator' | 'feature'; id: string; name?: string }

export function askLocked(item: LockedItem) {
  const shell = window.parent !== window ? window.parent : null;
  if (shell) { shell.postMessage({ source:'terminal', type:'locked', kind:item.kind, id:item.id, name:item.name || item.id }, location.origin); return }
  location.href = '/terminal';
}

/** the word of the lock mark, from the shell's labels (the Terminal runs in EDGE's frame, same origin) */
export function lockWord(): string {
  try { const w = (window.parent as any)?.EdgeLabels?.locked?.mark; if (typeof w === 'string' && w) return w } catch { /* not EDGE's frame */ }
  return 'Locked';
}

/** the lock mark (an inline 12 px icon in the text's colour, the word as its name for screen readers and its tooltip) */
export const lockMark = (cls = 'tk-lock') => {
  const w = lockWord().replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
  return `<span class="${cls}" role="img" aria-label="${w}" title="${w}"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg></span>`;
};
