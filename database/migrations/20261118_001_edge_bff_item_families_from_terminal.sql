-- EDGE multi-user Phase 3b follow-up (EXEC-MU-ACCOUNTS; user decision 2026-11-18, O3b-1: "Pokoknya gate-nya adalah
-- terminal ... Semua indikator yang nantinya akan ditutup di terminal, itu nanti juga tidak ada menu, baik di add
-- screener dan di add backtest juga"; contract verification/edge_multiuser/access_tiers/CONTRACT.md 8b "3b follow-up"):
-- the Terminal's item grants (terminal.indicator, terminal.flow_indicator) decide the indicator and Flow items of the
-- Backtest and the Screener too (apps/edge-bff/app/allow.py FAMILIES), so no tab can differ from the Terminal. The four
-- families edge-bff no longer reads are removed:
--   backtest.indicator, backtest.flow_indicator, screener.indicator, screener.flow_indicator
-- from plan_capabilities (the paid plan's {"stages": ["released"]} rows), user_capability_overrides and capabilities.
-- An override of one of them would be lost silently, so the migration reports how many there are and refuses when
-- there is any (0 on dev on 2026-11-18): move each to terminal.indicator or terminal.flow_indicator first.
-- The paid plan must hold terminal.indicator and terminal.flow_indicator with {"stages": ["released"]} (the seed of
-- 20261117_003), so the paid Backtest and Screener keep every released item. The meaning of those two rows now names
-- the three tabs. candle_pattern (backtest.candle_pattern, screener.candle_pattern) and screener.metric stay.
-- No table, grant, trigger or index changes. Forward-only; it refuses a second run; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
DECLARE
    removed constant text[] := ARRAY['backtest.indicator', 'backtest.flow_indicator', 'screener.indicator',
                                     'screener.flow_indicator'];
    overrides integer;
BEGIN
    IF to_regclass('edge_bff.capabilities') IS NULL
       OR NOT EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key = 'terminal.presets') THEN
        RAISE EXCEPTION 'the EDGE plan catalog of Phase 3a is missing: apply 20261117_003 and 20261117_004 first';
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE capability_key = ANY (removed)) <> 4 THEN
        RAISE EXCEPTION 'the four families of 20261117_003 (%) are not all there: this migration ran already, or the catalog changed; reconcile before applying',
            array_to_string(removed, ', ');
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE capability_key IN ('terminal.indicator', 'terminal.flow_indicator')
        AND kind = 'items') <> 2 THEN
        RAISE EXCEPTION 'terminal.indicator and terminal.flow_indicator (kind items) are missing: reconcile before applying';
    END IF;
    IF (SELECT count(*) FROM edge_bff.plans WHERE plan_key = 'paid') <> 1 THEN
        RAISE EXCEPTION 'the paid plan of 20261117_003 is missing: reconcile before applying';
    END IF;
    SELECT count(*) INTO overrides FROM edge_bff.user_capability_overrides WHERE capability_key = ANY (removed);
    RAISE NOTICE 'user_capability_overrides rows of the removed families: %', overrides;
    IF overrides > 0 THEN
        RAISE EXCEPTION '% user override(s) name a removed family (%): they would be lost. Move each to terminal.indicator or terminal.flow_indicator first',
            overrides, array_to_string(removed, ', ')
            USING HINT = 'SELECT user_id, capability_key, value, reason FROM edge_bff.user_capability_overrides WHERE capability_key IN (''backtest.indicator'', ''backtest.flow_indicator'', ''screener.indicator'', ''screener.flow_indicator'');';
    END IF;
END $preflight$;

DELETE FROM edge_bff.user_capability_overrides
WHERE capability_key IN ('backtest.indicator', 'backtest.flow_indicator', 'screener.indicator', 'screener.flow_indicator');
DELETE FROM edge_bff.plan_capabilities
WHERE capability_key IN ('backtest.indicator', 'backtest.flow_indicator', 'screener.indicator', 'screener.flow_indicator');
DELETE FROM edge_bff.capabilities
WHERE capability_key IN ('backtest.indicator', 'backtest.flow_indicator', 'screener.indicator', 'screener.flow_indicator');

