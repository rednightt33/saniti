-- Feature_Vocabulary verification report, corrections approved 2026-10-25 ("Cari solusi juga untuk ini. Kalau
-- straightforward, langsung edit. Inspect code base dulu dan dependensi. Seharusnya fitur 5 referke table IDX broker
-- summary."). The texts are corrected at their owner, Feature_Catalog, and every catalog copy that still holds the old
-- text follows; Feature_Vocabulary is then re-synced from the rebuilt seed (scripts/sync_feature_vocabulary.py).
--
-- Each correction names (feature table, column, field, old text, new text); the copies are found by key, not listed:
--   null_rule        -> Column_Catalog.null_rule, AI_calculation_catalog.missing_data_policy
--   minimum_history  -> AI_calculation_catalog.parameters.minimum_history
--   calculation      -> AI_calculation_catalog.definition (its " Calculation: " part), AI_column_catalog and
--                       Column_Catalog source_column_or_expression
--   unit             -> AI_column_catalog.unit, Column_Catalog.unit, AI_calculation_catalog.output_definition.unit
-- on the feature table itself and on its exposed stock view (<table>_Stock). A copy that no longer equals the old text
-- was edited on purpose elsewhere and is left alone.
-- Evidence (code, not memory): Feature 05 reads buy_freq/sell_freq from IDX_Broker_Summary
-- (20261022_005 refresh_feature_05) and the staging IDX_Broker_Summary_Freq with its sync was dropped (20261025_007);
-- stock Feature 06 sums the known frequencies with SUM, which skips NULL, and a day is NULL only when no source row of
-- the ticker, board and date carries frequency (20261022_005 refresh_feature_06, checked below on the live function).
-- The Feature 05 refresh_trigger and Table_Catalog.update_rule still named the dropped sync: they now name the
-- Broker Summary load.
-- Forward-only. Rollback: a later migration with old and new swapped.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '5min';

CREATE TEMP TABLE m_vocab (feature_table text NOT NULL, feature_column text NOT NULL, field text NOT NULL,
                           old_value text NOT NULL, new_value text NOT NULL,
                           PRIMARY KEY (feature_table, feature_column, field)) ON COMMIT DROP;
INSERT INTO m_vocab VALUES
    ('Feature_02_Broker_Rolling', 'investor_type', 'minimum_history',
     'Matching current profile',
     '1 source row'),
    ('Feature_02_Broker_Rolling_INDEX', 'investor_type', 'minimum_history',
     'Matching current profile',
     '1 source row'),
    ('Feature_05_Foreign_Domestic_Broker_Detail', 'buy_freq', 'calculation',
     'IDX_Broker_Summary.buy_freq (from IDX_Broker_Summary_Freq.buy_freq)',
     'IDX_Broker_Summary.buy_freq (stored with each Broker Summary row)'),
    ('Feature_05_Foreign_Domestic_Broker_Detail', 'buy_freq', 'null_rule',
     'NULL when the source has no frequency (non-4-letter symbols); never replaced by zero.',
     'NULL when the source row carries no frequency (up to 2026-08-31: the symbols that are not four letters, such as warrants and rights); never replaced by zero.'),
    ('Feature_05_Foreign_Domestic_Broker_Detail', 'sell_freq', 'calculation',
     'IDX_Broker_Summary.sell_freq (from IDX_Broker_Summary_Freq.sell_freq)',
     'IDX_Broker_Summary.sell_freq (stored with each Broker Summary row)'),
    ('Feature_05_Foreign_Domestic_Broker_Detail', 'sell_freq', 'null_rule',
     'NULL when the source has no frequency (non-4-letter symbols); never replaced by zero.',
     'NULL when the source row carries no frequency (up to 2026-08-31: the symbols that are not four letters, such as warrants and rights); never replaced by zero.'),
    ('Feature_06_Foreign_Domestic', 'foreign_buy_freq_1d', 'null_rule',
     'NULL for symbols without frequency; zero when that investor type did not trade.',
     'NULL when no source row of the ticker, board and date carries frequency; otherwise the sum of the known frequencies of that investor type, 0 when it has no row. A row without frequency adds nothing to the sum.'),
    ('Feature_06_Foreign_Domestic', 'foreign_sell_freq_1d', 'null_rule',
     'NULL for symbols without frequency; zero when that investor type did not trade.',
     'NULL when no source row of the ticker, board and date carries frequency; otherwise the sum of the known frequencies of that investor type, 0 when it has no row. A row without frequency adds nothing to the sum.'),
    ('Feature_06_Foreign_Domestic', 'domestic_buy_freq_1d', 'null_rule',
     'NULL for symbols without frequency; zero when that investor type did not trade.',
     'NULL when no source row of the ticker, board and date carries frequency; otherwise the sum of the known frequencies of that investor type, 0 when it has no row. A row without frequency adds nothing to the sum.'),
    ('Feature_06_Foreign_Domestic', 'domestic_sell_freq_1d', 'null_rule',
     'NULL for symbols without frequency; zero when that investor type did not trade.',
     'NULL when no source row of the ticker, board and date carries frequency; otherwise the sum of the known frequencies of that investor type, 0 when it has no row. A row without frequency adds nothing to the sum.'),
    ('Feature_06_Foreign_Domestic', 'foreign_freq_imbalance_20d', 'null_rule',
     'NULL before 20 sessions, when the denominator is 0 or frequency is missing.',
     'NULL before 20 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'domestic_freq_imbalance_20d', 'null_rule',
     'NULL before 20 sessions, when the denominator is 0 or frequency is missing.',
     'NULL before 20 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'domestic_buy_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'foreign_buy_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'domestic_buy_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'foreign_buy_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'domestic_sell_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'foreign_sell_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'domestic_sell_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic', 'foreign_sell_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing.',
     'NULL before 25 sessions or when a denominator is 0. Sessions whose frequency is NULL are skipped inside the window (SQL SUM ignores NULL): the value is computed from the sessions that carry frequency and is NULL only when none of them does.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_freq_imbalance_1d', 'null_rule',
     'NULL when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_freq_imbalance_20d', 'null_rule',
     'NULL before 20 sessions, when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 20 sessions, when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_buy_freq_share_1d', 'null_rule',
     'NULL when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_sell_freq_share_1d', 'null_rule',
     'NULL when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_avg_buy_value_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_avg_sell_value_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_buy_sell_ticket_ratio_1d', 'null_rule',
     'NULL when a frequency or the sell value is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when a frequency or the sell value is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_avg_buy_lots_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_avg_sell_lots_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_freq_imbalance_1d', 'null_rule',
     'NULL when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_freq_imbalance_20d', 'null_rule',
     'NULL before 20 sessions, when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 20 sessions, when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_buy_freq_share_1d', 'null_rule',
     'NULL when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_sell_freq_share_1d', 'null_rule',
     'NULL when the denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_avg_buy_value_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_avg_sell_value_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_buy_sell_ticket_ratio_1d', 'null_rule',
     'NULL when a frequency or the sell value is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when a frequency or the sell value is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_avg_buy_lots_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_avg_sell_lots_per_freq_1d', 'null_rule',
     'NULL when the frequency is 0 or missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when the frequency is 0 or missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_buy_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_buy_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_buy_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_buy_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_sell_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_sell_freq_share_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'domestic_sell_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_sell_value_per_freq_change_5d_vs_prev20d', 'null_rule',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL before 25 sessions, when a denominator is 0 or frequency is missing. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_value_freq_sign_mismatch_1d', 'null_rule',
     'NULL when F = 0, BF = SF or frequency is missing; FALSE when both have the same nonzero sign. INDEX sample: unavailable when contributing frequency input/window is incomplete; never divide full-scope value by partial-scope frequency.',
     'NULL when F = 0, BF = SF or frequency is missing; FALSE when both have the same nonzero sign. INDEX: NULL when the board-day (1d), any of the last 20 board-days (_20d) or any of the last 25 board-days (_vs_prev20d) has a source row with unknown frequency. Up to 2026-08-31 every Regular board-day had such a row, so these columns are NULL on Regular rows up to that date.'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_5d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_10d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_20d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_40d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_60d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_5d_base60d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_10d_base60d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic', 'foreign_net_percentile_20d_base60d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_5d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_10d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_20d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_40d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_60d_base252d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_5d_base60d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_10d_base60d', 'unit',
     'percent',
     'Percentile 0-100'),
    ('Feature_06_Foreign_Domestic_INDEX', 'foreign_net_percentile_20d_base60d', 'unit',
     'percent',
     'Percentile 0-100');

DO $preflight$
DECLARE
    r record;
    n integer;
BEGIN
    IF EXISTS (SELECT 1 FROM m_vocab WHERE field NOT IN ('null_rule', 'minimum_history', 'calculation', 'unit')) THEN
        RAISE EXCEPTION 'Unexpected corrected field';
    END IF;
    FOR r IN SELECT * FROM m_vocab LOOP
        EXECUTE format('SELECT count(*) FROM public."Feature_Catalog" WHERE is_active AND feature_table = $1
                        AND feature_column = $2 AND %I = $3', r.field)
            INTO n USING r.feature_table, r.feature_column, r.old_value;
        IF n <> 1 THEN
            RAISE EXCEPTION '%.% %: the live text is not the reviewed old text (% rows); re-export and review first',
                r.feature_table, r.feature_column, r.field, n;
        END IF;
    END LOOP;
    -- the corrected Feature 06 texts describe this code; refuse if the live function no longer has it
    IF position('WHEN b.freq_rows > 0 THEN coalesce(b.bf, 0) ELSE b.bf END' IN
                pg_get_functiondef('public.refresh_feature_06(text, date)'::regprocedure)) = 0 THEN
        RAISE EXCEPTION 'refresh_feature_06 no longer sums known frequencies as reviewed';
    END IF;
    IF to_regclass('public."IDX_Broker_Summary_Freq"') IS NOT NULL THEN
        RAISE EXCEPTION 'IDX_Broker_Summary_Freq still exists: the Feature 05 texts would be wrong';
    END IF;
END
$preflight$;

CREATE TEMP TABLE m_vocab_copies (copy text NOT NULL, updated integer NOT NULL) ON COMMIT DROP;

DO $apply$
DECLARE
    r record;
    n integer;
    objects text[];
BEGIN
    FOR r IN SELECT * FROM m_vocab ORDER BY feature_table, feature_column, field LOOP
        objects := ARRAY[r.feature_table, r.feature_table || '_Stock'];
        EXECUTE format('UPDATE public."Feature_Catalog" SET %I = $4, updated_at = CURRENT_TIMESTAMP WHERE is_active
                        AND feature_table = $1 AND feature_column = $2 AND %I = $3', r.field, r.field)
            USING r.feature_table, r.feature_column, r.old_value, r.new_value;
        IF r.field = 'null_rule' THEN
            UPDATE public."Column_Catalog" SET null_rule = r.new_value, updated_at = CURRENT_TIMESTAMP
            WHERE table_schema = 'public' AND table_name = ANY (objects) AND column_name = r.feature_column
              AND null_rule = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('Column_Catalog.null_rule', n);
            UPDATE public."AI_calculation_catalog" SET missing_data_policy = r.new_value, updated_at = CURRENT_TIMESTAMP
            WHERE target_table = ANY (objects) AND calculation_name = r.feature_column
              AND missing_data_policy = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('AI_calculation_catalog.missing_data_policy', n);
        ELSIF r.field = 'minimum_history' THEN
            UPDATE public."AI_calculation_catalog"
            SET parameters = jsonb_set(parameters, '{minimum_history}', to_jsonb(r.new_value)), updated_at = CURRENT_TIMESTAMP
            WHERE target_table = ANY (objects) AND calculation_name = r.feature_column
              AND parameters ->> 'minimum_history' = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('AI_calculation_catalog.parameters.minimum_history', n);
        ELSIF r.field = 'calculation' THEN
            UPDATE public."AI_calculation_catalog"
            SET definition = replace(definition, ' Calculation: ' || r.old_value, ' Calculation: ' || r.new_value),
                updated_at = CURRENT_TIMESTAMP
            WHERE target_table = ANY (objects) AND calculation_name = r.feature_column
              AND position(' Calculation: ' || r.old_value IN definition) > 0;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('AI_calculation_catalog.definition', n);
            UPDATE public."AI_column_catalog" SET source_column_or_expression = r.new_value, updated_at = CURRENT_TIMESTAMP
            WHERE table_name = ANY (objects) AND column_name = r.feature_column
              AND source_column_or_expression = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('AI_column_catalog.source_column_or_expression', n);
            UPDATE public."Column_Catalog" SET source_column_or_expression = r.new_value, updated_at = CURRENT_TIMESTAMP
            WHERE table_schema = 'public' AND table_name = ANY (objects) AND column_name = r.feature_column
              AND source_column_or_expression = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('Column_Catalog.source_column_or_expression', n);
        ELSE
            UPDATE public."AI_column_catalog" SET unit = r.new_value, updated_at = CURRENT_TIMESTAMP
            WHERE table_name = ANY (objects) AND column_name = r.feature_column AND unit = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('AI_column_catalog.unit', n);
            UPDATE public."Column_Catalog" SET unit = r.new_value, updated_at = CURRENT_TIMESTAMP
            WHERE table_schema = 'public' AND table_name = ANY (objects) AND column_name = r.feature_column
              AND unit = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('Column_Catalog.unit', n);
            UPDATE public."AI_calculation_catalog"
            SET output_definition = jsonb_set(output_definition, '{unit}', to_jsonb(r.new_value)), updated_at = CURRENT_TIMESTAMP
            WHERE target_table = ANY (objects) AND calculation_name = r.feature_column
              AND output_definition ->> 'unit' = r.old_value;
            GET DIAGNOSTICS n = ROW_COUNT; INSERT INTO m_vocab_copies VALUES ('AI_calculation_catalog.output_definition.unit', n);
        END IF;
    END LOOP;
END
$apply$;

-- Feature 05 is refreshed from the Broker Summary load itself (the load carries buy_freq and sell_freq)
UPDATE public."Feature_Catalog"
SET refresh_trigger = replace(refresh_trigger, 'after sync_broker_summary_freq for the same dates',
                              'after the IDX_Broker_Summary load for the same dates (the load carries buy_freq and sell_freq)'),
    updated_at = CURRENT_TIMESTAMP
WHERE is_active AND refresh_trigger LIKE '%sync_broker_summary_freq%';
UPDATE public."Table_Catalog"
SET update_rule = replace(update_rule, 'after sync_broker_summary_freq for the same dates',
                          'after the IDX_Broker_Summary load for the same dates (the load carries buy_freq and sell_freq)'),
    source_code_paths = CASE WHEN 'database/migrations/20261025_012_feature_vocabulary_corrections.sql' = ANY (source_code_paths)
                             THEN source_code_paths
                             ELSE array_append(source_code_paths, 'database/migrations/20261025_012_feature_vocabulary_corrections.sql') END,
    updated_at = CURRENT_TIMESTAMP
WHERE table_schema = 'public' AND update_rule LIKE '%sync_broker_summary_freq%';

DO $verify$
DECLARE
    r record;
    n integer;
BEGIN
    FOR r IN SELECT * FROM m_vocab LOOP
        EXECUTE format('SELECT count(*) FROM public."Feature_Catalog" WHERE is_active AND feature_table = $1
                        AND feature_column = $2 AND %I = $3', r.field)
            INTO n USING r.feature_table, r.feature_column, r.new_value;
        IF n <> 1 THEN
            RAISE EXCEPTION '%.% % was not corrected', r.feature_table, r.feature_column, r.field;
        END IF;
    END LOOP;
    -- no copy of a corrected column keeps an old text
    IF EXISTS (SELECT 1 FROM m_vocab AS m JOIN public."Column_Catalog" AS c
               ON c.table_schema = 'public' AND c.table_name IN (m.feature_table, m.feature_table || '_Stock')
              AND c.column_name = m.feature_column
               WHERE (m.field = 'null_rule' AND c.null_rule = m.old_value) OR (m.field = 'unit' AND c.unit = m.old_value)
                  OR (m.field = 'calculation' AND c.source_column_or_expression = m.old_value))
       OR EXISTS (SELECT 1 FROM m_vocab AS m JOIN public."AI_calculation_catalog" AS a
                  ON a.target_table IN (m.feature_table, m.feature_table || '_Stock') AND a.calculation_name = m.feature_column
                  WHERE (m.field = 'null_rule' AND a.missing_data_policy = m.old_value)
                     OR (m.field = 'minimum_history' AND a.parameters ->> 'minimum_history' = m.old_value)
                     OR (m.field = 'unit' AND a.output_definition ->> 'unit' = m.old_value)
                     OR (m.field = 'calculation' AND position(' Calculation: ' || m.old_value IN a.definition) > 0))
       OR EXISTS (SELECT 1 FROM m_vocab AS m JOIN public."AI_column_catalog" AS a
                  ON a.table_name IN (m.feature_table, m.feature_table || '_Stock') AND a.column_name = m.feature_column
                  WHERE (m.field = 'unit' AND a.unit = m.old_value)
                     OR (m.field = 'calculation' AND a.source_column_or_expression = m.old_value)) THEN
        RAISE EXCEPTION 'A catalog copy of a corrected column still holds its old text';
    END IF;
    IF EXISTS (SELECT 1 FROM public."Feature_Catalog" WHERE is_active
               AND (calculation || refresh_trigger || null_rule) ~ 'Summary_Freq|sync_broker_summary_freq')
       OR EXISTS (SELECT 1 FROM public."Table_Catalog" WHERE update_rule ~ 'Summary_Freq|sync_broker_summary_freq') THEN
        RAISE EXCEPTION 'A Feature or Table catalog row still names the dropped frequency staging';
    END IF;
END
$verify$;
COMMIT;
