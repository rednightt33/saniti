"""Research findings v2 (Multi-Angle Research): the independent validator of one bundle group.

It runs in the harness when the group's session completes, never in the model's process, and trusts nothing the
session computed. For each approved angle of the group it reads the recorded call and input (root-only copies,
checksummed when collected), checks the input against the angle's data contract, rebuilds a declarative input from
the bundle files with runtime/research_inputs.py, recomputes the statistics with runtime/research_engines.py and the
approved values (never the values the session passed), and writes one backend-authored finding per angle:

    FORMULA_AND_STATISTICS_VERIFIED  declarative input, reproduced here from the governed rows
    STATISTICS_VERIFIED              a frame the model's code built (inside the contract), statistics recomputed here
    EXECUTION_ONLY                   research_custom: nothing recomputable; at most INSUFFICIENT_EVIDENCE

An angle recorded twice, outside its contract, with an input that cannot be reproduced, or that the engine refuses is
INVALID; an angle without a record is missing (the completion stays INCOMPLETE) unless the caller finalizes the group,
which records it as NOT_RUN.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

VERSION = "research_findings/v2"
VALIDATOR_VERSION = 1
LEVEL_ORDER = ("EXECUTION_ONLY", "STATISTICS_VERIFIED", "FORMULA_AND_STATISTICS_VERIFIED")
RUNTIME = Path(__file__).resolve().parents[1] / "runtime"


def _module(name: str, filename: str):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, RUNTIME / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def engines():
    return _module("saniti_runtime_research_engines", "research_engines.py")


def inputs():
    _module("saniti_runtime_expression", "expression.py")  # research_inputs reads it under this private name
    return _module("saniti_runtime_research_inputs", "research_inputs.py")


def weakest(levels: list[str]) -> str | None:
    known = [level for level in levels if level in LEVEL_ORDER]
    return min(known, key=LEVEL_ORDER.index) if known else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_request(bundle: dict[str, Any], data_request_id: str, columns: list[str], path_of) -> Any:
    """Every delivered row of one bundle request (the files the session read), only the given columns."""
    import pandas as pd
    import pyarrow.parquet as pq

    dataset = next((d for d in bundle["datasets"] if d["data_request_id"] == data_request_id), None)
    if dataset is None:
        raise KeyError(data_request_id)
    frames = []
    for part in dataset["partitions"]:
        table = pq.read_table(path_of(bundle["input_bundle_id"], part["file"]))
        present = [c for c in columns if c in table.column_names]
        frames.append(table.select(present).to_pandas())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def _same(recorded, rebuilt) -> bool:
    """The recorded input equals the rebuilt one: same rows in (entity, date) order, same values (numbers within a
    relative 1e-9, missing values equal)."""
    import numpy as np
    import pandas as pd

    if set(recorded.columns) != set(rebuilt.columns) or len(recorded) != len(rebuilt):
        return False
    order = [c for c in ("entity", "date") if c in recorded.columns]
    a = recorded.assign(date=pd.to_datetime(recorded["date"]).dt.normalize()).sort_values(order, kind="mergesort")
    b = rebuilt.assign(date=pd.to_datetime(rebuilt["date"]).dt.normalize()).sort_values(order, kind="mergesort")
    a, b = a.reset_index(drop=True), b.reset_index(drop=True)
    for column in a.columns:
        x, y = a[column], b[column]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y) and not pd.api.types.is_bool_dtype(x):
            if not np.allclose(x.to_numpy(dtype="float64"), y.to_numpy(dtype="float64"), rtol=1e-9, atol=1e-12,
                               equal_nan=True):
                return False
        else:
            left = [None if v is None or (isinstance(v, float) and v != v) else v for v in x.tolist()]
            right = [None if v is None or (isinstance(v, float) and v != v) else v for v in y.tolist()]
            if [str(v) if isinstance(v, pd.Timestamp) else v for v in left] != \
                    [str(v) if isinstance(v, pd.Timestamp) else v for v in right]:
                return False
    return True


def _bounds(frame, angle: dict[str, Any], bundle: dict[str, Any], path_of) -> str | None:
    """None when the frame stays inside the contract (dates in the extracted windows, entities delivered)."""
    import pandas as pd

    names = [d["data_request_id"] for d in (angle.get("contract") or {}).get("datasets") or []]
    datasets = [d for d in bundle["datasets"] if d["data_request_id"] in names]
    windows = [(w["extract_from"], w["extract_to"]) for d in datasets for w in d.get("ranges") or []
               if w.get("extract_from") and w.get("extract_to")]
    if "date" in frame.columns and windows:
        dates = pd.to_datetime(frame["date"], errors="coerce")
        low, high = pd.Timestamp(min(w[0] for w in windows)), pd.Timestamp(max(w[1] for w in windows))
        if dates.isna().any() or ((dates < low) | (dates > high)).any():
            return "CONTRACT_DATE_OUTSIDE"
    if "entity" in frame.columns:
        delivered: set[str] = set()
        for dataset in datasets:
            column = dataset.get("entity_column")
            if column:
                rows = _read_request(bundle, dataset["data_request_id"], [column], path_of)
                delivered |= {str(v) for v in rows[column].dropna().tolist()}
        if delivered and not {str(v) for v in frame["entity"].dropna().tolist()} <= delivered:
            return "CONTRACT_ENTITY_OUTSIDE"
    return None


def _approved(angle: dict[str, Any]) -> dict[str, Any]:
    return {k: angle.get(k) for k in ("parameters", "expected_direction", "outcome_horizon_periods", "outcome_unit",
                                      "min_effect", "multiple_testing_policy", "candidate_count",
                                      "pairwise_comparisons", "holdout_start")}


def envelope(context: dict[str, Any], angle_id: str, angle: dict[str, Any], *, status: str, reason: str,
             level: str | None, direction: str = "NONE", result: dict[str, Any] | None = None,
             hashes: dict[str, Any] | None = None, output_ids: list[str] | None = None,
             warnings: list[str] | None = None) -> dict[str, Any]:
    result = result or {}
    primary = result.get("primary") or {}
    return {
        "findings_version": VERSION, "plan_id": context.get("plan_id"), "research_run_id": context.get("research_run_id"),
        "angle_id": angle_id, "angle_question": angle.get("angle_question"),
        "bundle_group_id": context.get("bundle_group_id"), "session_id": context.get("session_id"),
        "method_id": angle.get("method_id"), "method_family": angle.get("method_family"),
        "status": status, "status_reason": reason, "evidence_direction": direction,
        "expected_direction": angle.get("expected_direction"), "validation_level": level,
        "sample": result.get("sample"),
        "estimates": {"kind": result.get("estimate_kind"), "primary": {k: primary.get(k) for k in (
            "candidate", "estimate", "ci", "ci_adjusted", "p_value", "p_adjusted", "standard_error", "effective")},
            "candidates": [{k: c.get(k) for k in ("candidate", "estimate", "ci", "ci_adjusted", "p_value",
                                                  "p_adjusted")} for c in (result.get("candidates") or [])[:50]]},
        "comparator": result.get("comparator"), "multiple_testing": result.get("multiple_testing"),
        "secondary_checks": result.get("secondary"), "holdout": result.get("holdout"),
        "method_payload": result.get("method_payload"),
        "warnings": warnings or [], "limitations": [],
        "hashes": {**(context.get("hashes") or {}), **(hashes or {}),
                   "angle_data_contract_sha256": angle.get("angle_data_contract_sha256")},
        "versions": {"engine": getattr(engines(), "ENGINE_VERSION", None), "validator": VALIDATOR_VERSION},
        "released_output_ids": output_ids or []}


def validate_group(*, context: dict[str, Any], angles: dict[str, dict[str, Any]], bundle: dict[str, Any],
                   path_of, outputs: list[dict[str, Any]], executions: list[dict[str, Any]], outputs_root: Path,
                   finalize: bool = False) -> dict[str, Any]:
    """{findings: {angle_id: finding}, missing, invalid, unapproved, duplicates, calculation_validation}.
    outputs: this epoch's outputs of successful executions; executions: this epoch's executions."""
    import pandas as pd
    import pyarrow.parquet as pq

    E, I = engines(), inputs()
    by_execution = {e["execution_id"]: e for e in executions}
    ok_code = [e.get("code_sha256") or "" for e in executions if e["status"] == "OK"]
    session_code = hashlib.sha256("\n".join(ok_code).encode()).hexdigest()
    research_outputs = [o for o in outputs if str(o.get("name") or "").startswith(("research_call_", "research_input_"))]
    unapproved = sorted({o["name"] for o in research_outputs
                         if o["name"].split("_", 2)[-1] not in angles})
    findings: dict[str, dict[str, Any]] = {}
    missing, invalid, duplicates = [], [], []
    for angle_id, angle in sorted(angles.items()):
        calls = [o for o in research_outputs if o["name"] == f"research_call_{angle_id}"]
        stored_inputs = [o for o in research_outputs if o["name"] == f"research_input_{angle_id}"]
        if not calls:
            if finalize:
                findings[angle_id] = envelope(context, angle_id, angle, status="NOT_RUN", reason="NOT_RECORDED",
                                              level=None)
            else:
                missing.append(angle_id)
            continue
        ids = [o["output_id"] for o in calls + stored_inputs]
        if len(calls) > 1 or len(stored_inputs) > 1:
            duplicates.append(angle_id)
            invalid.append(angle_id)
            findings[angle_id] = envelope(context, angle_id, angle, status="INVALID", reason="DUPLICATE_ANGLE_OUTPUT",
                                          level=None, output_ids=ids)
            continue
        call_output = calls[0]
        code = (by_execution.get(call_output["execution_id"]) or {}).get("code_sha256")
        hashes = {"code_sha256": code, "session_code_sha256": session_code}

        def fail(reason: str, level: str | None = None) -> None:
            invalid.append(angle_id)
            findings[angle_id] = envelope(context, angle_id, angle, status="INVALID", reason=reason, level=level,
                                          hashes=hashes, output_ids=ids)

        try:
            call = json.loads((outputs_root / call_output["relative_path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fail("CALL_RECORD_UNREADABLE")
            continue
        if call.get("angle_id") != angle_id or call.get("method_id") != angle.get("method_id"):
            fail("CALL_RECORD_MISMATCH")
            continue
        mode = call.get("mode")
        if mode == "CUSTOM":
            findings[angle_id] = envelope(context, angle_id, angle, status="INSUFFICIENT_EVIDENCE",
                                          reason="EXECUTION_ONLY_NOT_VERIFIABLE", level="EXECUTION_ONLY",
                                          hashes=hashes, output_ids=ids,
                                          warnings=["Recorded by custom code; nothing was recomputed."])
            findings[angle_id]["custom"] = {"note": str(call.get("note") or "")[:1000]}
            continue
        if mode not in ("DECLARATIVE", "FRAME") or len(stored_inputs) != 1:
            fail("INPUT_NOT_RECORDED")
            continue
        stored = stored_inputs[0]
        path = outputs_root / stored["relative_path"]
        try:
            if stored.get("checksum_sha256") != (call.get("input") or {}).get("sha256") \
                    or _sha256_file(path) != stored.get("checksum_sha256"):
                fail("INPUT_CHECKSUM_MISMATCH")
                continue
            frame = pq.read_table(path).to_pandas()
        except (OSError, ValueError):
            fail("INPUT_UNREADABLE")
            continue
        hashes["input_sha256"] = stored.get("checksum_sha256")
        level = "FORMULA_AND_STATISTICS_VERIFIED" if mode == "DECLARATIVE" else "STATISTICS_VERIFIED"
        if mode == "DECLARATIVE":
            declaration = call.get("declaration") or {}
            dataset = next((d for d in (angle.get("contract") or {}).get("datasets") or []
                            if d["data_request_id"] == declaration.get("request")), None)
            delivered = next((d for d in bundle["datasets"] if d["data_request_id"] == declaration.get("request")),
                             None)
            if dataset is None or delivered is None:
                fail("REQUEST_OUTSIDE_CONTRACT")
                continue
            allowed = {w["range_id"] for w in dataset.get("ranges") or []}
            chosen = declaration.get("range_id")
            if chosen is not None and chosen not in allowed:
                fail("RANGE_OUTSIDE_CONTRACT")
                continue
            windows = [(w["start"], w["end"]) for w in delivered.get("ranges") or []
                       if w["range_id"] in allowed and (chosen is None or w["range_id"] == chosen)]
            keys = [c for c in (delivered.get("entity_column"), delivered.get("time_column")) if c]
            columns = [c for c in dataset.get("columns") or [] if c not in keys]
            try:
                rows = _read_request(bundle, delivered["data_request_id"], list(dict.fromkeys(keys + columns)),
                                     path_of)
                rebuilt, _ = I.build(angle["method_id"], declaration, rows,
                                     entity_column=delivered.get("entity_column"),
                                     time_column=delivered["time_column"], columns=columns, windows=windows,
                                     horizon=int(angle["outcome_horizon_periods"]), unit=angle["outcome_unit"])
            except I.InputError as exc:
                fail(exc.code)
                continue
            if not _same(frame, rebuilt):
                fail("INPUT_NOT_REPRODUCED", level)
                continue
            frame = rebuilt
        else:
            problem = _bounds(frame, angle, bundle, path_of)
            if problem:
                fail(problem, level)
                continue
        try:
            result = E.evaluate(angle["method_id"], frame, _approved(angle))
        except E.EngineError as exc:
            fail(exc.code, level)
            continue
        decision = E.decide(result, expected_direction=angle["expected_direction"], validation_level=level,
                            minimum_sample=angle.get("minimum_sample"))
        warnings = []
        if result.get("sample", {}).get("small_groups"):
            warnings.append(f"Groups with fewer than ten observations: {result['sample']['small_groups']}.")
        censored = ((call.get("input_info") or {}).get("censored_outcome_rows") or 0)
        if censored:
            warnings.append(f"{censored} rows had no complete forward outcome in the data and were not counted.")
        findings[angle_id] = envelope(context, angle_id, angle, status=decision["status"], reason=decision["reason"],
                                      level=level, direction=decision["evidence_direction"], result=result,
                                      hashes=hashes, output_ids=ids, warnings=warnings)
        findings[angle_id]["input"] = {"mode": mode, "rows": int(len(frame)),
                                       "declaration": call.get("declaration") if mode == "DECLARATIVE" else None}
    relied = [f.get("validation_level") for f in findings.values()
              if f["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE")]
    return {"findings": findings, "missing": missing, "invalid": sorted(set(invalid)), "unapproved": unapproved,
            "duplicates": duplicates, "calculation_validation": weakest([level for level in relied if level])
            or "NOT_PERFORMED"}


def holdout_start(angle_contract: dict[str, Any]) -> str | None:
    """The first date of the latest range of the angle's contract (its holdout), when it has at least two ranges."""
    starts = sorted({w["start"] for d in angle_contract.get("datasets") or [] for w in d.get("ranges") or []})
    return starts[-1] if len(starts) >= 2 else None


__all__ = ["VERSION", "engines", "envelope", "holdout_start", "inputs", "validate_group", "weakest"]
