#!/usr/bin/env python3
"""EXEC-RADAR R8: one source for the Feature 07 (Radar) catalog rows and the field dictionary.

  python scripts/generate_feature_07_catalog.py migration > database/migrations/20261114_002_catalog_feature_07_radar.sql
  python scripts/generate_feature_07_catalog.py dictionary > FEATURE_07_RADAR.md
  python scripts/generate_feature_07_catalog.py check      # every column of the CREATE TABLEs has exactly one entry

The measure, gate and result tables are Feature tables: every column gets an active Feature_Catalog v1 row
(scripts/audit_feature_catalog_semantics.py requires it) and a Column_Catalog row. The filter and rule tables hold the
Radar's labels and thresholds (Reference): Column_Catalog rows only. Every table gets a Table_Catalog row. The tables are
not exposed to the AI (no onboarding, NEW_TABLE_ONBOARDING_PLAN.md): readers are terminal_market_reader (publisher)
and pgweb_reader.
"""
from __future__ import annotations

import sys
from pathlib import Path

MIGRATION = "20261114_001_feature_07_radar.sql"
M = "Feature_07_Radar_Measure"
G = "Feature_07_Radar_Gate"
F = "Feature_07_Radar_Filter"
R = "Feature_07_Radar_Rule"
RES = "Feature_07_Radar_Result"
EVIDENCE = [f"database/migrations/{MIGRATION}", "verification/radar/validate_radar.py", "verification/radar/REHEARSAL.md",
            "FEATURE_07_RADAR.md", "SCREENER_LIBRARY.md", "DATABASE_CHANGELOG.md"]
SESSION = ("ticker sessions as Feature 06: the dates on which the ticker traded on any board; a session without a "
           "Regular trade counts zero on the Regular board")
REFRESH_M = ("refresh_feature_07(ticker, first changed date) after refresh_feature_06; reads the 400 sessions before; "
             "stockbit-updater refresh_radar at the end of a broker round")
REFRESH_D = "refresh_feature_07_day(date) for every date from the first changed one, in date order"
OWN = ("own-history rank: 100 x (previous values strictly below today's) / 252 over the ticker's 252 previous "
       "sessions; NULL unless 252 complete values (EXEC-RADAR D1)")
XS = "100 x (other stocks of the population strictly below) / (population - 1); NULL for a population of one"


# the reader's words for each column group, mapped onto the categories Feature_Catalog accepts
# (Feature_Catalog_feature_category_check, read live 2026-11-14)
CATEGORY = {"Identity": "Identity", "Window": "Metadata", "Universe": "Metadata", "Result": "Metadata",
            "Foreign Flow": "Broker Flow", "Liquidity": "Volume", "Broker Class Flow": "Broker Classification",
            "Cross Section": "Broker Abnormality", "Broker Concentration": "Broker Concentration",
            "Data Quality": "Data Quality"}


def col(name, category, definition, calculation, unit, null_rule, *, lookback="1 session", minimum="1 session",
        role="MEASURE", aggs=("AVG", "MEDIAN", "MIN", "MAX", "COUNT", "PERCENTILE"), ranking="CONTEXTUAL",
        filterable=True, groupable=False, use=None, misuse=None, source=None):
    assert category in CATEGORY, category
    assert role in ("IDENTITY", "DIMENSION", "MEASURE") and ranking in ("HIGHER", "LOWER", "CONTEXTUAL", "NOT_APPLICABLE")
    return dict(name=name, category=CATEGORY[category], group=category, definition=definition, calculation=calculation, unit=unit,
                null_rule=null_rule, lookback=lookback, minimum=minimum, role=role, aggs=list(aggs), ranking=ranking,
                filterable=filterable, groupable=groupable, source=source,
                use=use or "Read per ticker and date as the Radar's own measure; compare a ticker with its own history "
                           "or with other tickers on the same date.",
                misuse=misuse or "Regular board only: not comparable with Nego or Tunai flows; not a buy signal.")


IDENT = dict(role="IDENTITY", aggs=("COUNT", "COUNT_DISTINCT"), ranking="NOT_APPLICABLE", groupable=True)
SUMS = ("SUM", "AVG", "MEDIAN", "MIN", "MAX", "COUNT", "PERCENTILE")
FLAG = dict(role="DIMENSION", aggs=("COUNT",), ranking="NOT_APPLICABLE", groupable=True)
RANK = dict(role="MEASURE", ranking="HIGHER")
F06S = "Feature_06_Foreign_Domestic"
F03S = "Feature_03_Stock_Broker_Daily"
F05S = "Feature_05_Foreign_Domestic_Broker_Detail"


