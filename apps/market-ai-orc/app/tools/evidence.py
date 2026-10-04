"""get_evidence (round 2026-10-03 D6; HIGH_ALERT_PLAN.md Prioritas 2, ROUND_PLAN_2026-10-03_FASE_D.md): every main
claim of an answer recomputed by the backend on a path separate from the model's own code.

The model states a claim, the number as it will write it, and a recipe:

- WAREHOUSE (tier 1): a summary of a governed table (filters, a measure, a period, optionally the row of one group),
  run by the SQL Governor's POST /v1/summary under its own catalog rules;
- BASE_TABLE (tier 2): conditions and a measure over a base table the analysis released (for example 132 crash days
  x one broker, count where net > 0), recomputed by the sandbox from the stored file.

The backend compares its value with the number as written, with the rounding the number shows (the provenance rule):
TERCEK or TIDAK_COCOK (with the difference). A refused recipe is TIDAK_BISA_DICEK; claims past the limits (10 per
answer, 120 seconds) are TIDAK_DICEK_BATAS, never silently dropped. The model sees the status and the difference; the
user gets the evidence rows (at most 200) in the API response's evidence[], kept in AI_conversation_evidence.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..provenance import SourceIndex, parse_numbers
from .analysis import SandboxClient
from .artifacts import current_results, resolve_ref, source_bytes, stored_op
from .data_planner import sha256_json
from .metric import Period, as_of_date, predicate, scope_of
from .registry import ToolSpec
from .request_data import GovernorClient

MAX_CLAIMS = 10
TOTAL_SECONDS = 120.0
QUERY_SECONDS = 30.0
DESCRIPTION = (
    "Check main claims before answering: the backend recomputes each one apart from your code and compares it with "
    "the number as you will write it. WAREHOUSE recomputes from a governed table (filters, measure, period, the row "
    "of one group); BASE_TABLE from a released base table (conditions and a measure, e.g. count where net > 0). "
    "Returns TERCEK or TIDAK_COCOK with the difference per claim; the user gets the evidence rows. At most 10 claims."
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Condition(Strict):
    column: str = Field(min_length=1, max_length=63)
    op: Literal["EQ", "NE", "GT", "GE", "LT", "LE", "IN"]
    value: str | None = Field(max_length=100, description="The compared value (numbers as text); null with IN.")
    values: list[str] | None = Field(max_length=50, description="IN only.")


class BaseTableRecipe(Strict):
    ref: str | None = Field(pattern=r"^(out\.)?o[1-9][0-9]{0,3}$", description="The base table's reference.")
    output_id: str | None = Field(pattern=r"^out_[0-9a-f]{24}$")
    where: list[Condition] | None = Field(max_length=10)
    measure: Literal["COUNT", "COUNT_DISTINCT", "SUM", "MIN", "MAX", "MEAN"]
    column: str | None = Field(max_length=63, description="The measured column; null for COUNT.")

    @model_validator(mode="after")
    def _one_source(self) -> "BaseTableRecipe":
        if (self.ref is None) == (self.output_id is None):
            raise ValueError("give exactly one of ref or output_id")
        return self


class Equal(Strict):
    column: str = Field(min_length=1, max_length=63)
    value: str = Field(min_length=1, max_length=100)


class Filter(Strict):
    column: str = Field(min_length=1, max_length=63)
    values: list[str] = Field(min_length=1, max_length=50)


class WarehouseRecipe(Strict):
    source_table: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
    filters: list[Filter] | None = Field(max_length=6)
    group_by: list[str] | None = Field(max_length=4)
    measure_column: str | None = Field(max_length=63, description="Null for COUNT.")
    function: Literal["SUM", "MIN", "MAX", "FIRST", "LAST", "COUNT", "DAYS"] = Field(description=(
        "DAYS: the number of distinct dates with a row (measure_column null)."))
    period: Period
    as_of: str | None = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    row: list[Equal] | None = Field(max_length=4, description="The group the claim is about (its group_by values).")


class Claim(Strict):
    text: str = Field(min_length=1, max_length=300, description="The claim in words.")
    value_text: str = Field(min_length=1, max_length=40, description="The number exactly as the answer writes it.")
    warehouse: WarehouseRecipe | None
    base_table: BaseTableRecipe | None

    @model_validator(mode="after")
    def _one_recipe(self) -> "Claim":
        if (self.warehouse is None) == (self.base_table is None):
            raise ValueError("give exactly one recipe: warehouse or base_table")
        return self


class GetEvidenceArgs(Strict):
    claims: list[Claim] = Field(min_length=1, max_length=MAX_CLAIMS + 5)


def as_number(value: Any) -> float | None:
    """A backend value as a number: the Governor sends numeric aggregates as decimal text (exact), the sandbox as
    JSON numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(Decimal(value.strip()))
        except (InvalidOperation, ValueError):
            return None
    return None


