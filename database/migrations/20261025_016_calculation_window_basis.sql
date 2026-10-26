-- EXEC-M209 step 1 (user 2026-10-23: "...data-nya harus di-disclose kepada user bahwa ini adalah hari di mana saham
-- tersebut bertransaksi instead of hari kerja"; go 2026-10-25 EXEC-GO-1025 item 6): a structured window on every
-- stored Feature calculation whose lookback reads several observations.
--
-- parameters.window_basis  ENTITY_SESSIONS (the entity's own rows: the dates it traded or has a row), EXCHANGE_DAYS or
--                          CALENDAR_DAYS; every value set here is ENTITY_SESSIONS, read from each Feature's code:
--                          F01 ROWS BETWEEN n PRECEDING per ticker ordered by date (20260912_001), F02 ticker
--                          transaction dates, F04 the ticker's valid OHLCV bars (features/feature04/engine.py
--                          _segments), F06 the ticker's sessions (refresh_feature_06); the INDEX tables clone the same
--                          writers (scripts/backfill_index_features.py clone_writer, feature04 calculate).
-- parameters.window_length the number of observations the value reads: the first number of lookback_window
--                          ("20 sessions" 20; "20 current + 252 prior complete ticker-date observations" 20; "257
--                          sessions" 257). Only lookbacks of two or more get a window; "1 session", "Current trading
--                          observation" and cumulative text ("all sessions") are left without one.
-- Derived from lookback_window, not typed per row, so a new Feature row is covered by the same rule (the onboarding
-- guide requires these two fields for a new windowed column). Shown by get_catalog_details COLUMNS (window) and read
-- by the system's window-basis line (apps/market-ai-orc/app/tools/catalog.py WINDOWED_COLUMNS_SQL).
BEGIN;

UPDATE public."AI_calculation_catalog" k
SET parameters = k.parameters || jsonb_build_object(
        'window_basis', 'ENTITY_SESSIONS',
        'window_length', substring(k.parameters ->> 'lookback_window' FROM '\d+')::int),
    updated_at = now()
WHERE k.status = 'ACTIVE'
  AND k.target_table IN ('Feature_01_Stock_Daily', 'Feature_01_Stock_Daily_INDEX',
                         'Feature_02_Broker_Rolling', 'Feature_02_Broker_Rolling_INDEX',
                         'Feature_04_Technical_Indicator', 'Feature_04_Technical_Indicator_INDEX',
                         'Feature_06_Foreign_Domestic_Stock', 'Feature_06_Foreign_Domestic_INDEX')
  AND substring(k.parameters ->> 'lookback_window' FROM '\d+')::int >= 2
  AND NOT k.parameters ? 'window_basis';

DO $check$ DECLARE missing int; wrong int; BEGIN
 -- every active numbered lookback of two or more in a verified Feature table has its window
 SELECT count(*) INTO missing FROM public."AI_calculation_catalog" k
 WHERE k.status = 'ACTIVE' AND k.target_table LIKE 'Feature\_0_\_%'
   AND k.target_table NOT LIKE 'Feature\_03%' AND k.target_table NOT LIKE 'Feature\_05%'
   AND substring(k.parameters ->> 'lookback_window' FROM '\d+')::int >= 2 AND NOT k.parameters ? 'window_basis';
 IF missing > 0 THEN RAISE EXCEPTION '% windowed calculations lack window_basis', missing; END IF;
 -- no one-observation or daily calculation got a window
 SELECT count(*) INTO wrong FROM public."AI_calculation_catalog" k
 WHERE k.parameters ? 'window_basis'
   AND (coalesce(substring(k.parameters ->> 'lookback_window' FROM '\d+')::int, 0) < 2
        OR (k.parameters ->> 'window_length')::int <> substring(k.parameters ->> 'lookback_window' FROM '\d+')::int);
 IF wrong > 0 THEN RAISE EXCEPTION '% calculations have a window that does not match their lookback', wrong; END IF;
END $check$;

COMMIT;
