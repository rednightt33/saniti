/* Production entry: the Screener page on the live ScreenerApi (edge-bff /api/v1/screener/*; report FRONTEND
   INTEGRATION 9.1). The page imports only the wire contract (core/contract.ts) from the screener core and no formula:
   screens, previews and counts are computed by screener-worker (tests/bundle checks the built file, report I1). */
import './styles/screener.css';
import '../../terminal/src/styles/spin.css';   // EXEC-BACKTEST-SPIN: the loading ring every rack page shares
import { bootPage } from './app.ts';
import { liveApi } from './api/live.ts';
import { exampleApi } from './api/example.ts';
import { KEYS, keepInMemory } from './storage.ts';
import { exampleMode, viewOnly } from '../../shared/example-view.ts';

// 3e, the example mode (user 2026-11-21; ERRORS M527): the shell opens the page with ?example=1 for a principal holding
// screener.example; the page then opens on the example's screen with its stored run, keeps nothing in the browser
// (its storage in memory, no file cache) and stays a view of that day
if (exampleMode()) {
  viewOnly({ source: 'screener', name: 'Screener' });
  const api = exampleApi();
  const nothing = { get: async () => null, put: async () => {} };
  api.screen().then(s => { keepInMemory({ [KEYS.last]: { name: s.name, definition: s.definition, preset: s.preset }, [KEYS.panel]: { preview: false } }) },
    () => keepInMemory({ [KEYS.panel]: { preview: false } }))      // no screen: the page's own error shows (the run asks again)
    .then(() => bootPage(api, { cache: nothing }));
} else bootPage(liveApi());
