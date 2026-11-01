-- EXEC-FI-TERMINAL S0 (user go 2026-11-01: "Ok with above recommendation ... jalankan TERMINAL-IND-CARDS as well"): the
-- terminal publisher and API may read the fixed-income daily bars and their universe, to publish per-instrument files
-- (yield and price, each on its own dates) like the IDX prices. Read 2026-11-01: has_table_privilege was false for
-- terminal_market_reader, terminal_publisher_login and terminal_api_login on both tables.
-- Rollback: REVOKE SELECT ON public."Price_Fixed_Income", public."Universe_Fixed_income" FROM terminal_market_reader;
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'terminal_market_reader') THEN
        RAISE EXCEPTION 'terminal_market_reader missing: apply 20261025_001 first';
    END IF;
    IF to_regclass('public."Price_Fixed_Income"') IS NULL OR to_regclass('public."Universe_Fixed_income"') IS NULL THEN
        RAISE EXCEPTION 'fixed-income tables missing';
    END IF;
END $preflight$;
GRANT SELECT ON public."Price_Fixed_Income", public."Universe_Fixed_income" TO terminal_market_reader;
COMMIT;
