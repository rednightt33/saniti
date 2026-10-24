WITH raw AS MATERIALIZED (
 SELECT * FROM public."IDX_Broker_Summary" WHERE "Date"=DATE '2026-08-31'
), brokers AS (
 SELECT "Market Board" AS board,"Broker" AS broker,SUM("Buy Value") AS buy,SUM("Sell Value") AS sell,
 SUM("Buy Value"-"Sell Value") AS net,
 BOOL_OR("Buy Value"<>0 OR "Sell Value"<>0 OR "Buy Lots"<>0 OR "Sell Lots"<>0) AS active
 FROM raw GROUP BY 1,2
), ranked AS (
 SELECT *,row_number() OVER(PARTITION BY board ORDER BY net DESC,broker ASC) AS rank FROM brokers
), expected AS (
 SELECT board,COUNT(*) FILTER(WHERE active) AS active_broker_count,
 COUNT(*) FILTER(WHERE net>0) AS net_buy_broker_count,COUNT(*) FILTER(WHERE net<0) AS net_sell_broker_count,
 COUNT(*) FILTER(WHERE net=0 AND active) AS zero_net_active_broker_count,
 COUNT(*) FILTER(WHERE net>0)::double precision/NULLIF(COUNT(*) FILTER(WHERE active),0) AS net_buy_broker_ratio,
 (array_agg(broker ORDER BY net DESC,broker ASC) FILTER(WHERE net>0))[1] AS top_buyer,
 MAX(net) FILTER(WHERE net>0) AS top_buyer_net_value,
 (array_agg(broker ORDER BY net ASC,broker ASC) FILTER(WHERE net<0))[1] AS top_seller,
 MIN(net) FILTER(WHERE net<0) AS top_seller_net_value,
 COALESCE(SUM(net) FILTER(WHERE net>0 AND rank<=3),0) AS top3_buyer_net_value,
 COALESCE(SUM(net) FILTER(WHERE net>0),0) AS positive_net_value_total,
 SUM(buy) AS total_buy_value,SUM(sell) AS total_sell_value,SUM(net) AS all_broker_net
 FROM ranked GROUP BY board
), summed_stock_features AS (
 SELECT market_board AS board,COUNT(*) AS source_symbols,SUM(active_broker_count) AS sum_stock_active_broker_count,
 SUM(net_buy_broker_count) AS sum_stock_net_buy_broker_count,SUM(net_sell_broker_count) AS sum_stock_net_sell_broker_count,
 SUM(top_buyer_net_value) AS sum_stock_top_buyer_net_value,SUM(top_seller_net_value) AS sum_stock_top_seller_net_value,
 SUM(top3_buyer_net_value) AS sum_stock_top3_buyer_net_value,SUM(positive_net_value_total) AS sum_stock_positive_net_value_total
 FROM public."Feature_03_Stock_Broker_Daily" WHERE date=DATE '2026-08-31' AND ticker<>'IHSG' GROUP BY market_board
)
SELECT json_build_object('raw_expected',(SELECT json_agg(e ORDER BY board) FROM expected e),
 'stored',(SELECT json_agg(f ORDER BY market_board) FROM public."Feature_03_Stock_Broker_Daily" f WHERE ticker='IHSG' AND date=DATE '2026-08-31'),
 'sum_stock_features',(SELECT json_agg(s ORDER BY board) FROM summed_stock_features s),
 'raw_coverage',(SELECT json_agg(x ORDER BY board) FROM (SELECT "Market Board" AS board,COUNT(*) AS rows,COUNT(DISTINCT "Symbol") AS symbols,COUNT(DISTINCT "Broker") AS brokers FROM raw GROUP BY 1)x),
 'top_brokers',(SELECT json_agg(x ORDER BY board,net DESC,broker) FROM (SELECT * FROM ranked WHERE rank<=5)x));
