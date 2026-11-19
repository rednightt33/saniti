-- EDGE multi-user, re-check of Phases 0-3b, fix round (EXEC-MU-ACCOUNTS; track terminal, finding R1-22;
-- verification/edge_multiuser/fix_round/terminal.md): a value domain per capability, held by the catalog and checked by
-- capability_value_check when a plan or an override value is written, behind the switch EDGE_MULTIUSER (off until
-- Phase 6; with it off edge-bff reads none of these rows).
--
-- Why: Phase 2 checked a value against its kind only (a limit: any non-negative integer; a list: any array of strings),
-- while the services that carry a value take a narrower one. terminal-api's x-terminal-capabilities takes history_days
-- 0 to 36600 and tickers ^[A-Z0-9]{1,12}$ (apps/terminal-api/app/entitlements.py), and edge-bff's header is at most
-- 8 KiB. A value the catalog took but the wire did not (history_days 40000, a ticker 'bbca') failed every Terminal call
-- of the account. edge-bff now maps every value onto the wire (app/terminal_access.py capabilities: clamp, drop, refuse
-- first), because a value read back as the most restrictive one (0, []) still reaches it; this migration lets the admin
-- see the rule when writing, so such a value is never stored.
--
-- New columns of edge_bff.capabilities (NULL: no bound beyond the kind):
--   value_min, value_max  limit: the smallest and largest value; list: the fewest and most items
--   item_pattern          list: a POSIX regular expression every item matches
-- capability_value_check (replaced, same shape checks and messages as 20261117_003) reads them after the shape check and
-- refuses a value outside them with a hint that names the domain and an example (AGENTS.md "Gates and evidence").
-- capability_domain_holds refuses a change of a domain that a stored value would no longer fit.
--
-- Domains set here (the wire's own bounds; tests/test_terminal_fix_round.py compares them with terminal-api's code):
--   terminal.history_days       1 .. 36600 days (0 serves nothing dated: a plan without history holds no dated dataset)
--   terminal.tickers            0 .. 500 items, each ^[A-Z0-9]{1,12}$ (500 names of 12 characters fit the 8 KiB header)
--   terminal.tickers_per_hour, terminal.tickers_per_day, terminal.files_per_hour, terminal.megabytes_per_day
--                               1 .. 1000000000 (terminal-api's MAX_QUOTA; a plan that allows none holds no terminal.view)
-- Every other capability keeps no domain beyond its kind (a later migration may set one, for example a saved-item limit's
-- HARD as its value_max). No table grant or index changes (edge_bff_runtime reads the catalog tables with SELECT); the
-- two pure helper functions the value trigger calls are executable by edge_bff_runtime, which writes overrides. Refuses a
-- second run and a stored value outside a new domain (it names them). Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.capabilities') IS NULL
       OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgname = 'plan_capabilities_value_check') THEN
        RAISE EXCEPTION 'the EDGE plan catalog is missing: apply 20261117_003 first';
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE capability_key IN ('terminal.history_days', 'terminal.tickers',
            'terminal.tickers_per_hour', 'terminal.tickers_per_day', 'terminal.files_per_hour',
            'terminal.megabytes_per_day')) <> 6 THEN
        RAISE EXCEPTION 'a Terminal capability of 20261117_003 or 20261118_002 is missing: apply 20261118_002 first';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'edge_bff' AND table_name = 'capabilities'
               AND column_name IN ('value_min', 'value_max', 'item_pattern')) THEN
        RAISE EXCEPTION 'edge_bff.capabilities already has a value domain: reconcile before applying';
    END IF;
END $preflight$;

ALTER TABLE edge_bff.capabilities
    ADD COLUMN value_min bigint,
    ADD COLUMN value_max bigint,
    ADD COLUMN item_pattern text,
    ADD CONSTRAINT capabilities_domain_kind CHECK ((kind IN ('limit', 'list') OR (value_min IS NULL AND value_max IS NULL))
                                                   AND (kind = 'list' OR item_pattern IS NULL)),
    ADD CONSTRAINT capabilities_domain_bounds CHECK ((value_min IS NULL OR value_min >= 0)
                                                     AND (value_max IS NULL OR value_max >= coalesce(value_min, 0))),
    ADD CONSTRAINT capabilities_item_pattern CHECK (item_pattern IS NULL OR char_length(item_pattern) BETWEEN 1 AND 200);
