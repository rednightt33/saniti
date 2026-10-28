select ticker,
       sum(institutional_net_value) inst_net_20, sum(retail_net_value) retail_net_20,
       sum(foreign_net_value) foreign_net_20, sum(total_buy_value) value_20,
       100 * sum(institutional_net_value) / nullif(sum(total_buy_value), 0) inst_pct_20,
       100 * sum(retail_net_value) / nullif(sum(total_buy_value), 0) retail_pct_20,
       avg(net_buy_broker_ratio) avg_net_buy_broker_ratio_20,
       max(top3_buyer_share) filter (where date = date '2026-10-27') top3_share_1d,
       max(broker_concentration_hhi) filter (where date = date '2026-10-27') hhi_1d,
       count(*) sessions
from "Feature_03_Stock_Broker_Daily"
where date between date '2026-09-30' and date '2026-10-27' and market_board = 'Regular'
group by ticker
