-- EXEC-TERMINAL-SPEED step 5 (user 2026-10-26: "goalnya adalah kecepatan loading data, beserta dengan efisiensi di
-- backend"): one audit row per /bundle instead of one per file. file_count carries the number of files the row grants
-- (quotas sum it), object_keys the keys themselves. Existing rows are one file each (default 1, keys null).
-- Retention (90 days, user "Ok untuk saran kamu") is done by terminal-api with its existing DELETE privilege.
BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'terminal' AND table_name = 'access_log' AND column_name = 'file_count') THEN
        RAISE EXCEPTION 'terminal.access_log.file_count exists: already applied';
    END IF;
END $$;

ALTER TABLE terminal.access_log
    ADD COLUMN file_count integer NOT NULL DEFAULT 1 CHECK (file_count >= 1),
    ADD COLUMN object_keys text[];

COMMENT ON COLUMN terminal.access_log.file_count IS
    'Files granted by this row (a /bundle row grants several); quotas sum it. 1 for a single file or a history query.';
COMMENT ON COLUMN terminal.access_log.object_keys IS
    'Every object key a /bundle row granted (object_key then holds the first); null for a single-file row.';
COMMENT ON TABLE terminal.access_log IS
    'One row per /files or /bundle call and per fallback query; quotas are computed from it. Rows older than 90 days '
    'are deleted by terminal-api (EXEC-TERMINAL-SPEED).';

COMMIT;
