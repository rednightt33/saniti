SELECT feature_table, feature_column, unit, allowed_aggregations, point_in_time_safe, left(calculation,400) calc, left(misuse_warning,500) misuse
FROM "Feature_Catalog" WHERE is_active AND feature_table IN ('Feature_03_Stock_Broker_Daily','Feature_05_Foreign_Domestic_Broker_Detail') ORDER BY 1,2
