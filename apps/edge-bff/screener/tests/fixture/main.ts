/* Fixture build entry (vite build --mode fixture): the production page modules on the fixture ScreenerApi, the
   prototype's synthetic market, for the visual check only (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12). Never
   part of the production bundle (vite.config.ts; tests/bundle). */
import '../../src/styles/screener.css';
import '../../../terminal/src/styles/spin.css';
import { bootPage } from '../../src/app.ts';
import { fixtureApi } from './api.ts';

const api = fixtureApi();
(window as any).__fixture = api;
bootPage(api);
