-- EXEC-ONBOARD-1 (user 2026-10-20: "Ok view saja ya untuk no 1. Jalankan."; "Ok untuk no 2. Ok untuk no 3. Ok untuk
-- no 4."): the first raw table and the first Feature onboarded to the AI through the catalog only
-- (NEW_TABLE_ONBOARDING_PLAN.md section 6).
--
-- 1. Price_Fixed_Income_Final: a view of the final daily bars of Price_Fixed_Income (is_final AND "Timeframe" = '1D').
--    Neither the catalog nor the SQL Governor has a row filter, so the view is the exposed object and the base table
--    stays hidden from the AI. The view keeps the analytical columns only (no volume: always NULL at the source; no
--    load or finality bookkeeping). Live read 2026-10-20: every stored row is final 1D and (ticker, date,
--    metric_type) is unique among them (121,911 rows); the verify block re-checks the uniqueness.
-- 2. Universe_Fixed_income: reference table (country, instrument, tenor, unit) with instrument_name as the entity
--    name column, so the SQL Governor derives instrument names for lookups.
-- 3. Feature_04_Technical_Indicator: cross-asset Feature (equity and bonds, asset_type). Its columns come from
--    Feature_Catalog (active v4 definitions); the Pine SMI state columns (tracking_*, temp_*, *_bar) and the
--    calculation bookkeeping (calculation_version, calculated_at) are ai_allowed = false. Each Feature column gets an
--    AI_calculation_catalog row (as 20260922_001 did for Feature 01-03); an indicator or candle column that holds a
--    formula of AI_formula_reference names it in implementation_ref ('AI_formula_reference:CALC_nnn') and in
--    parameters.formula_reference with the relation: STORED_VARIANT (the stored column implements that indicator
--    with the stored parameters; compare definitions before treating both as identical) or RELATED_NOT_IDENTICAL
--    (a TA-Lib signed pattern code against a geometric reference definition).
-- 4. AI_catalog_relationships for the safe joins; SELECT for market_ai_sql_reader (and pgweb_reader when present);
--    ai_preview_table_rows extended to the three objects (Feature 04 preview leaves out the hidden columns).
-- 5. Table_Catalog / Column_Catalog for the view (scripts/sync_database_catalog.py covers base tables only) and the
--    migration path on the three registered objects. Indonesian meanings (description_id) are DRAFT.
--
-- Not changed: Price_Fixed_Income itself, Feature_Catalog, Feature_Relationship_Catalog, the data.
-- Rollback (forward-only: write a new migration): is_active = false on the three AI_table_catalog rows and
-- is_allowed = false on their relationships; revoke the grants; restore the seven-table preview function.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '3min';

DO $preflight$
BEGIN
    IF to_regclass('public."Price_Fixed_Income_Final"') IS NOT NULL THEN
        RAISE EXCEPTION 'Price_Fixed_Income_Final already exists';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" WHERE table_name IN
               ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator', 'Price_Fixed_Income')) THEN
        RAISE EXCEPTION 'An onboarded object is already in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Catalog"
        WHERE feature_table = 'Feature_04_Technical_Indicator' AND is_active AND version = 'v4') <> 57 THEN
        RAISE EXCEPTION 'Expected 57 active v4 Feature_Catalog definitions for Feature_04_Technical_Indicator';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = 'Feature_04_Technical_Indicator') <> 57 THEN
        RAISE EXCEPTION 'Expected 57 Feature_04_Technical_Indicator columns';
    END IF;
    IF (SELECT count(*) FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name IN
        ('Price_Fixed_Income', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator')) <> 3 THEN
        RAISE EXCEPTION 'The three source objects need their Table_Catalog rows';
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('market_ai_sql_reader', 'market_ai_preview_owner',
                                                        'market_ai_preview_reader')) <> 3 THEN
        RAISE EXCEPTION 'An expected AI role is missing';
    END IF;
    IF to_regprocedure('public.ai_preview_table_rows(text)') IS NULL THEN
        RAISE EXCEPTION 'public.ai_preview_table_rows(text) is missing';
    END IF;
    IF (SELECT count(*) FROM public."AI_formula_reference" WHERE calculation_id IN
        ('CALC_021', 'CALC_022', 'CALC_028', 'CALC_032', 'CALC_033', 'CALC_034', 'CALC_040', 'CALC_042', 'CALC_049',
         'CALC_050', 'CALC_161', 'CALC_162', 'CALC_165', 'CALC_166', 'CALC_167')) <> 15 THEN
        RAISE EXCEPTION 'Expected the 15 referenced AI_formula_reference rows';
    END IF;
END
$preflight$;

-- 1. the view
CREATE VIEW public."Price_Fixed_Income_Final" AS
SELECT p."Country" AS country,
       p.instrument_name,
       p.ticker::text AS ticker,
       p.metric_type::text AS metric_type,
       p.date,
       p.open,
       p.high,
       p.low,
       p.close,
       p.value_unit::text AS value_unit
FROM public."Price_Fixed_Income" AS p
WHERE p.is_final AND p."Timeframe" = '1D';

COMMENT ON VIEW public."Price_Fixed_Income_Final" IS
    'Final daily (1D) fixed-income bars of Price_Fixed_Income: one row per ticker, metric_type (price or yield_to_maturity) and market-local date. The object exposed to the AI; the base table keeps provisional rows and bookkeeping.';

REVOKE ALL ON public."Price_Fixed_Income_Final" FROM PUBLIC;
GRANT SELECT ON public."Price_Fixed_Income_Final", public."Universe_Fixed_income",
                public."Feature_04_Technical_Indicator"
    TO market_ai_sql_reader, market_ai_preview_owner;
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
        GRANT SELECT ON public."Price_Fixed_Income_Final" TO pgweb_reader;
    END IF;
END
$grant$;

-- 2. AI_table_catalog
INSERT INTO public."AI_table_catalog" (
    table_name, description, category, grain, primary_key_columns, time_column, entity_column, owner, is_active,
    ai_access_level, freshness_sla, coverage_enabled, documentation_status, data_domain, entity_type, asset_type,
    supported_frequencies, time_semantics, subject_metadata_status, row_presence, row_presence_status)
VALUES
    ('Price_Fixed_Income_Final',
     'Final daily government bond benchmark bars (Indonesia and United States, tenors 1 month to 30 years) from TradingView: open, high, low and close of the bond price (metric_type price) and of the bond yield (metric_type yield_to_maturity), with the unit of each row in value_unit. Use it for government bond yields (for example the Indonesia 10-year yield, ticker ID10Y with metric_type yield_to_maturity) and bond prices. Always filter metric_type: price and yield share the ticker. Instrument names, country and tenor are in Universe_Fixed_income.',
     'TRANSACTIONAL', 'One row per ticker, metric_type and market-local trading date (final daily bar)',
     ARRAY['ticker', 'metric_type', 'date'], 'date', 'ticker', 'Saniti', true, 'BOUNDED_READ', interval '1 day', true,
     'PARTIAL', 'MARKET', 'BOND', 'GOVERNMENT_BOND', ARRAY['1D'],
     'Market-local trading date of each country (Indonesia Asia/Jakarta, United States America/New_York); final daily bars only',
     'INFERRED', 'ACTIVITY_ONLY', 'INFERRED'),
    ('Universe_Fixed_income',
     'Current list of the government bond benchmark series Saniti loads: one row per ticker and metric_type (price or yield_to_maturity) with region, country, instrument name, tenor and the unit of its values. Use it to name or select bonds (by country or tenor) before reading Price_Fixed_Income_Final or the bond rows of Feature_04_Technical_Indicator.',
     'REFERENCE', 'One current row per ticker and metric_type', ARRAY['ticker', 'metric_type'], NULL, 'ticker', 'Saniti',
     true, 'BOUNDED_READ', interval '30 days', true, 'PARTIAL', 'MARKET', 'BOND', 'GOVERNMENT_BOND', ARRAY['STATIC'],
     'Current-state reference data; not point in time', 'INFERRED', 'NOT_APPLICABLE', 'INFERRED'),
    ('Feature_04_Technical_Indicator',
     'Daily technical indicators already calculated for every IDX stock (asset_type equity) and government bond benchmark (asset_type bonds): close, SMA 20/50, EMA 12/26/50/200, RSI 14, MACD line/signal/histogram, ATR 14, Bollinger bands 20, ADX 14, SMI, swing-high break, inside bar and 25 TA-Lib candlestick pattern codes (hammer, engulfing, doji, morning star, piercing, marubozu and others). Read the stored column instead of computing the indicator or pattern again. Filter asset_type: bond rows are calculated from the bond price series, not its yield.',
     'FEATURE', 'One row per asset_type, ticker and trading date (Daily timeframe)',
     ARRAY['ticker', 'trade_date', 'timeframe', 'asset_type'], 'trade_date', 'ticker', 'Saniti', true, 'BOUNDED_READ',
     interval '1 day', true, 'PARTIAL', 'MARKET', 'INSTRUMENT', NULL, ARRAY['1D'],
     'Source trading date of each asset: IDX trading date (Asia/Jakarta) for equity, the bond market''s local date for bonds',
     'INFERRED', 'ACTIVITY_ONLY', 'INFERRED');

-- 3. AI_column_catalog: the view
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT 'Price_Fixed_Income_Final', c.column_name, c.ordinal_position, meta.description, c.data_type, meta.semantic_type,
       meta.unit, true, c.column_name IN ('ticker', 'metric_type', 'date'), meta.source, false, true, meta.aggregations,
       true, meta.semantic_type IN ('IDENTIFIER', 'DIMENSION', 'TIME'), NULL,
       c.column_name IN ('ticker', 'date'), 'PARTIAL', meta.resample, NULL, 'HISTORICAL', meta.description_id, 'DRAFT',
       false
FROM information_schema.columns AS c
JOIN (VALUES
    ('country', 'DIMENSION', NULL, ARRAY['COUNT', 'COUNT_DISTINCT'], NULL, 'Price_Fixed_Income."Country"',
     'Country of the bond market: Indonesia or United States.',
     'Negara pasar obligasi: Indonesia atau United States.'),
    ('instrument_name', 'DIMENSION', NULL, ARRAY['COUNT', 'COUNT_DISTINCT'], NULL, 'Price_Fixed_Income.instrument_name',
     'Source name of the series, for example Indonesia 10 Year Government Bonds Yield (the yield series) or Indonesia 10 Year Government Bonds (the price series).',
     'Nama seri dari sumber, misalnya Indonesia 10 Year Government Bonds Yield (seri yield) atau Indonesia 10 Year Government Bonds (seri harga).'),
    ('ticker', 'IDENTIFIER', NULL, ARRAY['COUNT', 'COUNT_DISTINCT'], NULL, 'Price_Fixed_Income.ticker',
     'Benchmark code: country prefix ID or US, tenor and Y, for example ID10Y (Indonesia 10 year), ID01MY (1 month), US02Y. The price and the yield series share the ticker; metric_type tells them apart.',
     'Kode benchmark obligasi: awalan negara ID atau US, tenor, lalu Y, misalnya ID10Y (SUN Indonesia 10 tahun), ID01MY (1 bulan), US02Y. Seri harga dan seri yield memakai ticker yang sama; metric_type membedakannya.'),
    ('metric_type', 'DIMENSION', NULL, ARRAY['COUNT', 'COUNT_DISTINCT'], NULL, 'Price_Fixed_Income.metric_type',
     'Which series the row holds: price (bond price quote) or yield_to_maturity (yield in percent). Filter it in every query.',
     'Seri yang dimuat baris: price (kuotasi harga obligasi) atau yield_to_maturity (imbal hasil/yield dalam persen). Selalu filter kolom ini.'),
    ('date', 'TIME', NULL, ARRAY['COUNT', 'COUNT_DISTINCT', 'MIN', 'MAX'], NULL, 'Price_Fixed_Income.date',
     'Market-local trading date of the final daily bar (Indonesia Asia/Jakarta, United States America/New_York). Market holidays have no row.',
     'Tanggal perdagangan lokal pasar untuk bar harian final (Indonesia Asia/Jakarta, Amerika Serikat America/New_York). Hari libur pasar tidak punya baris.'),
    ('open', 'MEASURE', 'value_unit of the row', ARRAY['AVG', 'MEDIAN', 'MIN', 'MAX'], 'FIRST', 'Price_Fixed_Income.open',
     'Opening value of the day in the unit of value_unit (yield in percent, or the price quote).',
     'Nilai pembukaan hari itu dalam satuan value_unit (yield dalam persen, atau kuotasi harga).'),
    ('high', 'MEASURE', 'value_unit of the row', ARRAY['AVG', 'MEDIAN', 'MIN', 'MAX'], 'MAX', 'Price_Fixed_Income.high',
     'Highest value of the day in the unit of value_unit.',
     'Nilai tertinggi hari itu dalam satuan value_unit.'),
    ('low', 'MEASURE', 'value_unit of the row', ARRAY['AVG', 'MEDIAN', 'MIN', 'MAX'], 'MIN', 'Price_Fixed_Income.low',
     'Lowest value of the day in the unit of value_unit.',
     'Nilai terendah hari itu dalam satuan value_unit.'),
    ('close', 'MEASURE', 'value_unit of the row', ARRAY['AVG', 'MEDIAN', 'MIN', 'MAX'], 'LAST', 'Price_Fixed_Income.close',
     'Closing value of the day: the yield in percent (metric_type yield_to_maturity) or the price quote (metric_type price) in the unit of value_unit. A yield change is in percentage points.',
     'Nilai penutupan hari itu: yield obligasi dalam persen (metric_type yield_to_maturity) atau kuotasi harga obligasi (metric_type price) dalam satuan value_unit. Perubahan yield dinyatakan dalam poin persentase.'),
    ('value_unit', 'DIMENSION', NULL, ARRAY['COUNT', 'COUNT_DISTINCT'], NULL, 'Price_Fixed_Income.value_unit',
     'Unit label of open/high/low/close as recorded from the source: percent (yields), PCTPAR (price as percent of par) or PCTDY (the source''s quote unit of US Treasury bill price series). The PCTPAR and PCTDY meanings are inferred from the source labels.',
     'Label satuan open/high/low/close sesuai sumber: percent (yield), PCTPAR (harga sebagai persen dari nilai nominal) atau PCTDY (satuan kuotasi sumber untuk seri harga US Treasury bill). Arti PCTPAR dan PCTDY disimpulkan dari label sumber.')
) AS meta(column_name, semantic_type, unit, aggregations, resample, source, description, description_id)
  ON meta.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Price_Fixed_Income_Final';

-- 4. AI_column_catalog: the reference table (bookkeeping and source-mapping columns are not for the AI)
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT 'Universe_Fixed_income', c.column_name, c.ordinal_position, meta.description, c.data_type, meta.semantic_type,
       NULL, c.is_nullable = 'YES', c.column_name IN ('ticker', 'metric_type'), NULL, false, meta.allowed,
       ARRAY['COUNT', 'COUNT_DISTINCT'], meta.allowed, meta.allowed, NULL, c.column_name = 'ticker', 'PARTIAL', NULL,
       NULL, 'CURRENT_STATE', meta.description_id, CASE WHEN meta.description_id IS NOT NULL THEN 'DRAFT' END,
       c.column_name = 'instrument_name'
FROM information_schema.columns AS c
JOIN (VALUES
    ('region', 'DIMENSION', true, 'Geographic region of the bond market (Asia, Americas).',
     'Wilayah geografis pasar obligasi (Asia, Americas).'),
    ('country', 'DIMENSION', true, 'Country of the bond market: Indonesia or United States.',
     'Negara pasar obligasi: Indonesia atau United States.'),
    ('instrument_name', 'DIMENSION', true, 'Source name of the series (the yield series ends with Yield).',
     'Nama seri dari sumber (seri yield diakhiri kata Yield).'),
    ('ticker', 'IDENTIFIER', true, 'Benchmark code (country prefix ID or US, tenor, Y); shared by the price and the yield series of one tenor.',
     'Kode benchmark (awalan negara ID atau US, tenor, Y); dipakai bersama oleh seri harga dan seri yield satu tenor.'),
    ('exchange', 'DIMENSION', true, 'Source exchange code of the series (TVC).', 'Kode bursa sumber seri (TVC).'),
    ('security_type', 'DIMENSION', true, 'Security type of the series (government_bond_benchmark).',
     'Jenis efek seri (government_bond_benchmark).'),
    ('type_specs', 'DIMENSION', true, 'Issuer type detail (government).', 'Detail jenis penerbit (government).'),
    ('is_common_stock', 'DIMENSION', false, 'Source flag carried from the stock universe layout; not meaningful for bonds.', NULL),
    ('tradingview_country', 'DIMENSION', false, 'Country label used for the source request.', NULL),
    ('metric_type', 'DIMENSION', true, 'Which series the row describes: price or yield_to_maturity.',
     'Seri yang dijelaskan baris: price (harga) atau yield_to_maturity (yield).'),
    ('tenor', 'DIMENSION', true, 'Tenor of the benchmark as written by the source (for example 10Y, 3M).',
     'Tenor benchmark sesuai sumber (misalnya 10Y, 3M).'),
    ('updated_at', 'TIME', false, 'Time the universe row was last written (load bookkeeping).', NULL),
    ('tradingview_symbol', 'DIMENSION', false, 'Source symbol used to load the series.', NULL),
    ('value_unit', 'DIMENSION', true, 'Unit of the series values: percent (yields), PCTPAR or PCTDY (price series; meanings inferred from the source labels).',
     'Satuan nilai seri: percent (yield), PCTPAR atau PCTDY (seri harga; arti disimpulkan dari label sumber).')
) AS meta(column_name, semantic_type, allowed, description, description_id)
  ON meta.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Universe_Fixed_income';

-- 5. AI_column_catalog: Feature 04 from its active Feature_Catalog definitions
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT 'Feature_04_Technical_Indicator', c.column_name, c.ordinal_position,
       CASE c.column_name
           WHEN 'ticker' THEN 'Instrument code: the IDX stock ticker for equity rows, the bond benchmark code (for example ID10Y) for bond rows.'
           WHEN 'asset_type' THEN 'Universe-derived asset class: equity (IDX stocks) or bonds (government bond benchmarks). Filter it in every query.'
           ELSE f.definition END
         || CASE WHEN c.column_name LIKE 'cdl\_%' THEN ' Signed code: positive = bullish form, negative = bearish form, 0 = no pattern on that bar (filter <> 0 to find it); magnitude 100 standard, 80 a weaker TA-Lib form, 200 a confirmed hikkake; NULL = not enough history.'
                 WHEN c.column_name = ANY (price_like) THEN ' Price unit of the row: IDR for equity, the bond price quote for bonds.'
                 ELSE '' END
         || CASE WHEN c.column_name NOT IN ('ticker', 'trade_date', 'timeframe', 'asset_type')
                 THEN ' Bond rows are calculated from the bond price series (not its yield).' ELSE '' END,
       c.data_type,
       CASE WHEN c.column_name = 'ticker' THEN 'IDENTIFIER' WHEN c.column_name = 'trade_date' THEN 'TIME'
            WHEN f.semantic_role = 'DIMENSION' THEN 'DIMENSION' ELSE 'MEASURE' END,
       CASE WHEN c.column_name = ANY (price_like) THEN 'IDR (equity) or bond price quote (bonds)'
            WHEN c.column_name IN ('ticker', 'trade_date', 'timeframe', 'asset_type') THEN NULL
            ELSE f.unit END,
       c.is_nullable = 'YES', c.column_name IN ('ticker', 'trade_date', 'timeframe', 'asset_type'), f.calculation,
       false, NOT (c.column_name = ANY (hidden)),
       CASE WHEN c.column_name = 'trade_date' THEN ARRAY['COUNT', 'COUNT_DISTINCT', 'MIN', 'MAX']
            ELSE f.allowed_aggregations END,
       f.is_filterable AND NOT (c.column_name = ANY (hidden)),
       (f.is_groupable OR c.column_name IN ('ticker', 'trade_date')) AND NOT (c.column_name = ANY (hidden)),
       NULL, c.column_name IN ('ticker', 'trade_date'), 'PARTIAL',
       CASE WHEN c.column_name = 'close' THEN 'LAST' END, NULL, 'HISTORICAL',
       CASE WHEN c.column_name = ANY (hidden) THEN NULL
            WHEN c.column_name LIKE 'cdl\_%' THEN 'Kode pola candlestick TA-Lib ' || replace(substr(c.column_name, 5), '_', ' ')
                 || ': positif = bentuk bullish, negatif = bentuk bearish, 0 = tidak ada pola pada candle itu (filter <> 0 untuk mencarinya); NULL = riwayat belum cukup.'
            ELSE id.description_id END,
       CASE WHEN c.column_name = ANY (hidden) THEN NULL ELSE 'DRAFT' END,
       false
FROM information_schema.columns AS c
JOIN public."Feature_Catalog" AS f
  ON f.feature_table = c.table_name AND f.feature_column = c.column_name AND f.is_active
CROSS JOIN (SELECT ARRAY['tracking_high', 'tracking_low', 'temp_high', 'temp_high_bar', 'temp_low', 'temp_low_bar',
                         'calculation_version', 'calculated_at'] AS hidden,
                   ARRAY['close', 'sma_20', 'sma_50', 'ema_12', 'ema_26', 'ema_50', 'ema_200', 'bb_upper_20',
                         'bb_middle_20', 'bb_lower_20', 'atr_14', 'macd', 'macd_signal', 'macd_histogram',
                         'last_swing_high', 'temp_high', 'temp_low'] AS price_like) AS lists
LEFT JOIN (VALUES
    ('ticker', 'Kode instrumen: kode saham IDX (asset_type equity) atau kode benchmark obligasi seperti ID10Y (asset_type bonds).'),
    ('trade_date', 'Tanggal perdagangan candle harian sumber.'),
    ('timeframe', 'Interval candle; selalu Daily.'),
    ('asset_type', 'Kelas aset baris: equity (saham IDX) atau bonds (benchmark obligasi pemerintah). Selalu filter kolom ini.'),
    ('close', 'Harga penutupan harian dari sumber harga (saham: IDR; obligasi: kuotasi harga).'),
    ('sma_20', 'Rata-rata bergerak sederhana (SMA) 20 penutupan.'),
    ('sma_50', 'Rata-rata bergerak sederhana (SMA) 50 penutupan.'),
    ('ema_12', 'Rata-rata bergerak eksponensial (EMA) 12 penutupan.'),
    ('ema_26', 'Rata-rata bergerak eksponensial (EMA) 26 penutupan.'),
    ('ema_50', 'Rata-rata bergerak eksponensial (EMA) 50 penutupan.'),
    ('ema_200', 'Rata-rata bergerak eksponensial (EMA) 200 penutupan.'),
    ('rsi_14', 'RSI Wilder 14 periode, skala 0 sampai 100.'),
    ('macd', 'Garis MACD: EMA 12 dikurangi EMA 26.'),
    ('macd_signal', 'Garis sinyal MACD: EMA 9 dari garis MACD.'),
    ('macd_histogram', 'Histogram MACD: garis MACD dikurangi garis sinyal.'),
    ('atr_14', 'Average True Range Wilder 14 periode (volatilitas dalam satuan harga).'),
    ('bb_upper_20', 'Bollinger Band atas: SMA 20 ditambah 2 simpangan baku.'),
    ('bb_middle_20', 'Bollinger Band tengah: SMA 20.'),
    ('bb_lower_20', 'Bollinger Band bawah: SMA 20 dikurangi 2 simpangan baku.'),
    ('adx_14', 'ADX Wilder 14 periode: kekuatan tren pada skala 0 sampai 100.'),
    ('inside_bar', 'Inside bar: 1 bila rentang high-low candle ini berada di dalam rentang candle sebelumnya, selain itu 0.'),
    ('smi', 'Stochastic Momentum Index (SMI).'),
    ('last_swing_high', 'Swing high terakhir yang sudah terkonfirmasi (SMI turun melewati 40), dibawa ke depan sampai konfirmasi berikutnya.'),
    ('break_swing_high', 'Penanda 1 pada hari penutupan menembus swing high terakhir (sebelumnya di bawah atau sama), selain itu 0.')
) AS id(column_name, description_id) ON id.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Feature_04_Technical_Indicator';

-- 6. relationships
INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns, relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed, supported_join_semantics, left_time_column,
    right_time_column, effective_from_column, effective_to_column)
