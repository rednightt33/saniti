BEGIN;

DO $guard$
BEGIN
    IF to_regclass('public."Feature04_Technical_Indicator"') IS NULL
       OR to_regclass('public."Universe_Fixed_income"') IS NULL
       OR to_regclass('public."Price_Fixed_Income"') IS NULL
       OR to_regclass('public."Monitoring_Fixed_Income"') IS NULL
       OR to_regclass('public."Database_Table_Status"') IS NULL THEN
        RAISE EXCEPTION 'Required Feature04/fixed-income documentation objects are missing';
    END IF;
    IF NOT EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='Feature04_Technical_Indicator'
          AND column_name='asset_type'
    ) THEN
        RAISE EXCEPTION 'Feature04 asset_type migration must be applied first';
    END IF;
END
$guard$;

COMMENT ON TABLE public."Feature04_Technical_Indicator" IS
'56-column cross-asset daily technical Feature04. Identity is asset_type/ticker/trade_date/Daily; asset_type is resolved from approved equity or fixed-income universe membership.';
COMMENT ON TABLE public."Universe_Fixed_income" IS
'Approved fixed-income instruments and their TradingView price/yield series classification.';
COMMENT ON TABLE public."Price_Fixed_Income" IS
'TradingView fixed-income OHLC observations separated by metric_type and Timeframe; Feature04 consumes price/1D only.';
COMMENT ON TABLE public."Monitoring_Fixed_Income" IS
'Operational result for one independent fixed-income daily or recovery cron execution.';

INSERT INTO public."Database_Table_Status"(
    "Table Name","Table Category","Update Pattern","Latest Data Date",
    "Last Changed At","Last Checked At","Tracking Status","Last Operation"
)
VALUES
(
    'Universe_Fixed_income','Reference','Periodic / when the fixed-income universe changes',NULL,
    CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'Baseline only','BASELINE'
),
(
    'Price_Fixed_Income','Transactional','Daily and recovery fixed-income price/yield schedules',
    (SELECT max(date) FROM public."Price_Fixed_Income"),
    coalesce((SELECT max(ingestion_time) FROM public."Price_Fixed_Income"),CURRENT_TIMESTAMP),
    CURRENT_TIMESTAMP,'Latest date and write time derived from fixed-income observations','LOAD'
),
(
    'Monitoring_Fixed_Income','Monitoring','One row after each fixed-income daily or recovery execution',
    (SELECT max(target_date) FROM public."Monitoring_Fixed_Income"),
    coalesce((SELECT max(finished_at) FROM public."Monitoring_Fixed_Income"),CURRENT_TIMESTAMP),
    CURRENT_TIMESTAMP,'Derived from fixed-income cron monitoring rows','INSERT'
)
ON CONFLICT("Table Name") DO UPDATE SET
    "Table Category"=EXCLUDED."Table Category",
    "Update Pattern"=EXCLUDED."Update Pattern",
    "Latest Data Date"=EXCLUDED."Latest Data Date",
    "Last Changed At"=EXCLUDED."Last Changed At",
    "Last Checked At"=EXCLUDED."Last Checked At",
    "Tracking Status"=EXCLUDED."Tracking Status",
    "Last Operation"=EXCLUDED."Last Operation";

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."Database_Table_Status"
        WHERE "Table Name" IN ('Universe_Fixed_income','Price_Fixed_Income','Monitoring_Fixed_Income')) <> 3 THEN
        RAISE EXCEPTION 'Fixed-income status documentation is incomplete';
    END IF;
END
$verify$;

COMMIT;