def measure_columns():
    w5 = dict(lookback="5 sessions", minimum="5 sessions")
    b252 = dict(lookback="252 previous sessions", minimum="257 sessions")
    return [
        col("trade_date", "Identity", "Exchange trading date of a Regular session of the ticker.", f"{F06S}.trade_date",
            "date", "Never NULL.", **IDENT, source=F06S),
        col("ticker", "Identity", "Stock code (IDX_Stock_Universe tickers are the Radar's universe).", f"{F06S}.ticker",
            "code", "Never NULL.", **IDENT, source=F06S),
        col("s5_from", "Window", "First date of the ticker's own 5-session window ending on trade_date.",
            "trade_date of the session 4 sessions before (" + SESSION + ")", "date", "NULL until 5 sessions.",
            role="IDENTITY", aggs=("COUNT",), ranking="NOT_APPLICABLE", **{k: v for k, v in w5.items()}, source=F06S),
        col("foreign_net_1d", "Foreign Flow", "Regular foreign net buy value of the day (N); positive is net buying.",
            "foreign_buy_1d - foreign_sell_1d of the Regular row", "IDR", "Never NULL.", aggs=SUMS, source=F06S),
        col("total_buy_1d", "Liquidity", "Regular buy value of all investors on the day (TBV).",
            "foreign_buy_1d + domestic_buy_1d of the Regular row", "IDR", "Never NULL.", aggs=SUMS, source=F06S),
        col("total_buy_5d", "Liquidity", "G3 liquidity measure: Regular buy value of all investors over the ticker's "
            "5 sessions.", "sum of total_buy_1d over 5 sessions (zero on a session without a Regular trade)", "IDR",
            "NULL until 5 sessions.", aggs=SUMS, **w5, source=F06S),
        col("foreign_net_5d", "Foreign Flow", "Regular foreign net buy value over 5 sessions; positive is net buying.",
            "sum of foreign_net_1d over 5 sessions", "IDR", "NULL until 5 sessions.", aggs=SUMS, **w5, source=F06S),
        col("foreign_ratio_5d", "Foreign Flow", "S6 V1: foreign net as a percent of all Regular buying over 5 "
            "sessions (equals Feature 06 foreign_net_turnover_ratio_5d of the Regular row).",
            "100 x foreign_net_5d / total_buy_5d", "percent", "NULL until 5 sessions or when total_buy_5d is 0.", **w5,
            source=F06S),
        col("buy_days_5d", "Foreign Flow", "S1 persistence: sessions with a positive foreign net among the 5.",
            "count(foreign_net_1d > 0) over 5 sessions", "sessions", "NULL until 5 sessions.", **w5, source=F06S),
        col("foreign_net_5d_pct252", "Foreign Flow", "S1: rank of foreign_net_5d in the ticker's own year.", OWN,
            "percentile", "NULL without 252 previous 5-session values.", **RANK, **b252, source=F06S),
        col("foreign_net_5d_z252", "Foreign Flow", "S1 Strict: z-score of foreign_net_5d against the 252 previous "
            "values (sample standard deviation, as Feature 06).", "(foreign_net_5d - mean) / stddev_samp of the 252 "
            "previous foreign_net_5d", "z", "NULL without 252 previous values or when their deviation is 0.", **b252,
            source=F06S),
        col("foreign_ratio_5d_pct252", "Foreign Flow", "S6 V2: rank of foreign_ratio_5d in the ticker's own year; "
            "sessions without a ratio are skipped (A1).", OWN.replace("previous sessions", "previous sessions that "
            "have a ratio"), "percentile", "NULL without 252 previous ratios.", **RANK, **b252, source=F06S),
        col("foreign_ratio_5d_prev", "Foreign Flow", "The 5-session ratio five sessions before: the previous, "
            "non-overlapping block.", "foreign_ratio_5d of the session 5 sessions before", "percent",
            "NULL until 10 sessions or when that block had no Regular buying.", lookback="10 sessions",
            minimum="10 sessions", source=F06S),
        col("foreign_ratio_5d_change", "Foreign Flow", "S2 and S6-delta V1: change of the 5-session ratio against "
            "the previous block, in percentage points.", "foreign_ratio_5d - foreign_ratio_5d_prev", "points",
            "NULL when either ratio is NULL.", lookback="10 sessions", minimum="10 sessions", source=F06S),
        col("foreign_ratio_5d_pct252_prev", "Foreign Flow", "foreign_ratio_5d_pct252 five sessions before.",
            "foreign_ratio_5d_pct252 of the session 5 sessions before", "percentile", "NULL when that rank is NULL.",
            **RANK, lookback="257 previous sessions", minimum="262 sessions", source=F06S),
        col("foreign_ratio_5d_pct252_change", "Foreign Flow", "S6-delta V2: change of the own-year rank against five "
            "sessions before, in points.", "foreign_ratio_5d_pct252 - foreign_ratio_5d_pct252_prev", "points",
            "NULL when either rank is NULL.", lookback="257 previous sessions", minimum="262 sessions", source=F06S),
        col("foreign_net_5d_max_day", "Data Quality", "Largest one-day foreign net in the 5 sessions (one-day block "
            "note, D6).", "max(foreign_net_1d) over 5 sessions", "IDR", "NULL until 5 sessions.", **w5, source=F06S),
        col("foreign_net_5d_max_date", "Data Quality", "Date of foreign_net_5d_max_day (the latest one on a tie).",
            "trade_date of the largest foreign_net_1d in the window", "date", "NULL until 5 sessions.",
            role="IDENTITY", aggs=("COUNT",), ranking="NOT_APPLICABLE", **w5, source=F06S),
        col("inst_net_5d", "Broker Class Flow", "S7: net buy value of institution-class brokers over 5 sessions.",
            f"sum of {F03S}.institutional_net_value (Regular) over 5 sessions", "IDR", "NULL until 5 sessions or when a Regular session of the window has no Feature 03 row.",
            aggs=SUMS, **w5, source=F03S, misuse="Broker class describes each broker's usual clients, not the "
            "investor of each trade; one broker can make up the whole side. Regular board only."),
        col("retail_net_5d", "Broker Class Flow", "S7: net buy value of retail-class brokers over 5 sessions.",
            f"sum of {F03S}.retail_net_value (Regular) over 5 sessions", "IDR",
            "NULL until 5 sessions or when a Regular session of the window has no Feature 03 row.", aggs=SUMS,
            **w5, source=F03S, misuse="Broker class describes each broker's usual clients, not the investor of each "
            "trade. Regular board only."),
        col("fl34_5d", "Broker Class Flow", "S7 FL34 over 5 sessions: institution net minus retail net as a percent "
            "of all broker buying.", f"100 x (inst_net_5d - retail_net_5d) / sum of {F03S}.total_buy_value over 5 "
            "sessions", "percent",
            "NULL until 5 sessions, when the broker buying is 0, or when a Regular session of the window has no Feature 03 row.",
            **w5, source=F03S),
        col("fl34_5d_prev", "Broker Class Flow", "fl34_5d five sessions before (previous block).",
            "fl34_5d of the session 5 sessions before", "percent", "NULL until 10 sessions.", lookback="10 sessions",
            minimum="10 sessions", source=F03S),
        col("inst_share_5d", "Broker Class Flow", "S7 D: institution net as a percent of all broker buying over 5 "
            "sessions.", f"100 x inst_net_5d / sum of {F03S}.total_buy_value over 5 sessions", "percent",
            "NULL until 5 sessions, when the broker buying is 0, or when a Regular session of the window has no Feature 03 row.",
            **w5, source=F03S),
        col("inst_buy_days_5d", "Broker Class Flow", "Sessions with a positive institution net among the 5.",
            f"count({F03S}.institutional_net_value > 0) over 5 sessions", "sessions",
            "NULL until 5 sessions or when a Regular session of the window has no Feature 03 row.", **w5,
            source=F03S),
        col("adv20_prev", "Liquidity", "S8 ADV20: mean total_buy_1d of the 20 sessions before the day (the day "
            "excluded).", "avg(total_buy_1d) over the 20 previous sessions", "IDR", "NULL until 21 sessions.",
            lookback="20 previous sessions", minimum="21 sessions", source=F06S),
        col("foreign_ratio_1d", "Foreign Flow", "S8 U1: foreign net of the day as a percent of the day's buying.",
            "100 x foreign_net_1d / total_buy_1d", "percent", "NULL when total_buy_1d is 0.", source=F06S),
        col("net_vs_adv20", "Foreign Flow", "S8 U3 (x): foreign net of the day as a percent of ADV20.",
            "100 x foreign_net_1d / adv20_prev", "percent", "NULL until 21 sessions or when ADV20 is 0.",
            lookback="20 previous sessions", minimum="21 sessions", source=F06S),
        col("rz_foreign_ratio_1d", "Foreign Flow", "S8 trigger: robust z of foreign_ratio_1d against the ticker's "
            "252 previous sessions.", "(value - median) / (1.4826 x MAD) of the non-NULL previous values "
            "(feature_07_robust_z)", "robust z", "NULL with fewer than 200 previous values or MAD 0.",
            lookback="252 previous sessions", minimum="201 sessions", source=F06S),
        col("rz_net_vs_adv20", "Foreign Flow", "S8 trigger: robust z of net_vs_adv20 against the ticker's 252 "
            "previous sessions.", "(value - median) / (1.4826 x MAD) of the non-NULL previous values", "robust z",
            "NULL with fewer than 200 previous values or MAD 0.", lookback="252 previous sessions",
            minimum="221 sessions", source=F06S),
        col("net_1d_pct252", "Foreign Flow", "S8 guard 2: rank of foreign_net_1d in the ticker's own 252 previous "
            "sessions.", OWN, "percentile", "NULL without 252 previous sessions.", **RANK,
            lookback="252 previous sessions", minimum="253 sessions", source=F06S),
        col("g2_eligible", "Universe", "G2: universe stock with at least 5 Regular sessions in the last 16 market "
            "dates and a full 5-session window.", "ticker in IDX_Stock_Universe and count of its rows among the last "
            "16 dates >= 5 and total_buy_5d IS NOT NULL", "flag", "false before the date's refresh_feature_07_day.",
            **FLAG, lookback="16 market dates", source=M),
        col("gate_broad", "Universe", "G3 Broad: in G2 and total_buy_5d at or above the date's median (top 50%).",
            f"total_buy_5d >= {G}.broad_cut", "flag", "false outside G2.", **FLAG, source=M),
        col("gate_liquid", "Universe", "G3 Liquid: in G2 and total_buy_5d at or above the date's P80 (top 20%).",
            f"total_buy_5d >= {G}.liquid_cut", "flag", "false outside G2.", **FLAG, source=M),
        col("s2_rank_broad", "Cross Section", "S2: rank of foreign_ratio_5d_change among Broad stocks with a positive "
            "foreign_net_5d.", XS, "percentile", "NULL outside that population.", **RANK, source=M),
        col("s2_rank_liquid", "Cross Section", "S2: the same rank among Liquid stocks.", XS, "percentile",
            "NULL outside that population.", **RANK, source=M),
        col("s3_net_buyers", "Broker Concentration", "S3 k: brokers with a positive net over the ticker's 5 sessions "
            "(Regular, investor types summed).", f"count of brokers with sum({F05S}.buy_value - sell_value) > 0",
            "brokers", "NULL outside Broad or without broker rows.", **w5, source=F05S),
        col("s3_cr3", "Broker Concentration", "S3 CR3: share of the three largest net buyers in all net buying.",
            "sum of the 3 largest broker nets / sum of the positive broker nets", "ratio",
            "NULL outside Broad or without a net buyer.", **w5, source=F05S),
        col("s3_cr3_excess", "Broker Concentration", "S3 concentration: CR3 above an even split.",
            "s3_cr3 - 3 / s3_net_buyers", "ratio", "NULL when s3_cr3 is NULL.", **w5, source=F05S),
        col("s3_intensity", "Broker Concentration", "S3 intensity: net buying of the net buyers as a share of all "
            "broker gross buying.", f"sum of the positive broker nets / sum({F05S}.buy_value) of all brokers", "ratio",
            "NULL outside Broad or when the gross buying is 0.", **w5, source=F05S),
        col("s3_group_broad", "Cross Section", "S3 group of k among Broad stocks with k >= 10 (0 to 4; quintile edges "
            "of k, a value of k never split).", "count of the 4 linear quintile edges of k strictly below k",
            "group", "NULL outside that population.", **FLAG, source=M),
        col("s3_group_rank_broad", "Cross Section", "S3 B: rank of s3_cr3_excess inside its k group (Broad).", XS,
            "percentile", "NULL outside that population.", **RANK, source=M),
        col("s3_intensity_rank_broad", "Cross Section", "S3 C: rank of s3_intensity among Broad stocks with k >= 10.",
            XS, "percentile", "NULL outside that population.", **RANK, source=M),
        col("s3_group_liquid", "Cross Section", "S3 group of k among Liquid stocks with k >= 10.",
            "count of the 4 linear quintile edges of k strictly below k", "group", "NULL outside that population.",
            **FLAG, source=M),
        col("s3_group_rank_liquid", "Cross Section", "S3 B: rank of s3_cr3_excess inside its k group (Liquid).", XS,
            "percentile", "NULL outside that population.", **RANK, source=M),
        col("s3_intensity_rank_liquid", "Cross Section", "S3 C: rank of s3_intensity among Liquid stocks with k >= 10.",
            XS, "percentile", "NULL outside that population.", **RANK, source=M),
        col("calculated_at", "Data Quality", "When refresh_feature_07 wrote the row (the date's cross-section columns "
            "are written later by refresh_feature_07_day).", "statement_timestamp() at insert", "timestamp",
            "Never NULL.", role="IDENTITY", aggs=("MIN", "MAX", "COUNT"), ranking="NOT_APPLICABLE", source=M,
            use="Operational freshness check only.", misuse="Not a market time; do not use as an observation date."),
    ]


