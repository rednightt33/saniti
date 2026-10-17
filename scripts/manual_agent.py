"""EXEC-MANUAL (user 2026-10-17, troubleshooting only): Claude's side of the manual model.

Run inside the edge-bff service environment (EDGE_LOGIN, EDGE_INITIAL_PASSWORD; never printed):
  railway run --service edge-bff --environment dev -- python scripts/manual_agent.py list <dir>
      saves each waiting step's payload to <dir>/<step_id>.json and prints a short view of it
  railway run --service edge-bff --environment dev -- python scripts/manual_agent.py reply <step_id> <reply.json>
      posts a reply in the model's response shape: {"output": [{"type": "function_call", "name": ..., "arguments":
      "<json>", "call_id": ...}]} for a tool call, or {"output": [{"type": "message", "content": [{"type":
      "output_text", "text": "<final JSON>"}]}]} for the final answer
A step left unanswered for AI_MANUAL_AGENT_WAIT_SECONDS goes to AI_MODEL (the fallback).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = os.environ.get("EDGE_BASE_URL", "https://edge-bff-dev.up.railway.app")
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


def call(path: str, body: dict | None = None, csrf: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "Origin": BASE, **({"X-CSRF-Token": csrf} if csrf else {})}
    request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                     headers=headers, method="GET" if body is None else "POST")
    try:
        with OPENER.open(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def sign_in() -> str:
    login = os.environ.get("EDGE_INITIAL_LOGIN") or os.environ["EDGE_LOGIN"]
    code, data = call("/api/v1/auth/sign-in", {"login": login, "password": os.environ["EDGE_INITIAL_PASSWORD"]})
    if code != 200:
        raise SystemExit(f"sign-in failed ({code})")
    return data["csrf_token"]


def short(item: dict) -> str:
    kind = item.get("type") or item.get("role")
    text = item.get("content") if isinstance(item.get("content"), str) else item.get("output") or item.get("arguments")
    if not isinstance(text, str):
        text = json.dumps(item.get("content"), ensure_ascii=False)
    name = f" {item['name']}" if item.get("name") else ""
    return f"[{kind}{name}] {text[:600]}"


def main() -> None:
    action = sys.argv[1]
    csrf = sign_in()
    if action == "list":
        target = Path(sys.argv[2])
        target.mkdir(parents=True, exist_ok=True)
        code, data = call("/api/v1/dev/manual/steps")
        if code != 200:
            raise SystemExit(f"steps: {code} (switch off, or not signed in)")
        for step in data.get("steps", []):
            payload = step["payload"]
            (target / f"{step['step_id']}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1))
            tools = [t.get("name") for t in payload.get("tools") or []]
            print(f"STEP {step['step_id']} request {step['request_id']} waited {step['waited_seconds']} s; "
                  f"input items {len(payload.get('input') or [])}; tools {tools}")
            for item in (payload.get("input") or [])[-3:]:
                print("   ", short(item))
        if not data.get("steps"):
            print("no step waiting")
    elif action == "reply":
        reply = json.loads(Path(sys.argv[3]).read_text())
        code, data = call(f"/api/v1/dev/manual/steps/{sys.argv[2]}", {"response": reply}, csrf)
        print(code, data)
    call("/api/v1/auth/sign-out", {}, csrf)


if __name__ == "__main__":
    main()