VALUES
    ('Universe_Fixed_income', ARRAY['ticker', 'metric_type'], 'Price_Fixed_Income_Final', ARRAY['ticker', 'metric_type'],
     'ONE_TO_MANY', 'Current-state reference metadata', 'date x ticker x metric_type', false,
     'Current bond universe (country, tenor, instrument name) joined to the final daily bond bars on ticker and metric_type, so a country or tenor scope selects the series. Current state, not point in time.',
     'v1', true, ARRAY['CURRENT_STATE'], NULL, NULL, NULL, NULL),
    ('Price_Fixed_Income_Final', ARRAY['ticker', 'date'], 'Feature_04_Technical_Indicator', ARRAY['ticker', 'trade_date'],
     'MANY_TO_ONE', 'Exact trading date', 'date x ticker x metric_type', false,
     'Final daily bond bars joined to the bond rows of Feature 04 on ticker and date. Each ticker and date has a price and a yield row: filter metric_type before a ticker-date result. Feature 04 bond indicators come from the price series.',
     'v1', true, ARRAY['EXACT_DATE'], 'date', 'trade_date', NULL, NULL),
    ('Price_Stock_Indonesia_IDX', ARRAY['ticker', 'date'], 'Feature_04_Technical_Indicator', ARRAY['ticker', 'trade_date'],
     'ONE_TO_ONE', 'Exact trading date', 'date x ticker', false,
     'Stock price candle joined to the equity row of Feature 04 for the same ticker and trading date (no stock ticker is also a bond ticker). A missing indicator row is never replaced by an earlier one.',
     'v1', true, ARRAY['EXACT_DATE'], 'date', 'trade_date', NULL, NULL),
    ('Feature_04_Technical_Indicator', ARRAY['ticker', 'trade_date'], 'Feature_01_Stock_Daily', ARRAY['ticker', 'date'],
     'ONE_TO_ONE', 'Exact trading date', 'equity ticker x trade_date (Daily)', false,
     'Feature 04 equity rows joined to Feature 01 daily stock features on ticker and trade_date = date (Feature_Relationship_Catalog v1); filter asset_type equity; unmatched rows are kept apart, never filled.',
     'v1', true, ARRAY['EXACT_DATE'], 'trade_date', 'date', NULL, NULL),
    ('IDX_Stock_Universe', ARRAY['Ticker'], 'Feature_04_Technical_Indicator', ARRAY['ticker'],
     'ONE_TO_MANY', 'Current-state reference metadata', 'trade_date x ticker', false,
     'Current stock-universe classification joined to the equity rows of Feature 04, so a sector or industry scope restricts the indicators by ticker. Bond tickers have no match. Current state, not point in time.',
     'v1', true, ARRAY['CURRENT_STATE'], NULL, NULL, NULL, NULL);

