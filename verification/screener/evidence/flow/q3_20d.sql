with b as (
  select ticker, broker,
         sum(net_value) net, sum(buy_value) bv, sum(buy_lots) bl, sum(sell_value) sv
  from "Feature_05_Foreign_Domestic_Broker_Detail"
  where trade_date between date '2026-09-30' and date '2026-10-27' and market_board = 'Regular'
  group by ticker, broker
), r as (
  select b.*, row_number() over (partition by ticker order by net desc, broker) rb,
              row_number() over (partition by ticker order by net asc, broker) rs,
              sum(bv) over (partition by ticker) tv
  from b
), t as (
  select ticker, max(tv) traded_value,
         coalesce(sum(net) filter (where rb <= 3 and net > 0), 0) top3_buy_net,
         coalesce(sum(net) filter (where rs <= 3 and net < 0), 0) top3_sell_net,
         sum(bv) filter (where rb <= 3 and net > 0) / nullif(100 * sum(bl) filter (where rb <= 3 and net > 0), 0) top3_buyer_vwap,
         count(*) filter (where net > 0) net_buyers, count(*) filter (where net < 0) net_sellers
  from r group by ticker
)
select t.ticker, traded_value, top3_buy_net, top3_sell_net,
       100 * (top3_buy_net + top3_sell_net) / nullif(traded_value, 0) bandar_ratio_pct,
       top3_buyer_vwap, p.close, 100 * (p.close / nullif(top3_buyer_vwap, 0) - 1) close_vs_top3_vwap_pct,
       net_buyers, net_sellers
from t left join "Price_Stock_Indonesia_IDX" p on p.ticker = t.ticker and p.date = date '2026-10-27' and p.timeframe = 'Daily'
