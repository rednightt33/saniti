-- Presentation metadata only; caller owns transaction and verifies reviewed seed against live schema.
CREATE TABLE IF NOT EXISTS public."Feature_Vocabulary" (
 source_schema text NOT NULL DEFAULT 'public' CHECK(source_schema='public'),
 source_table text NOT NULL CHECK(btrim(source_table)<>''),
 column_name text NOT NULL CHECK(btrim(column_name)<>''),
 language_code text NOT NULL DEFAULT 'id-ID' CHECK(language_code='id-ID'),
 feature_number smallint NOT NULL CHECK(feature_number IN (1,2,3,5,6)),
 scope text NOT NULL CHECK(scope IN ('stock','index')),
 column_name_proper text NOT NULL CHECK(btrim(column_name_proper)<>''),
 formula text NOT NULL CHECK(btrim(formula)<>''),
 unit text NOT NULL CHECK(btrim(unit)<>''),
 definition text NOT NULL CHECK(btrim(definition)<>''),
 what_it_tells_us text NOT NULL CHECK(btrim(what_it_tells_us)<>''),
 grain text NOT NULL CHECK(btrim(grain)<>''),
 null_rule text NOT NULL CHECK(btrim(null_rule)<>''),
 lookback_window text NOT NULL,
 minimum_history text NOT NULL,
 caveat text NOT NULL,
 column_kind text NOT NULL CHECK(column_kind IN ('dimension','metric','quality','metadata')),
 display_order integer NOT NULL CHECK(display_order>0),
 source_feature_version text NOT NULL CHECK(source_feature_version ~ '^v[1-9][0-9]*$'),
 source_semantic_hash text NOT NULL CHECK(source_semantic_hash ~ '^[0-9a-f]{64}$'),
 review_status text NOT NULL CHECK(review_status IN ('DRAFT','VERIFIED')),
 validation_evidence text[] NOT NULL CHECK(cardinality(validation_evidence)>0),
 created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 PRIMARY KEY(source_schema,source_table,column_name,language_code),
 CHECK(scope=CASE WHEN right(source_table,6)='_INDEX' THEN 'index' ELSE 'stock' END),
 CHECK(feature_number=substring(source_table FROM '^Feature_([0-9]{2})_')::smallint)
);
COMMENT ON TABLE public."Feature_Vocabulary" IS
 'Reviewed Indonesian frontend dictionary for Feature01/02/03/05/06 stocks and INDEX; one entry per physical source table/column/language. No market data or executable formulas. Feature_Catalog remains semantic authority.';
DO $grant$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='pgweb') THEN GRANT SELECT ON public."Feature_Vocabulary" TO pgweb; END IF;
END $grant$;
INSERT INTO public."Table_Catalog"(table_schema,table_name,category,definition,grain,primary_key_columns,
 source_system,source_tables,source_code_paths,update_rule,documentation_status)
VALUES('public','Feature_Vocabulary','Reference',
 'Reviewed frontend names, formulas, units, definitions and interpretations for physical stock and INDEX Feature01/02/03/05/06 columns; Feature04 excluded.',
 'source_schema × source_table × column_name × language_code',
 ARRAY['source_schema','source_table','column_name','language_code'],
 'Reviewed source-code backed Feature_Catalog and physical schema',ARRAY['Feature_Catalog','Column_Catalog'],
 ARRAY['scripts/build_feature_vocabulary_seed.py','scripts/sync_feature_vocabulary.py','database/feature_vocabulary_seed.json','database/migrations/20261025_003_create_feature_vocabulary.sql'],
 'Explicit schema/semantic release synchronization, never daily price computation. Frontend API and AI onboarding remain separate.', 'VERIFIED')
ON CONFLICT(table_schema,table_name) DO NOTHING;
INSERT INTO public."Column_Catalog"(table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,
 default_expression,is_primary_key,definition,source_column_or_expression,unit,null_rule,source_code_paths,documentation_status)
SELECT 'public','Feature_Vocabulary',c.column_name,c.ordinal_position,c.data_type,c.is_nullable='YES',c.column_default,
 c.column_name=ANY(ARRAY['source_schema','source_table','column_name','language_code']),
 CASE c.column_name
 WHEN 'source_schema' THEN 'Exact schema of the described physical Feature column.'
 WHEN 'source_table' THEN 'Exact physical Feature source table; stock and INDEX definitions stay separate.'
 WHEN 'column_name' THEN 'Exact physical source column name.'
 WHEN 'language_code' THEN 'Language of the presentation text, initially id-ID.'
 WHEN 'feature_number' THEN 'Feature identifier 1,2,3,5 or6; Feature04 excluded.'
 WHEN 'scope' THEN 'stock (legacy non-INDEX tables) or index, derived from the exact source table identity; not an instrument-membership filter.'
 WHEN 'column_name_proper' THEN 'Reviewed readable English field label; acronyms and horizons preserved.'
 WHEN 'formula' THEN 'Display formula or identity rule, never executed as SQL.'
 WHEN 'unit' THEN 'Human-readable unit, distinguishing fraction, percent, percentage points and index points.'
 WHEN 'definition' THEN 'Indonesian explanation of what the source field measures.'
 WHEN 'what_it_tells_us' THEN 'Indonesian analytical interpretation without invented thresholds or prediction.'
 WHEN 'grain' THEN 'Business identity of one source Feature row.'
 WHEN 'null_rule' THEN 'Exact conditions for a legitimate NULL source value.'
 WHEN 'lookback_window' THEN 'Source calculation window in actual observed sessions.'
 WHEN 'minimum_history' THEN 'Minimum valid source history before the metric is available.'
 WHEN 'caveat' THEN 'Scope, source-quality and interpretation limitations.'
 WHEN 'column_kind' THEN 'dimension, metric, quality or metadata.'
 WHEN 'display_order' THEN 'Physical source column ordinal for consistent presentation.'
 WHEN 'source_feature_version' THEN 'Active source Feature_Catalog version at review.'
 WHEN 'source_semantic_hash' THEN 'SHA256 of relevant source semantic fields; detects silent metadata drift.'
 WHEN 'review_status' THEN 'DRAFT or VERIFIED after code-backed review and semantic-hash matching.'
 WHEN 'validation_evidence' THEN 'Nonempty repository evidence paths supporting the reviewed definition.'
 WHEN 'created_at' THEN 'Initial dictionary entry timestamp.'
 WHEN 'updated_at' THEN 'Latest actual entry change timestamp; idempotent sync leaves it unchanged.' END,
 'Reviewed seed and active Feature_Catalog; physical facts from information_schema.',
 CASE WHEN c.data_type='timestamp with time zone' THEN 'timestamp' ELSE 'metadata' END,
 'Never NULL; required metadata.',
 ARRAY['scripts/sync_feature_vocabulary.py','database/migrations/20261025_003_create_feature_vocabulary.sql'],'VERIFIED'
FROM information_schema.columns c WHERE c.table_schema='public' AND c.table_name='Feature_Vocabulary'
ON CONFLICT(table_schema,table_name,column_name) DO NOTHING;
