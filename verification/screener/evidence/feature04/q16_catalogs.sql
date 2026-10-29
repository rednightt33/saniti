select feature_table, version, is_active, count(*) from public."Feature_Catalog" where feature_table like 'Feature_04%' or feature_table like 'Feature04%' group by 1,2,3 order by 1,2,3;;
select table_name, count(*) from public."Column_Catalog" where table_name like 'Feature_04%' group by 1;;
select table_name, category, documentation_status, left(update_rule,120) update_rule, array_length(related_functions,1) nfun from public."Table_Catalog" where table_name like 'Feature_04%' or table_name like 'Feature04%' or table_name like 'Monitoring_Feature04%' or table_name='feature04_backfill_log' order by 1;;
select table_name, is_active, left(coalesce(description,''),80) from public."AI_table_catalog" where table_name like 'Feature_04%';;
select table_name, ai_allowed, count(*) from public."AI_column_catalog" where table_name like 'Feature_04%' group by 1,2 order by 1,2;;
select target_table, status, count(*) from public."AI_calculation_catalog" where target_table like 'Feature_04%' group by 1,2;;
select grantee, privilege_type, table_name from information_schema.role_table_grants where table_name in ('Feature_04_Technical_Indicator','Feature_04_Technical_Indicator_INDEX') order by 3,1,2
