-- EXEC-SCREENER-STOCK-LISTS (user 2026-11-09 "sync with main, merge. push to dev."): the terminal publisher may read the
-- stock lists, to publish the reference file `stock_lists` (publisher.py STOCK_LISTS_SQL reads Stock_List and
-- Stock_List_Member only). Found live 2026-11-09 15:39 UTC: the first publisher run with the file logged
-- stock_lists_failed InsufficientPrivilege. Cause (read in the code): the publisher connects as terminal_publisher_login,
-- a member of terminal_market_reader, which holds SELECT only on the tables granted to it by name
-- (20261025_100_create_terminal_schema.sql :115, 20261101_003_terminal_reader_fixed_income.sql); 20261109_001 granted
-- the new tables to pgweb_reader only. Same pattern as 20261101_003. History, load log and the view stay unread.
-- Rollback: REVOKE SELECT ON public."Stock_List", public."Stock_List_Member" FROM terminal_market_reader;
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') THEN
        RAISE EXCEPTION 'terminal_market_reader missing: apply 20261025_001 first';
    END IF;
    IF to_regclass('public."Stock_List"') IS NULL OR to_regclass('public."Stock_List_Member"') IS NULL THEN
        RAISE EXCEPTION 'Stock_List tables missing: apply 20261109_001 first';
    END IF;
END $preflight$;
GRANT SELECT ON public."Stock_List", public."Stock_List_Member" TO terminal_market_reader;
COMMIT;
