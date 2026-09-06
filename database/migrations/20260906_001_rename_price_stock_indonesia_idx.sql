BEGIN;

DO $migration$
BEGIN
    IF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NOT NULL
       AND to_regclass('public."price_stock_indonesia_IDX"') IS NULL THEN
        NULL;
    ELSIF to_regclass('public."Price_Stock_Indonesia_IDX"') IS NULL
          AND to_regclass('public."price_stock_indonesia_IDX"') IS NOT NULL THEN
        ALTER TABLE public."price_stock_indonesia_IDX"
            RENAME TO "Price_Stock_Indonesia_IDX";
    ELSE
        RAISE EXCEPTION
            'Expected exactly one of public."price_stock_indonesia_IDX" or public."Price_Stock_Indonesia_IDX" to exist';
    END IF;
END
$migration$;

DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'price_stock_indonesia_IDX_pkey'
          AND conrelid = 'public."Price_Stock_Indonesia_IDX"'::regclass
    ) THEN
        ALTER TABLE public."Price_Stock_Indonesia_IDX"
            RENAME CONSTRAINT "price_stock_indonesia_IDX_pkey"
            TO "Price_Stock_Indonesia_IDX_pkey";
    END IF;

    IF to_regclass('public.price_stock_indonesia_idx_date_idx') IS NOT NULL
       AND to_regclass('public."Price_Stock_Indonesia_IDX_date_idx"') IS NULL THEN
        ALTER INDEX public.price_stock_indonesia_idx_date_idx
            RENAME TO "Price_Stock_Indonesia_IDX_date_idx";
    END IF;
END
$migration$;

COMMIT;
