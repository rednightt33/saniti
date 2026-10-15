-- EXEC-BE1-2 (user 2026-10-15, "Ok, kita update saja kolom katalog untuk 2 kolom itu ya"; go "Ok jalankan"): the AI
-- catalog says what total_buy_value and total_sell_value of Feature_03_Stock_Broker_Daily can and cannot carry.
-- Summed over every broker the two are equal by construction (each trade has a buyer and a seller); their difference
-- is zero from 2021 and, in 2016-2020, a gap in the source Broker Summary (about 7% of Regular rows), never net demand
-- (ERRORS M154 a, M157; evidence verification/feature03/BUY_SELL_IDENTITY.md, measured 2026-10-15).
-- Changes text only: AI_column_catalog description and description_id (DRAFT) of the two columns, and the active
-- Feature_Catalog v2 misuse_warning and validation_evidence of the two features. No formula, status or data changes;
-- Column_Catalog follows Feature_Catalog through scripts/sync_database_catalog.py.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM public."AI_column_catalog"
        WHERE table_name = 'Feature_03_Stock_Broker_Daily'
          AND ((column_name = 'total_buy_value'
                AND description = 'Sum of all broker buy_value_1d for the ticker, date and board.')
            OR (column_name = 'total_sell_value'
                AND description = 'Sum of all broker sell_value_1d for the ticker, date and board.'))) <> 2 THEN
        RAISE EXCEPTION 'AI_column_catalog descriptions of total_buy_value/total_sell_value are not the expected ones';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table = 'Feature_03_Stock_Broker_Daily' AND feature_column IN ('total_buy_value', 'total_sell_value')
          AND version = 'v2' AND is_active AND misuse_warning NOT LIKE '%equal by construction%') <> 2 THEN
        RAISE EXCEPTION 'Expected the two active v2 Feature_Catalog rows without the buy/sell identity note';
    END IF;
END
$preflight$;

UPDATE public."AI_column_catalog" SET
    description = CASE column_name
        WHEN 'total_buy_value' THEN 'Sum of all broker buy_value_1d for the ticker, date and board. '
        ELSE 'Sum of all broker sell_value_1d for the ticker, date and board. ' END
        || 'Every trade has a buying and a selling broker, so over all brokers total_buy_value and total_sell_value '
        || 'are equal by construction: from 2021 they are equal on every row but four; in 2016-2020 the source '
        || 'Broker Summary leaves about 7% of Regular rows unequal by a few percent. Their difference (equal to '
        || 'foreign_net_value + domestic_net_value) is therefore zero or a source gap, never net buying or selling '
        || 'demand; read accumulation from per-broker or per-investor-type net (positive_net_value_total, '
        || 'foreign_net_value, domestic_net_value).',
    description_id = CASE column_name
        WHEN 'total_buy_value' THEN 'Jumlah semua buy_value_1d broker untuk kode saham, tanggal, dan papan. '
        ELSE 'Jumlah semua sell_value_1d broker untuk kode saham, tanggal, dan papan. ' END
        || 'Setiap transaksi punya broker pembeli dan broker penjual, sehingga atas semua broker total_buy_value dan '
        || 'total_sell_value sama menurut konstruksinya: sejak 2021 sama di semua baris kecuali empat; pada 2016-2020 '
        || 'sumber Broker Summary menyisakan sekitar 7% baris papan Regular yang berbeda beberapa persen. Selisih '
        || 'keduanya (sama dengan foreign_net_value + domestic_net_value) karena itu nol atau celah data sumber, bukan '
        || 'permintaan beli atau jual bersih; baca akumulasi dari net per broker atau per tipe investor '
        || '(positive_net_value_total, foreign_net_value, domestic_net_value).',
    description_id_status = 'DRAFT',
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'Feature_03_Stock_Broker_Daily' AND column_name IN ('total_buy_value', 'total_sell_value');

UPDATE public."Feature_Catalog" SET
    misuse_warning = misuse_warning || ' Over all brokers total buy and total sell value are equal by construction '
        || '(each trade has a buyer and a seller): from 2021 equal on every row but four, in 2016-2020 unequal on '
        || 'about 7% of Regular rows because of the source Broker Summary. Never read their difference as net '
        || 'demand or accumulation; use per-broker or per-investor-type net values.',
    validation_evidence = ARRAY(
        SELECT DISTINCT x FROM unnest(validation_evidence || ARRAY['verification/feature03/BUY_SELL_IDENTITY.md']) x
        ORDER BY x),
    updated_at = CURRENT_TIMESTAMP
WHERE feature_table = 'Feature_03_Stock_Broker_Daily' AND feature_column IN ('total_buy_value', 'total_sell_value')
  AND version = 'v2' AND is_active;

DO $verify$
BEGIN
    IF (SELECT count(*) FROM public."AI_column_catalog"
        WHERE table_name = 'Feature_03_Stock_Broker_Daily' AND column_name IN ('total_buy_value', 'total_sell_value')
          AND description LIKE '%equal by construction%' AND description_id LIKE '%sama menurut konstruksinya%'
          AND description_id_status = 'DRAFT' AND documentation_status = 'VERIFIED') <> 2 THEN
        RAISE EXCEPTION 'AI_column_catalog rows were not updated as planned';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table = 'Feature_03_Stock_Broker_Daily' AND feature_column IN ('total_buy_value', 'total_sell_value')
          AND version = 'v2' AND is_active AND misuse_warning LIKE '%equal by construction%'
          AND 'verification/feature03/BUY_SELL_IDENTITY.md' = ANY (validation_evidence)
          AND semantic_review_status = 'CALCULATION_VERIFIED') <> 2 THEN
        RAISE EXCEPTION 'Feature_Catalog rows were not updated as planned';
    END IF;
END
$verify$;

COMMIT;
