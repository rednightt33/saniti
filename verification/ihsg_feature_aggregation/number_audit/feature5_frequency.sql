WITH source AS MATERIALIZED (
 SELECT * FROM public."IDX_Broker_Summary" WHERE "Date"=DATE '2026-08-31'
), agg AS (
 SELECT "Broker" AS broker,"Investor Type" AS investor_type,"Market Board" AS market_board,
 count(*) AS input_rows,count(buy_freq) AS buy_known_rows,count(sell_freq) AS sell_known_rows,
 sum(buy_freq) AS known_buy_sum,sum(sell_freq) AS known_sell_sum,
 CASE WHEN count(buy_freq)=count(*) THEN sum(buy_freq) END AS expected_buy_freq,
 CASE WHEN count(sell_freq)=count(*) THEN sum(sell_freq) END AS expected_sell_freq
 FROM source GROUP BY 1,2,3
), compared AS (
 SELECT a.*,i.buy_freq AS index_buy_freq,i.sell_freq AS index_sell_freq,
 i.buy_freq IS NOT DISTINCT FROM a.expected_buy_freq AS buy_match,
 i.sell_freq IS NOT DISTINCT FROM a.expected_sell_freq AS sell_match
 FROM agg a LEFT JOIN public."Feature_05_Foreign_Domestic_Broker_Detail" i
 ON i.ticker='IHSG' AND i.trade_date=DATE '2026-08-31' AND i.broker=a.broker
 AND i.investor_type=a.investor_type AND i.market_board=a.market_board
)
SELECT json_build_object(
 'comparison_summary',(SELECT json_agg(x ORDER BY market_board) FROM (
 SELECT market_board,count(*) AS index_groups,sum(input_rows) AS source_rows,
 sum(input_rows-buy_known_rows) AS missing_buy_rows,sum(input_rows-sell_known_rows) AS missing_sell_rows,
 sum(known_buy_sum) AS source_known_buy_sum,sum(known_sell_sum) AS source_known_sell_sum,
 sum(index_buy_freq) AS index_known_buy_sum,sum(index_sell_freq) AS index_known_sell_sum,
 count(index_buy_freq) AS index_buy_available,count(index_sell_freq) AS index_sell_available,
 count(*) FILTER(WHERE NOT buy_match) AS buy_mismatches,count(*) FILTER(WHERE NOT sell_match) AS sell_mismatches
 FROM compared GROUP BY 1)x),
 'pd_groups',(SELECT json_agg(x ORDER BY market_board,investor_type) FROM compared x WHERE broker='PD'),
 'non_index_detail_summary',(SELECT json_agg(x ORDER BY market_board) FROM (
 SELECT market_board,count(*) AS rows,sum(buy_freq) AS known_buy_sum,sum(sell_freq) AS known_sell_sum,
 count(*) FILTER(WHERE buy_freq IS NULL) AS missing_buy_rows,count(*) FILTER(WHERE sell_freq IS NULL) AS missing_sell_rows
 FROM public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE trade_date=DATE '2026-08-31' AND ticker<>'IHSG' GROUP BY 1)x),
 'pd_emas',(SELECT json_agg(x ORDER BY investor_type,market_board) FROM (
 SELECT ticker,broker,investor_type,market_board,buy_value,sell_value,buy_freq,sell_freq
 FROM public."Feature_05_Foreign_Domestic_Broker_Detail" WHERE ticker='EMAS' AND trade_date=DATE '2026-08-31' AND broker='PD')x),
 'missing_symbol_examples',(SELECT json_agg(x) FROM (
 SELECT "Symbol" AS ticker,"Broker" AS broker,"Investor Type" AS investor_type,"Market Board" AS market_board,
 "Buy Value" AS buy_value,"Sell Value" AS sell_value,buy_freq,sell_freq FROM source
 WHERE "Broker"='PD' AND "Market Board"='Regular' AND (buy_freq IS NULL OR sell_freq IS NULL) ORDER BY "Symbol","Investor Type" LIMIT 10)x));
