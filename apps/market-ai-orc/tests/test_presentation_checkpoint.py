from __future__ import annotations

import copy
from types import SimpleNamespace

from app import presentation_checkpoint as checkpoints
from app.openrouter_client import ProviderError
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from conftest import ScriptedClient, final_response, make_settings
from test_dataneed_orchestrator import OUTPUT, Tools, answer, completed, flow
from test_result_store import MemoryStore

CONV = "conv_" + "a" * 32


def no_recalculation(*args):
    raise AssertionError("presentation retry must not fetch or restore computation inputs")


class SavedStore(MemoryStore):
    def output(self, conversation_id, output_id):
        entry = self.outputs.get(output_id)
        return SimpleNamespace(storage="POSTGRES", checksum_sha256="a" * 64) if entry and entry[0] == conversation_id else None


def completed_checkpoint():
    saved, fetched, store = {}, [], SavedStore()
    def write(step, document):
        saved[step] = copy.deepcopy(document)
        return True
    tools = Tools([completed()])
    class FinalTimeout(ScriptedClient):
        def create(self, payload, **options):
            if len(self.responses) == 1:
                assert saved["original"]["phase"] == "READY_FOR_PRESENTATION"
                assert OUTPUT in store.outputs  # storage happened before final generation began
            return super().create(payload, **options)
    script = FinalTimeout([*flow(), ProviderError("slow final", code="PROVIDER_TIMEOUT")])
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), script, tools.registry(), result_store=store,
                              output_fetcher=lambda *args: (fetched.append(args), b"result")[1],
                              carried_uploader=lambda *args: {})
    token = checkpoints.current.set(checkpoints.Context("original", write))
    try:
        result = agent.run(AgentRunRequest(request_id="original", conversation_id=CONV, message="Hitung return BBCA"))
    finally:
        checkpoints.current.reset(token)
    assert result.error.code == "PROVIDER_TIMEOUT"
    assert result.execution.presentation_recovery["available"] is True
    assert len(fetched) == 1  # the terminal save did not fetch/copy the same output again
    return saved["original"], store


def test_completed_results_are_saved_before_the_presentation_call():
    document, _ = completed_checkpoint()
    assert document["scope"] == "saved_computation" and "reasoning" not in document
    assert all(output.get("checksum_sha256") for output in document["outputs"])


def test_retry_uses_the_saved_contract_and_offers_no_query_or_computation_tools():
    document, store = completed_checkpoint()
    script = ScriptedClient([final_response(answer("Hasil tersimpan sudah tersedia."))])
    agent = AgentOrchestrator(make_settings(AI_ENABLE_DATANEED="true"), script, Tools([]).registry(), result_store=store,
                              output_fetcher=no_recalculation, carried_uploader=no_recalculation)
    token = checkpoints.resume.set(document)
    try:
        result = agent.run(AgentRunRequest(request_id="retry", conversation_id=CONV, message="Sajikan ulang",
                                           presentation_retry_of="original"))
    finally:
        checkpoints.resume.reset(token)
    assert result.status == "COMPLETED", result.error
    assert len(script.payloads) == 1 and "tools" not in script.payloads[0]
    assert "Hitung return BBCA" in str(script.payloads[0]["input"])


def test_missing_saved_results_stop_before_any_paid_call():
    document, store = completed_checkpoint()
    store.outputs.clear()
    script = ScriptedClient([])
    agent = AgentOrchestrator(make_settings(), script, Tools([]).registry(), result_store=store,
                              output_fetcher=no_recalculation, carried_uploader=no_recalculation)
    token = checkpoints.resume.set(document)
    try:
        result = agent.run(AgentRunRequest(request_id="missing", conversation_id=CONV, message="Sajikan ulang",
                                           presentation_retry_of="original"))
    finally:
        checkpoints.resume.reset(token)
    assert result.error.code == "PRESENTATION_RESULTS_UNAVAILABLE" and script.payloads == []
