explain
with cal as (
  select trade_date, row_number() over (order by trade_date desc) k
  from (select distinct date as trade_date from "Feature_03_Stock_Broker_Daily" where date between date '2026-07-31' and date '2026-10-27' and market_board='Regular') x
), w as (
  select f.ticker, c.k,
         sum(f.foreign_net_1d) fnet_all,
         sum(f.foreign_net_1d) filter (where f.market_board='Regular') fnet_reg,
         sum(f.foreign_buy_1d + f.domestic_buy_1d) filter (where f.market_board='Regular') val_reg,
         sum(f.foreign_buy_freq_1d + f.domestic_buy_freq_1d) filter (where f.market_board='Regular') trades_reg,
         max(f.foreign_net_20d) filter (where f.market_board='Regular') stored_fnet20
  from "Feature_06_Foreign_Domestic" f join cal c on c.trade_date = f.trade_date
  where f.trade_date between date '2026-07-31' and date '2026-10-27' and c.k <= 61
  group by f.ticker, c.k
), p as (
  select w.*, row_number() over (partition by ticker order by k) filter_rn
  from w where fnet_reg > 0
), streak as (
  select ticker, count(*) filter (where k = filter_rn) fstreak from p group by ticker
)
select w.ticker,
       sum(fnet_all) filter (where k <= 20) fnet_all_20,
       sum(fnet_reg) filter (where k <= 20) fnet_reg_20,
       max(stored_fnet20) filter (where k = 1) stored_fnet20,
       100 * sum(fnet_reg) filter (where k <= 20) / nullif(sum(val_reg) filter (where k <= 20), 0) fpct_reg_20,
       coalesce(max(s.fstreak), 0) fstreak,
       max(trades_reg) filter (where k = 1) / nullif(avg(trades_reg) filter (where k between 2 and 21), 0) freq_spike_20,
       count(*) filter (where k <= 20) sessions_20
from w left join streak s using (ticker)
group by w.ticker
