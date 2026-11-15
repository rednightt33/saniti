-- EXEC-INDEX-GROUP-HISTORY stage 3 fix (ERRORS M438): Price_Stock_Indonesia_IDX.ticker varchar(4) -> varchar(12), the
-- INDEX ticker rule of Feature_Index_Entity ('^[A-Z0-9]{1,12}$', the terminal-api and edge-bff ticker rule). The price
-- history job of 2026-11-15 stored 5 indexes of 4 letters or fewer and was refused for the 38 longer ones ("value too
-- long" on COPY); the daily price cron reads the same universe, so its batch would fail the same way until this is
-- applied.
-- How: the one trigger that names the column (idx_price_optional_volume_guard, UPDATE OF ticker, volume) is dropped and
-- created again unchanged in the same transaction (PostgreSQL refuses to change a column a trigger definition uses).
-- A longer varchar limit does not rewrite the table (rehearsed: the table file is unchanged); the partial index
-- Price_Stock_Indonesia_IDX_final_idx (ticker, date DESC WHERE is_final AND Daily, 44 MB on dev) is rebuilt while the
-- table is locked (seconds). No view depends on the column; the one foreign key that references it
-- (Feature_Calculation_Queue (ticker, price_date)) has a text ticker. No row changes.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

DO $preflight$
BEGIN
    IF (SELECT format_type(atttypid, atttypmod) FROM pg_attribute
         WHERE attrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass AND attname = 'ticker') <> 'character varying(4)' THEN
        RAISE EXCEPTION 'Price_Stock_Indonesia_IDX.ticker is not varchar(4): reconcile before applying';
    END IF;
    IF (SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass
         AND tgname = 'idx_price_optional_volume_guard')
       <> 'CREATE TRIGGER idx_price_optional_volume_guard BEFORE INSERT OR UPDATE OF ticker, volume ON public."Price_Stock_Indonesia_IDX" FOR EACH ROW EXECUTE FUNCTION validate_idx_optional_volume()' THEN
        RAISE EXCEPTION 'idx_price_optional_volume_guard differs from the definition read on dev 2026-11-15';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
                WHERE d.refobjid = 'public."Price_Stock_Indonesia_IDX"'::regclass AND r.ev_class <> d.refobjid) THEN
        RAISE EXCEPTION 'a view depends on Price_Stock_Indonesia_IDX: reconcile before applying';
    END IF;
END $preflight$;

DROP TRIGGER idx_price_optional_volume_guard ON public."Price_Stock_Indonesia_IDX";
ALTER TABLE public."Price_Stock_Indonesia_IDX" ALTER COLUMN ticker TYPE character varying(12);
CREATE TRIGGER idx_price_optional_volume_guard BEFORE INSERT OR UPDATE OF ticker, volume ON public."Price_Stock_Indonesia_IDX"
    FOR EACH ROW EXECUTE FUNCTION validate_idx_optional_volume();

DO $check$ BEGIN
    IF (SELECT format_type(atttypid, atttypmod) FROM pg_attribute
         WHERE attrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass AND attname = 'ticker') <> 'character varying(12)' THEN
        RAISE EXCEPTION 'ticker is not varchar(12) after the change';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass
                    AND tgname = 'idx_price_optional_volume_guard' AND tgenabled = 'O') THEN
        RAISE EXCEPTION 'idx_price_optional_volume_guard is missing or disabled';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_index WHERE indrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass AND NOT (indisvalid AND indisready)) THEN
        RAISE EXCEPTION 'an index of Price_Stock_Indonesia_IDX is not valid after the change';
    END IF;
END $check$;

COMMIT;

-- Rollback (only with the user's go, and only while no ticker longer than 4 is stored):
-- BEGIN; DROP TRIGGER idx_price_optional_volume_guard ON public."Price_Stock_Indonesia_IDX";
-- ALTER TABLE public."Price_Stock_Indonesia_IDX" ALTER COLUMN ticker TYPE character varying(4);
-- CREATE TRIGGER idx_price_optional_volume_guard BEFORE INSERT OR UPDATE OF ticker, volume ON public."Price_Stock_Indonesia_IDX"
--     FOR EACH ROW EXECUTE FUNCTION validate_idx_optional_volume();
-- COMMIT;
