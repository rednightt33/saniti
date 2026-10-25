WITH raw AS MATERIALIZED (
 SELECT * FROM public."IDX_Broker_Summary" WHERE "Date"=DATE '2026-08-31'
), pd_by_symbol AS (
 SELECT "Symbol" AS ticker,"Market Board" AS board,SUM("Buy Value") AS buy,SUM("Sell Value") AS sell,SUM("Buy Value"-"Sell Value") AS net
 FROM raw WHERE "Broker"='PD' GROUP BY 1,2
), totals AS (
 SELECT "Symbol" AS ticker,"Market Board" AS board,SUM("Buy Value") AS buy,SUM("Sell Value") AS sell,
 SUM("Buy Value"-"Sell Value") AS net FROM raw GROUP BY 1,2
), broker AS (
 SELECT "Broker" AS broker,"Market Board" AS board,SUM("Buy Value") AS buy,SUM("Sell Value") AS sell,
 SUM("Buy Value"-"Sell Value") AS net FROM raw WHERE "Symbol"='EMAS' GROUP BY 1,2
), ranked AS (
 SELECT *,row_number() OVER(PARTITION BY board ORDER BY net DESC,broker) AS buy_rank FROM broker
)
SELECT json_build_object(
 'stored',(SELECT json_agg(x ORDER BY ticker,market_board) FROM (SELECT * FROM public."Feature_03_Stock_Broker_Daily" WHERE date=DATE '2026-08-31' AND ticker IN ('EMAS','IHSG'))x),
 'pd_breakdown',(SELECT json_agg(x ORDER BY board) FROM (
 SELECT board,SUM(buy) AS all_buy,SUM(sell) AS all_sell,SUM(net) AS all_net,
 COALESCE(SUM(buy) FILTER(WHERE ticker='EMAS'),0) AS emas_buy,COALESCE(SUM(sell) FILTER(WHERE ticker='EMAS'),0) AS emas_sell,
 COALESCE(SUM(net) FILTER(WHERE ticker='EMAS'),0) AS emas_net,
 COALESCE(SUM(net) FILTER(WHERE ticker<>'EMAS'),0) AS other_net FROM pd_by_symbol GROUP BY 1)x),
 'emas_broker_ranking',(SELECT json_agg(x ORDER BY board,buy_rank) FROM ranked x WHERE buy_rank<=5),
 'raw_totals',(SELECT json_agg(x ORDER BY board,ticker) FROM totals x WHERE ticker='EMAS'),
 'source_imbalances',(SELECT json_agg(x ORDER BY board) FROM (
 SELECT board,COUNT(*) AS source_symbols,COUNT(*) FILTER(WHERE buy<>sell) AS unbalanced_symbols,SUM(buy) AS buy,SUM(sell) AS sell FROM totals GROUP BY 1)x));