def compare(value_text: str, backend: float | None) -> tuple[str, float | None]:
    """(status, difference): the claimed number against the backend's, with the rounding the number shows."""
    shown = parse_numbers(value_text)
    if backend is None or not shown:
        return "TIDAK_BISA_DICEK", None
    index = SourceIndex()
    index.add("BACKEND", [float(backend)])
    if index.kinds_matching(shown[0], False):
        return "TERCEK", 0.0
    # the reading of the written number closest to the backend's (1.250 is 1250 or 1.25 by its separators)
    claimed = min((value for value, _ in shown[0].candidates), key=lambda value: abs(float(backend) - value))
    return "TIDAK_COCOK", float(backend) - claimed


def _base_table(client: SandboxClient, recipe: BaseTableRecipe) -> dict[str, Any]:
    results = current_results.get()
    record = results.record if results is not None else {}
    entry = resolve_ref(record, recipe.ref) if recipe.ref else next(
        (o for o in record.get("outputs") or [] if o.get("output_id") == recipe.output_id), None)
    if recipe.ref and entry is None:
        return {"refused": "REF_NOT_FOUND: no output of this conversation has this reference"}
    output_id = str((entry or {}).get("output_id") or recipe.output_id)
    data, stored = source_bytes(results, output_id, (entry or {}).get("session_id"))
    fmt = stored.format if stored is not None else "PARQUET"
    meta = {"format": fmt, "checksum_sha256": hashlib.sha256(data).hexdigest(), "measure": recipe.measure,
            "column": recipe.column, "where": [c.model_dump() for c in recipe.where or []]}
    status, body, _ = stored_op(client, "recount", data, meta, timeout=QUERY_SECONDS)
    if status != 200:
        error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
        return {"refused": f"{error.get('code') or status}: {str(error.get('message') or '')[:300]}"}
    return {"value": body.get("value"), "rows": body.get("rows") or [], "rows_matched": body.get("rows_matched"),
            "source": {"output_id": output_id, "ref": (entry or {}).get("ref"), "name": (entry or {}).get("name")
                       or (stored.name if stored else None), "rows_total": body.get("rows_total")}}


def _warehouse(governor: GovernorClient, recipe: WarehouseRecipe) -> dict[str, Any]:
    counted = recipe.function in ("COUNT", "DAYS")
    if counted != (recipe.measure_column is None):
        return {"refused": "COUNT and DAYS take measure_column null; the other functions name a column"}
    as_of = as_of_date(recipe.as_of)
    period = recipe.period
    window = {"trading_days": period.trading_days, "as_of": as_of} if period.trading_days is not None \
        else {"from": period.start_date, "to": period.end_date}
    spec = {"summary_version": "summary_spec/v1", "source_table": recipe.source_table,
            "scope": scope_of({"type": "ALL"}, [predicate(f.column, f.values) for f in recipe.filters or []]),
            "restrictions": [], "group_by": list(recipe.group_by or []),
            # DAYS reads the summary's own days_present (distinct dates of the group), next to a row count
            "measures": [{"column": recipe.measure_column, "function": "COUNT" if counted else recipe.function,
                          "as": "claimed_value"}],
            "period": window}
    answer = governor.summary(spec, {"purpose": "EVIDENCE", "recipe_sha256": sha256_json(spec)},
                              timeout=QUERY_SECONDS)
    if answer.get("status") != "OK":
        return {"refused": f"{answer.get('code') or answer.get('status')}: {str(answer.get('message') or '')[:300]}"}
    rows = answer.get("rows") or []
    wanted = {e.column: e.value for e in recipe.row or []}
    chosen = [r for r in rows if all(str(r.get(k)) == v for k, v in wanted.items())]
    source = {"source_table": recipe.source_table, "query_id": answer.get("query_id"), "period": answer.get("period")}
    if len(chosen) != 1:
        return {"refused": f"the recipe selects {len(chosen)} rows of {len(rows)}; name the group in row",
                "rows": rows[:200], "source": source}
    value = chosen[0].get("days_present") if recipe.function == "DAYS" else chosen[0].get("claimed_value")
    return {"value": value, "rows": rows[:200], "rows_matched": len(rows), "source": source}


