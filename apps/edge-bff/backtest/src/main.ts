/* Production entry: the page on the live BacktestApi (edge-bff session, published market data, backtest jobs). */
// 3f (CONTRACT.md 8 "Lab code"): the lab formulas, registered before anything reads the formula maps; nothing in the
// public build (the Terminal's src/lab/none.ts), its src/lab/index.ts in the lab build edge-bff serves only to the admin
import '@edge-lab';
import './styles/backtest.css';
import '../../terminal/src/styles/spin.css';   // EXEC-BACKTEST-SPIN: the loading ring every rack page shares
import './styles/design.css';                  // Tahap D: the user's design file (decision 2a), over the page's own styles
import { boot } from './app.ts';
import { liveApi } from './api/live.ts';

boot(liveApi());
