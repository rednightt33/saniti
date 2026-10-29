SELECT column_name, data_type FROM information_schema.columns WHERE table_name='Feature_Catalog' ORDER BY ordinal_position;;
SELECT now(), current_setting('statement_timeout') st, current_setting('work_mem') wm, current_setting('shared_buffers') sb
