import { defineConfig, type Plugin } from 'vite';
import { releaseFilter } from '../shared/release-filter.mjs';

/* As the Screener page (apps/edge-bff/screener/vite.config.ts): one classic IIFE script at the end of <body> (the sub-app
   CSP forbids inline scripts); base /overview-app/ (edge-bff serves it, the shell shows it in the Overview tab's frame).
   --mode fixture -> tests/fixture/main.ts (saved Overview files of a local rehearsal, for the look check only) into
   dist-fixture/; never part of dist/ (tests/bundle.test.ts). */
function classicScriptAtEnd(): Plugin {
  return {
    name: 'overview-classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const tag = /\s*<script type="module" crossorigin src="([^"]+)"><\/script>/;
        const m = html.match(tag);
        if (!m) throw new Error('overview build: entry script tag not found');
        return html.replace(tag, '').replace('</body>', `  <script src="${m[1]}"></script>\n</body>`);
      }
    }
  };
}
const ENTRY: Record<string, string> = { fixture: '/tests/fixture/main.ts' };
function testEntry(mode: string): Plugin {
  return {
    name: 'overview-test-entry',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        const from = '<script type="module" src="/src/main.ts"></script>';
        if (html.split(from).length !== 2) throw new Error('overview build: production entry tag not found exactly once');
        return html.replace(from, `<script type="module" src="${ENTRY[mode]}"></script>`);
      }
    }
  };
}
export default defineConfig(({ mode }) => ({
  base: '/overview-app/',
  // 3f (round 2 of its checker, 2026-11-21; CONTRACT.md 8 "Lab code"): every page build applies the release filter, a
  // Web Worker's bundle included, so a registry the page comes to import never carries an item at the lab stage
  // (tests/test_3f_public_bundles.py builds every page on a copy whose registries hold fixture items)
  plugins: [releaseFilter({ lab: false }), ...(ENTRY[mode] ? [testEntry(mode)] : []), classicScriptAtEnd()],
  worker: { plugins: () => [releaseFilter({ lab: false })] },
  build: { outDir: ENTRY[mode] ? `dist-${mode}` : 'dist', emptyOutDir: true, assetsDir: 'assets', sourcemap: false, target: 'es2022',
           cssCodeSplit: false, rollupOptions: { output: { format: 'iife', inlineDynamicImports: true } } },
}));