def gate_columns():
    g = dict(source=M, use="Read the date's universe size and Broad/Liquid cut-offs next to the Radar results.",
             misuse="Cut-offs are relative and change every day; they are not a liquidity standard in rupiah.")
    return [
        col("trade_date", "Identity", "Result date.", f"{M}.trade_date", "date", "Never NULL.", **IDENT,
            **{k: v for k, v in g.items() if k == 'source'}),
        col("universe_n", "Universe", "G2 universe size of the date.", "count of g2_eligible rows", "stocks",
            "Never NULL.", aggs=("AVG", "MIN", "MAX"), **g),
        col("broad_cut", "Universe", "G3 Broad cut-off: median of total_buy_5d over the G2 universe.",
            "percentile_cont(0.5) of total_buy_5d", "IDR", "NULL with an empty universe.", **g),
        col("liquid_cut", "Universe", "G3 Liquid cut-off: P80 of total_buy_5d over the G2 universe.",
            "percentile_cont(0.8) of total_buy_5d", "IDR", "NULL with an empty universe.", **g),
        col("broad_n", "Universe", "Stocks in Broad.", "count of gate_broad rows", "stocks", "Never NULL.",
            aggs=("AVG", "MIN", "MAX"), **g),
        col("liquid_n", "Universe", "Stocks in Liquid.", "count of gate_liquid rows", "stocks", "Never NULL.",
            aggs=("AVG", "MIN", "MAX"), **g),
        col("calculated_at", "Data Quality", "When refresh_feature_07_day wrote the row.", "statement_timestamp()",
            "timestamp", "Never NULL.", role="IDENTITY", aggs=("MIN", "MAX", "COUNT"), ranking="NOT_APPLICABLE",
            source=M, use="Operational freshness check only.", misuse="Not a market time."),
    ]