-- 7. AI_calculation_catalog: one contract per Feature 04 column (the 20260922_001 pattern) with the formula reference
INSERT INTO public."AI_calculation_catalog" (
    calculation_name, version, target_table, target_columns, definition,
    required_inputs, parameters, defaults, implementation_ref,
    alignment_rules, missing_data_policy, output_definition,
    validation_evidence, status
)
SELECT
    feature.feature_column,
    feature.version,
    feature.feature_table,
    ARRAY[feature.feature_column],
    feature.definition || ' Calculation: ' || feature.calculation,
    jsonb_build_object(
        'source_tables', string_to_array(feature.source_tables, ' | '),
        'source_columns', string_to_array(feature.source_columns, ' | ')
    ),
    jsonb_build_object(
        'lookback_window', feature.lookback_window,
        'minimum_history', feature.minimum_history
    ) || CASE WHEN ref.ids IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('formula_reference', jsonb_build_object(
            'calculation_ids', to_jsonb(ref.ids), 'relation', ref.relation, 'note', ref.note)) END,
    '{}'::jsonb,
    table_catalog.source_code_paths
        || ARRAY['database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql']
        || coalesce((SELECT array_agg('AI_formula_reference:' || id ORDER BY id) FROM unnest(ref.ids) AS id), '{}'),
    feature.dependency_rule,
    feature.null_rule,
    jsonb_build_object(
        'unit', feature.unit,
        'semantic_role', feature.semantic_role,
        'allowed_aggregations', feature.allowed_aggregations,
        'availability_rule', feature.availability_rule,
        'point_in_time_safe', feature.point_in_time_safe,
        'ai_allowed', column_catalog.ai_allowed
    ),
    feature.validation_evidence,
    'ACTIVE'
