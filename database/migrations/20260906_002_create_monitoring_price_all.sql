BEGIN;

CREATE TABLE IF NOT EXISTS public."Monitoring_Price_ALL" (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exchange text NOT NULL,
    asset_type text NOT NULL,
    timeframe text NOT NULL DEFAULT '1d',
    run_type text NOT NULL,
    expected_symbols integer NOT NULL,
    queried_symbols integer NOT NULL,
    updated_symbols integer NOT NULL,
    missing_symbols integer NOT NULL,
    missing_symbol_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    update_for_date date NOT NULL,
    run_time timestamp with time zone NOT NULL,
    finished_at timestamp with time zone NOT NULL,
    attempt_count smallint NOT NULL,
    status text NOT NULL,
    last_error text,
    created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Monitoring_Price_ALL_run_type_check"
        CHECK (run_type IN ('DAILY', 'RECOVERY')),
    CONSTRAINT "Monitoring_Price_ALL_attempt_check"
        CHECK ((run_type = 'DAILY' AND attempt_count = 1)
            OR (run_type = 'RECOVERY' AND attempt_count = 2)),
    CONSTRAINT "Monitoring_Price_ALL_status_check"
        CHECK (status IN ('SUCCESS', 'PARTIAL', 'FAILED', 'SKIPPED', 'NEEDS_REVIEW')),
    CONSTRAINT "Monitoring_Price_ALL_counts_check"
        CHECK (
            expected_symbols >= 0
            AND queried_symbols >= 0
            AND updated_symbols >= 0
            AND missing_symbols >= 0
            AND queried_symbols <= expected_symbols
            AND updated_symbols <= queried_symbols
            AND missing_symbols = queried_symbols - updated_symbols
        ),
    CONSTRAINT "Monitoring_Price_ALL_missing_list_check"
        CHECK (jsonb_typeof(missing_symbol_list) = 'array'),
    CONSTRAINT "Monitoring_Price_ALL_timeframe_check"
        CHECK (timeframe = '1d'),
    CONSTRAINT "Monitoring_Price_ALL_finished_check"
        CHECK (finished_at >= run_time),
    CONSTRAINT "Monitoring_Price_ALL_run_key"
        UNIQUE (exchange, asset_type, timeframe, update_for_date, run_type)
);

CREATE INDEX IF NOT EXISTS "Monitoring_Price_ALL_date_status_idx"
    ON public."Monitoring_Price_ALL" (update_for_date DESC, status);

COMMENT ON TABLE public."Monitoring_Price_ALL" IS
    'Operational results for daily and recovery IDX price-update runs.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".exchange IS
    'Exchange copied from IDX_Stock_Universe for the monitored group.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".asset_type IS
    'Security Type copied from IDX_Stock_Universe for the monitored group.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".expected_symbols IS
    'Distinct universe tickers in the exchange and asset-type group at run time.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".missing_symbol_list IS
    'JSON array of tickers still missing after this run.';
COMMENT ON COLUMN public."Monitoring_Price_ALL".update_for_date IS
    'Trading date targeted by the run.';

COMMIT;
