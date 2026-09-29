-- Lean web research answers (POST /v1/ask). One row per question; kept 30 days (expires_at), then deleted by the
-- governor. Idempotent: safe to run again.
CREATE TABLE IF NOT EXISTS web_ask (
    ask_id        text        PRIMARY KEY,
    request_id    text        NOT NULL UNIQUE,
    question      text        NOT NULL CHECK (length(question) BETWEEN 3 AND 1000),
    as_of         date        NOT NULL,
    status        text        NOT NULL CHECK (status IN ('ANSWERED', 'NO_SOURCES', 'FAILED')),
    answer        text,
    plan          jsonb       NOT NULL,
    citations     jsonb       NOT NULL,
    sources       jsonb       NOT NULL,
    warnings      jsonb       NOT NULL,
    model         text        NOT NULL,
    cost_usd      numeric(10, 6),
    seconds       numeric(8, 2),
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS web_ask_created_at_idx ON web_ask (created_at DESC);
CREATE INDEX IF NOT EXISTS web_ask_expires_at_idx ON web_ask (expires_at);

COMMENT ON TABLE web_ask IS 'Answers of market-web-governor POST /v1/ask: question, answer, cited and listed sources. Retained 30 days.';
COMMENT ON COLUMN web_ask.citations IS 'Sources cited in the answer: [{n, date, publisher, title, url, via}]; dates come from the source list, never from the model.';
COMMENT ON COLUMN web_ask.sources IS 'Every source shown to the model, oldest first: [{n, date, publisher, title, url, via}].';

DO $roles$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_writer') THEN
        -- SELECT for idempotent replay by request_id; DELETE for the 30-day retention.
        GRANT SELECT, INSERT, DELETE ON web_ask TO web_event_writer;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_reader') THEN
        GRANT SELECT ON web_ask TO web_event_reader;
    END IF;
END
$roles$;
