CREATE OR REPLACE FUNCTION public.validate_feature_catalog_target()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.is_active THEN
        IF NEW.feature_table !~ '^Feature_[0-9]{2}_[A-Za-z0-9_]+$' THEN
            RAISE EXCEPTION 'Active Feature table name % is not governed', NEW.feature_table;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = NEW.feature_table
              AND column_name = NEW.feature_column
        ) THEN
            RAISE EXCEPTION 'Active catalog target %.% does not exist',
                NEW.feature_table, NEW.feature_column;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public."Table_Catalog"
            WHERE table_schema = 'public' AND table_name = NEW.feature_table
              AND category = 'Feature' AND documentation_status = 'VERIFIED'
        ) THEN
            RAISE EXCEPTION 'Active Feature table % is not VERIFIED in Table_Catalog',
                NEW.feature_table;
        END IF;
    END IF;
    RETURN NEW;
END
$function$
