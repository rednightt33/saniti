\set ON_ERROR_STOP 0
\echo == 1 IHSG broker row (legacy entity, new date): expect OK
BEGIN; INSERT INTO "Feature_06_Foreign_Domestic_INDEX" SELECT * FROM "Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' LIMIT 0;
WITH s AS (SELECT * FROM "Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' ORDER BY trade_date LIMIT 1)
INSERT INTO "Feature_06_Foreign_Domestic_INDEX" SELECT (jsonb_populate_record(NULL::"Feature_06_Foreign_Domestic_INDEX", to_jsonb(s) || '{"trade_date":"2015-06-01"}')).* FROM s; ROLLBACK;
\echo == 2 group GSALIM in Feature 06 on 2024-01-02: expect OK
BEGIN; WITH s AS (SELECT * FROM "Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' LIMIT 1)
INSERT INTO "Feature_06_Foreign_Domestic_INDEX" SELECT (jsonb_populate_record(NULL::"Feature_06_Foreign_Domestic_INDEX", to_jsonb(s) || '{"ticker":"GSALIM","trade_date":"2024-01-02"}')).* FROM s; ROLLBACK;
\echo == 3 group GSALIM in Feature 01: expect refusal (no price)
BEGIN; WITH s AS (SELECT * FROM "Feature_01_Stock_Daily_INDEX" WHERE ticker='IHSG' LIMIT 1)
INSERT INTO "Feature_01_Stock_Daily_INDEX" SELECT (jsonb_populate_record(NULL::"Feature_01_Stock_Daily_INDEX", to_jsonb(s) || '{"ticker":"GSALIM","date":"2024-01-02"}')).* FROM s; ROLLBACK;
\echo == 4 LQ45 in Feature 06 before its universe row: expect refusal (not a universe index yet)
BEGIN; WITH s AS (SELECT * FROM "Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' LIMIT 1)
INSERT INTO "Feature_06_Foreign_Domestic_INDEX" SELECT (jsonb_populate_record(NULL::"Feature_06_Foreign_Domestic_INDEX", to_jsonb(s) || '{"ticker":"LQ45","trade_date":"2024-01-02"}')).* FROM s; ROLLBACK;
\echo == 5 GSALIM before rows_from (2023-12-29): expect refusal
BEGIN; WITH s AS (SELECT * FROM "Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' LIMIT 1)
INSERT INTO "Feature_06_Foreign_Domestic_INDEX" SELECT (jsonb_populate_record(NULL::"Feature_06_Foreign_Domestic_INDEX", to_jsonb(s) || '{"ticker":"GSALIM","trade_date":"2023-12-29"}')).* FROM s; ROLLBACK;
\echo == 6 unregistered ticker BBCA: expect refusal
BEGIN; WITH s AS (SELECT * FROM "Feature_06_Foreign_Domestic_INDEX" WHERE ticker='IHSG' LIMIT 1)
INSERT INTO "Feature_06_Foreign_Domestic_INDEX" SELECT (jsonb_populate_record(NULL::"Feature_06_Foreign_Domestic_INDEX", to_jsonb(s) || '{"ticker":"BBCA","trade_date":"2024-01-02"}')).* FROM s; ROLLBACK;
