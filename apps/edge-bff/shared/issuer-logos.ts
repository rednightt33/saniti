/* The Terminal's issuer logos for the EDGE pages that show a stock (the Watchlist since EXEC-WATCHLIST L5; the Radar since
   EXEC-RADAR-VIEW, the user 2026-11-28: "tambahin asset logo ya disini"). One list for every page: the Terminal's reference
   file (GET /api/terminal/v1/reference/logos answers a presigned URL on the bucket, so a page reading it needs the
   Terminal's connect-src) and the images from /api/terminal/v1/logo/<T> on this origin. A stock without a logo, or whose
   image fails, shows its first letter (the page's monogram).

   The list is read at most every LOGO_HOURS per browser (each read of a reference file counts against the terminal
   account's quota, as the Terminal's); a per-viewer convenience, so a blocked storage only costs one more read. Its key is
   the Watchlist's (registered in shared/edge-session.ts STORAGE), shared by the pages so one read serves all of them. */
export const LOGO_KEY = 'edge.watchlist.logos';
const LOGO_HOURS = 12;
const enc = encodeURIComponent;

/** ticker → a short version of its logo (the image URL carries it, so a new logo is a new URL); {} when unreadable */
export async function readIssuerLogos(reference: () => Promise<{ url: string; sha256: string | null }>): Promise<Record<string, string>> {
  try {
    const c = JSON.parse(localStorage.getItem(LOGO_KEY) || 'null');
    if (c && typeof c.at === 'number' && Date.now() - c.at < LOGO_HOURS * 3600e3 && c.map && typeof c.map === 'object') return c.map;
  } catch { /* storage off or unreadable: read the list */ }
  const ref = await reference();
  const r = await fetch(ref.url);
  if (!r.ok) throw new Error('logos');
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (ref.sha256 && crypto?.subtle) {
    const got = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
    if (got !== ref.sha256) throw new Error('logos');                // not the announced file: monograms
  }
  const text = bytes[0] === 0x1f && bytes[1] === 0x8b
    ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()
    : new TextDecoder().decode(bytes);
  const doc = JSON.parse(text);
  const map: Record<string, string> = {};
  (doc.ticker || []).forEach((t: string, i: number) => { if (doc.sha256?.[i]) map[t] = String(doc.sha256[i]).slice(0, 12) });
  try { localStorage.setItem(LOGO_KEY, JSON.stringify({ at: Date.now(), map })) } catch { /* storage off */ }
  return map;
}

/** the image URL of a ticker's logo at a version */
export const issuerLogoSrc = (ticker: string, version: string) => `/api/terminal/v1/logo/${enc(ticker)}?v=${enc(version)}`;