FROM public."Feature_Catalog" AS feature
JOIN public."Table_Catalog" AS table_catalog
  ON table_catalog.table_schema = 'public' AND table_catalog.table_name = feature.feature_table
JOIN public."AI_column_catalog" AS column_catalog
  ON column_catalog.table_name = feature.feature_table AND column_catalog.column_name = feature.feature_column
LEFT JOIN (VALUES
    ('sma_20', ARRAY['CALC_021'], 'STORED_VARIANT', 'Simple moving average of 20 closes.'),
    ('sma_50', ARRAY['CALC_021'], 'STORED_VARIANT', 'Simple moving average of 50 closes.'),
    ('bb_middle_20', ARRAY['CALC_021'], 'STORED_VARIANT', 'The middle Bollinger band is the 20-close SMA.'),
    ('ema_12', ARRAY['CALC_022'], 'STORED_VARIANT', 'EMA of 12 closes, seeded with the SMA of the first 12.'),
    ('ema_26', ARRAY['CALC_022'], 'STORED_VARIANT', 'EMA of 26 closes, seeded with the SMA of the first 26.'),
    ('ema_50', ARRAY['CALC_022'], 'STORED_VARIANT', 'EMA of 50 closes, seeded with the SMA of the first 50.'),
    ('ema_200', ARRAY['CALC_022'], 'STORED_VARIANT', 'EMA of 200 closes, seeded with the SMA of the first 200.'),
    ('rsi_14', ARRAY['CALC_028'], 'STORED_VARIANT', 'TA-Lib RSI with Wilder smoothing over 14 changes; when average gain and loss are both zero the stored value is 0 (TA-Lib) where the reference uses 50.'),
    ('macd', ARRAY['CALC_032'], 'STORED_VARIANT', 'ema_12 - ema_26 with independently SMA-seeded EMAs (not TA-Lib MACD internal reseeding).'),
    ('macd_signal', ARRAY['CALC_033'], 'STORED_VARIANT', 'EMA 9 of the MACD line, SMA-seeded.'),
    ('macd_histogram', ARRAY['CALC_034'], 'STORED_VARIANT', 'macd - macd_signal.'),
    ('adx_14', ARRAY['CALC_040'], 'STORED_VARIANT', 'TA-Lib ADX with Wilder smoothing over 14.'),
    ('atr_14', ARRAY['CALC_042'], 'STORED_VARIANT', 'TA-Lib ATR with Wilder smoothing over 14.'),
    ('bb_upper_20', ARRAY['CALC_049'], 'STORED_VARIANT', 'SMA20 + 2 population standard deviations of 20 closes.'),
    ('bb_lower_20', ARRAY['CALC_050'], 'STORED_VARIANT', 'SMA20 - 2 population standard deviations of 20 closes.'),
    ('cdl_engulfing', ARRAY['CALC_161', 'CALC_162'], 'RELATED_NOT_IDENTICAL', 'TA-Lib CDLENGULFING returns +100/+80 for the bullish and -100/-80 for the bearish form in one column; the references define the bullish and the bearish body condition separately.'),
    ('cdl_doji', ARRAY['CALC_165'], 'RELATED_NOT_IDENTICAL', 'TA-Lib CDLDOJI returns a pattern code (100 or 0) from its default candle settings; the reference defines a body-to-range ratio.'),
    ('cdl_hammer', ARRAY['CALC_166'], 'RELATED_NOT_IDENTICAL', 'TA-Lib CDLHAMMER returns a pattern code (100 or 0) from its default candle settings and also compares the body with the previous candle; the reference defines the candle geometry only.'),
    ('inside_bar', ARRAY['CALC_167'], 'RELATED_NOT_IDENTICAL', 'Stored strict containment (high < previous high and low > previous low); the reference allows ties (<=, >=), so an equal high or low is 0 here and 1 there.')
) AS ref(column_name, ids, relation, note) ON ref.column_name = feature.feature_column
WHERE feature.is_active AND feature.feature_table = 'Feature_04_Technical_Indicator';

