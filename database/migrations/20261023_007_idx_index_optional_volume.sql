BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';

-- Index providers may publish OHLC without volume. Never turn absence into zero.
ALTER TABLE public."Price_Stock_Indonesia_IDX" ALTER COLUMN volume DROP NOT NULL;
ALTER TABLE public."Feature_01_Stock_Daily" ALTER COLUMN volume DROP NOT NULL;

CREATE OR REPLACE FUNCTION public.validate_idx_optional_volume()
RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  IF NEW.volume IS NULL AND NOT EXISTS (
    SELECT 1 FROM public."IDX_Stock_Universe" u
    WHERE u."Ticker"=NEW.ticker AND u."Security Type"='index'
  ) THEN
    RAISE EXCEPTION 'Missing volume is allowed only for an IDX universe index: %',NEW.ticker
      USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END
$function$;
COMMENT ON FUNCTION public.validate_idx_optional_volume() IS
  'Accept absent volume only for an index identified by IDX_Stock_Universe; keep stock volume mandatory.';
CREATE TRIGGER idx_price_optional_volume_guard
BEFORE INSERT OR UPDATE OF ticker,volume ON public."Price_Stock_Indonesia_IDX"
FOR EACH ROW EXECUTE FUNCTION public.validate_idx_optional_volume();
CREATE TRIGGER feature01_optional_volume_guard
BEFORE INSERT OR UPDATE OF ticker,volume ON public."Feature_01_Stock_Daily"
FOR EACH ROW EXECUTE FUNCTION public.validate_idx_optional_volume();

COMMENT ON COLUMN public."Price_Stock_Indonesia_IDX".volume IS
 'Source trading volume; NULL only for a universe-classified index whose provider has no volume. Zero is an observed zero, not a replacement for missing volume.';
COMMENT ON COLUMN public."Feature_01_Stock_Daily".volume IS
 'Exact source volume. NULL for an OHLC-only universe index; all volume-dependent features remain NULL without their required volume observations.';

UPDATE public."Column_Catalog" SET is_nullable=true,
 null_rule='NULL only for a universe-classified index without source volume; stock volume is required. Zero denotes an observed zero, never missing data.',
 updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN ('Price_Stock_Indonesia_IDX','Feature_01_Stock_Daily') AND column_name='volume';

UPDATE public."Feature_Catalog" SET
 null_rule='NULL for a universe-classified index without source volume. Stock volume is required and nonnegative; missing volume is never imputed as zero.',
 updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature_01_Stock_Daily' AND feature_column='volume' AND is_active;
UPDATE public."Feature_Catalog" SET
 availability_rule=coalesce(availability_rule,'') || ' An OHLC-only universe index has NULL source volume; this volume-derived feature remains NULL.',
 updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature_01_Stock_Daily'
 AND feature_column IN ('volume_avg_20d','volume_std_20d','volume_ratio_20d','volume_zscore_20d') AND is_active;

UPDATE public."Feature_Catalog" SET
 availability_rule=coalesce(availability_rule,'') || ' Universe-classified indices may have absent volume: valid OHLC remains eligible; the source symbol must match its universe mapping.',
 validation_evidence=array_append(validation_evidence,'verification/ihsg_price_history/APPLY.md'),
 updated_at=CURRENT_TIMESTAMP
WHERE feature_table='Feature_04_Technical_Indicator' AND is_active;

UPDATE public."Table_Catalog" SET
 related_functions=array_append(related_functions,'validate_idx_optional_volume()'),
 source_code_paths=array_append(source_code_paths,'database/migrations/20261023_007_idx_index_optional_volume.sql'),
 updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN ('Price_Stock_Indonesia_IDX','Feature_01_Stock_Daily');

UPDATE public."Table_Catalog" SET
 definition=definition || ' Includes universe-classified benchmark indices: missing index volume is NULL, and index price levels are in points.',
 updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN ('Price_Stock_Indonesia_IDX','Feature_01_Stock_Daily');
UPDATE public."Feature_Catalog" SET unit='source price unit',updated_at=CURRENT_TIMESTAMP
WHERE feature_table IN ('Feature_01_Stock_Daily','Feature_04_Technical_Indicator') AND is_active AND unit='IDR';
UPDATE public."Column_Catalog" SET unit='source price unit',updated_at=CURRENT_TIMESTAMP
WHERE table_schema='public' AND table_name IN ('Feature_01_Stock_Daily','Feature_04_Technical_Indicator') AND unit='IDR';
COMMIT;
