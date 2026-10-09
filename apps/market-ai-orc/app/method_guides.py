"""Method guides (G2_G3_REACTIVATION_PLAN.md 4b, user decision 2026-10-02): the model-facing menu and manual of the
analysis paths (G1 free code, G2 event study, G3 hypothesis plan, G4 multi-angle plan) and of the session helpers
whose misuse cost real runs.

This file is byte-identical in market-python-sandbox and market-ai-orc (app/method_guides.py); a test in each app
compares the two when both are present. The sandbox reports GUIDES_SHA256 in GET /v1/runtime (method_guides);
database migration 20261002_001 writes one row of public."AI_method_guide" per guide from GUIDES; market-ai-orc serves
those rows (the menu in get_system_capabilities and every run's start, the manual through get_method_guide) only when
the table, the sandbox and this file carry the same hash.

It describes; it does not compute. The sandbox tests keep it in step with the code: every input listed for a helper is
a parameter of that helper with the same default, and every runnable example runs in a session.

Layers (Agent Skills progressive disclosure): the menu (name, when to use and not, how the backend checks the result)
is offered at the start of every run; a guide is opened when the model needs it and stays in the conversation's data
record, so it is not opened twice; the examples are part of the guide.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GUIDES_VERSION = 7  # 2 (2026-10-02, HIGH ALERT): output definitions, event flow, approved success rule; 3 (2026-10-03, P26): thresholds with units, the approved outcome unit; 4 (2026-10-03, D6): base tables for claims, get_evidence; 5 (2026-10-05, P32/P33): counts over the approved ranges (in_period), activity z-scores without the current observation, backtest; 6 (2026-10-06, EXEC-E): get_evidence removed, cited figures by address; 7 (2026-10-09, M119): the session's own tables by name, working tables, the tables each helper emitted

# How the backend checks a result (ERRORS_AND_SOLUTIONS S23), from weakest to strongest.
VERIFICATION_LEVELS = {
    "DATA_COVERAGE_VERIFIED": "The data read covers the approved data need and every figure cited comes from a "
                              "released output; the formula of the code is not recalculated.",
    "BACKEND_HELPER": "The formula is the backend's tested helper code; the inputs and what you do with the result "
                      "are yours and are not recalculated.",
    "STATISTICS_VERIFIED": "The backend recomputes the statistics from the rows you passed; how those rows were built "
                           "is not checked.",
    "FORMULA_AND_STATISTICS_VERIFIED": "The backend rebuilds the input from your declaration and the delivered data and "
                                       "recomputes the result; a released result that differs fails.",
}


def _input(name: str, rule: str, *, of: str | None = None, default: Any = "__required__") -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "rule": rule}
    if of is not None:
        entry["of"] = of
    if default != "__required__":
        entry["default"] = default
    return entry


EXPRESSIONS = ("an expression over the request's columns, per entity and past values only: + - * / **, comparisons, "
               "& | ~, abs log exp sqrt sign min max where, lag(x, k), rolling_sum(x, n), rolling_mean(x, n)")

GUIDES: list[dict[str, Any]] = [
    {
        "name": "free_code", "g": "G1", "kind": "PATH",
        "title": "Free analysis code in the session",
        "use_when": ["A calculation, ranking, screen, description or comparison that no other method covers.",
                     "Explaining a result (why, what drives it, what stands out) by computing it from the data and "
                     "outputs already in the session.",
                     "Exploring the data first: each dataset's profile (in the session view) shows its columns, "
                     "ranges, frequent values and sample rows; print or inspect more before deciding the method."],
        "avoid_when": ["The outcome after an event, when event_study is offered (its result is recalculated by the "
                       "backend).",
                       "Testing a hypothesis with a verdict: that needs a research plan the user approves."],
        "helpers": [],
        "inputs": [_input("code", "Python for run_python. Read data only through the saniti helpers (load, load_range, "
                                  "sql, join, preaggregate, resample, period_return); a read outside them counts as not "
                                  "processed.")],
        "limits": ["A frame larger than the session's frame budget is refused before it loads "
                   "(MaterializationLimitExceeded): reduce it in sql() first; the session and its variables stay.",
                   "A table of an earlier result is loaded with load_output(output_id) (carried() lists them with "
                   "their labels); a figure built on it is never better checked than its label.",
                   "A table this session emitted in an earlier run_python is loaded the same way, by output_id or "
                   "name (label NOT_RELEASED until complete_analysis releases it). A frame needed again later is "
                   "kept with save_table(name, frame) and read with load_table(name): working tables share the "
                   "session's working_table_bytes, are never released and never cited; emit_table what you cite.",
                   "complete_analysis needs every approved request and range read in a successful execution and at "
                   "least one output.",
                   "Every released table or JSON states how it was made: emit_table(name, frame, description, "
                   "definition={'filters': [{'column', 'operator', 'value'}], 'period': {'start', 'end'}, "
                   "'thresholds': {...}, 'notes': '...'}) ({} when the code applied no filter beyond the data request); "
                   "complete_analysis does not release a result without one. Put row filters in the data request's "
                   "scope where you can, so the backend records them itself.",
                   "Only released outputs may be cited; print() is diagnostics only.",
                   "A sample size or a period's observation count uses the rows inside the approved ranges "
                   "(in_period(frame, request) or load_range): load() and include_buffers=True add warm-up and "
                   "forward rows that feed indicators only. When warm-up rows were used, state both spans (the "
                   "bundle's rows_in_ranges and rows_extracted).",
                   "A z-score that finds a spike in an activity series (volume, traded value or lots, a broker or "
                   "foreign flow: the catalog sums it over time) compares the observation with the ones before it: "
                   "the rolling mean and deviation of x.shift(1), as Pine's ta.sma(volume[1], n); a price z-score "
                   "keeps the current observation.",
                   "Release every figure the answer cites (its table or JSON output), so the answer writes it by its "
                   "address: a figure typed from your code without an address is refused once."],
        "verification": {"level": "DATA_COVERAGE_VERIFIED",
                         "checked": ["every approved request and range was delivered and read",
                                     "every figure of the answer comes from a released output (value references)",
                                     "every cited figure is read by the backend from its released output (DIRUJUK); "
                                     "it is not recomputed apart from your code"],
                         "not_checked": ["the formula of your code: say that the calculation was not independently "
                                         "recalculated"]},
        "results": "Released outputs of complete_analysis, cited as value references such as "
                   "{{out.o1.rows[<column>=<value>].<column>}}.",
        "insight": ["Start from the explained result's own table (load_output) and its definition in the data "
                    "record (filters, period, thresholds); never guess how an earlier result was made, and say how "
                    "a different definition differs.",
                    "Answer why with a computed breakdown, not a guess: change between periods, top and bottom "
                    "contributors, the measure split by a dimension, unusual values, concentration.",
                    "Split only by catalog columns that are groupable; add values only where the catalog's "
                    "aggregation rule is SUM.",
                    "Compare with a baseline (other entities, other periods) and size the difference.",
                    "Call the result an association, not a cause; causes outside the database (news, corporate "
                    "actions) are not available; offer a test (event study or a research plan) when the user wants "
                    "evidence."],
        "common_errors": [
            {"code": "SanitiError: 1 is not a data request", "seen_in": "S21",
             "fix": "range(n) is Python's built-in; one approved range is load_range(request, range_id) or "
                    "saniti.range."},
            {"code": "MaterializationLimitExceeded", "seen_in": "G14",
             "fix": "aggregate in sql() (GROUP BY the entity and date columns) before loading into pandas."},
            {"code": "TypeError on a date comparison", "seen_in": "2026-09-26 stress test",
             "fix": "the time column holds datetime.date objects: compare with datetime.date or convert with "
                    "pd.to_datetime first."},
            {"code": "a unit shown twice", "seen_in": "P22",
             "fix": "a format such as pct, pp or rp already shows its unit: do not type it after the reference."},
            {"code": "is not a table this session can load", "seen_in": "M119",
             "fix": "a table emitted in the same run_python is still your variable; from the next run_python load it "
                    "with load_output(name); keep any other frame with save_table(name, frame)."}],
        "examples": [
            {"title": "Ranking from a SQL summary", "runnable": True,
             "code": "top = sql('SELECT ticker, max(close) AS high, min(close) AS low FROM prices GROUP BY ticker "
                     "ORDER BY high DESC')\nload('stock_classification')\nemit_table('high_low', top, definition={})"},
            {"title": "Contribution of each entity to a change between two ranges", "runnable": True,
             "code": "now = load_range('prices', 'current_ytd')\nbefore = load_range('prices', "
                     "'previous_comparable')\nload('stock_classification')\nchange = (now.groupby('ticker')"
                     "['close'].last() - before.groupby('ticker')['close'].last()).rename('change')\n"
                     "share = (change / change.abs().sum()).rename('share_of_total_move')\n"
                     "emit_table('drivers', pd.concat([change, share], axis=1).sort_values('change'), definition={})"}],
    },
    {
        "name": "event_study", "g": "G2", "kind": "PATH",
        "title": "Event study: the outcome after an event against a baseline",
        "use_when": ["What happened after an event (a fall, a spike, a flow above a level): the forward return "
                     "after it against a baseline, with the number of events and its uncertainty.",
                     "Building the events and baseline rows of a hypothesis plan."],
        "avoid_when": ["A request with more than one row per entity and date (for example per broker): reduce it to "
                       "one row per entity and date first, or use another request.",
                       "A verdict on a hypothesis: pass the events to a hypothesis plan."],
        "helpers": ["event_study"],
        "inputs": [
            _input("request", "The data request id or logical name.", of="event_study"),
            _input("event", "A condition, " + EXPRESSIONS + "; for example close / lag(close, 1) - 1 <= -0.05.",
                   of="event_study"),
            _input("outcome", "{'forward_return': '<price column>'}; add 'request': '<data request id>' when the price "
                              "is in another request. Never a price level or a trailing return column.",
                   of="event_study"),
            _input("horizon", "Observations the outcome spans (one to two hundred sixty).", of="event_study"),
            _input("range_id", "One approved range, or every range (each range is studied on its own window).",
                   of="event_study", default=None),
            _input("overlap_policy", "NON_OVERLAPPING keeps an entity's next event only a horizon after the last one "
                                     "it kept; ALL keeps every event.", of="event_study", default="NON_OVERLAPPING"),
            _input("baseline", "ALL_ELIGIBLE (every row with a defined condition and outcome) or NON_EVENT (the rows "
                               "without the event).", of="event_study", default="ALL_ELIGIBLE"),
            _input("min_events", "The policy minimum reported as meets_min_events (default thirty); it never drops "
                                 "the study.", of="event_study", default=None),
            _input("holdout_start", "A date YYYY-MM-DD: adds IN_SAMPLE and OUT_OF_SAMPLE rows.", of="event_study",
                   default=None),
            _input("outcome_unit", "PERCENT or DECIMAL; leave unset in a research session (the approved experiment's unit "
                                   "is used, a different one is refused).", of="event_study", default=None),
            _input("name", "The output name (event_study_<n> when omitted).", of="event_study", default=None)],
        "limits": ["One row per entity and date (DUPLICATE_ENTITY_DATE otherwise).",
                   "Ranges of the request may not overlap (RANGES_OVERLAP); choose one with range_id.",
                   "An event whose outcome runs past the delivered data is censored and counted apart.",
                   "The request is loaded whole, so it must fit the session's frame budget."],
        "verification": {"level": "FORMULA_AND_STATISTICS_VERIFIED",
                         "checked": ["complete_analysis rebuilds the events and outcomes from the declaration and the "
                                     "bundle files and recomputes both tables; a match labels them "
                                     "CALCULATION_VERIFIED",
                                     "a released table that differs fails completion (CALCULATION_MISMATCH)"],
                         "not_checked": ["anything you compute afterwards from the tables or frames in your own code"]},
        "results": "Four tables: <name> (one row per segment ALL, IN_SAMPLE, OUT_OF_SAMPLE: event_count, event_dates, "
                   "effective_event_dates, mean, median, hit_rate, baseline_count, baseline_mean, baseline_median, "
                   "delta_mean, delta_ci_low, delta_ci_high, delta_p_value, censored_count, overlapping_dropped, "
                   "meets_min_events), <name>_events (date, entity, outcome), <name>_baseline and <name>_flow "
                   "(rows_in_window, condition_unknown, condition_true = the qualifying events, censored, "
                   "overlapping_dropped, used; condition_true = censored + overlapping_dropped + used); the call also "
                   "returns the events, baseline and flow frames, tables (the name of each table, which "
                   "load_output(name) reads in a later run_python) and rows_in_period (the rows each range used; buffer rows "
                   "only fed lags and forward returns). Cite {{out.o1.rows[segment=ALL].delta_mean}}; quote every "
                   "count of the event flow from <name>_flow, never derive one. The interval and p-value treat events "
                   "on one date as one observation.",
        "common_errors": [
            {"code": "DUPLICATE_ENTITY_DATE", "seen_in": "event_study",
             "fix": "use a request with one row per entity and date, or narrow its scope."},
            {"code": "EXPRESSION_INVALID", "seen_in": "event_study",
             "fix": "use only the request's columns and the expression functions; the name in the message is the "
                    "one that is unknown."},
            {"code": "CALCULATION_MISMATCH", "seen_in": "event_study",
             "fix": "never overwrite or re-emit the study's tables; run event_study again under the same name."},
            {"code": "a price level as the outcome", "seen_in": "S15",
             "fix": "the outcome is {'forward_return': '<price column>'}; the backend computes the return."}],
        "examples": [
            {"title": "Five-day return after a fall of at least five percent", "runnable": True,
             "code": "study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.05', {'forward_return': 'close'}, "
                     "5, name='drops')\nload('stock_classification')\nprint(study['summary'][0]['event_count'])"},
            {"title": "One range, every event, compared with the days without an event", "runnable": True,
             "code": "study = event_study('prices', 'close > rolling_mean(close, 5)', {'forward_return': 'close'}, 1, "
                     "range_id='current_ytd', overlap_policy='ALL', baseline='NON_EVENT', name='above_mean')\n"
                     "load('prices')\nload('stock_classification')"}],
    },
    {
        "name": "backtest", "g": None, "kind": "HELPER",
        "title": "Backtest: trades of a stated entry and exit rule on the governed prices",
        "use_when": ["Testing a trading rule the user states or scripts (for example a Pine strategy): the trades, "
                     "win rate, average gain and loss, realized reward to risk, profit factor and drawdown over the "
                     "approved period."],
        "avoid_when": ["The average outcome after an event against a baseline (event_study).",
                       "Adding exit rules the user did not state: use only the stop, target, exit signal or holding "
                       "limit the user or the script gives, and name any you assume as a choice."],
        "helpers": ["backtest"],
        "inputs": [
            _input("request", "The price request (data request id or logical name).", of="backtest"),
            _input("frame", "Your frame with the request's entity and date columns and the signal columns; compute "
                            "indicators on the whole frame, warm-up rows included.", of="backtest"),
            _input("signal", "A boolean column: True on the bar whose close triggers an entry (filled at the next "
                             "bar's open).", of="backtest"),
            _input("exit_signal", "A boolean column: True on the bar whose close triggers an exit (filled at the next "
                                  "bar's open).", of="backtest", default=None),
            _input("stop", "Stop loss as a fraction of the entry price (0.05 for 5%).", of="backtest", default=None),
            _input("target", "Take profit as a fraction of the entry price (0.10 for 10%).", of="backtest",
                   default=None),
            _input("max_hold", "Bars to hold at most (closed at the last bar's close).", of="backtest", default=None),
            _input("fee", "Cost per side as a fraction (0.0015 for 0.15%).", of="backtest", default=None),
            _input("unit", "PERCENT (default) or DECIMAL for the returns.", of="backtest", default=None),
            _input("prices", "{'open', 'high', 'low', 'close'} -> the request's columns when named differently.",
                   of="backtest", default=None),
            _input("range_id", "One approved range (default: every range, each traded on its own).", of="backtest",
                   default=None),
            _input("name", "The output name (backtest_<n> when omitted).", of="backtest", default=None)],
        "limits": ["Long only, one position per entity; a signal while a position is open is skipped and counted.",
                   "Stop and target are checked from the entry bar; a bar that opens beyond a level fills at its "
                   "open; when both levels are inside one bar the stop is taken first.",
                   "Only bars inside the approved ranges trade; a position still open at a range's end closes at its "
                   "last close (OPEN_AT_END).",
                   "Prices are read from the bundle, not from your frame; the frame gives the signal dates only."],
        "verification": {"level": "STATISTICS_VERIFIED",
                         "checked": ["complete_analysis re-runs the simulation on the bundle prices from the recorded "
                                     "signal dates and compares both tables; a match labels them CALCULATION_VERIFIED",
                                     "a released table that differs fails completion (CALCULATION_MISMATCH)"],
                         "not_checked": ["how your code computed the signals (the indicators and the crossing rule)"]},
        "results": "<name>_trades (entity, range_id, signal_date, entry_date, entry_price, exit_date, exit_price, "
                   "exit_reason STOP, TARGET, EXIT_SIGNAL, MAX_HOLD or OPEN_AT_END, bars_held, return) and "
                   "<name>_summary (per entity and ALL: signals, signals_skipped, trades, wins, win_rate, "
                   "mean_return, median_return, average_win, average_loss, realized_reward_risk, profit_factor, "
                   "cumulative_return, max_drawdown, bars_in_period, bars_buffer, first_date, last_date). Quote the "
                   "trade count and the period's bars from <name>_summary; bars_buffer are warm-up rows, not sample. The call "
                   "returns the trades frame and tables (each table's name, for load_output in a later run_python).",
        "common_errors": [
            {"code": "PRICE_COLUMN_MISSING", "seen_in": "backtest",
             "fix": "pass prices={'open': ..., 'high': ..., 'low': ..., 'close': ...} with the request's columns."},
            {"code": "CALCULATION_MISMATCH", "seen_in": "backtest",
             "fix": "never overwrite or re-emit the backtest's tables; run backtest again under the same name."},
            {"code": "warm-up bars counted as the test period", "seen_in": "P32",
             "fix": "quote bars_in_period; the warm-up rows are bars_buffer."}],
        "examples": [
            {"title": "Moving-average cross with a stop, a target and an exit on the opposite cross", "runnable": True,
             "code": "full = load('prices').sort_values(['ticker', 'date'])\n"
                     "fast = full.groupby('ticker')['close'].transform(lambda s: s.ewm(span=5, adjust=False).mean())\n"
                     "slow = full.groupby('ticker')['close'].transform(lambda s: s.ewm(span=20, adjust=False).mean())\n"
                     "above = (fast > slow).astype(bool)\nbefore = above.groupby(full['ticker']).shift(1)\n"
                     "full['up'] = above & (before == False)\nfull['down'] = ~above & (before == True)\n"
                     "bt = backtest('prices', full, 'up', exit_signal='down', stop=0.05, target=0.10, name='cross')\n"
                     "load('stock_classification')\nprint(bt['summary'][-1]['trades'])"}],
    },
    {
        "name": "hypothesis_plan", "g": "G3", "kind": "PATH",
        "title": "Hypothesis plan: hypotheses you formulate, tested with the backend's verdict",
        "use_when": ["One to four specific condition -> outcome hypotheses you formulate from the question and the "
                     "data, each with a baseline, a verdict and a judgement of its sample.",
                     "Testing an event study's events as a hypothesis."],
        "avoid_when": ["One root hypothesis examined with several library methods (multi-angle plan).",
                       "A description or calculation without a hypothesis (free code)."],
        "helpers": ["event_summary"],
        "inputs": [
            _input("experiments", "One to four, each with hypothesis_id, hypothesis, objective, condition, outcome, "
                                  "baseline, candidate_count, pairwise_comparisons, multiple_testing_policy, "
                                  "holdout_required, minimum sample, expected_direction, outcome_horizon_periods, "
                                  "outcome_unit, success_definition and min_effect (each threshold as the user wrote it, with its "
                                  "unit: min_effect_unit, success_rule.unit)."),
            _input("events", "One row per occurrence of the condition with its outcome and date (your code, or an "
                             "event study's events frame).", of="event_summary"),
            _input("baseline", "The comparison rows with outcome and date (your code, or an event study's baseline "
                               "frame).", of="event_summary"),
            _input("hypothesis_id", "The approved experiment's hypothesis_id.", of="event_summary"),
            _input("outcome_column", "The outcome column of both frames.", of="event_summary"),
            _input("date_column", "The date column of both frames.", of="event_summary"),
            _input("success_column", "A boolean column for success; refused when the approved plan has a "
                                     "success_rule.", of="event_summary", default=None),
            _input("success_above", "Leave unset: the approved plan's success_rule is applied by the backend (outcome "
                                    "above zero when the plan has none); a different value is refused.",
                   of="event_summary", default=None),
            _input("horizon_periods", "Periods one outcome spans (overlapping outcomes count once).",
                   of="event_summary", default=1),
            _input("outcome_unit", "Leave unset: the approved experiment's outcome_unit is used (a different one is "
                                   "refused).", of="event_summary", default=None),
            _input("expected_direction", "HIGHER, LOWER or DIFFERENT.", of="event_summary", default="HIGHER"),
            _input("min_effect", "The smallest effect that matters, when the user named one.", of="event_summary",
                   default=None),
            _input("comparisons", "Comparisons of the multiple-testing correction.", of="event_summary", default=1),
            _input("multiple_testing_policy", "NONE, BONFERRONI, HOLM or BENJAMINI_HOCHBERG.", of="event_summary",
                   default="NONE")],
        "limits": ["The user approves the plan before any data is used; check_data_feasibility first.",
                   "Each RESEARCH data need copies research_governance from its approved experiment.",
                   "The Research Governor bounds the hypotheses, experiments and follow-ups.",
                   "A research analysis without event_summary for each hypothesis is not completed."],
        "verification": {"level": "STATISTICS_VERIFIED",
                         "checked": ["the difference, interval, p-value, effective sample, smallest detectable "
                                     "effect, sample category and verdict are recomputed from the per-date "
                                     "aggregates of the rows passed to event_summary, with the approved values"],
                         "not_checked": ["how the events and baseline rows were built, unless they come from "
                                         "event_study, whose rows the backend rebuilt from its declaration"]},
        "results": "complete_analysis returns research_findings, one per hypothesis (verdict, sample category, "
                   "angle_a difference with its interval, angle_b success shares). Cite "
                   "{{finding.<hypothesis_id>.angle_a.difference}}; copy the verdict unchanged.",
        "common_errors": [
            {"code": "research findings MISSING", "seen_in": "research findings v1",
             "fix": "call event_summary once per hypothesis before complete_analysis."},
            {"code": "RESEARCH_PLAN_MISMATCH", "seen_in": "research plan v1",
             "fix": "copy hypothesis_id, hypothesis, objective, condition, outcome, baseline and the policy exactly "
                    "from the approved experiment."}],
        "examples": [
            {"title": "An event study's rows as a hypothesis", "runnable": True,
             "code": "study = event_study('prices', 'close / lag(close, 1) - 1 <= -0.01', {'forward_return': "
                     "'close'}, 1, name='dips')\nload('stock_classification')\nresult = event_summary("
                     "study['events'], study['baseline'], hypothesis_id='dip_rebound', outcome_column='outcome', "
                     "date_column='date')\nprint(result['verdict'])"}],
    },
    {
        "name": "multi_angle", "g": "G4", "kind": "PATH",
        "title": "Multi-angle plan: one root hypothesis from several library methods",
        "use_when": ["One root hypothesis examined from several angles, each answered by one method of the research "
                     "library with its own status, and a synthesis of where the angles agree."],
        "avoid_when": ["A hypothesis no library method answers (hypothesis plan).",
                       "A single calculation or event study (free code, event study)."],
        "helpers": [],
        "inputs": [_input("angles", "Each angle: angle_id, its question, a method of get_research_library with its "
                                    "parameters, horizon, unit, comparisons, multiple-testing policy, holdout and, for "
                                    "a return outcome, the request and price column; checked with "
                                    "check_research_feasibility before the plan is shown.")],
        "limits": ["The negotiated number of angles per plan.",
                   "Each angle is recorded once with its research helper in the approved bundle group.",
                   "The user approves the plan before any data is used."],
        "verification": {"level": "FORMULA_AND_STATISTICS_VERIFIED",
                         "checked": ["a declarative angle (expressions over a request) is rebuilt and recomputed by "
                                     "the backend"],
                         "not_checked": ["an angle recorded from a frame your code built is checked only for staying "
                                         "inside its data contract (STATISTICS_VERIFIED)",
                                         "research_custom verifies execution only"]},
        "results": "complete_research_run returns one finding per angle and a synthesis map. Cite "
                   "{{finding.<angle_id>.estimates.primary.estimate}}; copy each status unchanged.",
        "common_errors": [
            {"code": "OUTCOME_NOT_APPROVED", "seen_in": "S15",
             "fix": "the outcome is {'forward_return': '<price column>'}, never a price level."},
            {"code": "PLAN_FEASIBILITY", "seen_in": "M49",
             "fix": "present exactly the angles and designs check_research_feasibility returned FEASIBLE."}],
        "examples": [
            {"title": "The sequence of calls", "runnable": False,
             "code": "get_research_library -> check_research_feasibility -> RESEARCH_PLAN_CONFIRMATION -> (approval) "
                     "start_research_run -> run_research_code: research_conditional('<angle_id>', "
                     "request='<data_request_id>', condition='close / lag(close, 1) - 1 <= -0.05', "
                     "outcome={'forward_return': 'close'}) -> complete_research_run"}],
    },
    {
        "name": "period_return", "g": None, "kind": "HELPER",
        "title": "Return over a named calendar period (YTD, month, quarter, year)",
        "use_when": ["A return over a named calendar period, one row per entity, with one boundary convention."],
        "avoid_when": ["A return between two dates the user gave, an event's forward return, a rolling return."],
        "helpers": ["period_return"],
        "inputs": [
            _input("request", "The data request id or logical name; it needs a history buffer of one trading "
                              "observation.", of="period_return"),
            _input("range_id", "The approved range of the period.", of="period_return"),
            _input("value_column", "The price column.", of="period_return", default="close"),
            _input("entity_column", "When the request's entity column is not the catalog's.", of="period_return",
                   default=None),
            _input("date_column", "When the request's time column is not the catalog's.", of="period_return",
                   default=None)],
        "limits": ["The base is the last valid value strictly before the range start, the end the last valid value "
                   "on or before its end.",
                   "Without a history buffer it refuses (PeriodReturnError) instead of using the first value inside "
                   "the period."],
        "verification": {"level": "BACKEND_HELPER",
                         "checked": ["the boundary convention and the return formula are the helper's tested code"],
                         "not_checked": ["rankings or averages you compute from its rows"]},
        "results": "One row per entity: base_date, base_value, end_date, end_value, return_decimal, return_pct and "
                   "calculation_status (COMPLETE or why not); leave entities that are not COMPLETE out of rankings.",
        "common_errors": [
            {"code": "NO_PRIOR_CLOSE", "seen_in": "D12",
             "fix": "the entity has no value before the period within the buffer: report it, do not fill it."}],
        "examples": [
            {"title": "Year-to-date return per entity", "runnable": True,
             "code": "ytd = period_return('prices', 'current_ytd')\nload('prices')\nload('stock_classification')\n"
                     "emit_table('ytd', ytd, definition={})"}],
    },
    {
        "name": "resample", "g": None, "kind": "HELPER",
        "title": "Weekly or monthly rows from daily rows with the catalog's rules",
        "use_when": ["A weekly or monthly analysis of a daily request that declared resample."],
        "avoid_when": ["A column without a catalog resample rule (ResampleRuleMissing): drop it or stay daily."],
        "helpers": ["resample"],
        "inputs": [
            _input("frame", "The daily rows (from load or load_range).", of="resample"),
            _input("request", "The data request id or logical name whose catalog rules apply.", of="resample"),
            _input("frequency", "The target frequency when the request declares none.", of="resample", default=None)],
        "limits": ["Each column follows its catalog resample_aggregation (FIRST, LAST, MAX, MIN, SUM).",
                   "Compare or rank only periods with period_complete true."],
        "verification": {"level": "BACKEND_HELPER",
                         "checked": ["the aggregation of each column is the catalog's rule in the helper's code"],
                         "not_checked": ["what you compute from the periods"]},
        "results": "One row per entity and period with period_start, period_end, actual_first_date, "
                   "actual_last_date, observations and period_complete.",
        "common_errors": [
            {"code": "ResampleRuleMissing", "seen_in": "P13",
             "fix": "the column has no catalog rule; keys of the request's grain are not value columns."}],
        "examples": [],
    },
    {
        "name": "join_and_preaggregate", "g": None, "kind": "HELPER",
        "title": "Joining two requests by an approved relationship",
        "use_when": ["Combining two requests of the bundle through a relationship the data need approved."],
        "avoid_when": ["A pandas merge you design yourself: its grain and point-in-time semantics are not checked."],
        "helpers": ["join", "preaggregate"],
        "inputs": [
            _input("relationship_id", "The approved relationship.", of="join"),
            _input("left", "A frame of the left request (default: all of it).", of="join", default=None),
            _input("right", "A frame of the right request (default: all of it).", of="join", default=None),
            _input("how", "inner or left (default: the relationship's join type).", of="join", default=None),
            _input("relationship_id", "The relationship whose many side is reduced to its key grain.",
                   of="preaggregate"),
            _input("frame", "The many side's rows (default: all of it).", of="preaggregate", default=None),
            _input("measures", "The columns to aggregate, each with the catalog's cross-entity rule.",
                   of="preaggregate", default=None)],
        "limits": ["A column without a catalog cross-entity rule raises AggregationRuleMissing.",
                   "A relationship that requires preaggregation accepts only preaggregate's result."],
        "verification": {"level": "BACKEND_HELPER",
                         "checked": ["the join keys, cardinality and point-in-time semantics of the relationship"],
                         "not_checked": ["the calculation after the join"]},
        "results": "A frame at the relationship's grain; join_report() gives matched and unmatched rows.",
        "common_errors": [
            {"code": "JoinCardinalityError", "seen_in": "join",
             "fix": "preaggregate the many side to the relationship's key grain first."}],
        "examples": [],
    },
    {
        "name": "reading_data", "g": None, "kind": "HELPER",
        "title": "Reading the bundle: load, load_range, in_period and sql",
        "use_when": ["Every read of the approved data; sql() first for large requests (summaries in DuckDB)."],
        "avoid_when": ["Reading the input files directly: it counts as not processed."],
        "helpers": ["load", "load_range", "in_period", "sql", "load_output", "carried"],
        "inputs": [
            _input("request", "The data request id or logical name.", of="load"),
            _input("columns", "Columns to read (default: all).", of="load", default=None),
            _input("request", "The data request id or logical name.", of="load_range"),
            _input("range_id", "One approved range.", of="load_range"),
            _input("columns", "Columns to read (default: all).", of="load_range", default=None),
            _input("include_buffers", "True widens the range to its warm-up and future buffers.", of="load_range",
                   default=False),
            _input("frame", "A frame with the request's date column (for example from load or include_buffers=True).",
                   of="in_period"),
            _input("request", "The data request id or logical name.", of="in_period"),
            _input("range_id", "One approved range (default: every range).", of="in_period", default=None),
            _input("date_column", "The frame's date column (default: the request's).", of="in_period", default=None),
            _input("query", "DuckDB SQL over one view per logical name.", of="sql"),
            _input("params", "Query parameters.", of="sql", default=None),
            _input("output_id", "A released table of this conversation (an analysis table, an event study's tables, "
                                "a hypothesis plan's aggregates, a multi-angle angle's input), from carried() or the "
                                "data record.", of="load_output"),
            _input("columns", "Columns to read (default: all).", of="load_output", default=None)],
        "limits": ["A request shown as AGGREGATE_FIRST is reduced in sql() before it becomes a pandas frame.",
                   "Every approved request and range must be read before complete_analysis.",
                   "Row counts name their span: rows_extracted (everything delivered, buffers included), "
                   "rows_in_ranges and ranges[].rows (inside the approved ranges), ranges[].buffer_rows_before and "
                   "buffer_rows_after. A sample size uses the rows inside the ranges: "
                   "frame[in_period(frame, request)].",
                   "A research plan's session loads only the carried tables its approved plan names; an analysis "
                   "session loads any released table of the conversation (24 hours)."],
        "verification": {"level": "DATA_COVERAGE_VERIFIED",
                         "checked": ["what was read, per request and range, for coverage",
                                     "which carried tables were loaded (carried_inputs of the final status, with "
                                     "their labels)"],
                         "not_checked": ["the SQL or pandas logic"]},
        "results": "pandas frames; the time column holds datetime.date objects and numbers are float64; a carried "
                   "frame's attrs hold its label and origin.",
        "common_errors": [
            {"code": "MaterializationLimitExceeded", "seen_in": "G14",
             "fix": "GROUP BY the entity and date columns in sql() first."},
            {"code": "SanitiError: 1 is not a data request", "seen_in": "S21",
             "fix": "plain range() is Python's; the helper is load_range."}],
        "examples": [
            {"title": "An earlier result as input, with its label", "runnable": False,
             "code": "for table in carried():\n    print(table['output_id'], table['name'], table['kind'], "
                     "table['label'])\nearlier = load_output('<output_id>')\nprint(earlier.attrs['label'])"},
            {"title": "Indicators on the whole history, counts over the approved ranges only", "runnable": True,
             "code": "full = load('prices').sort_values(['ticker', 'date'])\n"
                     "full['ma5'] = full.groupby('ticker')['close'].transform(lambda s: s.rolling(5).mean())\n"
                     "inside = full[in_period(full, 'prices')]\nload('stock_classification')\n"
                     "emit_table('above_ma5', inside.assign(above=inside['close'] > inside['ma5'])"
                     ".groupby('ticker', as_index=False)['above'].sum(), definition={})"},
            {"title": "A summary in DuckDB, then one range in pandas", "runnable": True,
             "code": "daily = sql('SELECT date, avg(close) AS mean_close FROM prices GROUP BY date ORDER BY date')\n"
                     "previous = load_range('prices', 'previous_comparable')\nload('prices')\n"
                     "load('stock_classification')\nemit_table('daily_mean', daily, definition={})"}],
    },
]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def guide_sha256(guide: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(guide).encode("utf-8")).hexdigest()


def guides_sha256() -> str:
    return hashlib.sha256(_canonical({"version": GUIDES_VERSION, "levels": VERIFICATION_LEVELS,
                                      "guides": GUIDES}).encode("utf-8")).hexdigest()


GUIDES_SHA256 = guides_sha256()


def by_name() -> dict[str, dict[str, Any]]:
    return {g["name"]: g for g in GUIDES}


def menu_entry(guide: dict[str, Any]) -> dict[str, Any]:
    """Layer one: what the method is for, when not to use it and how the backend checks it."""
    return {"name": guide["name"], "g": guide["g"], "kind": guide["kind"], "title": guide["title"],
            "use_when": guide["use_when"], "avoid_when": guide["avoid_when"],
            "verification": guide["verification"]["level"], "version": GUIDES_VERSION,
            "sha256": guide_sha256(guide)}


def rows() -> list[dict[str, Any]]:
    """One database row per guide (migration 20261002_001)."""
    return [{"name": g["name"], "guides_version": GUIDES_VERSION, "kind": g["kind"], "g": g["g"], "guide": g,
             "guide_sha256": guide_sha256(g)} for g in GUIDES]
