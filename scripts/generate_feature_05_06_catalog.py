#!/usr/bin/env python3
"""EXEC-F05-F06: one source for the Feature 05/06 catalog rows and the field dictionary.

  python scripts/generate_feature_05_06_catalog.py migration > database/migrations/<file>.sql
  python scripts/generate_feature_05_06_catalog.py dictionary > FEATURE_05_06_FOREIGN_DOMESTIC.md

Every column of both Feature tables gets an active Feature_Catalog v1 row (scripts/audit_feature_catalog_semantics.py
requires it), a Column_Catalog row, and both tables a Table_Catalog row; IDX_Broker_Summary gets Column_Catalog rows
for buy_freq/sell_freq and sync_broker_summary_freq in related_functions; Feature 05 -> Feature 06 is registered in
Feature_Relationship_Catalog. IDX_Broker_Summary_Freq and IDX_Net_Foreign_Summary stay unregistered (their loader is
outside this repository; open item since 2026-10-20).
"""
from __future__ import annotations

import sys

F05 = "Feature_05_Foreign_Domestic_Broker_Detail"
F06 = "Feature_06_Foreign_Domestic"
PK = {"Feature_05_Foreign_Domestic_Broker_Detail": {"ticker", "trade_date", "broker", "investor_type", "market_board"},
      "Feature_06_Foreign_Domestic": {"ticker", "market_board", "trade_date"}}
EVIDENCE = ["database/migrations/20261022_002_create_feature_05_foreign_domestic_broker_detail.sql",
            "database/migrations/20261022_003_create_feature_06_foreign_domestic.sql",
            "scripts/check_feature_06_sample.py", "FEATURE_05_06_FOREIGN_DOMESTIC.md", "DATABASE_CHANGELOG.md"]
SESSION = ("ticker sessions: the dates on which the ticker has any Feature 05 row on any board (as Feature 02); a "
           "board that did not trade in a session counts zero")
WARMUP = "NULL until the ticker has {n} sessions"
REFRESH_05 = "refresh_feature_05(date range, tickers) after sync_broker_summary_freq for the same dates"
REFRESH_06 = "refresh_feature_06(ticker, first changed date) after refresh_feature_05; reads 312 prior sessions"
GAP_NOTE = ("2016 to August 2020 rows with source_balance_gap = true come from a source that lacks some brokers "
            "(ERRORS M157); their foreign and domestic nets do not sum to zero")


def col(name, ftype, category, definition, calculation, unit, null_rule, *, lookback="1 session", minimum="1 session",
        role="MEASURE", aggs=("AVG", "MEDIAN", "MIN", "MAX", "COUNT", "PERCENTILE"), ranking="CONTEXTUAL",
        filterable=True, groupable=False, interpretation=None, use=None, misuse=None):
    return dict(name=name, type=ftype, category=category, definition=definition, calculation=calculation, unit=unit,
                null_rule=null_rule, lookback=lookback, minimum=minimum, role=role, aggs=list(aggs), ranking=ranking,
                filterable=filterable, groupable=groupable, interpretation=interpretation or definition,
                use=use or "Compare within the same ticker and board over time, or across tickers on the same date.",
                misuse=misuse or "Do not compare across boards or sum across boards.")


IDENT = dict(role="IDENTITY", aggs=("COUNT", "COUNT_DISTINCT"), ranking="NOT_APPLICABLE", groupable=True)
SUMS = ("SUM", "AVG", "MEDIAN", "MIN", "MAX", "COUNT", "PERCENTILE")


