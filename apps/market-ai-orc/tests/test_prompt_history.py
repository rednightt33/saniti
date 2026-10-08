"""System prompt history (user decision 2026-10-08: "buat dokumentasi / history system prompt agar selalu bisa
fallback"): the newest snapshot in prompts/history is what the code renders, so every change to the prompt or the
final-response schema leaves a version to fall back to (scripts/snapshot_system_prompt.py record)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import test_prompt_pass2 as pass2

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("snapshot_system_prompt", ROOT / "scripts" / "snapshot_system_prompt.py")
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


def test_the_history_renders_the_dev_profile_of_the_prompt_tests() -> None:
    assert snapshot.DEV == pass2.DEV and snapshot.DEV_TOOLS == pass2.DEV_TOOLS


def test_the_newest_snapshot_is_what_the_code_renders() -> None:
    newest = snapshot.versions()[-1]
    prompt, schema = snapshot.render(ROOT / "apps" / "market-ai-orc")
    assert (newest / "system_prompt.md").read_text(encoding="utf-8") == prompt, \
        "the system prompt changed: run scripts/snapshot_system_prompt.py record <name> --decision ... --change ..."
    assert (newest / "response_schema.json").read_text(encoding="utf-8") == schema, \
        "the response schema changed: run scripts/snapshot_system_prompt.py record <name> --decision ... --change ..."


def test_every_version_is_complete_and_listed() -> None:
    index = snapshot.INDEX.read_text(encoding="utf-8")
    for number, folder in enumerate(snapshot.versions(), start=1):
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        assert meta["version"] == number and meta["decision"] and meta["change"]
        assert meta["prompt_sha256"] == snapshot.sha((folder / "system_prompt.md").read_text(encoding="utf-8"))
        assert f"history/{folder.name}/system_prompt.md" in index
