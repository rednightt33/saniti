-- EDGE Terminal chart layouts (EXEC-TERMINAL-LAYOUTS, user 2026-11-06: "di akun edge. Tidak usah mengganti saham."):
-- the chart layouts one EDGE owner saves in the Terminal (indicators with their settings, pane collapse, timeframe, chart
-- style, Price/Return, Volume, Events and the Flow Timeline's settings), opened on whatever ticker is shown. One new table
-- in the existing operational schema edge_bff, used by edge_bff_runtime only; no market data is stored here (a layout is
-- the page's own settings), no existing table, role or grant changes. Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'edge_bff') OR
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'edge_bff schema/role is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'terminal_layouts') THEN
        RAISE EXCEPTION 'edge_bff.terminal_layouts exists: reconcile before applying';
    END IF;
END $preflight$;

-- One row per saved layout of an owner. state is the page's settings as the page sent them (apps/edge-bff/terminal
-- src/app/layouts.ts LAYOUT_KEYS: stored setting name -> value); edge-bff checks only its shape and size, the page drops
-- what it no longer knows when it opens a layout. summary is the page's one-line description for the menu (for example
-- "D · 4 indicators"). revision is the optimistic-concurrency counter of name and state: a write with a stale revision is
-- refused (409 REVISION_CONFLICT); favorite and opened_at change without it.
CREATE TABLE edge_bff.terminal_layouts (
    layout_id text PRIMARY KEY CHECK (layout_id ~ '^lay_[0-9a-f]{32}$'),
    owner_key text NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120 AND name = btrim(name)),
    state jsonb NOT NULL CHECK (jsonb_typeof(state) = 'object')
        CONSTRAINT terminal_layouts_state_size CHECK (octet_length(state::text) <= 65536),
    summary text NOT NULL DEFAULT '' CHECK (length(summary) <= 120),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    favorite boolean NOT NULL DEFAULT false,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    opened_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT terminal_layouts_owner_name UNIQUE (owner_key, name)
);
-- The menu's list: one owner's layouts, the most recently opened first.
CREATE INDEX terminal_layouts_owner_opened ON edge_bff.terminal_layouts(owner_key, opened_at DESC);

COMMENT ON TABLE edge_bff.terminal_layouts IS 'EDGE Terminal chart layouts per owner: the page''s chart settings (indicators, panes, timeframe, style, Flow Timeline), applied to the ticker on screen; never market data.';
COMMENT ON COLUMN edge_bff.terminal_layouts.state IS 'Stored setting name -> value as the page sent it (terminal src/app/layouts.ts LAYOUT_KEYS); shape and size checked only, never adjusted.';
COMMENT ON COLUMN edge_bff.terminal_layouts.summary IS 'The page''s one-line description for the layout menu (timeframe and number of indicators).';
COMMENT ON COLUMN edge_bff.terminal_layouts.revision IS 'Optimistic concurrency of name and state: 1 at creation, +1 at every replace; a replace naming another revision is refused (409 REVISION_CONFLICT).';
COMMENT ON COLUMN edge_bff.terminal_layouts.opened_at IS 'When the owner last opened or saved the layout (the menu''s Recently used order).';

-- What edge-bff (apps/edge-bff/app/layouts.py) does to it and no more: listed, created, replaced, marked and deleted.
REVOKE ALL ON edge_bff.terminal_layouts FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.terminal_layouts TO edge_bff_runtime;
DO $verify$
BEGIN
    -- one privilege per call: has_table_privilege with a list is true when any one of them is held
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS needed(privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.terminal_layouts', privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use edge_bff.terminal_layouts';
    END IF;
    -- and nothing else: TRUNCATE would empty every owner's layouts at once
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.terminal_layouts', 'TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than edge_bff.terminal_layouts needs';
    END IF;
    IF has_table_privilege('public', 'edge_bff.terminal_layouts', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'PUBLIC can use edge_bff.terminal_layouts';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; it deletes every saved layout):
-- BEGIN;
-- DROP TABLE edge_bff.terminal_layouts;
-- COMMIT;
