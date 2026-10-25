import { defineConfig, type Plugin } from 'vite';

/* The reference page inlines lightweight-charts-drawing 0.6.2 with one change: its accent colour "#1e53e5" is "#171717"
   (selection handles and default ink follow the terminal's black). The same one-constant patch is applied to the npm
   build here; the build fails if the constant is not found exactly once (a library upgrade must be re-checked). */
function drawingInk(): Plugin {
  const from = 'const Eo = "#1e53e5";', to = 'const Eo = "#171717";';
  return {
    name: 'terminal-drawing-ink',
    transform(code, id) {
      if (!/lightweight-charts-drawing[\\/]dist[\\/]lightweight-charts-drawing\.es\.js$/.test(id)) return null;
      if (code.split(from).length !== 2) throw new Error('lightweight-charts-drawing: accent constant not found exactly once');
      return { code: code.replace(from, to), map: null };
    }
  };
}

/* The reference runs its script as a classic script at the end of <body>, while the page is still being parsed (after
   the head's style sheets). A module script runs later, and the chart then meets the web font at another moment: the
   opening view moved by one bar in the 1:1 check. The build is one IIFE file loaded at the same place, the same way. */
function classicScriptAtEnd(): Plugin {
  return {
    name: 'terminal-classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const tag = /\s*<script type="module" crossorigin src="([^"]+)"><\/script>/;
        const m = html.match(tag);
        if (!m) throw new Error('terminal build: entry script tag not found');
        return html.replace(tag, '').replace('</body>', `  <script src="${m[1]}"></script>\n</body>`);
      }
    }
  };
}

// Built into ../static/terminal-app and served by edge-bff at /terminal-app/ (FRONTEND_ARCHITECTURE.md section 2).
export default defineConfig({
  base: '/terminal-app/',
  plugins: [drawingInk(), classicScriptAtEnd()],
  optimizeDeps: { exclude: ['lightweight-charts-drawing'] },
  build: { outDir: '../static/terminal-app', emptyOutDir: true, assetsDir: 'assets', sourcemap: false, target: 'es2022', cssCodeSplit: false,
           rollupOptions: { output: { format: 'iife', inlineDynamicImports: true } } },
});
