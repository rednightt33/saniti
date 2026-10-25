WITH target AS (SELECT unnest(ARRAY['Feature_01_Stock_Daily_INDEX','Feature_02_Broker_Rolling_INDEX',
 'Feature_03_Stock_Broker_Daily_INDEX','Feature_04_Technical_Indicator_INDEX',
 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX','Feature_06_Foreign_Domestic_INDEX','Feature_Vocabulary']) AS name)
SELECT jsonb_build_object('checked_at',clock_timestamp(),
 'tables',(SELECT jsonb_agg(jsonb_build_object('name',c.relname,'comment',obj_description(c.oid)))
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN (SELECT name FROM target)),
 'columns',(SELECT jsonb_agg(jsonb_build_object('table_name',c.table_name,'column_name',c.column_name,'ordinal_position',c.ordinal_position,
  'data_type',c.data_type,'is_nullable',c.is_nullable,'column_default',c.column_default,'definition',m.definition) ORDER BY c.table_name,c.ordinal_position)
  FROM information_schema.columns c LEFT JOIN public."Column_Catalog" m ON m.table_schema=c.table_schema AND m.table_name=c.table_name AND m.column_name=c.column_name
  WHERE c.table_schema='public' AND c.table_name IN (SELECT name FROM target)),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('table_name',r.relname,'name',c.conname,'type',c.contype,'definition',pg_get_constraintdef(c.oid)))
  FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid JOIN pg_namespace n ON n.oid=r.relnamespace
  WHERE n.nspname='public' AND r.relname IN (SELECT name FROM target)),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('table_name',tablename,'name',indexname,'definition',indexdef)) FROM pg_indexes WHERE schemaname='public' AND tablename IN (SELECT name FROM target)),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('table_name',r.relname,'name',t.tgname,'definition',pg_get_triggerdef(t.oid)))
  FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid JOIN pg_namespace n ON n.oid=r.relnamespace
  WHERE NOT t.tgisinternal AND n.nspname='public' AND r.relname IN (SELECT name FROM target)));
