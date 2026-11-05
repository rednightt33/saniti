-- EXEC-UNIVERSE-BROKER L3 (user go 2026-11-05: "Untuk point nomor 4 OK --> masukan exec ... Jalankan. Go"):
-- the Feature 01 worker claims every due item of one ticker together and, for several items, refreshes the whole ticker
-- once (apps/feature-01-worker/worker.py, test_worker_db.py). No table or function changes; only the catalog text of
-- the queue and the log says so. The SQL routines are unchanged (the INDEX bootstrap clones
-- refresh_feature_01_stock_daily, 20261025_011).
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $preflight$
BEGIN
    IF (SELECT update_rule FROM public."Table_Catalog"
        WHERE table_schema = 'public' AND table_name = 'Feature_Calculation_Log')
       IS DISTINCT FROM 'The Feature 01 worker records one completed result for every claim, including retries and expired leases.'
    OR (SELECT update_rule FROM public."Table_Catalog"
        WHERE table_schema = 'public' AND table_name = 'Feature_Calculation_Queue')
       IS DISTINCT FROM 'A price-row trigger transactionally creates/reopens work; a separate worker claims, calculates, retries, and completes it.'
    THEN
        RAISE EXCEPTION 'Feature 01 queue/log catalog text differs from 20260913_006; nothing changed';
    END IF;
END
$preflight$;

UPDATE public."Table_Catalog"
SET update_rule = 'The Feature 01 worker records one completed result for every claimed queue item, including retries, '
                  'superseded items and expired leases; a claim of several items of one ticker writes one row per item '
                  '(rows_refreshed on the first).',
    updated_at = now()
WHERE table_schema = 'public' AND table_name = 'Feature_Calculation_Log';

UPDATE public."Table_Catalog"
SET update_rule = 'A price-row trigger transactionally creates/reopens work; a separate worker claims the due items of '
                  'one ticker together, calculates (one item: its row and the 120 following; several: the whole ticker '
                  'once), retries, and completes them.',
    updated_at = now()
WHERE table_schema = 'public' AND table_name = 'Feature_Calculation_Queue';

DO $postcheck$
BEGIN
    IF (SELECT count(*) FROM public."Table_Catalog"
        WHERE table_schema = 'public' AND table_name IN ('Feature_Calculation_Log', 'Feature_Calculation_Queue')
          AND update_rule LIKE '%one ticker%') <> 2 THEN
        RAISE EXCEPTION 'Feature 01 queue/log catalog text was not updated';
    END IF;
END
$postcheck$;

COMMIT;
