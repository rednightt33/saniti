DO $$
DECLARE f int; c text; n bigint; a bigint; b bigint;
BEGIN
 FOR f IN 1..6 LOOP
  SELECT string_agg(quote_ident(column_name), ',' ORDER BY ordinal_position) INTO c FROM information_schema.columns
   WHERE table_name = 'reg_old_calc'||f AND column_name <> 'calculated_at';
  EXECUTE format('SELECT count(*) FROM ((SELECT %1$s FROM reg_old_calc%2$s EXCEPT ALL SELECT %1$s FROM reg_new_calc%2$s) UNION ALL (SELECT %1$s FROM reg_new_calc%2$s EXCEPT ALL SELECT %1$s FROM reg_old_calc%2$s)) x', c, f) INTO n;
  EXECUTE format('SELECT count(*) FROM reg_old_calc%s', f) INTO a; EXECUTE format('SELECT count(*) FROM reg_new_calc%s', f) INTO b;
  RAISE NOTICE 'F0% old=% new=% differing=%', f, a, b, n;
 END LOOP;
END $$;
