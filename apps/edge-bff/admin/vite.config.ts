import { defineConfig, type Plugin } from 'vite';
import { releaseFilter } from '../shared/release-filter.mjs';

/* As the Watchlist page (apps/edge-bff/watchlist/vite.config.ts): one classic IIFE script at the end of <body> (the
   sub-app CSP forbids inline scripts); base /admin-app/ (edge-bff serves it to the beta's admin only, the shell shows it
   in the /admin frame). --mode fixture -> tests/fixture/main.ts (made-up accounts and tickets in memory, for the look
   check only) into dist-fixture/; never part of dist/ (tests/bundle.test.mjs). */
function classicScriptAtEnd(): Plugin {
  return {
    name: 'admin-classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const tag = /\s*<script type="module" crossorigin src="([^"]+)"><\/script>/;
        const m = html.match(tag);
        if (!m) throw new Error('admin build: entry script tag not found');
        return html.replace(tag, '').replace('</body>', `  <script src="${m[1]}"></script>\n</body>`);
      }
    }
  };
}
const ENTRY: Record<string, string> = { fixture: '/tests/fixture/main.ts' };
function testEntry(mode: string): Plugin {
  return {
    name: 'admin-test-entry',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        const from = '<script type="module" src="/src/main.ts"></script>';
        if (html.split(from).length !== 2) throw new Error('admin build: production entry tag not found exactly once');
        return html.replace(from, `<script type="module" src="${ENTRY[mode]}"></script>`);
      }
    }
  };
}
export default defineConfig(({ mode }) => ({
  base: '/admin-app/',
  // 3f round 2 (CONTRACT.md 8 "Lab code"): every page build applies the release filter, so a registry this page comes to
  // import never carries an item at the lab stage (tests/test_3f_public_bundles.py builds every page with it)
  plugins: [releaseFilter({ lab: false }), ...(ENTRY[mode] ? [testEntry(mode)] : []), classicScriptAtEnd()],
  worker: { plugins: () => [releaseFilter({ lab: false })] },
  build: { outDir: ENTRY[mode] ? `dist-${mode}` : 'dist', emptyOutDir: true, assetsDir: 'assets', sourcemap: false, target: 'es2022',
           cssCodeSplit: false, rollupOptions: { output: { format: 'iife', inlineDynamicImports: true } } },
}));
