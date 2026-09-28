-- IP1 Stage D (implementation plan IP1, 2026-09-27): point-in-time reference history and the metadata a
-- point-in-time DataNeedSpec is checked against. Scope approved by the user: history tables captured prospectively,
-- overlap prevention with an exclusion constraint (btree_gist), descriptive mode stays the default and point in time
-- is opt-in, refused where history is insufficient.
--
-- Three kinds of time are kept apart (IP1 D1):
--   effective   valid_from / valid_to  when a classification is in effect (captured rows: the Asia/Jakarta date Saniti
--                                       recorded it; the true date is on or before it and unknown: valid_basis)
--   available   available_at           when the information was available to decisions (recording time, or a
--                                       documented publication time given by a correction: available_basis)
--   recorded    recorded_from / _to    when Saniti recorded / superseded the row (knowledge time); superseded rows
--                                       are kept, never deleted
-- pit_valid_from / pit_valid_to (generated) is the point-in-time validity a join uses: the row applies to observation
-- date t when it was in effect on t and recorded before t (a value recorded on a date is used from the next date).
-- Recorded time is the conservative bound of availability (information cannot be recorded before it was available),
-- so selection never looks ahead; a documented earlier publication time is kept but not used for selection.
--
-- History starts at the first capture (this migration): nothing is claimed for earlier dates (no 2018 backfill). A key
-- missing from one load is counted in Reference_History_Capture_Log, never recorded as a delisting. The capture runs
-- in statement-level AFTER triggers on IDX_Stock_Universe and IDX_Broker_Profile; it never fails the reference load
-- (a failure is logged and the next capture, which compares the whole source with history, records the change later).
--
-- AI catalog: AI_column_catalog.value_time_basis (HISTORICAL / CURRENT_STATE), the two history tables, EFFECTIVE_DATED
-- relationships from the observation tables to them (effective columns pit_valid_from / pit_valid_to), and read access
-- for the SQL Governor to the history tables and to the Table_Catalog availability metadata.
--
-- Rollback (forward-only: write a new migration): set is_allowed=false on the EFFECTIVE_DATED relationships and
-- is_active=false on the two AI_table_catalog rows, and drop the two reference_history_capture triggers. The collected
-- history is kept.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $preflight$
BEGIN
    IF to_regclass('public."IDX_Stock_Universe_History"') IS NOT NULL
       OR to_regclass('public."IDX_Broker_Profile_History"') IS NOT NULL
       OR to_regclass('public."Reference_History_Capture_Log"') IS NOT NULL THEN
        RAISE EXCEPTION 'The reference history tables already exist';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'AI_column_catalog' AND column_name = 'value_time_basis') THEN
        RAISE EXCEPTION 'AI_column_catalog.value_time_basis already exists';
    END IF;
    IF (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AND (table_name, column_name) IN (
            ('IDX_Stock_Universe', 'Ticker'), ('IDX_Stock_Universe', 'Company Name'), ('IDX_Stock_Universe', 'Exchange'),
            ('IDX_Stock_Universe', 'Security Type'), ('IDX_Stock_Universe', 'Type Specs'),
            ('IDX_Stock_Universe', 'Is Common Stock'), ('IDX_Stock_Universe', 'ISIN'), ('IDX_Stock_Universe', 'Sector'),
            ('IDX_Stock_Universe', 'Industry'), ('IDX_Broker_Profile', 'broker_code'),
            ('IDX_Broker_Profile', 'broker_name'), ('IDX_Broker_Profile', 'broker_type'),
            ('IDX_Broker_Profile', 'broker_classification'))) <> 13 THEN
        RAISE EXCEPTION 'A tracked reference column is missing';
    END IF;
    IF (SELECT count(*) FROM pg_available_extensions WHERE name = 'btree_gist') <> 1 THEN
        RAISE EXCEPTION 'btree_gist is not available';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
               WHERE t.tgname = 'reference_history_capture') THEN
        RAISE EXCEPTION 'A reference_history_capture trigger already exists';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE tool_name = 'submit_data_need_spec' AND version = 'v3')
       OR NOT EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE tool_name = 'check_data_feasibility' AND version = 'v2')
       OR EXISTS (SELECT 1 FROM public."Tool_Catalog" WHERE (tool_name, version) IN
                  (('submit_data_need_spec', 'v4'), ('check_data_feasibility', 'v3'))) THEN
        RAISE EXCEPTION 'Unexpected Tool_Catalog versions for the DataNeed tools';
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('market_ai_sql_reader', 'market_ai_catalog_reader',
                                                        'pgweb_reader')) <> 3 THEN
        RAISE EXCEPTION 'An expected reader role is missing';
    END IF;
END
$preflight$;

-- BEGIN reference history core
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

CREATE TABLE public."Reference_History_Capture_Log" (
    capture_id bigint GENERATED ALWAYS AS IDENTITY,
    source_table text NOT NULL,
    trigger_operation text NOT NULL,
    captured_at timestamp with time zone NOT NULL DEFAULT now(),
    status text NOT NULL,
    source_rows integer,
    versions_changed integer,
    versions_opened integer,
    absent_entities integer,
    absent_examples text[] NOT NULL DEFAULT '{}',
    error text,
    CONSTRAINT "Reference_History_Capture_Log_pkey" PRIMARY KEY (capture_id),
    CONSTRAINT "Reference_History_Capture_Log_source_check"
        CHECK (source_table IN ('IDX_Stock_Universe', 'IDX_Broker_Profile')),
    CONSTRAINT "Reference_History_Capture_Log_operation_check"
        CHECK (trigger_operation IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'INITIAL', 'MANUAL', 'CORRECTION')),
    CONSTRAINT "Reference_History_Capture_Log_status_check" CHECK (
        (status IN ('CAPTURED', 'NO_CHANGE') AND error IS NULL) OR (status = 'FAILED' AND error IS NOT NULL))
);

CREATE TABLE public."IDX_Stock_Universe_History" (
    history_id bigint GENERATED ALWAYS AS IDENTITY,
    "Ticker" text NOT NULL,
    "Company Name" text,
    "Exchange" text,
    "Security Type" text,
    "Type Specs" text,
    "Is Common Stock" text,
    "ISIN" text,
    "Sector" text,
    "Industry" text,
    valid_from date NOT NULL,
    valid_to date,
    valid_basis text NOT NULL,
    available_at timestamp with time zone NOT NULL,
    available_basis text NOT NULL,
    recorded_from timestamp with time zone NOT NULL,
    recorded_to timestamp with time zone,
    superseded_reason text,
    pit_valid_from date GENERATED ALWAYS AS
        (greatest(valid_from, (timezone('Asia/Jakarta', recorded_from))::date + 1)) STORED,
    pit_valid_to date GENERATED ALWAYS AS
        (least(valid_to, (timezone('Asia/Jakarta', recorded_to))::date + 1)) STORED,
    capture_id bigint NOT NULL,
    source_provenance jsonb NOT NULL,
    CONSTRAINT "IDX_Stock_Universe_History_pkey" PRIMARY KEY (history_id),
    CONSTRAINT "IDX_Stock_Universe_History_capture_fkey" FOREIGN KEY (capture_id)
        REFERENCES public."Reference_History_Capture_Log" (capture_id),
    CONSTRAINT "IDX_Stock_Universe_History_key_check" CHECK (btrim("Ticker") <> ''),
    CONSTRAINT "IDX_Stock_Universe_History_valid_check" CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT "IDX_Stock_Universe_History_recorded_check" CHECK (recorded_to IS NULL OR recorded_to >= recorded_from),
    CONSTRAINT "IDX_Stock_Universe_History_available_check" CHECK (available_at <= recorded_from),
    CONSTRAINT "IDX_Stock_Universe_History_valid_basis_check" CHECK (valid_basis IN ('FIRST_CAPTURE', 'CHANGE_CAPTURED', 'DOCUMENTED')),
    CONSTRAINT "IDX_Stock_Universe_History_available_basis_check" CHECK (available_basis IN ('RECORDED', 'DOCUMENTED_PUBLICATION')),
    CONSTRAINT "IDX_Stock_Universe_History_superseded_check" CHECK (
        (recorded_to IS NULL AND superseded_reason IS NULL)
        OR (recorded_to IS NOT NULL AND superseded_reason IN ('CHANGE_CAPTURED', 'SAME_DAY_REVISION', 'CORRECTION'))),
    CONSTRAINT "IDX_Stock_Universe_History_provenance_check" CHECK (jsonb_typeof(source_provenance) = 'object'),
    -- one version per key for every (validity date, knowledge time) pair: no ambiguous overlap within the same
    -- knowledge version; empty knowledge ranges (superseded in the transaction that recorded them) overlap nothing
    CONSTRAINT "IDX_Stock_Universe_History_no_overlap" EXCLUDE USING gist (
        "Ticker" WITH =,
        daterange(valid_from, valid_to, '[)') WITH &&,
        tstzrange(recorded_from, recorded_to, '[)') WITH &&)
);

