-- EXEC-EVENT-ANNOTATION (user go 2026-10-25): Stockbit corporate actions and insider movements, and the one annotation
-- table EDGE reads. Loaded by apps/stockbit-event-annotation/job.py (full pull + reconcile on every update).
BEGIN;

CREATE TABLE public.stockbit_corporate_action (
 corporate_action_key text PRIMARY KEY CHECK (corporate_action_key ~ '^[a-z_]+:[^:]+$'),
 action_type text NOT NULL CHECK (action_type = ANY (ARRAY['DIVIDEND','STOCK_DIVIDEND','STOCK_SPLIT','REVERSE_SPLIT',
   'BONUS_SHARE','RIGHT_ISSUE','WARRANT','TENDER_OFFER','RUPS','PUBLIC_EXPOSE'])),
 source_slug text NOT NULL,
 source_record_id text NOT NULL,
 symbol text NOT NULL CHECK (symbol = upper(btrim(symbol)) AND symbol <> ''),
 ticker text NOT NULL CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''),
 instrument_code text,
 annotation_date date NOT NULL,
 annotation_date_role text NOT NULL CHECK (annotation_date_role = ANY (ARRAY['EX_DATE','TRADING_START','OFFER_START',
   'MEETING_DATE','EXPOSE_DATE'])),
 cum_date date,
 ex_date date,
 record_date date,
 pay_date date,
 start_date date,
 end_date date,
 source_payload jsonb NOT NULL,
 first_seen_at timestamptz NOT NULL,
 last_seen_at timestamptz NOT NULL,
 source_removed_at timestamptz,
 load_run_id text NOT NULL,
 ingestion_time timestamptz NOT NULL DEFAULT statement_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 UNIQUE (source_slug, source_record_id),
 CHECK (corporate_action_key = source_slug || ':' || source_record_id),
 CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX stockbit_corporate_action_ticker_date_idx ON public.stockbit_corporate_action (ticker, annotation_date);
COMMENT ON TABLE public.stockbit_corporate_action IS
 'Stockbit corporate actions (dividend, stock split, reverse split, bonus share, rights issue, warrant incl. structured warrants, tender offer, RUPS shareholder meeting, public expose), one row per Stockbit event id, full-pulled and reconciled per update; source of idx_event_annotation.';

CREATE TABLE public.stockbit_insider_transaction (
 insider_key text PRIMARY KEY CHECK (insider_key ~ '^INS:[0-9a-f]{24}:[1-9][0-9]*$'),
 ticker text NOT NULL CHECK (ticker = upper(btrim(ticker)) AND ticker <> ''),
 transaction_date date NOT NULL,
 action_type text NOT NULL,
 holder_id text,
 holder_name text,
 holder_roles text[] NOT NULL DEFAULT '{}',
 holder_nationality text,
 broker_code text,
 shares_before numeric NOT NULL,
 shares_after numeric NOT NULL,
 shares_change numeric NOT NULL,
 pct_before numeric,
 pct_after numeric,
 pct_change numeric,
 pct_quality_flag text NOT NULL CHECK (pct_quality_flag = ANY (ARRAY['OK','ROUNDING','INCONSISTENT','NOT_CHECKABLE',
   'INVALID_SENTINEL'])),
 price numeric,
 is_estimated_price boolean NOT NULL,
 value_idr numeric,
 data_origin text NOT NULL,
 source_copies integer NOT NULL CHECK (source_copies >= 1),
 source_payload jsonb NOT NULL,
 first_seen_at timestamptz NOT NULL,
 last_seen_at timestamptz NOT NULL,
 source_removed_at timestamptz,
 load_run_id text NOT NULL,
 ingestion_time timestamptz NOT NULL DEFAULT statement_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 CHECK (shares_after - shares_before = shares_change),
 CHECK (last_seen_at >= first_seen_at)
);
CREATE INDEX stockbit_insider_transaction_ticker_date_idx ON public.stockbit_insider_transaction (ticker, transaction_date);
COMMENT ON TABLE public.stockbit_insider_transaction IS
 'Stockbit insider / major holder (IDX insider reports and KSEI 5% holder changes) share movements: who bought or sold, broker, shares and ownership percent; one row per distinct movement, full-pulled and reconciled per update; source of idx_event_annotation.';