def f05_columns():
    c = [
        col("trade_date", "date", "Identity", "Exchange trading date of the source row.", 'IDX_Broker_Summary."Date"',
            "date", "Never NULL.", **IDENT),
        col("ticker", "text", "Identity", "Source Symbol, including warrants and rights.", 'IDX_Broker_Summary."Symbol"',
            "code", "Never NULL; exact source symbol.", **IDENT),
        col("broker", "text", "Identity", "Two-character broker code.", 'IDX_Broker_Summary."Broker"', "code",
            "Never NULL.", **IDENT),
        col("market_board", "text", "Identity", "Source board: Regular, Nego or Tunai.", 'IDX_Broker_Summary."Market Board"',
            "category", "Never NULL; boards are never implicitly combined.", **IDENT),
        col("investor_type", "text", "Identity", "Source investor identity: Foreign or Domestic, not broker domicile.",
            'IDX_Broker_Summary."Investor Type"', "category", "Never NULL.", **IDENT),
        col("buy_value", "numeric", "Broker Flow", "Gross buy value.", 'IDX_Broker_Summary."Buy Value"', "IDR",
            "Never NULL.", aggs=SUMS),
        col("sell_value", "numeric", "Broker Flow", "Gross sell value.", 'IDX_Broker_Summary."Sell Value"', "IDR",
            "Never NULL.", aggs=SUMS),
        col("net_value", "numeric", "Broker Flow", "Net buy value; positive is net buying, negative net selling.",
            "buy_value - sell_value", "IDR", "Never NULL.", aggs=SUMS),
        col("buy_lots", "numeric", "Volume", "Lots bought (1 lot = 100 shares; odd lots as fractions).",
            'IDX_Broker_Summary."Buy Lots"', "lots", "Never NULL.", aggs=SUMS),
        col("sell_lots", "numeric", "Volume", "Lots sold (1 lot = 100 shares; odd lots as fractions).",
            'IDX_Broker_Summary."Sell Lots"', "lots", "Never NULL.", aggs=SUMS),
        col("net_lots", "numeric", "Volume", "Net lots; positive is net buying.", "buy_lots - sell_lots", "lots",
            "Never NULL.", aggs=SUMS),
        col("buy_freq", "bigint", "Volume", "Number of buy transactions.", "IDX_Broker_Summary.buy_freq "
            "(from IDX_Broker_Summary_Freq.buy_freq)", "transactions",
            "NULL when the source has no frequency (non-4-letter symbols); never replaced by zero.", aggs=SUMS),
        col("sell_freq", "bigint", "Volume", "Number of sell transactions.", "IDX_Broker_Summary.sell_freq "
            "(from IDX_Broker_Summary_Freq.sell_freq)", "transactions",
            "NULL when the source has no frequency (non-4-letter symbols); never replaced by zero.", aggs=SUMS),
        col("source_balance_gap", "boolean", "Data Quality", "Internal: total buy value over all brokers differs from "
            "total sell value for this date, ticker and board in the source (ERRORS M157).",
            "SUM(Buy Value) <> SUM(Sell Value) over IDX_Broker_Summary rows of the date, ticker and board", "flag",
            "Never NULL.", aggs=("COUNT",), ranking="NOT_APPLICABLE", groupable=True,
            use="Internal data-quality filter; not exposed to the AI.",
            misuse="Not a market signal; do not show it to users as one."),
        col("calculated_at", "timestamptz", "Metadata", "Statement timestamp when the row was written.",
            "statement_timestamp()", "timestamp", "Never NULL.", role="DIMENSION", aggs=("MIN", "MAX", "COUNT"),
            ranking="NOT_APPLICABLE", use="Operational audit of refreshes only.",
            misuse="Not source time and not data availability time."),
    ]
    for x in c:
        x["source"] = "IDX_Broker_Summary"
        x["minimum"] = "1 source row"
        if x["category"] in ("Broker Flow", "Volume"):
            x["misuse"] = ("Investor type is the source investor, not the broker's domicile; do not mix boards. "
                           + GAP_NOTE + ".")
            x["use"] = "Base metric for Feature 06 and broker-level questions on one ticker, date and board."
    return c