COMMENT ON COLUMN edge_bff.capabilities.value_min IS 'The smallest value a plan or an override may hold (limit), or the fewest items (list); NULL: no bound beyond the kind. Checked by capability_value_check when a value is written.';
COMMENT ON COLUMN edge_bff.capabilities.value_max IS 'The largest value a plan or an override may hold (limit), or the most items (list); NULL: no bound beyond the kind. Checked by capability_value_check when a value is written.';
COMMENT ON COLUMN edge_bff.capabilities.item_pattern IS 'A POSIX regular expression every item of a list value matches (list only); NULL: any string. Checked by capability_value_check when a value is written.';

-- the domain of one capability, as a sentence for the hint
CREATE FUNCTION edge_bff.capability_domain_text(k text, lo bigint, hi bigint, pat text) RETURNS text
    LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $fn$
    SELECT CASE k
        WHEN 'limit' THEN 'a whole number from ' || coalesce(lo, 0)::text || coalesce(' to ' || hi::text, ' up')
        WHEN 'list' THEN 'a list of ' || coalesce(lo, 0)::text || coalesce(' to ' || hi::text, ' or more') || ' items'
                         || coalesce(', each matching ' || pat, '')
        ELSE 'a value of its kind' END
$fn$;
REVOKE ALL ON FUNCTION edge_bff.capability_domain_text(text, bigint, bigint, text) FROM PUBLIC;

-- whether a value of the right shape fits a domain (NULL bounds: none)
CREATE FUNCTION edge_bff.capability_domain_fits(v jsonb, k text, lo bigint, hi bigint, pat text) RETURNS boolean
    LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, pg_temp AS $fn$
    SELECT CASE k
        WHEN 'limit' THEN (lo IS NULL OR v::text::numeric >= lo) AND (hi IS NULL OR v::text::numeric <= hi)
        WHEN 'list' THEN (lo IS NULL OR jsonb_array_length(v) >= lo) AND (hi IS NULL OR jsonb_array_length(v) <= hi)
                         AND (pat IS NULL OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text(v) e WHERE e !~ pat))
        ELSE true END
$fn$;
REVOKE ALL ON FUNCTION edge_bff.capability_domain_fits(jsonb, text, bigint, bigint, text) FROM PUBLIC;
-- the value trigger runs as the role that writes (edge_bff_runtime writes overrides, Phase 4): both helpers are pure
GRANT EXECUTE ON FUNCTION edge_bff.capability_domain_fits(jsonb, text, bigint, bigint, text),
    edge_bff.capability_domain_text(text, bigint, bigint, text) TO edge_bff_runtime;

-- the value check of 20261117_003, with the domain after the shape (the shape refusal and its hint are unchanged)
CREATE OR REPLACE FUNCTION edge_bff.capability_value_check() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    k text;
    lo bigint;
    hi bigint;
    pat text;
    v jsonb := NEW.value;
    ok boolean;
