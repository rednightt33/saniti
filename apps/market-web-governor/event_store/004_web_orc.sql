-- Orchestrator web route (POST /v1/orc/web, PLAN_2026-10-05.md item 12): a cache of shaped results per need and a
-- budget ledger per run. The routes /v1/fact, /v1/ask, /v1/web-needs, /v1/search and /v1/fetch and their tables are not
-- touched. Idempotent: safe to run again.
CREATE TABLE IF NOT EXISTS web_orc_result (
    cache_key   text        PRIMARY KEY CHECK (cache_key ~ '^[0-9a-f]{64}$'),
    need        text        NOT NULL CHECK (length(need) BETWEEN 3 AND 500),
    purpose     text        NOT NULL CHECK (purpose IN ('CITE', 'CONTEXT')),
    status      text        NOT NULL CHECK (status IN ('OK', 'PARTIAL', 'NOT_FOUND')),
    result      jsonb       NOT NULL,
    model       text        NOT NULL,
    cost_usd    numeric(10, 6),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS web_orc_result_expires_at_idx ON web_orc_result (expires_at);

CREATE TABLE IF NOT EXISTS web_orc_budget (
    budget_key  text          PRIMARY KEY CHECK (length(budget_key) BETWEEN 1 AND 200),
    calls       integer       NOT NULL DEFAULT 0 CHECK (calls >= 0),
    cost_usd    numeric(12, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    updated_at  timestamptz   NOT NULL DEFAULT now(),
    expires_at  timestamptz   NOT NULL
);
CREATE INDEX IF NOT EXISTS web_orc_budget_expires_at_idx ON web_orc_budget (expires_at);

COMMENT ON TABLE web_orc_result IS 'Shaped results of market-web-governor POST /v1/orc/web (facts, numbers, events, series, lists with verbatim quotes and a citable envelope). Retained WEB_ORC_CACHE_DAYS.';
COMMENT ON COLUMN web_orc_result.result IS 'The route response without its budget: {status, result_id, depth, items, citable, conflicts, sources, warnings}.';
COMMENT ON TABLE web_orc_budget IS 'Calls and cost spent per orchestrator run (budget_key, one user turn) by POST /v1/orc/web; bounded by WEB_ORC_MAX_CALLS_PER_RUN and WEB_ORC_MAX_USD_PER_RUN. Retained one day.';

DO $roles$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_writer') THEN
        GRANT SELECT, INSERT, DELETE ON web_orc_result TO web_event_writer;
        GRANT SELECT, INSERT, UPDATE, DELETE ON web_orc_budget TO web_event_writer;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_reader') THEN
        GRANT SELECT ON web_orc_result, web_orc_budget TO web_event_reader;
    END IF;
END
$roles$;
