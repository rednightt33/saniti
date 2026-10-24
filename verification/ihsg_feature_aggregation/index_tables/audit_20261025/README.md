# Feature03 INDEX follow-up audit and deferred Feature05 column removal

Date: 2026-10-25 WIB. Read-only source/table check; no data, schema or runtime changes.
Target sample: IHSG 2026-08-31, Regular/Nego/Tunai separately.

Requested fields: top_buyer_net_value, top_seller, top_seller_net_value, top3_buyer_net_value,
positive_net_value_total, top3_buyer_share, broker_concentration_hhi.

Result: **21 comparisons, zero mismatches**. Source transactions are first summed across all symbols
and both investor types per broker/board; rankings use those broker nets, ties broker code ascending.
Top buyer/seller retain positive/negative signs. Top-three buyers use positive nets only. Their share
is top3_buyer_net_value / positive_net_value_total, not a share of gross turnover. HHI is NULL by prior
explicit user policy, despite being mathematically computable. Source scope is the previously declared
all-raw-symbol market proxy, not official historical index constituents.

| Board | Top buyer / net | Top seller / net | Top-three net | Total positive net | Top-three share |
|---|---|---|---:|---:|---:|
| Regular | PD / 628,869,060,400 | ZP / -595,514,539,800 | 1,177,743,686,500 | 1,952,122,575,100 | 0.6033144135120042 |
| Nego | AI / 628,434,108,000 | PD / -797,161,023,430 | 1,462,078,347,585 | 1,777,556,990,855 | 0.8225212216018708 |
| Tunai | NI / 795,000 | YJ / -1,276,000 | 1,276,000 | 1,276,000 | 1 |

All amounts IDR. HHI is NULL on all three boards. SQL and JSON keep the direct raw-source reference,
stored payload and top-three broker constituents. The source query also confirms all five coverage
columns are still physically present in Feature05 INDEX; user said to record their removal, not run it now.

Planned removal applies only to Feature05 INDEX: frequency_source_rows, buy_freq_known_rows,
sell_freq_known_rows, buy_freq_missing_rows, sell_freq_missing_rows. Feature06 counterparts remain.
Writer/catalog compatibility and internal completeness checks must be preserved in the future migration.