-- 8. preview: the three objects added; Feature 04 rows leave out its hidden columns
CREATE OR REPLACE FUNCTION public.ai_preview_table_rows(p_table_name text)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    order_clause text;
    hidden text[];
    result json;
BEGIN
    -- Each ORDER BY follows an existing index or the primary key where one exists, so LIMIT 20 needs no full sort
    -- on the large tables; Feature 04's order was measured before this migration (DATABASE_CHANGELOG.md).
    order_clause := CASE p_table_name
        WHEN 'Feature_01_Stock_Daily' THEN 'date DESC, ticker DESC'
        WHEN 'Feature_02_Broker_Rolling' THEN
            'date DESC, market_board DESC, ticker DESC, broker DESC, investor_type DESC'
        WHEN 'Feature_03_Stock_Broker_Daily' THEN 'date DESC, market_board DESC, ticker DESC'
        WHEN 'IDX_Broker_Profile' THEN 'broker_code ASC'
        WHEN 'IDX_Broker_Summary' THEN
            '"Date" DESC, "Symbol" DESC, "Broker" DESC, "Investor Type" DESC, "Market Board" DESC'
        WHEN 'IDX_Stock_Universe' THEN '"Ticker" ASC'
        WHEN 'Price_Stock_Indonesia_IDX' THEN 'date DESC, ticker DESC'
        WHEN 'Price_Fixed_Income_Final' THEN 'date DESC, ticker DESC, metric_type DESC'
        WHEN 'Universe_Fixed_income' THEN 'ticker ASC, metric_type ASC'
        WHEN 'Feature_04_Technical_Indicator' THEN 'trade_date DESC, asset_type DESC, ticker DESC'
        ELSE NULL
    END;
    IF order_clause IS NULL THEN
        RAISE EXCEPTION 'Table is not approved for preview' USING ERRCODE = 'insufficient_privilege';
    END IF;
    hidden := CASE p_table_name
        WHEN 'Feature_04_Technical_Indicator' THEN ARRAY['tracking_high', 'tracking_low', 'temp_high',
            'temp_high_bar', 'temp_low', 'temp_low_bar', 'calculation_version', 'calculated_at']
        ELSE ARRAY[]::text[]
    END;

    EXECUTE format(
        $query$
        SELECT json_build_object(
            'table_name', %1$L,
            'order_by', %2$L,
            'row_limit', 20,
            'columns', (
                SELECT json_agg(json_build_object(
                           'name', a.attname,
                           'type', format_type(a.atttypid, a.atttypmod),
                           'nullable', NOT a.attnotnull) ORDER BY a.attnum)
                FROM pg_catalog.pg_attribute AS a
                WHERE a.attrelid = %3$L::regclass AND a.attnum > 0 AND NOT a.attisdropped
                  AND NOT (a.attname::text = ANY (%4$L::text[]))
            ),
            'rows', COALESCE((
                SELECT json_agg(CASE WHEN cardinality(%4$L::text[]) = 0 THEN to_json(sample)
                                     ELSE (to_jsonb(sample) - %4$L::text[])::json END ORDER BY %2$s)
                FROM (SELECT * FROM public.%1$I ORDER BY %2$s LIMIT 20) AS sample
            ), '[]'::json)
        )
        $query$,
        p_table_name, order_clause, format('public.%I', p_table_name), hidden
    ) INTO result;
    RETURN result;
