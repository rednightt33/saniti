"""AI_TOOLS.md is generated from the code (round 2026-10-03, A3; AGENTS.md Mandatory workflow): a tool, session helper
or method guide added, removed or re-switched without regenerating it fails here."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _generator():
    spec = importlib.util.spec_from_file_location("generate_ai_tools_doc", ROOT / "scripts/generate_ai_tools_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_tools_md_matches_the_code() -> None:
    generator = _generator()
    expected = generator.render(generator.current_snapshot())
    assert (ROOT / "AI_TOOLS.md").read_text(encoding="utf-8") == expected, \
        "regenerate with scripts/generate_ai_tools_doc.py (AGENTS.md, AI tools rule)"


def test_every_listed_name_has_a_plain_sentence() -> None:
    generator = _generator()
    names = {t["name"] for t in generator.model_tools()} | set(generator.session_helpers())
    names |= {generator.GUIDE_ALIAS.get(g["name"], g["name"]) for g in generator.method_guides()}
    assert names <= set(generator.PLAIN), sorted(names - set(generator.PLAIN))
