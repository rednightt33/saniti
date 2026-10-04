"""AI_MODELS.md is generated from the code (user request 2026-10-04; AGENTS.md Mandatory workflow): a model call site
added, removed or changed (model, reasoning, token limit, tools, structured output, provider routing), or a model
setting renamed, without regenerating it fails here."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _generator():
    spec = importlib.util.spec_from_file_location("generate_ai_models_doc", ROOT / "scripts/generate_ai_models_doc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_models_md_matches_the_code() -> None:
    generator = _generator()
    expected = generator.render(generator.current_snapshot())
    assert (ROOT / "AI_MODELS.md").read_text(encoding="utf-8") == expected, \
        "regenerate with scripts/generate_ai_models_doc.py (AGENTS.md, AI models rule)"


def test_every_call_site_has_a_purpose_and_the_main_loop_is_found() -> None:
    generator = _generator()
    keys = {f"{s['service']}:{s['file']}:{s['function']}" for s in generator.call_sites()}
    assert keys == set(generator.PURPOSE)
    assert "market-ai-orc:orchestrator.py:_loop" in keys and "market-web-governor:fact.py:_extract" in keys


def test_secret_names_and_values_are_never_listed() -> None:
    generator = _generator()
    assert not any(generator.SECRET_NAME.search(n) for n in generator.listed_names())
    try:
        generator.snapshot_from_values({"AI_MODEL": "sk-or-v1-" + "a" * 48}, "x")
    except SystemExit:
        pass
    else:
        raise AssertionError("a secret-looking value was written")
