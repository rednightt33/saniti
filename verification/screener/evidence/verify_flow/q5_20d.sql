explain (analyze, buffers)
select ticker, sum(net_value) n20 from "Feature_05_Foreign_Domestic_Broker_Detail" where trade_date between date '2026-09-30' and date '2026-10-27' and broker='YP' and market_board='Regular' group by ticker
