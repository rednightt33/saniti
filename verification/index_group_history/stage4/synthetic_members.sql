\set ON_ERROR_STOP 1
BEGIN;
SET session_replication_role = replica;
UPDATE "Feature_Index_Entity" SET rows_from = '2025-07-01' WHERE ticker <> 'IHSG';
-- LQ45 (local only): first record 2025-03-03 (counted from 2025-03-04) AMMN, BRMS, MEGA; NCKL recorded 2025-07-14
-- (counted from 2025-07-15); MEGA leaves, recorded 2025-09-01 (out from 2025-09-02)
INSERT INTO "Stock_List_Member_History" (list_key,"Ticker",valid_from,valid_to,valid_basis,available_at,available_basis,
  recorded_from,recorded_to,superseded_reason,run_id,source_provenance)
SELECT 'INDEX:550', t, v::date, NULL, valid_basis, rec::timestamptz, available_basis, rec::timestamptz,
  CASE WHEN t='MEGA' THEN '2025-09-01 03:00+00'::timestamptz END, CASE WHEN t='MEGA' THEN 'CHANGE_CAPTURED' END, run_id, source_provenance
FROM (SELECT * FROM "Stock_List_Member_History" LIMIT 1) x,
 (VALUES ('AMMN','2025-03-03','2025-03-03 03:00+00'),('BRMS','2025-03-03','2025-03-03 03:00+00'),('MEGA','2025-03-03','2025-03-03 03:00+00'),
         ('NCKL','2025-07-14','2025-07-14 03:00+00')) v(t,v,rec);
-- universe: first capture 2025-03-03; CITA first seen 2025-06-02; BWPT moves to Basic Materials, recorded 2025-08-04
UPDATE "IDX_Stock_Universe_History" SET valid_from='2025-03-03', recorded_from='2025-03-03 03:00+00', available_at='2025-03-03 03:00+00'
 WHERE "Security Type"='stock';
UPDATE "IDX_Stock_Universe_History" SET valid_from='2025-06-02', recorded_from='2025-06-02 03:00+00', available_at='2025-06-02 03:00+00'
 WHERE "Ticker"='CITA';
UPDATE "IDX_Stock_Universe_History" SET recorded_to='2025-08-04 03:00+00', superseded_reason='CHANGE_CAPTURED'
 WHERE "Ticker"='BWPT' AND "Sector"='Consumer Non-Cyclicals';
INSERT INTO "IDX_Stock_Universe_History" ("Ticker","Company Name","Exchange","Security Type","Type Specs","Is Common Stock","ISIN",
  "Sector","Industry",valid_from,valid_to,valid_basis,available_at,available_basis,recorded_from,recorded_to,superseded_reason,capture_id,source_provenance)
SELECT "Ticker","Company Name","Exchange","Security Type","Type Specs","Is Common Stock","ISIN",'Basic Materials',"Industry",
  '2025-08-04',NULL,valid_basis,'2025-08-04 03:00+00',available_basis,'2025-08-04 03:00+00',NULL,NULL,capture_id,source_provenance
FROM "IDX_Stock_Universe_History" WHERE "Ticker"='BWPT';
COMMIT;
SELECT list_key,"Ticker",pit_valid_from,pit_valid_to FROM "Stock_List_Member_History" WHERE list_key='INDEX:550' ORDER BY 2;
SELECT "Ticker","Sector",pit_valid_from,pit_valid_to FROM "IDX_Stock_Universe_History" WHERE "Security Type"='stock' ORDER BY 1,3;
