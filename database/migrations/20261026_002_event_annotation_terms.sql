-- EXEC-M223 (user go 2026-10-26: "Jalankan untuk ke 3 exec tersebut"; ERRORS M223): the terms of a corporate action
-- become typed columns of idx_event_annotation, so the AI can read the dividend amount, the cum/ex/record/pay dates,
-- split and rights ratios and the rights, warrant and tender prices. Until now refresh_idx_event_annotation() copied one
-- annotation_date per action plus source_payload, which is hidden from the AI (20261025_015).
--
-- The loader is unchanged: apps/stockbit-event-annotation/job.py already stores the dates as typed columns of
-- stockbit_corporate_action and the verbatim row in source_payload, then calls this function in its transaction.
--
-- Evidence, read-only jobs 87e18813 and the follow-up probe (2026-10-26), active source rows:
-- - DIVIDEND 5,301: dividend_value numeric text in every row (2 rows are 0 at the source), dividend_currency
--   CURRENCY_IDR in every row; BBCA dividend:118073 value 25, cum 2026-08-28, ex 2026-08-31, record 2026-09-01,
--   pay 2026-09-16.
-- - STOCK_SPLIT 258, REVERSE_SPLIT 34, BONUS_SHARE 91: stocksplit_old/stocksplit_new numeric in every row (the *_ratio
--   texts carry the same numbers with thousands separators); RIGHT_ISSUE 325: rightissue_old/rightissue_new and
--   rightissue_price numeric in every row; WARRANT 2,223: wrant_exc_price; TENDER_OFFER 190: tender_price.
-- - STOCK_DIVIDEND has no row; RUPS and PUBLIC_EXPOSE carry no amount or ratio.
--
-- Which payload key fills which column is data (idx_event_annotation_terms_map), not code: a new action type or key is
-- one row there, read by the function on the next refresh. A mapped value that is not a plain number reads NULL.
-- Rollback (forward-only): restore the 20261025_013 function body by a later migration; the new columns stay NULL.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

DO $preflight$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = 'idx_event_annotation') <> 26 THEN
        RAISE EXCEPTION 'idx_event_annotation does not have the 26 columns of 20261025_013';
    END IF;
    IF to_regclass('public.idx_event_annotation_terms_map') IS NOT NULL THEN
        RAISE EXCEPTION 'idx_event_annotation_terms_map already exists';
    END IF;
END
$preflight$;

ALTER TABLE public.idx_event_annotation
    ADD COLUMN cum_date date,
    ADD COLUMN ex_date date,
    ADD COLUMN record_date date,
    ADD COLUMN pay_date date,
    ADD COLUMN start_date date,
    ADD COLUMN end_date date,
    ADD COLUMN amount_per_share numeric,
    ADD COLUMN currency text,
    ADD COLUMN ratio_old numeric,
    ADD COLUMN ratio_new numeric;

CREATE TABLE public.idx_event_annotation_terms_map (
    action_type text NOT NULL,
    target_column text NOT NULL CHECK (target_column = ANY (ARRAY['amount_per_share','currency','ratio_old','ratio_new'])),
    payload_key text NOT NULL CHECK (btrim(payload_key) <> ''),
    meaning text NOT NULL,
    PRIMARY KEY (action_type, target_column)
);
COMMENT ON TABLE public.idx_event_annotation_terms_map IS
 'Which stockbit_corporate_action.source_payload key fills which term column of idx_event_annotation, per action type; read by refresh_idx_event_annotation().';

