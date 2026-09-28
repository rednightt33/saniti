"""IP2 in the orchestrator: weekly/monthly guidance (AI_ENABLE_DERIVED_FREQUENCY) and the audit outbox
(AI_AUDIT_STORE_ENABLED / AI_AUDIT_STORE_REQUIRED). With both off the orchestrator is unchanged."""
from __future__ import annotations

import json
import os
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from app.audit_outbox import AuditOutbox, sanitize
from app.config import ConfigError, Settings
from app.orchestrator import DERIVED_FREQUENCY_LINE, DERIVED_FREQUENCY_RULES, AgentOrchestrator, build_system_prompt
from app.schemas import AgentRunRequest
from conftest import BASE_ENV, ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import Tools, answer, completed, flow

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "..", "..", "database", "migrations",
                         "20260928_001_create_ai_audit_store.sql")


# ---------------------------------------------------------------------------------------- derived frequency

def test_the_weekly_monthly_rules_are_in_the_prompt_only_when_on() -> None:
    assert build_system_prompt(False, True, derived_frequency=True).endswith(DERIVED_FREQUENCY_RULES)
    assert DERIVED_FREQUENCY_RULES not in build_system_prompt(False, True)
    # the only digits are the DataNeedSpec frequency codes (list markers skipped), never a figure
    body = re.sub(r"(?m)^\d+\. ", "", DERIVED_FREQUENCY_RULES)
    assert set(re.findall(r"\S*\d\S*", body)) == {"1D,", "1W,", "1M,"}
    for phrase in ("never monthly from weekly", "saniti.resample(frame, request)", "period_complete true",
                   "Never sum daily returns", "WEEKLY", "MONTHLY"):
        assert phrase in DERIVED_FREQUENCY_RULES.replace("\n", " ")


def test_derived_frequency_needs_the_dataneed_flow_and_discloses_the_derivation() -> None:
    off = AgentOrchestrator(make_settings(), ScriptedClient([]), Tools([]).registry(), derived_frequency=True)
    assert off.derived_frequency is False and DERIVED_FREQUENCY_RULES not in off.system_prompt
    scripted = ScriptedClient([*flow(), final_response(answer("Return YTD BBCA 12,35%."))])
    derived = {"requests": [{"data_request_id": "data_request_1_A", "analysis_frequency": "1W"}]}
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), scripted,
                              Tools([completed(derived_frequency=derived)]).registry(), derived_frequency=True)
    assert DERIVED_FREQUENCY_RULES in agent.system_prompt
    result = agent.run(AgentRunRequest(request_id="dn", message="Return mingguan BBCA?"))
    assert DERIVED_FREQUENCY_LINE in result.response.limitations
    assert result.execution.analysis_final_status["derived_frequency"] == derived  # provenance in the record


# ---------------------------------------------------------------------------------------- audit outbox

class Outbox:
    def __init__(self, fail: bool = False) -> None:
        self.payloads: list[dict] = []
        self.fail = fail

    def write(self, payload: dict) -> None:
        if self.fail:
            raise OSError("database unavailable")
        self.payloads.append(json.loads(json.dumps(payload, default=str)))


def audited_run(outbox: Outbox, **settings: str):
    scripted = ScriptedClient([*flow(), final_response(answer("Return YTD BBCA 12,35%."))])
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true", **settings), scripted,
                              Tools([completed()], stdout="").registry(), audit_outbox=outbox)
    return agent.run(AgentRunRequest(request_id="dn-audit", conversation_id="conv_" + "a" * 32,
                                     message="Berapa return YTD BBCA?"))


def test_a_finished_run_is_handed_to_the_outbox_with_observable_events_only() -> None:
    outbox = Outbox()
    result = audited_run(outbox)
    [payload] = outbox.payloads
    assert payload["schema"] == "saniti.audit.run_finished/v1" and payload["request_id"] == "dn-audit"
    assert payload["conversation_id"] == "conv_" + "a" * 32
    tools = [e["tool"] for e in payload["events"] if e["type"] == "tool.call"]
    assert tools == ["submit_data_need_spec", "prepare_data_bundle", "open_analysis_session", "run_python",
                     "complete_analysis"]
    assert all(len(e["arguments_sha256"]) == 64 and len(e["result_sha256"]) == 64
               for e in payload["events"] if e["type"] == "tool.call")
    assert [e["type"] for e in payload["events"]].count("model.call") == result.execution.iterations
    assert payload["expected"] == {"execution_ids": ["exe_1"], "completion_ids": ["cmp_1"]}
    assert payload["final_response"]["answer"] == "Return YTD BBCA 12,35%."
    assert payload["summary"]["reasoning_token_count"] == result.execution.reasoning_tokens  # a count, not content
    text = json.dumps(payload)
    assert '"reasoning"' not in text and "encrypted_content" not in text


