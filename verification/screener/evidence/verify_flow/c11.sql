with u as (select "Ticker" t from "IDX_Stock_Universe" where "Security Type"='stock'),
w as (select ticker, sum(foreign_net_1d) allb, sum(foreign_net_1d) filter (where market_board='Regular') rg
      from "Feature_06_Foreign_Domestic" where trade_date between date '2026-09-30' and date '2026-10-27' and ticker in (select t from u) group by 1)
select count(*) n, count(*) filter (where allb <> coalesce(rg,0)) differ,
 count(*) filter (where abs(allb - coalesce(rg,0)) > 0.1*greatest(abs(coalesce(rg,0)),1)) gt10pct,
 count(*) filter (where sign(allb) <> sign(coalesce(rg,0))) signflip,
 count(*) filter (where sign(allb) <> sign(coalesce(rg,0)) and sign(allb)<>0 and sign(coalesce(rg,0))<>0) strict_flip
from w;;
with u as (select "Ticker" t from "IDX_Stock_Universe" where "Security Type"='stock')
select ticker, round(sum(foreign_net_1d) filter (where market_board='Regular')/1e9,2) rg, round(sum(foreign_net_1d)/1e9,2) allb from "Feature_06_Foreign_Domestic" where trade_date between date '2026-09-30' and date '2026-10-27' and ticker in ('CARE') group by 1
