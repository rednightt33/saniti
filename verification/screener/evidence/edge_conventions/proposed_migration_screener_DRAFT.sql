-- DRAFT ONLY (PROPOSED, audit 2026-10-27). NOT a repository file, NOT applied, NOT approved.
-- Follows the edge_bff conventions of 20261008_002 / 20261024_002 / 20261026_005: BEGIN; lock/statement timeouts;
-- $preflight$ block; owner_key text keyed rows; CHECKed ids; COMMENTs; per-table REVOKE FROM PUBLIC and exact GRANTs to
-- edge_bff_runtime; $verify$ block checking each needed privilege one call at a time, nothing more, and PUBLIC nothing;
-- rollback body as a comment.
-- Open product decisions that change this draft: one watchlist or several named lists; whether "My metrics" are stored
-- server-side; limits (screens per owner, tickers per watchlist).
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
               AND table_name IN ('screener_screens', 'watchlist_items')) THEN
        RAISE EXCEPTION 'an edge_bff screener table exists: reconcile before applying';
    END IF;
END $preflight$;

-- A saved screen: the page's definition (universe, conditions with indicator id + parameters, match logic, sort) as
-- JSON; edge-bff reads only its name and size, never market data.
CREATE TABLE edge_bff.screener_screens (
    screen_id text PRIMARY KEY CHECK (screen_id ~ '^scr_[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120 AND name = btrim(name)),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object' AND octet_length(definition::text) <= 65536),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    registry_version text CHECK (length(registry_version) BETWEEN 1 AND 200),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner_key, name)
);
CREATE INDEX screener_screens_owner_updated ON edge_bff.screener_screens(owner_key, updated_at DESC);

-- The owner's watchlist (one list, as the prototype's edge-watchlist set). Tickers are not checked against the rack
-- here (edge-bff holds no market data); the page shows a ticker that is no longer published as such.
CREATE TABLE edge_bff.watchlist_items (
    owner_key text NOT NULL,
    ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{1,12}$'),
    added_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_key, ticker)
);

COMMENT ON TABLE edge_bff.screener_screens IS 'EDGE Screener saved screens per owner: the definition the page saved (JSON); never market data or results.';
COMMENT ON COLUMN edge_bff.screener_screens.definition IS 'The screen as the page sent it (schema_version); edge-bff stores it unchanged.';
COMMENT ON COLUMN edge_bff.screener_screens.revision IS 'Incremented on every update; a write naming an older revision is refused (409).';
COMMENT ON TABLE edge_bff.watchlist_items IS 'EDGE watchlist per owner: one row per ticker the owner added.';

REVOKE ALL ON edge_bff.screener_screens, edge_bff.watchlist_items FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.screener_screens TO edge_bff_runtime;
GRANT SELECT, INSERT, DELETE ON edge_bff.watchlist_items TO edge_bff_runtime;
DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM (VALUES ('screener_screens', 'SELECT'), ('screener_screens', 'INSERT'),
                                     ('screener_screens', 'UPDATE'), ('screener_screens', 'DELETE'),
                                     ('watchlist_items', 'SELECT'), ('watchlist_items', 'INSERT'),
                                     ('watchlist_items', 'DELETE')) AS needed(tbl, privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.' || tbl, privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use the screener tables';
    END IF;
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.screener_screens', 'TRUNCATE, REFERENCES, TRIGGER')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.watchlist_items', 'UPDATE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than the screener tables need';
    END IF;
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['screener_screens', 'watchlist_items']) AS t(tbl)
               WHERE has_table_privilege('public', 'edge_bff.' || tbl, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')) THEN
        RAISE EXCEPTION 'PUBLIC can use the screener tables';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; it deletes every saved screen and watchlist row):
-- BEGIN;
-- DROP TABLE edge_bff.watchlist_items;
-- DROP TABLE edge_bff.screener_screens;
-- COMMIT;
