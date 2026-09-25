"""Completion: ExecutionManifest, processing coverage (every approved request and range read through the helpers in
a successful execution), final status, and output release only on coverage PASS."""
from __future__ import annotations

from conftest import requires_root
from test_dataneed_bundles import HEADERS, approve, build, env, ytd_parts  # noqa: F401 - env is a fixture
from test_dataneed_sessions import ok, run, session  # noqa: F401 - session is a fixture

pytestmark = requires_root

YTD = """
prices = load('prices')
banks = load('stock_classification')
last = prices.groupby('ticker', as_index=False)['close'].last()
emit_table('last_close', last)
"""


def complete(env):  # noqa: F811
    response = env["api"].post(f"/v1/sessions/{env['session_id']}/complete", json={"request_id": "req_bundle_1"},
                               headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_complete_analysis_passes_releases_its_outputs_and_closes_the_session(session) -> None:
    table = ok(session, YTD)["outputs"][0]
    result = complete(session)
    final = result["final_status"]
    assert result["status"] == "COMPLETED" and result["next_action"] == "ANSWER_FROM_RELEASED_OUTPUTS"
    assert final == final | {"data_need_validation": "PASS", "research_governance": "NOT_APPLICABLE",
                             "sql_governance": "PASS", "data_quality_profiling": "COMPLETE", "data_coverage": "PASS",
                             "sandbox_execution": "SUCCESS", "calculation_validation": "NOT_PERFORMED",
                             "execution_complete": True, "evidence_label": "DATA_COVERAGE_VERIFIED"}
    assert "HISTORICAL_REFERENCE_USES_CURRENT_STATE" in final["warnings"]
    assert "the calculation was independently verified" in final["claims_forbidden"]
    assert [o["output_id"] for o in result["released_outputs"]] == [table["output_id"]]
    coverage = result["coverage"]
    assert coverage["coverage_status"] == "PASS" and {r["processing"] for r in coverage["requests"]} == {"PROCESSED"}
    assert coverage["requests"][0]["ranges"][0] == {"range_id": "current_ytd", "delivery": "PASS",
                                                    "processing": "PROCESSED", "status": "PASS"}
    page = session["api"].get(f"/v1/sessions/{session['session_id']}/outputs/{table['output_id']}",
                              params={"request_id": "req_bundle_1"}, headers=HEADERS).json()
    assert page["released"] is True
    state = session["api"].get(f"/v1/sessions/{session['session_id']}", params={"request_id": "req_bundle_1"},
                               headers=HEADERS).json()
    assert state["status"] == "CLOSED" and state["close_reason"] == "COMPLETED"
    assert complete(session)["replayed"] is True
    stored = session["dataneed"].store.completion_for_session(session["session_id"])
    reads = stored["execution_manifest"]["reads"]
    assert reads["data_request_1_A"]["full_reads"] == 1 and reads["data_request_1_B"]["full_reads"] == 1


def test_unprocessed_requests_and_ranges_fail_coverage_and_the_session_stays_open(session) -> None:
    ok(session, "cur = saniti.range('prices', 'current_ytd')\nemit_json('n', {'rows': len(cur)})")
    result = complete(session)
    assert result["status"] == "INCOMPLETE" and result["final_status"]["data_coverage"] == "FAIL"
    assert result["final_status"]["evidence_label"] == "NOT_VALIDATED" and result["released_outputs"] == []
    requests = {r["data_request_id"]: r for r in result["coverage"]["requests"]}
    prices = {g["range_id"]: g["processing"] for g in requests["data_request_1_A"]["ranges"]}
    assert prices == {"current_ytd": "PROCESSED", "previous_comparable": "NOT_PROCESSED"}
    assert requests["data_request_1_B"]["processing"] == "NOT_PROCESSED"
    assert result["next_action"] == "RUN_PYTHON" and "prices:previous_comparable" in result["message"]
    ok(session, "prev = saniti.range('prices', 'previous_comparable')\nbanks = saniti.join(2)")
    assert complete(session)["status"] == "COMPLETED"


def test_reading_the_input_files_directly_is_not_processing(session) -> None:
    ok(session, """
import glob, os
frames = [pd.read_parquet(p) for p in glob.glob(os.path.join(os.getcwd(), '..', 'input', '*.parquet'))]
emit_json('rows', {'rows': sum(len(f) for f in frames)})
""")
    result = complete(session)
    assert result["final_status"]["data_coverage"] == "FAIL"
    assert {r["processing"] for r in result["coverage"]["requests"]} == {"NOT_PROCESSED"}


def test_reads_and_outputs_of_failed_executions_do_not_count(session) -> None:
    body = run(session, YTD + "\nraise ValueError('late failure')").json()
    assert body["status"] == "SCRIPT_ERROR" and body["outputs"]
    result = complete(session)
    assert result["final_status"]["sandbox_execution"] == "FAILED"
    assert result["final_status"]["data_coverage"] == "FAIL" and result["released_outputs"] == []


def test_an_analysis_without_outputs_is_not_a_success(session) -> None:
    ok(session, "prices = load('prices')\nbanks = load('stock_classification')")
    result = complete(session)
    assert result["final_status"]["data_coverage"] == "PASS"
    assert result["final_status"]["sandbox_execution"] == "FAILED" and result["status"] == "INCOMPLETE"


def test_insufficient_data_after_the_last_success_asks_for_a_revision(session) -> None:
    ok(session, YTD)
    run(session, "saniti.insufficient_data('prices', 'previous_comparable', value=200)")
    result = complete(session)
    assert result["final_status"]["sandbox_execution"] == "INSUFFICIENT_INPUT_DATA"
    assert result["next_action"] == "REVISE_DATA_NEED_SPEC" and result["released_outputs"] == []
