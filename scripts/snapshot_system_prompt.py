"""System prompt history (user decision 2026-10-08: "buat dokumentasi / history system prompt agar selalu bisa
fallback"). Every change to what the orc model reads is kept as a numbered snapshot, so any earlier version can be read,
compared and restored.

A snapshot holds what the dev model reads at the start of every call: the rendered system prompt and the final-response
schema (its field descriptions are instructions too), rendered from the code with the dev profile below. The index is
prompts/SYSTEM_PROMPT_HISTORY.md: version, date, user decision, what changed, sizes and sha256, and how to fall back.

    python scripts/snapshot_system_prompt.py record <slug> --decision "<user's words>" --change "<what changed>"
    python scripts/snapshot_system_prompt.py record <slug> ... --source <dir>   # render another tree (an old commit)
    python scripts/snapshot_system_prompt.py check                               # the newest snapshot is the code's

Run it from the repository root with the orc's virtualenv. apps/market-ai-orc/tests/test_prompt_history.py fails when
the code renders a prompt or schema the newest snapshot does not hold.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "prompts" / "history"
INDEX = ROOT / "prompts" / "SYSTEM_PROMPT_HISTORY.md"
# the dev deployment's prompt switches (tests/test_prompt_pass2.py DEV; test_prompt_history keeps them equal)
DEV = dict(lookup_fact=False, dataneed=True, plan_confirmation=True, period_return=True, final_contract=True,
           conversation_reuse=True, methodology=True, plan_feasibility=True, point_in_time=True,
           derived_frequency=True, research_findings=True, multi_angle=True, angle_limits=(2, 5, 0),
           value_references=True, hypothesis_plans=True)
DEV_TOOLS = frozenset({"query_metric", "lookup_reference", "research_web"})
# A3 (EXEC-1018B Fase 5): what dev really renders on top of the prompt tests' profile: the run memory, merged steps and
# table directives switches (dev: on), and the tools of the dev registry, derived from the switches AI_TOOLS.md's dev
# snapshot lists (taken from Railway); the fast lane's own prefix (E2) is kept beside the standard one
LIVE = dict(memo_note=True, merged_steps=True, table_directives=True)
HEADER = """# System prompt history

Every version of what the orc model reads at the start of each call: the system prompt and the final-response schema,
rendered with the dev profile (`scripts/snapshot_system_prompt.py`). The newest entry is what the code renders now
(`apps/market-ai-orc/tests/test_prompt_history.py`). Recorded with `scripts/snapshot_system_prompt.py record`
whenever the rendered prompt or schema changes (AGENTS.md, Mandatory workflow).

## How to fall back

1. Find the version to return to below; its commit is the commit that added its snapshot folder
   (`git log --diff-filter=A -- prompts/history/<folder>`).
2. Fastest, without code: in Railway, redeploy the orc deployment built from that commit or a later one with the same
   prompt sha256 (RAILWAY_CHANGELOG.md lists deployments by commit). Verify the deployment reaches SUCCESS.
3. In code: `git revert` the commits after that version that changed `apps/market-ai-orc/app/orchestrator.py` prompt
   texts or `app/schemas.py` descriptions, run the orc tests, record a new snapshot (it must have the old sha256), push
   `main`, and verify the deployment.
4. A snapshot is text to compare and restore, not a file the service reads: a prompt goes with the tools and checks of
   its code, so an old prompt is restored together with its code, never alone.

## Versions

| Version | Date | Name | Prompt chars | Prompt sha256 | Schema sha256 | User decision |
|---|---|---|---|---|---|---|
"""


RENDER = """
import importlib.util, inspect, json, sys
sys.path.insert(0, sys.argv[1])
from app.orchestrator import build_system_prompt
from app.schemas import final_response_schema
dev, tools, live, off = (json.loads(sys.argv[2]), frozenset(json.loads(sys.argv[3])), json.loads(sys.argv[4]),
                         tuple(json.loads(sys.argv[5])))
dev["angle_limits"] = tuple(dev["angle_limits"])
fast = None
if "research_sections" in inspect.signature(build_system_prompt).parameters:
    # A3: the dev registry's tools and the live switches (trees before EXEC-1018B Fase 5 render the old profile)
    spec = importlib.util.spec_from_file_location("tools_doc", sys.argv[6])
    doc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doc)
    registry = doc._build(off)
    from app import tool_desks as desks
    names = frozenset(registry.names())
    effect = lambda name: getattr(registry.get(name), "effect", None)
    prompt = build_system_prompt(**dev, **live, tools=names, tool_envelope=True)
    fast = build_system_prompt(**dev, **live, tools=desks.tools("FASTLANE", names, effect), tool_envelope=True,
                               research_sections=False)
    schema = final_response_schema(True, True, True, True, True, True, memo_note=True, conversation_facts=True,
                                   next_step=True)
else:
    prompt = build_system_prompt(**dev, tools=tools, tool_envelope=True)
    schema = final_response_schema(True, True, True, True, True, True, conversation_facts=True)
print(json.dumps({"prompt": prompt, "fast": fast,
                  "schema": json.dumps(schema, ensure_ascii=False, indent=1, sort_keys=True) + "\\n"}))
