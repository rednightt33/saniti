-- Record the completed v2 rebuild in the operational freshness ledger.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='1min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table='Feature_03_Stock_Broker_Daily' AND version='v2' AND is_active) <> 24
       OR (SELECT count(*) FROM public."Feature_03_Stock_Broker_Daily") = 0 THEN
        RAISE EXCEPTION 'Feature 03 v2 definitions or rebuilt rows are missing';
    END IF;
END
$preflight$;

UPDATE public."Database_Table_Status"
SET "Last Changed At"=(SELECT max(calculated_at) FROM public."Feature_03_Stock_Broker_Daily"),
    "Last Operation"='FULL_REBUILD_V2',
    "Tracking Status"='Derived from Investor-Type Feature 02; Feature 03 v2 refresh is manual'
WHERE "Table Name"='Feature_03_Stock_Broker_Daily';

COMMIT;