def f06_columns():
    c = []
    ident = [("trade_date", "date", "Trading date on which this board of the ticker traded."),
             ("ticker", "text", "Source symbol (Feature 05 ticker)."),
             ("market_board", "text", "Source board: Regular, Nego or Tunai; no ALL board (user decision).")]
    for n, t, d in ident:
        c.append(col(n, t, "Identity", d, f"Feature 05 {n}", "date" if t == "date" else "code",
                     "Never NULL; boards are never implicitly combined." if n == "market_board" else "Never NULL.",
                     **IDENT))
    daily = [("foreign_buy_1d", "Foreign buy value", "FB = SUM(buy_value) WHERE investor_type = Foreign"),
             ("foreign_sell_1d", "Foreign sell value", "FS = SUM(sell_value) WHERE investor_type = Foreign"),
             ("foreign_net_1d", "Foreign net value; positive is net buying", "F = FB - FS"),
             ("domestic_buy_1d", "Domestic buy value", "DB = SUM(buy_value) WHERE investor_type = Domestic"),
             ("domestic_sell_1d", "Domestic sell value", "DS = SUM(sell_value) WHERE investor_type = Domestic"),
             ("domestic_net_1d", "Domestic net value; positive is net buying", "D = DB - DS")]
    for n, d, calc in daily:
        c.append(col(n, "numeric", "Broker Flow", d + " for the ticker, date and board.", calc + " over Feature 05",
                     "IDR", "Never NULL; zero when that investor type did not trade.", aggs=SUMS))
    for p, sym in (("foreign", "F"), ("domestic", "D")):
        c.append(col(f"{p}_cumulative_net", "numeric", "Broker Flow",
                     f"Running total of {p} net value since the ticker's first session on this board's history.",
                     f"SUM({sym}) over all sessions up to and including the date (a refresh continues the stored "
                     "value of the row before its range)", "IDR", "Never NULL.", lookback="all sessions",
                     misuse="Starts at the ticker's first valid observation, not at 2016 for every ticker; do not "
                            "compare levels between tickers with different history lengths. " + GAP_NOTE + "."))
    for n in (5, 10, 20, 40, 60):
        c.append(col(f"foreign_net_{n}d", "numeric", "Broker Flow", f"Foreign net value over the last {n} sessions.",
                     f"SUM_{n}(F); {SESSION}", "IDR", WARMUP.format(n=n), lookback=f"{n} sessions",
                     minimum=f"{n} sessions", aggs=SUMS[1:]))
    for n in (5, 10, 20, 60):
        c.append(col(f"domestic_net_{n}d", "numeric", "Broker Flow", f"Domestic net value over the last {n} sessions.",
                     f"SUM_{n}(D); {SESSION}", "IDR", WARMUP.format(n=n), lookback=f"{n} sessions",
                     minimum=f"{n} sessions", aggs=SUMS[1:],
                     misuse="On balanced days it equals minus the foreign value; differences come from source gaps."))
    pct = "percent"
    c += [
        col("foreign_net_turnover_ratio_1d", "double precision", "Broker Flow",
            "Foreign net value as a share of total traded value (buy side).", "100 * F / T, T = FB + DB", pct,
            "NULL when T = 0."),
        col("foreign_net_turnover_ratio_5d", "double precision", "Broker Flow",
            "Foreign net value over 5 sessions as a share of 5-session traded value.", "100 * SUM_5(F) / SUM_5(T)", pct,
            "NULL when the denominator is 0 or before 5 sessions.", lookback="5 sessions", minimum="5 sessions"),
        col("foreign_net_turnover_ratio_20d", "double precision", "Broker Flow",
            "Foreign net value over 20 sessions as a share of 20-session traded value.", "100 * SUM_20(F) / SUM_20(T)",
            pct, "NULL when the denominator is 0 or before 20 sessions.", lookback="20 sessions",
            minimum="20 sessions"),
        col("foreign_buy_share_1d", "double precision", "Broker Flow", "Foreign buying as a share of traded value.",
            "100 * FB / T", pct, "NULL when T = 0."),
        col("foreign_sell_share_1d", "double precision", "Broker Flow", "Foreign selling as a share of traded value.",
            "100 * FS / T", pct, "NULL when T = 0."),
    ]
    for side, cond in (("buy", "F > 0"), ("sell", "F < 0")):
        for n in (5, 10, 20, 40):
            c.append(col(f"foreign_{side}_days_{n}d", "smallint", "Broker Persistence",
                         f"Sessions with foreign net {side}ing in the last {n} sessions.",
                         f"COUNT({cond}) over {n} sessions; F = 0 counts neither", "sessions",
                         WARMUP.format(n=n), lookback=f"{n} sessions", minimum=f"{n} sessions"))
    for base, need in ((252, 252), (60, 60)):
        for n in ((5, 10, 20, 40, 60) if base == 252 else (5, 10, 20)):
            first = n + base
            c.append(col(f"foreign_net_zscore_{n}d_base{base}d", "double precision", "Broker Abnormality",
                         f"Z-score of today's {n}-session foreign net against its previous {base} values.",
                         f"(foreign_net_{n}d - AVG(prev {base} foreign_net_{n}d)) / STDDEV_SAMP(prev {base}); today "
                         "excluded", "standard deviations",
                         f"NULL until {base} complete prior values exist (session {first}) or when the standard "
                         "deviation is 0.", lookback=f"{first} sessions", minimum=f"{first} sessions",
                         ranking="CONTEXTUAL",
                         misuse="Overlapping windows make consecutive values dependent; do not treat as independent "
                                "observations. " + GAP_NOTE + "."))
            c.append(col(f"foreign_net_percentile_{n}d_base{base}d", "double precision", "Broker Abnormality",
                         f"Midrank percentile of today's {n}-session foreign net among its previous {base} values.",
                         f"100 * (COUNT(prev < current) + 0.5 * COUNT(prev = current)) / {base}; today excluded",
                         pct, f"NULL until {base} complete prior values exist (session {first}).",
                         lookback=f"{first} sessions", minimum=f"{first} sessions",
                         misuse="A percentile of the ticker's own history, not a cross-sectional rank."))
    c += [
        col("foreign_flow_vs_prev_20d", "numeric", "Broker Flow",
            "Foreign net of the last 20 sessions minus the 20 sessions before them.",
            "SUM(F, sessions t-19..t) - SUM(F, sessions t-39..t-20); windows do not overlap", "IDR",
            WARMUP.format(n=40), lookback="40 sessions", minimum="40 sessions"),
        col("foreign_flow_vs_prev_40d", "numeric", "Broker Flow",
            "Foreign net of the last 40 sessions minus the 40 sessions before them.",
            "SUM(F, sessions t-39..t) - SUM(F, sessions t-79..t-40); windows do not overlap", "IDR",
            WARMUP.format(n=80), lookback="80 sessions", minimum="80 sessions"),
    ]
    strength_misuse = ("Proposed EDGE formula, not the TradingView Foreign Strength; no Strong/Weak thresholds are "
                       "defined. Range -100 to +100.")
    c += [
        col("foreign_strength_20d", "double precision", "Broker Flow",
            "Direction consistency of daily foreign net ratios over 20 sessions.",
            "100 * SUM_20(R) / SUM_20(ABS(R)), R = F / T; sessions with T = 0 have no R", "index -100..100",
            "NULL before 20 sessions or when SUM_20(ABS(R)) = 0.", lookback="20 sessions", minimum="20 sessions",
            misuse=strength_misuse),
        col("foreign_strength_50d", "double precision", "Broker Flow",
            "Direction consistency of daily foreign net ratios over 50 sessions.",
            "100 * SUM_50(R) / SUM_50(ABS(R)), R = F / T", "index -100..100",
            "NULL before 50 sessions or when SUM_50(ABS(R)) = 0.", lookback="50 sessions", minimum="50 sessions",
            misuse=strength_misuse),
        col("foreign_strength_momentum_5d", "double precision", "Broker Flow",
            "Change of foreign_strength_20d over 5 sessions.",
            "foreign_strength_20d - foreign_strength_20d five sessions ago", "index points",
            "NULL when either value is NULL.", lookback="25 sessions", minimum="25 sessions", misuse=strength_misuse),
    ]
    tx = "transactions"
    for n, d, calc in (("foreign_buy_freq_1d", "Foreign buy transactions", "BF = SUM(buy_freq) WHERE Foreign"),
                       ("foreign_sell_freq_1d", "Foreign sell transactions", "SF = SUM(sell_freq) WHERE Foreign"),
                       ("domestic_buy_freq_1d", "Domestic buy transactions", "DBF = SUM(buy_freq) WHERE Domestic"),
                       ("domestic_sell_freq_1d", "Domestic sell transactions", "DSF = SUM(sell_freq) WHERE Domestic")):
        c.append(col(n, "bigint", "Volume", d + ".", calc, tx,
                     "NULL for symbols without frequency; zero when that investor type did not trade.", aggs=SUMS))
    for p, B, S, VB, VS, LB, LS in (("foreign", "BF", "SF", "FB", "FS", "FBL", "FSL"),
                                     ("domestic", "DBF", "DSF", "DB", "DS", "DBL", "DSL")):
        c += [
            col(f"{p}_freq_imbalance_1d", "double precision", "Volume",
                f"{p.title()} buy versus sell transaction imbalance.", f"100 * ({B} - {S}) / ({B} + {S})", pct,
                "NULL when the denominator is 0 or frequency is missing."),
            col(f"{p}_freq_imbalance_20d", "double precision", "Volume",
                f"{p.title()} transaction imbalance over 20 sessions.",
                f"100 * (SUM_20({B}) - SUM_20({S})) / (SUM_20({B}) + SUM_20({S}))", pct,
                "NULL before 20 sessions, when the denominator is 0 or frequency is missing.",
                lookback="20 sessions", minimum="20 sessions"),
            col(f"{p}_buy_freq_share_1d", "double precision", "Volume",
                f"{p.title()} share of buy transactions.", f"100 * {B} / (BF + DBF)", pct,
                "NULL when the denominator is 0 or frequency is missing."),
            col(f"{p}_sell_freq_share_1d", "double precision", "Volume",
                f"{p.title()} share of sell transactions.", f"100 * {S} / (SF + DSF)", pct,
                "NULL when the denominator is 0 or frequency is missing."),
            col(f"{p}_avg_buy_value_per_freq_1d", "double precision", "Volume",
                f"Average {p} buy value per transaction (ticket size).", f"{VB} / {B}", "IDR per transaction",
                "NULL when the frequency is 0 or missing."),
            col(f"{p}_avg_sell_value_per_freq_1d", "double precision", "Volume",
                f"Average {p} sell value per transaction.", f"{VS} / {S}", "IDR per transaction",
                "NULL when the frequency is 0 or missing."),
            col(f"{p}_buy_sell_ticket_ratio_1d", "double precision", "Volume",
                f"{p.title()} average buy ticket divided by average sell ticket.", f"({VB} / {B}) / ({VS} / {S})",
                "ratio", "NULL when a frequency or the sell value is 0 or missing."),
            col(f"{p}_avg_buy_lots_per_freq_1d", "double precision", "Volume",
                f"Average {p} lots per buy transaction.", f"{LB} / {B}", "lots per transaction",
                "NULL when the frequency is 0 or missing."),
            col(f"{p}_avg_sell_lots_per_freq_1d", "double precision", "Volume",
                f"Average {p} lots per sell transaction.", f"{LS} / {S}", "lots per transaction",
                "NULL when the frequency is 0 or missing."),
        ]
    for side, B, D, VF, VD in (("buy", "BF", "DBF", "FB", "DB"), ("sell", "SF", "DSF", "FS", "DS")):
        for p, Q, V in (("domestic", D, VD), ("foreign", B, VF)):
            c.append(col(f"{p}_{side}_freq_share_change_5d_vs_prev20d", "double precision", "Volume",
                         f"Change of the {p} share of {side} transactions: last 5 sessions versus the 20 before.",
                         f"100 * SUM_5({Q}) / (SUM_5({B}) + SUM_5({D})) - same over sessions t-24..t-5 "
                         "(window totals, not averages of daily ratios)", "percentage points",
                         "NULL before 25 sessions, when a denominator is 0 or frequency is missing.",
                         lookback="25 sessions", minimum="25 sessions"))
            c.append(col(f"{p}_{side}_value_per_freq_change_5d_vs_prev20d", "double precision", "Volume",
                         f"Percent change of the {p} average {side} value per transaction: last 5 sessions versus "
                         "the 20 before.",
                         f"100 * ((SUM_5({V}) / SUM_5({Q})) / (SUM_t-24..t-5({V}) / SUM_t-24..t-5({Q})) - 1)", pct,
                         "NULL before 25 sessions, when a denominator is 0 or frequency is missing.",
                         lookback="25 sessions", minimum="25 sessions"))
    order = ["domestic_buy_freq_share_change_5d_vs_prev20d", "foreign_buy_freq_share_change_5d_vs_prev20d",
             "domestic_buy_value_per_freq_change_5d_vs_prev20d", "foreign_buy_value_per_freq_change_5d_vs_prev20d",
             "domestic_sell_freq_share_change_5d_vs_prev20d", "foreign_sell_freq_share_change_5d_vs_prev20d",
             "domestic_sell_value_per_freq_change_5d_vs_prev20d", "foreign_sell_value_per_freq_change_5d_vs_prev20d"]
    head = [x for x in c if x["name"] not in order]
    c = head + sorted([x for x in c if x["name"] in order], key=lambda x: order.index(x["name"]))
    c.append(col("foreign_value_freq_sign_mismatch_1d", "boolean", "Volume",
                  "Foreign net value and foreign net transaction count point in different directions.",
                  "SIGN(F) <> SIGN(BF - SF)", "flag",
                  "NULL when F = 0, BF = SF or frequency is missing; FALSE when both have the same nonzero sign.",
                  aggs=("COUNT",), ranking="NOT_APPLICABLE", groupable=True))
    c.append(col("source_balance_gap", "boolean", "Data Quality",
                  "Internal: Feature 05 marks this date, ticker and board as a source gap (ERRORS M157).",
                  "BOOL_OR(Feature 05 source_balance_gap) for the date, ticker and board", "flag", "Never NULL.",
                  aggs=("COUNT",), ranking="NOT_APPLICABLE", groupable=True,
                  use="Internal data-quality filter; not exposed to the AI.",
                  misuse="Not a market signal; do not show it to users as one."))
    c.append(col("calculated_at", "timestamptz", "Metadata", "Statement timestamp when the row was written.",
                  "statement_timestamp()", "timestamp", "Never NULL.", role="DIMENSION", aggs=("MIN", "MAX", "COUNT"),
                  ranking="NOT_APPLICABLE", use="Operational audit of refreshes only.",
                  misuse="Not source time and not data availability time."))
    for x in c:
        x["source"] = F05
    order = table_order("feature_06_foreign_domestic", "20261022_003_create_feature_06_foreign_domestic.sql")  # created lower-case, renamed by 005
    return sorted(c, key=lambda x: order.index(x["name"]))