"""


def dev_off_switches() -> list[str]:
    """A3: the switches AI_TOOLS.md's dev snapshot (taken from Railway, names and on/off only) lists as off."""
    text = (ROOT / "AI_TOOLS.md").read_text(encoding="utf-8")
    block = text.split("<!-- dev-snapshot:start -->", 1)[-1].split("<!-- dev-snapshot:end -->", 1)[0]
    return sorted(re.findall(r"\| `(AI_[A-Z0-9_]+)` \| off \|", block))


def render(source: Path) -> tuple[str, str]:
    """The dev system prompt and final-response schema of the orc tree at source, rendered in its own process so the
    caller's loaded modules (a test run, another tree) are never replaced."""
    prompt, schema, _ = render_all(source)
    return prompt, schema


def render_all(source: Path) -> tuple[str, str, str | None]:
    """render(), plus the fast lane's prefix (E2) when the tree builds one."""
    done = subprocess.run([sys.executable, "-c", RENDER, str(source), json.dumps(DEV), json.dumps(sorted(DEV_TOOLS)),
                           json.dumps(LIVE), json.dumps(dev_off_switches()),
                           str(ROOT / "scripts" / "generate_ai_tools_doc.py")],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    if done.returncode:
        raise SystemExit(f"rendering {source} failed:\n{done.stderr[-2000:]}")
    out = json.loads(done.stdout)
    return out["prompt"], out["schema"], out.get("fast")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def versions() -> list[Path]:
    return sorted(p for p in HISTORY.iterdir() if p.is_dir()) if HISTORY.exists() else []


def record(slug: str, decision: str, change: str, source: Path, date: str) -> None:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise SystemExit("slug: lower-case words joined by hyphens")
    prompt, schema, fast = render_all(source)
    existing = versions()
    if existing and (existing[-1] / "system_prompt.md").read_text(encoding="utf-8") == prompt \
            and (existing[-1] / "response_schema.json").read_text(encoding="utf-8") == schema \
            and _fast_text(existing[-1]) == fast:
        raise SystemExit(f"nothing changed since {existing[-1].name}; no snapshot written")
    number = len(existing) + 1
    folder = HISTORY / f"v{number:03d}-{date}-{slug}"
    folder.mkdir(parents=True)
    (folder / "system_prompt.md").write_text(prompt, encoding="utf-8")
    (folder / "response_schema.json").write_text(schema, encoding="utf-8")
    if fast is not None:
        (folder / "fast_prompt.md").write_text(fast, encoding="utf-8")
    meta = {"version": number, "date": date, "name": slug, "decision": decision, "change": change,
            "prompt_chars": len(prompt), "prompt_sha256": sha(prompt), "schema_sha256": sha(schema),
            **({"fast_prompt_chars": len(fast), "fast_prompt_sha256": sha(fast)} if fast is not None else {})}
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_index()
    print(f"recorded {folder.relative_to(ROOT)} (prompt {len(prompt):,} chars, sha256 {sha(prompt)[:12]})")


def _fast_text(folder: Path) -> str | None:
    path = folder / "fast_prompt.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def write_index() -> None:
    rows, details = [], []
    for folder in versions():
        m = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        rows.append(f"| v{m['version']:03d} | {m['date']} | [{m['name']}](history/{folder.name}/system_prompt.md) | "
                    f"{m['prompt_chars']:,} | `{m['prompt_sha256'][:12]}` | `{m['schema_sha256'][:12]}` | "
                    f"{m['decision']} |")
        fast = (f" Fast lane prefix: [{m['fast_prompt_chars']:,} chars](history/{folder.name}/fast_prompt.md), "
                f"sha256 `{m['fast_prompt_sha256'][:12]}`.") if m.get("fast_prompt_sha256") else ""
        details.append(f"### v{m['version']:03d} {m['name']} ({m['date']})\n\n{m['change']}{fast}\n")
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(HEADER + "\n".join(rows) + "\n\n## Changes\n\n" + "\n".join(details), encoding="utf-8")


def check() -> None:
    existing = versions()
    if not existing:
        raise SystemExit("no snapshot yet")
    prompt, schema, fast = render_all(ROOT / "apps" / "market-ai-orc")
    newest = existing[-1]
    stale = [name for name, text in (("system_prompt.md", prompt), ("response_schema.json", schema))
             if (newest / name).read_text(encoding="utf-8") != text]
    if _fast_text(newest) != fast:
        stale.append("fast_prompt.md")
    if stale:
        raise SystemExit(f"the code renders a new {', '.join(stale)}; record it: scripts/snapshot_system_prompt.py record")
    print(f"current: {newest.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("slug")
    rec.add_argument("--decision", required=True, help="the user's words and date that approved the change")
    rec.add_argument("--change", required=True, help="what changed, in plain words")
    rec.add_argument("--source", default=str(ROOT / "apps" / "market-ai-orc"), help="orc tree to render")
    rec.add_argument("--date", default=dt.date.today().isoformat())
    sub.add_parser("check")
    args = parser.parse_args()
    if args.command == "record":
        record(args.slug, args.decision, args.change, Path(args.source), args.date)
    else:
        check()
