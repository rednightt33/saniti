-- EDGE multi-user Phase 3a (EXEC-MU-ACCOUNTS; decisions D1-D8 of the user 2026-11-17, EXEC.md; contract
-- verification/edge_multiuser/access_tiers/CONTRACT.md 8b "3a in detail"): the catalog rows the edge-bff route gates and
-- saved-item caps read, behind the switch EDGE_MULTIUSER (off until Phase 6; with it off edge-bff reads none of these
-- rows, the switch-off principal of the configured owner holds '*').
--
-- New capabilities (edge_bff.capabilities):
--   admin.manual            flag   the manual troubleshooting model (saniti/claude-manual); no plan row: only '*' holds it
--   terminal.presets        flag   save and reopen indicator presets in the Terminal
--   terminal.layouts_max    limit  saved Terminal layouts per account          (paid 50, app/layouts.py LAYOUT_LIMIT)
--   terminal.presets_max    limit  saved indicator presets per account         (paid 100, app/presets.py PRESET_LIMIT)
--   terminal.drawings_max   limit  places with saved drawings per account      (paid 5000, app/drawings.py SET_LIMIT)
--   screener.saved_items    limit  saved screens, and My metrics, per account  (paid 50, app/screener.py SCREEN_LIMIT)
--   backtest.queued_jobs    limit  backtests waiting in the queue per account  (paid 3, config.py backtest_queued_per_owner)
-- Each limit is read as min(plan value, the module constant): the constant stays the hard ceiling (HARD) no plan or
-- override can raise (app/principal.py Principal.capped). The paid values are today's constants (decision D6).
--
-- The paid plan (decisions D1 and D8: the Monitor is admin only for now) loses monitor.view, monitor.chat and
-- monitor.model and gains monitor.example, terminal.presets and the five limits above. The capability_value_check
-- trigger of 20261117_003 checks every new value against its kind when it is written. Plan keys appear only in the seed
-- migrations (tests/test_plan_catalog.py greps apps/edge-bff/app for them). No table, grant or index changes.
-- Forward-only; rollback block at the end (comment).
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.capabilities') IS NULL OR to_regclass('edge_bff.plan_capabilities') IS NULL
       OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE NOT tgisinternal AND tgname = 'plan_capabilities_value_check') THEN
        RAISE EXCEPTION 'the EDGE plan catalog is missing: apply 20261117_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key IN ('admin.manual', 'terminal.presets',
                   'terminal.layouts_max', 'terminal.presets_max', 'terminal.drawings_max', 'screener.saved_items',
                   'backtest.queued_jobs')) THEN
        RAISE EXCEPTION 'a Phase 3a capability exists already: reconcile before applying';
    END IF;
    IF (SELECT count(*) FROM edge_bff.plans WHERE plan_key = 'paid') <> 1 THEN
        RAISE EXCEPTION 'the paid plan of 20261117_003 is missing: reconcile before applying';
    END IF;
END $preflight$;

-- ---- the new capability rows ------------------------------------------------------------------------------------------
INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name) VALUES
    ('admin.manual', 'flag', NULL, 'Lets the account choose the manual troubleshooting model in the Monitor tab; meant for the operators of EDGE only.', 'Manual agent (troubleshooting)'),
    ('terminal.presets', 'flag', NULL, 'Lets the account save indicator settings as presets in the Terminal and reopen them.', 'Indicator presets'),
    ('terminal.layouts_max', 'limit', 'layouts', 'The most Terminal chart layouts the account may keep.', 'Saved layouts'),
    ('terminal.presets_max', 'limit', 'presets', 'The most indicator presets the account may keep in the Terminal.', 'Saved indicator presets'),
    ('terminal.drawings_max', 'limit', 'places', 'The most chart places (a ticker with its chart, Flow Timeline or pane) that may keep drawings.', 'Places with drawings'),
    ('screener.saved_items', 'limit', 'saved items', 'The most saved screens the account may keep, and as many of its own metrics.', 'Saved screens'),
    ('backtest.queued_jobs', 'limit', 'backtests', 'The most backtests of the account that may wait in the queue at one time.', 'Queued backtests');

-- ---- the paid plan (decisions D1, D6 and D8) --------------------------------------------------------------------------
DELETE FROM edge_bff.plan_capabilities
WHERE plan_key = 'paid' AND capability_key IN ('monitor.view', 'monitor.chat', 'monitor.model');
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('paid', 'monitor.example', 'true'),
    ('paid', 'terminal.presets', 'true'),
    ('paid', 'terminal.layouts_max', '50'),
    ('paid', 'terminal.presets_max', '100'),
    ('paid', 'terminal.drawings_max', '5000'),
    ('paid', 'screener.saved_items', '50'),
    ('paid', 'backtest.queued_jobs', '3');

DO $verify$
DECLARE
    paid constant jsonb := '{"monitor.example": true, "terminal.presets": true, "terminal.layouts_max": 50,
        "terminal.presets_max": 100, "terminal.drawings_max": 5000, "screener.saved_items": 50,
        "backtest.queued_jobs": 3}';
    k text;
BEGIN
    IF (SELECT count(*) FROM edge_bff.capabilities) <> 48 THEN
        RAISE EXCEPTION 'the capabilities differ from the 41 of 20261117_003 plus the 7 of Phase 3a';
    END IF;
    FOR k IN SELECT jsonb_object_keys(paid) LOOP
        IF (SELECT value FROM edge_bff.plan_capabilities WHERE plan_key = 'paid' AND capability_key = k)
           IS DISTINCT FROM paid -> k THEN
            RAISE EXCEPTION 'the paid plan does not hold % = %', k, paid -> k;
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'paid'
               AND capability_key IN ('monitor.view', 'monitor.chat', 'monitor.model')) THEN
        RAISE EXCEPTION 'the paid plan still holds a Monitor capability (decisions D1 and D8: admin only)';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key = 'admin.manual') THEN
        RAISE EXCEPTION 'a plan holds admin.manual: only * may hold it';
    END IF;
    IF (SELECT count(DISTINCT plan_key) FROM edge_bff.plan_capabilities WHERE capability_key = '*') <> 1 THEN
        RAISE EXCEPTION 'exactly one plan must hold *';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE kind = 'limit' AND unit IS NULL) THEN
        RAISE EXCEPTION 'a limit capability has no unit';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; deploy the edge-bff before Phase 3a first, which gates no route on
-- these rows, or keep EDGE_MULTIUSER off: the switch-off principal reads no catalog row):
-- BEGIN;
-- DELETE FROM edge_bff.capabilities WHERE capability_key IN ('admin.manual', 'terminal.presets', 'terminal.layouts_max',
--     'terminal.presets_max', 'terminal.drawings_max', 'screener.saved_items', 'backtest.queued_jobs');  -- cascades
-- DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'paid' AND capability_key = 'monitor.example';
-- INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
--     ('paid', 'monitor.view', 'true'), ('paid', 'monitor.chat', 'true'), ('paid', 'monitor.model', '{"all": true}');
-- COMMIT;