def table_order(table: str, migration_file: str) -> list[str]:
    """Column order of the CREATE TABLE in the migration, so the catalog and dictionary follow the table."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "database" / "migrations" / migration_file).read_text()
    body = text.split(f"CREATE TABLE public.{table} (", 1)[1].split("CONSTRAINT", 1)[0]
    return [ln.split()[0] for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("--")]


def q(v):
    return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"


def arr(v):
    return "ARRAY[" + ",".join(q(x) for x in v) + "]::text[]"


def migration() -> str:
    out = ["-- EXEC-F05-F06 Fase 4: catalog rows, generated by scripts/generate_feature_05_06_catalog.py.",
           "BEGIN;", "SET LOCAL lock_timeout = '10s';", ""]
    tables = [
        (F05, "Feature", "Broker-level daily buy/sell value, lots and frequency by investor type and board; the only "
         "source of Feature 06.", "One row per date, ticker, broker, investor type and board that traded",
         ["ticker", "trade_date", "broker", "investor_type", "market_board"],
         "Stockbit broker summary (IDX_Broker_Summary with buy_freq/sell_freq)", ["IDX_Broker_Summary"],
         ["database/migrations/20261022_002_create_feature_05_foreign_domestic_broker_detail.sql",
          "apps/feature-05-06-job/job.py"], REFRESH_05, ["refresh_feature_05(date,date,text[])"]),
        (F06, "Feature", "Stock-level foreign/domestic flow, persistence, z-scores and percentiles, strength and "
         "frequency analytics per ticker, board and date.", "One row per date, ticker and board that traded",
         ["ticker", "market_board", "trade_date"], "Feature 05 only", [F05],
         ["database/migrations/20261022_003_create_feature_06_foreign_domestic.sql", "apps/feature-05-06-job/job.py",
          "scripts/check_feature_06_sample.py"], REFRESH_06,
         ["refresh_feature_06(text,date)", "feature_06_midrank_percentile(numeric,numeric[],integer)"]),
    ]
    for (t, cat, d, grain, pk, sys_, src, paths, rule, funcs) in tables:
        out.append(f"""INSERT INTO public."Table_Catalog" (table_schema, table_name, category, definition, grain,
    primary_key_columns, source_system, source_tables, source_code_paths, update_rule, related_functions,
    documentation_status, readiness_mode, readiness_date_column, observation_date_column, availability_rule,
    point_in_time_status, historical_metadata_method)