CREATE TABLE public.idx_event_annotation (
 event_key text PRIMARY KEY,
 event_family text NOT NULL CHECK (event_family = ANY (ARRAY['CORPORATE_ACTION','INSIDER'])),
 event_type text NOT NULL CHECK (event_type = ANY (ARRAY['DIVIDEND','STOCK_DIVIDEND','STOCK_SPLIT','REVERSE_SPLIT',
   'BONUS_SHARE','RIGHT_ISSUE','WARRANT','TENDER_OFFER','RUPS','PUBLIC_EXPOSE','INSIDER_TRANSACTION'])),
 ticker text NOT NULL,
 instrument_code text,
 annotation_date date NOT NULL,
 annotation_date_role text NOT NULL CHECK (annotation_date_role = ANY (ARRAY['EX_DATE','TRADING_START','OFFER_START',
   'MEETING_DATE','EXPOSE_DATE','TRANSACTION_DATE'])),
 action text,
 holder_name text,
 holder_role text,
 holder_nationality text,
 broker_code text,
 shares_before numeric,
 shares_after numeric,
 shares_change numeric,
 pct_after numeric,
 pct_change numeric,
 pct_quality_flag text,
 price numeric,
 is_estimated_price boolean,
 value_idr numeric,
 data_origin text,
 source_payload jsonb NOT NULL,
 source_endpoint text NOT NULL,
 source_fetched_at timestamptz NOT NULL,
 ingestion_time timestamptz NOT NULL DEFAULT statement_timestamp(),
 CHECK ((event_family = 'INSIDER') = (event_type = 'INSIDER_TRANSACTION')),
 CHECK (event_family <> 'INSIDER' OR (action IS NOT NULL AND data_origin IS NOT NULL AND shares_change IS NOT NULL
   AND pct_quality_flag IS NOT NULL))
);
CREATE INDEX idx_event_annotation_ticker_date_idx ON public.idx_event_annotation (ticker, annotation_date);
CREATE INDEX idx_event_annotation_family_date_idx ON public.idx_event_annotation (event_family, annotation_date);
COMMENT ON TABLE public.idx_event_annotation IS
 'One annotation source for EDGE price charts: IDX stock corporate actions (type and date) and insider transactions (who, broker, current and change percent, origin IDX/KSEI), rebuilt from stockbit_corporate_action and stockbit_insider_transaction by refresh_idx_event_annotation().';

CREATE FUNCTION public.refresh_idx_event_annotation() RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE n bigint;
BEGIN
 -- full rebuild from the active source rows; the caller owns the transaction
 DELETE FROM public.idx_event_annotation;
 INSERT INTO public.idx_event_annotation (event_key, event_family, event_type, ticker, instrument_code, annotation_date,
   annotation_date_role, source_payload, source_endpoint, source_fetched_at)
 SELECT 'CA:' || corporate_action_key, 'CORPORATE_ACTION', action_type, ticker, instrument_code, annotation_date,
        annotation_date_role, source_payload, '/corpaction/' || source_slug, last_seen_at
 FROM public.stockbit_corporate_action WHERE source_removed_at IS NULL;
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
 'Rebuilds idx_event_annotation from the active rows of stockbit_corporate_action and stockbit_insider_transaction; returns the row count. Called by apps/stockbit-event-annotation/job.py inside its load transaction.';

DO $grant$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgweb') THEN
  GRANT SELECT ON public.stockbit_corporate_action, public.stockbit_insider_transaction, public.idx_event_annotation TO pgweb;
 END IF;
END $grant$;

INSERT INTO public."Table_Catalog"(table_schema, table_name, category, definition, grain, primary_key_columns,
 source_system, source_tables, source_code_paths, update_rule, related_functions, documentation_status,
 readiness_mode, readiness_date_column, observation_date_column, availability_rule)
VALUES
('public','stockbit_corporate_action','Transactional',
 'Stockbit corporate actions of IDX listed securities: dividend, stock split, reverse split, bonus share, rights issue, warrant (structured warrants on their underlying ticker), tender offer, RUPS and public expose. Typed key dates plus the verbatim Stockbit row.',
 'One Stockbit corporate action (type slug x Stockbit event id)', ARRAY['corporate_action_key'],
 'Stockbit exodus /corpaction/{type}?year=', ARRAY[]::text[],
 ARRAY['apps/stockbit-event-annotation/stockbit_events.py','apps/stockbit-event-annotation/job.py',
       'database/migrations/20261025_011_create_stockbit_event_annotation.sql'],
 'Ad hoc on user request: full pull of every type and year, reconciled (new inserted, changed updated, absent marked source_removed_at); UPDATE_TABLE.md.',
 ARRAY['refresh_idx_event_annotation'], 'VERIFIED', 'NOT_APPLICABLE', NULL, 'annotation_date',
 'Event dates are announced schedules; last_seen_at is when Saniti last saw the row.'),