BEGIN
    SELECT kind, value_min, value_max, item_pattern INTO k, lo, hi, pat FROM edge_bff.capabilities
        WHERE capability_key = NEW.capability_key;
    ok := CASE k
        WHEN 'flag' THEN v IN ('true'::jsonb, 'false'::jsonb)
        WHEN 'limit' THEN jsonb_typeof(v) = 'number' AND v::text ~ '^[0-9]+$'
        WHEN 'list' THEN jsonb_typeof(v) = 'array'
            AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v) e WHERE jsonb_typeof(e) <> 'string')
        WHEN 'items' THEN jsonb_typeof(v) = 'object'
            AND NOT EXISTS (SELECT 1 FROM jsonb_object_keys(v) x WHERE x NOT IN ('ids', 'stages', 'all'))
            AND (NOT v ? 'ids' OR (jsonb_typeof(v -> 'ids') = 'array'
                 AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v -> 'ids') e WHERE jsonb_typeof(e) <> 'string')))
            AND (NOT v ? 'stages' OR (jsonb_typeof(v -> 'stages') = 'array'
                 AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v -> 'stages') e
                                 WHERE e NOT IN ('"lab"'::jsonb, '"released"'::jsonb))))
            AND (NOT v ? 'all' OR jsonb_typeof(v -> 'all') = 'boolean')
        ELSE false END;
    IF NOT coalesce(ok, false) THEN
        RAISE EXCEPTION 'edge_bff.%: the value % does not fit capability % (kind %)', TG_TABLE_NAME, v, NEW.capability_key,
            coalesce(k, 'unknown')
            USING HINT = 'flag: true or false; limit: a non-negative integer such as 730; list: an array of strings '
                         'such as ["BBCA"]; items: {"ids": ["I01"], "stages": ["released"], "all": false}, each key optional';
    END IF;
    IF NOT edge_bff.capability_domain_fits(v, k, lo, hi, pat) THEN
        RAISE EXCEPTION 'edge_bff.%: the value % is outside the domain of capability %', TG_TABLE_NAME, v,
            NEW.capability_key
            USING HINT = NEW.capability_key || ' takes ' || edge_bff.capability_domain_text(k, lo, hi, pat)
                         || ' (edge_bff.capabilities value_min, value_max, item_pattern). Example: '
                         || CASE k WHEN 'limit' THEN coalesce(lo, 0)::text ELSE '["BBCA"]' END || '.';
    END IF;
    RETURN NEW;
END $fn$;
COMMENT ON FUNCTION edge_bff.capability_value_check() IS 'Refuses a plan_capabilities or user_capability_overrides value that does not fit its capability kind (flag true/false, limit non-negative integer, list of strings, items {ids, stages lab/released, all}; C1 Phase 2 F1) or its domain (capabilities value_min, value_max, item_pattern; re-check R1-22).';

-- a domain cannot change while a stored value would no longer fit it (the values were checked against the old one)
CREATE FUNCTION edge_bff.capability_domain_holds() RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    found text;
BEGIN
    SELECT string_agg(x.who || ' ' || x.value::text, ', ') INTO found FROM (
        SELECT 'plan ' || plan_key AS who, value FROM edge_bff.plan_capabilities WHERE capability_key = NEW.capability_key
        UNION ALL
        SELECT 'user ' || user_id, value FROM edge_bff.user_capability_overrides WHERE capability_key = NEW.capability_key
    ) x WHERE NOT edge_bff.capability_domain_fits(x.value, NEW.kind, NEW.value_min, NEW.value_max, NEW.item_pattern);
    IF found IS NOT NULL THEN
        RAISE EXCEPTION 'edge_bff.capabilities: % values of % fall outside its new domain: %', NEW.capability_key,
            NEW.capability_key, found
            USING HINT = 'Change those values to fit ' || edge_bff.capability_domain_text(NEW.kind, NEW.value_min,
                         NEW.value_max, NEW.item_pattern) || ' in the same migration, then the domain.';
    END IF;
    RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION edge_bff.capability_domain_holds() FROM PUBLIC;
CREATE TRIGGER capabilities_domain_holds BEFORE INSERT OR UPDATE OF value_min, value_max, item_pattern
    ON edge_bff.capabilities FOR EACH ROW EXECUTE FUNCTION edge_bff.capability_domain_holds();
COMMENT ON FUNCTION edge_bff.capability_domain_holds() IS 'Refuses a capabilities domain (value_min, value_max, item_pattern) that a stored plan or override value of the capability would not fit; re-check R1-22.';

-- the domains of the wire's capabilities (refused here, naming them, when a stored value lies outside)
UPDATE edge_bff.capabilities SET value_min = 1, value_max = 36600 WHERE capability_key = 'terminal.history_days';
UPDATE edge_bff.capabilities SET value_min = 0, value_max = 500, item_pattern = '^[A-Z0-9]{1,12}$'
    WHERE capability_key = 'terminal.tickers';