VALUES ('public', {q(t)}, {q(cat)}, {q(d)}, {q(grain)}, {arr(pk)}, {q(sys_)}, {arr(src)}, {arr(paths)}, {q(rule)},
    {arr(funcs)}, 'VERIFIED', 'DATA_DATE', 'trade_date', 'trade_date',
    {q("Only through the last refreshed Broker Summary date; " + GAP_NOTE + ".")}, 'AVAILABLE',
    'Investor Type is source point-in-time data; no current-state profile metadata is used.');
""")
    for t, cols in ((F05, f05_columns()), (F06, f06_columns())):
        for i, x in enumerate(cols, 1):
            out.append(f"""INSERT INTO public."Column_Catalog" (table_schema, table_name, column_name, ordinal_position,
    data_type, is_nullable, is_primary_key, definition, source_column_or_expression, unit, null_rule,
    source_code_paths, documentation_status)
SELECT 'public', {q(t)}, c.column_name, c.ordinal_position, c.data_type, c.is_nullable = 'YES',
    {str(x['name'] in PK[t]).lower()},
    {q(x['definition'])}, 'Feature_Catalog active semantic version', {q(x['unit'])}, {q(x['null_rule'])},
    {arr(EVIDENCE[:3])}, 'VERIFIED'
FROM information_schema.columns c WHERE c.table_schema = 'public' AND c.table_name = {q(t)} AND c.column_name = {q(x['name'])};
""")
            out.append(f"""INSERT INTO public."Feature_Catalog" (feature_table, feature_column, grain, feature_category,
    definition, calculation, source_tables, source_columns, lookback_window, minimum_history, unit, null_rule,
    refresh_trigger, dependency_rule, version, is_active, semantic_role, allowed_aggregations, ranking_interpretation,
    is_filterable, is_groupable, availability_rule, point_in_time_safe, historical_metadata_warning,
    analytical_interpretation, recommended_use, misuse_warning, semantic_review_status, validation_evidence)