CREATE FUNCTION public.capture_stock_universe_history(p_operation text)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_now timestamp with time zone := now();
    v_day date := (timezone('Asia/Jakarta', now()))::date;
    v_capture bigint;
    v_ids bigint[];
    v_rows integer;
    v_changed integer := 0;
    v_opened integer := 0;
    v_absent integer;
    v_examples text[];
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('IDX_Stock_Universe_History'));
    INSERT INTO public."Reference_History_Capture_Log" (source_table, trigger_operation, captured_at, status)
    VALUES ('IDX_Stock_Universe', p_operation, v_now, 'NO_CHANGE')
    RETURNING capture_id INTO v_capture;
    SELECT count(*) INTO v_rows FROM public."IDX_Stock_Universe";

    -- open versions of current knowledge whose tracked attributes differ from the source row
    SELECT coalesce(array_agg(h.history_id), '{}') INTO v_ids
    FROM public."IDX_Stock_Universe" AS s
    JOIN public."IDX_Stock_Universe_History" AS h ON h."Ticker" = s."Ticker" AND h.recorded_to IS NULL AND h.valid_to IS NULL
    WHERE (h."Company Name", h."Exchange", h."Security Type", h."Type Specs", h."Is Common Stock", h."ISIN", h."Sector", h."Industry") IS DISTINCT FROM (s."Company Name", s."Exchange", s."Security Type", s."Type Specs", s."Is Common Stock", s."ISIN", s."Sector", s."Industry");

    -- 1. the superseded knowledge is kept (recorded_to), never deleted
    UPDATE public."IDX_Stock_Universe_History" AS h
    SET recorded_to = v_now,
        superseded_reason = CASE WHEN h.valid_from >= v_day THEN 'SAME_DAY_REVISION' ELSE 'CHANGE_CAPTURED' END
    WHERE h.history_id = ANY (v_ids);
    GET DIAGNOSTICS v_changed = ROW_COUNT;

    -- 2. current knowledge: the old version, now closed at the date the change was recorded
    INSERT INTO public."IDX_Stock_Universe_History" ("Ticker", "Company Name", "Exchange", "Security Type", "Type Specs", "Is Common Stock", "ISIN", "Sector", "Industry", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT h."Ticker", h."Company Name", h."Exchange", h."Security Type", h."Type Specs", h."Is Common Stock", h."ISIN", h."Sector", h."Industry", h.valid_from, v_day, h.valid_basis, v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('source_table', 'IDX_Stock_Universe', 'operation', p_operation, 'capture_id', v_capture,
                              'closes_history_id', h.history_id)
    FROM public."IDX_Stock_Universe_History" AS h
    WHERE h.history_id = ANY (v_ids) AND h.valid_from < v_day;

    -- 3. the new version, valid from the date the change was recorded (the true change date is on or before it)
    INSERT INTO public."IDX_Stock_Universe_History" ("Ticker", "Company Name", "Exchange", "Security Type", "Type Specs", "Is Common Stock", "ISIN", "Sector", "Industry", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT s."Ticker", s."Company Name", s."Exchange", s."Security Type", s."Type Specs", s."Is Common Stock", s."ISIN", s."Sector", s."Industry",
           CASE WHEN h.valid_from >= v_day THEN h.valid_from ELSE v_day END, NULL,
           CASE WHEN h.valid_from >= v_day THEN h.valid_basis ELSE 'CHANGE_CAPTURED' END,
           v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('source_table', 'IDX_Stock_Universe', 'operation', p_operation, 'capture_id', v_capture,
                              'replaces_history_id', h.history_id)
    FROM public."IDX_Stock_Universe_History" AS h
    JOIN public."IDX_Stock_Universe" AS s ON s."Ticker" = h."Ticker"
    WHERE h.history_id = ANY (v_ids);

    -- 4. keys without an open version: first capture (the true start is earlier and unknown) or a reappearance
    INSERT INTO public."IDX_Stock_Universe_History" ("Ticker", "Company Name", "Exchange", "Security Type", "Type Specs", "Is Common Stock", "ISIN", "Sector", "Industry", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT s."Ticker", s."Company Name", s."Exchange", s."Security Type", s."Type Specs", s."Is Common Stock", s."ISIN", s."Sector", s."Industry", v_day, NULL,
           CASE WHEN EXISTS (SELECT 1 FROM public."IDX_Stock_Universe_History" AS e WHERE e."Ticker" = s."Ticker")
                THEN 'CHANGE_CAPTURED' ELSE 'FIRST_CAPTURE' END,
           v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('source_table', 'IDX_Stock_Universe', 'operation', p_operation, 'capture_id', v_capture)
    FROM public."IDX_Stock_Universe" AS s
    WHERE NOT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe_History" AS h
                      WHERE h."Ticker" = s."Ticker" AND h.recorded_to IS NULL AND h.valid_to IS NULL);
    GET DIAGNOSTICS v_opened = ROW_COUNT;

    -- 5. a key missing from the source is only counted: absence in one load is not a delisting
    SELECT count(*), (array_agg(h."Ticker" ORDER BY h."Ticker"))[1:20] INTO v_absent, v_examples
    FROM public."IDX_Stock_Universe_History" AS h
    WHERE h.recorded_to IS NULL AND h.valid_to IS NULL
      AND NOT EXISTS (SELECT 1 FROM public."IDX_Stock_Universe" AS s WHERE s."Ticker" = h."Ticker");

    UPDATE public."Reference_History_Capture_Log"
    SET status = CASE WHEN v_changed + v_opened > 0 THEN 'CAPTURED' ELSE 'NO_CHANGE' END,
        source_rows = v_rows, versions_changed = v_changed, versions_opened = v_opened,
        absent_entities = v_absent, absent_examples = coalesce(v_examples, '{}')
    WHERE capture_id = v_capture;
    RETURN v_capture;
END
$function$;

CREATE FUNCTION public.correct_stock_universe_history(
    p_key text, p_valid_from date, p_valid_to date, p_attributes jsonb, p_valid_basis text,
    p_available_at timestamp with time zone, p_reason text, p_source text)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_now timestamp with time zone := now();
    v_capture bigint;
    v_ids bigint[];
    v_changed integer;
    v_opened integer := 0;
    v_count integer;
    v_expected text[] := ARRAY['Company Name', 'Exchange', 'Security Type', 'Type Specs', 'Is Common Stock', 'ISIN', 'Sector', 'Industry'];
BEGIN
    IF coalesce(btrim(p_reason), '') = '' OR coalesce(btrim(p_source), '') = '' THEN
        RAISE EXCEPTION 'A correction needs a reason and a source';
    END IF;
    IF p_key IS NULL OR p_valid_from IS NULL OR (p_valid_to IS NOT NULL AND p_valid_to <= p_valid_from) THEN
        RAISE EXCEPTION 'A correction needs a key and a validity period [valid_from, valid_to)';
    END IF;
    IF p_available_at IS NOT NULL AND p_available_at > v_now THEN
        RAISE EXCEPTION 'available_at cannot be later than the correction';
    END IF;
    IF jsonb_typeof(p_attributes) IS DISTINCT FROM 'object'
       OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(p_attributes) AS key)
          IS DISTINCT FROM (SELECT array_agg(a ORDER BY a) FROM unnest(v_expected) AS a) THEN
        RAISE EXCEPTION 'p_attributes must give exactly: %', v_expected;
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('IDX_Stock_Universe_History'));
    INSERT INTO public."Reference_History_Capture_Log" (source_table, trigger_operation, captured_at, status)
    VALUES ('IDX_Stock_Universe', 'CORRECTION', v_now, 'CAPTURED')
    RETURNING capture_id INTO v_capture;

    SELECT coalesce(array_agg(h.history_id), '{}') INTO v_ids
    FROM public."IDX_Stock_Universe_History" AS h
    WHERE h."Ticker" = p_key AND h.recorded_to IS NULL
      AND daterange(h.valid_from, h.valid_to, '[)') && daterange(p_valid_from, p_valid_to, '[)');
    UPDATE public."IDX_Stock_Universe_History" SET recorded_to = v_now, superseded_reason = 'CORRECTION' WHERE history_id = ANY (v_ids);
    GET DIAGNOSTICS v_changed = ROW_COUNT;

    -- the uncorrected parts of the superseded versions stay current knowledge
    INSERT INTO public."IDX_Stock_Universe_History" ("Ticker", "Company Name", "Exchange", "Security Type", "Type Specs", "Is Common Stock", "ISIN", "Sector", "Industry", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT h."Ticker", h."Company Name", h."Exchange", h."Security Type", h."Type Specs", h."Is Common Stock", h."ISIN", h."Sector", h."Industry", h.valid_from, p_valid_from, h.valid_basis, v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('correction_remainder_of', h.history_id, 'capture_id', v_capture)
    FROM public."IDX_Stock_Universe_History" AS h
    WHERE h.history_id = ANY (v_ids) AND h.valid_from < p_valid_from;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    v_opened := v_opened + v_count;
    INSERT INTO public."IDX_Stock_Universe_History" ("Ticker", "Company Name", "Exchange", "Security Type", "Type Specs", "Is Common Stock", "ISIN", "Sector", "Industry", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT h."Ticker", h."Company Name", h."Exchange", h."Security Type", h."Type Specs", h."Is Common Stock", h."ISIN", h."Sector", h."Industry", p_valid_to, h.valid_to, h.valid_basis, v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('correction_remainder_of', h.history_id, 'capture_id', v_capture)
    FROM public."IDX_Stock_Universe_History" AS h
    WHERE h.history_id = ANY (v_ids) AND p_valid_to IS NOT NULL AND (h.valid_to IS NULL OR h.valid_to > p_valid_to);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    v_opened := v_opened + v_count;

    INSERT INTO public."IDX_Stock_Universe_History" ("Ticker", "Company Name", "Exchange", "Security Type", "Type Specs", "Is Common Stock", "ISIN", "Sector", "Industry", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT p_key, r."Company Name", r."Exchange", r."Security Type", r."Type Specs", r."Is Common Stock", r."ISIN", r."Sector", r."Industry", p_valid_from, p_valid_to, p_valid_basis, coalesce(p_available_at, v_now),
           CASE WHEN p_available_at IS NULL THEN 'RECORDED' ELSE 'DOCUMENTED_PUBLICATION' END, v_now, v_capture,
           jsonb_build_object('correction', true, 'reason', p_reason, 'source', p_source, 'capture_id', v_capture,
                              'supersedes', to_jsonb(v_ids))
    FROM jsonb_populate_record(NULL::public."IDX_Stock_Universe_History", p_attributes) AS r;
    v_opened := v_opened + 1;

    UPDATE public."Reference_History_Capture_Log"
    SET versions_changed = v_changed, versions_opened = v_opened
    WHERE capture_id = v_capture;
    RETURN v_capture;
END
$function$;

CREATE FUNCTION public.stock_universe_history_as_known(p_known_at timestamp with time zone, p_valid_on date)
RETURNS SETOF public."IDX_Stock_Universe_History"
LANGUAGE sql
STABLE
AS $function$
    SELECT * FROM public."IDX_Stock_Universe_History"
    WHERE recorded_from <= p_known_at AND (recorded_to IS NULL OR p_known_at < recorded_to)
      AND valid_from <= p_valid_on AND (valid_to IS NULL OR p_valid_on < valid_to)
$function$;

CREATE TABLE public."IDX_Broker_Profile_History" (
    history_id bigint GENERATED ALWAYS AS IDENTITY,
    "broker_code" text NOT NULL,
    "broker_name" text,
    "broker_type" text,
    "broker_classification" text,
    valid_from date NOT NULL,
    valid_to date,
    valid_basis text NOT NULL,
    available_at timestamp with time zone NOT NULL,
    available_basis text NOT NULL,
    recorded_from timestamp with time zone NOT NULL,
    recorded_to timestamp with time zone,
    superseded_reason text,
    pit_valid_from date GENERATED ALWAYS AS
        (greatest(valid_from, (timezone('Asia/Jakarta', recorded_from))::date + 1)) STORED,
    pit_valid_to date GENERATED ALWAYS AS
        (least(valid_to, (timezone('Asia/Jakarta', recorded_to))::date + 1)) STORED,
    capture_id bigint NOT NULL,
    source_provenance jsonb NOT NULL,
    CONSTRAINT "IDX_Broker_Profile_History_pkey" PRIMARY KEY (history_id),
    CONSTRAINT "IDX_Broker_Profile_History_capture_fkey" FOREIGN KEY (capture_id)
        REFERENCES public."Reference_History_Capture_Log" (capture_id),
    CONSTRAINT "IDX_Broker_Profile_History_key_check" CHECK (btrim("broker_code") <> ''),
    CONSTRAINT "IDX_Broker_Profile_History_valid_check" CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT "IDX_Broker_Profile_History_recorded_check" CHECK (recorded_to IS NULL OR recorded_to >= recorded_from),
    CONSTRAINT "IDX_Broker_Profile_History_available_check" CHECK (available_at <= recorded_from),
    CONSTRAINT "IDX_Broker_Profile_History_valid_basis_check" CHECK (valid_basis IN ('FIRST_CAPTURE', 'CHANGE_CAPTURED', 'DOCUMENTED')),
    CONSTRAINT "IDX_Broker_Profile_History_available_basis_check" CHECK (available_basis IN ('RECORDED', 'DOCUMENTED_PUBLICATION')),
    CONSTRAINT "IDX_Broker_Profile_History_superseded_check" CHECK (
        (recorded_to IS NULL AND superseded_reason IS NULL)
        OR (recorded_to IS NOT NULL AND superseded_reason IN ('CHANGE_CAPTURED', 'SAME_DAY_REVISION', 'CORRECTION'))),
    CONSTRAINT "IDX_Broker_Profile_History_provenance_check" CHECK (jsonb_typeof(source_provenance) = 'object'),
    -- one version per key for every (validity date, knowledge time) pair: no ambiguous overlap within the same
    -- knowledge version; empty knowledge ranges (superseded in the transaction that recorded them) overlap nothing
    CONSTRAINT "IDX_Broker_Profile_History_no_overlap" EXCLUDE USING gist (
        "broker_code" WITH =,
        daterange(valid_from, valid_to, '[)') WITH &&,
        tstzrange(recorded_from, recorded_to, '[)') WITH &&)
);

CREATE FUNCTION public.capture_broker_profile_history(p_operation text)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_now timestamp with time zone := now();
    v_day date := (timezone('Asia/Jakarta', now()))::date;
    v_capture bigint;
    v_ids bigint[];
    v_rows integer;
    v_changed integer := 0;
    v_opened integer := 0;
    v_absent integer;
    v_examples text[];
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('IDX_Broker_Profile_History'));
    INSERT INTO public."Reference_History_Capture_Log" (source_table, trigger_operation, captured_at, status)
    VALUES ('IDX_Broker_Profile', p_operation, v_now, 'NO_CHANGE')
    RETURNING capture_id INTO v_capture;
    SELECT count(*) INTO v_rows FROM public."IDX_Broker_Profile";

    -- open versions of current knowledge whose tracked attributes differ from the source row
    SELECT coalesce(array_agg(h.history_id), '{}') INTO v_ids
    FROM public."IDX_Broker_Profile" AS s
    JOIN public."IDX_Broker_Profile_History" AS h ON h."broker_code" = s."broker_code" AND h.recorded_to IS NULL AND h.valid_to IS NULL
    WHERE (h."broker_name", h."broker_type", h."broker_classification") IS DISTINCT FROM (s."broker_name", s."broker_type", s."broker_classification");

    -- 1. the superseded knowledge is kept (recorded_to), never deleted
    UPDATE public."IDX_Broker_Profile_History" AS h
    SET recorded_to = v_now,
        superseded_reason = CASE WHEN h.valid_from >= v_day THEN 'SAME_DAY_REVISION' ELSE 'CHANGE_CAPTURED' END
    WHERE h.history_id = ANY (v_ids);
    GET DIAGNOSTICS v_changed = ROW_COUNT;

    -- 2. current knowledge: the old version, now closed at the date the change was recorded
    INSERT INTO public."IDX_Broker_Profile_History" ("broker_code", "broker_name", "broker_type", "broker_classification", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT h."broker_code", h."broker_name", h."broker_type", h."broker_classification", h.valid_from, v_day, h.valid_basis, v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('source_table', 'IDX_Broker_Profile', 'operation', p_operation, 'capture_id', v_capture,
                              'closes_history_id', h.history_id)
    FROM public."IDX_Broker_Profile_History" AS h
    WHERE h.history_id = ANY (v_ids) AND h.valid_from < v_day;

    -- 3. the new version, valid from the date the change was recorded (the true change date is on or before it)
    INSERT INTO public."IDX_Broker_Profile_History" ("broker_code", "broker_name", "broker_type", "broker_classification", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT s."broker_code", s."broker_name", s."broker_type", s."broker_classification",
           CASE WHEN h.valid_from >= v_day THEN h.valid_from ELSE v_day END, NULL,
           CASE WHEN h.valid_from >= v_day THEN h.valid_basis ELSE 'CHANGE_CAPTURED' END,
           v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('source_table', 'IDX_Broker_Profile', 'operation', p_operation, 'capture_id', v_capture,
                              'replaces_history_id', h.history_id)
    FROM public."IDX_Broker_Profile_History" AS h
    JOIN public."IDX_Broker_Profile" AS s ON s."broker_code" = h."broker_code"
    WHERE h.history_id = ANY (v_ids);

    -- 4. keys without an open version: first capture (the true start is earlier and unknown) or a reappearance
    INSERT INTO public."IDX_Broker_Profile_History" ("broker_code", "broker_name", "broker_type", "broker_classification", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT s."broker_code", s."broker_name", s."broker_type", s."broker_classification", v_day, NULL,
           CASE WHEN EXISTS (SELECT 1 FROM public."IDX_Broker_Profile_History" AS e WHERE e."broker_code" = s."broker_code")
                THEN 'CHANGE_CAPTURED' ELSE 'FIRST_CAPTURE' END,
           v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('source_table', 'IDX_Broker_Profile', 'operation', p_operation, 'capture_id', v_capture)
    FROM public."IDX_Broker_Profile" AS s
    WHERE NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Profile_History" AS h
                      WHERE h."broker_code" = s."broker_code" AND h.recorded_to IS NULL AND h.valid_to IS NULL);
    GET DIAGNOSTICS v_opened = ROW_COUNT;

    -- 5. a key missing from the source is only counted: absence in one load is not a delisting
    SELECT count(*), (array_agg(h."broker_code" ORDER BY h."broker_code"))[1:20] INTO v_absent, v_examples
    FROM public."IDX_Broker_Profile_History" AS h
    WHERE h.recorded_to IS NULL AND h.valid_to IS NULL
      AND NOT EXISTS (SELECT 1 FROM public."IDX_Broker_Profile" AS s WHERE s."broker_code" = h."broker_code");

    UPDATE public."Reference_History_Capture_Log"
    SET status = CASE WHEN v_changed + v_opened > 0 THEN 'CAPTURED' ELSE 'NO_CHANGE' END,
        source_rows = v_rows, versions_changed = v_changed, versions_opened = v_opened,
        absent_entities = v_absent, absent_examples = coalesce(v_examples, '{}')
    WHERE capture_id = v_capture;
    RETURN v_capture;
END
$function$;

CREATE FUNCTION public.correct_broker_profile_history(
    p_key text, p_valid_from date, p_valid_to date, p_attributes jsonb, p_valid_basis text,
    p_available_at timestamp with time zone, p_reason text, p_source text)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_now timestamp with time zone := now();
    v_capture bigint;
    v_ids bigint[];
    v_changed integer;
    v_opened integer := 0;
    v_count integer;
    v_expected text[] := ARRAY['broker_name', 'broker_type', 'broker_classification'];
BEGIN
    IF coalesce(btrim(p_reason), '') = '' OR coalesce(btrim(p_source), '') = '' THEN
        RAISE EXCEPTION 'A correction needs a reason and a source';
    END IF;
    IF p_key IS NULL OR p_valid_from IS NULL OR (p_valid_to IS NOT NULL AND p_valid_to <= p_valid_from) THEN
        RAISE EXCEPTION 'A correction needs a key and a validity period [valid_from, valid_to)';
    END IF;
    IF p_available_at IS NOT NULL AND p_available_at > v_now THEN
        RAISE EXCEPTION 'available_at cannot be later than the correction';
    END IF;
    IF jsonb_typeof(p_attributes) IS DISTINCT FROM 'object'
       OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(p_attributes) AS key)
          IS DISTINCT FROM (SELECT array_agg(a ORDER BY a) FROM unnest(v_expected) AS a) THEN
        RAISE EXCEPTION 'p_attributes must give exactly: %', v_expected;
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('IDX_Broker_Profile_History'));
    INSERT INTO public."Reference_History_Capture_Log" (source_table, trigger_operation, captured_at, status)
    VALUES ('IDX_Broker_Profile', 'CORRECTION', v_now, 'CAPTURED')
    RETURNING capture_id INTO v_capture;

    SELECT coalesce(array_agg(h.history_id), '{}') INTO v_ids
    FROM public."IDX_Broker_Profile_History" AS h
    WHERE h."broker_code" = p_key AND h.recorded_to IS NULL
      AND daterange(h.valid_from, h.valid_to, '[)') && daterange(p_valid_from, p_valid_to, '[)');
    UPDATE public."IDX_Broker_Profile_History" SET recorded_to = v_now, superseded_reason = 'CORRECTION' WHERE history_id = ANY (v_ids);
    GET DIAGNOSTICS v_changed = ROW_COUNT;

    -- the uncorrected parts of the superseded versions stay current knowledge
    INSERT INTO public."IDX_Broker_Profile_History" ("broker_code", "broker_name", "broker_type", "broker_classification", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT h."broker_code", h."broker_name", h."broker_type", h."broker_classification", h.valid_from, p_valid_from, h.valid_basis, v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('correction_remainder_of', h.history_id, 'capture_id', v_capture)
    FROM public."IDX_Broker_Profile_History" AS h
    WHERE h.history_id = ANY (v_ids) AND h.valid_from < p_valid_from;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    v_opened := v_opened + v_count;
    INSERT INTO public."IDX_Broker_Profile_History" ("broker_code", "broker_name", "broker_type", "broker_classification", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT h."broker_code", h."broker_name", h."broker_type", h."broker_classification", p_valid_to, h.valid_to, h.valid_basis, v_now, 'RECORDED', v_now, v_capture,
           jsonb_build_object('correction_remainder_of', h.history_id, 'capture_id', v_capture)
    FROM public."IDX_Broker_Profile_History" AS h
    WHERE h.history_id = ANY (v_ids) AND p_valid_to IS NOT NULL AND (h.valid_to IS NULL OR h.valid_to > p_valid_to);
    GET DIAGNOSTICS v_count = ROW_COUNT;
    v_opened := v_opened + v_count;

    INSERT INTO public."IDX_Broker_Profile_History" ("broker_code", "broker_name", "broker_type", "broker_classification", valid_from, valid_to, valid_basis, available_at, available_basis,
                            recorded_from, capture_id, source_provenance)
    SELECT p_key, r."broker_name", r."broker_type", r."broker_classification", p_valid_from, p_valid_to, p_valid_basis, coalesce(p_available_at, v_now),
           CASE WHEN p_available_at IS NULL THEN 'RECORDED' ELSE 'DOCUMENTED_PUBLICATION' END, v_now, v_capture,
           jsonb_build_object('correction', true, 'reason', p_reason, 'source', p_source, 'capture_id', v_capture,
                              'supersedes', to_jsonb(v_ids))
    FROM jsonb_populate_record(NULL::public."IDX_Broker_Profile_History", p_attributes) AS r;
    v_opened := v_opened + 1;

    UPDATE public."Reference_History_Capture_Log"
    SET versions_changed = v_changed, versions_opened = v_opened
    WHERE capture_id = v_capture;
    RETURN v_capture;
END
$function$;

CREATE FUNCTION public.broker_profile_history_as_known(p_known_at timestamp with time zone, p_valid_on date)
RETURNS SETOF public."IDX_Broker_Profile_History"
LANGUAGE sql
STABLE
AS $function$
    SELECT * FROM public."IDX_Broker_Profile_History"
    WHERE recorded_from <= p_known_at AND (recorded_to IS NULL OR p_known_at < recorded_to)
      AND valid_from <= p_valid_on AND (valid_to IS NULL OR p_valid_on < valid_to)
$function$;

CREATE FUNCTION public.capture_reference_history()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
BEGIN
    BEGIN
        IF TG_TABLE_NAME = 'IDX_Stock_Universe' THEN
            PERFORM public.capture_stock_universe_history(TG_OP);
        ELSIF TG_TABLE_NAME = 'IDX_Broker_Profile' THEN
            PERFORM public.capture_broker_profile_history(TG_OP);
        END IF;
    EXCEPTION WHEN OTHERS THEN
        -- never fail the reference load: the failure is logged, and the next capture compares the whole source
        -- with history again, so a missed change is recorded later (conservatively), never lost
        INSERT INTO public."Reference_History_Capture_Log" (source_table, trigger_operation, status, error)
        VALUES (TG_TABLE_NAME, TG_OP, 'FAILED', left(SQLSTATE || ' ' || SQLERRM, 1000));
    END;
    RETURN NULL;
END
$function$;

CREATE TRIGGER reference_history_capture
AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON public."IDX_Stock_Universe"
FOR EACH STATEMENT EXECUTE FUNCTION public.capture_reference_history();
CREATE TRIGGER reference_history_capture
AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON public."IDX_Broker_Profile"
FOR EACH STATEMENT EXECUTE FUNCTION public.capture_reference_history();

REVOKE ALL ON FUNCTION public.capture_reference_history() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.capture_stock_universe_history(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.capture_broker_profile_history(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.correct_stock_universe_history(text, date, date, jsonb, text, timestamp with time zone, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.correct_broker_profile_history(text, date, date, jsonb, text, timestamp with time zone, text, text) FROM PUBLIC;
-- END reference history core

-- the first snapshot: valid from the capture date only (FIRST_CAPTURE), never backdated
SELECT public.capture_stock_universe_history('INITIAL');
SELECT public.capture_broker_profile_history('INITIAL');

REVOKE ALL ON public."IDX_Stock_Universe_History", public."IDX_Broker_Profile_History",
              public."Reference_History_Capture_Log" FROM PUBLIC;
GRANT SELECT ON public."IDX_Stock_Universe_History", public."IDX_Broker_Profile_History"
    TO market_ai_sql_reader, pgweb_reader;
GRANT SELECT ON public."Reference_History_Capture_Log" TO pgweb_reader;
-- the availability metadata a point-in-time spec is checked against (Governor contract, orc discovery); the other
-- Table_Catalog columns stay unreadable to these roles
GRANT SELECT (table_schema, table_name, observation_date_column, data_available_at_column, availability_rule,
              point_in_time_status, historical_metadata_method)
    ON public."Table_Catalog" TO market_ai_sql_reader, market_ai_catalog_reader;

COMMENT ON TABLE public."IDX_Stock_Universe_History" IS
    'Point-in-time history of the tracked IDX_Stock_Universe attributes, captured from the first capture onward: one row per ticker version and knowledge version (bitemporal); superseded knowledge is kept.';
COMMENT ON TABLE public."IDX_Broker_Profile_History" IS
    'Point-in-time history of IDX_Broker_Profile (name, broker_type, broker_classification), captured from the first capture onward: one row per broker version and knowledge version (bitemporal); superseded knowledge is kept.';
COMMENT ON TABLE public."Reference_History_Capture_Log" IS
    'One row per capture of a reference table into its history (trigger, initial, manual or correction): counts of changed and new versions, keys absent from the load, and the error of a failed capture.';

-- value_time_basis: whether a column holds the value of its row's date (HISTORICAL) or today's reference value on
-- every row (CURRENT_STATE). A point-in-time spec may not read or filter a CURRENT_STATE column.
ALTER TABLE public."AI_column_catalog" ADD COLUMN value_time_basis text;
UPDATE public."AI_column_catalog" SET value_time_basis = CASE
    WHEN table_name IN ('IDX_Stock_Universe', 'IDX_Broker_Profile') THEN 'CURRENT_STATE'
    WHEN EXISTS (SELECT 1 FROM public."Feature_Catalog" AS f
                 WHERE f.is_active AND f.feature_table = "AI_column_catalog".table_name
                   AND f.feature_column = "AI_column_catalog".column_name
                   AND NOT f.point_in_time_safe AND f.historical_metadata_warning ILIKE '%current%')
        THEN 'CURRENT_STATE'
    ELSE 'HISTORICAL' END;
ALTER TABLE public."AI_column_catalog"
    ALTER COLUMN value_time_basis SET NOT NULL,
    ADD CONSTRAINT "AI_column_catalog_value_time_basis_check"
        CHECK (value_time_basis IN ('HISTORICAL', 'CURRENT_STATE'));
COMMENT ON COLUMN public."AI_column_catalog".value_time_basis IS
    'HISTORICAL: the value belongs to its row''s date (or version). CURRENT_STATE: today''s reference value repeated on every row (current classification); a point-in-time DataNeedSpec may not read or filter it.';

INSERT INTO public."AI_table_catalog" (
    table_name, description, category, grain, primary_key_columns, time_column, entity_column, owner, is_active,
    ai_access_level, freshness_sla, coverage_enabled, documentation_status, data_domain, entity_type, asset_type,
    supported_frequencies, time_semantics, subject_metadata_status)
VALUES
    ('IDX_Stock_Universe_History',
     'Point-in-time history of the stock universe classification (Sector, Industry, security type, company name) recorded by Saniti from its first capture onward. Join it to dated tables through its EFFECTIVE_DATED relationships (pit_valid_from / pit_valid_to): each observation date gets the version Saniti had already recorded, so a sector filter uses the sector of that date. It holds nothing before the first capture: earlier dates need the current-state IDX_Stock_Universe (historical descriptive, with disclosure).',
     'REFERENCE', 'One row per ticker, validity period and knowledge version (bitemporal)', ARRAY['history_id'], NULL,
     'Ticker', 'Saniti', true, 'BOUNDED_READ', NULL, false, 'PARTIAL', 'MARKET', 'STOCK', 'IDX_EQUITY',
     ARRAY['STATIC'],
     'Effective-dated reference history: valid_from/valid_to effective period, recorded_from/recorded_to knowledge period; pit_valid_from/pit_valid_to is the point-in-time validity joins use',
     'INFERRED'),
    ('IDX_Broker_Profile_History',
     'Point-in-time history of the broker profile (name, domicile broker_type, usage broker_classification) recorded by Saniti from its first capture onward. Join it to broker activity through its EFFECTIVE_DATED relationships (pit_valid_from / pit_valid_to): each observation date gets the classification Saniti had already recorded. It holds nothing before the first capture.',
     'REFERENCE', 'One row per broker code, validity period and knowledge version (bitemporal)', ARRAY['history_id'], NULL,
     'broker_code', 'Saniti', true, 'BOUNDED_READ', NULL, false, 'PARTIAL', 'MARKET', 'BROKER', NULL,
     ARRAY['STATIC'],
     'Effective-dated reference history: valid_from/valid_to effective period, recorded_from/recorded_to knowledge period; pit_valid_from/pit_valid_to is the point-in-time validity joins use',
     'INFERRED');

INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis)
SELECT 'IDX_Stock_Universe_History', c.column_name, c.ordinal_position,
       coalesce(meta.description, src.description || ' Value of this version.'),
       c.data_type, coalesce(meta.semantic_type, src.semantic_type),
       NULL, c.is_nullable = 'YES', c.column_name = 'history_id',
       CASE WHEN src.column_name IS NOT NULL THEN 'IDX_Stock_Universe."' || c.column_name || '" at capture'
            WHEN c.is_generated = 'ALWAYS' THEN c.generation_expression END,
       false, true,
       CASE WHEN coalesce(meta.semantic_type, src.semantic_type) = 'TIME' THEN ARRAY['MIN', 'MAX']
            ELSE ARRAY['COUNT', 'COUNT_DISTINCT'] END,
       true, true, src.example_value, false, 'PARTIAL', NULL, NULL, 'HISTORICAL'
FROM information_schema.columns AS c
LEFT JOIN public."AI_column_catalog" AS src
       ON src.table_name = 'IDX_Stock_Universe' AND src.column_name = c.column_name AND c.column_name = ANY(ARRAY['Ticker', 'Company Name', 'Exchange', 'Security Type', 'Type Specs', 'Is Common Stock', 'ISIN', 'Sector', 'Industry']::text[])
CROSS JOIN LATERAL (SELECT CASE c.column_name
        WHEN 'history_id' THEN 'IDENTIFIER'
        WHEN 'Ticker' THEN 'IDENTIFIER'
        WHEN 'broker_code' THEN 'IDENTIFIER'
        WHEN 'valid_from' THEN 'TIME'
        WHEN 'valid_to' THEN 'TIME'
        WHEN 'valid_basis' THEN 'DIMENSION'
        WHEN 'available_at' THEN 'TIME'
        WHEN 'available_basis' THEN 'DIMENSION'
        WHEN 'recorded_from' THEN 'TIME'
        WHEN 'recorded_to' THEN 'TIME'
        WHEN 'superseded_reason' THEN 'DIMENSION'
        WHEN 'pit_valid_from' THEN 'TIME'
        WHEN 'pit_valid_to' THEN 'TIME'
    END AS semantic_type, CASE c.column_name
        WHEN 'history_id' THEN 'Row id of one version (identity only).'
        WHEN 'Ticker' THEN 'IDX ticker: the entity key (several rows per ticker, one per version; history_id identifies a row).'
        WHEN 'broker_code' THEN 'Two-character IDX broker code: the entity key (several rows per broker, one per version; history_id identifies a row).'
        WHEN 'valid_from' THEN 'Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis).'
        WHEN 'valid_to' THEN 'Effective end of this version (exclusive); NULL = still in effect in this knowledge version.'
        WHEN 'valid_basis' THEN 'FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction).'
        WHEN 'available_at' THEN 'When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound.'
        WHEN 'available_basis' THEN 'RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from.'
        WHEN 'recorded_from' THEN 'When Saniti recorded this row (start of the knowledge period).'
        WHEN 'recorded_to' THEN 'When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept.'
        WHEN 'superseded_reason' THEN 'Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge.'
        WHEN 'pit_valid_from' THEN 'First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to.'
        WHEN 'pit_valid_to' THEN 'Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date.'
    END AS description) AS meta
WHERE c.table_schema = 'public' AND c.table_name = 'IDX_Stock_Universe_History'
  AND c.column_name NOT IN ('capture_id', 'source_provenance');

INSERT INTO public."AI_column_catalog" (
    table_name, column_name, ordinal_position, description, data_type, semantic_type, unit, nullable, is_primary_key,
    source_column_or_expression, is_sensitive, ai_allowed, allowed_aggregations, filter_allowed, group_by_allowed,
    example_value, coverage_required, documentation_status, resample_aggregation, cross_entity_aggregation,
    value_time_basis)
SELECT 'IDX_Broker_Profile_History', c.column_name, c.ordinal_position,
       coalesce(meta.description, src.description || ' Value of this version.'),
       c.data_type, coalesce(meta.semantic_type, src.semantic_type),
       NULL, c.is_nullable = 'YES', c.column_name = 'history_id',
       CASE WHEN src.column_name IS NOT NULL THEN 'IDX_Broker_Profile."' || c.column_name || '" at capture'
            WHEN c.is_generated = 'ALWAYS' THEN c.generation_expression END,
       false, true,
       CASE WHEN coalesce(meta.semantic_type, src.semantic_type) = 'TIME' THEN ARRAY['MIN', 'MAX']
            ELSE ARRAY['COUNT', 'COUNT_DISTINCT'] END,
       true, true, src.example_value, false, 'PARTIAL', NULL, NULL, 'HISTORICAL'
FROM information_schema.columns AS c
LEFT JOIN public."AI_column_catalog" AS src
       ON src.table_name = 'IDX_Broker_Profile' AND src.column_name = c.column_name AND c.column_name = ANY(ARRAY['broker_code', 'broker_name', 'broker_type', 'broker_classification']::text[])
CROSS JOIN LATERAL (SELECT CASE c.column_name
        WHEN 'history_id' THEN 'IDENTIFIER'
        WHEN 'Ticker' THEN 'IDENTIFIER'
        WHEN 'broker_code' THEN 'IDENTIFIER'
        WHEN 'valid_from' THEN 'TIME'
        WHEN 'valid_to' THEN 'TIME'
        WHEN 'valid_basis' THEN 'DIMENSION'
        WHEN 'available_at' THEN 'TIME'
        WHEN 'available_basis' THEN 'DIMENSION'
        WHEN 'recorded_from' THEN 'TIME'
        WHEN 'recorded_to' THEN 'TIME'
        WHEN 'superseded_reason' THEN 'DIMENSION'
        WHEN 'pit_valid_from' THEN 'TIME'
        WHEN 'pit_valid_to' THEN 'TIME'
    END AS semantic_type, CASE c.column_name
        WHEN 'history_id' THEN 'Row id of one version (identity only).'
        WHEN 'Ticker' THEN 'IDX ticker: the entity key (several rows per ticker, one per version; history_id identifies a row).'
        WHEN 'broker_code' THEN 'Two-character IDX broker code: the entity key (several rows per broker, one per version; history_id identifies a row).'
        WHEN 'valid_from' THEN 'Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis).'
        WHEN 'valid_to' THEN 'Effective end of this version (exclusive); NULL = still in effect in this knowledge version.'
        WHEN 'valid_basis' THEN 'FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction).'
        WHEN 'available_at' THEN 'When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound.'
        WHEN 'available_basis' THEN 'RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from.'
        WHEN 'recorded_from' THEN 'When Saniti recorded this row (start of the knowledge period).'
        WHEN 'recorded_to' THEN 'When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept.'
        WHEN 'superseded_reason' THEN 'Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge.'
        WHEN 'pit_valid_from' THEN 'First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to.'
        WHEN 'pit_valid_to' THEN 'Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date.'
    END AS description) AS meta
WHERE c.table_schema = 'public' AND c.table_name = 'IDX_Broker_Profile_History'
  AND c.column_name NOT IN ('capture_id', 'source_provenance');

INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns, relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed, supported_join_semantics, left_time_column,
    right_time_column, effective_from_column, effective_to_column)
VALUES
    ('Price_Stock_Indonesia_IDX', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'date x ticker',
     false, 'Daily prices joined to the stock classification Saniti had recorded before each date (point in time): a sector or industry scope on the history restricts prices to the tickers of that sector on that date. Dates before the first capture have no version.', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('Feature_01_Stock_Daily', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'date x ticker',
     false, 'Daily stock features joined to the stock classification recorded before each date (point in time). Use this instead of Feature 01 sector/industry (current state) for point-in-time work.', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('Feature_02_Broker_Rolling', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'date x ticker x broker x investor_type x market_board',
     false, 'Broker rolling flows joined to the stock classification recorded before each date (point in time); boards and investor types stay separate rows.', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('Feature_03_Stock_Broker_Daily', ARRAY['ticker'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'date x ticker x market_board',
     false, 'Stock-level daily broker features joined to the stock classification recorded before each date (point in time); boards stay separate rows. Feature 03 classified net values (institutional, retail, mixed, niche) remain current-state.', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('IDX_Broker_Summary', ARRAY['Symbol'], 'IDX_Stock_Universe_History', ARRAY['Ticker'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'Broker Summary primary-key grain (Date x Symbol x Broker x Investor Type x Market Board)',
     false, 'Broker activity joined to the stock classification recorded before each date (point in time). Symbols never in the universe (rights, warrants) have no version.', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('Feature_02_Broker_Rolling', ARRAY['broker'], 'IDX_Broker_Profile_History', ARRAY['broker_code'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'date x ticker x broker x investor_type x market_board',
     false, 'Broker rolling flows joined to the broker profile (broker_type domicile, broker_classification) recorded before each date (point in time). Use this instead of Feature 02 broker_classification (current state) for point-in-time work.', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to'),
    ('IDX_Broker_Summary', ARRAY['Broker'], 'IDX_Broker_Profile_History', ARRAY['broker_code'], 'MANY_TO_ONE',
     'Point in time: the version in effect and already recorded on the observation date', 'Broker Summary primary-key grain (Date x Symbol x Broker x Investor Type x Market Board)',
     false, 'Broker activity joined to the broker profile recorded before each date (point in time).', 'v1', true, ARRAY['EFFECTIVE_DATED'], NULL, NULL, 'pit_valid_from', 'pit_valid_to');

INSERT INTO public."Table_Catalog" (
    table_schema, table_name, category, definition, grain, primary_key_columns, source_system, source_tables,
    source_code_paths, update_rule, related_functions, documentation_status, readiness_mode, readiness_date_column,
    observation_date_column, data_available_at_column, availability_rule, point_in_time_status,
    historical_metadata_method)
VALUES
    ('public', 'IDX_Stock_Universe_History', 'Reference',
     'Point-in-time (bitemporal) history of the tracked IDX_Stock_Universe attributes (Company Name, Exchange, Security Type, Type Specs, Is Common Stock, ISIN, Sector, Industry), captured by Saniti from the first capture onward. Current knowledge is recorded_to IS NULL; superseded knowledge is kept.',
     'One row per Ticker, validity period [valid_from, valid_to) and knowledge period [recorded_from, recorded_to)',
     ARRAY['history_id'], 'Saniti capture of IDX_Stock_Universe (statement trigger reference_history_capture) and corrections',
     ARRAY['IDX_Stock_Universe', 'Reference_History_Capture_Log']::text[], ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql'],
     'Appended by the capture after every write statement on IDX_Stock_Universe (a change supersedes the open version and records the new one; a missing key is only counted) and by public.correct_stock_universe_history for documented corrections. Rows are never deleted.',
     ARRAY['public.capture_reference_history()', 'public.capture_stock_universe_history(text)', 'public.correct_stock_universe_history(text, date, date, jsonb, text, timestamp with time zone, text, text)', 'public.stock_universe_history_as_known(timestamp with time zone, date)']::text[], 'PARTIAL', 'NOT_APPLICABLE', NULL, 'valid_from', 'available_at',
     'Point-in-time use selects the row with pit_valid_from <= observation date < pit_valid_to: a version is used from the Asia/Jakarta date after Saniti recorded it (recorded time is the conservative bound of availability; a documented earlier publication time is kept in available_at but not used for selection). Nothing is known before the first capture.', 'PARTIAL',
     'PROSPECTIVE_CAPTURE from the first capture of IDX_Stock_Universe; no history before it. Absence from one load is not a delisting. Corrections keep the superseded knowledge (recorded_to).'),
    ('public', 'IDX_Broker_Profile_History', 'Reference',
     'Point-in-time (bitemporal) history of the tracked IDX_Broker_Profile attributes (broker_name, broker_type, broker_classification), captured by Saniti from the first capture onward. Current knowledge is recorded_to IS NULL; superseded knowledge is kept.',
     'One row per broker_code, validity period [valid_from, valid_to) and knowledge period [recorded_from, recorded_to)',
     ARRAY['history_id'], 'Saniti capture of IDX_Broker_Profile (statement trigger reference_history_capture) and corrections',
     ARRAY['IDX_Broker_Profile', 'Reference_History_Capture_Log']::text[], ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql'],
     'Appended by the capture after every write statement on IDX_Broker_Profile (a change supersedes the open version and records the new one; a missing key is only counted) and by public.correct_broker_profile_history for documented corrections. Rows are never deleted.',
     ARRAY['public.capture_reference_history()', 'public.capture_broker_profile_history(text)', 'public.correct_broker_profile_history(text, date, date, jsonb, text, timestamp with time zone, text, text)', 'public.broker_profile_history_as_known(timestamp with time zone, date)']::text[], 'PARTIAL', 'NOT_APPLICABLE', NULL, 'valid_from', 'available_at',
     'Point-in-time use selects the row with pit_valid_from <= observation date < pit_valid_to: a version is used from the Asia/Jakarta date after Saniti recorded it (recorded time is the conservative bound of availability; a documented earlier publication time is kept in available_at but not used for selection). Nothing is known before the first capture.', 'PARTIAL',
     'PROSPECTIVE_CAPTURE from the first capture of IDX_Broker_Profile; no history before it. Absence from one load is not a delisting. Corrections keep the superseded knowledge (recorded_to).'),
    ('public', 'Reference_History_Capture_Log', 'System',
     'One row per capture of IDX_Stock_Universe or IDX_Broker_Profile into its history (trigger, initial, manual or correction): changed and new versions, keys absent from the load, and the error of a failed capture.',
     'One row per capture_id', ARRAY['capture_id'], 'Reference history capture functions',
     ARRAY['IDX_Stock_Universe', 'IDX_Broker_Profile']::text[], ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql'],
     'Inserted by every capture and correction; a failed trigger capture writes status FAILED with its error and leaves the reference load unaffected.',
     ARRAY['public.capture_reference_history()', 'public.capture_stock_universe_history(text)', 'public.capture_broker_profile_history(text)', 'public.correct_stock_universe_history(text, date, date, jsonb, text, timestamp with time zone, text, text)', 'public.correct_broker_profile_history(text, date, date, jsonb, text, timestamp with time zone, text, text)']::text[], 'PARTIAL', 'NOT_APPLICABLE', NULL, 'captured_at', NULL,
     'Operational capture audit, not market data.', 'NOT_APPLICABLE', NULL);

UPDATE public."Table_Catalog"
SET related_functions = related_functions || ARRAY['public.capture_reference_history()'],
    source_code_paths = source_code_paths || ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql'],
    historical_metadata_method = historical_metadata_method || CASE table_name
        WHEN 'IDX_Stock_Universe' THEN ' Point-in-time history from its first capture: IDX_Stock_Universe_History.'
        ELSE ' Point-in-time history from its first capture: IDX_Broker_Profile_History.' END
WHERE table_schema = 'public' AND table_name IN ('IDX_Stock_Universe', 'IDX_Broker_Profile');

UPDATE public."Table_Catalog"
SET source_code_paths = source_code_paths || ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql']
WHERE table_schema = 'public' AND table_name = 'AI_column_catalog';

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, default_expression,
    is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths, documentation_status)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES',
       c.column_default, c.column_name = CASE c.table_name WHEN 'Reference_History_Capture_Log' THEN 'capture_id'
                                          ELSE 'history_id' END,
       CASE c.table_name || '.' || c.column_name
        WHEN 'IDX_Stock_Universe_History.history_id' THEN 'Row id of one version (identity only).'
        WHEN 'IDX_Stock_Universe_History.Ticker' THEN 'IDX ticker: the entity key (several rows per ticker, one per version; history_id identifies a row).'
        WHEN 'IDX_Stock_Universe_History.broker_code' THEN 'Two-character IDX broker code: the entity key (several rows per broker, one per version; history_id identifies a row).'
        WHEN 'IDX_Stock_Universe_History.valid_from' THEN 'Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis).'
        WHEN 'IDX_Stock_Universe_History.valid_to' THEN 'Effective end of this version (exclusive); NULL = still in effect in this knowledge version.'
        WHEN 'IDX_Stock_Universe_History.valid_basis' THEN 'FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction).'
        WHEN 'IDX_Stock_Universe_History.available_at' THEN 'When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound.'
        WHEN 'IDX_Stock_Universe_History.available_basis' THEN 'RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from.'
        WHEN 'IDX_Stock_Universe_History.recorded_from' THEN 'When Saniti recorded this row (start of the knowledge period).'
        WHEN 'IDX_Stock_Universe_History.recorded_to' THEN 'When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept.'
        WHEN 'IDX_Stock_Universe_History.superseded_reason' THEN 'Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge.'
        WHEN 'IDX_Stock_Universe_History.pit_valid_from' THEN 'First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to.'
        WHEN 'IDX_Stock_Universe_History.pit_valid_to' THEN 'Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date.'
        WHEN 'IDX_Stock_Universe_History.capture_id' THEN 'The Reference_History_Capture_Log row of the capture or correction that wrote this row.'
        WHEN 'IDX_Stock_Universe_History.source_provenance' THEN 'How the row was written: source table, operation and capture id, the version it closes or replaces, or a correction''s reason, source and superseded ids.'
        WHEN 'IDX_Stock_Universe_History.Ticker' THEN 'Entity key, as in IDX_Stock_Universe.'
        WHEN 'IDX_Stock_Universe_History.Company Name' THEN 'IDX_Stock_Universe.Company Name of this version.'
        WHEN 'IDX_Stock_Universe_History.Exchange' THEN 'IDX_Stock_Universe.Exchange of this version.'
        WHEN 'IDX_Stock_Universe_History.Security Type' THEN 'IDX_Stock_Universe.Security Type of this version.'
        WHEN 'IDX_Stock_Universe_History.Type Specs' THEN 'IDX_Stock_Universe.Type Specs of this version.'
        WHEN 'IDX_Stock_Universe_History.Is Common Stock' THEN 'IDX_Stock_Universe.Is Common Stock of this version.'
        WHEN 'IDX_Stock_Universe_History.ISIN' THEN 'IDX_Stock_Universe.ISIN of this version.'
        WHEN 'IDX_Stock_Universe_History.Sector' THEN 'IDX_Stock_Universe.Sector of this version.'
        WHEN 'IDX_Stock_Universe_History.Industry' THEN 'IDX_Stock_Universe.Industry of this version.'
        WHEN 'IDX_Broker_Profile_History.history_id' THEN 'Row id of one version (identity only).'
        WHEN 'IDX_Broker_Profile_History.Ticker' THEN 'IDX ticker: the entity key (several rows per ticker, one per version; history_id identifies a row).'
        WHEN 'IDX_Broker_Profile_History.broker_code' THEN 'Two-character IDX broker code: the entity key (several rows per broker, one per version; history_id identifies a row).'
        WHEN 'IDX_Broker_Profile_History.valid_from' THEN 'Effective start of this version (inclusive). FIRST_CAPTURE and CHANGE_CAPTURED rows use the Asia/Jakarta date Saniti recorded it; the true date is on or before it and unknown (valid_basis).'
        WHEN 'IDX_Broker_Profile_History.valid_to' THEN 'Effective end of this version (exclusive); NULL = still in effect in this knowledge version.'
        WHEN 'IDX_Broker_Profile_History.valid_basis' THEN 'FIRST_CAPTURE (valid_from is the first recording date; the true start is earlier and unknown), CHANGE_CAPTURED (valid_from is the date the change was recorded; the true change date is on or before it) or DOCUMENTED (a documented effective date given by a correction).'
        WHEN 'IDX_Broker_Profile_History.available_at' THEN 'When the information was available to decisions: the recording time (available_basis RECORDED) or a documented publication time (DOCUMENTED_PUBLICATION, corrections only). Point-in-time selection uses recorded time, its conservative bound.'
        WHEN 'IDX_Broker_Profile_History.available_basis' THEN 'RECORDED or DOCUMENTED_PUBLICATION: where available_at comes from.'
        WHEN 'IDX_Broker_Profile_History.recorded_from' THEN 'When Saniti recorded this row (start of the knowledge period).'
        WHEN 'IDX_Broker_Profile_History.recorded_to' THEN 'When Saniti superseded this row (end of the knowledge period, exclusive); NULL = current knowledge. Superseded rows are kept.'
        WHEN 'IDX_Broker_Profile_History.superseded_reason' THEN 'Why the row was superseded: CHANGE_CAPTURED, SAME_DAY_REVISION or CORRECTION; NULL for current knowledge.'
        WHEN 'IDX_Broker_Profile_History.pit_valid_from' THEN 'First observation date this row applies to point in time: the later of valid_from and the Asia/Jakarta date after recorded_from (a value recorded on a date is used from the next date). EFFECTIVE_DATED joins use pit_valid_from <= date < pit_valid_to.'
        WHEN 'IDX_Broker_Profile_History.pit_valid_to' THEN 'Observation date from which this row no longer applies point in time (exclusive): the earlier of valid_to and the Asia/Jakarta date after recorded_to; NULL = open. A row with pit_valid_to <= pit_valid_from applies to no date.'
        WHEN 'IDX_Broker_Profile_History.capture_id' THEN 'The Reference_History_Capture_Log row of the capture or correction that wrote this row.'
        WHEN 'IDX_Broker_Profile_History.source_provenance' THEN 'How the row was written: source table, operation and capture id, the version it closes or replaces, or a correction''s reason, source and superseded ids.'
        WHEN 'IDX_Broker_Profile_History.broker_code' THEN 'Entity key, as in IDX_Broker_Profile.'
        WHEN 'IDX_Broker_Profile_History.broker_name' THEN 'IDX_Broker_Profile.broker_name of this version.'
        WHEN 'IDX_Broker_Profile_History.broker_type' THEN 'IDX_Broker_Profile.broker_type of this version.'
        WHEN 'IDX_Broker_Profile_History.broker_classification' THEN 'IDX_Broker_Profile.broker_classification of this version.'
        WHEN 'Reference_History_Capture_Log.capture_id' THEN 'Identity of one capture or correction.'
        WHEN 'Reference_History_Capture_Log.source_table' THEN 'IDX_Stock_Universe or IDX_Broker_Profile.'
        WHEN 'Reference_History_Capture_Log.trigger_operation' THEN 'INSERT, UPDATE, DELETE or TRUNCATE (trigger), INITIAL (migration), MANUAL, or CORRECTION.'
        WHEN 'Reference_History_Capture_Log.captured_at' THEN 'Transaction time of the capture; the recorded_from of the rows it wrote.'
        WHEN 'Reference_History_Capture_Log.status' THEN 'CAPTURED (versions written), NO_CHANGE, or FAILED (error set; the reference load itself succeeded).'
        WHEN 'Reference_History_Capture_Log.source_rows' THEN 'Rows in the source table at capture time.'
        WHEN 'Reference_History_Capture_Log.versions_changed' THEN 'Versions superseded (changed attributes, or overlapped by a correction).'
        WHEN 'Reference_History_Capture_Log.versions_opened' THEN 'Versions written for new keys, reappearing keys or correction remainders.'
        WHEN 'Reference_History_Capture_Log.absent_entities' THEN 'Keys with an open version but no source row: counted only, never closed.'
        WHEN 'Reference_History_Capture_Log.absent_examples' THEN 'Up to 20 of the absent keys.'
        WHEN 'Reference_History_Capture_Log.error' THEN 'SQLSTATE and message of a failed capture; NULL otherwise.'
       END,
       CASE WHEN c.is_generated = 'ALWAYS' THEN c.generation_expression END, NULL,
       CASE WHEN c.is_nullable = 'YES' THEN 'NULL when not applicable, as the definition states.'
            ELSE 'NULL is not permitted.' END,
       ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql'], 'PARTIAL'
FROM information_schema.columns AS c
WHERE c.table_schema = 'public'
  AND c.table_name IN ('IDX_Stock_Universe_History', 'IDX_Broker_Profile_History', 'Reference_History_Capture_Log');

INSERT INTO public."Column_Catalog" (
    table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, default_expression,
    is_primary_key, definition, source_column_or_expression, unit, null_rule, source_code_paths, documentation_status)
SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position, c.data_type, false, NULL, false,
       'HISTORICAL (the value belongs to its row''s date or version) or CURRENT_STATE (today''s reference value on every row); a point-in-time DataNeedSpec may not read or filter a CURRENT_STATE column.',
       NULL, NULL, 'NULL is not permitted.',
       ARRAY['database/migrations/20260927_006_reference_history_point_in_time.sql'], 'PARTIAL'
FROM information_schema.columns AS c
WHERE c.table_schema = 'public' AND c.table_name = 'AI_column_catalog' AND c.column_name = 'value_time_basis';

-- Tool_Catalog: the time_basis versions of the DataNeed tools, inactive (market-ai-orc registers them from code only
-- with AI_ENABLE_POINT_IN_TIME); every other column is copied from the previous version
INSERT INTO public."Tool_Catalog" (
    tool_name, tool_family, tool_type, purpose, input_schema, output_schema,
    execution_type, handler_name, default_output_rows, max_output_rows,
    max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
    timeout_seconds, max_output_bytes, max_llm_result_rows,
    max_llm_result_bytes, max_llm_result_tokens,
    requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
    tool_specific_limits, version, is_active
)
SELECT tool_name, tool_family, tool_type, purpose, next.input_schema::jsonb, output_schema,
       execution_type, handler_name, default_output_rows, max_output_rows,
       max_input_rows, max_tickers, max_date_range_days, max_estimated_rows,
       timeout_seconds, max_output_bytes, max_llm_result_rows,
       max_llm_result_bytes, max_llm_result_tokens,
       requires_analytics_worker, requires_feature_catalog, requires_data_readiness,
       tool_specific_limits || next.limits::jsonb, next.version, false
FROM public."Tool_Catalog" AS previous
JOIN (VALUES
    ('submit_data_need_spec', 'v3', 'v4', '{"type":"object","properties":{"spec_version":{"enum":["data_need_spec/v2"],"type":"string"},"request_group_id":{"description":"Lower-case id of this data need, e.g. data_request_1; revisions keep it.","type":"string"},"revision":{"description":"1 for the first submission, then the next number for each revision.","type":"integer"},"mode":{"enum":["ANALYSIS","RESEARCH"],"type":"string"},"question":{"description":"The user''s question, restated.","type":"string"},"subject":{"additionalProperties":false,"properties":{"data_domain":{"type":"string"},"entity_type":{"type":"string"},"asset_type":{"anyOf":[{"type":"string"},{"type":"null"}]}},"required":["data_domain","entity_type","asset_type"],"type":"object"},"data_requests":{"description":"1-8 logical data requests.","items":{"additionalProperties":false,"properties":{"data_request_id":{"description":"<request_group_id>_<suffix>, suffix 1-12 letters/digits, e.g. data_request_1_A. Stable across revisions.","type":"string"},"logical_name":{"description":"Lower-case name the session loads the data by, e.g. prices.","type":"string"},"source_table":{"description":"Catalog table.","type":"string"},"entity_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"The table''s catalog entity_column; null when it has none."},"time_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"The table''s catalog time_column; null for static tables."},"columns":{"description":"Catalog columns needed (entity and time columns are always added).","items":{"type":"string"},"type":"array"},"scope":{"additionalProperties":false,"properties":{"type":{"description":"ALL (every row; only as the whole scope), PREDICATE (column operator value), AND / OR (children: at least two nodes), NOT (child: one node). At most 4 levels and 40 nodes.","enum":["ALL","PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"PREDICATE: a filterable catalog column of this request''s table; else null."},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}],"description":"PREDICATE only; else null."},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."},"children":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},"type":"array"},{"type":"null"}],"description":"AND / OR only; else null."},"child":{"anyOf":[{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},{"type":"null"}],"description":"NOT only; else null."}},"required":["type","column","operator","value","children","child"],"type":"object","description":"Which rows, as an expression tree on filterable columns of this table."},"time_ranges":{"description":"One or more named ranges ([] for static tables).","items":{"additionalProperties":false,"properties":{"range_id":{"description":"Unique within the request, e.g. current_ytd, previous_comparable.","type":"string"},"start":{"description":"YYYY-MM-DD, first date of the range.","type":"string"},"end":{"description":"YYYY-MM-DD, last date of the range; not after the reference date.","type":"string"}},"required":["range_id","start","end"],"type":"object"},"type":"array"},"source_frequency":{"description":"A supported_frequencies value of the table (1D, ...; STATIC).","type":"string"},"analysis_frequency":{"description":"Frequency of the analysis (same as source, or coarser with resample).","type":"string"},"resample":{"anyOf":[{"enum":["DAILY","WEEKLY","MONTHLY","QUARTERLY","YEARLY"],"type":"string"},{"type":"null"}],"description":"Required when analysis_frequency is coarser than source_frequency; else null."},"history_buffer":{"anyOf":[{"additionalProperties":false,"properties":{"value":{"type":"integer"},"unit":{"enum":["TRADING_OBSERVATIONS","CALENDAR_DAYS"],"type":"string"}},"required":["value","unit"],"type":"object"},{"type":"null"}],"description":"Observations before each range needed as warm-up; null if none."},"future_buffer":{"anyOf":[{"additionalProperties":false,"properties":{"value":{"type":"integer"},"unit":{"enum":["TRADING_OBSERVATIONS","CALENDAR_DAYS"],"type":"string"}},"required":["value","unit"],"type":"object"},{"type":"null"}],"description":"Observations after each range (e.g. forward outcomes); null if none."},"ordering":{"description":"Row order of the delivered dataset ([] for none).","items":{"additionalProperties":false,"properties":{"column":{"type":"string"},"direction":{"enum":["ASC","DESC"],"type":"string"}},"required":["column","direction"],"type":"object"},"type":"array"},"sampling_allowed":{"description":"Always false: data is never sampled.","type":"boolean"}},"required":["data_request_id","logical_name","source_table","entity_column","time_column","columns","scope","time_ranges","source_frequency","analysis_frequency","resample","history_buffer","future_buffer","ordering","sampling_allowed"],"type":"object"},"type":"array"},"relationships":{"description":"Catalog relationships between requests ([] for none), each with every key pair.","items":{"additionalProperties":false,"description":"data_need_spec/v2 (AI_ENABLE_COMPOSITE_KEYS, IP1 Stage B): a relationship names every entity key pair.","properties":{"relationship_id":{"description":"Catalog relationship_id between the two requests'' tables.","type":"integer"},"left_request_id":{"type":"string"},"left_columns":{"description":"Every entity key column of the catalog relationship on this side, in the order of its left_columns / right_columns without the time column (a composite key such as ticker, broker, investor_type and market_board names all of them).","items":{"type":"string"},"type":"array"},"right_request_id":{"type":"string"},"right_columns":{"description":"The matching right-side key columns, pair by pair with left_columns.","items":{"type":"string"},"type":"array"},"join_type":{"description":"INNER restricts the left request to rows with a match in the right request''s scope; LEFT leaves it unrestricted. Each request is delivered as its own dataset; the analysis joins them.","enum":["INNER","LEFT"],"type":"string"},"join_semantics":{"description":"One of the relationship''s supported_join_semantics in the catalog.","enum":["CURRENT_STATE","EXACT_DATE","AS_OF","EFFECTIVE_DATED"],"type":"string"},"left_time_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EXACT_DATE / AS_OF: the catalog left time column; else null."},"right_time_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EXACT_DATE / AS_OF: the catalog right time column; else null."},"as_of_direction":{"anyOf":[{"enum":["BACKWARD"],"type":"string"},{"type":"null"}],"description":"AS_OF only; else null."},"effective_from_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EFFECTIVE_DATED only: catalog column; else null."},"effective_to_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EFFECTIVE_DATED only: catalog column; else null."}},"required":["relationship_id","left_request_id","left_columns","right_request_id","right_columns","join_type","join_semantics","left_time_column","right_time_column","as_of_direction","effective_from_column","effective_to_column"],"type":"object"},"type":"array"},"time_basis":{"description":"HISTORICAL_DESCRIPTIVE (normal): history may be described with current reference data such as today''s sector, disclosed. POINT_IN_TIME only when the user asks for what was known at the time (no look-ahead, backtest, classification as of each date): only values in effect and already recorded on each date, through the EFFECTIVE_DATED relationships of the history tables; refused with POINT_IN_TIME_UNAVAILABLE where that history does not exist, never replaced by current data.","enum":["HISTORICAL_DESCRIPTIVE","POINT_IN_TIME"],"type":"string"},"research_governance":{"anyOf":[{"additionalProperties":false,"properties":{"hypothesis_id":{"description":"Lower-case id; revisions of a request group keep it.","type":"string"},"hypothesis":{"type":"string"},"objective":{"type":"string"},"condition":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"The condition or event, in plain words; a declaration only. With an approved Research Plan: its experiment''s text."},"outcome":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"The outcome measured after the condition, in plain words."},"baseline":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"What the outcome is compared with, in plain words."},"candidate_count":{"description":"Conditions, lags or parameter combinations the experiment evaluates.","type":"integer"},"pairwise_comparisons":{"type":"integer"},"holdout":{"anyOf":[{"additionalProperties":false,"properties":{"data_request_id":{"type":"string"},"range_id":{"description":"One of that request''s declared ranges, kept out of fitting.","type":"string"}},"required":["data_request_id","range_id"],"type":"object"},{"type":"null"}]},"minimum_sample":{"anyOf":[{"additionalProperties":false,"properties":{"value":{"type":"integer"},"unit":{"enum":["EVENTS","OBSERVATIONS","ENTITIES"],"type":"string"}},"required":["value","unit"],"type":"object"},{"type":"null"}]},"multiple_testing_policy":{"description":"NONE only for a single comparison.","enum":["NONE","BONFERRONI","HOLM","BENJAMINI_HOCHBERG"],"type":"string"},"followup_of":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"request_group_id of an approved experiment on the same hypothesis this one follows up; else null."}},"required":["hypothesis_id","hypothesis","objective","condition","outcome","baseline","candidate_count","pairwise_comparisons","holdout","minimum_sample","multiple_testing_policy","followup_of"],"type":"object"},{"type":"null"}],"description":"Required for RESEARCH; null for ANALYSIS."}},"required":["spec_version","request_group_id","revision","mode","question","subject","data_requests","relationships","time_basis","research_governance"],"additionalProperties":false}',
     '{"feature_flag":"AI_ENABLE_POINT_IN_TIME","registry_state":"data_need_spec/v2 input with time_basis (HISTORICAL_DESCRIPTIVE / POINT_IN_TIME). Registered in market-ai-orc only with AI_ENABLE_COMPOSITE_KEYS and AI_ENABLE_POINT_IN_TIME and a sandbox reporting point_in_time; v3 (no time_basis) or v2 otherwise.","runtime_commit":"4dfa7af","spec_version":"data_need_spec/v2","time_basis":["HISTORICAL_DESCRIPTIVE","POINT_IN_TIME"]}'),
    ('check_data_feasibility', 'v2', 'v3', '{"type":"object","properties":{"spec_version":{"enum":["data_need_spec/v2"],"type":"string"},"request_group_id":{"description":"Lower-case id of this data need, e.g. data_request_1; revisions keep it.","type":"string"},"revision":{"description":"1 for the first submission, then the next number for each revision.","type":"integer"},"mode":{"enum":["ANALYSIS","RESEARCH"],"type":"string"},"question":{"description":"The user''s question, restated.","type":"string"},"subject":{"additionalProperties":false,"properties":{"data_domain":{"type":"string"},"entity_type":{"type":"string"},"asset_type":{"anyOf":[{"type":"string"},{"type":"null"}]}},"required":["data_domain","entity_type","asset_type"],"type":"object"},"data_requests":{"description":"1-8 logical data requests.","items":{"additionalProperties":false,"properties":{"data_request_id":{"description":"<request_group_id>_<suffix>, suffix 1-12 letters/digits, e.g. data_request_1_A. Stable across revisions.","type":"string"},"logical_name":{"description":"Lower-case name the session loads the data by, e.g. prices.","type":"string"},"source_table":{"description":"Catalog table.","type":"string"},"entity_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"The table''s catalog entity_column; null when it has none."},"time_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"The table''s catalog time_column; null for static tables."},"columns":{"description":"Catalog columns needed (entity and time columns are always added).","items":{"type":"string"},"type":"array"},"scope":{"additionalProperties":false,"properties":{"type":{"description":"ALL (every row; only as the whole scope), PREDICATE (column operator value), AND / OR (children: at least two nodes), NOT (child: one node). At most 4 levels and 40 nodes.","enum":["ALL","PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"PREDICATE: a filterable catalog column of this request''s table; else null."},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}],"description":"PREDICATE only; else null."},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."},"children":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},"type":"array"},{"type":"null"}],"description":"AND / OR only; else null."},"child":{"anyOf":[{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"properties":{"type":{"enum":["PREDICATE","AND","OR","NOT"],"type":"string"},"column":{"anyOf":[{"type":"string"},{"type":"null"}]},"operator":{"anyOf":[{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},{"type":"null"}]},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}]},"children":{"anyOf":[{"items":{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},"type":"array"},{"type":"null"}]},"child":{"anyOf":[{"additionalProperties":false,"description":"Depth 4: only a predicate fits here.","properties":{"type":{"enum":["PREDICATE"],"type":"string"},"column":{"type":"string"},"operator":{"enum":["EQ","NEQ","GT","GTE","LT","LTE","IN","NOT_IN","BETWEEN","IS_NULL","IS_NOT_NULL"],"type":"string"},"value":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"},{"type":"boolean"},{"items":{"anyOf":[{"type":"string"},{"type":"integer"},{"type":"number"}]},"type":"array"},{"type":"null"}],"description":"Scalar for EQ/NEQ/GT/GTE/LT/LTE; a list for IN/NOT_IN; [low, high] for BETWEEN; null for IS_NULL/IS_NOT_NULL. The exact catalog data value."}},"required":["type","column","operator","value"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},{"type":"null"}]}},"required":["type","column","operator","value","children","child"],"type":"object"},{"type":"null"}],"description":"NOT only; else null."}},"required":["type","column","operator","value","children","child"],"type":"object","description":"Which rows, as an expression tree on filterable columns of this table."},"time_ranges":{"description":"One or more named ranges ([] for static tables).","items":{"additionalProperties":false,"properties":{"range_id":{"description":"Unique within the request, e.g. current_ytd, previous_comparable.","type":"string"},"start":{"description":"YYYY-MM-DD, first date of the range.","type":"string"},"end":{"description":"YYYY-MM-DD, last date of the range; not after the reference date.","type":"string"}},"required":["range_id","start","end"],"type":"object"},"type":"array"},"source_frequency":{"description":"A supported_frequencies value of the table (1D, ...; STATIC).","type":"string"},"analysis_frequency":{"description":"Frequency of the analysis (same as source, or coarser with resample).","type":"string"},"resample":{"anyOf":[{"enum":["DAILY","WEEKLY","MONTHLY","QUARTERLY","YEARLY"],"type":"string"},{"type":"null"}],"description":"Required when analysis_frequency is coarser than source_frequency; else null."},"history_buffer":{"anyOf":[{"additionalProperties":false,"properties":{"value":{"type":"integer"},"unit":{"enum":["TRADING_OBSERVATIONS","CALENDAR_DAYS"],"type":"string"}},"required":["value","unit"],"type":"object"},{"type":"null"}],"description":"Observations before each range needed as warm-up; null if none."},"future_buffer":{"anyOf":[{"additionalProperties":false,"properties":{"value":{"type":"integer"},"unit":{"enum":["TRADING_OBSERVATIONS","CALENDAR_DAYS"],"type":"string"}},"required":["value","unit"],"type":"object"},{"type":"null"}],"description":"Observations after each range (e.g. forward outcomes); null if none."},"ordering":{"description":"Row order of the delivered dataset ([] for none).","items":{"additionalProperties":false,"properties":{"column":{"type":"string"},"direction":{"enum":["ASC","DESC"],"type":"string"}},"required":["column","direction"],"type":"object"},"type":"array"},"sampling_allowed":{"description":"Always false: data is never sampled.","type":"boolean"}},"required":["data_request_id","logical_name","source_table","entity_column","time_column","columns","scope","time_ranges","source_frequency","analysis_frequency","resample","history_buffer","future_buffer","ordering","sampling_allowed"],"type":"object"},"type":"array"},"relationships":{"description":"Catalog relationships between requests ([] for none), each with every key pair.","items":{"additionalProperties":false,"description":"data_need_spec/v2 (AI_ENABLE_COMPOSITE_KEYS, IP1 Stage B): a relationship names every entity key pair.","properties":{"relationship_id":{"description":"Catalog relationship_id between the two requests'' tables.","type":"integer"},"left_request_id":{"type":"string"},"left_columns":{"description":"Every entity key column of the catalog relationship on this side, in the order of its left_columns / right_columns without the time column (a composite key such as ticker, broker, investor_type and market_board names all of them).","items":{"type":"string"},"type":"array"},"right_request_id":{"type":"string"},"right_columns":{"description":"The matching right-side key columns, pair by pair with left_columns.","items":{"type":"string"},"type":"array"},"join_type":{"description":"INNER restricts the left request to rows with a match in the right request''s scope; LEFT leaves it unrestricted. Each request is delivered as its own dataset; the analysis joins them.","enum":["INNER","LEFT"],"type":"string"},"join_semantics":{"description":"One of the relationship''s supported_join_semantics in the catalog.","enum":["CURRENT_STATE","EXACT_DATE","AS_OF","EFFECTIVE_DATED"],"type":"string"},"left_time_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EXACT_DATE / AS_OF: the catalog left time column; else null."},"right_time_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EXACT_DATE / AS_OF: the catalog right time column; else null."},"as_of_direction":{"anyOf":[{"enum":["BACKWARD"],"type":"string"},{"type":"null"}],"description":"AS_OF only; else null."},"effective_from_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EFFECTIVE_DATED only: catalog column; else null."},"effective_to_column":{"anyOf":[{"type":"string"},{"type":"null"}],"description":"EFFECTIVE_DATED only: catalog column; else null."}},"required":["relationship_id","left_request_id","left_columns","right_request_id","right_columns","join_type","join_semantics","left_time_column","right_time_column","as_of_direction","effective_from_column","effective_to_column"],"type":"object"},"type":"array"},"time_basis":{"description":"HISTORICAL_DESCRIPTIVE (normal): history may be described with current reference data such as today''s sector, disclosed. POINT_IN_TIME only when the user asks for what was known at the time (no look-ahead, backtest, classification as of each date): only values in effect and already recorded on each date, through the EFFECTIVE_DATED relationships of the history tables; refused with POINT_IN_TIME_UNAVAILABLE where that history does not exist, never replaced by current data.","enum":["HISTORICAL_DESCRIPTIVE","POINT_IN_TIME"],"type":"string"}},"required":["spec_version","request_group_id","revision","mode","question","subject","data_requests","relationships","time_basis"],"additionalProperties":false}',
     '{"feature_flag":"AI_ENABLE_POINT_IN_TIME","registry_state":"data_need_spec/v2 input with time_basis. Registered in market-ai-orc only with AI_ENABLE_PLAN_FEASIBILITY, AI_ENABLE_COMPOSITE_KEYS and AI_ENABLE_POINT_IN_TIME; v2 or v1 input otherwise.","runtime_commit":"4dfa7af","spec_version":"data_need_spec/v2","time_basis":["HISTORICAL_DESCRIPTIVE","POINT_IN_TIME"]}')
) AS next(name, from_version, version, input_schema, limits)
  ON previous.tool_name = next.name AND previous.version = next.from_version;

DO $verify$
DECLARE
    v_universe bigint;
    v_profile bigint;
    v_probe text;
BEGIN
    SELECT count(*) INTO v_universe FROM public."IDX_Stock_Universe";
    SELECT count(*) INTO v_profile FROM public."IDX_Broker_Profile";
    -- the first snapshot: one open FIRST_CAPTURE version per source row, valid from the capture date only
    IF (SELECT count(*) FROM public."IDX_Stock_Universe_History"
        WHERE recorded_to IS NULL AND valid_to IS NULL AND valid_basis = 'FIRST_CAPTURE'
          AND valid_from = (timezone('Asia/Jakarta', now()))::date) <> v_universe
       OR (SELECT count(*) FROM public."IDX_Stock_Universe_History") <> v_universe
       OR (SELECT count(*) FROM public."IDX_Broker_Profile_History"
           WHERE recorded_to IS NULL AND valid_to IS NULL AND valid_basis = 'FIRST_CAPTURE') <> v_profile
       OR (SELECT count(*) FROM public."IDX_Broker_Profile_History") <> v_profile THEN
        RAISE EXCEPTION 'The first capture does not match the source tables';
    END IF;
    IF (SELECT count(*) FROM public."Reference_History_Capture_Log" WHERE status = 'CAPTURED'
        AND trigger_operation = 'INITIAL') <> 2 THEN
        RAISE EXCEPTION 'The initial captures are not logged';
    END IF;
    IF (SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        WHERE t.tgname = 'reference_history_capture' AND c.relname IN ('IDX_Stock_Universe', 'IDX_Broker_Profile')
          AND t.tgenabled = 'O') <> 2 THEN
        RAISE EXCEPTION 'The capture triggers are not enabled';
    END IF;
    -- the trigger path, probed in a rolled-back subtransaction (no log row, no Database_Table_Status change is kept):
    -- a statement that changes nothing records nothing and fails nothing
    BEGIN
        UPDATE public."IDX_Broker_Profile" SET broker_name = broker_name WHERE false;
        UPDATE public."IDX_Stock_Universe" SET "Sector" = "Sector" WHERE false;
        SELECT string_agg(status, ',' ORDER BY capture_id) INTO v_probe FROM public."Reference_History_Capture_Log"
        WHERE trigger_operation = 'UPDATE';
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'probe:' || coalesce(v_probe, 'none');
    EXCEPTION WHEN raise_exception THEN
        v_probe := SQLERRM;
    END;
    IF v_probe IS DISTINCT FROM 'probe:NO_CHANGE,NO_CHANGE' THEN
        RAISE EXCEPTION 'The capture triggers did not run cleanly: %', v_probe;
    END IF;
    -- value_time_basis: exactly the documented current-state columns of the seven tables
    IF (SELECT array_agg(table_name || '.' || column_name ORDER BY table_name || '.' || column_name) FROM public."AI_column_catalog"
        WHERE value_time_basis = 'CURRENT_STATE'
          AND table_name NOT IN ('IDX_Stock_Universe', 'IDX_Broker_Profile'))
       IS DISTINCT FROM ARRAY['Feature_01_Stock_Daily.industry', 'Feature_01_Stock_Daily.sector',
                              'Feature_02_Broker_Rolling.broker_classification',
                              'Feature_03_Stock_Broker_Daily.institutional_net_value',
                              'Feature_03_Stock_Broker_Daily.mixed_net_value',
                              'Feature_03_Stock_Broker_Daily.niche_net_value',
                              'Feature_03_Stock_Broker_Daily.retail_net_value'] THEN
        RAISE EXCEPTION 'Unexpected CURRENT_STATE columns: %', (SELECT array_agg(table_name || '.' || column_name ORDER BY table_name || '.' || column_name)
            FROM public."AI_column_catalog" WHERE value_time_basis = 'CURRENT_STATE'
              AND table_name NOT IN ('IDX_Stock_Universe', 'IDX_Broker_Profile'));
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_column_catalog" WHERE table_name IN ('IDX_Stock_Universe', 'IDX_Broker_Profile')
               AND value_time_basis <> 'CURRENT_STATE') THEN
        RAISE EXCEPTION 'A current reference column is not CURRENT_STATE';
    END IF;
    -- AI catalog: both history tables, every exposed column, seven EFFECTIVE_DATED relationships
    IF (SELECT count(*) FROM public."AI_table_catalog" WHERE table_name IN ('IDX_Stock_Universe_History',
            'IDX_Broker_Profile_History') AND is_active AND time_column IS NULL) <> 2
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'IDX_Stock_Universe_History'
           AND description IS NOT NULL AND value_time_basis = 'HISTORICAL') <> 20
       OR (SELECT count(*) FROM public."AI_column_catalog" WHERE table_name = 'IDX_Broker_Profile_History'
           AND description IS NOT NULL AND value_time_basis = 'HISTORICAL') <> 15 THEN
        RAISE EXCEPTION 'The history tables are not completely registered in the AI catalog';
    END IF;
    IF (SELECT count(*) FROM public."AI_catalog_relationships" WHERE supported_join_semantics = ARRAY['EFFECTIVE_DATED']
        AND effective_from_column = 'pit_valid_from' AND effective_to_column = 'pit_valid_to' AND is_allowed
        AND right_table IN ('IDX_Stock_Universe_History', 'IDX_Broker_Profile_History')) <> 7 THEN
        RAISE EXCEPTION 'The EFFECTIVE_DATED relationships are not all registered';
    END IF;
    -- every relationship key column exists on both sides
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships" r
               WHERE r.right_table IN ('IDX_Stock_Universe_History', 'IDX_Broker_Profile_History')
                 AND (NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" c WHERE c.table_name = r.left_table
                                  AND c.column_name = r.left_columns[1])
                      OR NOT EXISTS (SELECT 1 FROM public."AI_column_catalog" c WHERE c.table_name = r.right_table
                                     AND c.column_name = r.right_columns[1]))) THEN
        RAISE EXCEPTION 'A relationship key column is not in the AI catalog';
    END IF;
    -- documentation catalogs
    IF (SELECT count(*) FROM public."Table_Catalog" WHERE table_name IN ('IDX_Stock_Universe_History',
            'IDX_Broker_Profile_History', 'Reference_History_Capture_Log')) <> 3
       OR EXISTS (SELECT 1 FROM information_schema.columns c
                  WHERE c.table_schema = 'public'
                    AND c.table_name IN ('IDX_Stock_Universe_History', 'IDX_Broker_Profile_History',
                                         'Reference_History_Capture_Log')
                    AND NOT EXISTS (SELECT 1 FROM public."Column_Catalog" k WHERE k.table_name = c.table_name
                                    AND k.column_name = c.column_name AND k.definition IS NOT NULL))
       OR NOT EXISTS (SELECT 1 FROM public."Column_Catalog" WHERE table_name = 'AI_column_catalog'
                      AND column_name = 'value_time_basis') THEN
        RAISE EXCEPTION 'A new table or column lacks its Table_Catalog / Column_Catalog definition';
    END IF;
    IF (SELECT count(*) FROM public."Tool_Catalog" WHERE NOT is_active
        AND ((tool_name = 'submit_data_need_spec' AND version = 'v4')
             OR (tool_name = 'check_data_feasibility' AND version = 'v3'))
        AND input_schema->'properties'->'time_basis'->'enum' = '["HISTORICAL_DESCRIPTIVE", "POINT_IN_TIME"]'::jsonb
        AND input_schema->'required' ? 'time_basis') <> 2 THEN
        RAISE EXCEPTION 'The time_basis tool contracts were not registered';
    END IF;
    -- privileges: the Governor reads the history and the availability metadata, nothing else of Table_Catalog
    IF NOT has_table_privilege('market_ai_sql_reader', 'public."IDX_Stock_Universe_History"', 'SELECT')
       OR NOT has_table_privilege('market_ai_sql_reader', 'public."IDX_Broker_Profile_History"', 'SELECT')
       OR has_table_privilege('market_ai_sql_reader', 'public."IDX_Stock_Universe_History"', 'INSERT,UPDATE,DELETE')
       OR NOT has_column_privilege('market_ai_sql_reader', 'public."Table_Catalog"', 'point_in_time_status', 'SELECT')
       OR has_column_privilege('market_ai_sql_reader', 'public."Table_Catalog"', 'source_system', 'SELECT')
       OR NOT has_column_privilege('market_ai_catalog_reader', 'public."Table_Catalog"', 'availability_rule', 'SELECT')
       OR has_function_privilege('market_ai_sql_reader',
            'public.correct_stock_universe_history(text, date, date, jsonb, text, timestamp with time zone, text, text)',
            'EXECUTE') THEN
        RAISE EXCEPTION 'Unexpected privileges on the history tables or Table_Catalog';
    END IF;
END
$verify$;

COMMIT;
