/* 3f (EXEC option A item 4; CONTRACT.md 8a "Lab code"; LIVE_PROMOTION.md section 3): the formulas of the items at the
   lab stage, registered into the shared formula maps before the page starts. Only the lab build reaches this module (the
   alias '@edge-lab'; the public build gets none.ts), and edge-bff serves the lab build only to the admin on the beta, so
   a lab formula is never in a file a visitor downloads (tests: shared/release-filter.mjs's proof builds, the bundle scan
   tests/test_3f_public_bundles.py).

   No item is at the lab stage today. A lab technical indicator's function goes here, keyed as its registry entry's `key`:

     import { F } from '../calc/indicators';
     F.my_key = (B, p) => ({ value: ... });

   Its registry entry goes into data/indRegistry.json with the item at stage "lab" in catalog/releases.json; the public
   build leaves the entry out. Releasing it moves the function into calc/indicators.ts (the workers' engine version
   follows). A lab Flow indicator needs a registration point in calc/flow.ts first (its map is not exported): not built
   (LIVE_PROMOTION.md section 3). */
export {};
