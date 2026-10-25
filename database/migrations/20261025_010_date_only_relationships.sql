-- EXEC-M216 (user 2026-10-25, "Oke, kita go dengan eksekusi B."): relationships between a stock Feature table and its
-- IDX Composite Index (IHSG) counterpart, on the keys both share and the same date. Feature 01 and 04 share no key but
-- the date (a date-only relationship, empty request_key_columns); the broker Features share the market board, broker
-- and investor type. Needs the date-only join of the SQL Governor (extract.py), the sandbox (data_need.py,
-- saniti_session.py) and market-ai-orc (round_ae, 20261025_009), deployed before this migration.
--
-- Derived, not listed: for each *_INDEX table registered in Table_Catalog, its counterpart is the exposed stock object
-- of the same base table (as in 20261025_005); the paired columns are the primary key columns (AI_table_catalog) of
-- both, without the entity column and the time column, that hold at least one common stored value (Feature 04's
-- asset_type is 'equity'/'bonds' in the stock table and 'index' in the INDEX table, so it is not a key between them).
-- The INDEX side is the "one" side (MANY_TO_ONE): a data need must fix its ticker (and every other key column left
-- open) in its scope, ONE_SIDE_NOT_UNIQUE otherwise, so a second index never doubles the rows.
--
-- A new CHECK keeps a relationship without an entity pair (its only pair is the time pair) to EXACT_DATE / AS_OF.
-- Forward-only. Rollback: is_allowed = false (AI_catalog_relationships) and is_active = false
-- (Feature_Relationship_Catalog) on the rows of this migration.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '10min';

CREATE TEMP TABLE m216 (index_table text PRIMARY KEY, base text NOT NULL, counterpart text, time_column text,
                        entity_column text, index_key text[], counterpart_key text[], pairs text[]) ON COMMIT DROP;
INSERT INTO m216 (index_table, base)
SELECT t.table_name, left(t.table_name, length(t.table_name) - 6)
FROM public."Table_Catalog" AS t
WHERE t.table_schema = 'public' AND t.table_name ~ '^Feature_0[1-6]_[A-Za-z_]+_INDEX$';
UPDATE m216 AS m
SET counterpart = (SELECT a.table_name FROM public."AI_table_catalog" AS a
                   WHERE a.is_active AND a.table_name IN (m.base, m.base || '_Stock')
                   ORDER BY a.table_name = m.base DESC LIMIT 1),
    time_column = i.time_column, entity_column = i.entity_column, index_key = i.primary_key_columns
FROM public."AI_table_catalog" AS i
WHERE i.table_name = m.index_table AND i.is_active;
UPDATE m216 AS m SET counterpart_key = c.primary_key_columns
FROM public."AI_table_catalog" AS c WHERE c.table_name = m.counterpart;

DO $preflight$
DECLARE
    r record;
BEGIN
    IF (SELECT count(*) FROM m216) <> 6 OR EXISTS (SELECT 1 FROM m216 WHERE counterpart IS NULL OR index_key IS NULL
                                                   OR counterpart_key IS NULL OR time_column IS NULL) THEN
        RAISE EXCEPTION 'Expected six active INDEX tables with an exposed stock counterpart: reconcile first';
    END IF;
    FOR r IN SELECT m.*, c.time_column AS counterpart_time, c.entity_column AS counterpart_entity
             FROM m216 AS m JOIN public."AI_table_catalog" AS c ON c.table_name = m.counterpart LOOP
        IF r.counterpart_time IS DISTINCT FROM r.time_column OR r.counterpart_entity IS DISTINCT FROM r.entity_column THEN
            RAISE EXCEPTION '% and % name their time or entity column differently', r.counterpart, r.index_table;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships" AS a JOIN m216 AS m
               ON (a.left_table, a.right_table) IN ((m.counterpart, m.index_table), (m.index_table, m.counterpart)))
       OR EXISTS (SELECT 1 FROM public."Feature_Relationship_Catalog" AS f JOIN m216 AS m
                  ON (f.left_feature_table, f.right_feature_table) IN ((m.base, m.index_table), (m.index_table, m.base))) THEN
        RAISE EXCEPTION 'A stock-to-INDEX relationship is already registered';
    END IF;
    IF EXISTS (SELECT 1 FROM public."AI_catalog_relationships"
               WHERE cardinality(left_columns) = 1 AND left_columns[1] = left_time_column
                 AND right_columns[1] = right_time_column) THEN
        RAISE EXCEPTION 'A date-only relationship already exists: review it before the CHECK';
    END IF;
END
$preflight$;

-- the shared key columns that hold a common stored value: the INDEX values are probed most frequent first and the
-- search stops at the first one the stock object also holds
DO $pairs$
DECLARE
    m record;
    col text;
    v text;
    shared boolean;
    found text[];
