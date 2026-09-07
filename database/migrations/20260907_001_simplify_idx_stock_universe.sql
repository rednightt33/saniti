BEGIN;

ALTER TABLE public."IDX_Stock_Universe"
    DROP COLUMN IF EXISTS "Average Volume 10D",
    DROP COLUMN IF EXISTS "Market Cap",
    DROP COLUMN IF EXISTS "Number of Shareholders",
    DROP COLUMN IF EXISTS "Number of Employees",
    DROP COLUMN IF EXISTS "Sector Translated",
    DROP COLUMN IF EXISTS "Industry Translated",
    ADD COLUMN IF NOT EXISTS "Sector" text,
    ADD COLUMN IF NOT EXISTS "Industry" text;

DO $check$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public."IDX_Stock_Universe" AS stock
        LEFT JOIN public."Universe_Equity_Description" AS description
            ON description."Ticker" = stock."Ticker"
        WHERE description."Ticker" IS NULL
           OR NULLIF(BTRIM(description."Sector"), '') IS NULL
           OR NULLIF(BTRIM(description."Industry"), '') IS NULL
    ) THEN
        RAISE EXCEPTION
            'IDX_Stock_Universe contains ticker(s) without complete Sector/Industry mapping';
    END IF;
END
$check$;

UPDATE public."IDX_Stock_Universe" AS stock
SET
    "Sector" = description."Sector",
    "Industry" = description."Industry"
FROM public."Universe_Equity_Description" AS description
WHERE description."Ticker" = stock."Ticker"
  AND (
      stock."Sector" IS DISTINCT FROM description."Sector"
      OR stock."Industry" IS DISTINCT FROM description."Industry"
  );

ALTER TABLE public."IDX_Stock_Universe"
    ALTER COLUMN "Sector" SET NOT NULL,
    ALTER COLUMN "Industry" SET NOT NULL;

COMMIT;
