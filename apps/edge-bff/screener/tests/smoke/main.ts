/* Smoke build entry (vite build --mode smoke). PLACEHOLDER of the Phase 1 foundation: the page agent boots the page
   modules here with a stub ScreenerApi whose answers arrive late (the loading-state smoke run, ERRORS M253; report
   TEST PLAN 10b.12). Never part of the production bundle (vite.config.ts). */
import { SCHEMA_VERSION } from '../../src/core/contract.ts';

const root = document.getElementById('app');
if (root) root.textContent = `EDGE Screener smoke build (contract schema ${SCHEMA_VERSION}).`;
