/* Production entry: the page on the live BacktestApi (edge-bff session, published market data, backtest jobs). */
import './styles/backtest.css';
import '../../terminal/src/styles/spin.css';   // EXEC-BACKTEST-SPIN: the loading ring every rack page shares
import { boot } from './app.ts';
import { liveApi } from './api/live.ts';

boot(liveApi());
