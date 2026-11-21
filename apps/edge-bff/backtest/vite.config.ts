import { defineConfig, type Plugin } from 'vite';
import { labAlias, releaseFilter } from '../shared/release-filter.mjs';

/* The reference (backtest.html) runs its script as a classic script at the end of <body>, while the page is still
   being parsed (after the head's style sheet). A module script runs later and meets the web font at another moment
   (the Terminal's 1:1 check moved its opening view by one bar for that reason), so the build is one IIFE file loaded at
   the same place, the same way (as apps/edge-bff/terminal/vite.config.ts). */
function classicScriptAtEnd(): Plugin {
  return {
    name: 'backtest-classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const tag = /\s*<script type="module" crossorigin src="([^"]+)"><\/script>/;
        const m = html.match(tag);
        if (!m) throw new Error('backtest build: entry script tag not found');
        return html.replace(tag, '').replace('</body>', `  <script src="${m[1]}"></script>\n</body>`);
      }
    }
  };
}

/* One page, three builds (CONTRACT.md section 10): the production page (src/main.ts: session, edge-bff and the shared
   core) into dist/, and two test builds that boot the same page modules with another BacktestApi (src/api/types.ts):
   --mode smoke  -> tests/smoke/main.ts   (a tiny generated stub, for the Playwright smoke run)  into dist-smoke/
   --mode fixture -> tests/fixture/main.ts (the reference's synthetic data and mock-up engine, for the 1:1 check)
                                                                                                    into dist-fixture/
   The test entries are never part of dist/; tests/bundle.test.mjs checks that the production bundle carries none of
   the reference generator's markers. */
const ENTRY: Record<string, string> = { smoke: '/tests/smoke/main.ts', fixture: '/tests/fixture/main.ts' };

function testEntry(mode: string): Plugin {
  return {
    name: 'backtest-test-entry',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        const from = '<script type="module" src="/src/main.ts"></script>';
        if (html.split(from).length !== 2) throw new Error('backtest build: production entry tag not found exactly once');
        return html.replace(from, `<script type="module" src="${ENTRY[mode]}"></script>`);
      }
    }
  };
}

/* Served by edge-bff at /backtest-app/ (CONTRACT.md section 10; the EDGE tab "Backtest" shows it in an iframe).
   3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): the production page is built twice by `npm run build`. dist/
   keeps only the released items of the registries (shared/release-filter.mjs) and has no lab formula ('@edge-lab' is
   the Terminal's src/lab/none.ts); --mode lab keeps every item and the lab formulas, into dist-lab/, which edge-bff
   serves at /backtest-app/lab/ only to the admin on the beta. The test builds are public builds. */
/** The build's configuration; `extra`, `labModule` and `outDir` are for the proof builds of the tests only (the
    Terminal's tests/lab/: a fixture lab item that never enters the release file). */
export function backtestConfig(mode: string, { extra = {}, labModule = undefined as string | undefined, outDir = '',
                                              releases = undefined as string | undefined } = {}) {
  const lab = mode === 'lab';
  const filter = () => releaseFilter({ lab, extra, ...(releases ? { releases } : {}) });
  return {
    base: lab ? '/backtest-app/lab/' : '/backtest-app/',
    plugins: [filter(), ...(ENTRY[mode] ? [testEntry(mode)] : []), classicScriptAtEnd()],
    // the load worker's bundle takes only these (checker L1): the same filter
    worker: { plugins: () => [filter()] },
    resolve: { alias: labAlias({ lab, module: labModule }) },
    build: { outDir: outDir || (ENTRY[mode] || lab ? `dist-${mode}` : 'dist'), emptyOutDir: true, assetsDir: 'assets', sourcemap: false,
             target: 'es2022', cssCodeSplit: false, rollupOptions: { output: { format: 'iife' as const, inlineDynamicImports: true } } },
  };
}

export default defineConfig(({ mode }) => backtestConfig(mode));