UPDATE edge_bff.capabilities SET value_min = 1, value_max = 1000000000
    WHERE capability_key IN ('terminal.tickers_per_hour', 'terminal.tickers_per_day', 'terminal.files_per_hour',
                             'terminal.megabytes_per_day');

DO $verify$
DECLARE
    want constant jsonb := '{"terminal.history_days": [1, 36600, null], "terminal.tickers": [0, 500, "^[A-Z0-9]{1,12}$"],
        "terminal.tickers_per_hour": [1, 1000000000, null], "terminal.tickers_per_day": [1, 1000000000, null],
        "terminal.files_per_hour": [1, 1000000000, null], "terminal.megabytes_per_day": [1, 1000000000, null]}';
    k text;
    bad text;
BEGIN
    FOR k IN SELECT jsonb_object_keys(want) LOOP
        IF (SELECT jsonb_build_array(value_min, value_max, item_pattern) FROM edge_bff.capabilities
            WHERE capability_key = k) IS DISTINCT FROM want -> k THEN
            RAISE EXCEPTION 'the domain of % is not %', k, want -> k;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key NOT IN (SELECT jsonb_object_keys(want))
               AND (value_min IS NOT NULL OR value_max IS NOT NULL OR item_pattern IS NOT NULL)) THEN
        RAISE EXCEPTION 'a capability other than the six of this migration has a domain';
    END IF;
    SELECT string_agg(x.capability_key || ' ' || x.value::text, ', ') INTO bad FROM (
        SELECT capability_key, value FROM edge_bff.plan_capabilities
        UNION ALL SELECT capability_key, value FROM edge_bff.user_capability_overrides) x
        JOIN edge_bff.capabilities c USING (capability_key)
        WHERE NOT edge_bff.capability_domain_fits(x.value, c.kind, c.value_min, c.value_max, c.item_pattern);
    IF bad IS NOT NULL THEN
        RAISE EXCEPTION 'stored values outside their domain: %', bad;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgname = 'capabilities_domain_holds')
       OR (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('plan_capabilities_value_check',
               'user_capability_overrides_value_check')) <> 2 THEN
        RAISE EXCEPTION 'the value and domain triggers are not all in place';
    END IF;
    IF NOT edge_bff.capability_domain_fits('730', 'limit', 1, 36600, NULL)
       OR edge_bff.capability_domain_fits('0', 'limit', 1, 36600, NULL)
       OR edge_bff.capability_domain_fits('40000', 'limit', 1, 36600, NULL)
       OR NOT edge_bff.capability_domain_fits('["BBCA", "BBRI"]', 'list', 0, 500, '^[A-Z0-9]{1,12}$')
       OR edge_bff.capability_domain_fits('["bbca"]', 'list', 0, 500, '^[A-Z0-9]{1,12}$')
       OR edge_bff.capability_domain_fits('[" BBCA"]', 'list', 0, 500, '^[A-Z0-9]{1,12}$') THEN
        RAISE EXCEPTION 'capability_domain_fits does not hold its own examples';
    END IF;
    IF NOT has_function_privilege('edge_bff_runtime', 'edge_bff.capability_domain_fits(jsonb, text, bigint, bigint, text)',
                                  'EXECUTE')
       OR has_function_privilege('public', 'edge_bff.capability_domain_holds()', 'EXECUTE') THEN
        RAISE EXCEPTION 'the domain functions do not have the privileges of this migration';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; edge-bff keeps mapping every value onto the wire without it):
-- BEGIN;
-- DROP TRIGGER capabilities_domain_holds ON edge_bff.capabilities;
-- DROP FUNCTION edge_bff.capability_domain_holds();
-- (CREATE OR REPLACE edge_bff.capability_value_check with the body of 20261117_003)
-- DROP FUNCTION edge_bff.capability_domain_fits(jsonb, text, bigint, bigint, text),
--     edge_bff.capability_domain_text(text, bigint, bigint, text);
-- ALTER TABLE edge_bff.capabilities DROP COLUMN value_min, DROP COLUMN value_max, DROP COLUMN item_pattern;
-- COMMIT;
