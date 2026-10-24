# IHSG Feature03 number audit — 2026-08-31

Read-only audit on 2026-10-24 WIB. User clarified the comparison is Feature 3, date 2026-08-31;
no numerical comparison values or external reference were supplied. The audit checks both raw-source
recalculation and the sum of non-IHSG per-ticker Feature03 rows. No table/data/configuration was changed.

## Results

All eight questioned fields match raw source recalculation for Regular, Nego and Tunai:
**24 comparisons, 0 differences**. `column_comparisons.csv` contains each comparison.
`feature3_raw_reconciliation.sql` computes directly from IDX_Broker_Summary, independently of the
index sample writer; JSON evidence includes stored rows, per-ticker sums, raw coverage and top brokers.

Regular board (IDR for values):

| Column | IHSG stored and raw recalculation | SUM of per-ticker feature column |
|---|---:|---:|
| active_broker_count | 89 | 24,912 |
| net_buy_broker_count | 45 | 13,278 |
| net_sell_broker_count | 44 | 11,497 |
| net_buy_broker_ratio | 45/89 = 0.5056179775280899 | Not additive; must recalculate from counts |
| top_buyer_net_value | 628,869,060,400 | 3,571,342,558,500 |
| top_seller_net_value | -595,514,539,800 | -3,608,443,403,400 |
| top3_buyer_net_value | 1,177,743,686,500 | 5,987,895,148,200 |
| positive_net_value_total | 1,952,122,575,100 | 8,499,098,032,400 |

These are different measures, not inconsistent arithmetic. Per-ticker activity counts count the same
broker repeatedly across symbols. Per-ticker winners can be different brokers; adding those winners
does not identify the market-wide winner or the top three market-wide brokers. Buyer/seller flags and
positive-flow clipping are applied after all symbols are netted per broker in the index calculation.

Exact definitions:

| Column | Index aggregate rule |
|---|---|
| active_broker_count | Unique brokers with any nonzero gross buy/sell value or lots on the date/board |
| net_buy_broker_count | Brokers with SUM(all source-symbol buy minus sell) > 0 |
| net_sell_broker_count | Brokers with that aggregate net < 0 |
| net_buy_broker_ratio | net-buy brokers / active brokers (includes active zero-net brokers in denominator) |
| top_buyer_net_value | Greatest positive aggregate broker net; broker code breaks ties |
| top_seller_net_value | Most negative aggregate broker net, preserving the sign |
| top3_buyer_net_value | Sum of the three greatest positive aggregate broker nets |
| positive_net_value_total | Sum of positive aggregate broker nets after cross-symbol netting |

A concrete source example, PD/Regular (see `pd_regular_netting.json`):

- Buy value 1,238,163,368,700; sell value 609,294,308,300; market-wide net 628,869,060,400.
- Summing PD's positive symbol nets alone gives 787,526,901,000, while its negative symbol nets sum
  to -158,657,840,600. Their sum is the market-wide net. Taking positive values before versus after
  netting is not interchangeable.
- PD was net buyer on 437 symbols, net seller on 383 and zero-net on 1, while contributing only one
  market-wide net-buy broker. Foreign/Domestic rows are combined per broker for these metrics.

Regular market-wide top three net buyers: PD 628,869,060,400 + CC 404,060,893,300 + CP 144,813,732,800
= 1,177,743,686,500. Top net seller is ZP at -595,514,539,800.

Zero-net activity is another potential comparison difference: Nego has 50 active brokers, composed of
16 net buyers + 18 net sellers + 16 active zero-net brokers. Tunai: 4 = 2 + 1 + 1. Regular: 89 = 45 + 44.
Thus active_broker_count need not equal net_buy_broker_count + net_sell_broker_count.

Gross money remains additive: Regular buy=sell=20,968,636,367,500; Nego buy=sell=4,054,672,626,274;
Tunai buy=sell=2,441,000. All-broker net is zero on every board, even though total positive broker net
is positive (negative broker nets offset it). Counts/ranks/ratios/positive-part sums are not additive.

## Scope and pending decisions

Regular includes 1,313 source symbols and 89 brokers; Nego 128 symbols/50 brokers; Tunai 5 symbols/4
brokers. Raw symbols include warrants/rights, not only current common-stock membership. The audit
proves correctness for that declared scope; it does not prove parity with an official constituent-only
IHSG screen or a gross-buy ranking. If the user means a different comparator, its exact values, board,
investor-type filter and instrument universe must be matched before diagnosing a code defect.

The new dedicated _INDEX table plan does not itself change these formulas. Changing to sums of existing
feature columns would redefine the measures and needs a separate explicit decision. No numerical fix,
schema creation, row migration, deletion or bulk calculation was executed by this audit.

Sources inspected: `20260914_047_define_feature_03_investor_type_v2.sql`, especially lines 55–123,
and `scripts/upsert_index_broker_feature_sample.py` daily aggregation and reference checks.

## EMAS vs index and gross buy/sell balance — follow-up read-only audit

Fresh source and stored comparison (`emas_vs_index.sql` / `.json`), 2026-08-31 Regular:

| Metric | EMAS only | Market-wide IHSG aggregate |
|---|---:|---:|
| top_buyer_net_value | PD 466,745,795,000 | PD 628,869,060,400 |
| top_seller_net_value | AK -144,751,107,500 | ZP -595,514,539,800 |
| top3_buyer_net_value | PD/LG/XL 583,278,315,000 | PD/CC/CP 1,177,743,686,500 |
| positive_net_value_total | 587,209,590,000 | 1,952,122,575,100 |

PD/EMAS buy=537,107,162,500 and sell=70,361,367,500, giving net 466,745,795,000 as the user
observed. PD's net in all other symbols is 162,123,265,400; adding it gives market net 628,869,060,400.
The formula is identical; the security scope changes. Different securities' top sellers and top-three
buyer identities cannot be assumed to remain the market-wide winners.

EMAS total buy=total sell=786,528,127,500. Market-wide Regular total buy=total sell=20,968,636,367,500.
Both are verified directly from raw source; the code sums Buy Value and Sell Value independently.
For complete matched executions at the same date/security/board, each transaction has an equal-value
buy side and sell side. Positive broker nets are offset by negative broker nets. The gross market-wide
buy/sell totals are therefore normally equal, while an individual broker or investor class can have
a nonzero net. Do not add both sides to report single-counted trading turnover.

On this date raw imbalance checks found zero unbalanced source symbols on Regular (1,313), Nego
(128), and Tunai (5). This is not a claim that every historical source date is complete; known historical
source gaps can create unequal totals and must remain flagged. No formula/data/schema changes made.
