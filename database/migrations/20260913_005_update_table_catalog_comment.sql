BEGIN;

SET LOCAL lock_timeout = '5s';

COMMENT ON TABLE public."Table_Catalog" IS
    'Curated meanings, grain, provenance, and update contracts for approved public data tables; not a freshness monitor.';

COMMIT;
