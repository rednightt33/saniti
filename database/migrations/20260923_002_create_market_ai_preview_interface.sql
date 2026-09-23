-- Market-data preview interface for market-ai-orc.
-- public.ai_preview_table_rows(text) returns at most 20 rows, in a fixed index-backed order,
-- from exactly seven approved tables. Callers receive EXECUTE on this function only, never
-- SELECT on the tables, so the table allowlist, row limit, and ordering are enforced by the
-- database rather than by application code. Grant market_ai_preview_reader to the
-- market_ai_orc login with scripts/provision_market_ai_orc_login.py.
--
-- A SECURITY DEFINER function runs with its owner's privileges, so the function is owned by
-- market_ai_preview_owner (NOLOGIN, SELECT on exactly the seven tables, no write privilege)
-- instead of the role applying this migration. Transferring ownership to a role without CREATE
-- on schema public requires a superuser; otherwise the whole migration rolls back.
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
DECLARE
    target_name text;
BEGIN
    IF to_regprocedure('public.ai_preview_table_rows(text)') IS NOT NULL THEN
        RAISE EXCEPTION 'public.ai_preview_table_rows(text) already exists';
    END IF;
    FOREACH target_name IN ARRAY ARRAY[
        'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
        'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX'
    ]
    LOOP
        IF to_regclass(format('public.%I', target_name)) IS NULL THEN
            RAISE EXCEPTION 'Preview table is missing: %', target_name;
        END IF;
    END LOOP;
END
$preflight$;

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_preview_reader') THEN
        CREATE ROLE market_ai_preview_reader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'market_ai_preview_owner') THEN
        CREATE ROLE market_ai_preview_owner NOLOGIN;
    END IF;
END
$role$;

GRANT USAGE ON SCHEMA public TO market_ai_preview_owner;
GRANT SELECT ON
    public."Feature_01_Stock_Daily", public."Feature_02_Broker_Rolling",
    public."Feature_03_Stock_Broker_Daily", public."IDX_Broker_Profile", public."IDX_Broker_Summary",
    public."IDX_Stock_Universe", public."Price_Stock_Indonesia_IDX"
TO market_ai_preview_owner;

CREATE FUNCTION public.ai_preview_table_rows(p_table_name text)
RETURNS json
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
    order_clause text;
    result json;
BEGIN
    -- Each ORDER BY follows an existing unique index or the primary key so that LIMIT 20 is
    -- satisfied by an index scan (plus a tiny incremental sort), never a full-table sort.
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
        ELSE NULL
    END;
    IF order_clause IS NULL THEN
        RAISE EXCEPTION 'Table is not approved for preview' USING ERRCODE = 'insufficient_privilege';
    END IF;

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
            ),
            'rows', COALESCE((
                SELECT json_agg(to_json(sample) ORDER BY %2$s)
                FROM (SELECT * FROM public.%1$I ORDER BY %2$s LIMIT 20) AS sample
            ), '[]'::json)
        )
        $query$,
        p_table_name, order_clause, format('public.%I', p_table_name)
    ) INTO result;
    RETURN result;
END
$function$;

COMMENT ON FUNCTION public.ai_preview_table_rows(text) IS
    'market-ai-orc preview: at most 20 rows in a fixed index-backed order from seven approved market-data tables; EXECUTE only via market_ai_preview_reader.';

REVOKE ALL ON FUNCTION public.ai_preview_table_rows(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.ai_preview_table_rows(text) TO market_ai_preview_reader;
ALTER FUNCTION public.ai_preview_table_rows(text) OWNER TO market_ai_preview_owner;

DO $verify$
DECLARE
    relation record;
    fn oid := 'public.ai_preview_table_rows(text)'::regprocedure;
    approved text[] := ARRAY[
        'Feature_01_Stock_Daily', 'Feature_02_Broker_Rolling', 'Feature_03_Stock_Broker_Daily',
        'IDX_Broker_Profile', 'IDX_Broker_Summary', 'IDX_Stock_Universe', 'Price_Stock_Indonesia_IDX'
    ];
BEGIN
    IF NOT (SELECT prosecdef FROM pg_proc WHERE oid = fn) THEN
        RAISE EXCEPTION 'Preview function must be SECURITY DEFINER';
    END IF;
    IF (SELECT proowner FROM pg_proc WHERE oid = fn) <> 'market_ai_preview_owner'::regrole THEN
        RAISE EXCEPTION 'Preview function must be owned by market_ai_preview_owner';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'market_ai_preview_owner'
          AND (rolcanlogin OR rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'market_ai_preview_owner must be a NOLOGIN role without elevated attributes';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_auth_members
        WHERE member = 'market_ai_preview_owner'::regrole OR roleid = 'market_ai_preview_owner'::regrole
    ) THEN
        RAISE EXCEPTION 'market_ai_preview_owner must neither belong to nor be granted to any role';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc, unnest(proconfig) AS setting
        WHERE oid = fn AND setting LIKE 'search_path=%'
    ) THEN
        RAISE EXCEPTION 'Preview function must pin search_path';
    END IF;
    IF EXISTS (
        SELECT 1 FROM aclexplode((SELECT proacl FROM pg_proc WHERE oid = fn)) AS acl
        WHERE acl.grantee = 0
    ) THEN
        RAISE EXCEPTION 'PUBLIC must not execute the preview function';
    END IF;
    IF NOT has_function_privilege('market_ai_preview_reader', fn, 'EXECUTE') THEN
        RAISE EXCEPTION 'market_ai_preview_reader EXECUTE grant is missing';
    END IF;
    FOR relation IN
        SELECT c.oid, c.relname
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        IF has_table_privilege(
            'market_ai_preview_reader', relation.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'
        ) THEN
            RAISE EXCEPTION 'market_ai_preview_reader unexpectedly has table access to %', relation.relname;
        END IF;
        IF has_table_privilege(
            'market_ai_preview_owner', relation.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
        ) THEN
            RAISE EXCEPTION 'market_ai_preview_owner unexpectedly has write access to %', relation.relname;
        END IF;
        IF has_table_privilege('market_ai_preview_owner', relation.oid, 'SELECT')
           <> (relation.relname = ANY(approved)) THEN
            RAISE EXCEPTION 'market_ai_preview_owner SELECT on % does not match the approved list',
                relation.relname;
        END IF;
    END LOOP;
END
$verify$;

COMMIT;
