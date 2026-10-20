"""EXEC-M181 and the branch behaviours (user 2026-10-19/20: "Ya oke, okay, standar juga boleh"; "Otomatis 1x, lalu
tawarkan"): with AI_PROVIDER_STREAMING a model call is streamed and a provider that sends no content (keep-alive
comments do not count) within the first-content limit, or none for the idle limit after that, has stalled. The run asks
such a call once more at the same level where the user sees it, then fails with a plain reason; the stop button and
the run's time limit end a call in flight. AI_FASTLANE_KEEP_REASONING keeps the chosen reasoning on every fast-lane
call and asks a runaway again at the same level. Without the switches nothing changes."""
from __future__ import annotations

import http.server
import json
import threading
import time

import httpx
import pytest

from app import lanes, progress, stop
from app.model_choices import resolve
from app.openrouter_client import CALL_STOPPED, OpenRouterClient, ProviderError
from app.orchestrator import RUNAWAY_NOTE
from app.tools.request_data import current_run_deadline
from app.user_texts import PROGRESS_PROVIDER_RETRY, PROGRESS_RUNAWAY_RETRY
from conftest import ANSWER, final_response, make_settings
from test_dataneed_orchestrator import answer, flow
from test_fastlane import FAST_ON, run

FINAL = {"id": "gen-1", "object": "response", "status": "completed", "model": "deepseek/deepseek-v4.1-flash",
         "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}],
         "usage": {"input_tokens": 10, "output_tokens": 3}}


def sse(event: dict) -> bytes:
    return f"data: {json.dumps(event)}\n\n".encode()


def delta(kind: str = "response.reasoning_text.delta") -> bytes:
    return sse({"type": kind, "delta": "x"})


KEEPALIVE = b": OPENROUTER PROCESSING\n\n"


def client(chunks, *, first=0.4, idle=0.4, tool_idle=0.4, status=200, content_type="text/event-stream", calls=None,
           timeout=30):
    """An OpenRouterClient whose transport replays chunks (bytes, or a float = seconds to wait) for every call."""
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(json.loads(request.content))

        def body():
            for chunk in chunks:
                if isinstance(chunk, float):
                    time.sleep(chunk)
                else:
                    yield chunk
        return httpx.Response(status, headers={"content-type": content_type}, content=body())
    return OpenRouterClient("k", timeout, transport=httpx.MockTransport(handler), streaming=True,
                            first_content_seconds=first, idle_seconds=idle, tool_idle_seconds=tool_idle)


# ---------------------------------------------------------------- the client

def test_a_streamed_call_returns_the_final_response_as_without_streaming() -> None:
    calls: list = []
    result = client([KEEPALIVE, delta(), delta("response.output_text.delta"),
                     sse({"type": "response.completed", "response": FINAL}), b"data: [DONE]\n\n"],
                    calls=calls).create({"model": "m", "input": []})
    assert result == FINAL and calls[0]["stream"] is True


