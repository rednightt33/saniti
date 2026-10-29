SELECT left(execution_id::text,8) id, mode, status, started_at, finished_at, token_expires_at, broker_rows FROM "Monitoring_Stockbit_Update" ORDER BY started_at DESC LIMIT 5
