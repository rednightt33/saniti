from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from app.config import Settings


BASE_ENV = {
    "MARKET_AI_ORC_API_KEY": "test-internal-key",
    "OPENROUTER_API_KEY": "sk-or-test-secret-value",
}


def make_settings(**overrides: str) -> Settings:
    return Settings.from_env({**BASE_ENV, **overrides})


def usage(input_tokens: int = 100, output_tokens: int = 20, reasoning_tokens: int = 5) -> dict[str, Any]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
        "total_tokens": input_tokens + output_tokens,
    }


def tool_call_response(
    name: str, arguments: str = "{}", call_id: str = "call_1", response_id: str = "resp_tool"
) -> dict[str, Any]:
    return {
        "id": response_id,
        "output": [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "hidden"}]},
            {"type": "function_call", "id": "fc_1", "call_id": call_id, "name": name,
             "arguments": arguments},
        ],
        "usage": usage(),
    }


def final_response(body: dict[str, Any] | str, response_id: str = "resp_final") -> dict[str, Any]:
    text = body if isinstance(body, str) else json.dumps(body)
    return {
        "id": response_id,
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": usage(),
    }


ANSWER = {
    "response_type": "ANSWER",
    "answer": "Database querying and Python analysis are not available yet.",
    "clarification_question": None,
    "assumptions": [],
    "limitations": [],
}


class ScriptedClient:
    """Returns scripted provider responses in order and records deep copies of payloads."""

    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = list(responses)
        self.payloads: list[dict[str, Any]] = []

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(copy.deepcopy(payload))
        if not self.responses:
            raise AssertionError("ScriptedClient ran out of responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def settings() -> Settings:
    return make_settings()