VALUES ({q(t)}, {q(x['name'])}, {q('Date x ticker x broker x investor type x board' if t == F05 else 'Date x ticker x board')},
    {q(x['category'])}, {q(x['definition'])}, {q(x['calculation'])}, {q(x['source'])}, {q(x['source'] + ' columns per calculation')},
    {q(x['lookback'])}, {q(x['minimum'])}, {q(x['unit'])}, {q(x['null_rule'])},
    {q(REFRESH_05 if t == F05 else REFRESH_06)}, {q('Requires IDX_Broker_Summary with synced frequency' if t == F05 else 'Requires Feature 05 refreshed for the same dates')},
    'v1', true, {q(x['role'])}, {arr(x['aggs'])}, {q(x['ranking'])}, {str(x['filterable']).lower()},
    {str(x['groupable']).lower()}, {q('Use only through the last refreshed Broker Summary date.')}, true,
    {q('Source Investor Type is point-in-time data.')}, {q(x['interpretation'])}, {q(x['use'])}, {q(x['misuse'])},
    'CALCULATION_VERIFIED', {arr(EVIDENCE)});
""")
    for name, d in (("buy_freq", "Number of buy transactions for the key, copied from IDX_Broker_Summary_Freq.buy_freq on the same Date, Symbol, Broker, Investor Type and Market Board."),
                    ("sell_freq", "Number of sell transactions for the key, copied from IDX_Broker_Summary_Freq.sell_freq on the same key.")):
        out.append(f"""INSERT INTO public."Column_Catalog" (table_schema, table_name, column_name, ordinal_position,
    data_type, is_nullable, is_primary_key, definition, source_column_or_expression, unit, null_rule,
    source_code_paths, documentation_status)
