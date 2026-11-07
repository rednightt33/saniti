-- EDGE Terminal drawings on the EDGE account (EXEC-DRAW-PANES, user 2026-11-07: "semua gambar harus di simpan di akun
-- EDGE, sama seperti trading view"; "3 jalankan dulu"): the trend lines, rays, brush strokes and texts one owner draws in
-- the Terminal, per ticker and per place: the price chart, the Flow Timeline, and each indicator pane (EXEC-DRAW-PANES 2A:
-- a pane's drawings belong to that pane). One new table in the existing operational schema edge_bff, used by
-- edge_bff_runtime only; a drawing is the owner's own marking, not market data; no existing table, role or grant changes.
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
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'edge_bff' AND table_name = 'terminal_drawings') THEN
        RAISE EXCEPTION 'edge_bff.terminal_drawings exists: reconcile before applying';
    END IF;
END $preflight$;

-- One row per set of drawings of an owner: ticker (terminal-api's ticker rule) and set_id, the place the set is drawn in:
-- 'chart' (the price chart), 'flow' (the Flow Timeline) or 'pane_' and the pane's 16 hexadecimal digits (an indicator
-- pane; the id is kept with the indicator in the page's settings and layouts). drawings is the drawing library's list as
-- the page sent it (apps/edge-bff/terminal src/app/drawings.ts); edge-bff checks only its shape and size. revision is the
-- optimistic-concurrency counter: a write with a stale revision is refused (409 REVISION_CONFLICT).
CREATE TABLE edge_bff.terminal_drawings (
    owner_key text NOT NULL,
    ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{1,12}$'),
    set_id text NOT NULL CHECK (set_id ~ '^(chart|flow|pane_[0-9a-f]{16})$'),
    drawings jsonb NOT NULL CHECK (jsonb_typeof(drawings) = 'array')
        CONSTRAINT terminal_drawings_size CHECK (octet_length(drawings::text) <= 100000),
    schema_version integer NOT NULL CHECK (schema_version >= 1),
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- the page reads one ticker's sets at a time: the key's (owner_key, ticker) prefix serves it
    PRIMARY KEY (owner_key, ticker, set_id)
);

COMMENT ON TABLE edge_bff.terminal_drawings IS 'EDGE Terminal drawings per owner, ticker and place (price chart, Flow Timeline, indicator pane); the owner''s own markings, never market data.';
COMMENT ON COLUMN edge_bff.terminal_drawings.set_id IS 'Where the set is drawn: chart, flow, or pane_ and the indicator pane''s id (kept with the indicator in the page''s settings).';
COMMENT ON COLUMN edge_bff.terminal_drawings.drawings IS 'The drawing library''s list as the page sent it (terminal src/app/drawings.ts); shape and size checked only, never adjusted.';
COMMENT ON COLUMN edge_bff.terminal_drawings.revision IS 'Optimistic concurrency: 1 at creation, +1 at every replace; a replace naming another revision is refused (409 REVISION_CONFLICT).';

-- What edge-bff (apps/edge-bff/app/drawings.py) does to it and no more: read per ticker, created, replaced and deleted.
REVOKE ALL ON edge_bff.terminal_drawings FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON edge_bff.terminal_drawings TO edge_bff_runtime;
DO $verify$
BEGIN
    -- one privilege per call: has_table_privilege with a list is true when any one of them is held
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS needed(privilege)
               WHERE NOT has_table_privilege('edge_bff_runtime', 'edge_bff.terminal_drawings', privilege)) THEN
        RAISE EXCEPTION 'edge_bff_runtime cannot use edge_bff.terminal_drawings';
    END IF;
    -- and nothing else: TRUNCATE would empty every owner's drawings at once
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.terminal_drawings', 'TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'edge_bff_runtime has more than edge_bff.terminal_drawings needs';
    END IF;
    IF has_table_privilege('public', 'edge_bff.terminal_drawings', 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') THEN
        RAISE EXCEPTION 'PUBLIC can use edge_bff.terminal_drawings';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; it deletes every saved drawing):
-- BEGIN;
-- DROP TABLE edge_bff.terminal_drawings;
-- COMMIT;
