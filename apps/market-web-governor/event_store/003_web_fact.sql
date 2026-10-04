-- Light fact finder (POST /v1/fact, PLAN_FINAL_2026-10-04.md Fase 4): one row per fact key (subject + attribute),
-- replaced on refresh, kept 30 days (expires_at), then deleted by the governor. Only CONFIRMED and CONFLICTING
-- results are kept. Idempotent: safe to run again.
CREATE TABLE IF NOT EXISTS web_fact (
    fact_id     text        PRIMARY KEY,
    fact_key    text        NOT NULL UNIQUE CHECK (fact_key ~ '^[0-9a-f]{64}$'),
    subject     text        NOT NULL CHECK (length(subject) BETWEEN 2 AND 200),
    attribute   text        NOT NULL CHECK (length(attribute) BETWEEN 2 AND 200),
    status      text        NOT NULL CHECK (status IN ('CONFIRMED', 'CONFLICTING', 'PARTIAL', 'NOT_FOUND')),
    value       text,
    versions    jsonb       NOT NULL,
    sources     jsonb       NOT NULL,
    warnings    jsonb       NOT NULL,
    model       text        NOT NULL,
    cost_usd    numeric(10, 6),
    seconds     numeric(8, 2),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS web_fact_expires_at_idx ON web_fact (expires_at);

COMMENT ON TABLE web_fact IS 'Facts found by market-web-governor POST /v1/fact: status decided by code from verbatim quotes. Retained 30 days.';
COMMENT ON COLUMN web_fact.versions IS 'Each value with the domains that state it and their verbatim quotes: [{value, domains, official, quotes: [{source, quote, url, domain, date, source_tier}]}].';
COMMENT ON COLUMN web_fact.sources IS 'Every search result read: [{n, url, domain, title, date, source_tier}].';

DO $roles$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_writer') THEN
        GRANT SELECT, INSERT, DELETE ON web_fact TO web_event_writer;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_reader') THEN
        GRANT SELECT ON web_fact TO web_event_reader;
    END IF;
END
$roles$;