def result_columns():
    r = dict(source=f"{M}, {R}", use="Read one date, filter, level and gate as the Radar board shows it.",
             misuse="A hit is a candidate to examine, not a recommendation; thresholds marked provisional in "
                    f"{R}.status may change.")
    return [
        col("trade_date", "Identity", "Result date.", f"{M}.trade_date", "date", "Never NULL.", **IDENT, source=M),
        col("filter_id", "Identity", "Filter: S1, S2, S3, S6, S6D_RATIO, S6D_RANK, S6D_BOTH, S7, S8.",
            f"{F}.filter_id", "code", "Never NULL.", **IDENT, source=F),
        col("level", "Identity", "Threshold level: loose, standard, strict (S8: standard only, its own levels).",
            f"{R}.level", "category", "Never NULL.", **IDENT, source=R),
        col("gate", "Identity", "Liquidity gate: broad or liquid.", "G3 gate", "category", "Never NULL.", **IDENT,
            source=M),
        col("ticker", "Identity", "Stock code.", f"{M}.ticker", "code", "Never NULL.", **IDENT, source=M),
        col("status", "Result", "hit: every condition met (S8: A and B); near: every condition but one met and not a "
            "hit the date before; left: a hit on the previous result date that is not one now.", "rule evaluation of "
            f"{R} against {M}", "category", "Never NULL.", **FLAG, **r),
        col("met", "Result", "Conditions met as a bitmask: 1 = A, 2 = B, 4 = C, 8 = D.", "sum of the bits of the met "
            "conditions", "bitmask", "NULL for left when the stock is outside the gate or has no data.", **FLAG, **r),
        col("cond_n", "Result", "Number of conditions of the filter.", f"count of {R} rows of the filter and level",
            "conditions", "Never NULL (0 for left without data).", **FLAG, **r),
        col("run_day", "Result", "Hits: consecutive result dates the stock has been a hit in this filter, level and "
            "gate.", "previous result date's run_day + 1, else 1", "result dates", "NULL for near and left.",
            ranking="HIGHER", **r),
        col("left_reason", "Result", "Left: the first condition no longer met (A-D), 'gate' (outside the gate) or "
            "'no_data' (no Regular session).", "first unset bit of met", "category", "NULL unless status = left.",
            **FLAG, **r),
        col("strong", "Result", "S8 hits: true = Strong (all three checks), false = Watch.", "condition C of S8",
            "flag", "NULL unless an S8 hit.", **FLAG, **r),
        col("sort_value", "Result", "The filter's sort key (RADAR_PAGE_SPEC.md section 5, D3): S1 z, S2 and S6D_RATIO "
            "and S6D_BOTH ratio change, S3 mean of the two ranks, S6 ratio, S6D_RANK rank change, S7 FL34, S8 the "
            "larger robust z.", f"the filter's column of {M}", "filter unit", "NULL when that column is NULL.",
            ranking="HIGHER", **r),
        col("flag", "Result", "Outlier note (D6): a one-day block (one day >= 80% of a positive 5-session foreign net, "
            "on S1, S2, S6 and S6-delta) and a corporate action inside the stock's 5 sessions.",
            "text from foreign_net_5d_max_day and idx_event_annotation CORPORATE_ACTION", "text", "NULL without a "
            "note; not written for left.", **FLAG, **r),
        col("rule_version", "Identity", "Version of the rules that produced the row.", "feature_07_rule_version()",
            "code", "Never NULL.", **IDENT, source=R),
        col("calculated_at", "Data Quality", "When refresh_feature_07_day wrote the row.", "statement_timestamp()",
            "timestamp", "Never NULL.", role="IDENTITY", aggs=("MIN", "MAX", "COUNT"), ranking="NOT_APPLICABLE",
            source=RES, use="Operational freshness check only.", misuse="Not a market time."),
    ]


