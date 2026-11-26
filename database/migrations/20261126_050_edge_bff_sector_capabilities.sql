-- EDGE, EXEC-SECTOR-ANALYSIS S3 (the user's go 2026-11-26: "1A 2A 3 go"; decisions UD66 F and J): the Sector Analysis
-- tab's two capabilities, as the Market Overview's (20261117_003, 20261121_002). The user, decision J: "j saat ini hanya
-- main, but later bisa semua pengunjung termasuk free. Untuk free dan guest, which is yang belum login, efeknya akan sama
-- seperti overview, tapi dia bisa cross tab. Dia bisa pilih tab 1, 2, 3, 4, 5. Tapi kalau klik di setiap tab, maka
-- efeknya sama seperti dia mengklik overview."
--
--   sector.view     opens the real tab (edge-bff /api/v1/sector, app/sector.py): the paid plan; the admin through '*'
--   sector.example  its example of one day (edge-bff /api/v1/examples/sector, app/examples.py): the free and the guest
--                   plan, as overview.example
--
-- What it changes where (decision F: the tab is released on main, the live site later on the user's request):
-- - the beta (EDGE_MULTIUSER off): nothing; the configured owner holds '*';
-- - the live site: nothing while `live` runs a commit whose catalog/releases.json does not list the tab `sector`: an
--   unlisted tab is lab there, so principal.beta_only refuses both keys to everyone and live_view drops them;
-- - a site that runs the commit listing `sector` as released: paid accounts open the tab, free accounts and visitors see
--   its example.
-- No data_scope (20261119_030): as overview.view, the tab reads the publisher's page files, not a worker that reads every
-- stock.
--
-- Expand only: two new capabilities and three plan rows; an older edge-bff reads none of them. No grant changes
-- (edge_bff_runtime reads the catalog tables with SELECT). Refuses a second run. Forward-only; rollback block at the end.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '1min';
DO $preflight$
BEGIN
    IF to_regclass('edge_bff.capabilities') IS NULL OR to_regclass('edge_bff.plan_capabilities') IS NULL THEN
        RAISE EXCEPTION 'the EDGE plan catalog is missing: apply 20261117_003 first';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.capabilities WHERE capability_key IN ('sector.view', 'sector.example')) THEN
        RAISE EXCEPTION 'sector.view or sector.example exists: this migration ran already';
    END IF;
    IF (SELECT count(*) FROM edge_bff.plans WHERE plan_key IN ('free', 'paid')) <> 2
       OR NOT EXISTS (SELECT 1 FROM edge_bff.plans WHERE plan_key = 'guest' AND for_guests) THEN
        RAISE EXCEPTION 'the plans free, paid and guest are missing: apply 20261117_003 and 20261119_070 first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'guest' AND capability_key = 'overview.example') THEN
        RAISE EXCEPTION 'the guest plan does not hold overview.example: apply 20261121_002 first';
    END IF;
END $preflight$;

INSERT INTO edge_bff.capabilities(capability_key, kind, unit, means, display_name) VALUES
    ('sector.view', 'flag', NULL, 'Opens the real Sector Analysis tab.', 'Sector Analysis'),
    ('sector.example', 'flag', NULL, 'Shows Sector Analysis as it opens, on the latest market date: its five tabs can be '
     'switched, and every other control asks to sign in or to upgrade.', 'Sector Analysis example');
INSERT INTO edge_bff.plan_capabilities(plan_key, capability_key, value) VALUES
    ('paid', 'sector.view', 'true'),
    ('free', 'sector.example', 'true'),
    ('guest', 'sector.example', 'true');

DO $verify$
BEGIN
    IF (SELECT count(*) FROM edge_bff.capabilities WHERE capability_key IN ('sector.view', 'sector.example')
        AND kind = 'flag' AND data_scope IS NULL) <> 2 THEN
        RAISE EXCEPTION 'verify: sector.view and sector.example are flags without a data scope';
    END IF;
    IF (SELECT array_agg(plan_key || ' ' || capability_key ORDER BY plan_key, capability_key)
        FROM edge_bff.plan_capabilities WHERE capability_key LIKE 'sector.%' AND value = 'true'::jsonb)
       IS DISTINCT FROM ARRAY['free sector.example', 'guest sector.example', 'paid sector.view']
       OR EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key LIKE 'sector.%' AND value <> 'true'::jsonb) THEN
        RAISE EXCEPTION 'verify: the paid plan holds sector.view, the free and the guest plan sector.example, and nothing else of the tab';
    END IF;
    IF EXISTS (SELECT 1 FROM edge_bff.plan_capabilities WHERE plan_key = 'paid' AND capability_key = 'sector.example') THEN
        RAISE EXCEPTION 'verify: the paid plan holds the example (it opens the tab itself)';
    END IF;
    IF to_regprocedure('edge_bff.data_scope_conflicts(text, bigint)') IS NOT NULL
       AND EXISTS (SELECT 1 FROM unnest(ARRAY['paid', 'free', 'guest']) AS p(plan_key)
                   CROSS JOIN LATERAL edge_bff.data_scope_conflicts(p.plan_key, NULL)) THEN
        RAISE EXCEPTION 'verify: a plan given a Sector Analysis flag clashes with the restricted-plan rule (20261119_030)';
    END IF;
END $verify$;
COMMIT;

-- Rollback (a new forward migration with this body; free accounts and visitors then see the locked tab, paid accounts
-- the page "not in your plan"):
-- BEGIN;
-- DELETE FROM edge_bff.user_capability_overrides WHERE capability_key IN ('sector.view', 'sector.example');
-- DELETE FROM edge_bff.plan_capabilities WHERE capability_key IN ('sector.view', 'sector.example');
-- DELETE FROM edge_bff.capabilities WHERE capability_key IN ('sector.view', 'sector.example');
-- COMMIT;