END
$function$;

COMMENT ON FUNCTION public.ai_preview_table_rows(text) IS
    'market-ai-orc preview: at most 20 rows in a fixed order from ten approved market-data objects (Feature 04 without its hidden state columns); EXECUTE only via market_ai_preview_reader.';

-- 9. Table_Catalog / Column_Catalog
INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain, primary_key_columns, source_system, source_tables,
    source_code_paths, update_rule, related_functions, documentation_status, readiness_mode, readiness_date_column,
    observation_date_column, data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method)
VALUES
    ('public', 'Price_Fixed_Income_Final', 'Source',
     'View of the final daily (Timeframe 1D, is_final) bars of Price_Fixed_Income with the analytical columns only: country, instrument_name, ticker, metric_type, date, open, high, low, close, value_unit. The object exposed to the AI.',
     'ticker x metric_type x market-local date (final 1D bar)', ARRAY['ticker', 'metric_type', 'date'],
     'TradingView (through Price_Fixed_Income)', ARRAY['Price_Fixed_Income']::text[],
     ARRAY['database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql',
           'apps/fixed-income-price-cron/fixed_income_update.py'],
     'A view: changes when Price_Fixed_Income changes; only rows already final appear.',
     ARRAY['public.ai_preview_table_rows(text)']::text[], 'PARTIAL', 'DATA_DATE', 'date', 'date', NULL,
     'Final bar of the market-local date: use it no earlier than the next session of that market. The base table''s ingestion_time (not in the view) records load time, not historical availability.',
     'PARTIAL',
     'Bars are kept historically; the series list (Universe_Fixed_income) is current state.');