INSERT INTO public.idx_event_annotation_terms_map (action_type, target_column, payload_key, meaning) VALUES
 ('DIVIDEND', 'amount_per_share', 'dividend_value', 'Cash dividend per share, in currency.'),
 ('DIVIDEND', 'currency', 'dividend_currency', 'Currency of the dividend (Stockbit CURRENCY_ prefix removed).'),
 ('STOCK_SPLIT', 'ratio_old', 'stocksplit_old', 'Shares held before the split.'),
 ('STOCK_SPLIT', 'ratio_new', 'stocksplit_new', 'Shares held after the split for ratio_old before.'),
 ('REVERSE_SPLIT', 'ratio_old', 'stocksplit_old', 'Shares held before the reverse split.'),
 ('REVERSE_SPLIT', 'ratio_new', 'stocksplit_new', 'Shares held after the reverse split for ratio_old before.'),
 ('BONUS_SHARE', 'ratio_old', 'stocksplit_old', 'Shares held that entitle to ratio_new bonus shares.'),
 ('BONUS_SHARE', 'ratio_new', 'stocksplit_new', 'Bonus shares received for ratio_old held.'),
 ('RIGHT_ISSUE', 'ratio_old', 'rightissue_old', 'Shares held that entitle to ratio_new new shares.'),
 ('RIGHT_ISSUE', 'ratio_new', 'rightissue_new', 'New shares offered for ratio_old held.'),
 ('RIGHT_ISSUE', 'amount_per_share', 'rightissue_price', 'Exercise price per new share, IDR.'),
 ('WARRANT', 'amount_per_share', 'wrant_exc_price', 'Exercise price per share, IDR.'),
 ('TENDER_OFFER', 'amount_per_share', 'tender_price', 'Tender offer price per share, IDR.');

CREATE OR REPLACE FUNCTION public.refresh_idx_event_annotation() RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE n bigint;
BEGIN
 -- full rebuild from the active source rows; the caller owns the transaction
 DELETE FROM public.idx_event_annotation;
 INSERT INTO public.idx_event_annotation (event_key, event_family, event_type, ticker, instrument_code, annotation_date,
   annotation_date_role, cum_date, ex_date, record_date, pay_date, start_date, end_date, amount_per_share, currency,
   ratio_old, ratio_new, source_payload, source_endpoint, source_fetched_at)
 SELECT 'CA:' || c.corporate_action_key, 'CORPORATE_ACTION', c.action_type, c.ticker, c.instrument_code,
        c.annotation_date, c.annotation_date_role, c.cum_date, c.ex_date, c.record_date, c.pay_date, c.start_date,
        c.end_date, t.amount_per_share, t.currency, t.ratio_old, t.ratio_new, c.source_payload,
        '/corpaction/' || c.source_slug, c.last_seen_at
 FROM public.stockbit_corporate_action c
 LEFT JOIN LATERAL (
   -- terms from the payload keys the map names for this action type; a value that is not a plain number is NULL
   SELECT max(CASE WHEN m.target_column = 'amount_per_share' AND v.v ~ '^-?[0-9]+(\.[0-9]+)?$' THEN v.v::numeric END) AS amount_per_share,
          max(CASE WHEN m.target_column = 'currency' THEN regexp_replace(v.v, '^CURRENCY_', '') END) AS currency,
          max(CASE WHEN m.target_column = 'ratio_old' AND v.v ~ '^-?[0-9]+(\.[0-9]+)?$' THEN v.v::numeric END) AS ratio_old,
          max(CASE WHEN m.target_column = 'ratio_new' AND v.v ~ '^-?[0-9]+(\.[0-9]+)?$' THEN v.v::numeric END) AS ratio_new
   FROM public.idx_event_annotation_terms_map m
   CROSS JOIN LATERAL (SELECT nullif(btrim(c.source_payload ->> m.payload_key), '') AS v) v
   WHERE m.action_type = c.action_type
 ) t ON true
 WHERE c.source_removed_at IS NULL;
 INSERT INTO public.idx_event_annotation (event_key, event_family, event_type, ticker, annotation_date,
   annotation_date_role, action, holder_name, holder_role, holder_nationality, broker_code, shares_before, shares_after,
   shares_change, pct_after, pct_change, pct_quality_flag, price, is_estimated_price, value_idr, data_origin,
   source_payload, source_endpoint, source_fetched_at)
 SELECT insider_key, 'INSIDER', 'INSIDER_TRANSACTION', ticker, transaction_date, 'TRANSACTION_DATE', action_type,
        holder_name, NULLIF(array_to_string(holder_roles, ', '), ''), holder_nationality, broker_code, shares_before,
        shares_after, shares_change, pct_after, pct_change, pct_quality_flag, price, is_estimated_price, value_idr,
        data_origin, source_payload, '/insider/company/majorholder', last_seen_at
 FROM public.stockbit_insider_transaction WHERE source_removed_at IS NULL;
 SELECT count(*) INTO n FROM public.idx_event_annotation;
 RETURN n;
