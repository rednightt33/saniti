-- EDGE Terminal indicator presets (EXEC-IND-PRESETS, user 2026-11-06: "men-save indikator beserta dengan filternya";
-- "Q1 A" (on the EDGE account), "Q2 A"): one indicator with its parameters, filters and style, saved by the signed-in owner
-- under a name and added again from the Indicators window on any ticker. One new table in the existing operational schema
-- edge_bff, used by edge_bff_runtime only; no market data is stored here, no existing table, role or grant changes.
-- Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'edge_bff schema/role is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'indicator_presets') THEN
        RAISE EXCEPTION 'edge_bff.indicator_presets exists: reconcile before applying';
    END IF;
END $preflight$;

-- One row per saved preset of an owner. def_id is the Terminal's indicator id (registry FLxx, Ixx, or a built-in id);
-- config is {params, style, on?, fold?} as the page sent it (apps/edge-bff/terminal src/app/presets.ts); edge-bff checks
-- only its shape and size, the page drops what it no longer knows when it adds a preset. summary is the page's one-line
-- description of the filters. revision is the optimistic-concurrency counter of name and config; favorite and used_at
-- change without it.
CREATE TABLE edge_bff.indicator_presets (
    preset_id text PRIMARY KEY CHECK (preset_id ~ '^ipr_[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120 AND name = btrim(name)),
    def_id text NOT NULL CHECK (def_id ~ '^[A-Za-z0-9_]{1,40}$'),
    config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object')
        CONSTRAINT indicator_presets_config_size CHECK (octet_length(config::text) <= 16384),
    summary text NOT NULL DEFAULT '' CHECK (length(summary) <= 300),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    favorite boolean NOT NULL DEFAULT false,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT indicator_presets_owner_name UNIQUE (owner_key, name)
);
-- The Indicators window's list: one owner's presets, the most recently used first.
CREATE INDEX indicator_presets_owner_used ON edge_bff.indicator_presets(owner_key, used_at DESC);

COMMENT ON TABLE edge_bff.indicator_presets IS 'EDGE Terminal indicator presets per owner: one indicator with its parameters, filters and style, added again on any ticker; never market data.';
COMMENT ON COLUMN edge_bff.indicator_presets.def_id IS 'The Terminal indicator id (flow registry FLxx, indicator registry, or a built-in id).';
COMMENT ON COLUMN edge_bff.indicator_presets.config IS '{params, style, on?, fold?} as the page sent it (terminal src/app/presets.ts); shape and size checked only, never adjusted.';
COMMENT ON COLUMN edge_bff.indicator_presets.summary IS 'The page''s one-line description of the preset''s filters for the Indicators window.';
COMMENT ON COLUMN edge_bff.indicator_presets.revision IS 'Optimistic concurrency of name and config: 1 at creation, +1 at every replace; a replace naming another revision is refused (409 REVISION_CONFLICT).';
COMMENT ON COLUMN edge_bff.indicator_presets.used_at IS 'When the owner last added or saved the preset (the list''s order).';

-- What edge-bff (apps/edge-bff/app/presets.py) does to it and no more: listed, created, replaced, marked and deleted.
REVOKE ALL ON edge_bff.indicator_presets FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.indicator_presets TO edge_bff_runtime;
DO $verify$
BEGIN
    -- one privilege per call: has_table_privilege with a list is true when any one of them is held
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS needed(privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.indicator_presets', privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use edge_bff.indicator_presets';
    END IF;
    -- and nothing else: TRUNCATE would empty every owner's presets at once
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.indicator_presets', 'TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than edge_bff.indicator_presets needs';
    END IF;
    IF has_table_privilege('public', 'edge_bff.indicator_presets', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'PUBLIC can use edge_bff.indicator_presets';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; it deletes every saved preset):
-- BEGIN;
-- DROP TABLE edge_bff.indicator_presets;
-- COMMIT;
