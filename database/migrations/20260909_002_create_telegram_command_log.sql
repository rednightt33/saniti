BEGIN;

CREATE TABLE IF NOT EXISTS public."Telegram_Command_Log" (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_update_id bigint NOT NULL,
    chat_id bigint NOT NULL,
    command text NOT NULL,
    target_service text NOT NULL,
    requested_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    triggered_at timestamp with time zone,
    finished_at timestamp with time zone,
    status text NOT NULL DEFAULT 'RECEIVED',
    railway_reference text,
    last_error text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Telegram_Command_Log_update_key" UNIQUE (telegram_update_id),
    CONSTRAINT "Telegram_Command_Log_status_check"
        CHECK (status IN ('RECEIVED', 'TRIGGERED', 'BLOCKED', 'FAILED')),
    CONSTRAINT "Telegram_Command_Log_command_not_blank"
        CHECK (btrim(command) <> ''),
    CONSTRAINT "Telegram_Command_Log_target_not_blank"
        CHECK (btrim(target_service) <> '')
);

CREATE INDEX IF NOT EXISTS "Telegram_Command_Log_service_time_idx"
    ON public."Telegram_Command_Log" (target_service, requested_at DESC);

CREATE INDEX IF NOT EXISTS "Telegram_Command_Log_status_idx"
    ON public."Telegram_Command_Log" (status, requested_at DESC);

COMMENT ON TABLE public."Telegram_Command_Log" IS
    'Inbound Telegram command audit and duplicate-prevention ledger for telegram-trigger.';
COMMENT ON COLUMN public."Telegram_Command_Log".telegram_update_id IS
    'Unique Telegram update identifier; repeated webhook deliveries reuse the existing command row.';
COMMENT ON COLUMN public."Telegram_Command_Log".railway_reference IS
    'Allowlisted Railway service-instance identifier used for the Run Now request.';

COMMIT;