def reference_columns():
    """Column_Catalog only: (table, column, definition, unit, null rule)."""
    return [
        (F, "rule_version", "Rule version.", "code", "Never NULL."),
        (F, "filter_id", "Filter id (S6-delta is stored as three: S6D_RATIO, S6D_RANK, S6D_BOTH).", "code", "Never NULL."),
        (F, "position", "Order on the board.", "position", "Never NULL."),
        (F, "column_id", "Board column the filter belongs to (S6D_* share S6D).", "code", "Never NULL."),
        (F, "column_label", "Column heading.", "text", "Never NULL."),
        (F, "variant_label", "S6-delta variant: Ratio, Rank, Both.", "text", "NULL for single-variant filters."),
        (F, "is_default_variant", "The variant a column shows first.", "flag", "Never NULL."),
        (F, "name", "Filter name (English, the page's wording).", "text", "Never NULL."),
        (F, "question", "What the filter asks (shown on the page).", "text", "Never NULL."),
        (F, "warning", "How to read it: the filter's reading warning.", "text", "Never NULL."),
        (F, "sort_label", "Name of the sort key.", "text", "Never NULL."),
        (F, "own_levels", "true for S8 (Strong/Watch instead of Loose/Standard/Strict).", "flag", "Never NULL."),
        (R, "rule_version", "Rule version.", "code", "Never NULL."),
        (R, "filter_id", "Filter id.", "code", "Never NULL."),
        (R, "cond_key", "Condition A, B, C or D.", "code", "Never NULL."),
        (R, "level", "loose, standard or strict (S8: standard only).", "category", "Never NULL."),
        (R, "label", "Condition text shown on the page, with the level's threshold.", "text", "Never NULL."),
        (R, "threshold", "The condition's threshold at the level.", "condition unit", "Never NULL."),
        (R, "threshold2", "Second threshold (S1 Strict z; S6D_BOTH rank change).", "condition unit",
         "NULL when the condition has one threshold."),
        (R, "status", "decided, or provisional (S6-delta D thresholds until R4 of EXEC-RADAR, option C).", "category",
         "Never NULL."),
    ]


