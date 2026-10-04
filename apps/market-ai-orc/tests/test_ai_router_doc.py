"""AI_ROUTER.md is generated from the router code (user request 2026-10-04: the router's criteria documented in the
repository; AGENTS.md Mandatory workflow, AI router)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ai_router_md_matches_the_code() -> None:
    spec = importlib.util.spec_from_file_location("generate_ai_router_doc", ROOT / "scripts/generate_ai_router_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (ROOT / "AI_ROUTER.md").read_text(encoding="utf-8") == module.render(), \
        "regenerate with scripts/generate_ai_router_doc.py (AGENTS.md, AI router rule)"