def test_a_reply_cut_at_the_output_limit_comes_back_incomplete() -> None:
    incomplete = {**FINAL, "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}
    result = client([delta(), sse({"type": "response.incomplete", "response": incomplete})]).create({"model": "m"})
    assert result["status"] == "incomplete"


def test_keep_alive_comments_alone_are_a_stall_and_are_not_retried_silently_when_asked() -> None:
    calls: list = []
    started = time.monotonic()
    with pytest.raises(ProviderError) as raised:
        client([KEEPALIVE, 0.05] * 200, calls=calls).create({"model": "m"}, retry_stalls=False)
    assert raised.value.code == "PROVIDER_STALLED" and "0.4 s" in str(raised.value)
    assert time.monotonic() - started < 3 and len(calls) == 1


def test_a_provider_that_stops_after_some_content_stalls_at_the_idle_limit() -> None:
    with pytest.raises(ProviderError) as raised:
        client([delta(), *([KEEPALIVE, 0.05] * 200)]).create({"model": "m"}, retry_stalls=False)
    assert raised.value.code == "PROVIDER_STALLED"


def test_a_slow_provider_that_keeps_sending_content_is_never_cut() -> None:
    chunks = [x for _ in range(12) for x in (delta(), 0.15)]  # 1.8 s in all, gaps below the 0.4 s idle limit
    result = client([*chunks, sse({"type": "response.completed", "response": FINAL})]).create({"model": "m"})
    assert result == FINAL


TOOLS = {"model": "m", "tools": [{"type": "function", "name": "run_python"}], "tool_choice": "auto"}
QUIET = [KEEPALIVE, 0.05] * 16  # 0.8 s of keep-alive comments only
CALL = sse({"type": "response.function_call_arguments.delta", "delta": "{...}"})


def test_a_tool_call_written_in_silence_after_reasoning_gets_the_tool_limit() -> None:
    """Measured 2026-10-20: DeepSeek and MiMo send a tool call's arguments in one piece after a silence."""
    done = sse({"type": "response.completed", "response": FINAL})
    assert client([delta(), *QUIET, CALL, done], tool_idle=2.0).create(TOOLS, retry_stalls=False) == FINAL
    with pytest.raises(ProviderError) as raised:  # the same silence while text is written, or without tools
        client([delta("response.output_text.delta"), *QUIET, done], tool_idle=2.0).create(TOOLS, retry_stalls=False)
    assert raised.value.code == "PROVIDER_STALLED"
    with pytest.raises(ProviderError):
        client([delta(), *QUIET, CALL, done], tool_idle=2.0).create({"model": "m"}, retry_stalls=False)
    # with thinking off, the first content may be the tool call itself
    off = {**TOOLS, "reasoning": {"enabled": False}}
    assert client([*QUIET, CALL, done], tool_idle=2.0).create(off, retry_stalls=False) == FINAL


def test_by_default_a_stalled_call_keeps_the_clients_retries() -> None:
    calls: list = []
    with pytest.raises(ProviderError) as raised:
        client([KEEPALIVE, 0.05] * 200, calls=calls, first=0.2).create({"model": "m"}, attempts=2)
    assert raised.value.code == "PROVIDER_STALLED" and len(calls) == 2


def test_the_stop_flag_and_the_run_deadline_end_a_call_in_flight() -> None:
    flag = threading.Event()
    token = stop.current_stop.set(flag)
    try:
        threading.Timer(0.3, flag.set).start()
        with pytest.raises(ProviderError) as raised:
            client([delta(), 0.05] * 400, idle=5).create({"model": "m"})
        assert raised.value.code == CALL_STOPPED
    finally:
        stop.current_stop.reset(token)
    token = current_run_deadline.set(time.monotonic() + 0.3)
    try:
        with pytest.raises(ProviderError) as raised:
            client([delta(), 0.05] * 400, idle=5).create({"model": "m"})
        assert raised.value.code == "RUN_DEADLINE"
    finally:
        current_run_deadline.reset(token)


def test_an_error_inside_the_stream_is_a_provider_failure_and_a_refusal_keeps_its_code() -> None:
    with pytest.raises(ProviderError) as raised:
        client([delta(), sse({"type": "error", "message": "upstream died"})]).create({"model": "m"}, attempts=1)
    assert raised.value.code == "PROVIDER_UNAVAILABLE" and "upstream died" in str(raised.value)
    refusal = json.dumps({"error": {"message": "bad request", "code": 400}}).encode()
    with pytest.raises(ProviderError) as raised:
        client([refusal], status=400, content_type="application/json").create({"model": "m"})
    assert raised.value.code == "PROVIDER_REJECTED"


class Hanging(http.server.BaseHTTPRequestHandler):
    """A real socket: one keep-alive, then nothing at all (a provider that holds the connection silently)."""

    def do_POST(self):  # noqa: N802 - http.server API
        self.rfile.read(int(self.headers.get("content-length") or 0))
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(KEEPALIVE)
        self.wfile.flush()
        time.sleep(4)

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("pressed", [False, True])
def test_a_silent_socket_is_closed_at_the_first_content_limit_or_at_the_stop(pressed) -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hanging)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    flag = threading.Event()
    token = stop.current_stop.set(flag)
    try:
        real = OpenRouterClient("k", 30, streaming=True, first_content_seconds=0.5 if not pressed else 20,
                                idle_seconds=0.5)
        real.client = httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}")
        if pressed:
            threading.Timer(0.3, flag.set).start()
        started = time.monotonic()
        with pytest.raises(ProviderError) as raised:
            real.create({"model": "m"}, retry_stalls=False)
        assert raised.value.code == (CALL_STOPPED if pressed else "PROVIDER_STALLED")
        assert time.monotonic() - started < 2.5  # the server stays silent for 4 s
    finally:
        stop.current_stop.reset(token)
        server.shutdown()


# ---------------------------------------------------------------- the run

STREAM_ON = {**FAST_ON, "AI_PROVIDER_STREAMING": "true"}
STALLED = ProviderError("the AI provider sent no output for 45 s", code="PROVIDER_STALLED")


def tracked(script, **kwargs):
    with progress.tracking(kwargs.pop("request_id", "f1"), None) as record:
        result = run(script, **kwargs)
    return (*result, [s["label"] for s in record.view()["steps"]])


