-- EXEC-TERMINAL-API (user 2026-10-26: "Untuk batas saat ini di eliminate saja dulu. Ini kita mau tahap testing dan front
-- end design"): the testing (gateway) account gets no practical download limits. TEMPORARY, this account only; the
-- defaults in terminal.quota stay for real subscribers. Remove: DELETE FROM terminal.quota_override WHERE subscriber_id =
-- (SELECT subscriber_id FROM terminal.subscriber WHERE email = 'edge-owner@terminal.local') AND name IN
-- ('files_per_hour','tickers_per_hour','tickers_per_day','megabytes_per_day','history_per_hour').
BEGIN;
INSERT INTO terminal.quota_override (subscriber_id, name, value)
SELECT s.subscriber_id, q.name, 1000000000
FROM terminal.subscriber s
CROSS JOIN (VALUES ('files_per_hour'), ('tickers_per_hour'), ('tickers_per_day'), ('megabytes_per_day'), ('history_per_hour')) AS q(name)
WHERE s.email = 'edge-owner@terminal.local'
ON CONFLICT (subscriber_id, name) DO UPDATE SET value = EXCLUDED.value;
COMMIT;
