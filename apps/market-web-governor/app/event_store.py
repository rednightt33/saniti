"""Writer for the web research event store (Postgres-E8GM, table web_event_item). The governor's role can only
INSERT; a row that already exists for the same (web_need_id, evidence_id) is skipped."""
from __future__ import annotations

import json
from typing import Any, Protocol

COLUMNS = (
    "item_id", "card_id", "card_rank", "question", "verdict", "summary", "limitations", "analysis_mode", "tickers",
    "entities", "event_cluster_id", "event_date", "event_date_precision", "published_at", "published_precision",
    "published_at_source", "retrieved_at", "anchor_event_description", "anchor_event_date", "temporal_status",
    "lead_time_days", "relation_to_anchor", "publisher", "url", "domain", "source_tier", "source_verified",
    "source_note", "copy_of_evidence_id", "quote", "content_sha256", "web_need_id", "evidence_id", "citation_id",
    "classification_status", "event_type", "impact_level", "impact_rule_id", "impact_capped", "impact_scope",
    "novelty", "attribution", "certainty", "materiality_metric", "materiality_value", "materiality_evidence",
    "impact_rationale", "impact_confidence", "rubric_version", "review_status", "review_reason", "model_slot",
    "model", "classifier_model", "locale",
)
JSON_COLUMNS = {"limitations", "entities"}


class EventStore(Protocol):
    def write(self, rows: list[dict[str, Any]]) -> int: ...


class EventStoreError(RuntimeError):
    pass


class PostgresEventStore:
    def __init__(self, url: str):
        self.url = url

    def write(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        import psycopg

        placeholders = ", ".join(["%s"] * len(COLUMNS))
        sql = (f"INSERT INTO web_event_item ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
               "ON CONFLICT DO NOTHING")  # no conflict target: an INSERT-only role needs no SELECT
        values = [
            tuple(json.dumps(row.get(column)) if column in JSON_COLUMNS else row.get(column) for column in COLUMNS)
            for row in rows
        ]
        try:
            with psycopg.connect(self.url, connect_timeout=10, application_name="market-web-governor") as connection:
                with connection.cursor() as cursor:
                    cursor.executemany(sql, values)
                    written = cursor.rowcount
                connection.commit()
        except psycopg.Error as exc:
            # Never include the connection string or row values in the message.
            raise EventStoreError(f"event store write failed: {type(exc).__name__}") from exc
        return max(written, 0)