def test_sanitizing_drops_reasoning_and_redacts_secrets_and_urls() -> None:
    clean = sanitize({"reasoning": "hidden", "items": [{"thinking": "x", "ok": 1}], "api_key": "k" * 40,
                      "Authorization": "Bearer abc", "url": "https://bucket/objects/x?X-Amz-Signature=abc",
                      "note": "a" * 5000})
    assert "reasoning" not in clean and clean["items"] == [{"ok": 1}]
    assert clean["api_key"] == clean["Authorization"] == "[redacted]" and clean["url"] == "[url]"
    assert len(clean["note"]) < 2100


def test_an_audit_outage_never_changes_the_answer_in_optional_mode() -> None:
    baseline = audited_run(Outbox())
    failed = audited_run(Outbox(fail=True))
    assert failed.status == baseline.status == "COMPLETED"
    assert failed.response.answer == baseline.response.answer


def test_required_mode_withholds_the_answer_when_the_run_cannot_be_recorded() -> None:
    result = audited_run(Outbox(fail=True), AI_AUDIT_STORE_ENABLED="true", AI_AUDIT_STORE_REQUIRED="true",
                         AUDIT_OUTBOX_DATABASE_URL="postgresql://orc@localhost/db")
    assert result.status == "FAILED" and result.error.code == "AUDIT_UNAVAILABLE" and result.response is None


def test_audit_settings_are_required_only_while_on() -> None:
    assert Settings.from_env(BASE_ENV).ai_audit_store_enabled is False
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE_ENV, "AI_AUDIT_STORE_ENABLED": "true"})
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE_ENV, "AI_AUDIT_STORE_REQUIRED": "true"})
    ok = Settings.from_env({**BASE_ENV, "AI_AUDIT_STORE_ENABLED": "true",
                            "AUDIT_OUTBOX_DATABASE_URL": "postgresql://orc@localhost/db"})
    assert "AUDIT_OUTBOX_DATABASE_URL" not in repr(ok) and "orc@localhost" not in repr(ok)


def test_without_the_flags_the_orchestrator_is_unchanged() -> None:
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), ScriptedClient([]), Tools([]).registry())
    assert agent.audit_outbox is None and agent.derived_frequency is False
    assert DERIVED_FREQUENCY_RULES not in agent.system_prompt


# ---------------------------------------------------------------------------------------- outbox privileges (PG)

@pytest.fixture()
def outbox_database():
    admin = os.environ.get("ORC_TEST_POSTGRES_URL")
    if not admin:
        pytest.skip("ORC_TEST_POSTGRES_URL is not set")
    name = f"orc_outbox_{secrets.token_hex(4)}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
        c.execute("DO $$BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'orc_outbox_test') THEN "
                  "CREATE ROLE orc_outbox_test LOGIN; END IF; END$$")
        # like the live orchestrator login (scripts/provision_market_ai_orc_login.py)
        c.execute("ALTER ROLE orc_outbox_test SET default_transaction_read_only = on")
    parts = urlsplit(admin)
    database = urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))
    with psycopg.connect(database, autocommit=True) as c:
        c.execute(open(MIGRATION).read())
        c.execute("GRANT market_ai_audit_outbox_writer TO orc_outbox_test")
    host = parts.netloc.split("@", 1)[-1]
    yield database, urlunsplit((parts.scheme, f"orc_outbox_test@{host}", f"/{name}", "", ""))
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_the_outbox_login_can_only_insert_and_retries_are_idempotent(outbox_database) -> None:
    admin, writer = outbox_database
    outbox = AuditOutbox(writer)
    payload = {"schema": "saniti.audit.run_finished/v1", "request_id": "req-9", "events": []}
    outbox.write(payload)
    outbox.write({**payload, "events": [{"type": "changed"}]})  # a retry keeps the first row
    with psycopg.connect(admin) as c:
        rows = c.execute("SELECT request_id, status, payload->'events' FROM ai_audit.ingest_outbox").fetchall()
    assert rows == [("req-9", "PENDING", [])]
    # the privileges, not the read-only default, are what stop the other statements
    for statement in ("SELECT * FROM ai_audit.ingest_outbox", "UPDATE ai_audit.ingest_outbox SET status = 'COMPLETE'",
                      "DELETE FROM ai_audit.ingest_outbox"):
        with psycopg.connect(writer, autocommit=True) as c:
            c.execute("SET default_transaction_read_only = off")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute(statement)
