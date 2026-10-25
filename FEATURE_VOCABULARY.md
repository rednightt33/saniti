# Feature vocabulary

`public."Feature_Vocabulary"` is presentation metadata for Feature01,02,03,05,06, covering the stock
and dedicated INDEX tables separately. Feature04 is excluded. This guide describes the approved
implementation; live migration/load results are recorded in DATABASE_CHANGELOG.md and verification/.

The seven main display fields are `feature_number`, `column_name`, `column_name_proper`, `formula`,
`unit`, `definition`, `what_it_tells_us`. Proper names are English; explanations are Indonesian.
`source_table` and `scope` identify whether a definition describes stocks or INDEX. There is no
ticker or trade date in this dictionary, and no daily market values are copied into it.

One entry is identified by source_schema/source_table/column_name/language_code. The initial
language is id-ID. The expected first load has 391 entries after the five Feature05 INDEX coverage
columns are removed: stock 193 + INDEX 198. Identity/date/profile/quality/operational columns remain
documented and are labeled by `column_kind`; they are not presented as invented numerical signals.

## Interpretation rules

- INDEX transaction features describe all raw source symbols, including non-stock instruments,
  preserving each market board. They are market-flow aggregates, not an official historical IHSG
  constituent basket. INDEX price features use actual index closes, not summed stock prices.
- For broker features, scope=stock labels the legacy non-INDEX tables, not a promise that every
  source symbol is an ordinary share. These source tables can also contain warrants, rights and
  other instruments; an ordinary-stock subset requires an explicit universe filter.
- Cumulative INDEX flow includes earlier balances for symbols absent on the output date. Its broker
  source baseline is independent of the shorter index price history. Stock cumulative starts at the
  instrument's own first source observation. Compare balances only on aligned scope/baselines.
- D means observed sessions. Stock broker windows count the ticker's observed sessions; INDEX
  broker windows count aggregate market sessions. Inactive broker/board activity contributes zero
  only where the source contract establishes no activity; unknown frequency is not zero.
- Feature05 INDEX frequency SUM retains known contributions. Completeness is computed internally
  and remains visible in Feature06 coverage columns. Derived INDEX frequency ratios/ticket sizes
  remain NULL when the relevant source window is incomplete.
- Stock Feature06 frequency sums only the known frequencies (SQL SUM skips NULL): a day is NULL only when
  no source row of the ticker, board and date carries frequency, and a window skips such days. Up to
  2026-08-31 the source rows without frequency are the symbols that are not four letters (warrants,
  rights and similar); since 2026-09-01 every Broker Summary row carries frequency (`refresh_feature_06`,
  `20261022_005`).
- A percentile column (`*_percentile_*`) is a midrank percentile on 0–100, labelled "Persentil 0–100",
  not a percent of a quantity.
- `high_20d`/`high_60d` in Feature01 mean the highest **close**, not candle high. Fraction, percent,
  percentage-point change, IDR and index points are different units. HHI INDEX is deliberately NULL.
- Foreign Strength is the EDGE formula 100×SUM(R)/SUM(ABS(R)), R=foreign net/turnover. Its range
  is −100..+100; zero-turnover sessions have no R. It measures directional consistency rather than
  price return and is not asserted to equal TradingView Foreign Strength. No strong/weak cutoff is
  invented. Source quality flags and historical metadata warnings remain applicable.

## Maintenance

Feature_Catalog remains the formula authority. Reviewed templates are in
`scripts/build_feature_vocabulary_seed.py`; the checked-in seed is `database/feature_vocabulary_seed.json`.
The builder rejects any unknown column. A semantic SHA256 covers the source formula, definition,
unit, NULL/history rules, scope references and interpretation; sync refuses drift after review even
when the active version string is unchanged.

After a schema/semantic change, export the exact active source inventory and physical ordinals,
review/update the templates, regenerate the seed, and run `scripts/sync_feature_vocabulary.py`
(rollback by default; `--apply` only within an approved release). It checks exact physical coverage,
payload equality and idempotence. An unchanged entry preserves created_at/updated_at. New/changed
vocabulary fields require catalog/schema documentation; vocabulary rows are not new indicators.

A correction of a copied text (formula, unit, NULL or history rule) is made at its owner,
Feature_Catalog, by a migration that also updates every catalog copy still holding the old text
(Column_Catalog, AI_column_catalog, AI_calculation_catalog), then the seed is rebuilt and synced in the
same transaction. Example: `20261025_012_feature_vocabulary_corrections.sql` (63 corrections, EXEC.md
"Feature_Vocabulary: koreksi laporan verifikasi").

No new service or cron is required. This task does not implement a frontend API/UI, grant browser
database credentials, expose new AI tools, or enable automatic INDEX updates. The frontend can later
read the seven fields with source_table/scope/language filters through the approved BFF access path.

```sql
SELECT feature_number, column_name, column_name_proper, formula, unit,
       definition, what_it_tells_us
FROM public."Feature_Vocabulary"
WHERE source_schema = 'public'
  AND source_table = 'Feature_06_Foreign_Domestic_INDEX'
  AND language_code = 'id-ID'
ORDER BY display_order;
```
