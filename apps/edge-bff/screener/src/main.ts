/* EDGE Screener page entry (production build). PLACEHOLDER of the Phase 1 foundation (EXEC-SCREENER, go 2026-10-28):
   the page agent replaces it with the module-by-module port of the prototype (report FRONTEND INTEGRATION 9.1-9.2:
   state, universe-ui, presets-ui, builder, browser, results, preview, dialogs, storage, texts) over a ScreenerApi
   (src/api/types.ts, live.ts). The page imports only the wire contract (core/contract.ts) and the universe filter
   (core/universe.ts) from the core: no formula code reaches the browser (report I1, TEST PLAN 10b.12). */
import { SCHEMA_VERSION } from './core/contract.ts';

const root = document.getElementById('app');
if (root) root.textContent = `EDGE Screener (contract schema ${SCHEMA_VERSION}) is being built.`;
