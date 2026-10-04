"""get_lineage (round 2026-10-03 D3; ROUND_PLAN_2026-10-03_FASE_D.md): where a number came from.

The chain answer -> output -> execution (code) -> bundle -> Governor query -> source tables was spread over the data
record, the sandbox and the store, and the Governor query was not recorded at all. get_lineage puts it together from
what each layer records, with no row values:

- the output: name, definition, data date, label (data record or the conversation's store);
- the execution that released it: code hash, modules, status and what it read (ranges, columns, earlier outputs);
- the bundle: per dataset its source table, row filter (readable, from the data record), restricting relationships,
  rows, actual ranges and the Governor queries (bundles made before D3: NOT_RECORDED);
- earlier outputs the execution loaded (load_output), followed up to three levels.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis import SandboxClient
from .artifacts import RunResults, current_results, pending_execution, resolve_ref
from .registry import ToolSpec
from .request_data import current_request_id

BUNDLE_LINEAGE_VERSION = 1  # the sandbox's GET /v1/bundles/{id}/lineage
MAX_DEPTH = 3
DESCRIPTION = (
    "Where an output's numbers came from: its definition and data date, the execution that made it (code hash, "
    "modules, what it read), the bundle (source tables, row filters, ranges, rows) and the Governor queries, and "
    "earlier outputs it loaded. Give ref (out.o3), output_id or execution_id. No row values."
)


class GetLineageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str | None = Field(pattern=r"^(out\.)?o[1-9][0-9]{0,3}$", description="The output's value reference.")
    output_id: str | None = Field(pattern=r"^out_[0-9a-f]{24}$")
    execution_id: str | None = Field(pattern=r"^exe_[0-9a-f]{24}$")

    @model_validator(mode="after")
    def _one_source(self) -> "GetLineageArgs":
        if sum(v is not None for v in (self.ref, self.output_id, self.execution_id)) != 1:
            raise ValueError("give exactly one of ref, output_id or execution_id")
        return self


def _record_output(results: RunResults, output_id: str) -> dict[str, Any] | None:
    return next((o for o in results.record.get("outputs") or [] if isinstance(o, dict)
                 and o.get("output_id") == output_id), None)


def _output_view(results: RunResults, output_id: str) -> dict[str, Any] | None:
    """The output as the data record or the store knows it (lineage, definition, data date)."""
    entry = _record_output(results, output_id)
    stored = results.store.output(results.conversation_id, output_id) \
        if results.store is not None and results.conversation_id else None
    if entry is None and stored is None:
        return None
    lineage = (entry or {}).get("lineage") or (stored.lineage if stored else None) or {}
    return {"output_id": output_id, "ref": (entry or {}).get("ref"),
            "name": (entry or {}).get("name") or (stored.name if stored else None),
            "label": (entry or {}).get("label") or (stored.label if stored else None),
            "definition": (entry or {}).get("definition") or (stored.definition if stored else None),
            "data_as_of": (entry or {}).get("data_as_of") or (lineage.get("data_as_of") if isinstance(lineage, dict)
                                                               else None) or (stored.data_as_of if stored else None),
            "request_id": (entry or {}).get("request_id") or (stored.request_id if stored else None),
            "stored": stored is not None, "_lineage": lineage if isinstance(lineage, dict) else {}}


def _execution_view(results: RunResults, execution_id: str) -> dict[str, Any]:
    row = (results.store.execution(results.conversation_id, execution_id)
           if results.store is not None and results.conversation_id else None) \
        or pending_execution(results, execution_id)
    if row is None:
        return {"execution_id": execution_id, "status": "NOT_RECORDED"}
    access = row.get("access")
    reads = access.get("reads") if isinstance(access, dict) else access if isinstance(access, list) else []
    return {"execution_id": execution_id, "status": row.get("status"), "code_sha256": row.get("code_sha256"),
            "modules": row.get("modules") or [], "read": [r for r in reads or [] if isinstance(r, dict)][:20]}


def _need(results: RunResults, need_id: str | None) -> dict[str, Any]:
    return next((n for n in results.record.get("needs") or [] if isinstance(n, dict) and n.get("need_id") == need_id),
                {})


def _bundle(client: SandboxClient, bundle_id: str | None, need: dict[str, Any]) -> dict[str, Any] | None:
    if not bundle_id:
        return None
    response = client._call("GET", f"/v1/bundles/{bundle_id}/lineage", timeout=15.0,
                            params={"request_id": current_request_id.get() or ""})
    if response.status_code != 200:
        return {"input_bundle_id": bundle_id, "status": "NOT_AVAILABLE"}
    body = client._json(response)
    readable = {r.get("data_request_id"): r for r in need.get("requests") or [] if isinstance(r, dict)}
    for dataset in body.get("datasets") or []:
        request = readable.get(dataset.get("data_request_id")) or {}
        if request.get("scope"):
            dataset["scope"] = request["scope"]  # the row filter as text (the data record's derived reading)
        if request.get("restrictions"):
            dataset["restrictions"] = request["restrictions"]
    return body


def _source_tables(bundle: dict[str, Any] | None) -> list[str]:
    """The tables the numbers come from: each dataset's source table and the tables of its restrictions."""
    tables: list[str] = []
    for dataset in (bundle or {}).get("datasets") or []:
        names = [dataset.get("source_table")] + [str(r).split(":", 1)[0] for r in dataset.get("restrictions") or []]
        tables += [n for n in names if n and n not in tables]
    return tables


