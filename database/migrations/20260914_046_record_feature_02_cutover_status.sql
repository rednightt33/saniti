-- Record the canonical replacement in the operational status and routine provenance.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='1min';

DO $preflight$
BEGIN
    IF to_regclass('public."Feature_02_Broker_Rolling_v2"') IS NOT NULL
       OR (SELECT count(*) FROM public."Feature_Catalog"
           WHERE feature_table='Feature_02_Broker_Rolling' AND version='v2' AND is_active) <> 38 THEN
        RAISE EXCEPTION 'Feature 02 v2 cutover is not verified';
    END IF;
END
$preflight$;

UPDATE public."Database_Table_Status"
SET "Last Changed At"=CURRENT_TIMESTAMP,
    "Last Operation"='CUTOVER_V2',
    "Tracking Status"='Derived from IDX_Broker_Summary; Investor-Type Feature 02 v2 refresh is manual'
WHERE "Table Name"='Feature_02_Broker_Rolling';

UPDATE public."Table_Catalog"
SET source_code_paths=array_append(source_code_paths,
        'database/migrations/20260914_043_cutover_feature_02_investor_type.sql')
WHERE table_schema='public' AND table_name='Feature_03_Stock_Broker_Daily'
  AND NOT ('database/migrations/20260914_043_cutover_feature_02_investor_type.sql'
           = ANY(source_code_paths));

COMMIT;