def evidence_specs(client: SandboxClient, governor: GovernorClient, *, timeout_seconds: float,
                   max_result_bytes: int) -> list[ToolSpec]:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetEvidenceArgs)
        results = current_results.get()
        started = time.monotonic()
        checked = sum(1 for e in (results.evidence if results is not None else []))
        out: list[dict[str, Any]] = []
        for claim in arguments.claims:
            entry: dict[str, Any] = {"evidence_id": f"evd_{secrets.token_hex(12)}", "claim": claim.text,
                                     "value_text": claim.value_text,
                                     "kind": "WAREHOUSE" if claim.warehouse is not None else "BASE_TABLE",
                                     "recipe": (claim.warehouse or claim.base_table).model_dump(),
                                     "backend_value": None, "difference": None, "rows": [], "source": {}}
            if checked >= MAX_CLAIMS or time.monotonic() - started > TOTAL_SECONDS:
                entry["status"] = "TIDAK_DICEK_BATAS"
            else:
                checked += 1
                try:
                    found = _warehouse(governor, claim.warehouse) if claim.warehouse is not None \
                        else _base_table(client, claim.base_table)
                except Exception as exc:  # noqa: BLE001 - one claim's failure is its status, not the tool's
                    found = {"refused": f"{type(exc).__name__}: {str(exc)[:200]}"}
                entry.update(rows=list(found.get("rows") or [])[:200], source=found.get("source") or {},
                             rows_matched=found.get("rows_matched"))
                if "refused" in found:
                    entry.update(status="TIDAK_BISA_DICEK", reason=found["refused"])
                else:
                    entry["backend_value"] = as_number(found.get("value"))
                    entry["status"], entry["difference"] = compare(claim.value_text, entry["backend_value"])
                    if entry["status"] == "TIDAK_BISA_DICEK":  # never without a reason
                        entry["reason"] = "the backend found no value for the recipe" \
                            if entry["backend_value"] is None else "the number as written could not be read"
            if results is not None:
                results.evidence.append(entry)
                if results.store is not None and results.conversation_id:
                    try:
                        results.store.save_evidence(results.conversation_id, results.request_id, entry)
                        entry["stored"] = True
                    except Exception:  # noqa: BLE001 - the check stands; it is not kept
                        entry["stored"] = False
            out.append({k: entry.get(k) for k in ("evidence_id", "claim", "value_text", "status", "backend_value",
                                                  "difference", "reason") if entry.get(k) is not None}
                       | {"rows_matched": entry.get("rows_matched")})
        mismatched = [e for e in out if e["status"] == "TIDAK_COCOK"]
        return {"status": "OK", "claims": out,
                "next_action": "FIX_THE_NUMBERS_OR_SAY_SO" if mismatched else "RETURN_FINAL_RESPONSE",
                "note": "Write each checked number as value_text; a TIDAK_COCOK number must be corrected or stated as "
                        "not matching. The user sees the evidence rows; never paste them."}

    return [ToolSpec(name="get_evidence", description=DESCRIPTION, arguments_model=GetEvidenceArgs, handler=handler,
                     timeout_seconds=TOTAL_SECONDS + QUERY_SECONDS + 10, max_result_bytes=max_result_bytes)]
