explain (analyze, buffers, timing)
select u."Ticker", x.last_date, x.close, x.prev_close, x.close / nullif(x.prev_close, 0) - 1 as chg_1d, x.atv20, x.n20
from public."IDX_Stock_Universe" u
cross join lateral (
  select max(date) filter (where rn = 1) last_date, max(close) filter (where rn = 1) close, max(close) filter (where rn = 2) prev_close,
         avg(close * volume) filter (where rn <= 20) atv20, count(*) filter (where rn <= 20) n20
  from (select p.date, p.close, p.volume, row_number() over (order by p.date desc) rn
        from public."Price_Stock_Indonesia_IDX" p
        where p.ticker = u."Ticker" and p.is_final and p.timeframe = 'Daily'
        order by p.date desc limit 21) s) x ;;
explain (analyze, buffers, timing)
with w as (
  select ticker, date, close,
         lag(close) over (partition by ticker order by date) prev_close,
         avg(close * volume) over (partition by ticker order by date rows between 19 preceding and current row) atv20,
         count(*) over (partition by ticker order by date rows between 19 preceding and current row) n20,
         max(date) over (partition by ticker) last_date
  from public."Price_Stock_Indonesia_IDX"
  where is_final and timeframe = 'Daily' and date >= date '2026-10-27' - 45)
select ticker, date, close, prev_close, close / nullif(prev_close, 0) - 1 chg_1d, atv20, n20 from w where date = last_date