def table_order(table: str) -> list[str]:
    text = (Path(__file__).resolve().parent.parent / "database" / "migrations" / MIGRATION).read_text()
    body = text.split(f'CREATE TABLE public."{table}" (', 1)[1]
    names = []
    for ln in body.splitlines()[1:]:
        s = ln.strip()
        if s.startswith(")"):
            break
        if not s or s.startswith("--") or s.split()[0] in ("CONSTRAINT", "PRIMARY", "FOREIGN"):
            continue
        names.append(s.split()[0])
    return names


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def arr(v):
    return "ARRAY[" + ",".join(q(x) for x in v) + "]::text[]"


FEATURE_TABLES = ((M, measure_columns, "Date x ticker (Regular sessions)"),
                  (G, gate_columns, "Date"),
                  (RES, result_columns, "Date x filter x level x gate x ticker"))
PKS = {M: ["ticker", "trade_date"], G: ["trade_date"], F: ["rule_version", "filter_id"],
       R: ["rule_version", "filter_id", "cond_key", "level"], RES: ["trade_date", "filter_id", "level", "gate", "ticker"]}


def check() -> list[str]:
    problems = []
    for t, cols, _ in FEATURE_TABLES:
        want, have = table_order(t), [c["name"] for c in cols()]
        if want != have:
            problems.append(f"{t}: table {want} vs catalog {have}")
    for t in (F, R):
        want, have = table_order(t), [c for tt, c, *_ in reference_columns() if tt == t]
        if want != have:
            problems.append(f"{t}: table {want} vs catalog {have}")
    return problems


