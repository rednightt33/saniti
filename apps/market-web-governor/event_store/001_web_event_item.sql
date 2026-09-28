-- Web research event store (Postgres-E8GM), migration 001.
-- One row per news or event item found by market-web-governor. Rows are immutable: the writer role can only INSERT;
-- a correction is a new row. Review columns are changed only by a separate review role (not created here).
-- Roles are created by the migration job with passwords passed as psql variables; no secret is stored in this file.

BEGIN;

CREATE TABLE IF NOT EXISTS web_event_item (
    item_id                 text PRIMARY KEY,
    created_at              timestamptz NOT NULL DEFAULT now(),
    record_version          integer NOT NULL DEFAULT 1,

    -- card (repeated on each row of one card)
    card_id                 text NOT NULL,
    card_rank               integer NOT NULL CHECK (card_rank >= 1),
    question                text NOT NULL,
    verdict                 text NOT NULL CHECK (verdict IN ('CONFIRMED','PARTIAL','NOT_FOUND','CONTRADICTED','BLOCKED')),
    summary                 text,
    limitations             jsonb NOT NULL DEFAULT '[]'::jsonb,
    analysis_mode           text NOT NULL CHECK (analysis_mode IN ('EVIDENCE','EVENT_PRECURSOR')),

    -- subject
    tickers                 text[] NOT NULL DEFAULT '{}',
    entities                jsonb NOT NULL DEFAULT '[]'::jsonb,
    event_cluster_id        text,

    -- dates
    event_date              date,
    event_date_precision    text NOT NULL CHECK (event_date_precision IN ('DAY','MONTH','QUARTER','YEAR','UNKNOWN')),
    published_at            date,
    published_precision     text NOT NULL CHECK (published_precision IN ('DAY','MONTH','UNKNOWN')),
    published_at_source     text NOT NULL CHECK (published_at_source IN ('PROVIDER','HTML_META','URL','TEXT','UNKNOWN')),
    retrieved_at            timestamptz NOT NULL,

    -- anchor (EVENT_PRECURSOR)
    anchor_event_description text,
    anchor_event_date       date,
    temporal_status         text CHECK (temporal_status IN ('PRE_EVENT','POST_EVENT_RETROSPECTIVE','UNDATED')),
    lead_time_days          integer,
    relation_to_anchor      text CHECK (relation_to_anchor IN ('DIRECT','INDIRECT','CONTEXT','COUNTER','NOT_APPLICABLE')),

    -- source (decided by code)
    publisher               text NOT NULL,
    url                     text NOT NULL,
    domain                  text NOT NULL,
    source_tier             text NOT NULL CHECK (source_tier IN ('PRIMARY','TRUSTED_SECONDARY','SECONDARY','UNKNOWN')),
    source_verified         boolean NOT NULL,
    source_note             text,
    copy_of_evidence_id     text,
    quote                   text NOT NULL CHECK (length(quote) > 0),
    content_sha256          text NOT NULL,

    -- audit link to market-web-governor (kept there 30 days)
    web_need_id             text NOT NULL,
    evidence_id             text NOT NULL,
    citation_id             text NOT NULL,

    -- importance (AI interpretation under the rubric; NULL when unclassified)
    classification_status   text NOT NULL CHECK (classification_status IN ('CLASSIFIED','UNCLASSIFIED','NOT_REQUESTED')),
    event_type              text CHECK (event_type IN ('M_AND_A','CHANGE_OF_CONTROL','CAPITAL_RAISE','DIVIDEND','BUYBACK',
                                'EARNINGS','GUIDANCE','MANAGEMENT_CHANGE','INVESTMENT','CONTRACT','PARTNERSHIP','REGULATORY',
                                'LEGAL','RATING','CORPORATE_GOVERNANCE','OPERATIONS','MARKETING','MARKET_ACTIVITY','MACRO',
                                'OTHER')),
    impact_level            smallint CHECK (impact_level BETWEEN 1 AND 5),
    impact_rule_id          text,
    impact_capped           boolean NOT NULL DEFAULT false,
    impact_scope            text CHECK (impact_scope IN ('ISSUER','GROUP','SECTOR','MARKET')),
    novelty                 text CHECK (novelty IN ('NEW','UPDATE','REPEAT','UNKNOWN')),
    attribution             text CHECK (attribution IN ('OFFICIAL_DOCUMENT','OFFICIAL_STATEMENT','NAMED_SOURCE',
                                'ANONYMOUS_SOURCE','ANALYST_OPINION','NO_ATTRIBUTION')),
    certainty               text CHECK (certainty IN ('OFFICIAL','REPORTED','RUMOUR','UNVERIFIED')),
    materiality_metric      text CHECK (materiality_metric IN ('TRANSACTION_TO_EQUITY_PCT','TRANSACTION_TO_ASSETS_PCT',
                                'CONTRACT_TO_REVENUE_PCT','OWNERSHIP_PCT','NONE')),
    materiality_value       numeric,
    materiality_evidence    text,
    impact_rationale        text CHECK (impact_rationale IS NULL OR length(impact_rationale) <= 300),
    impact_confidence       text CHECK (impact_confidence IN ('HIGH','MEDIUM','LOW')),
    rubric_version          text,

    -- review
    review_status           text NOT NULL DEFAULT 'UNREVIEWED'
                                CHECK (review_status IN ('UNREVIEWED','NEEDS_REVIEW','CONFIRMED','OVERRIDDEN')),
    review_reason           text,
    reviewed_by             text,
    reviewed_at             timestamptz,
    review_note             text,

    -- provenance
    model_slot              integer,
    model                   text,
    classifier_model        text,
    locale                  text NOT NULL,

    CONSTRAINT web_event_item_classified_complete CHECK (
        classification_status <> 'CLASSIFIED'
        OR (event_type IS NOT NULL AND impact_level IS NOT NULL AND impact_rule_id IS NOT NULL
            AND certainty IS NOT NULL AND rubric_version IS NOT NULL)),
    CONSTRAINT web_event_item_once UNIQUE (web_need_id, evidence_id)
);

CREATE INDEX IF NOT EXISTS web_event_item_ticker_date_idx ON web_event_item USING gin (tickers);
CREATE INDEX IF NOT EXISTS web_event_item_event_date_idx ON web_event_item (event_date, impact_level);
CREATE INDEX IF NOT EXISTS web_event_item_published_idx ON web_event_item (published_at);
CREATE INDEX IF NOT EXISTS web_event_item_card_idx ON web_event_item (card_id, card_rank);

COMMENT ON TABLE web_event_item IS
  'Web research items from market-web-governor: one row per news or event item; immutable; importance fields are '
  'AI interpretation under rubric_version.';

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_writer') THEN
        CREATE ROLE web_event_writer LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_event_reader') THEN
        CREATE ROLE web_event_reader LOGIN;
    END IF;
END
$roles$;

REVOKE ALL ON web_event_item FROM PUBLIC;
REVOKE ALL ON web_event_item FROM web_event_writer, web_event_reader;
GRANT INSERT ON web_event_item TO web_event_writer;
GRANT SELECT ON web_event_item TO web_event_reader;

COMMIT;
