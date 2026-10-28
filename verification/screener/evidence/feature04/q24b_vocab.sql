select source_table, feature_number, language_code, count(*) from public."Feature_Vocabulary" group by 1,2,3 order by 1,2,3
