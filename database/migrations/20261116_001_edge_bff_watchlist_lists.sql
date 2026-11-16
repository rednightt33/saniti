-- EXEC-WATCHLIST L2 (user go 2026-11-16: "Go"; decisions 2026-11-16 1A: per account, ready for EDGE-MULTIUSER; 2A:
-- named lists replace P12's one list, the Screener's star uses the first list and today's starred tickers become the
-- first list "Watchlist"). edge-bff's Watchlist lists: one new table in the operational schema edge_bff and two columns
-- on watchlist_items. No market data is stored here (the figures come from the publisher's watchlist-stocks file); no
-- other table, role or grant changes. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'watchlist_items') THEN
        RAISE EXCEPTION 'edge_bff.watchlist_items is missing: apply 20261028_001 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'watchlist_lists') THEN
        RAISE EXCEPTION 'edge_bff.watchlist_lists exists: reconcile before applying';
    END IF;
    -- the first list holds today's starred tickers; a list holds at most 50 (apps/edge-bff/app/watchlist.py PER_LIST):
    -- more would need the user's decision (EXEC-WATCHLIST L2), never a silent cut
    IF EXISTS (SELECT 1 FROM edge_bff.watchlist_items GROUP BY owner_key HAVING count(*) > 50) THEN
        RAISE EXCEPTION 'an owner watches more than 50 tickers: ask the user before moving them into one list';
    END IF;
END $preflight$;

-- One row per named list of an owner. position orders the tabs (the first is the Screener's star list); a restored
-- list takes back its old position, so positions may have gaps. indicators: the list's chosen indicator keys in their
-- order, NULL = the default of the data file (the keys are the publisher's catalog, watchlist.py CATALOG; this table
-- checks only their shape, so a new indicator needs no migration).
CREATE TABLE edge_bff.watchlist_lists (
    owner_key text NOT NULL,
    list_id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    position integer NOT NULL,
    indicators text[],
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_key, list_id),
    CONSTRAINT watchlist_lists_name CHECK (name = btrim(name) AND char_length(name) BETWEEN 1 AND 40),
    CONSTRAINT watchlist_lists_indicators CHECK (indicators IS NULL OR (cardinality(indicators) BETWEEN 1 AND 8
        AND array_to_string(indicators, ',') ~ '^[a-z0-9_]{1,24}(,[a-z0-9_]{1,24}){0,7}$'))
);
-- a name is unique per owner whatever its case ("Banks" and "banks" are one list)
CREATE UNIQUE INDEX watchlist_lists_owner_name ON edge_bff.watchlist_lists(owner_key, lower(name));

-- today's starred tickers: one list "Watchlist" per owner that has any, in the order they were starred
INSERT INTO edge_bff.watchlist_lists(owner_key, name, position)
SELECT DISTINCT owner_key, 'Watchlist', 0 FROM edge_bff.watchlist_items;

ALTER TABLE edge_bff.watchlist_items ADD COLUMN list_id uuid, ADD COLUMN position integer;
UPDATE edge_bff.watchlist_items AS i SET list_id = l.list_id, position = o.n
FROM edge_bff.watchlist_lists AS l,
     (SELECT owner_key, ticker, (row_number() OVER (PARTITION BY owner_key ORDER BY added_at, ticker) - 1)::integer AS n
      FROM edge_bff.watchlist_items) AS o
WHERE l.owner_key = i.owner_key AND o.owner_key = i.owner_key AND o.ticker = i.ticker;
ALTER TABLE edge_bff.watchlist_items ALTER COLUMN list_id SET NOT NULL, ALTER COLUMN position SET NOT NULL,
    DROP CONSTRAINT watchlist_items_pkey, ADD PRIMARY KEY (owner_key, list_id, ticker),
    ADD CONSTRAINT watchlist_items_list FOREIGN KEY (owner_key, list_id)
        REFERENCES edge_bff.watchlist_lists(owner_key, list_id) ON DELETE CASCADE;

COMMENT ON TABLE edge_bff.watchlist_lists IS 'EDGE Watchlist: the named lists of one owner (account). Lists and their indicator choice only, never market data.';
COMMENT ON COLUMN edge_bff.watchlist_lists.position IS 'Tab order (lowest first; the first list is the Screener star''s list). A restored list takes back its old position, so gaps are allowed.';
COMMENT ON COLUMN edge_bff.watchlist_lists.indicators IS 'The list''s indicator keys in display order (1 to 8, keys of the publisher''s watchlist-stocks catalog); NULL = the file''s default.';
COMMENT ON TABLE edge_bff.watchlist_items IS 'EDGE Watchlist: the tickers of each list of one owner (EXEC-WATCHLIST; before it, the one Screener watchlist).';
COMMENT ON COLUMN edge_bff.watchlist_items.position IS 'Order inside the list (lowest first); a removed ticker put back with Undo takes back its old position.';

-- what edge-bff (apps/edge-bff/app/watchlist.py) does: lists are listed, created, renamed, re-chosen and deleted; items
-- are listed, added and removed (never updated), as before
REVOKE ALL ON edge_bff.watchlist_lists FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.watchlist_lists TO edge_bff_runtime;
DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM (VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE')) AS needed(privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.watchlist_lists', privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use edge_bff.watchlist_lists';
    END IF;
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.watchlist_lists', 'TRUNCATE, REFERENCES, TRIGGER')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.watchlist_items', 'UPDATE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than the watchlist tables need';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.watchlist_items WHERE list_id IS NULL) THEN
        RAISE EXCEPTION 'a watched ticker has no list';
    END IF;
END $verify$;
COMMIT;

-- Rollback (only with the user's approval; drops every named list, keeps one row per starred ticker of the first list):
-- BEGIN;
-- DELETE FROM edge_bff.watchlist_items AS i USING edge_bff.watchlist_lists AS l
--   WHERE l.owner_key = i.owner_key AND l.list_id = i.list_id
--   AND l.position > (SELECT min(position) FROM edge_bff.watchlist_lists AS f WHERE f.owner_key = l.owner_key);
-- ALTER TABLE edge_bff.watchlist_items DROP CONSTRAINT watchlist_items_list, DROP CONSTRAINT watchlist_items_pkey,
--   ADD PRIMARY KEY (owner_key, ticker), DROP COLUMN list_id, DROP COLUMN position;
-- DROP TABLE edge_bff.watchlist_lists;
-- COMMIT;
