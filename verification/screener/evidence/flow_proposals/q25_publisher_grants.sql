SELECT t, has_table_privilege('terminal_publisher_login', t, 'SELECT') publisher_select
FROM unnest(ARRAY['public."Feature_03_Stock_Broker_Daily"','public."Feature_05_Foreign_Domestic_Broker_Detail"','public."Feature_06_Foreign_Domestic"','public."IDX_Broker_Profile"','public."Feature_02_Broker_Rolling"']) t
