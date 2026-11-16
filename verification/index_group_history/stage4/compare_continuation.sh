P="psql -h /home/pgr/pg -p 55432 -U postgres -q"
for t in Feature_01_Stock_Daily_INDEX Feature_02_Broker_Rolling_INDEX Feature_03_Stock_Broker_Daily_INDEX Feature_04_Technical_Indicator_INDEX Feature_05_Foreign_Domestic_Broker_Detail_INDEX Feature_06_Foreign_Domestic_INDEX; do
  $P -d ent2 -c "\copy (SELECT * FROM \"$t\" WHERE ticker <> 'IHSG') TO '/home/pgr/$t.csv' CSV"
  $P -d ent -c "DROP TABLE IF EXISTS \"cmp_$t\"" -c "CREATE TABLE \"cmp_$t\" (LIKE \"$t\")" -c "\copy \"cmp_$t\" FROM '/home/pgr/$t.csv' CSV"
  $P -d ent -At -c "SELECT '$t', (SELECT count(*) FROM \"$t\" WHERE ticker<>'IHSG'), (SELECT count(*) FROM \"cmp_$t\"), (SELECT count(*) FROM ((SELECT (to_jsonb(a)-'calculated_at') FROM \"$t\" a WHERE ticker<>'IHSG' EXCEPT ALL SELECT (to_jsonb(c)-'calculated_at') FROM \"cmp_$t\" c) UNION ALL (SELECT (to_jsonb(c)-'calculated_at') FROM \"cmp_$t\" c EXCEPT ALL SELECT (to_jsonb(a)-'calculated_at') FROM \"$t\" a WHERE ticker<>'IHSG')) x)"
done
