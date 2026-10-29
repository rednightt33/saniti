/* Production entry: the Screener page on the live ScreenerApi (edge-bff /api/v1/screener/*; report FRONTEND
   INTEGRATION 9.1). The page imports only the wire contract (core/contract.ts) from the screener core and no formula:
   screens, previews and counts are computed by screener-worker (tests/bundle checks the built file, report I1). */
import './styles/screener.css';
import '../../terminal/src/styles/spin.css';   // EXEC-BACKTEST-SPIN: the loading ring every rack page shares
import { bootPage } from './app.ts';
import { liveApi } from './api/live.ts';

bootPage(liveApi());
