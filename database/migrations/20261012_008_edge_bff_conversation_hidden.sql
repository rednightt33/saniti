-- EXEC-DELETE (user decision 2026-10-12: "pakai B hanya sembunyikan di front end tapi backend bisa akses if needed"):
-- a conversation the user deletes in EDGE is hidden from the conversation list only. Orc keeps its history, results
-- and exports under its own retention; the audit records stay.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'edge_bff' AND table_name = 'conversation_ui') THEN
        RAISE EXCEPTION 'edge_bff.conversation_ui is missing: apply 20261008_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'edge_bff' AND table_name = 'conversation_ui' AND column_name = 'hidden_at') THEN
        RAISE EXCEPTION 'edge_bff.conversation_ui.hidden_at exists: reconcile before applying';
    END IF;
END $preflight$;
ALTER TABLE edge_bff.conversation_ui ADD COLUMN hidden_at timestamptz;
COMMENT ON COLUMN edge_bff.conversation_ui.hidden_at IS
    'When the user deleted the conversation in EDGE: hidden from the list only; Orc keeps it under its own retention.';
COMMIT;
