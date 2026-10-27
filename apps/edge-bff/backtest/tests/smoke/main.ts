/* Smoke build entry (vite build --mode smoke): the page modules on the tiny stub BacktestApi of stub.ts; ?hostile=1
   gives the market with markup in its strings, ?flow=1 the market with flow available, ?wide=1 the market with eight
   more stocks that every preview and run leaves out and one without price files (stub.ts stubApi). */
import '../../src/styles/backtest.css';
import { boot } from '../../src/app.ts';
import { stubApi } from './stub.ts';

const q = new URLSearchParams(location.search);
boot(stubApi({ hostile: q.get('hostile') === '1', flow: q.get('flow') === '1', wide: q.get('wide') === '1' }));
