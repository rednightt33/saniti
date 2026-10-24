import re, sys
from pgq import q
Q = {
'P1 ohlcv BBCA 1y': """select date,open,high,low,close,volume from "Price_Stock_Indonesia_IDX" where ticker='BBCA' and timeframe='Daily' and is_final and date between '2025-10-23' and '2026-10-23' order by date""",
'P2 ohlcv BBCA all': """select date,open,high,low,close,volume from "Price_Stock_Indonesia_IDX" where ticker='BBCA' and timeframe='Daily' and is_final order by date""",
'P3 ohlcv BBCA+IHSG all': """select ticker,date,close from "Price_Stock_Indonesia_IDX" where ticker in ('BBCA','IHSG') and timeframe='Daily' and is_final order by ticker,date""",
'R1 raw broker BBCA 1d': """select "Broker",sum("Buy Value"),sum("Sell Value"),sum("Buy Lots"),sum("Sell Lots") from "IDX_Broker_Summary" where "Symbol"='BBCA' and "Date"='2026-08-31' group by 1""",
'R2 raw broker BBCA 20d': """select "Broker",sum("Buy Value"),sum("Sell Value") from "IDX_Broker_Summary" where "Symbol"='BBCA' and "Date" between '2026-08-03' and '2026-08-31' group by 1""",
'R3 raw broker BBCA 1y': """select "Broker",sum("Buy Value"),sum("Sell Value") from "IDX_Broker_Summary" where "Symbol"='BBCA' and "Date" between '2025-09-01' and '2026-08-31' group by 1""",
'F1 f05 broker BBCA 1d': """select broker,sum(buy_value),sum(sell_value),sum(buy_lots),sum(sell_lots) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and trade_date='2026-08-31' group by 1""",
'F2 f05 broker BBCA 20d': """select broker,sum(buy_value),sum(sell_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and trade_date between '2026-08-03' and '2026-08-31' group by 1""",
'F3 f05 broker BBCA 1y': """select broker,sum(buy_value),sum(sell_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and trade_date between '2025-09-01' and '2026-08-31' group by 1""",
'F4 f05 flow BBCA all, Foreign, daily': """select trade_date,sum(net_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and investor_type='Foreign' group by 1 order by 1""",
'F5 f05 flow BBCA 3y, 3 brokers': """select trade_date,sum(net_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and trade_date >= '2023-09-01' and broker = any('{YP,AK,ZP}') group by 1 order by 1""",
'F6 f05 inventory 5 brokers 30d': """select trade_date,broker,sum(net_lots),sum(net_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='BBCA' and trade_date between '2026-07-20' and '2026-08-31' and broker = any('{YP,AK,ZP,CC,BK}') group by 1,2 order by 1,2""",
'F7 f05 flow GOTO all, all inv': """select trade_date,sum(net_value) from "Feature_05_Foreign_Domestic_Broker_Detail" where ticker='GOTO' group by 1 order by 1""",
'S1 f06 flow BBCA all Foreign': """select trade_date,sum(foreign_net_1d) from "Feature_06_Foreign_Domestic" where ticker='BBCA' group by 1 order by 1""",
}
only = sys.argv[1:] 
for k, sql in Q.items():
    if only and not any(k.startswith(o) for o in only): continue
    r = q('EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) ' + sql)
    if 'error' in r: print(k, 'ERROR', r['error'][:200]); continue
    lines = [x[0] for x in r['rows']]
    ex = next((l for l in lines if 'Execution Time' in l), '')
    plan = [l.strip() for l in lines if re.search(r'Scan|Buffers: shared', l)][:6]
    top = lines[0]
    rows = re.search(r'actual time=\S+ rows=(\d+)', top)
    print(f'## {k}: {ex.strip()} | out rows {rows.group(1) if rows else "?"}')
    for l in plan: print('   ', l[:170])