@pytest.mark.parametrize("lane", [lanes.FAST, lanes.STANDARD])
def test_a_stalled_call_is_asked_once_more_at_the_same_level_and_the_user_sees_it(lane) -> None:
    result, scripted, _, steps = tracked([*flow()[:1], STALLED, *flow()[1:], final_response(ANSWER)], lane=lane,
                                         path="RESEARCH" if lane == lanes.FAST else "ANALYSIS",
                                         settings={**STREAM_ON, "AI_FASTLANE_KEEP_REASONING": "true"})
    assert result.status == "COMPLETED"
    assert PROGRESS_PROVIDER_RETRY in steps
    assert scripted.payloads[1]["reasoning"] == scripted.payloads[2]["reasoning"]  # the same call, the same level
    assert all(o.get("retry_stalls") is False and "timeout" not in o for o in scripted.options)


def test_a_second_stall_fails_the_run_with_the_stall_code() -> None:
    result, _, _ = run([STALLED, STALLED], lane=lanes.FAST, settings=STREAM_ON)
    assert result.status == "FAILED" and result.error.code == "PROVIDER_STALLED"


def test_a_call_stopped_in_flight_ends_the_run_like_the_stop_button() -> None:
    stopped = ProviderError("the run was stopped during the model call", code=CALL_STOPPED)
    result, scripted, _ = run([stopped, final_response(ANSWER)], lane=lanes.FAST, settings=STREAM_ON)
    assert result.status == "LIMITED" and result.response.response_type == "LIMITATION"
    assert "dihentikan oleh Anda" in json.dumps(result.response.limitations)
    assert len(scripted.payloads) == 1  # no call after the stop


def test_without_streaming_the_client_options_are_as_before() -> None:
    _, scripted, _ = run([*flow(), final_response(ANSWER)], lane=lanes.STANDARD, path="ANALYSIS")
    assert set(map(json.dumps, scripted.options)) == {"{}"}


# ---------------------------------------------------------------- keep reasoning

KEEP = {**FAST_ON, "AI_FASTLANE_KEEP_REASONING": "true"}


def test_keep_reasoning_uses_the_chosen_level_on_every_call_without_the_90_s_cut() -> None:
    result, scripted, _ = run([*flow(), final_response(answer("Return YTD BBCA 12,35%."))], lane=lanes.FAST,
                              path="RESEARCH", settings=KEEP)
    assert result.status == "COMPLETED"
    assert {json.dumps(p["reasoning"]) for p in scripted.payloads} == {json.dumps({"effort": "high"})}
    assert all("timeout" not in o for o in scripted.options)


def runaway():
    """A turn that used the whole output budget on reasoning: no text, no tool call."""
    return {"id": "r", "status": "incomplete", "output": [{"type": "reasoning", "summary": []}],
            "usage": {"input_tokens": 10, "output_tokens": 24000, "output_tokens_details": {"reasoning_tokens": 24000}}}


def test_keep_reasoning_asks_a_runaway_again_at_the_same_level_then_fails_plainly() -> None:
    result, scripted, _, steps = tracked([runaway(), *flow(), final_response(ANSWER)], lane=lanes.FAST,
                                         path="RESEARCH", settings=KEEP)
    assert result.status == "COMPLETED" and PROGRESS_RUNAWAY_RETRY in steps
    assert scripted.payloads[1]["reasoning"] == {"effort": "high"}
    assert RUNAWAY_NOTE in json.dumps(scripted.payloads[1]["input"])
    failed, _, _ = run([runaway(), runaway()], lane=lanes.FAST, path="RESEARCH", settings=KEEP)
    assert failed.status == "FAILED" and failed.error.code == "REASONING_RUNAWAY"
    lowered, plain, _ = run([runaway(), *flow(), final_response(ANSWER)], lane=lanes.FAST, path="RESEARCH")
    assert lowered.status == "COMPLETED" and plain.payloads[1]["reasoning"] == {"effort": "low"}  # M150 as before


def test_the_qwen_reasoning_budget_comes_from_the_setting() -> None:
    assert resolve("qwen/qwen3.8-flash", "on", make_settings()).reasoning == {"max_tokens": 8000}
    assert resolve("qwen/qwen3.8-flash", "on", make_settings(AI_MAX_REASONING_TOKENS="12000")).reasoning \
        == {"max_tokens": 12000}
    assert resolve("deepseek/deepseek-v4.1-flash", "high", make_settings(AI_MAX_REASONING_TOKENS="12000")).reasoning \
        == {"effort": "high"}


def test_the_stream_limits_must_stay_below_the_call_limit() -> None:
    from app.config import ConfigError
    with pytest.raises(ConfigError):
        make_settings(AI_PROVIDER_STREAMING="true", AI_REQUEST_TIMEOUT_SECONDS="100")  # the tool limit is 120 s
    assert make_settings(AI_REQUEST_TIMEOUT_SECONDS="30").ai_provider_streaming is False  # checked only when on
