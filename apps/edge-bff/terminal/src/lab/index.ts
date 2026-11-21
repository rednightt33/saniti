/* 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"; LIVE_PROMOTION.md section 3): the formulas of the items at the
   lab stage, registered into the shared formula maps before the page starts. Only the lab build reaches this module (the
   alias '@edge-lab'; the public build gets none.ts), and edge-bff serves the lab build only to the admin on the beta, so
   a lab formula is never in a file a visitor downloads (tests: shared/release-filter.mjs's proof builds, the bundle scan
   tests/test_3f_public_bundles.py).

   No item may be at the lab stage yet: tests/test_releases.py LAB_ITEM_HELD_UNTIL names what must be closed first (the
   registry generators and both workers must load this module too). Once it is, a lab technical indicator's function
   goes here, keyed as its registry entry's `key`:

     import { F } from '../calc/indicators';
     F.my_key = (B, p) => ({ value: ... });

   Its registry entry goes into data/indRegistry.json with the item at stage "lab" in catalog/releases.json; the public
   build leaves the entry out. Releasing it moves the function into calc/indicators.ts. A lab Flow indicator needs a
   registration point in calc/flow.ts first (its map is not exported), reached from main.ts: not built
   (LIVE_PROMOTION.md section 3). */
export {};