END $fn$;
COMMENT ON FUNCTION public.refresh_idx_event_annotation() IS
 'Rebuilds idx_event_annotation from the active rows of stockbit_corporate_action and stockbit_insider_transaction, with the corporate action dates and the terms named by idx_event_annotation_terms_map; returns the row count. Called by apps/stockbit-event-annotation/job.py inside its load transaction.';

SELECT public.refresh_idx_event_annotation();

DO $grant$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb') THEN
  GRANT SELECT ON public.idx_event_annotation_terms_map TO pgweb;
 END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb_reader') THEN
  GRANT SELECT ON public.idx_event_annotation_terms_map TO pgweb_reader;
 END IF;
END $grant$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule)
VALUES ('public', 'idx_event_annotation_terms_map', 'Reference',
 'Which Stockbit corporate action payload key fills which term column of idx_event_annotation (amount_per_share, currency, ratio_old, ratio_new), per action type.',
 'One action type and target column', ARRAY['action_type','target_column'], 'Saniti (read from live Stockbit payloads)',
 ARRAY['stockbit_corporate_action'], ARRAY['database/migrations/20261026_002_event_annotation_terms.sql'],
 'Changed by migration when Stockbit adds an action type or key; read on every refresh_idx_event_annotation().',
 ARRAY['refresh_idx_event_annotation'], 'VERIFIED', 'NOT_APPLICABLE', NULL, NULL, 'Static mapping.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

UPDATE public."Table_Catalog"
SET definition = 'Corporate actions (type, dates and terms: cum, ex, record and pay dates, period start and end, amount per share, currency, old:new ratio) and insider transactions (action, holder, broker, current percent, change percent, quality flag, origin IDX/KSEI) of IDX stocks; the annotation source of EDGE price charts and the event table the AI reads.',
    source_tables = ARRAY['stockbit_corporate_action','stockbit_insider_transaction','idx_event_annotation_terms_map'],
    source_code_paths = CASE WHEN 'database/migrations/20261026_002_event_annotation_terms.sql' = ANY (source_code_paths)
                             THEN source_code_paths
                             ELSE array_append(source_code_paths, 'database/migrations/20261026_002_event_annotation_terms.sql') END,
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND table_name = 'idx_event_annotation';

WITH d(table_name, column_name, definition, unit, null_rule) AS (VALUES
 ('idx_event_annotation','cum_date','Cum date: last trading date to hold the share and receive the action (dividend, split, bonus, rights).',NULL,'NULL for insider rows and for types without a cum date (warrant, tender offer, RUPS, public expose).'),
 ('idx_event_annotation','ex_date','Ex date: first trading date without the entitlement (dividend, split, bonus, rights).',NULL,'NULL for insider rows and for types without an ex date.'),
 ('idx_event_annotation','record_date','Recording date of the shareholder register (RUPS: eligible date).',NULL,'NULL for insider rows and for types without one (warrant, tender offer, public expose).'),
 ('idx_event_annotation','pay_date','Payment or distribution date (dividend, bonus share, tender offer).',NULL,'NULL for insider rows and for other types.'),
 ('idx_event_annotation','start_date','Start of the period: rights trading, warrant trading, tender offer; RUPS or public expose date.',NULL,'NULL for insider rows and for dividend, split and bonus.'),
 ('idx_event_annotation','end_date','End of the period: rights trading, warrant trading, tender offer.',NULL,'NULL for insider rows and for types without a period.'),
 ('idx_event_annotation','amount_per_share','Amount per share: cash dividend (in currency), rights exercise price, warrant exercise price or tender offer price (IDR).','IDR per share','NULL for insider rows, for split, reverse split, bonus, RUPS and public expose, and when Stockbit gives no number; 2 dividend rows are 0 at the source.'),
 ('idx_event_annotation','currency','Currency of a dividend as Stockbit gives it (IDR for every row on 2026-10-26).',NULL,'NULL for rows other than dividends; rights, warrant and tender prices are IDR.'),
 ('idx_event_annotation','ratio_old','Old side of the ratio: shares held before a split or reverse split, or shares held that entitle to ratio_new (bonus, rights).','shares','NULL for insider rows and for types without a ratio (dividend, warrant, tender offer, RUPS, public expose).'),
 ('idx_event_annotation','ratio_new','New side of the ratio: shares after a split or reverse split for ratio_old before, or bonus or new rights shares received for ratio_old held.','shares','NULL for insider rows and for types without a ratio.'),
 ('idx_event_annotation_terms_map','action_type','Corporate action type of stockbit_corporate_action.',NULL,'Never NULL.'),
 ('idx_event_annotation_terms_map','target_column','Term column of idx_event_annotation: amount_per_share, currency, ratio_old, ratio_new.',NULL,'Never NULL.'),
 ('idx_event_annotation_terms_map','payload_key','Key of stockbit_corporate_action.source_payload that holds the value.',NULL,'Never NULL.'),
 ('idx_event_annotation_terms_map','meaning','What the value means for this action type.',NULL,'Never NULL.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 c.table_name = 'idx_event_annotation_terms_map' AND c.column_name IN ('action_type','target_column'), d.definition,
 CASE WHEN c.table_name = 'idx_event_annotation' AND c.column_name LIKE '%\_date' ESCAPE '\'
      THEN 'stockbit_corporate_action.' || c.column_name
      WHEN c.table_name = 'idx_event_annotation'
      THEN 'stockbit_corporate_action.source_payload via idx_event_annotation_terms_map'
      ELSE 'database/migrations/20261026_002_event_annotation_terms.sql' END,
 d.unit, d.null_rule,
 ARRAY['database/migrations/20261026_002_event_annotation_terms.sql'], 'VERIFIED'
FROM information_schema.columns c JOIN d USING (table_name, column_name)
WHERE c.table_schema = 'public'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

-- the AI reads the new columns (onboarding 20261025_015 pattern); semantic types follow annotation_date and price
WITH r(column_name, semantic_type, aggs, description_id) AS (VALUES
 ('cum_date', 'TIME', ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], 'Tanggal cum: hari bursa terakhir memegang saham agar berhak atas aksi korporasi (dividen, split, saham bonus, rights).'),
 ('ex_date', 'TIME', ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], 'Tanggal ex: hari bursa pertama saham diperdagangkan tanpa hak tersebut.'),
 ('record_date', 'TIME', ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], 'Tanggal pencatatan (recording date) daftar pemegang saham; untuk RUPS tanggal pemegang saham yang berhak hadir.'),
 ('pay_date', 'TIME', ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], 'Tanggal pembayaran atau pembagian (dividen, saham bonus, tender offer).'),
 ('start_date', 'TIME', ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], 'Awal periode: perdagangan rights atau waran, masa tender offer; tanggal RUPS atau public expose.'),
 ('end_date', 'TIME', ARRAY['COUNT','COUNT_DISTINCT','MIN','MAX'], 'Akhir periode: perdagangan rights atau waran, masa tender offer.'),
 ('amount_per_share', 'MEASURE', ARRAY['MIN','MAX','AVG'], 'Nilai per lembar: dividen tunai (dalam currency), harga pelaksanaan rights, harga pelaksanaan waran, atau harga tender offer (rupiah).'),
 ('currency', 'DIMENSION', ARRAY['COUNT','COUNT_DISTINCT'], 'Mata uang dividen dari Stockbit (semuanya IDR per 2026-10-26).'),
 ('ratio_old', 'MEASURE', ARRAY['MIN','MAX','AVG'], 'Sisi lama rasio: jumlah saham sebelum split atau reverse split, atau saham yang dimiliki untuk mendapat ratio_new (bonus, rights).'),
 ('ratio_new', 'MEASURE', ARRAY['MIN','MAX','AVG'], 'Sisi baru rasio: jumlah saham sesudah split atau reverse split, atau saham bonus atau saham baru rights yang diterima per ratio_old.'))
INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis, description_id, description_id_status, entity_name)
SELECT c.table_name, c.column_name, c.ordinal_position, k.definition || coalesce(' Null: ' || k.null_rule, ''),
       c.data_type, r.semantic_type, k.unit, c.is_nullable = 'YES', false, k.source_column_or_expression, false, true,
       r.aggs, true, r.semantic_type <> 'MEASURE', NULL, false, 'PARTIAL', NULL, NULL, 'HISTORICAL',
       r.description_id, 'DRAFT', false
FROM information_schema.columns AS c
JOIN r ON r.column_name = c.column_name
JOIN public."Column_Catalog" AS k ON k.table_schema = 'public' AND k.table_name = c.table_name AND k.column_name = c.column_name
WHERE c.table_schema = 'public' AND c.table_name = 'idx_event_annotation';

UPDATE public."AI_table_catalog"
SET description = replace(description,
      'annotation_date is the ex date, trading start, offer start, meeting or expose date (annotation_date_role).',
      'annotation_date is the ex date, trading start, offer start, meeting or expose date (annotation_date_role). '
      || 'Terms of a corporate action are typed columns: cum_date, ex_date, record_date, pay_date, start_date, end_date, '
      || 'amount_per_share (dividen per lembar, harga rights, waran or tender, IDR), currency, and the ratio '
      || 'ratio_old:ratio_new (stock split, reverse split, saham bonus, rights issue).'),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'idx_event_annotation';

