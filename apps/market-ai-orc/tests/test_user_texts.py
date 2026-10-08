"""M125 (user decision 2026-10-08): every line the backend writes for the user is plain Indonesian without internal
names (table, column, output, analysis or session ids, backend codes). The texts live in app/user_texts.py; this reads
them, every user-facing notice or line the orchestrator defines, and the lines it builds, so a new English or coded
line fails here wherever it is added."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app import user_texts as texts

APP = Path(__file__).resolve().parents[1] / "app"
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")
# a sentence in English reads as such through its function words (a language check, not a list of phrases)
ENGLISH = re.compile(r"\b(the|was|were|is|are|not|and|of|this|its|from|could|which|that|below|been)\b")
# orchestrator constants with these suffixes are written for the model, not the user (instructions in English)
MODEL_FACING = {"STRICT_SCHEMA_LINE": "a schema reminder sent to the model",
                "PLAN_VERSION_SUCCESS_RULE_LINE": "part of a repair instruction sent to the model"}


def problems(text: str) -> list[str]:
    plain = PLACEHOLDER.sub("", text)
    found = [f"internal name {m.group(0)!r}" for m in texts.INTERNAL_NAME.finditer(plain)]
    english = ENGLISH.findall(plain.lower())
    if len(english) >= 2:
        found.append(f"English ({', '.join(sorted(set(english)))})")
    return found


def user_texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in vars(texts).items():
        if name.isupper() and isinstance(value, str):
            out[name] = value
        elif name.isupper() and isinstance(value, dict) and name not in ("WORDS", "PARTS", "PLAN_ITEM"):
            out.update({f"{name}[{key}]": v for key, v in value.items() if isinstance(v, str)})
    out.update({f"WORDS[{key}]": value for key, value in texts.WORDS.items()})
    return out


def test_every_backend_text_for_the_user_is_plain_indonesian() -> None:
    found = {name: issues for name, text in user_texts().items() if (issues := problems(text))}
    assert found == {}, found


def test_pause_reasons_and_choices_are_plain_indonesian() -> None:
    from app import stop_policy
    shown = {f"OPTIONS[{k}]": v for k, v in stop_policy.OPTIONS.items()}
    shown.update({f"CAUSES[{k}]": c.reason for k, c in stop_policy.CAUSES.items() if c.reason})
    found = {name: issues for name, text in shown.items() if (issues := problems(text))}
    assert found == {}, found


def orchestrator_constants() -> dict[str, str]:
    """Every module's notices and lines (the orchestrator, mode 4, the routers, ...)."""
    out = {}
    for path in sorted(APP.glob("*.py")):
        out.update({f"{path.stem}.{name}": text for name, text in module_constants(path).items()})
    return out


def module_constants(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.endswith(("_NOTICE", "_LINE")) and name not in MODEL_FACING:
                try:
                    out[name] = ast.literal_eval(node.value)
                except ValueError:
                    continue
    return out


def test_the_orchestrators_own_notices_and_lines_are_plain_indonesian() -> None:
    found = {name: issues for name, text in orchestrator_constants().items() if (issues := problems(text))}
    assert found == {}, found


def test_the_lines_the_orchestrator_builds_for_the_user_are_plain_indonesian() -> None:
    """Literal text appended to a response's limitation lines (lines.append / to_confirm) inside the orchestrator."""
    source = (APP / "orchestrator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append" \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "lines" and node.args:
            parts = text_parts(node.args[0])
            text = " ".join(parts)
            if text and (issues := problems(text)):
                found.append((node.lineno, text[:80], issues))
    # the confirmation, model-memory and debug lines are built elsewhere; the user's lines here must all be clean
    assert [f for f in found if f[0] not in DEBUG_LINES(source)] == [], found


def text_parts(node: ast.AST) -> list[str]:
    """The literal text of an expression: string constants and f-string pieces, not dict keys or call arguments."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    if isinstance(node, ast.BinOp):
        return text_parts(node.left) + text_parts(node.right)
    return []


def DEBUG_LINES(source: str) -> set[int]:
    """Lines appended to lists that are not shown to the user (a bundle listing, a value-reference check)."""
    return {i for i, line in enumerate(source.splitlines(), start=1)
            if 'lines.append("- " + dumps(' in line or 'lines.append(f"{expression} -> ' in line}


def test_a_code_without_words_is_shown_readable_not_raw() -> None:
    assert texts.words("SUPPORTED") == "didukung data"
    assert texts.words("SOMETHING_NEW_FROM_THE_ENGINE") == "something new from the engine"
    assert "_" not in texts.words("ANOTHER_CODE")


def test_a_cited_figure_is_named_from_its_address() -> None:
    """Derived from the address, so a new field or output needs no wording change to be readable."""
    assert texts.value_label("finding.vol_spike_up.groups.CONDITION.dates") == \
        "Dari hasil riset: jumlah tanggal, kelompok sinyal"
    assert texts.value_label("out.o3.rows.2.mean_return", {"out.o3": "Peringkat broker"}) == \
        "Dari Peringkat broker: mean return"
    # M125 P2 (live answer 2026-10-08): a row picked by its key is named by the key, never "rows[ticker=bris]"
    assert texts.value_label("reference.r1.rows[Ticker=BRIS].Company Name") == \
        "Dari tabel referensi: company name (BRIS)"
    assert texts.value_label("finding.h1.angle_a.condition_mean") == "Dari hasil riset: rata-rata kelompok sinyal, sudut a"
    assert "_" not in texts.value_label("finding.x.some_new_field")


def test_a_plan_value_to_confirm_names_its_place_in_the_plan() -> None:
    assert texts.plan_item("experiments", 0) == "eksperimen 1" and texts.plan_item("angles", 2) == "sudut 3"
    assert texts.horizon_text({(10, "DAY")}) == "10 hari"


def test_every_namespace_the_orchestrator_registers_has_a_name_for_the_reader() -> None:
    """M125 P2: a value reference reads one of the namespaces the orchestrator registers; each is named in
    SOURCE_NAMES, so a new namespace fails here until it has words (derived from the code, not listed by hand)."""
    import re
    from pathlib import Path
    from app.value_refs import OUTSIDE_NAMESPACES
    code = (Path(__file__).resolve().parents[1] / "app" / "orchestrator.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'sources\.add\(\(?"([a-z]+)"', code)) | set(OUTSIDE_NAMESPACES.values())
    assert registered and registered <= set(texts.SOURCE_NAMES), registered - set(texts.SOURCE_NAMES)
    for name in texts.SOURCE_NAMES.values():
        assert not texts.INTERNAL_NAME.search(name)
