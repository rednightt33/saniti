#!/usr/bin/env python3
"""Bounded provider smoke for strict structured Responses output (no database)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "apps" / "market-ai-backend"
sys.path.insert(0, str(APP_ROOT))

from app.openai_client import ResponsesClient  # noqa: E402
from app.schemas import FINAL_RESPONSE_SCHEMA  # noqa: E402


def main() -> None:
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
    secret_name = "OPENROUTER_DEEPSEEK" if provider == "openrouter" else "OPENAI_API_KEY"
    api_key = os.environ.get(secret_name, "")
    if not api_key:
        raise RuntimeError(f"{secret_name} is required")
    model = os.getenv("AI_MODEL") or (
        "deepseek/deepseek-v4.1-flash" if provider == "openrouter" else "gpt-5.6-terra"
    )
    effort = os.getenv("AI_REASONING_EFFORT") or ("high" if provider == "openrouter" else "medium")
    client = ResponsesClient(provider, api_key, 60)
    try:
        response = client.create({
            "model": model,
            "reasoning": {"effort": effort},
            "instructions": "Return the requested JSON only. Do not invent evidence.",
            "input": "Return a low-confidence test result with no evidence and one optional next analysis.",
            "tools": [{
                "type": "function",
                "name": "unused_probe",
                "description": "A probe that must not be called for this request.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "strict": True,
            }],
            "parallel_tool_calls": False,
            "max_output_tokens": 600,
            "store": False,
            "text": {"format": {
                "type": "json_schema",
                "name": "market_analysis",
                "schema": FINAL_RESPONSE_SCHEMA,
                "strict": True,
            }},
        })
    finally:
        client.close()

    output_types = [item.get("type") for item in response.get("output", [])]
    texts = [
        content.get("text", "")
        for item in response.get("output", []) if item.get("type") == "message"
        for content in item.get("content", []) if content.get("type") == "output_text"
    ]
    parsed = json.loads("".join(texts))
    missing = sorted(set(FINAL_RESPONSE_SCHEMA["required"]) - set(parsed))
    if missing:
        raise RuntimeError(f"Structured output omitted required fields: {missing}")
    usage = response.get("usage") or {}
    print(json.dumps({
        "overall": "PASS",
        "provider": provider,
        "model": response.get("model") or model,
        "response_id": response.get("id"),
        "output_types": output_types,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }))


if __name__ == "__main__":
    main()