SELECT 'public', 'IDX_Broker_Summary', c.column_name, c.ordinal_position, c.data_type, true, false, {q(d)},
    {q('IDX_Broker_Summary_Freq.' + name + ' via sync_broker_summary_freq')}, 'transactions',
    'NULL when IDX_Broker_Summary_Freq has no row for the key (non-4-letter symbols) or before the sync; never zero for missing.',
    ARRAY['database/migrations/20261022_001_add_broker_summary_freq.sql'], 'VERIFIED'
FROM information_schema.columns c WHERE c.table_schema = 'public' AND c.table_name = 'IDX_Broker_Summary' AND c.column_name = {q(name)};
""")
    out.append("""UPDATE public."Table_Catalog"
SET related_functions = array_append(related_functions, 'sync_broker_summary_freq(date,date)'),
    source_code_paths = array_append(source_code_paths, 'database/migrations/20261022_001_add_broker_summary_freq.sql'),
    updated_at = now()
WHERE table_schema = 'public' AND table_name = 'IDX_Broker_Summary'
  AND NOT 'sync_broker_summary_freq(date,date)' = ANY (related_functions);
""")
    out.append(f"""INSERT INTO public."Feature_Relationship_Catalog" (left_feature_table, right_feature_table,
    left_join_columns, right_join_columns, relationship_type, safe_output_grain, requires_preaggregation, definition,
    version, is_active)