DO $verify$
BEGIN
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = 'idx_event_annotation') <> 36 THEN
        RAISE EXCEPTION 'idx_event_annotation should have 36 columns';
    END IF;
    IF (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'idx_event_annotation') <> 36
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'idx_event_annotation' AND ai_allowed) <> 32 THEN
        RAISE EXCEPTION 'Expected 36 AI_column_catalog rows, 32 visible';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns c WHERE c.table_schema = 'public'
               AND c.table_name IN ('idx_event_annotation', 'idx_event_annotation_terms_map')
               AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public'
                               AND k.table_name = c.table_name AND k.column_name = c.column_name)) THEN
        RAISE EXCEPTION 'A column lacks its Column_Catalog row';
    END IF;
    IF (SELECT description FROM public."AI_table_catalog" WHERE table_name = 'idx_event_annotation') NOT LIKE '%amount_per_share%' THEN
        RAISE EXCEPTION 'AI_table_catalog description was not extended';
    END IF;
    -- every mapped key that holds a value in an active source row lands as a non-NULL term
    IF EXISTS (SELECT 1 FROM public.stockbit_corporate_action c
               JOIN public.idx_event_annotation_terms_map m ON m.action_type = c.action_type
               JOIN public.idx_event_annotation e ON e.event_key = 'CA:' || c.corporate_action_key
               WHERE c.source_removed_at IS NULL AND nullif(btrim(c.source_payload ->> m.payload_key), '') IS NOT NULL
                 AND CASE m.target_column WHEN 'amount_per_share' THEN e.amount_per_share IS NULL
                                          WHEN 'currency' THEN e.currency IS NULL
                                          WHEN 'ratio_old' THEN e.ratio_old IS NULL
                                          ELSE e.ratio_new IS NULL END) THEN
        RAISE EXCEPTION 'A mapped source value did not land as a number';
    END IF;
END
$verify$;
COMMIT;