('public','stockbit_insider_transaction','Transactional',
 'Stockbit insider and major holder share movements of IDX stocks (IDX insider reports and KSEI 5% holder changes): holder, role, nationality, broker, shares before/after/change, ownership percent, price, value, origin.',
 'One distinct movement: ticker, holder id, date, action, shares before/after/change, price, origin, payload variant', ARRAY['insider_key'],
 'Stockbit exodus /insider/company/majorholder', ARRAY[]::text[],
 ARRAY['apps/stockbit-event-annotation/stockbit_events.py','apps/stockbit-event-annotation/job.py',
       'database/migrations/20261025_011_create_stockbit_event_annotation.sql'],
 'Ad hoc on user request: full pull per ticker, reconciled (new inserted, changed updated, absent marked source_removed_at); UPDATE_TABLE.md.',
 ARRAY['refresh_idx_event_annotation'], 'VERIFIED', 'NOT_APPLICABLE', NULL, 'transaction_date',
 'KSEI rows carry the report date of the position, not always the trade date; last_seen_at is when Saniti last saw the row.'),
('public','idx_event_annotation','Feature',
 'One annotation source for EDGE price charts: corporate actions (type and date only) and insider transactions (action, holder, broker, current percent, change percent, quality flag, origin IDX/KSEI).',
 'One event: corporate action or insider movement', ARRAY['event_key'],
 'Derived from Stockbit source tables', ARRAY['stockbit_corporate_action','stockbit_insider_transaction'],
 ARRAY['database/migrations/20261025_011_create_stockbit_event_annotation.sql','apps/stockbit-event-annotation/job.py'],
 'Rebuilt by refresh_idx_event_annotation() at the end of every Stockbit event load, in the same transaction.',
 ARRAY['refresh_idx_event_annotation'], 'VERIFIED', 'NOT_APPLICABLE', NULL, 'annotation_date',
 'Same as the source tables; source_fetched_at is the last pull that saw the row.')
ON CONFLICT (table_schema, table_name) DO NOTHING;

