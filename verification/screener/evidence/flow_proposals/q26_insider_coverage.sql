SELECT data_origin, count(*) n, min(transaction_date) first_d, max(transaction_date) last_d, max(last_seen_at) last_pull,
       count(*) FILTER (WHERE transaction_date >= DATE '2026-09-30') since_0930,
       count(DISTINCT ticker) FILTER (WHERE transaction_date >= DATE '2026-09-30') tickers_since_0930,
       count(*) FILTER (WHERE transaction_date >= DATE '2026-09-30' AND action_type IN ('BUY','SELL')) buy_sell_since_0930,
       count(*) FILTER (WHERE source_removed_at IS NOT NULL) removed
FROM stockbit_insider_transaction GROUP BY 1;;
SELECT action_type, count(*) FROM stockbit_insider_transaction WHERE transaction_date >= DATE '2026-01-01' GROUP BY 1 ORDER BY 2 DESC LIMIT 8;;
SELECT has_table_privilege('terminal_publisher_login', 'public.stockbit_insider_transaction', 'SELECT') pub_insider, has_table_privilege('terminal_publisher_login', 'public.idx_event_annotation', 'SELECT') pub_annotation
