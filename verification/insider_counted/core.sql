-- EXEC-INSIDER-COUNT core (user decisions 2026-11-01, ERRORS M241/M242). The migration runs this file as is; the
-- rehearsal (rehearse_job.py) runs it with public.idx_event_annotation and public.refresh_idx_event_annotation
-- replaced by pg_temp copies, so both run the same text.
--
-- counted: the row a count or a sum of insider movements uses. Every IDX report is counted. A KSEI row (KSEI's own
-- daily change of a 5% holder, estimated price, report date) is counted only when the same holder of the same ticker
-- has no IDX report within WINDOW_DAYS calendar days: the holder reported to IDX in that period, so IDX is used.
-- count_reason names why; covered_by_event_keys lists the IDX reports that cover a KSEI row. Corporate actions are
-- counted (the rule is insider only). No row is removed.
-- M242: a price or value Stockbit shows as "-" (raw 0) is unknown and stored NULL.

ALTER TABLE public.idx_event_annotation
  ADD COLUMN counted boolean,
  ADD COLUMN count_reason text,
  ADD COLUMN covered_by_event_keys text[];

CREATE OR REPLACE FUNCTION public.refresh_idx_event_annotation() RETURNS bigint
LANGUAGE plpgsql AS $fn$
DECLARE
 n bigint;
 window_days CONSTANT integer := 5;  -- user 2026-11-01 "1 setuju" (±5 days)
BEGIN
 -- full rebuild from the active source rows; the caller owns the transaction
 DELETE FROM public.idx_event_annotation;
 INSERT INTO public.idx_event_annotation (event_key, event_family, event_type, ticker, instrument_code, annotation_date,
   annotation_date_role, cum_date, ex_date, record_date, pay_date, start_date, end_date, amount_per_share, currency,
   ratio_old, ratio_new, source_payload, source_endpoint, source_fetched_at, counted, count_reason)
 SELECT 'CA:' || c.corporate_action_key, 'CORPORATE_ACTION', c.action_type, c.ticker, c.instrument_code,
        c.annotation_date, c.annotation_date_role, c.cum_date, c.ex_date, c.record_date, c.pay_date, c.start_date,
        c.end_date, t.amount_per_share, t.currency, t.ratio_old, t.ratio_new, c.source_payload,
        '/corpaction/' || c.source_slug, c.last_seen_at, true, 'CORPORATE_ACTION'
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
   source_payload, source_endpoint, source_fetched_at, counted, count_reason, covered_by_event_keys)
 WITH s AS (
   SELECT i.*, nullif(lower(regexp_replace(btrim(i.holder_name), '\s+', ' ', 'g')), '') AS holder_folded,  -- case and spaces
          -- M242: "-" is Stockbit's mark for an unknown amount; a real 0 stays 0
          CASE WHEN i.source_payload -> 'price' ->> 'formatted' = '-' THEN NULL ELSE i.price END AS price_known,
          CASE WHEN i.source_payload -> 'value' ->> 'formatted' = '-' THEN NULL ELSE i.value_idr END AS value_known
   FROM public.stockbit_insider_transaction i WHERE i.source_removed_at IS NULL
 ), idx AS (
   SELECT insider_key, ticker, holder_folded, transaction_date, shares_change FROM s WHERE data_origin = 'IDX'
 ), k AS (
   SELECT s.insider_key,
          array_agg(x.insider_key ORDER BY x.transaction_date, x.insider_key)
            FILTER (WHERE x.insider_key IS NOT NULL) AS covered,
          bool_or(x.shares_change = s.shares_change) AS exact,
          -- KSEI's daily change equal to the sum of the holder's IDX reports in the days before it; a zero change
          -- (rights, splits) or no IDX report in that span is not an aggregate
          s.shares_change <> 0
            AND count(*) FILTER (WHERE s.transaction_date - x.transaction_date BETWEEN 0 AND window_days) > 0
            AND sum(x.shares_change) FILTER (WHERE s.transaction_date - x.transaction_date BETWEEN 0 AND window_days)
                = s.shares_change AS aggregated
   FROM s LEFT JOIN idx x ON x.ticker = s.ticker AND x.holder_folded = s.holder_folded
                          AND abs(s.transaction_date - x.transaction_date) <= window_days
   WHERE s.data_origin = 'KSEI'
   GROUP BY s.insider_key, s.shares_change, s.transaction_date
 )
 SELECT s.insider_key, 'INSIDER', 'INSIDER_TRANSACTION', s.ticker, s.transaction_date, 'TRANSACTION_DATE', s.action_type,
        s.holder_name, NULLIF(array_to_string(s.holder_roles, ', '), ''), s.holder_nationality, s.broker_code,
        s.shares_before, s.shares_after, s.shares_change, s.pct_after, s.pct_change, s.pct_quality_flag, s.price_known,
        s.is_estimated_price, s.value_known, s.data_origin, s.source_payload, '/insider/company/majorholder',
        s.last_seen_at,
        s.data_origin <> 'KSEI' OR k.covered IS NULL,
        -- an origin other than IDX and KSEI is counted under its own reason instead of failing the load
        CASE WHEN s.data_origin = 'IDX' THEN 'IDX'
             WHEN s.data_origin <> 'KSEI' THEN 'OTHER_ORIGIN'
             WHEN k.covered IS NULL THEN 'KSEI_ONLY'
             WHEN k.exact THEN 'KSEI_EXACT_IDX'
             WHEN k.aggregated THEN 'KSEI_AGGREGATED_IDX'
             ELSE 'KSEI_HOLDER_IN_IDX' END,
        k.covered
 FROM s LEFT JOIN k ON k.insider_key = s.insider_key;
 SELECT count(*) INTO n FROM public.idx_event_annotation;
 RETURN n;
END $fn$;

SELECT public.refresh_idx_event_annotation();

ALTER TABLE public.idx_event_annotation
  ALTER COLUMN counted SET NOT NULL,
  ALTER COLUMN count_reason SET NOT NULL,
  ADD CONSTRAINT idx_event_annotation_count_reason_check CHECK (count_reason = ANY (ARRAY['CORPORATE_ACTION', 'IDX',
    'OTHER_ORIGIN', 'KSEI_ONLY', 'KSEI_EXACT_IDX', 'KSEI_AGGREGATED_IDX', 'KSEI_HOLDER_IN_IDX'])),
  ADD CONSTRAINT idx_event_annotation_counted_check CHECK (counted = (count_reason IN ('CORPORATE_ACTION', 'IDX',
    'OTHER_ORIGIN', 'KSEI_ONLY'))),
  ADD CONSTRAINT idx_event_annotation_covered_check CHECK ((count_reason LIKE 'KSEI\_%IDX') = (covered_by_event_keys IS NOT NULL));
