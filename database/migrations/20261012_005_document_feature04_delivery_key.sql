BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '2min';

SELECT pg_advisory_xact_lock(hashtextextended('feature04-telegram-delivery-catalog-v1',0));

UPDATE public."Table_Catalog"
SET definition='Outbound Telegram delivery and edit ledger for execution-level price results and logical Feature04 market/date or retry results.',
    update_rule='telegram-monitor inserts or reclaims a delivery identity, then records sent or edited Telegram message IDs and failures.',
    source_code_paths=ARRAY['apps/telegram-monitor/telegram_monitor.py','database/migrations/20261012_005_document_feature04_delivery_key.sql'],
    updated_at=clock_timestamp()
WHERE table_schema='public' AND table_name='Telegram_Notification_Log';

UPDATE public."Column_Catalog"
SET definition='Delivery identity: source execution ID for price/manual results, or logical market/date/retry key for Feature04.',
    source_column_or_expression='Source monitoring execution_id or telegram-monitor Feature04 delivery_key',
    null_rule='Never NULL.',
    source_code_paths=ARRAY['apps/telegram-monitor/telegram_monitor.py','database/migrations/20261012_005_document_feature04_delivery_key.sql'],
    documentation_status='VERIFIED',
    updated_at=clock_timestamp()
WHERE table_schema='public' AND table_name='Telegram_Notification_Log'
  AND column_name='source_execution_id';

DO $block$
BEGIN
    IF NOT EXISTS(
        SELECT 1 FROM public."Column_Catalog"
        WHERE table_schema='public' AND table_name='Telegram_Notification_Log'
          AND column_name='source_execution_id'
          AND source_column_or_expression='Source monitoring execution_id or telegram-monitor Feature04 delivery_key'
    ) THEN
        RAISE EXCEPTION 'Telegram_Notification_Log.source_execution_id catalog row is missing';
    END IF;
END
$block$;

COMMIT;
