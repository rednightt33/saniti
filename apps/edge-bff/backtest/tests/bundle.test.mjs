/* The production bundle (dist/, `npm run build`) carries none of the reference's synthetic data generator or its demo
   engine (CONTRACT.md section 10): its seed, its Gaussian draw and its ticker table (names survive only unminified;
   the seed and the table's rows survive minification), and it links the EDGE icons (review finding (b)). Run after the
   build. */
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const MARKERS = [
  ['the generator seed', /20261025/],
  ['the generator Gaussian draw', /gauss/i],
  ['the generator ticker table', /\bTICKERS\b/],
  ['the generator ticker table rows', /\[["'`]BBCA["'`],\s*6200\b/],
];
async function files(dir) {
  const out = [];
  for (const e of await readdir(dir, { withFileTypes:true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...await files(p)); else if (/\.(js|html|css)$/.test(e.name)) out.push(p);
  }
  return out;
}

describe('production bundle', () => {
  it('is built (dist/index.html and one script)', async () => {
    const html = await readFile(join(DIST, 'index.html'), 'utf8').catch(() => { throw new Error('dist/ is missing: run `npm run build` first') });
    expect(html).toMatch(/<script src="\/backtest-app\/assets\/[^"]+\.js"><\/script>\s*<\/body>/);
  });
  it('links the EDGE icons, as EDGE\'s own page does (static/index.html), which edge-bff serves (app/main.py)', async () => {
    const html = await readFile(join(DIST, 'index.html'), 'utf8');
    const main = await readFile(fileURLToPath(new URL('../../app/main.py', import.meta.url)), 'utf8');
    for (const [href, type] of [['/favicon.svg', 'image/svg+xml'], ['/favicon-32.png', 'image/png']]) {
      expect(html).toContain(`<link rel="icon" href="${href}" type="${type}"`);
      expect(main).toContain(`@app.get('${href}')`);
      await readFile(fileURLToPath(new URL(`../../static${href}`, import.meta.url)));
    }
  });
  it.each(MARKERS)('has no trace of %s', async (_, re) => {
    for (const f of await files(DIST)) expect(re.test(await readFile(f, 'utf8')), `${f} matches ${re}`).toBe(false);
  });
});
