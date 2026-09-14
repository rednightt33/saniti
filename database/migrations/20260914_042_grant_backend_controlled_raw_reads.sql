-- Permit only the credentialed backend to construct controlled raw-data snapshots.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
DECLARE table_name text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='market_ai_app') THEN
        RAISE EXCEPTION 'market_ai_app role is required';
    END IF;
    FOREACH table_name IN ARRAY ARRAY[
        'Price_Stock_Indonesia_IDX','IDX_Broker_Summary','IDX_Stock_Universe',
        'Universe_Equity_Description','IDX_Broker_Profile'
    ] LOOP
        IF to_regclass(format('public.%I',table_name)) IS NULL THEN
            RAISE EXCEPTION 'Required catalog-approved table is missing: %',table_name;
        END IF;
    END LOOP;
END
$preflight$;

GRANT SELECT ON
    public."Price_Stock_Indonesia_IDX",
    public."IDX_Broker_Summary",
    public."IDX_Stock_Universe",
    public."Universe_Equity_Description",
    public."IDX_Broker_Profile"
TO market_ai_app;

REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON
    public."Price_Stock_Indonesia_IDX",
    public."IDX_Broker_Summary",
    public."IDX_Stock_Universe",
    public."Universe_Equity_Description",
    public."IDX_Broker_Profile"
FROM market_ai_app;

REVOKE ALL ON
    public."Price_Stock_Indonesia_IDX",
    public."IDX_Broker_Summary",
    public."IDX_Stock_Universe",
    public."Universe_Equity_Description",
    public."IDX_Broker_Profile"
FROM market_query_sandbox,market_statistical_worker,market_analytics_worker;

DO $validate$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'Price_Stock_Indonesia_IDX','IDX_Broker_Summary','IDX_Stock_Universe',
        'Universe_Equity_Description','IDX_Broker_Profile'
    ] LOOP
        IF NOT has_table_privilege('market_ai_app',format('public.%I',table_name),'SELECT') THEN
            RAISE EXCEPTION 'market_ai_app SELECT grant missing for %',table_name;
        END IF;
        IF has_table_privilege('market_ai_app',format('public.%I',table_name),'INSERT,UPDATE,DELETE') THEN
            RAISE EXCEPTION 'market_ai_app unexpectedly has raw mutation privilege on %',table_name;
        END IF;
        IF has_table_privilege('market_query_sandbox',format('public.%I',table_name),'SELECT')
           OR has_table_privilege('market_statistical_worker',format('public.%I',table_name),'SELECT')
           OR has_table_privilege('market_analytics_worker',format('public.%I',table_name),'SELECT') THEN
            RAISE EXCEPTION 'A worker role unexpectedly has raw SELECT on %',table_name;
        END IF;
    END LOOP;
END
$validate$;

COMMIT;
