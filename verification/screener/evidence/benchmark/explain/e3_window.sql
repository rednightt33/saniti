explain (analyze, buffers, timing)
select ticker, date, open::float8, high::float8, low::float8, close::float8, volume::float8
from public."Price_Stock_Indonesia_IDX" where timeframe = 'Daily' and is_final and date >= date '2023-10-01' order by ticker, date ;;
explain (analyze, buffers, timing)
select ticker, date, open::float8, high::float8, low::float8, close::float8, volume::float8
from public."Price_Stock_Indonesia_IDX" where timeframe = 'Daily' and is_final order by ticker, date
