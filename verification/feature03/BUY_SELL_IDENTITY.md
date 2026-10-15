# Feature_03: total buy value and total sell value (EXEC-BE1-2, ERRORS M154 a and M157)

User decision 2026-10-15 ("Ok, kita update saja kolom katalog untuk 2 kolom itu ya"; go "Ok jalankan"): the catalog
says what `total_buy_value` and `total_sell_value` can and cannot carry, so the AI does not read their difference as
demand.

## Why the two should be equal

`total_buy_value` and `total_sell_value` sum every broker's `buy_value_1d` and `sell_value_1d` for one ticker, date and
board. Every trade has a buying broker and a selling broker for the same value, so over all brokers the two sums are
equal and their difference is zero. `foreign_net_value + domestic_net_value = total_buy_value - total_sell_value` holds
on every stored row (DATABASE_CHANGELOG, Feature 03 v2 rebuild), and Feature_03 reconciles exactly to the raw Broker
Summary, so any gap comes from the source.

## Measured 2026-10-15 (read-only, pgweb, `lucid-patience/dev`)

```sql
SELECT market_board, extract(year FROM date)::int AS y, count(*) AS n,
       count(*) FILTER (WHERE total_buy_value <> total_sell_value) AS unequal,
       round(avg(CASE WHEN total_buy_value <> total_sell_value
                      THEN abs(total_buy_value - total_sell_value) / nullif(greatest(total_buy_value, total_sell_value), 0)
                 END)::numeric, 4) AS avg_rel_diff
FROM public."Feature_03_Stock_Broker_Daily" GROUP BY 1, 2 ORDER BY 1, 2;
```

All 2,268,015 rows (2016-01-04 to 2026-08-31): 47,768 unequal, the largest gap Rp 291,005,760,675.

| Board | 2016 | 2017 | 2018 | 2019 | 2020 | 2021–2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| Regular rows unequal | 14,270 of 97,000 | 7,849 of 118,461 | 9,084 of 136,753 | 10,647 of 145,085 | 5,446 of 154,717 | 0 | 2 of 261,053 | 2 of 203,536 |
| Regular mean gap | 3.8% | 5.1% | 4.0% | 3.4% | 5.4% | – | 2.5% | 80% |
| Nego rows unequal | 76 | 53 | 9 | 139 | 116 | 0 | 0 | 0 |
| Tunai rows unequal | 41 | 10 | 15 | 7 | 2 | 0 | 0 | 0 |

So the identity holds from 2021 (four exceptions in 2025–2026), and in 2016–2020 the source leaves about 7% of
Regular rows unequal. The cause in the source (for example brokers missing from the older Broker Summary) is not yet
verified: ERRORS M157.

## What the catalog says

`AI_column_catalog.description` (and the DRAFT Indonesian `description_id`) of both columns, and the active
`Feature_Catalog` v2 `misuse_warning`: the two are equal by construction; their difference is zero or a gap in the
source (2016–2020), never net demand; accumulation is read from per-broker or per-investor-type net
(`positive_net_value_total`, `foreign_net_value`, `domestic_net_value`). Migration
`database/migrations/20261015_011_feature03_buy_sell_identity.sql`.

An earlier check that found one unequal row in 89,933 covered only part of the table; the full count above replaces it.
