import { defineConfig, type Plugin } from 'vite';

/* As the Screener page (apps/edge-bff/screener/vite.config.ts): one classic IIFE script at the end of <body> (the sub-app
   CSP forbids inline scripts); base /watchlist-app/ (edge-bff serves it, the shell shows it in the Watchlist tab's frame).
   --mode fixture -> tests/fixture/main.ts (a small made-up file and an in-memory list store, for the look check only) into
   dist-fixture/; never part of dist/ (tests/bundle.test.ts). */
function classicScriptAtEnd(): Plugin {
  return {
    name: 'watchlist-classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const tag = /\s*<script type="module" crossorigin src="([^"]+)"><\/script>/;
        const m = html.match(tag);
        if (!m) throw new Error('watchlist build: entry script tag not found');
        return html.replace(tag, '').replace('</body>', `  <script src="${m[1]}"></script>\n</body>`);
      }
    }
  };
}
const ENTRY: Record<string, string> = { fixture: '/tests/fixture/main.ts' };
function testEntry(mode: string): Plugin {
  return {
    name: 'watchlist-test-entry',
    transformIndexHtml: {
      order: 'pre',
      handler(html) {
        const from = '<script type="module" src="/src/main.ts"></script>';
        if (html.split(from).length !== 2) throw new Error('watchlist build: production entry tag not found exactly once');
        return html.replace(from, `<script type="module" src="${ENTRY[mode]}"></script>`);
      }
    }
  };
}
export default defineConfig(({ mode }) => ({
  base: '/watchlist-app/',
  plugins: [...(ENTRY[mode] ? [testEntry(mode)] : []), classicScriptAtEnd()],
  build: { outDir: ENTRY[mode] ? `dist-${mode}` : 'dist', emptyOutDir: true, assetsDir: 'assets', sourcemap: false, target: 'es2022',
           cssCodeSplit: false, rollupOptions: { output: { format: 'iife', inlineDynamicImports: true } } },
}));
