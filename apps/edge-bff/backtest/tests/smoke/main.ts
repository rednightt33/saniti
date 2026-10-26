/* Smoke build entry (vite build --mode smoke): the page modules on the tiny stub BacktestApi of stub.ts. */
import '../../src/styles/backtest.css';
import { boot } from '../../src/app.ts';
import { stubApi } from './stub.ts';

boot(stubApi());
