/* 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"; LIVE_PROMOTION.md section 3): the formulas of the items at the
   lab stage, registered into the shared formula maps before the page starts. Only the lab build reaches this module (the
   alias '@edge-lab'; the public build gets none.ts), and edge-bff serves the lab build only to the admin on the beta, so
   a lab formula is never in a file a visitor downloads (tests: shared/release-filter.mjs's proof builds, the bundle scan
   tests/test_3f_public_bundles.py). The workers, their compute threads and the registry generators register it too
   (apps/backtest-worker/loader/resolve.mjs and register.mjs).

   A lab technical indicator (INDICATOR_BETA_TO_LIVE.md, Part A; the user lifted the lab item guard on 2026-11-23):
   its defaults and its function go here, keyed as its registry entry's `key`, built with the same wrapper as the
   released ones (the first lab indicator exports `def`, `srcOf`, `SRC` and `Seg` from calc/indicators.ts):

     import { DEFAULTS, F, def, SRC, srcOf } from '../calc/indicators';
     DEFAULTS.my_key = { length: 20, source: 'close' };
     F.my_key = def('my_key', ['out'], SRC, (B, p) => ({ out: ... }));

   Its registry entry goes into data/indRegistry.json with the item at stage "lab" in catalog/releases.json; the public
   build leaves the entry out. Releasing it moves both lines into calc/indicators.ts (Part B).

   A lab Flow indicator (INDICATOR_BETA_TO_LIVE.md, "A lab Flow indicator"; built 2026-11-23, step 3 of the user's
   sequence): its registry entry comes from the spreadsheet (scripts/build_flow_registry.py) with the item at stage "lab";
   its formula goes here, registered under its id with the building blocks the released ones use:

     import { flowKit as K, registerFlow } from '../calc/flow';
     registerFlow('<its FL id>', (c, p) => ({ value: K.each(c.rows, K.W(p, 20), (a, t) => ...) }));

   registerFlow refuses an id that already has a formula. Releasing it (or putting it at preview) moves the formula into
   calc/flow.ts FLOW (terminal/tests/calc/public_formulas.test.ts and calc/flow.test.ts "registry" compute every entry
   of the public build). */

// Nothing is at the lab stage since 2026-11-26: I54-I60 were released to calc/indicators.ts (INDICATOR_BETA_TO_LIVE.md Part B).
export {};
