/* Fixture build entry (vite build --mode fixture). PLACEHOLDER of the Phase 1 foundation: the page agent boots the page
   modules here with the fixture ScreenerApi that keeps the prototype's synthetic data, for the 1:1 visual check only
   (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12). Never part of the production bundle (vite.config.ts). */
import { SCHEMA_VERSION } from '../../src/core/contract.ts';

const root = document.getElementById('app');
if (root) root.textContent = `EDGE Screener fixture build (contract schema ${SCHEMA_VERSION}).`;
