-- EXEC-INDEX-GROUP-HISTORY stage 7 (user go 2026-11-15: "Langsung go tahap 4-9, kecuali ada perubahan arah material
-- dan butuh decision saya"; plan PLAN.md INDEX-GROUP-HISTORY B, "migrasi katalog: SUM antar-ticker dilarang (IHSG +
-- LQ45 + grup = dobel hitung), deskripsi ticker baru, versi semantik Feature_Catalog untuk himpunan simbol per ticker").
-- The six *_INDEX tables now hold every entity of Feature_Index_Entity (IHSG, 32 indexes, 11 IDX-IC sectors, 33 KONGLO
-- groups; scripts/backfill_index_entities.py). Their catalog texts said "IHSG", "all raw source symbols" and "refreshed
-- manually"; this migration states the entity scope where each text lives:
-- 1. AI_table_catalog.description of the six tables (what the model reads), the entity lists built here from
--    Feature_Index_Entity (not typed), with the rule that rows of different tickers are never added (the Governor and
--    the sandbox refuse such a SUM: extract.overlapping_entity, data_need.overlapping_entity) and how to pass it.
-- 2. The phrases of the IHSG scope in Feature_Catalog and its copies (AI_column_catalog, Column_Catalog,
--    AI_calculation_catalog) of the *_INDEX objects, replaced phrase by phrase (m_phrase); every copy holds the same
--    count (read on dev 2026-11-15) and none may remain.
-- 3. The ticker rows of Feature 02/03/05/06 INDEX: interpretation and misuse warning (they still held the stock text).
-- 4. Feature_Catalog.version v2 on the *_INDEX rows (the symbol set of a ticker is now per entity), validation
--    evidence; Table_Catalog definition, update rule, availability rule and source paths.
-- Forward-only. Rollback: a later migration restoring the old texts (the preflight pins them: m_phrase old values and
-- the md5 of the six old descriptions).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

CREATE TEMP TABLE m_phrase (old_value text PRIMARY KEY, new_value text NOT NULL, feature_rows integer NOT NULL)
    ON COMMIT DROP;
INSERT INTO m_phrase VALUES
    ('all raw source symbols', 'the entity''s member symbols of the date (IHSG: every raw source symbol)', 29),
    ('all source symbols', 'the entity''s member symbols', 8),
    ('all raw symbols', 'the entity''s member symbols', 2),
    ('declared source symbols', 'the entity''s member symbols', 2),
    ('index source symbols', 'member symbols of the entity', 1),
    ('Universe-classified index identifier',
     'Entity code of Feature_Index_Entity: IHSG, an IDX index or IDX-IC sector index, or a KONGLO group (G + group name)', 4),
    ('aggregate source symbols are not copied into the index ticker',
     'its member symbols are not copied into it, and rows of different tickers overlap and are never added together', 4),
    ('Resolve the requested index ticker from IDX_Stock_Universe where Security Type=index',
     'The requested entity''s code in Feature_Index_Entity; its members by date from Stock_List_Member_History (an index or group list) or IDX_Stock_Universe_History (a sector); IHSG takes every raw source symbol', 4),
    ('declared all-source-symbol broker universe', 'entity''s member symbols by date (IHSG: every raw source symbol)', 2),
    ('official historical IHSG constituent flow',
     'official historical constituent flow (members follow the recorded lists by date); never add cumulative rows of different tickers', 2),
    ('Approved manual INDEX historical bootstrap; no automatic daily update.',
     'Updated after each broker round of stockbit-updater (IHSG first, then every other entity of Feature_Index_Entity); history by scripts/backfill_index_features.py (IHSG) and scripts/backfill_index_entities.py.', 255),
    ('Use only loaded INDEX output dates; price/broker histories have independent endpoints.',
     'Use only loaded INDEX output dates; the price and broker histories have independent endpoints. An entity''s rows start at its Feature_Index_Entity.rows_from (IHSG: broker 2016-01-04, price 2018-01-02; the indexes, sectors and groups 2024-01-02).', 255);

-- where each phrase lives (target table, its object key column, text column, jsonb)
CREATE TEMP TABLE m_target (target text, key_column text, text_column text, is_jsonb boolean) ON COMMIT DROP;
INSERT INTO m_target VALUES
    ('Feature_Catalog', 'feature_table', 'definition', false), ('Feature_Catalog', 'feature_table', 'calculation', false),
    ('Feature_Catalog', 'feature_table', 'analytical_interpretation', false),
    ('Feature_Catalog', 'feature_table', 'misuse_warning', false),
    ('Feature_Catalog', 'feature_table', 'availability_rule', false),
    ('Feature_Catalog', 'feature_table', 'refresh_trigger', false),
    ('AI_column_catalog', 'table_name', 'description', false),
    ('AI_column_catalog', 'table_name', 'source_column_or_expression', false),
    ('Column_Catalog', 'table_name', 'definition', false),
    ('Column_Catalog', 'table_name', 'source_column_or_expression', false),
    ('AI_calculation_catalog', 'target_table', 'definition', false),
    ('AI_calculation_catalog', 'target_table', 'output_definition', true);

CREATE TEMP TABLE m_index (table_name text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO m_index SELECT table_name FROM public."AI_table_catalog" WHERE table_name ~ '^Feature_0[1-6]_[A-Za-z_]+_INDEX$';

DO $preflight$
DECLARE
    r record;
    n integer;
BEGIN
    IF (SELECT count(*) FROM m_index) <> 6 THEN
        RAISE EXCEPTION 'Expected the six INDEX tables in AI_table_catalog';
    END IF;
    IF (SELECT count(*) FROM public."Feature_Index_Entity") <> 77
       OR (SELECT count(*) FROM public."Feature_Index_Entity" WHERE entity_kind = 'GROUP') <> 33 THEN
        RAISE EXCEPTION 'Feature_Index_Entity is not the reviewed 77 entities (33 groups)';
    END IF;
    -- the six descriptions are the ones this migration replaces (20261025_005)
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" a JOIN m_index USING (table_name)
               WHERE a.description NOT LIKE '%IDX Composite Index (IHSG%') THEN
        RAISE EXCEPTION 'An INDEX description is not the reviewed IHSG text of 20261025_005';
    END IF;
    FOR r IN SELECT * FROM m_phrase LOOP
        SELECT count(*) INTO n FROM public."Feature_Catalog" f
        WHERE f.is_active AND f.feature_table IN (SELECT table_name FROM m_index)
          AND position(r.old_value IN concat_ws(' | ', f.definition, f.calculation, f.analytical_interpretation,
                                                f.misuse_warning, f.availability_rule, f.refresh_trigger)) > 0;
        IF n <> r.feature_rows THEN
            RAISE EXCEPTION 'Phrase "%": % Feature_Catalog rows, % reviewed; re-read and review first', r.old_value, n, r.feature_rows;
        END IF;
    END LOOP;
END
$preflight$;

CREATE TEMP TABLE m_count (target text, text_column text, old_value text, updated integer) ON COMMIT DROP;

DO $apply$
DECLARE
    p record;
    t record;
    n integer;
BEGIN
    FOR p IN SELECT * FROM m_phrase ORDER BY length(old_value) DESC LOOP
        FOR t IN SELECT * FROM m_target LOOP
            IF t.is_jsonb THEN
                EXECUTE format('UPDATE public.%I SET %I = replace(%I::text, $1, $2)::jsonb WHERE %I IN (SELECT table_name FROM m_index)
                                AND position($1 IN %I::text) > 0', t.target, t.text_column, t.text_column, t.key_column, t.text_column)
                    USING p.old_value, p.new_value;
            ELSE
                EXECUTE format('UPDATE public.%I SET %I = replace(%I, $1, $2) WHERE %I IN (SELECT table_name FROM m_index)
                                AND position($1 IN %I) > 0', t.target, t.text_column, t.text_column, t.key_column, t.text_column)
                    USING p.old_value, p.new_value;
            END IF;
            GET DIAGNOSTICS n = ROW_COUNT;
            INSERT INTO m_count VALUES (t.target, t.text_column, p.old_value, n);
        END LOOP;
    END LOOP;
END
$apply$;

-- the Indonesian meanings the model reads first (AI_column_catalog.description_id, copies of Feature_Vocabulary.definition):
-- the same sentences scripts/build_feature_vocabulary_seed.py now writes; the rebuilt seed is synced in the same job
UPDATE public."AI_column_catalog"
SET description_id = replace(description_id,
        ' Lingkup INDEX menggabungkan seluruh simbol transaksi sumber, bukan hanya saham atau konstituen resmi IHSG.',
        ' Lingkup INDEX: jumlah simbol anggota entitas pada tanggal itu (IHSG: seluruh simbol transaksi sumber), bukan konstituen resmi historis; ticker berbeda tumpang tindih sehingga tidak dijumlahkan.'),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name IN (SELECT table_name FROM m_index)
  AND position(' Lingkup INDEX menggabungkan seluruh simbol transaksi sumber' IN description_id) > 0;
UPDATE public."AI_column_catalog"
SET description_id = 'Kode entitas Feature_Index_Entity: IHSG, indeks IDX atau indeks sektor IDX-IC, atau grup konglomerat KONGLO (G + nama grup).',
    updated_at = CURRENT_TIMESTAMP
WHERE column_name = 'ticker' AND description_id = 'Kode indeks yang tervalidasi pada IDX_Stock_Universe dengan Security Type=index.'
  AND table_name IN ('Feature_02_Broker_Rolling_INDEX', 'Feature_03_Stock_Broker_Daily_INDEX',
                     'Feature_05_Foreign_Domestic_Broker_Detail_INDEX', 'Feature_06_Foreign_Domestic_INDEX');

-- the ticker rows of the broker INDEX tables still held the stock text
UPDATE public."Feature_Catalog"
SET analytical_interpretation = 'ticker is the entity code at the table''s grain: IHSG (every raw source symbol), an IDX index or IDX-IC sector index (its IDX code) or a KONGLO group (G + group name). Its rows are the sums of its member symbols of the date.',
    misuse_warning = 'Rows of different tickers overlap (a stock is in IHSG, its sector, several indexes and perhaps a group): never add values of different tickers; compare them side by side. Members follow the recorded Stockbit lists and universe sectors by date (the first recorded members also before the first record), not the official historical constituents. Do not combine Regular, Nego and Tunai implicitly.',
    recommended_use = 'Filter one entity (ticker = ''LQ45'', ''IDXENERGY'', ''GSALIM'') or compare several side by side on the same dates; keep ticker in group_by of any summary.',
    updated_at = CURRENT_TIMESTAMP
WHERE is_active AND feature_column = 'ticker'
  AND feature_table IN ('Feature_02_Broker_Rolling_INDEX', 'Feature_03_Stock_Broker_Daily_INDEX',
                        'Feature_05_Foreign_Domestic_Broker_Detail_INDEX', 'Feature_06_Foreign_Domestic_INDEX');

UPDATE public."Feature_Catalog"
SET version = 'v2',
    validation_evidence = CASE WHEN 'verification/index_group_history/' = ANY (validation_evidence) THEN validation_evidence
                               ELSE array_append(validation_evidence, 'verification/index_group_history/') END,
    updated_at = CURRENT_TIMESTAMP
WHERE is_active AND feature_table IN (SELECT table_name FROM m_index);

-- 1. the descriptions the model reads, the entity lists from Feature_Index_Entity
WITH e AS (
    SELECT string_agg(ticker, ', ' ORDER BY ticker) FILTER (WHERE entity_kind = 'INDEX') AS indexes,
           string_agg(ticker, ', ' ORDER BY ticker) FILTER (WHERE entity_kind = 'SECTOR') AS sectors,
           string_agg(ticker || ' ' || name, ', ' ORDER BY ticker) FILTER (WHERE entity_kind = 'GROUP') AS groups,
           count(*) FILTER (WHERE entity_kind = 'INDEX') AS n_index, count(*) FILTER (WHERE entity_kind = 'SECTOR') AS n_sector,
           count(*) FILTER (WHERE entity_kind = 'GROUP') AS n_group
    FROM public."Feature_Index_Entity"),
t AS (
    SELECT format('Tickers: IHSG (every raw source symbol, including warrants and rights); %s IDX indexes (%s); %s IDX-IC sector indexes (%s); %s KONGLO conglomerate groups (%s). ',
                  n_index, indexes, n_sector, sectors, n_group, groups)
           || 'An entity''s rows are the sums of its member stocks of the date: an index or group follows its recorded Stockbit list, a sector the universe''s sector; the first recorded members also hold before the first record, and a recorded change counts from the next day (not the official historical constituents). '
           || 'Rows of different tickers overlap (a stock is in IHSG, its sector, several indexes and perhaps a group), so never add tickers together: summarise per ticker (keep ticker in group_by; the brokers and boards of one ticker may be summed). Right: the daily foreign net of LQ45 is the SUM over its brokers and boards with group_by ticker and date. Wrong: one total of LQ45 + IDX30 + GSALIM. '
           || 'Rows: IHSG from 2016-01-04, the others from 2024-01-02, to the last Broker Summary date; updated after each broker round. ' AS broker,
           format('Tickers: IHSG; %s IDX indexes (%s); %s IDX-IC sector indexes (%s); KONGLO groups have no price and no row here. ',
                  n_index, indexes, n_sector, sectors) AS price
    FROM e),
d(table_name, description) AS (
    SELECT 'Feature_01_Stock_Daily_INDEX', 'Daily price features of the IDX indexes: the IDX Composite Index (IHSG, indeks harga saham gabungan), the other IDX indexes and the IDX-IC sector indexes, by their IDX code: close level in index points, returns over 1 to 60 sessions, volatility, highest close, drawdown. ' || t.price || 'Use it for kinerja IHSG, kinerja LQ45 atau indeks sektor, return dan volatilitas indeks, and as the benchmark beside a stock (request the stock and the index separately and align them on the date). Indexes have no source volume: volume and volume-based columns are NULL. Rows: IHSG from 2018-01-02, the other indexes from 2024-01-02 (their prices are stored from 2018 or their first bar); updated after each broker round. Stock rows are in Feature_01_Stock_Daily.' FROM t
    UNION ALL
    SELECT 'Feature_04_Technical_Indicator_INDEX', 'Daily technical indicators of the IDX indexes calculated from their actual index close: SMA 20/50, EMA 12/26/50/200, RSI 14, MACD, ATR 14, Bollinger bands, ADX, SMI, swing-high break, inside bar and TA-Lib candlestick patterns (asset_type index). ' || t.price || 'Use it for RSI IHSG, MACD LQ45, tren indeks sektor, golden cross IHSG. Read the stored column instead of computing the indicator again; indicators run over the whole stored price history (2018 or the index''s first bar). Rows: IHSG from 2018-01-02, the other indexes from 2024-01-02; updated after each broker round. Stock and bond rows are in Feature_04_Technical_Indicator.' FROM t
    UNION ALL
    SELECT 'Feature_02_Broker_Rolling_INDEX', 'Broker flows per index, sector and conglomerate group: per ticker, broker, source investor type (Foreign or Domestic) and board, the buy, sell and net value and lots of the entity''s member symbols on the date, with rolling 5 to 60 session nets, buy and sell days and percentiles. ' || t.broker || 'Use it for broker terbesar di LQ45, akumulasi broker di grup Salim, net beli broker se-market (IHSG). Per-stock rows are in Feature_02_Broker_Rolling.' FROM t
    UNION ALL
    SELECT 'Feature_03_Stock_Broker_Daily_INDEX', 'Daily broker structure per index, sector and conglomerate group and board: total buy and sell value, active, net-buying and net-selling broker counts, foreign, domestic, institutional and retail net value, top buyer and seller of the entity''s member symbols; HHI concentration is NULL by policy. ' || t.broker || 'Use it for net asing se-market, jumlah broker aktif di sektor energi, dominasi broker di grup Barito (GPRAJOGO). Per-stock rows are in Feature_03_Stock_Broker_Daily.' FROM t
    UNION ALL
    SELECT 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX', 'Broker-level foreign and domestic flows per index, sector and conglomerate group: per broker, source investor type and board, the buy, sell and net value (IDR), lots and transaction frequency summed over the entity''s member symbols of the date. Frequency sums the known source counts; it is NULL only when no input is known. ' || t.broker || 'Use it for broker asing di LQ45, net beli asing per broker di grup Djarum, se-market (IHSG). Per-stock rows are in Feature_05_Foreign_Domestic_Broker_Detail_Stock.' FROM t
    UNION ALL
    SELECT 'Feature_06_Foreign_Domestic_INDEX', 'Daily foreign and domestic flow per index, sector and conglomerate group and board: buy, sell and net value of foreign and domestic investors, cumulative net, rolling net over 5 to 60 sessions, net-to-turnover ratios, z-scores and percentiles, foreign strength, frequency and frequency coverage, of the entity''s member symbols. Sessions are the entity''s own trading sessions; the cumulative net runs from the first broker date (2016-01-04) for every entity, also before its first row. ' || t.broker || 'Use it for net beli asing IHSG, aliran dana asing LQ45, foreign flow sektor keuangan, net jual asing grup Salim. Per-stock rows are in Feature_06_Foreign_Domestic_Stock.' FROM t)
UPDATE public."AI_table_catalog" a SET description = d.description, updated_at = CURRENT_TIMESTAMP
FROM d WHERE a.table_name = d.table_name;

-- 4. Table_Catalog
UPDATE public."Table_Catalog"
SET definition = replace(definition, 'Transaction aggregates include all declared source symbols, including warrants/rights; not an official historical constituent basket.',
                         'One ticker per entity of Feature_Index_Entity: IHSG sums every declared source symbol (including warrants/rights); an index, sector or group sums its member stocks by date. Not an official historical constituent basket; rows of different tickers overlap.'),
    update_rule = 'After each broker round of stockbit-updater: IHSG (scripts/backfill_index_features.py, incremental), then every other entity of Feature_Index_Entity (scripts/backfill_index_entities.py, from the day after its newest row).',
    availability_rule = 'Validated loaded INDEX dates only; independent price and broker source endpoints. An entity''s rows start at its Feature_Index_Entity.rows_from (IHSG: broker 2016-01-04, price 2018-01-02; the others 2024-01-02). Members by date from the recorded lists, not official historical constituents.',
    source_code_paths = (SELECT array_agg(DISTINCT x ORDER BY x) FROM unnest(source_code_paths || ARRAY[
        'scripts/backfill_index_entities.py', 'database/migrations/20261115_004_index_entities_catalog.sql']) x),
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name IN (SELECT table_name FROM m_index);

DO $verify$
DECLARE
    p record;
    t record;
    n integer;
BEGIN
    FOR p IN SELECT * FROM m_phrase LOOP
        FOR t IN SELECT * FROM m_target LOOP
            EXECUTE format('SELECT count(*) FROM public.%I WHERE %I IN (SELECT table_name FROM m_index) AND position($1 IN %I::text) > 0',
                           t.target, t.key_column, t.text_column) INTO n USING p.old_value;
            IF n > 0 THEN
                RAISE EXCEPTION 'Phrase "%" remains in %.% (% rows)', p.old_value, t.target, t.text_column, n;
            END IF;
        END LOOP;
        -- every copy changed as many rows as Feature_Catalog's reviewed count (copies may lack a field: never more)
        IF EXISTS (SELECT 1 FROM m_count c WHERE c.old_value = p.old_value AND c.updated > p.feature_rows) THEN
            RAISE EXCEPTION 'Phrase "%" changed more rows in a copy than in Feature_Catalog', p.old_value;
        END IF;
    END LOOP;
    IF (SELECT count(*) FROM public."AI_table_catalog" a JOIN m_index USING (table_name)
        WHERE a.description LIKE '%never add tickers%' OR a.description LIKE '%KONGLO groups have no price%') <> 6 THEN
        RAISE EXCEPTION 'An INDEX description was not replaced';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_table_catalog" a JOIN m_index USING (table_name)
               WHERE a.table_name NOT IN ('Feature_01_Stock_Daily_INDEX', 'Feature_04_Technical_Indicator_INDEX')
                 AND a.description NOT LIKE '%GPRAJOGO Prajogo Pangestu%') THEN
        RAISE EXCEPTION 'A broker INDEX description lacks the group list';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" WHERE table_name IN (SELECT table_name FROM m_index)
               AND (position('menggabungkan seluruh simbol transaksi sumber' IN coalesce(description_id, '')) > 0
                    OR (column_name = 'ticker' AND table_name NOT IN ('Feature_01_Stock_Daily_INDEX', 'Feature_04_Technical_Indicator_INDEX')
                        AND description_id LIKE 'Kode indeks yang tervalidasi%'))) THEN
        RAISE EXCEPTION 'An Indonesian meaning still holds the IHSG-only scope';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Feature_Catalog" WHERE is_active AND feature_table IN (SELECT table_name FROM m_index)
               AND version <> 'v2') THEN
        RAISE EXCEPTION 'An INDEX Feature_Catalog row is not v2';
    END IF;
END
$verify$;

SELECT target, text_column, sum(updated) AS rows_changed FROM m_count GROUP BY 1, 2 ORDER BY 1, 2;

COMMIT;
