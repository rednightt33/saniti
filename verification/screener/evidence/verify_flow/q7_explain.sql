explain (analyze, buffers)
with b as (
  select ticker, broker,
         sum(net_value) filter (where trade_date >= date '2026-10-21') n5,
         sum(net_value) filter (where trade_date >= date '2026-10-14') n10,
         sum(net_value) n20,
         sum(buy_value) filter (where trade_date >= date '2026-10-14') bv10, sum(buy_lots) filter (where trade_date >= date '2026-10-14') bl10,
         sum(buy_value) filter (where trade_date >= date '2026-10-21') tv5_part,
         sum(buy_value) filter (where trade_date >= date '2026-10-14') tv10_part,
         sum(buy_value) tv20_part
  from "Feature_05_Foreign_Domestic_Broker_Detail"
  where trade_date between date '2026-09-30' and date '2026-10-27' and market_board = 'Regular'
  group by ticker, broker
), r as (
  select b.*,
         row_number() over (partition by ticker order by n5 desc nulls last, broker) b5, row_number() over (partition by ticker order by n5 asc nulls last, broker) s5,
         row_number() over (partition by ticker order by n10 desc nulls last, broker) b10, row_number() over (partition by ticker order by n10 asc nulls last, broker) s10,
         row_number() over (partition by ticker order by n20 desc, broker) b20, row_number() over (partition by ticker order by n20 asc, broker) s20
  from b
)
select ticker,
  sum(tv5_part) tv5, sum(tv10_part) tv10, sum(tv20_part) tv20,
  coalesce(sum(n5) filter (where b5 <= 3 and n5 > 0), 0) + coalesce(sum(n5) filter (where s5 <= 3 and n5 < 0), 0) top3_5,
  coalesce(sum(n10) filter (where b10 <= 3 and n10 > 0), 0) + coalesce(sum(n10) filter (where s10 <= 3 and n10 < 0), 0) top3_10,
  coalesce(sum(n20) filter (where b20 <= 3 and n20 > 0), 0) + coalesce(sum(n20) filter (where s20 <= 3 and n20 < 0), 0) top3_20,
  coalesce(sum(n5) filter (where b5 <= 5 and n5 > 0), 0) + coalesce(sum(n5) filter (where s5 <= 5 and n5 < 0), 0) top5_5,
  coalesce(sum(n10) filter (where b10 <= 5 and n10 > 0), 0) + coalesce(sum(n10) filter (where s10 <= 5 and n10 < 0), 0) top5_10,
  coalesce(sum(n20) filter (where b20 <= 5 and n20 > 0), 0) + coalesce(sum(n20) filter (where s20 <= 5 and n20 < 0), 0) top5_20,
  sum(bv10) filter (where b10 <= 3 and n10 > 0) / nullif(100 * sum(bl10) filter (where b10 <= 3 and n10 > 0), 0) top3_vwap_10,
  count(*) filter (where n20 > 0) buyers_20, count(*) filter (where n20 < 0) sellers_20,
  sum(n20) filter (where b20 <= 3 and n20 > 0) / nullif(sum(n20) filter (where n20 > 0), 0) top3_buy_share_20,
  (array_agg(broker order by n20 desc, broker))[1] top_buyer_20, (array_agg(broker order by n20 asc, broker))[1] top_seller_20
from r group by ticker
