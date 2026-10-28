/* The production bundle (dist/, `npm run build`) is a thin client (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12,
   invariant I1): no formula code (the Terminal's indicators.ts, the Backtest core's registry and conditions, the
   screener core's evaluation modules, the generated registries) and no fixture code (the prototype's synthetic market,
   the fixture ScreenerApi), one classic IIFE script at the end of <body>, the EDGE icons linked. The markers are
   strings that survive minification; each is checked to be present in the fixture build (dist-fixture/, when built),
   so a marker that stops proving anything fails here. A second check reads the page's sources: the page imports
   from the screener core only contract.ts and universe.ts, and nothing from the Backtest core or the Terminal's calc.
   Run after `npm run build` (and `npm run build:fixture` for the marker self-check). */
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
const DIST = join(ROOT, 'dist'), FIXTURE = join(ROOT, 'dist-fixture');
const FORMULA = [
  ['the indicator module F (indicators.ts keys)', /ultimate_osc|bollinger_pctb|market_fi/],
  ['the backtest registry (backtest-registry.json)', /"F\.sma"|F\.sma/],
  ['the screener registry (screener-registry.json)', /probe_params/],
  ['the backtest core registry checks', /PARAM_NOT_ACCEPTED|is not an indicator of the registry/],
  ['the Klinger formula name', /Klinger/],
];
const FIXTURE_MARKERS = [
  ['the prototype ticker table', /BBCA\|Bank Central Asia/],
  ['the prototype seeded random (FNV offset)', /2166136261/],
  ['the prototype broker table', /Mirae Asset/],
  ['the fixture ScreenerApi storage', /scr\.fixture\./],
  ['the fixture failure injection', /fixture failure/],
];
async function files(dir) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes:true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...await files(p)); else if (/\.(js|html|css)$/.test(e.name)) out.push(p);
  }
  return out;
}
const text = async dir => (await Promise.all((await files(dir)).map(f => readFile(f, 'utf8')))).join('\n');
const built = async dir => { try { await readFile(join(dir, 'index.html')); return true } catch { return false } };

describe('production bundle', () => {
  it('is built: dist/index.html with one classic script at the end of <body>', async () => {
    const html = await readFile(join(DIST, 'index.html'), 'utf8').catch(() => { throw new Error('dist/ is missing: run `npm run build` first') });
    expect(html).toMatch(/<script src="\/screener-app\/assets\/[^"]+\.js"><\/script>\s*<\/body>/);
    expect(html).not.toMatch(/type="module"/);
    expect((html.match(/<script/g) || []).length).toBe(1);
    expect(html).toContain('data-boot="skeleton"');
  });
  it('links the EDGE icons that edge-bff serves', async () => {
    const html = await readFile(join(DIST, 'index.html'), 'utf8');
    for (const [href, type] of [['/favicon.svg', 'image/svg+xml'], ['/favicon-32.png', 'image/png']]) expect(html).toContain(`<link rel="icon" href="${href}" type="${type}"`);
  });
  it.each([...FORMULA, ...FIXTURE_MARKERS])('has no trace of %s', async (_, re) => {
    expect(re.test(await text(DIST))).toBe(false);
  });
  it.each([...FORMULA, ...FIXTURE_MARKERS])('marker self-check: the fixture build carries %s', async (_, re) => {
    if (!await built(FIXTURE)) return;                     // `npm run build:fixture` not run: the absence checks above stand
    expect(re.test(await text(FIXTURE))).toBe(true);
  });
});

describe('page sources', () => {
  it('import from the screener core only contract.ts and universe.ts, and no formula module', async () => {
    const src = join(ROOT, 'src'), bad = [];
    const walk = async dir => { for (const e of await readdir(dir, { withFileTypes:true })) { const p = join(dir, e.name); if (e.isDirectory()) { if (e.name !== 'core') await walk(p) } else if (/\.ts$/.test(e.name)) {
      const body = await readFile(p, 'utf8');
      for (const m of body.matchAll(/^\s*import\s+(type\s+)?[^'"]*?from\s+['"]([^'"]+)['"]/gm)) {
        const spec = m[2], typeOnly = !!m[1];
        if (/\/core\//.test(spec) && !/backtest\/src\/core\//.test(spec) && !/\/core\/(contract|universe)\.ts$/.test(spec)) bad.push(`${p}: ${spec}`);
        if (/backtest\/src\/core\//.test(spec) && !typeOnly) bad.push(`${p}: ${spec}`);
        if (/terminal\/src\/calc\//.test(spec)) bad.push(`${p}: ${spec}`);
        if (/tests\//.test(spec)) bad.push(`${p}: ${spec}`);
      }
    } } };
    await walk(src);
    expect(bad).toEqual([]);
  });
});