def migration() -> str:
    out = ["-- EXEC-RADAR R8: catalog rows of the Radar tables, generated by scripts/generate_feature_07_catalog.py.",
           "BEGIN;", "SET LOCAL lock_timeout = '10s';", ""]
    paths = [f"database/migrations/{MIGRATION}", "apps/stockbit-updater/refresh.py", "verification/radar/backfill_job.py"]
    funcs = ["refresh_feature_07(text,date)", "refresh_feature_07_day(date)",
             "feature_07_below_percentile(double precision,double precision[],integer)",
             "feature_07_robust_z(double precision,double precision[],integer)", "feature_07_rule_version()"]
    tables = [
        (M, "Feature", "Radar measures per universe ticker and Regular session: the 5-session foreign flow, its "
         "changes and own-year ranks, broker-class flow, broker concentration, the one-day spike, and the date's "
         "universe, gates and cross-stock ranks (SCREENER_LIBRARY.md filters S1, S2, S3, S6, S6-delta, S7, S8).",
         "One row per Regular session of a universe ticker", "Features 03, 05 and 06",
         [F06S, F03S, F05S, "IDX_Stock_Universe"], REFRESH_M),
        (G, "Feature", "Per result date, the G2 universe size and the Broad/Liquid cut-offs of 5-session Regular "
         "buying.", "One row per result date", "Feature 07 measures", [M], REFRESH_D),
        (F, "Reference", "The Radar's filters: board column, English name, question, reading warning and sort key, "
         "per rule version.", "One row per rule version and filter", "Migration (user decisions in EXEC-RADAR)", [],
         "Changed only by a migration with a new rule version"),
        (R, "Reference", "Every condition of every Radar filter with its threshold per level and its English label; "
         "the only place a threshold lives.", "One row per rule version, filter, condition and level",
         "Migration (user decisions in EXEC-RADAR)", [], "Changed only by a migration with a new rule version"),
        (RES, "Feature", "Per result date, filter, level and gate: the stocks that pass (hit), miss one condition "
         "(near) or no longer pass (left), with the met conditions, run of days, sort value and outlier note.",
         "One row per result date, filter, level, gate and listed ticker", "Feature 07 measures and rules",
         [M, F, R, "idx_event_annotation"], REFRESH_D),
    ]
    for (t, cat, d, grain, sys_, src, rule) in tables:
        out.append(f"""INSERT INTO public."Table_Catalog" (table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths, update_rule, related_functions,
    documentation_status, readiness_mode, readiness_date_column, observation_date_column, availability_rule,
    point_in_time_status, historical_metadata_method)
VALUES ('public', {q(t)}, {q(cat)}, {q(d)}, {q(grain)}, {arr(PKS[t])}, {q(sys_)}, {arr(src)}, {arr(paths)}, {q(rule)},
    {arr(funcs)}, 'VERIFIED', {q('DATA_DATE' if cat == 'Feature' else 'REFERENCE_STATE')},
    {q('trade_date' if cat == 'Feature' else None)}, {q('trade_date' if cat == 'Feature' else None)},
    {q('Only through the last broker round that ran the Radar step; Regular board only.' if cat == 'Feature' else 'Static per rule version.')},
    {q('AVAILABLE' if cat == 'Feature' else 'NOT_APPLICABLE')},
    'IDX_Stock_Universe is read as of each refresh (current universe), not as of the trade date.');
""")
    for t, cols, grain in FEATURE_TABLES:
        for x in cols():
            out.append(f"""INSERT INTO public."Column_Catalog" (table_schema, table_name, column_name, ordinal_position,
    data_type, is_nullable, is_primary_key, definition, source_column_or_expression, unit, null_rule,
    source_code_paths, documentation_status)
SELECT 'public', {q(t)}, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES',
    {str(x['name'] in PKS[t]).lower()},
    {q(x['definition'])}, 'Feature_Catalog active semantic version', {q(x['unit'])}, {q(x['null_rule'])},
    {arr(EVIDENCE[:3])}, 'VERIFIED'
FROM information_schema.columns c WHERE c.table_schema = 'public' AND c.table_name = {q(t)} AND c.column_name = {q(x['name'])};
""")
            out.append(f"""INSERT INTO public."Feature_Catalog" (feature_table, feature_column, grain, feature_category,
    definition, calculation, source_tables, source_columns, lookback_window, minimum_history, unit, null_rule,
    refresh_trigger, dependency_rule, version, is_active, semantic_role, allowed_aggregations, ranking_interpretation,
    is_filterable, is_groupable, availability_rule, point_in_time_safe, historical_metadata_warning,
    analytical_interpretation, recommended_use, misuse_warning, semantic_review_status, validation_evidence)
VALUES ({q(t)}, {q(x['name'])}, {q(grain)}, {q(x['category'])}, {q(x['definition'])}, {q(x['calculation'])},
    {q(x['source'] or M)}, {q((x['source'] or M) + ' columns per calculation')}, {q(x['lookback'])}, {q(x['minimum'])},
    {q(x['unit'])}, {q(x['null_rule'])}, {q(REFRESH_M if t == M and x['source'] not in (M,) else REFRESH_D)},
    {q('Requires Features 03, 05 and 06 refreshed for the same dates')},
    'v1', true, {q(x['role'])}, {arr(x['aggs'])}, {q(x['ranking'])}, {str(x['filterable']).lower()},
    {str(x['groupable']).lower()}, {q('Use only through the last broker round that ran the Radar step.')}, true,
    {q('The universe is IDX_Stock_Universe as of the refresh, not as of the trade date.')}, {q(x['definition'])},
    {q(x['use'])}, {q(x['misuse'])}, 'CALCULATION_VERIFIED', {arr(EVIDENCE)});
""")
    order = {t: table_order(t) for t in (F, R)}
    for (t, c, d, unit, null_rule) in reference_columns():
        out.append(f"""INSERT INTO public."Column_Catalog" (table_schema, table_name, column_name, ordinal_position,
    data_type, is_nullable, is_primary_key, definition, source_column_or_expression, unit, null_rule,
    source_code_paths, documentation_status)
SELECT 'public', {q(t)}, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES', {str(c in PKS[t]).lower()},
    {q(d)}, {q('migration ' + MIGRATION)}, {q(unit)}, {q(null_rule)}, {arr(EVIDENCE[:1])}, 'VERIFIED'
FROM information_schema.columns c WHERE c.table_schema = 'public' AND c.table_name = {q(t)} AND c.column_name = {q(c)};
""")
        assert c in order[t], (t, c)
    out.append("COMMIT;")
    return "\n".join(out)


