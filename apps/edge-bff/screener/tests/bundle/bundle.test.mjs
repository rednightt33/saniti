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
    for (const [href, type] of [['/favicon.svg', 'image/svg+xml'], ['/favicon-32.png', 'image/png']]) expect(html).toMatch(new RegExp(`<link rel="icon" href="${href.replace(/[.+]/g, '\\$&')}(\\?v=\\d{8})?" type="${type.replace(/[.+]/g, '\\$&')}"`));   // the version: EXEC-FAVICON-SQUARE 2026-11-03
  });
  it.each([...FORMULA, ...FIXTURE_MARKERS])('has no trace of %s', async (_, re) => {
    expect(re.test(await text(DIST))).toBe(false);
  });
  it.each([...FORMULA, ...FIXTURE_MARKERS])('marker self-check: the fixture build carries %s', async (_, re) => {
    if (!await built(FIXTURE)) return;                     // `npm run build:fixture` not run: the absence checks above stand
    expect(re.test(await text(FIXTURE))).toBe(true);
  });
});

/* EXEC-SCREENER-V21 (BRIEF_COMMON section 2 and 4): the design reference (three-panel v21) drives its page through
   global hooks, document-wide MutationObservers and polling intervals on a fixture build; none of that may reach the
   production page, which runs under the sub-app CSP (script-src 'self': no inline script, no inline handler, no eval). */
const REFERENCE_HOOKS = [
  ['a global window.__ hook (the reference window.__scr / __gate, the fixture window.__fixture)', /window\.__|__scr\b|__gate\b|__fixture\b/],
  ['a MutationObserver (the reference watches the whole document)', /MutationObserver/],
  ['a polling setInterval', /setInterval/],
  ['eval or new Function (forbidden by the CSP)', /\beval\(|new Function\b|\bFunction\(\s*["'`]/],
  ['document.write', /document\.write/],
];
describe('production bundle (EXEC-SCREENER-V21)', () => {
  it.each(REFERENCE_HOOKS)('has no %s', async (_, re) => {
    const js = (await files(DIST)).filter(f => f.endsWith('.js'));
    expect(js.length).toBe(1);
    expect(re.test(await readFile(js[0], 'utf8'))).toBe(false);
  });
  it('index.html is CSP-compatible: one external classic script, no inline script, no inline event handler, no javascript: URL', async () => {
    const html = await readFile(join(DIST, 'index.html'), 'utf8');
    const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
    expect(scripts.length).toBe(1);
    expect(scripts[0][1]).toMatch(/^\s*src="\/screener-app\/assets\/[^"]+\.js"\s*$/);
    expect(scripts[0][2].trim()).toBe('');
    expect(html).not.toMatch(/\son[a-z]+\s*=/i);
    expect(html).not.toMatch(/javascript:/i);
    // the v21 slots the Screen now controls are drawn into, and the page's three panes
    for (const id of ['pageActs', 'screenBar', 'pendBar', 'cardU', 'cardC', 'cardR', 'preview', 'colPop', 'naPop']) expect(html).toContain(`id="${id}"`);
  });
  it('the CSS is one linked file under the base path; no @import of another origin', async () => {
    const html = await readFile(join(DIST, 'index.html'), 'utf8');
    expect((html.match(/<link rel="stylesheet"[^>]*href="\/screener-app\/assets\/[^"]+\.css"/g) || []).length).toBe(1);
    const css = (await files(DIST)).filter(f => f.endsWith('.css'));
    for (const f of css) expect(await readFile(f, 'utf8')).not.toMatch(/@import\s+url\(\s*["']?https?:/);
  });
});
describe('page sources (EXEC-SCREENER-V21)', () => {
  it('no window.__ hook, MutationObserver, setInterval, eval or new Function in the page modules', async () => {
    const src = join(ROOT, 'src'), bad = [];
    const walk = async dir => { for (const e of await readdir(dir, { withFileTypes:true })) { const p = join(dir, e.name); if (e.isDirectory()) await walk(p); else if (/\.ts$/.test(e.name)) {
      const body = (await readFile(p, 'utf8')).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
      for (const [what, re] of REFERENCE_HOOKS) if (re.test(body)) bad.push(`${p}: ${what}`);
    } } };
    await walk(src);
    expect(bad).toEqual([]);
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
