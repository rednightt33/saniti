-- EXEC-RADAR R4 (user decision 2026-11-14: "1A"): the S6-delta thresholds stay as they are (V1Δ 12 / 20 / 35, V2Δ
-- 40 / 65 / 90 points) and are no longer provisional. Only the label changes: the 9 rule rows of condition D of
-- S6D_RATIO, S6D_RANK and S6D_BOTH become 'decided', and the three filters' warning loses "Thresholds are provisional.".
-- No threshold, result or rule version changes; the publisher's stamp reads these rows and rebuilds radar-meta.
-- The 20-date measurement the user saw before deciding: verification/radar/DEV_RUN.md (median V1Δ 10.4 / 18.2 / 28.6,
-- V2Δ 32.1 / 59.3 / 77.6).
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '1min';

DO $preflight$
DECLARE
    n_rules integer;
    n_filters integer;
BEGIN
    SELECT count(*) INTO n_rules FROM public."Feature_07_Radar_Rule"
    WHERE rule_version = 'radar-v1' AND filter_id IN ('S6D_RATIO', 'S6D_RANK', 'S6D_BOTH') AND cond_key = 'D'
      AND status = 'provisional'
      AND ((filter_id <> 'S6D_RANK' AND threshold = CASE level WHEN 'loose' THEN 12 WHEN 'standard' THEN 20 ELSE 35 END)
        OR (filter_id = 'S6D_RANK' AND threshold = CASE level WHEN 'loose' THEN 40 WHEN 'standard' THEN 65 ELSE 90 END))
      AND (filter_id <> 'S6D_BOTH' OR threshold2 = CASE level WHEN 'loose' THEN 40 WHEN 'standard' THEN 65 ELSE 90 END);
    SELECT count(*) INTO n_filters FROM public."Feature_07_Radar_Filter"
    WHERE rule_version = 'radar-v1' AND filter_id IN ('S6D_RATIO', 'S6D_RANK', 'S6D_BOTH')
      AND warning LIKE '% Thresholds are provisional.';
    IF n_rules <> 9 OR n_filters <> 3 THEN
        RAISE EXCEPTION 'expected 9 provisional S6-delta rule rows with the approved thresholds and 3 warnings, found % and %',
            n_rules, n_filters;
    END IF;
END
$preflight$;

UPDATE public."Feature_07_Radar_Rule" SET status = 'decided'
WHERE rule_version = 'radar-v1' AND filter_id IN ('S6D_RATIO', 'S6D_RANK', 'S6D_BOTH') AND cond_key = 'D'
  AND status = 'provisional';

UPDATE public."Feature_07_Radar_Filter" SET warning = replace(warning, ' Thresholds are provisional.', '')
WHERE rule_version = 'radar-v1' AND filter_id IN ('S6D_RATIO', 'S6D_RANK', 'S6D_BOTH');

DO $verify$
BEGIN
    IF EXISTS (SELECT 1 FROM public."Feature_07_Radar_Rule" WHERE status = 'provisional') THEN
        RAISE EXCEPTION 'a provisional rule row is left';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Feature_07_Radar_Filter" WHERE warning LIKE '%provisional%') THEN
        RAISE EXCEPTION 'a provisional warning is left';
    END IF;
END
$verify$;

COMMIT;
