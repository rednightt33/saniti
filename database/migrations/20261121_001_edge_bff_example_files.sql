-- EDGE multi-user, 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A, the user's go for steps 1-5;
-- ERRORS M527): "kayak semacam static HTML di hari tersebut saja". A visitor who is not signed in (the guest plan) and the
-- free plan see each data page as it opens, with the data of one past date (30 October 2026 for the Radar, the
-- Watchlist, the Screener and the Backtest), and every click asks to sign in or to upgrade. This table keeps those
-- files: the files of each page's opening view, built once from the data of that date by a capture job
-- (verification/edge_multiuser/example_mode/capture_job.py, apps/terminal-publisher/examples.py), gzip JSON in the
-- shape the page reads from its live route. edge-bff serves them as GET /api/v1/examples/<tab>/index and
-- /api/v1/examples/<tab>/file/<name> (app/examples.py) to a principal holding <tab>.example, from its own memory (read
-- from here at most every few minutes).
--
-- One row per file; a capture replaces the rows of one tab in one transaction. The checks hold every row to what the
-- route serves: the name of the page family's own form, the body's length and its SHA-256 as stated (sha256() of
-- PostgreSQL 11+), a body of at most 8 MiB, and the date the data was cut at.
--
-- Expand only: a new table nothing reads yet. edge_bff_runtime (edge-bff) may only read it; the capture job writes it
-- as the database owner. Refuses a second run. Forward-only; rollback block at the end. The guest plan's rows that open
-- the examples to visitors are a migration of their own (20261121_002), applied when the live site runs the code that
-- reads them (EXEC.md, the user's go of 2026-11-21).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regnamespace('edge_bff') IS NULL OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edge_bff_runtime') THEN
        RAISE EXCEPTION 'the schema edge_bff or the role edge_bff_runtime is missing: apply the edge_bff migrations first';
    END IF;
    IF to_regclass('edge_bff.example_files') IS NOT NULL THEN
        RAISE EXCEPTION 'edge_bff.example_files exists: this migration ran already';
    END IF;
END $preflight$;

CREATE TABLE edge_bff.example_files (
    tab text NOT NULL CONSTRAINT example_files_tab CHECK (tab ~ '^[a-z]{1,24}$'),
    name text NOT NULL CONSTRAINT example_files_name CHECK (name ~ '^[a-z0-9][a-z0-9_-]{0,63}$' AND name LIKE tab || '-%'),
    as_of date NOT NULL,
    rows integer NOT NULL CONSTRAINT example_files_rows CHECK (rows >= 0),
    bytes integer NOT NULL CONSTRAINT example_files_bytes CHECK (bytes BETWEEN 1 AND 8388608),
    sha256 text NOT NULL CONSTRAINT example_files_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    body bytea NOT NULL,
    made_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tab, name),
    CONSTRAINT example_files_body CHECK (octet_length(body) = bytes AND encode(sha256(body), 'hex') = sha256)
);
COMMENT ON TABLE edge_bff.example_files IS
    'EXEC-MU-ACCOUNTS 3e, the example mode (user 2026-11-21): the files of each data page''s opening view, cut at one past '
    'date (as_of), gzip JSON as the page reads them; served by edge-bff to a principal holding <tab>.example '
    '(app/examples.py); written only by the capture job (verification/edge_multiuser/example_mode/capture_job.py).';
COMMENT ON COLUMN edge_bff.example_files.as_of IS
    'the date the data was cut at: no date after it is named in the file (the capture job refuses one)';
COMMENT ON COLUMN edge_bff.example_files.body IS
    'the file''s gzip JSON bytes, as the page''s live route would send them; bytes and sha256 describe exactly these bytes';
REVOKE ALL ON edge_bff.example_files FROM PUBLIC;
GRANT SELECT ON edge_bff.example_files TO edge_bff_runtime;

DO $verify$
BEGIN
    IF to_regclass('edge_bff.example_files') IS NULL THEN
        RAISE EXCEPTION 'verify: edge_bff.example_files is missing';
    END IF;
    IF NOT has_table_privilege('edge_bff_runtime', 'edge_bff.example_files', 'SELECT')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.example_files', 'INSERT')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.example_files', 'UPDATE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.example_files', 'DELETE') THEN
        RAISE EXCEPTION 'verify: edge_bff_runtime must read edge_bff.example_files and write nothing to it';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body, once no edge-bff that reads the table runs):
-- BEGIN;
-- DROP TABLE edge_bff.example_files;
-- COMMIT;
