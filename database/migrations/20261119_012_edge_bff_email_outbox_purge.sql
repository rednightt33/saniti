-- EDGE multi-user, fix round of the ultracode re-check (EXEC-MU-ACCOUNTS; verification/edge_multiuser/fix_round/auth.md;
-- contract verification/edge_multiuser/access_tiers/CONTRACT.md sections 1, 4 and 5), behind the switch EDGE_MULTIUSER
-- (off until Phase 6; with it off nothing is written to the outbox, so both reads and the purge find no row).
-- 1. ERRORS R2-35: the hot reads of edge_bff.email_outbox scanned every email ever sent: the 60-second gap between code
--    emails of an address (app/auth_flows.py _may_send, on every register, resend, forgot and sign-in restart, by
--    to_email and created_at) and the sender's claim every 5 s (app/mailer.py OutboxStore.claim: the expired and
--    suppressed UPDATEs and the SELECT ... FOR UPDATE SKIP LOCKED, all on rows still pending or sending). Two indexes:
--      email_outbox_to_email_created  (to_email, created_at)          _may_send; the purge by address
--      email_outbox_unsent            (next_at) WHERE pending/sending  the claim (a handful of rows, whatever the size)
--    Measured (EXPLAIN, 20 000 sent rows, tests/test_c2_ops_recheck.py): without them all four statements are Seq Scans;
--    with them none is (the finder's control and this migration's run, fix_round/auth.md).
-- 2. ERRORS R2-24: the hourly purge deleted a registration never verified 24 h after it was made (CONTRACT 4), but every
--    outbox row naming its address stayed for ever, and edge_bff_runtime holds no DELETE on the outbox (20261116_003:
--    "never deleted"). The rule here follows CONTRACT 4's: an address that has no row in edge_bff.users (no account and
--    no pending registration: never verified and purged, or never registered) keeps no sent, failed, expired or
--    suppressed outbox row older than 24 h. The function edge_bff.purge_email_outbox(max_rows) deletes exactly those, at
--    most max_rows per call (NULL: 10 000, and never more; the hourly housekeeping passes its batch, store.PURGE_BATCH,
--    each batch in its own transaction); edge_bff_runtime may execute it and still holds no DELETE on the table, so the
--    rule is the only delete edge-bff can make. The rows of an address that has an account are kept: their retention is a decision of the
--    user (fix_round/auth.md, decisions; the Privacy text names it), applied later by replacing this function.
-- Forward-only; refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.email_outbox') IS NULL OR to_regclass('edge_bff.users') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.email_outbox or edge_bff.users is missing: apply 20261116_003 first';
    END IF;
    IF to_regclass('edge_bff.email_outbox_to_email_created') IS NOT NULL OR to_regclass('edge_bff.email_outbox_unsent') IS NOT NULL
       OR EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'purge_email_outbox' AND pronamespace = 'edge_bff'::regnamespace) THEN
        RAISE EXCEPTION 'an index or the function of this migration exists: reconcile before applying';
    END IF;
END $preflight$;

CREATE INDEX email_outbox_to_email_created ON edge_bff.email_outbox (to_email, created_at);
CREATE INDEX email_outbox_unsent ON edge_bff.email_outbox (next_at) WHERE status IN ('pending', 'sending');

CREATE FUNCTION edge_bff.purge_email_outbox(max_rows integer) RETURNS integer LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, edge_bff AS $fn$
    WITH gone AS (
        SELECT o.outbox_id FROM edge_bff.email_outbox o
        WHERE o.status IN ('sent', 'failed', 'expired', 'suppressed')
          AND o.created_at < now() - interval '24 hours'
          AND NOT EXISTS (SELECT 1 FROM edge_bff.users u WHERE u.email = o.to_email)
        ORDER BY o.outbox_id LIMIT greatest(1, least(coalesce(max_rows, 10000), 10000))),
    deleted AS (DELETE FROM edge_bff.email_outbox o USING gone WHERE o.outbox_id = gone.outbox_id RETURNING 1)
    SELECT count(*)::integer FROM deleted
$fn$;
COMMENT ON FUNCTION edge_bff.purge_email_outbox(integer) IS 'ERRORS R2-24: deletes (at most max_rows per call, NULL or more than 10 000 = 10 000) the sent, failed, expired or suppressed outbox rows older than 24 h of addresses with no row in edge_bff.users; called hourly by edge-bff (store.py PURGES outbox, worker.Housekeeping). The rows of an address with an account are kept until the user sets their retention.';
REVOKE ALL ON FUNCTION edge_bff.purge_email_outbox(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION edge_bff.purge_email_outbox(integer) TO edge_bff_runtime;
COMMENT ON TABLE edge_bff.email_outbox IS 'EDGE emails to send (Resend, Idempotency-Key = idempotency_key). A code email carries expires_at = the code expiry and is never sent after it; payload is nulled once sent. Rows of an address with no account are deleted 24 h after they were made (purge_email_outbox); edge_bff_runtime holds no DELETE.';

DO $verify$
BEGIN
    -- the runtime still cannot delete from the outbox itself (20261116_003), and may run the purge only
    IF has_table_privilege('edge_bff_runtime', 'edge_bff.email_outbox', 'DELETE')
       OR has_table_privilege('edge_bff_runtime', 'edge_bff.email_outbox', 'TRUNCATE') THEN
        RAISE EXCEPTION 'edge_bff_runtime may delete from edge_bff.email_outbox';
    END IF;
    IF NOT has_function_privilege('edge_bff_runtime', 'edge_bff.purge_email_outbox(integer)', 'EXECUTE')
       OR has_function_privilege('public', 'edge_bff.purge_email_outbox(integer)', 'EXECUTE') THEN
        RAISE EXCEPTION 'edge_bff.purge_email_outbox(integer) is not for edge_bff_runtime only';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE oid = 'edge_bff.purge_email_outbox(integer)'::regprocedure AND prosecdef
                   AND proconfig @> ARRAY['search_path=pg_catalog, edge_bff']) THEN
        RAISE EXCEPTION 'edge_bff.purge_email_outbox(integer) must be SECURITY DEFINER with a fixed search_path';
    END IF;
    IF (SELECT count(*) FROM pg_indexes WHERE schemaname = 'edge_bff' AND tablename = 'email_outbox'
        AND indexname IN ('email_outbox_to_email_created', 'email_outbox_unsent')) <> 2 THEN
        RAISE EXCEPTION 'an index of edge_bff.email_outbox is missing';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy an edge-bff that does not call the purge first):
-- BEGIN;
-- DROP FUNCTION edge_bff.purge_email_outbox(integer);
-- DROP INDEX edge_bff.email_outbox_unsent, edge_bff.email_outbox_to_email_created;
-- COMMIT;