UPDATE public."Table_Catalog"
SET source_code_paths = source_code_paths || ARRAY['database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql'],
    related_functions = CASE WHEN table_name IN ('Universe_Fixed_income', 'Feature_04_Technical_Indicator')
                             THEN related_functions || ARRAY['public.ai_preview_table_rows(text)']
                             ELSE related_functions END
WHERE table_schema = 'public' AND table_name IN ('Price_Fixed_Income', 'Universe_Fixed_income',
                                                 'Feature_04_Technical_Indicator', 'AI_table_catalog',
                                                 'AI_column_catalog', 'AI_catalog_relationships',
                                                 'AI_calculation_catalog')
  AND NOT ('database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql' = ANY (source_code_paths));

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, default_expression,
    is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths, documentation_status)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', NULL, false,
       a.description, a.source_column_or_expression, a.unit,
       'NULL never appears: every source column is NOT NULL in Price_Fixed_Income.',
       ARRAY['database/migrations/20261020_001_onboard_fixed_income_and_feature04.sql'], 'PARTIAL'
FROM information_schema.columns AS c
JOIN public."AI_column_catalog" AS a ON a.table_name = c.table_name AND a.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'Price_Fixed_Income_Final';

DO $verify$
DECLARE
    v_rows bigint;
    v_keys bigint;
    v_base bigint;