WITH d(table_name, column_name, definition, unit, null_rule) AS (VALUES
 ('stockbit_corporate_action','corporate_action_key','Stable key: Stockbit type slug, colon, Stockbit event id (e.g. dividend:12345).',NULL,'Never NULL.'),
 ('stockbit_corporate_action','action_type','Corporate action type: DIVIDEND, STOCK_DIVIDEND, STOCK_SPLIT, REVERSE_SPLIT, BONUS_SHARE, RIGHT_ISSUE, WARRANT, TENDER_OFFER, RUPS, PUBLIC_EXPOSE.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','source_slug','Stockbit endpoint slug of /corpaction/{slug}.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','source_record_id','Stockbit event id from the type''s id field (dividend_id, stocksplit_id, ...).',NULL,'Never NULL.'),
 ('stockbit_corporate_action','symbol','Security code as Stockbit gives it (company_symbol), including structured-warrant codes.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','ticker','Chart ticker: the 4-letter underlying of a structured warrant (IDX code pattern AAAA + 6 characters, underlying a known stock), else symbol.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','instrument_code','Original structured-warrant code when ticker is its underlying.',NULL,'NULL when ticker = symbol.'),
 ('stockbit_corporate_action','annotation_date','Chart marker date: ex date (dividend, split, bonus, rights), trading start (warrant), offer start (tender), meeting date (RUPS), expose date.',NULL,'Never NULL; a row without it stops the load.'),
 ('stockbit_corporate_action','annotation_date_role','Meaning of annotation_date: EX_DATE, TRADING_START, OFFER_START, MEETING_DATE, EXPOSE_DATE.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','cum_date','Cum date from Stockbit.',NULL,'NULL when the type has no cum date or Stockbit gives none.'),
 ('stockbit_corporate_action','ex_date','Ex date from Stockbit.',NULL,'NULL when the type has no ex date or Stockbit gives none.'),
 ('stockbit_corporate_action','record_date','Recording date (RUPS: eligible date).',NULL,'NULL when not applicable or not given.'),
 ('stockbit_corporate_action','pay_date','Payment date (dividend, bonus, tender).',NULL,'NULL when not applicable or not given.'),
 ('stockbit_corporate_action','start_date','Start of the period: rights trading, warrant trading, tender offer, RUPS or expose date.',NULL,'NULL when not applicable or not given.'),
 ('stockbit_corporate_action','end_date','End of the period: rights trading, warrant trading, tender offer.',NULL,'NULL when not applicable or not given.'),
 ('stockbit_corporate_action','source_payload','Verbatim Stockbit row; every detail (ratios, prices, venues) is kept here.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','first_seen_at','First pull that saw the row.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','last_seen_at','Latest pull that saw the row.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','source_removed_at','First pull that no longer returned the row; the row is kept, not deleted.',NULL,'NULL while Stockbit still returns the row.'),
 ('stockbit_corporate_action','load_run_id','Run id of the latest load that wrote the row.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','ingestion_time','Database time of the first insert.',NULL,'Never NULL.'),
 ('stockbit_corporate_action','updated_at','Database time of the latest change of the row''s content or removal state.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','insider_key','Stable key: INS, hash of ticker, holder id, date, action, shares before/after/change, price and origin, and the payload variant number.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','ticker','IDX stock code.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','transaction_date','Movement date from Stockbit (KSEI: report date of the position).',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','action_type','Movement type from Stockbit without the ACTION_TYPE_ prefix: BUY, SELL, CROSS, TRANSFER, RIGHT_ISSUE, WARRANT_EXERCISE, ...',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','holder_id','Stockbit holder id (the API field id identifies the holder, not the movement).',NULL,'NULL when Stockbit gives none.'),
 ('stockbit_insider_transaction','holder_name','Holder name.',NULL,'NULL when Stockbit gives none.'),
 ('stockbit_insider_transaction','holder_roles','Insider roles: DIREKTUR, KOMISARIS, PENGENDALI.',NULL,'Empty array when Stockbit gives no badge.'),
 ('stockbit_insider_transaction','holder_nationality','LOCAL or FOREIGN.',NULL,'NULL when Stockbit gives none.'),
 ('stockbit_insider_transaction','broker_code','Broker code of the movement.',NULL,'NULL when Stockbit gives none (about half of the rows).'),
 ('stockbit_insider_transaction','shares_before','Shares held before the movement.','shares','Never NULL.'),
 ('stockbit_insider_transaction','shares_after','Shares held after the movement.','shares','Never NULL.'),
 ('stockbit_insider_transaction','shares_change','shares_after minus shares_before (positive buy/added, negative sell/reduced).','shares','Never NULL.'),
 ('stockbit_insider_transaction','pct_before','Stockbit ownership percent before, on the previous report''s share base (kept for completeness; not shown in the annotation).','% (5 = 5%)','NULL when Stockbit sends its overflow value; 0 may be a source placeholder (D21).'),
 ('stockbit_insider_transaction','pct_after','Current %: Stockbit ownership percent after the movement = shares_after / current shares outstanding.','% (5 = 5%)','NULL when Stockbit sends its overflow value (D21).'),
 ('stockbit_insider_transaction','pct_change','Change %: Stockbit shares_change / current shares outstanding; not pct_after minus pct_before.','% (5 = 5%)','NULL when Stockbit sends its overflow value (D21).'),
 ('stockbit_insider_transaction','pct_quality_flag','In-row check: pct_change vs pct_after x shares_change / shares_after: OK, ROUNDING, INCONSISTENT, NOT_CHECKABLE (shares_change or shares_after 0), INVALID_SENTINEL.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','price','Movement price per share.','IDR per share','NULL when Stockbit gives none.'),
 ('stockbit_insider_transaction','is_estimated_price','TRUE when the price is Stockbit''s estimate (most KSEI rows).',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','value_idr','Movement value (shares x price).','IDR','NULL when Stockbit gives none.'),
 ('stockbit_insider_transaction','data_origin','IDX (insider report) or KSEI (5% holder position change).',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','source_copies','How many identical copies of this movement Stockbit listed in the pull (exact duplicates are one row).','rows','Never NULL.'),
 ('stockbit_insider_transaction','source_payload','Verbatim Stockbit movement.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','first_seen_at','First pull that saw the row.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','last_seen_at','Latest pull that saw the row.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','source_removed_at','First pull that no longer returned the row; the row is kept, not deleted.',NULL,'NULL while Stockbit still returns the row.'),
 ('stockbit_insider_transaction','load_run_id','Run id of the latest load that wrote the row.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','ingestion_time','Database time of the first insert.',NULL,'Never NULL.'),
 ('stockbit_insider_transaction','updated_at','Database time of the latest change of the row''s content or removal state.',NULL,'Never NULL.'),
 ('idx_event_annotation','event_key','CA:<corporate_action_key> or the insider_key.',NULL,'Never NULL.'),
 ('idx_event_annotation','event_family','CORPORATE_ACTION or INSIDER.',NULL,'Never NULL.'),
 ('idx_event_annotation','event_type','Corporate action type or INSIDER_TRANSACTION.',NULL,'Never NULL.'),
 ('idx_event_annotation','ticker','Chart ticker.',NULL,'Never NULL.'),
 ('idx_event_annotation','instrument_code','Structured-warrant code shown on its underlying''s chart.',NULL,'NULL unless a structured warrant.'),
 ('idx_event_annotation','annotation_date','Chart marker date.',NULL,'Never NULL.'),
 ('idx_event_annotation','annotation_date_role','Meaning of annotation_date: EX_DATE, TRADING_START, OFFER_START, MEETING_DATE, EXPOSE_DATE, TRANSACTION_DATE.',NULL,'Never NULL.'),
 ('idx_event_annotation','action','Insider movement type (BUY, SELL, ...).',NULL,'NULL for corporate actions.'),
 ('idx_event_annotation','holder_name','Insider holder name.',NULL,'NULL for corporate actions.'),
 ('idx_event_annotation','holder_role','Insider roles joined by comma: DIREKTUR, KOMISARIS, PENGENDALI.',NULL,'NULL for corporate actions or without a badge.'),
 ('idx_event_annotation','holder_nationality','LOCAL or FOREIGN.',NULL,'NULL for corporate actions.'),
 ('idx_event_annotation','broker_code','Broker code of the insider movement.',NULL,'NULL for corporate actions or when Stockbit gives none.'),
 ('idx_event_annotation','shares_before','Shares before the insider movement.','shares','NULL for corporate actions.'),
 ('idx_event_annotation','shares_after','Shares after the insider movement.','shares','NULL for corporate actions.'),
 ('idx_event_annotation','shares_change','Change in shares (+ added, - reduced).','shares','NULL for corporate actions.'),
 ('idx_event_annotation','pct_after','Current % ownership after the movement (Stockbit).','% (5 = 5%)','NULL for corporate actions or when the source value is invalid (INVALID_SENTINEL).'),
 ('idx_event_annotation','pct_change','Change % = shares_change / current shares outstanding (Stockbit).','% (5 = 5%)','NULL for corporate actions or when the source value is invalid.'),
 ('idx_event_annotation','pct_quality_flag','In-row percent check: OK, ROUNDING, INCONSISTENT, NOT_CHECKABLE, INVALID_SENTINEL.',NULL,'NULL for corporate actions.'),
 ('idx_event_annotation','price','Insider movement price.','IDR per share','NULL for corporate actions or when not given.'),
 ('idx_event_annotation','is_estimated_price','TRUE when the insider price is Stockbit''s estimate.',NULL,'NULL for corporate actions.'),
 ('idx_event_annotation','value_idr','Insider movement value.','IDR','NULL for corporate actions or when not given.'),
 ('idx_event_annotation','data_origin','IDX or KSEI.',NULL,'NULL for corporate actions.'),
 ('idx_event_annotation','source_payload','Verbatim Stockbit row (corporate action details live here).',NULL,'Never NULL.'),
 ('idx_event_annotation','source_endpoint','Stockbit endpoint of the row.',NULL,'Never NULL.'),
 ('idx_event_annotation','source_fetched_at','Latest pull that saw the source row.',NULL,'Never NULL.'),
 ('idx_event_annotation','ingestion_time','Database time of the latest rebuild.',NULL,'Never NULL.'))
INSERT INTO public."Column_Catalog"(table_schema, table_name, column_name, ordinal_position, data_type, is_nullable,
 default_expression, is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths,
 documentation_status)
SELECT 'public', c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', c.column_default,
 c.column_name = ANY (ARRAY['corporate_action_key','insider_key','event_key']), d.definition,
 'apps/stockbit-event-annotation/stockbit_events.py', d.unit, d.null_rule,
 ARRAY['apps/stockbit-event-annotation/stockbit_events.py','database/migrations/20261025_011_create_stockbit_event_annotation.sql'],
 'VERIFIED'
FROM information_schema.columns c JOIN d USING (table_name, column_name)
WHERE c.table_schema = 'public'
ON CONFLICT (table_schema, table_name, column_name) DO NOTHING;

DO $check$ DECLARE missing int; BEGIN
 SELECT count(*) INTO missing FROM information_schema.columns c
 WHERE c.table_schema = 'public' AND c.table_name IN ('stockbit_corporate_action','stockbit_insider_transaction','idx_event_annotation')
   AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_schema = 'public' AND k.table_name = c.table_name
                   AND k.column_name = c.column_name);
 IF missing > 0 THEN RAISE EXCEPTION '% columns lack a Column_Catalog row', missing; END IF;
END $check$;

COMMIT;
