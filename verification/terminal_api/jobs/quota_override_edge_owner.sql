-- EXEC-TERMINAL-API T3 (user 2026-10-25: "Saya dulu untuk testing"): the EDGE owner's gateway account opens a ticker
-- with its full price history (~27 files: price 2018-2026, IHSG, broker 2021-2026, events, references), so the default
-- 60 files per hour allows about two tickers. TEMPORARY override for this one account until the user decides the
-- default (FUTURE_PLAN.md). Remove: DELETE FROM terminal.quota_override WHERE subscriber_id = (SELECT subscriber_id FROM
-- terminal.subscriber WHERE email = 'edge-owner@terminal.local') AND name = 'files_per_hour'.
BEGIN;
INSERT INTO terminal.quota_override (subscriber_id, name, value)
SELECT subscriber_id, 'files_per_hour', 600 FROM terminal.subscriber WHERE email = 'edge-owner@terminal.local'
ON CONFLICT (subscriber_id, name) DO UPDATE SET value = EXCLUDED.value;
COMMIT;
