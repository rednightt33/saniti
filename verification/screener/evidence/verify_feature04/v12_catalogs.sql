select feature_table, version, is_active, count(*) from public."Feature_Catalog" where feature_table ilike 'Feature_04%' group by 1,2,3 order by 1,2;;
select table_name, left(update_rule, 600) from public."Table_Catalog" where table_name ilike 'Feature_04%';;
select table_name, ai_allowed, count(*), string_agg(column_name, ',' order by column_name) filter (where not ai_allowed) from public."AI_column_catalog" where table_name ilike 'Feature_04%' group by 1,2;;
select target_table, status, count(*) from public."AI_calculation_catalog" where target_table ilike 'Feature_04%' group by 1,2;;
select table_name, is_active, ai_access_level from public."AI_table_catalog" where table_name ilike 'Feature_04%';;
select source_table, feature_number, count(*) from public."Feature_Vocabulary" group by 1,2 order by 2,1