UPDATE edge_bff.capabilities
SET means = 'Which chart indicators the account may use in the Terminal, and so in the Backtest and the Screener too.'
WHERE capability_key = 'terminal.indicator';
UPDATE edge_bff.capabilities
SET means = 'Which Flow (broker and investor flow) indicators the account may use in the Terminal, and so in the Backtest and the Screener too.'
WHERE capability_key = 'terminal.flow_indicator';

DO $verify$
DECLARE
    k text;
BEGIN
    -- no total count: a later migration (20261118_002) adds capabilities; the preflight required the 4 families, and
    -- the check below proves they are gone, so exactly 4 rows left the catalog
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key IN ('backtest.indicator', 'backtest.flow_indicator',
                   'screener.indicator', 'screener.flow_indicator'))
       OR EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key IN ('backtest.indicator',
                   'backtest.flow_indicator', 'screener.indicator', 'screener.flow_indicator'))
       OR EXISTS (SELECT 1 FROM edge_bff.user_capability_overrides WHERE capability_key IN ('backtest.indicator',
                   'backtest.flow_indicator', 'screener.indicator', 'screener.flow_indicator')) THEN
        RAISE EXCEPTION 'a removed family is still in capabilities, plan_capabilities or user_capability_overrides';
    END IF;
    -- the paid plan keeps every released indicator and Flow item, now read by all three tabs from these two rows
    FOREACH k IN ARRAY ARRAY['terminal.indicator', 'terminal.flow_indicator'] LOOP
        IF (SELECT value FROM edge_bff.plan_capabilities WHERE plan_key = 'paid' AND capability_key = k)
           IS DISTINCT FROM '{"stages": ["released"]}'::jsonb THEN
            RAISE EXCEPTION 'the paid plan does not hold % = {"stages": ["released"]}', k;
        END IF;
    END LOOP;
    -- the families that stay: the candlestick patterns per tab and the Screener metrics
    IF (SELECT count(*) FROM edge_bff.plan_capabilities WHERE plan_key = 'paid' AND capability_key IN
            ('backtest.candle_pattern', 'screener.candle_pattern', 'screener.metric')
            AND value = '{"stages": ["released"]}'::jsonb) <> 3 THEN
        RAISE EXCEPTION 'the paid plan lost a candle_pattern or screener.metric grant';
    END IF;
    IF (SELECT count(DISTINCT plan_key) FROM edge_bff.plan_capabilities WHERE capability_key = '*') <> 1 THEN
        RAISE EXCEPTION 'exactly one plan must hold *';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the edge-bff before the 3b follow-up first, whose
-- allow.FAMILIES reads these rows, or keep EDGE_MULTIUSER off: the switch-off principal reads no catalog row):
-- BEGIN;
-- INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name) VALUES
--     ('backtest.indicator', 'items', NULL, 'Which indicators a backtest of the account may use.', 'Backtest indicators'),
--     ('backtest.flow_indicator', 'items', NULL, 'Which Flow indicators a backtest of the account may use.', 'Backtest Flow indicators'),
--     ('screener.indicator', 'items', NULL, 'Which indicators a screen of the account may use.', 'Screener indicators'),
--     ('screener.flow_indicator', 'items', NULL, 'Which Flow indicators a screen of the account may use.', 'Screener Flow indicators');
-- INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
--     ('paid', 'backtest.indicator', '{"stages": ["released"]}'), ('paid', 'backtest.flow_indicator', '{"stages": ["released"]}'),
--     ('paid', 'screener.indicator', '{"stages": ["released"]}'), ('paid', 'screener.flow_indicator', '{"stages": ["released"]}');
-- UPDATE edge_bff.capabilities SET means = 'Which chart indicators the Terminal offers the account.'
-- WHERE capability_key = 'terminal.indicator';
-- UPDATE edge_bff.capabilities SET means = 'Which Flow (broker and investor flow) indicators the Terminal offers the account.'
-- WHERE capability_key = 'terminal.flow_indicator';
-- COMMIT;
