-- Execute with the market Postgres administrative connection. No mutations; do not print credentials.
BEGIN READ ONLY;
SET LOCAL statement_timeout='10s';
SELECT current_database(), current_user, version();
SELECT n.nspname, c.relname, c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='edge_bff' OR (n.nspname='public' AND c.relname IN ('AI_conversation','AI_conversation_turn'))
ORDER BY 1,2;
SELECT table_schema,table_name,column_name,data_type,is_nullable
FROM information_schema.columns WHERE table_schema='edge_bff'
 OR (table_schema='public' AND table_name IN ('AI_conversation','AI_conversation_turn'))
ORDER BY table_schema,table_name,ordinal_position;
SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls,rolcanlogin
FROM pg_roles WHERE rolname IN ('edge_bff_login','edge_bff_runtime','market_ai_conversation','market_ai_conversation_store');
SELECT grantee,table_schema,table_name,privilege_type
FROM information_schema.table_privileges WHERE grantee='PUBLIC' OR grantee LIKE 'edge_bff%'
 OR (table_schema='public' AND table_name IN ('AI_conversation','AI_conversation_turn'));
SELECT r.rolname AS granted_role,u.rolname AS member FROM pg_auth_members m
JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles u ON u.oid=m.member
WHERE u.rolname LIKE 'edge_bff%' OR u.rolname='market_ai_conversation';
SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes
WHERE schemaname='edge_bff' OR (schemaname='public' AND tablename IN ('AI_conversation','AI_conversation_turn'));
SELECT n.nspname,c.relname,con.conname,pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='edge_bff' OR (n.nspname='public' AND c.relname IN ('AI_conversation','AI_conversation_turn'));
ROLLBACK;
