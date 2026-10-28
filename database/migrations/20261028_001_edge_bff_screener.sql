-- EDGE screener (EXEC-SCREENER, user go 2026-10-28; P12 (a), user 2026-10-28: "P12 OK", one watchlist; report
-- DATABASE / FEATURE CHANGES 7.2, API CONTRACT 8.7): edge-bff's saved screens and My metrics (one table, kind screen |
-- metric) and the owner's one watchlist. Two new tables in the existing operational schema edge_bff, used by
-- edge_bff_runtime only; no market data is stored here (screens are computed by the private screener-worker from the
-- rack), no existing table, role or grant changes. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'edge_bff schema/role is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff'
               AND table_name IN ('screener_items', 'watchlist_items')) THEN
        RAISE EXCEPTION 'an edge_bff screener table exists: reconcile before applying';
    END IF;
END $preflight$;

-- One row per saved item of an owner: a saved screen (kind 'screen', definition {definition, view?}: the portable
-- screen definition and the table's sort and near toggle) or a My metric (kind 'metric', definition {test}: one
-- condition card's test). Stored as the page sent it once the screener-worker's /v1/validate accepted it, and never
-- adjusted: a parameter that later leaves the registry range is flagged on load (needs_review), not changed. revision
-- is the optimistic-concurrency counter: a write with a stale revision is refused (409 REVISION_CONFLICT).
CREATE TABLE edge_bff.screener_items (
    item_id text PRIMARY KEY CHECK (item_id ~ '^scr_[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('screen', 'metric')),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120 AND name = btrim(name)),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object')
        CONSTRAINT screener_items_definition_size CHECK (octet_length(definition::text) <= 65536),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    registry_version text NOT NULL CHECK (length(registry_version) BETWEEN 1 AND 200),
    screener_registry_version text NOT NULL CHECK (length(screener_registry_version) BETWEEN 1 AND 200),
    definition_hash text NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT screener_items_owner_kind_name UNIQUE (owner_key, kind, name)
);
-- The page's list: one owner's items of one kind, the latest changed first.
CREATE INDEX screener_items_owner_kind_updated ON edge_bff.screener_items(owner_key, kind, updated_at DESC);

-- The owner's one watchlist (P12: one list, no named lists): one row per watched ticker.
CREATE TABLE edge_bff.watchlist_items (
    owner_key text NOT NULL,
    ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{1,12}$'),
    added_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_key, ticker)
);

COMMENT ON TABLE edge_bff.screener_items IS 'EDGE screener saved items per owner: saved screens (kind screen) and My metrics (kind metric); definitions only, never market data or results.';
COMMENT ON COLUMN edge_bff.screener_items.definition IS 'kind screen: {definition, view?} (the portable screen definition, apps/edge-bff/screener/src/core/contract.ts, and the table view); kind metric: {test}. As the page sent it after the worker validated it; never adjusted.';
COMMENT ON COLUMN edge_bff.screener_items.registry_version IS 'versions.registry (backtest-registry.json registry_version) when the item was last validated and saved.';
COMMENT ON COLUMN edge_bff.screener_items.screener_registry_version IS 'versions.screener_registry (screener-registry.json) when the item was last validated and saved; an item saved under another version is validated again on load.';
COMMENT ON COLUMN edge_bff.screener_items.definition_hash IS 'The worker''s /v1/validate definition_hash (sha256 of the canonical definition with parameters resolved and labels removed).';
COMMENT ON COLUMN edge_bff.screener_items.revision IS 'Optimistic concurrency: 1 at creation, +1 at every replace; a replace naming another revision is refused (409 REVISION_CONFLICT).';
COMMENT ON TABLE edge_bff.watchlist_items IS 'EDGE screener watchlist: the tickers one owner watches (one list per owner).';

-- Each table gets what edge-bff (apps/edge-bff/app/screener.py) does to it and no more: saved items are listed,
-- created, replaced and deleted; watchlist rows are listed, added (INSERT ... ON CONFLICT DO NOTHING) and removed,
-- never updated.
REVOKE ALL ON edge_bff.screener_items, edge_bff.watchlist_items FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.screener_items TO edge_bff_runtime;
GRANT SELECT, INSERT, DELETE ON edge_bff.watchlist_items TO edge_bff_runtime;
DO $verify$
BEGIN
    -- one privilege per call: has_table_privilege with a list is true when any one of them is held
    IF EXISTS (SELECT 1 FROM (VALUES ('screener_items', 'SELECT'), ('screener_items', 'INSERT'), ('screener_items', 'UPDATE'),
                                     ('screener_items', 'DELETE'),
                                     ('watchlist_items', 'SELECT'), ('watchlist_items', 'INSERT'), ('watchlist_items', 'DELETE'))
                    AS needed(tbl, privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.' || tbl, privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use the screener tables';
    END IF;
    -- and nothing else (a list is true when any one of them is held): TRUNCATE would empty every owner's items at once
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.screener_items', 'TRUNCATE, REFERENCES, TRIGGER')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.watchlist_items', 'UPDATE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than the screener tables need';
    END IF;
    -- and PUBLIC (every role) nothing on either of them (a list: true when any one is held)
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['screener_items', 'watchlist_items']) AS t(tbl)
               WHERE has_table_privilege('public', 'edge_bff.' || tbl, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')) THEN
        RAISE EXCEPTION 'PUBLIC can use the screener tables';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; it deletes every saved screen, My metric and watchlist entry):
-- BEGIN;
-- DROP TABLE edge_bff.watchlist_items;
-- DROP TABLE edge_bff.screener_items;
-- COMMIT;
