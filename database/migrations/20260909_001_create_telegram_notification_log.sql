BEGIN;

CREATE TABLE IF NOT EXISTS public."Telegram_Notification_Log" (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_table text NOT NULL,
    source_execution_id text NOT NULL,
    notification_type text NOT NULL DEFAULT 'COMPLETED',
    send_status text NOT NULL DEFAULT 'PENDING',
    attempt_count integer NOT NULL DEFAULT 0,
    telegram_message_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    sent_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Telegram_Notification_Log_delivery_key"
        UNIQUE (source_table, source_execution_id, notification_type),
    CONSTRAINT "Telegram_Notification_Log_status_check"
        CHECK (send_status IN ('PENDING', 'SENDING', 'SENT', 'FAILED')),
    CONSTRAINT "Telegram_Notification_Log_attempt_count_check"
        CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS "Telegram_Notification_Log_status_idx"
    ON public."Telegram_Notification_Log" (send_status, updated_at DESC);

COMMENT ON TABLE public."Telegram_Notification_Log" IS
    'Delivery ledger used by telegram-monitor to prevent duplicate notifications.';
COMMENT ON COLUMN public."Telegram_Notification_Log".source_execution_id IS
    'The execution_id from the source monitoring table; one completed run is sent once.';

COMMIT;
