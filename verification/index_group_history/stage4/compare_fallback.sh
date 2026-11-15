P="psql -h /home/pgr/pg -p 55432 -U postgres -q"
for t in Feature_02_Broker_Rolling_INDEX Feature_03_Stock_Broker_Daily_INDEX Feature_05_Foreign_Domestic_Broker_Detail_INDEX Feature_06_Foreign_Domestic_INDEX; do
  dc=trade_date; case $t in Feature_02*|Feature_03*) dc=date;; esac
  $P -d ent2 -c "\copy (SELECT * FROM \"$t\" WHERE ticker = 'GCTCORP' AND $dc >= '2025-10-15') TO '/home/pgr/g_$t.csv' CSV"
  $P -d ent3 -c "DROP TABLE IF EXISTS \"cmp_$t\"" -c "CREATE TABLE \"cmp_$t\" (LIKE \"$t\")" -c "\copy \"cmp_$t\" FROM '/home/pgr/g_$t.csv' CSV"
  $P -d ent3 -At -c "SELECT '$t', (SELECT count(*) FROM \"cmp_$t\"), (SELECT count(*) FROM ((SELECT (to_jsonb(a)-'calculated_at') FROM \"$t\" a WHERE ticker='GCTCORP' AND $dc >= '2025-10-15' EXCEPT ALL SELECT (to_jsonb(c)-'calculated_at') FROM \"cmp_$t\" c) UNION ALL (SELECT (to_jsonb(c)-'calculated_at') FROM \"cmp_$t\" c EXCEPT ALL SELECT (to_jsonb(a)-'calculated_at') FROM \"$t\" a WHERE ticker='GCTCORP' AND $dc >= '2025-10-15')) x)"
done
