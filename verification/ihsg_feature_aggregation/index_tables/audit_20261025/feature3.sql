WITH per_broker AS (
 SELECT "Market Board" AS market_board,"Broker" AS broker,
 SUM("Buy Value") AS buy,SUM("Sell Value") AS sell,SUM("Buy Value"-"Sell Value") AS net
 FROM public."IDX_Broker_Summary" WHERE "Date"=DATE '2026-08-31'
 GROUP BY "Market Board","Broker"
), ranked AS (
 SELECT *,row_number() OVER(PARTITION BY market_board ORDER BY net DESC,broker ASC) AS buyer_rank,
 row_number() OVER(PARTITION BY market_board ORDER BY net ASC,broker ASC) AS seller_rank FROM per_broker
), expected AS (
 SELECT market_board,(array_agg(broker ORDER BY net DESC,broker ASC) FILTER(WHERE net>0))[1] AS top_buyer,
 MAX(net) FILTER(WHERE net>0) AS top_buyer_net_value,
 (array_agg(broker ORDER BY net ASC,broker ASC) FILTER(WHERE net<0))[1] AS top_seller,
 MIN(net) FILTER(WHERE net<0) AS top_seller_net_value,
 COALESCE(SUM(net) FILTER(WHERE net>0 AND buyer_rank<=3),0) AS top3_buyer_net_value,
 COALESCE(SUM(net) FILTER(WHERE net>0),0) AS positive_net_value_total,
 COALESCE(SUM(net) FILTER(WHERE net>0 AND buyer_rank<=3),0)::double precision/
 NULLIF(SUM(net) FILTER(WHERE net>0)::double precision,0) AS top3_buyer_share
 FROM ranked GROUP BY 1
)
SELECT json_build_object(
 'expected',(SELECT json_agg(e ORDER BY market_board) FROM expected e),
 'stored',(SELECT json_agg(f ORDER BY market_board) FROM public."Feature_03_Stock_Broker_Daily_INDEX" f WHERE ticker='IHSG' AND date=DATE '2026-08-31'),
 'top_three_buyers',(SELECT json_agg(r ORDER BY market_board,buyer_rank) FROM ranked r WHERE net>0 AND buyer_rank<=3),
 'feature5_coverage_columns',(SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='public' AND table_name='Feature_05_Foreign_Domestic_Broker_Detail_INDEX' AND column_name IN ('frequency_source_rows','buy_freq_known_rows','sell_freq_known_rows','buy_freq_missing_rows','sell_freq_missing_rows')));