BEGIN
    FOR m IN SELECT * FROM m216 LOOP
        found := ARRAY[]::text[];
        FOREACH col IN ARRAY m.index_key LOOP
            CONTINUE WHEN col IN (m.entity_column, m.time_column) OR NOT col = ANY(m.counterpart_key);
            shared := false;
            FOR v IN EXECUTE format('SELECT %I::text FROM public.%I GROUP BY 1 ORDER BY count(*) DESC', col,
                                    m.index_table) LOOP
                EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.%I WHERE %I::text = $1)', m.counterpart, col)
                    INTO shared USING v;
                EXIT WHEN shared;
            END LOOP;
            IF shared THEN
                found := found || col;
            END IF;
        END LOOP;
        UPDATE m216 SET pairs = found WHERE index_table = m.index_table;
    END LOOP;
END
$pairs$;

INSERT INTO public."Feature_Relationship_Catalog" (
    left_feature_table, right_feature_table, left_join_columns, right_join_columns, relationship_type,
    safe_output_grain, requires_preaggregation, definition, version, is_active)
SELECT m.base, m.index_table, m.pairs || m.time_column, m.pairs || m.time_column, 'MANY_TO_ONE',
       array_to_string(m.counterpart_key, ' x '), false,
       'Each stock row with the IDX Composite Index (IHSG) row of the same ' || m.time_column
       || CASE WHEN cardinality(m.pairs) = 0 THEN ' (date only: the INDEX request names its ticker)'
               ELSE ' and ' || array_to_string(m.pairs, ', ') || ' (the INDEX request names its ticker)' END
       || '; EXEC-M216.', 'v1', true
FROM m216 AS m;

INSERT INTO public."AI_catalog_relationships" (
    left_table, left_columns, right_table, right_columns, relationship_type, temporal_rule, safe_output_grain,
    requires_preaggregation, description, version, is_allowed, supported_join_semantics, left_time_column,
    right_time_column, effective_from_column, effective_to_column)
SELECT m.counterpart, m.pairs || m.time_column, m.index_table, m.pairs || m.time_column, 'MANY_TO_ONE',
       'Exact trading date', array_to_string(m.counterpart_key, ' x '), false,
       CASE WHEN cardinality(m.pairs) = 0
            THEN 'Stock rows and the index row of the same date (date only: request_key_columns are empty). '
            ELSE 'Stock rows and the index row of the same date and ' || array_to_string(m.pairs, ', ') || '. ' END
       || 'The index request must fix ticker and every other key the relationship leaves open in its scope '
       || '(for example ticker EQ ''IHSG''); EXEC-M216.',
       'v1', true, ARRAY['EXACT_DATE'], m.time_column, m.time_column, NULL, NULL
FROM m216 AS m;

ALTER TABLE public."AI_catalog_relationships"
    ADD CONSTRAINT "AI_catalog_relationships_date_only_check" CHECK (
        NOT (cardinality(left_columns) = 1 AND left_columns[1] = left_time_column
             AND right_columns[1] = right_time_column)
        OR supported_join_semantics <@ ARRAY['EXACT_DATE', 'AS_OF']::text[]) NOT VALID;
ALTER TABLE public."AI_catalog_relationships" VALIDATE CONSTRAINT "AI_catalog_relationships_date_only_check";

DO $verify$
DECLARE
    r record;
BEGIN
    IF (SELECT count(*) FROM public."AI_catalog_relationships" AS a JOIN m216 AS m
        ON a.left_table = m.counterpart AND a.right_table = m.index_table AND a.is_allowed) <> 6
       OR (SELECT count(*) FROM public."Feature_Relationship_Catalog" AS f JOIN m216 AS m
           ON f.left_feature_table = m.base AND f.right_feature_table = m.index_table AND f.is_active) <> 6 THEN
        RAISE EXCEPTION 'Expected six relationships in each catalog';
    END IF;
    -- every pair is a shared key column (never the entity), the time pair comes last
    FOR r IN SELECT m.*, a.left_columns, a.right_columns FROM m216 AS m JOIN public."AI_catalog_relationships" AS a
             ON a.left_table = m.counterpart AND a.right_table = m.index_table LOOP
        IF r.left_columns <> r.right_columns OR r.left_columns[cardinality(r.left_columns)] <> r.time_column
           OR r.entity_column = ANY(r.left_columns)
           OR NOT (r.pairs <@ r.index_key AND r.pairs <@ r.counterpart_key) THEN
            RAISE EXCEPTION 'Relationship % -> % has unexpected keys %', r.counterpart, r.index_table, r.left_columns;
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM m216 WHERE cardinality(pairs) = 0) THEN
        RAISE EXCEPTION 'No date-only relationship was derived (Feature 01 shares only ticker and date)';
    END IF;
END
$verify$;
COMMIT;