BEGIN
    SELECT count(*), count(DISTINCT (ticker, metric_type, date)) INTO v_rows, v_keys
    FROM public."Price_Fixed_Income_Final";
    SELECT count(*) INTO v_base FROM public."Price_Fixed_Income" WHERE is_final AND "Timeframe" = '1D';
    IF v_rows <> v_keys OR v_rows <> v_base OR v_rows = 0 THEN
        RAISE EXCEPTION 'Price_Fixed_Income_Final rows %, keys %, base final 1D rows %', v_rows, v_keys, v_base;
    END IF;
    IF (SELECT count(*) FROM public."AI_table_catalog" WHERE table_name IN ('Price_Fixed_Income_Final',
            'Universe_Fixed_income', 'Feature_04_Technical_Indicator') AND is_active
            AND ai_access_level = 'BOUNDED_READ') <> 3 THEN
        RAISE EXCEPTION 'The three objects are not active in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Price_Fixed_Income_Final') <> 10
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Universe_Fixed_income') <> 14
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_04_Technical_Indicator') <> 57
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Feature_04_Technical_Indicator'
           AND ai_allowed) <> 49
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'Universe_Fixed_income'
           AND ai_allowed) <> 10 THEN
        RAISE EXCEPTION 'Unexpected AI_column_catalog rows for the onboarded objects';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog"
               WHERE table_name IN ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator')
                 AND ai_allowed AND (description IS NULL OR btrim(description) = '' OR description_id IS NULL
                                     OR description_id_status <> 'DRAFT')) THEN
        RAISE EXCEPTION 'An exposed column lacks its description or DRAFT Indonesian meaning';
    END IF;
    IF (SELECT count(*) FROM public."AI_calculation_catalog" WHERE target_table = 'Feature_04_Technical_Indicator'
        AND status = 'ACTIVE') <> 57
       OR (SELECT count(*) FROM public."AI_calculation_catalog" WHERE target_table = 'Feature_04_Technical_Indicator'
           AND parameters ? 'formula_reference') <> 19 THEN
        RAISE EXCEPTION 'Unexpected Feature 04 AI_calculation_catalog rows';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_calculation_catalog" AS k, unnest(k.implementation_ref) AS ref
               WHERE k.target_table = 'Feature_04_Technical_Indicator' AND ref LIKE 'AI_formula_reference:%'
                 AND NOT EXISTS (SELECT 1 FROM public."AI_formula_reference" AS f
                                 WHERE 'AI_formula_reference:' || f.calculation_id = ref)) THEN
        RAISE EXCEPTION 'A formula reference names a missing AI_formula_reference row';
    END IF;
    -- every relationship key column is an exposed catalog column
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships" AS r,
                    LATERAL (SELECT r.left_table AS t, unnest(r.left_columns) AS col
                             UNION ALL SELECT r.right_table, unnest(r.right_columns)) AS k
               WHERE (r.left_table IN ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator')
                      OR r.right_table IN ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator'))
                 AND NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" AS c
                                 WHERE c.table_name = k.t AND c.column_name = k.col AND c.ai_allowed)) THEN
        RAISE EXCEPTION 'A relationship key column is not an exposed AI catalog column';
    END IF;
    IF (SELECT count(*) FROM public."AI_catalog_relationships" WHERE is_allowed AND
        (left_table IN ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator')
         OR right_table IN ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator'))) <> 5 THEN
        RAISE EXCEPTION 'Expected five relationships for the onboarded objects';
    END IF;
    -- privileges: the AI reader sees the view, not the base table
    IF NOT has_table_privilege('market_ai_sql_reader', 'public."Price_Fixed_Income_Final"', 'SELECT')
       OR NOT has_table_privilege('market_ai_sql_reader', 'public."Universe_Fixed_income"', 'SELECT')
       OR NOT has_table_privilege('market_ai_sql_reader', 'public."Feature_04_Technical_Indicator"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."Price_Fixed_Income"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."Price_Fixed_Income_Final"', 'INSERT,UPDATE,DELETE,TRUNCATE')
       OR has_table_privilege('market_ai_preview_reader', 'public."Price_Fixed_Income_Final"', 'SELECT')
       OR (SELECT proowner FROM pg_proc WHERE oid = 'public.ai_preview_table_rows(text)'::regprocedure)
          <> 'market_ai_preview_owner'::regrole
       OR NOT (SELECT prosecdef FROM pg_proc WHERE oid = 'public.ai_preview_table_rows(text)'::regprocedure) THEN
        RAISE EXCEPTION 'Unexpected privileges on the onboarded objects or the preview function';
    END IF;
    IF (SELECT count(*) FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name = 'Price_Fixed_Income_Final') <> 1
       OR (SELECT count(*) FROM public."Column_Catalog" WHERE table_schema = 'public'
           AND table_name = 'Price_Fixed_Income_Final' AND definition IS NOT NULL) <> 10 THEN
        RAISE EXCEPTION 'Table_Catalog / Column_Catalog are not complete for Price_Fixed_Income_Final';
    END IF;
    -- the three onboarded objects list the preview function (live 2026-10-20: Price_Stock_Indonesia_IDX's row no
    -- longer lists it; a separate catalog drift, recorded in DATABASE_CHANGELOG.md, not changed here)
    IF (SELECT count(*) FROM public."Table_Catalog" WHERE table_schema = 'public'
        AND table_name IN ('Price_Fixed_Income_Final', 'Universe_Fixed_income', 'Feature_04_Technical_Indicator')
        AND 'public.ai_preview_table_rows(text)' = ANY (related_functions)) <> 3 THEN
        RAISE EXCEPTION 'An onboarded object does not list ai_preview_table_rows in related_functions';
    END IF;
END
$verify$;

COMMIT;
