with w as (select ticker, sum(foreign_net_1d) f, sum(foreign_buy_1d+domestic_buy_1d) t, count(distinct trade_date) nreg
           from "Feature_06_Foreign_Domestic" where trade_date between date '2026-09-30' and date '2026-10-27' and market_board='Regular' group by 1),
s as (select ticker, count(distinct trade_date) nany from "Feature_06_Foreign_Domestic" where trade_date between date '2026-09-30' and date '2026-10-27' group by 1),
l as (select ticker, foreign_net_turnover_ratio_20d r20, foreign_net_20d f20 from "Feature_06_Foreign_Domestic" where trade_date=date '2026-10-27' and market_board='Regular')
select count(*) n,
 count(*) filter (where abs(l.r20 - 100*w.f/nullif(w.t,0)) < 1e-9) eq_ratio,
 count(*) filter (where l.f20 = w.f) eq_net,
 count(*) filter (where not coalesce(abs(l.r20 - 100*w.f/nullif(w.t,0)) < 1e-9,false) and s.nany = 20) ne_with_20_any,
 count(*) filter (where not coalesce(abs(l.r20 - 100*w.f/nullif(w.t,0)) < 1e-9,false) and w.nreg = 20) ne_with_20_reg,
 count(*) filter (where l.r20 is null) stored_null
from l join w using (ticker) join s using (ticker)
