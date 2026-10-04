"""Write AI_MODELS.md: every place in the repository that calls a language model, with the model, reasoning, output-token
limit, tools, structured output and provider routing of that call, the settings that control them (name and code
default) and the values set on Railway dev (user request 2026-10-04: one up-to-date list in the repo).

Derived from the code, not written by hand:
- call sites: every dict literal with a "model" key and an "input"/"messages"/"instructions" key in apps/<service>/app,
  read with ast, plus the calls that start from a payload builder of the same file and then change it
  (payload.update({...}) and payload["key"] = value);
- settings: the environment names read in each service's app/config.py, with their default, kept when the name is
  about models (MODEL, REASONING, TOKENS, PROVIDER, CONTEXT, ENGINE, SLOT, RESULTS, REPLAY, MODE, ROUTER, SECONDS).
  Names that hold secrets (_KEY, _SECRET, _PASSWORD, _URL, _TOKEN) are never listed;
- Railway: whether the service exists in .railway/railway.ts.
The only hand-written part is PURPOSE, one sentence per call site; the generator fails on a call site without a
sentence or a sentence for a call site that no longer exists. market-ai-orc tests/test_ai_models_doc.py fails when
AI_MODELS.md drifts from the code.

The dev values are live state: pass --dev-values with a JSON object name -> value built from `railway variables --kv`
of market-ai-orc and market-web-governor, filtered to the listed names (see --help). Values that look like secrets are
refused. Without --dev-values the snapshot already in AI_MODELS.md is kept.

Usage (from the repository root): python scripts/generate_ai_models_doc.py [--dev-values values.json --date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "AI_MODELS.md"
SNAPSHOT_START = "<!-- dev-values:start -->"
SNAPSHOT_END = "<!-- dev-values:end -->"
SERVICES = ("market-ai-orc", "market-web-governor", "market-ai-backend")
PAYLOAD_KEYS = {"input", "messages", "instructions"}
FIELDS = ("model", "reasoning", "max_output_tokens", "tools", "tool_choice", "text", "store", "provider", "session_id")
SETTING_NAME = re.compile(r"^(AI_|WEB_|OPENROUTER_).*(MODEL|REASON|TOKENS|PROVIDER|CONTEXT|ENGINE|SLOT|RESULTS|REPLAY|MODE|ROUTER|SECONDS)")
SECRET_NAME = re.compile(r"(_KEY|_SECRET|_PASSWORD|_URL|_TOKEN)$")
SECRET_VALUE = re.compile(r"^(sk-|Bearer )|[A-Za-z0-9_\-]{40,}")

# One sentence per call site ("<service>:<file>:<function>"), plain language for the team.
PURPOSE = {
    "market-ai-orc:orchestrator.py:_loop":
        "Loop utama AI analis: setiap langkah percakapan dengan alat (data, sandbox, bukti, fakta web) sampai jawaban "
        "final; dipakai juga oleh setiap langkah mode 4.",
    "market-ai-orc:orchestrator.py:_router_call":
        "Dua router (satu panggilan kecil tanpa alat, kriteria di AI_ROUTER.md): router pesan pertama (classify_first: "
        "CHAT, FACT, ANALYSIS, RESEARCH, EXPLORE) dan router pesan lanjutan (classify_turn: CLARIFY, INSIGHT, CONTINUE, "
        "APPROVE, ...).",
    "market-ai-orc:orchestrator.py:_classify_reply":
        "Membaca balasan user atas rencana riset yang menunggu (setuju, ubah, batal, topik lain).",
    "market-web-governor:ask.py:ask":
        "Jawaban akhir riset web /v1/ask dari artikel yang sudah dibaca.",
    "market-web-governor:ask.py:_implications":
        "Implikasi untuk pasar dari jawaban riset web /v1/ask.",
    "market-web-governor:ask.py:_follow_ups":
        "Usulan pertanyaan lanjutan untuk /v1/ask.",
    "market-web-governor:ask.py:_plan":
        "Merencanakan kueri pencarian untuk /v1/ask.",
    "market-web-governor:ask.py:_scan":
        "Satu pencarian web (Exa) per kueri rencana /v1/ask.",
    "market-web-governor:ask.py:_read_articles":
        "Memilih artikel dari hasil pencarian lalu membaca isinya (pencarian satu hasil per artikel).",
    "market-web-governor:ask.py:_review":
        "Menilai apakah bukti /v1/ask sudah cukup atau perlu putaran pencarian lagi.",
    "market-web-governor:fact.py:_search":
        "Fakta ringan /v1/fact (alat find_web_fact AI): dua pencarian web paralel, satu terbatas ke domain resmi.",
    "market-web-governor:fact.py:_extract":
        "Fakta ringan /v1/fact: mengambil nilai dan kutipan verbatim per sumber dari hasil pencarian.",
    "market-web-governor:provider.py:research_criterion":
        "Riset web per kriteria bukti (WebNeedSpec): satu pencarian per kriteria lalu penilaian.",
    "market-web-governor:provider.py:read_document":
        "Membaca satu dokumen/URL untuk riset web.",
    "market-web-governor:provider.py:classify":
        "Klasifikasi event/berita web dengan skema JSON ketat (slot klasifikasi, dicek silang slot lain).",
    "market-ai-backend:orchestrator.py:_tool_loop":
        "Loop AI layanan lama market-ai-backend.",
}


def _src(node: ast.AST | None) -> str:
    return "" if node is None else ast.unparse(node)


def _tool_types(node: ast.AST | None) -> str:
    if node is None:
        return ""
    found = []
    for item in ast.walk(node):
        if isinstance(item, ast.Dict):
            entries = {k.value: v for k, v in zip(item.keys, item.values) if isinstance(k, ast.Constant)}
            if "type" in entries:
                kind = _src(entries["type"]).strip("'\"")
                params = entries.get("parameters")
                extra = []
                if isinstance(params, ast.Dict):
                    for k, v in zip(params.keys, params.values):
                        if isinstance(k, ast.Constant) and k.value in ("engine", "max_results", "max_uses"):
                            extra.append(f"{k.value}={_src(v)}")
                found.append(kind + (f" ({', '.join(extra)})" if extra else ""))
    return "; ".join(found) or _src(node)


def _text_format(node: ast.AST | None) -> str:
    if node is None:
        return ""
    for item in ast.walk(node):
        if isinstance(item, ast.Dict):
            entries = {k.value: v for k, v in zip(item.keys, item.values) if isinstance(k, ast.Constant)}
            if "type" in entries and "name" in entries:
                return f"{_src(entries['type']).strip(chr(39))} {_src(entries['name']).strip(chr(39))}"
    return _src(node)


def _fields(entries: dict[str, ast.AST]) -> dict[str, str]:
    out = {}
    for key in FIELDS:
        value = entries.get(key)
        if key == "tools":
            out[key] = _tool_types(value)
        elif key == "text":
            out[key] = _text_format(value)
        else:
            out[key] = _src(value)
    return out


def call_sites() -> list[dict]:
    sites: list[dict] = []
    for service in SERVICES:
        for path in sorted((ROOT / "apps" / service / "app").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            builders = set()
            functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            seen_lines = set()
            for fn in functions:
                for node in ast.walk(fn):
                    if isinstance(node, ast.Dict) and node.lineno not in seen_lines:
                        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                        if "model" in keys and keys & PAYLOAD_KEYS:
                            seen_lines.add(node.lineno)
                            entries = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
                            # keys the same function adds to that dict afterwards (payload["tools"] = tools)
                            local = {t.id for a in ast.walk(fn) if isinstance(a, (ast.Assign, ast.AnnAssign))
                                     and a.value is node
                                     for t in (a.targets if isinstance(a, ast.Assign) else [a.target])
                                     if isinstance(t, ast.Name)}
                            for a in ast.walk(fn):
                                if isinstance(a, ast.Assign) and isinstance(a.targets[0], ast.Subscript) and \
                                        isinstance(a.targets[0].value, ast.Name) and a.targets[0].value.id in local \
                                        and isinstance(a.targets[0].slice, ast.Constant):
                                    entries.setdefault(a.targets[0].slice.value, a.value)
                            sites.append({"service": service, "file": path.name, "function": fn.name,
                                          "line": node.lineno, **_fields(entries)})
                            # a builder returns the payload itself for its callers to send (and maybe change)
                            names = {t.id for a in ast.walk(fn) if isinstance(a, ast.Assign) and a.value is node
                                     for t in a.targets if isinstance(t, ast.Name)}
                            names |= {a.target.id for a in ast.walk(fn) if isinstance(a, ast.AnnAssign)
                                      and a.value is node and isinstance(a.target, ast.Name)}
                            if any(isinstance(r, ast.Return) and (r.value is node or isinstance(r.value, ast.Name)
                                                                  and r.value.id in names) for r in ast.walk(fn)):
                                builders.add(fn.name)
            # builders that are then changed by their callers (payload = self._payload(...); payload["x"] = ...)
            for fn in functions:
                if fn.name in builders:
                    continue
                called = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                          and n.func.attr in builders]
                if not called:
                    continue
                entries: dict[str, ast.AST] = {}
                for node in ast.walk(fn):
                    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Subscript) and \
                            isinstance(node.targets[0].slice, ast.Constant):
                        entries[node.targets[0].slice.value] = node.value
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                            node.func.attr == "update" and node.args and isinstance(node.args[0], ast.Dict):
                        for k, v in zip(node.args[0].keys, node.args[0].values):
                            if isinstance(k, ast.Constant):
                                entries[k.value] = v
                base = next(s for s in sites if s["file"] == path.name and s["function"] == called[0].func.attr
                            and s["service"] == service)
                merged = {**base, **{k: v for k, v in _fields(entries).items() if v}}
                merged.update({"function": fn.name, "line": called[0].lineno,
                               "builder": called[0].func.attr})
                sites.append(merged)
    # a payload builder only called by others is listed through its callers
    callers = {(s["service"], s["file"], s.get("builder")) for s in sites if s.get("builder")}  # listed by caller
    return [s for s in sites if (s["service"], s["file"], s["function"]) not in callers]


DEFAULT_PATTERNS = [
    re.compile(r'_(?:integer|ratio|boolean|optional|float|flag)\(\s*env\s*,\s*"(?P<name>[A-Z0-9_]+)"\s*(?:,\s*(?P<default>[^,)]+))?'),
    re.compile(r'env\.get\(\s*"(?P<name>[A-Z0-9_]+)"\s*(?:,\s*(?P<default>"[^"]*"|[^,)]+))?'),
    re.compile(r'prefix\s*\+\s*"(?P<name>[A-Z0-9_]+)"'),
]


def settings() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for service in SERVICES:
        config = ROOT / "apps" / service / "app" / "config.py"
        if not config.exists():
            continue
        text = config.read_text(encoding="utf-8")
        found: dict[str, str] = {}
        for pattern in DEFAULT_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group("name")
                if pattern is DEFAULT_PATTERNS[2]:
                    name = "WEB_SLOT_<n>_" + name
                default = (match.groupdict().get("default") or "").strip()
                if default in ('""', "''", ""):
                    # env.get("X", "").strip() or "fallback": the fallback is the real default
                    line = text[match.end():text.find("\n", match.end())]
                    fallback = re.search(r'\bor\s+("[^"]*"|\d[\d_.]*)', line)
                    default = fallback.group(1) if fallback else default
                if SETTING_NAME.search(name if not name.startswith("WEB_SLOT_<n>_") else "WEB_" + name) \
                        and not SECRET_NAME.search(name):
                    found.setdefault(name, default or "(tidak ada)")
        out[service] = sorted(found.items())
    return out


def deployed() -> dict[str, bool]:
    text = (ROOT / ".railway" / "railway.ts").read_text(encoding="utf-8")
    return {service: f'"/apps/{service}"' in text for service in SERVICES}


def _plain(site: dict) -> str:
    key = f"{site['service']}:{site['file']}:{site['function']}"
    if key not in PURPOSE:
        raise SystemExit(f"PURPOSE has no sentence for {key!r}: add one in scripts/generate_ai_models_doc.py")
    return PURPOSE[key]


def _cell(value: str) -> str:
    return f"`{value}`".replace("|", "\\|") if value else "-"


def _snapshot_values(snapshot: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"^\| `([A-Z0-9_]+)` \| `([^`]*)` \|$", snapshot, re.M)}


def in_use(snapshot: str) -> list[str]:
    """Which model each caller uses on dev, derived from the snapshot (empty when there is none)."""
    v = _snapshot_values(snapshot)
    if not v:
        return []
    switch = v.get("AI_MODEL_SWITCH", "1")
    orc = v.get("AI_MODEL_2") if switch == "2" else v.get("AI_MODEL")

    def slot(n: str) -> str:
        model = v.get(f"WEB_SLOT_{n}_MODEL") or (v.get("WEB_OPENROUTER_MODEL") if n == "1" else None)
        return f"`{model}` (slot {n})" if model else f"slot {n} (kosong)"
    rows = ["| Pemakai | Model di dev | Diturunkan dari |", "|---|---|---|",
            f"| orc: semua panggilan | `{orc}` | `AI_MODEL_SWITCH={switch}` |",
            f"| web-governor: fakta, riset web, /v1/ask | {slot(v.get('WEB_DEFAULT_SLOT', '1'))} | `WEB_DEFAULT_SLOT` |",
            f"| web-governor: klasifikasi | {slot(v.get('WEB_CLASSIFIER_SLOT', '1'))} | `WEB_CLASSIFIER_SLOT` |"]
    check = v.get("WEB_CLASSIFIER_CHECK_SLOT", "0")
    if check not in ("", "0"):
        rows.append(f"| web-governor: cek silang klasifikasi | {slot(check)} | `WEB_CLASSIFIER_CHECK_SLOT` |")
    return rows


def render(snapshot: str) -> str:
    sites, conf, live = call_sites(), settings(), deployed()
    keys = {f"{s['service']}:{s['file']}:{s['function']}" for s in sites}
    stale = sorted(set(PURPOSE) - keys)
    if stale:
        raise SystemExit(f"PURPOSE has sentences for call sites that no longer exist: {stale}")
    lines = ["# Model AI yang dipakai (dibuat dari kode)", "",
             "GENERATED by `scripts/generate_ai_models_doc.py` from the code of "
             + ", ".join(f"`apps/{s}`" for s in SERVICES) + " and the Railway dev values below; "
             "`apps/market-ai-orc/tests/test_ai_models_doc.py` fails when this file and the code drift apart. Do not "
             "edit by hand: change the code or PURPOSE, then regenerate (AGENTS.md, Mandatory workflow). Keputusan "
             "model dan penyedia ada di AGENTS.md (Model and provider).", "",
             "## Model yang dipakai sekarang (dev)", "", *(in_use(snapshot) or ["Belum ada snapshot dev."]), "",
             "## Layanan", "", "| Layanan | Ada di Railway (`.railway/railway.ts`) |", "|---|---|"]
    lines += [f"| `{s}` | {'ya' if live[s] else '**tidak dideploy**'} |" for s in SERVICES]
    lines += ["", "## Titik panggilan model", "",
              "Nilai seperti `self.settings.ai_model` atau `slot.model` dibaca dari setelan di bawah; nilai dev ada di "
              "bagian terakhir.", ""]
    for service in SERVICES:
        rows = [s for s in sites if s["service"] == service]
        if not rows:
            continue
        lines += [f"### `{service}`", "",
                  "| Fungsi | Untuk apa | Model | Reasoning | Maks. token keluaran | Alat | Keluaran terstruktur | "
                  "Penyedia / sesi |", "|---|---|---|---|---|---|---|---|"]
        for s in sorted(rows, key=lambda r: (r["file"], r["line"])):
            route = " ; ".join(x for x in (s["provider"], s["session_id"]) if x)
            lines.append(f"| `{s['file']}:{s['function']}` | {_plain(s)} | {_cell(s['model'])} | "
                         f"{_cell(s['reasoning'])} | {_cell(s['max_output_tokens'])} | {_cell(s['tools'])} | "
                         f"{_cell(s['text'])} | {_cell(route)} |")
        lines.append("")
    lines += ["## Setelan (nama variabel dan bawaan kode)", ""]
    for service, items in conf.items():
        lines += [f"### `{service}`", "", "| Variabel | Bawaan di kode |", "|---|---|"]
        lines += [f"| `{name}` | {_cell(default)} |" for name, default in items]
        lines.append("")
    lines += ["## Nilai di Railway dev", "", SNAPSHOT_START, snapshot.strip("\n"), SNAPSHOT_END, ""]
    return "\n".join(lines)


def listed_names() -> set[str]:
    return {name for items in settings().values() for name, _ in items}


def snapshot_from_values(values: dict[str, str], date: str) -> str:
    names = listed_names()
    patterns = [re.compile("^" + n.replace("<n>", r"\d+") + "$") for n in names if "<n>" in n]
    rows = [f"Diambil {date} dari `railway variables --kv` (hanya nama di daftar setelan; nilai rahasia ditolak).", "",
            "| Variabel | dev |", "|---|---|"]
    for name in sorted(values):
        if name not in names and not any(p.match(name) for p in patterns):
            continue
        value = str(values[name])
        if SECRET_NAME.search(name) or SECRET_VALUE.search(value) and "/" not in value:
            raise SystemExit(f"{name} looks like a secret: not written")
        rows.append(f"| `{name}` | `{value}` |")
    return "\n".join(rows)


def current_snapshot() -> str:
    if not TARGET.exists():
        return "Belum diambil."
    text = TARGET.read_text(encoding="utf-8")
    if SNAPSHOT_START not in text or SNAPSHOT_END not in text:
        return "Belum diambil."
    return text.split(SNAPSHOT_START, 1)[1].split(SNAPSHOT_END, 1)[0].strip("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Write AI_MODELS.md")
    parser.add_argument("--dev-values", help="JSON file: variable name -> value (non-secret model settings only)")
    parser.add_argument("--date", help="date of the snapshot, e.g. 2026-10-04")
    args = parser.parse_args()
    snapshot = current_snapshot()
    if args.dev_values:
        snapshot = snapshot_from_values(json.loads(Path(args.dev_values).read_text()), args.date or "")
    TARGET.write_text(render(snapshot), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
