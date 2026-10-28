import { defineConfig, type Plugin } from 'vite';

/* The prototype (screener EDGE layout.html) runs its script as a classic script at the end of <body>, while the page is
   still being parsed, and the Terminal and Backtest pages are built the same way for that reason (a module script runs
   later and meets the web font at another moment; apps/edge-bff/backtest/vite.config.ts). The build is one IIFE file
   loaded at the same place (report FRONTEND INTEGRATION 9.1; the sub-app CSP forbids inline scripts,
   apps/edge-bff/app/main.py). */
function classicScriptAtEnd(): Plugin {
  return {
    name: 'screener-classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const tag = /\s*<script type="module" crossorigin src="([^"]+)"><\/script>/;
        const m = html.match(tag);
        if (!m) throw new Error('screener build: entry script tag not found');
        return html.replace(tag, '').replace('</body>', `  <script src="${m[1]}"></script>\n</body>`);
      }
    }
  };
}

/* One page, three builds (the Backtest precedent, apps/edge-bff/backtest/CONTRACT.md section 10): the production page
   (src/main.ts: session, edge-bff /api/v1/screener/* and the wire contract only, no formula code) into dist/, and two
   test builds that boot the same page modules with another ScreenerApi (src/api/types.ts):
   --mode smoke   -> tests/smoke/main.ts   (a stub with late answers, for the loading-state smoke run, ERRORS M253)  into dist-smoke/
   --mode fixture -> tests/fixture/main.ts (the prototype's synthetic data, for the 1:1 visual check only)            into dist-fixture/
   The test entries are never part of dist/; the bundle test checks that the production bundle carries no formula
   (indicators.ts, conditions.ts) and no fixture code (report TEST PLAN 10b.12). */
const ENTRY: Record<string, string> = { smoke: '/tests/smoke/main.ts', fixture: '/tests/fixture/main.ts' };

function testEntry(mode: string): Plugin {
  return {
    name: 'screener-test-entry',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        const from = '<script type="module" src="/src/main.ts"></script>';
        if (html.split(from).length !== 2) throw new Error('screener build: production entry tag not found exactly once');
        return html.replace(from, `<script type="module" src="${ENTRY[mode]}"></script>`);
      }
    }
  };
}

// Served by edge-bff at /screener-app/ (the EDGE tab "Screener" shows it in an iframe at /screener; report 9.1, 9.7).
export default defineConfig(({ mode }) => ({
  base: '/screener-app/',
  plugins: [...(ENTRY[mode] ? [testEntry(mode)] : []), classicScriptAtEnd()],
  build: { outDir: ENTRY[mode] ? `dist-${mode}` : 'dist', emptyOutDir: true, assetsDir: 'assets', sourcemap: false, target: 'es2022',
           cssCodeSplit: false, rollupOptions: { output: { format: 'iife', inlineDynamicImports: true } } },
}));
