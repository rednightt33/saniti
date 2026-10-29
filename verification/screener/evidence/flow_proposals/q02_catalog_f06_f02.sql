SELECT feature_table, feature_column, unit, allowed_aggregations, point_in_time_safe, left(calculation,350) calc, left(misuse_warning,450) misuse, left(null_rule,200) nullrule
FROM "Feature_Catalog" WHERE is_active AND (
 (feature_table='Feature_06_Foreign_Domestic' AND feature_column IN ('foreign_net_1d','foreign_buy_1d','foreign_net_20d','foreign_net_turnover_ratio_20d','foreign_buy_share_1d','foreign_net_zscore_20d_base252d','foreign_buy_days_20d','foreign_buy_freq_1d','foreign_strength_20d','foreign_cumulative_net','foreign_net_percentile_20d_base252d','foreign_avg_buy_value_per_freq_1d','foreign_buy_value_per_freq_change_5d_vs_prev20d','foreign_freq_imbalance_20d','market_board'))
 OR (feature_table='Feature_02_Broker_Rolling' AND feature_column IN ('broker_classification','net_value_20d','buy_day_ratio_20d','net_value_zscore_20d','largest_buy_day_share_20d','positive_net_value_20d','market_board')))
ORDER BY 1,2;;
SELECT feature_column, misuse_warning FROM "Feature_Catalog" WHERE is_active AND feature_table='Feature_03_Stock_Broker_Daily' AND feature_column='total_buy_value'
