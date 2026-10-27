/* Fixture build entry (vite build --mode fixture -> dist-fixture/): the page modules on the reference's synthetic data
   and mock-up engine (api.ts). /backtest-app/?fixture=reference starts the way the reference does, with one run at
   load (its last statement, run(false)); without the parameter the page starts like production ("Not run yet"). The
   portfolio's picked stocks at load are the reference's "Demo 10", its default universe (PF7). */
import '../../src/styles/backtest.css';
import { boot } from '../../src/app.ts';
import { fixtureApi } from './api.ts';
import { DEMO_10 } from './state.ts';

boot(fixtureApi(), { autorun: new URLSearchParams(location.search).get('fixture') === 'reference', portfolio: DEMO_10 });
