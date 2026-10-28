select ticker, sum(net_value) net_5, sum(buy_value) bv_5, sum(buy_lots) bl_5, count(distinct trade_date) active_sessions
from "Feature_05_Foreign_Domestic_Broker_Detail"
where trade_date between date '2026-10-21' and date '2026-10-27' and broker = 'YP'
group by ticker
