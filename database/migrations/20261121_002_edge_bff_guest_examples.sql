-- EDGE multi-user, 3e, the example mode as the user set it on 2026-11-21 (EXEC.md option A; ERRORS M527): a visitor who
-- is not signed in sees each data page as it opens, like the free plan: "Kalau dia klik tombol, maka untuk user yang
-- belum login, akan muncul login box ... Begitupun untuk radar, watchlist, screener, dan backtest", and the latest
-- Market Overview (the user's "A", 2026-11-21). The guest plan (20261119_070) gets the five example flags the free plan
-- holds since 20261117_003, and their descriptions say what each example now is.
--
-- Apply order (EXEC.md, the user's go of 2026-11-21: "the plans' rows applied when the live site runs the code that
-- reads them"): after 20261121_001 and after the live site runs the edge-bff that serves /api/v1/examples. An older
-- edge-bff reads no <tab>.example key, so these rows change nothing it shows; the plans are data both sites share.
--
-- Expand only: five new plan_capabilities rows and new texts of five capabilities.means (read only for display). No
-- grant changes. The example flags are not data_scope every_stock (20261119_030): an example is a fixed set of files
-- served by edge-bff, not a worker that reads every stock, so the guest plan's Terminal limits stand beside them.
-- Refuses a second run. Forward-only; rollback block at the end.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.example_files') IS NULL THEN
        RAISE EXCEPTION 'edge_bff.example_files is missing: apply 20261121_001 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM edge_bff.plans WHERE plan_key = 'guest' AND for_guests) THEN
        RAISE EXCEPTION 'the guest plan is missing: apply 20261119_070 first';
    END IF;
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE kind = 'flag' AND data_scope IS NULL AND capability_key IN
        ('overview.example', 'radar.example', 'watchlist.example', 'screener.example', 'backtest.example')) <> 5 THEN
        RAISE EXCEPTION 'the five example flags are not all flags without a data scope: reconcile before applying';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key LIKE '%.example') THEN
        RAISE EXCEPTION 'the guest plan holds an example flag already: this migration ran already';
    END IF;
END $preflight$;

INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('guest', 'overview.example', 'true'),
    ('guest', 'radar.example', 'true'),
    ('guest', 'watchlist.example', 'true'),
    ('guest', 'screener.example', 'true'),
    ('guest', 'backtest.example', 'true');

UPDATE edge_bff.capabilities SET means = CASE capability_key
    WHEN 'overview.example' THEN 'Shows the Market Overview as it opens, on the latest market date: the index and group '
        'filter and the choices that are not time work, and every time control asks to sign in or to upgrade.'
    WHEN 'radar.example' THEN 'Shows the Radar as it opens, with the data of one past date (scrolling only); every click '
        'asks to sign in or to upgrade.'
    WHEN 'watchlist.example' THEN 'Shows the Watchlist as it opens, with one example list and the data of one past date '
        '(scrolling only); every click asks to sign in or to upgrade.'
    WHEN 'screener.example' THEN 'Shows the Screener as it opens, with one preset and its results on one past date '
        '(scrolling only); every click asks to sign in or to upgrade.'
    WHEN 'backtest.example' THEN 'Shows the Backtest as it opens, with its default setup run on the data up to one past '
        'date (scrolling only); every click asks to sign in or to upgrade.'
    END
WHERE capability_key IN ('overview.example', 'radar.example', 'watchlist.example', 'screener.example', 'backtest.example');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND value = 'true'::jsonb AND capability_key IN
        ('overview.example', 'radar.example', 'watchlist.example', 'screener.example', 'backtest.example')) <> 5
       OR (SELECT count(*) FROM edge_bff.plan_capabilities WHERE plan_key = 'guest') <> 10 THEN
        RAISE EXCEPTION 'verify: the guest plan holds its five Terminal grants and the five example flags, and nothing else';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'guest'
               AND (capability_key IN ('*', 'monitor.example', 'terminal.example')
                    OR (capability_key LIKE '%.view' AND capability_key <> 'terminal.view'))) THEN
        RAISE EXCEPTION 'verify: the guest plan holds a tab''s view (other than the Terminal), * or another example';
    END IF;
    IF to_regprocedure('edge_bff.data_scope_conflicts(text, bigint)') IS NOT NULL
       AND EXISTS (SELECT 1 FROM edge_bff.data_scope_conflicts('guest', NULL)) THEN
        RAISE EXCEPTION 'verify: the guest plan clashes with the restricted-plan rule (20261119_030)';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key IN ('overview.example', 'radar.example',
               'watchlist.example', 'screener.example', 'backtest.example') AND means LIKE '%no live data%') THEN
        RAISE EXCEPTION 'verify: an example flag still says it shows no live data';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; visitors then see the locked pages again):
-- BEGIN;
-- DELETE FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key IN
--     ('overview.example', 'radar.example', 'watchlist.example', 'screener.example', 'backtest.example');
-- COMMIT;