def lineage_of(client: SandboxClient, results: RunResults, output_id: str | None, execution_id: str | None,
               depth: int = 0, seen: set[str] | None = None) -> dict[str, Any]:
    seen = seen if seen is not None else set()
    out: dict[str, Any] = {}
    need_id = bundle_id = None
    if output_id is not None:
        seen.add(output_id)
        view = _output_view(results, output_id)
        if view is None:
            return {"status": "REJECTED", "code": "OUTPUT_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                    "message": "No output with this id or reference belongs to this conversation."}
        lineage = view.pop("_lineage")
        out["output"] = view
        execution_id = execution_id or lineage.get("execution_id")
        need_id, bundle_id = lineage.get("need_id"), lineage.get("bundle_id")
    if execution_id:
        out["execution"] = _execution_view(results, execution_id)
    need = _need(results, need_id)
    bundle = _bundle(client, bundle_id, need)
    if bundle is not None:
        out["bundle"] = bundle
        out["governor"] = [q for d in bundle.get("datasets") or [] if isinstance(d.get("governor"), list)
                           for q in d["governor"]]
    out["source_tables"] = _source_tables(bundle)
    loaded = [str(r.get("output_id")) for r in (out.get("execution") or {}).get("read") or []
              if r.get("kind") == "load_output" and r.get("output_id")]
    if loaded and depth < MAX_DEPTH:
        out["inputs"] = [lineage_of(client, results, o, None, depth + 1, seen) for o in loaded if o not in seen]
    elif loaded:
        out["inputs_not_followed"] = loaded
    return out


def lineage_specs(client: SandboxClient, *, timeout_seconds: float, max_result_bytes: int) -> list[ToolSpec]:
    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, GetLineageArgs)
        results = current_results.get()
        if results is None:
            return {"status": "REJECTED", "code": "OUTPUT_NOT_AVAILABLE", "next_action": "REPORT_LIMITATION",
                    "message": "Lineage needs the conversation's results."}
        output_id = arguments.output_id
        if arguments.ref is not None:
            entry = resolve_ref(results.record, arguments.ref)
            if entry is None:
                return {"status": "REJECTED", "code": "REF_NOT_FOUND", "next_action": "FIX_ARGUMENTS",
                        "message": "No output of this conversation has this reference; the data record lists them."}
            output_id = str(entry["output_id"])
        return lineage_of(client, results, output_id, arguments.execution_id)

    return [ToolSpec(name="get_lineage", effect="READS", description=DESCRIPTION, arguments_model=GetLineageArgs, handler=handler,
                     timeout_seconds=timeout_seconds + 30, max_result_bytes=max_result_bytes)]
