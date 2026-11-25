-- EXEC-PRICE-DISTORTION F4 (UD46, the user 2026-11-24: "B", "masukan exec ya"; ERRORS M561): both hiding chips of the
-- Screener's universe are switched off once in every saved screen. Since EXEC-PRICE-DISTORTION a stale stock and a stock
-- with a detected price distortion are shown with a badge (the user 2026-11-24: "value harus tetap ditampilkan as is
-- dengan badge"), and the chips are off unless the user switches them on (contract.ts UNIVERSE_DEFAULTS); a screen saved
-- before holds them as explicit true values and would keep hiding those stocks.
-- Data only: no table, column, role or grant of edge_bff.screener_items changes. The universe object of every row it
-- changes is kept first in a backup table (R7), so the change can be undone (rollback block at the end). A row whose
-- chips are both false or absent is left as it is. The row's revision goes up by one (a page holding the old revision
-- reloads instead of writing the old chips back: 409 REVISION_CONFLICT); updated_at stays (the user did not change it).
-- definition_hash stays as saved: it is the worker's hash of the definition when it was saved (SavedItem, informational:
-- the page's counts cache key and the CSV's fallback; nothing compares it with the definition), refreshed at the next
-- save; the worker validates every saved screen again under the new registry versions on load (app/screener.py reviewed).
-- My metrics (kind metric) have no universe of their own (app/screener.py METRIC_UNIVERSE) and are not touched.
-- Forward-only; a rerun refuses (the backup table exists).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'screener_items') THEN
        RAISE EXCEPTION 'edge_bff.screener_items is missing: apply 20261028_001 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff'
               AND table_name = 'screener_items_chips_backup_20261125') THEN
        RAISE EXCEPTION 'edge_bff.screener_items_chips_backup_20261125 exists: this migration was applied already';
    END IF;
END $preflight$;

-- The universe object of every saved screen with either chip on, as it was before this migration.
CREATE TABLE edge_bff.screener_items_chips_backup_20261125 (
    item_id text PRIMARY KEY,
    owner_key text NOT NULL,
    universe jsonb NOT NULL CHECK (jsonb_typeof(universe) = 'object'),
    revision bigint NOT NULL,
    backed_up_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
REVOKE ALL ON edge_bff.screener_items_chips_backup_20261125 FROM PUBLIC;
COMMENT ON TABLE edge_bff.screener_items_chips_backup_20261125 IS 'EXEC-PRICE-DISTORTION F4 (UD46): the universe of each saved screen whose hiding chips (traded_on_eval_date, exclude_price_breaks) migration 20261125_001 switched off, as it was before; for undoing it only. No service reads it.';

INSERT INTO edge_bff.screener_items_chips_backup_20261125 (item_id, owner_key, universe, revision)
SELECT item_id, owner_key, definition #> '{definition,universe}', revision
FROM edge_bff.screener_items
WHERE kind = 'screen'
  AND jsonb_typeof(definition #> '{definition,universe}') = 'object'
  AND ((definition #> '{definition,universe,traded_on_eval_date}') = 'true'::jsonb
       OR (definition #> '{definition,universe,exclude_price_breaks}') = 'true'::jsonb);

UPDATE edge_bff.screener_items s
SET definition = jsonb_set(jsonb_set(s.definition, '{definition,universe,traded_on_eval_date}', 'false'::jsonb),
                           '{definition,universe,exclude_price_breaks}', 'false'::jsonb),
    revision = s.revision + 1
FROM edge_bff.screener_items_chips_backup_20261125 b
WHERE s.item_id = b.item_id;

DO $check$
DECLARE
    left_on bigint;
    backed bigint;
    changed bigint;
BEGIN
    SELECT count(*) INTO left_on FROM edge_bff.screener_items
    WHERE kind = 'screen'
      AND ((definition #> '{definition,universe,traded_on_eval_date}') = 'true'::jsonb
           OR (definition #> '{definition,universe,exclude_price_breaks}') = 'true'::jsonb);
    SELECT count(*) INTO backed FROM edge_bff.screener_items_chips_backup_20261125;
    SELECT count(*) INTO changed FROM edge_bff.screener_items s JOIN edge_bff.screener_items_chips_backup_20261125 b USING (item_id)
    WHERE s.revision = b.revision + 1
      AND (s.definition #> '{definition,universe}') - 'traded_on_eval_date' - 'exclude_price_breaks'
          = b.universe - 'traded_on_eval_date' - 'exclude_price_breaks';
    IF left_on <> 0 OR changed <> backed THEN
        RAISE EXCEPTION 'chips off: % screens still hide, % of % changed rows differ elsewhere', left_on, backed - changed, backed;
    END IF;
    RAISE NOTICE 'chips off: % saved screens switched off, backed up', backed;
END $check$;

COMMIT;

-- Rollback (by hand, with the user's go): put every backed-up universe back and drop the backup.
-- BEGIN;
-- UPDATE edge_bff.screener_items s SET definition = jsonb_set(s.definition, '{definition,universe}', b.universe),
--        revision = s.revision + 1
-- FROM edge_bff.screener_items_chips_backup_20261125 b WHERE s.item_id = b.item_id;
-- DROP TABLE edge_bff.screener_items_chips_backup_20261125;
-- COMMIT;