def dictionary() -> str:
    lines = ["# Feature 07: Radar measures, gates and results", "",
             "Generated by `scripts/generate_feature_07_catalog.py` (EXEC-RADAR). The same text is in "
             "`Feature_Catalog` v1 and `Column_Catalog`. Filters and their wording: "
             "`verification/radar/RADAR_PAGE_SPEC.md`; definitions and worked examples: `SCREENER_LIBRARY.md`.", "",
             "Sessions: " + SESSION + ". A window is NULL until it is full; a ratio with a zero denominator is NULL. "
             "Own-history ranks: " + OWN + ". Cross-stock ranks: " + XS + ".", ""]
    for t, cols, grain in FEATURE_TABLES:
        cs = cols()
        lines += [f"## `{t}` ({len(cs)} columns; grain: {grain})", "",
                  "| Column | Category | Definition | Formula | Unit | NULL rule | Minimum history |",
                  "|---|---|---|---|---|---|---|"]
        for x in cs:
            cells = [f"`{x['name']}`", x["group"], x["definition"], x["calculation"], x["unit"], x["null_rule"],
                     x["minimum"]]
            lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in cells) + " |")
        lines.append("")
    for t in (F, R):
        lines += [f"## `{t}`", "", "| Column | Definition | Unit | NULL rule |", "|---|---|---|---|"]
        for (tt, c, d, unit, null_rule) in reference_columns():
            if tt == t:
                lines.append(f"| `{c}` | {d} | {unit} | {null_rule} |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "dictionary"
    if what == "check":
        p = check()
        print("\n".join(p) if p else "OK")
        sys.exit(1 if p else 0)
    sys.stdout.write((migration() if what == "migration" else dictionary()).rstrip("\n") + "\n")