VALUES ({q(F05)}, {q(F06)}, ARRAY['ticker','market_board','trade_date'], ARRAY['ticker','market_board','trade_date'],
    'MANY_TO_ONE', 'Date x ticker x board after Feature 05 is aggregated by investor type', true,
    'Feature 06 is Feature 05 summed by investor type per ticker, board and date; join only after aggregating Feature 05.',
    'v1', true);
""")
    out.append("COMMIT;")
    return "\n".join(out)


def dictionary() -> str:
    lines = ["# Feature 05 and Feature 06: foreign/domestic flow and frequency", "",
             "Generated by `scripts/generate_feature_05_06_catalog.py` (EXEC-F05-F06). The same text is in "
             "`Feature_Catalog` v1.", "",
             "Sessions: " + SESSION + ". A window is NULL until it is full; a ratio with a zero denominator is "
             "NULL; the nine dates missing from IDX_Broker_Summary (2016-2017) are not sessions. " + GAP_NOTE + ".",
             ""]
    for t, cols in ((F05, f05_columns()), (F06, f06_columns())):
        lines += [f"## `{t}` ({len(cols)} columns)", "",
                  "| Column | Type | Category | Definition | Formula | Unit | NULL rule | Minimum history |",
                  "|---|---|---|---|---|---|---|---|"]
        for x in cols:
            cells = [f"`{x['name']}`", x["type"], x["category"], x["definition"], x["calculation"], x["unit"],
                     x["null_rule"], x["minimum"]]
            lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in cells) + " |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "dictionary"
    if what == "count":
        print(len(f05_columns()), len(f06_columns()))
    else:
        sys.stdout.write((migration() if what == "migration" else dictionary()).rstrip("\n") + "\n")
