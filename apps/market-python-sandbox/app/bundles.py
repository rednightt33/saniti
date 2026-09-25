"""Governed data bundles: the immutable, checksum-protected input of an analysis session.

market-ai-orc's Execution Planner extracts every part of an approved DataNeedSpec through the SQL Governor and then
asks for a bundle: POST /v1/bundles {request_id, need_id, plan}. The plan lists, per data request, the extraction
envelopes and every physical part (partition_id, dataset_id, part_key, window, entity partition). This module

1. checks the need is approved for this request and the plan names exactly its data requests;
2. obtains a Governor grant for every dataset (the internal validator manifest with lineage and executed scope),
   enforces the bundle size limits, and downloads each file with its checksum verified;
3. stores the files read-only under the bundle store on the service volume (root only);
4. runs the Data Quality Profiler (runtime/profiler.py) in a confined process as the validator user;
5. runs delivery coverage (app/coverage.py): lineage, executed scope, catalog version, partition tiling, and
   delivered rows and entities against the SQL manifests;
6. records the bundle with its manifest and checksum. A bundle whose coverage fails is REJECTED, never READY.

The bundle is read-only for everyone after this: no request field can add, remove or replace a file, the sandbox
never queries the database, and nothing is sampled or truncated. The files survive a restart of the service (the
volume) until the bundle expires; sessions copy them into their own workspace.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .coverage import delivery_coverage, part_key, sha256_json
from .data_need import buffer_days
from .datasets import DatasetFailure, DatasetProvider
from .executor import read_child_json
from .records import utc_now

BUNDLE_ID = re.compile(r"^bundle_[0-9a-f]{24}$")
PARTITION_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}_[A-Za-z0-9]{1,12}__[a-z0-9_]{1,60}$")
PLAN_ID = re.compile(r"^plan_[0-9a-f]{24}$")
DATASET_ID = re.compile(r"^ds_[0-9a-f]{24}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHUNK = 1 << 20


class BundleError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 422, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details


def explicit_entities(scope: dict[str, Any], entity_column: str | None) -> list[str] | None:
    """Entities a scope names explicitly (EQ/IN on the entity column at the top level or directly under AND)."""
    if not entity_column:
        return None
    nodes = [scope] if scope.get("type") == "PREDICATE" else (scope.get("children") or []) \
        if scope.get("type") == "AND" else []
    named = [set(n["values"]) for n in nodes if n.get("type") == "PREDICATE" and n.get("column") == entity_column
             and n.get("operator") in ("EQ", "IN")]
    if not named:
        return None
    return sorted(set.intersection(*named))


def _window(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"from", "to"} or not all(
            isinstance(value[k], str) and DATE.fullmatch(value[k]) for k in ("from", "to")):
        raise BundleError("INVALID_PLAN", "A part window must be {from, to} dates.")
    return {"from": value["from"], "to": value["to"]}


def _partition(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"modulus", "remainder"} or not all(
            isinstance(value[k], int) and not isinstance(value[k], bool) for k in value) \
            or not 2 <= value["modulus"] <= 4096 or not 0 <= value["remainder"] < value["modulus"]:
        raise BundleError("INVALID_PLAN", "An entity partition must be {modulus 2..4096, remainder < modulus}.")
    return {"modulus": value["modulus"], "remainder": value["remainder"]}


def normalize_plan(raw: Any, approved: dict[str, Any], max_parts: int) -> dict[str, Any]:
    """The planner's plan in canonical form; structural problems are INVALID_PLAN."""
    if not isinstance(raw, dict) or not isinstance(raw.get("plan_id"), str) or not PLAN_ID.fullmatch(raw["plan_id"]) \
            or not isinstance(raw.get("requests"), list):
        raise BundleError("INVALID_PLAN", "plan must be {plan_id, requests[], decisions[]}.")
    requests, seen_parts, seen_datasets = [], set(), set()
    for item in raw["requests"]:
        if not isinstance(item, dict) or not isinstance(item.get("data_request_id"), str) \
                or not isinstance(item.get("parts"), list):
            raise BundleError("INVALID_PLAN", "Each plan request needs data_request_id and parts[].")
        parts = []
        for part in item["parts"]:
            if not isinstance(part, dict) or not isinstance(part.get("partition_id"), str) \
                    or not PARTITION_ID.fullmatch(part["partition_id"]) \
                    or not part["partition_id"].startswith(item["data_request_id"] + "__") \
                    or not isinstance(part.get("dataset_id"), str) or not DATASET_ID.fullmatch(part["dataset_id"]) \
                    or not isinstance(part.get("part_key"), str):
                raise BundleError("INVALID_PLAN", "Each part needs partition_id (<data_request_id>__...), dataset_id "
                                                  "and part_key.")
            if part["partition_id"] in seen_parts or part["dataset_id"] in seen_datasets:
                raise BundleError("INVALID_PLAN", f"{part['partition_id']}: partition and dataset ids must be unique.")
            seen_parts.add(part["partition_id"])
            seen_datasets.add(part["dataset_id"])
            parts.append({"partition_id": part["partition_id"], "dataset_id": part["dataset_id"],
                          "part_key": part["part_key"], "window": _window(part.get("window")),
                          "entity_partition": _partition(part.get("entity_partition"))})
        requests.append({"data_request_id": item["data_request_id"],
                         "envelopes": [e for e in item.get("envelopes") or [] if isinstance(e, dict)][:32],
                         "parts": sorted(parts, key=lambda p: p["partition_id"])})
    if len(seen_parts) > max_parts:
        raise BundleError("BUNDLE_TOO_LARGE", f"The plan has {len(seen_parts)} parts; a bundle holds at most "
                                              f"{max_parts}.", limit=max_parts)
    decisions = raw.get("decisions") if isinstance(raw.get("decisions"), list) else []
    return {"plan_id": raw["plan_id"], "requests": sorted(requests, key=lambda r: r["data_request_id"]),
            "decisions": json.loads(json.dumps(decisions[:64], default=str))}


class BundleBuilder:
    def __init__(self, analysis: Any, store: Any) -> None:
        self.analysis = analysis
        self.settings = analysis.settings
        self.store = store
        self.root = Path(self.settings.bundle_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    # ------------------------------------------------------------------ build

    def build(self, request_id: str, need: dict[str, Any], raw_plan: Any) -> dict[str, Any]:
        s = self.settings
        approved = need
        plan = normalize_plan(raw_plan, approved, s.bundle_max_parts)
        plan_sha = sha256_json(plan)
        for earlier in self.store.bundles_for(request_id):
            if earlier["need_id"] == need["need_id"] and earlier["manifest"].get("plan_sha256") == plan_sha \
                    and earlier["status"] == "READY" and (self.root / earlier["bundle_id"]).is_dir():
                return {**earlier["manifest"], "replayed": True}
        bundle_id = f"bundle_{secrets.token_hex(12)}"
        grants: dict[str, Any] = {}
        try:
            for request in plan["requests"]:
                for part in request["parts"]:
                    grants[part["partition_id"]] = self.analysis.datasets.grant(
                        part["dataset_id"], request_id=request_id, analysis_id=bundle_id)
        except DatasetFailure as failure:
            raise BundleError(failure.code, failure.message) from failure
        rows = sum(g.row_count for g in grants.values())
        size = sum(g.byte_count for g in grants.values())
        if rows > s.bundle_max_rows or size > s.bundle_max_bytes:
            raise BundleError("BUNDLE_TOO_LARGE", f"The extracted data holds {rows} rows / {size} bytes; a bundle "
                                                  f"holds at most {s.bundle_max_rows} rows / {s.bundle_max_bytes} "
                                                  "bytes. Narrow the DataNeedSpec (scope, ranges or columns).",
                              rows=rows, bytes=size, limit_rows=s.bundle_max_rows, limit_bytes=s.bundle_max_bytes)
        used = sum(b["manifest"].get("byte_count") or 0 for b in self.store.bundles_for(request_id)
                   if b["status"] == "READY")
        if used + size > s.max_input_bytes_per_request:
            raise BundleError("REQUEST_BUDGET_EXCEEDED", "This request has used its input-data budget.",
                              http_status=429)
        directory = self.root / bundle_id
        directory.mkdir(mode=0o700)
        try:
            files = self._store_files(directory, plan, grants)
            quality = self._profile(bundle_id, approved, plan, files)
            delivered = {pid: {"validator": g.manifest.get("validator_manifest") or {}, "row_count": g.row_count,
                               "entities_present": (g.manifest.get("validator_manifest") or {}).get(
                                   "entities_present")} for pid, g in grants.items()}
            coverage = delivery_coverage(approved, need, plan, delivered, quality)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        manifest = self._manifest(bundle_id, request_id, need, approved, plan, plan_sha, grants, files, quality,
                                  coverage, size, rows)
        status = manifest["status"]
        if status != "READY":
            shutil.rmtree(directory, ignore_errors=True)
        self.store.insert_bundle({"bundle_id": bundle_id, "request_id": request_id, "need_id": need["need_id"],
                                  "request_group_id": approved["request_group_id"], "revision": approved["revision"],
                                  "status": status, "checksum_sha256": manifest["checksum_sha256"],
                                  "manifest": manifest, "created_at": manifest["created_at"],
                                  "expires_at": manifest["expires_at"]})
        self.evict()
        return manifest

    def _store_files(self, directory: Path, plan: dict[str, Any], grants: dict[str, Any]) -> dict[str, dict[str, Any]]:
        files: dict[str, dict[str, Any]] = {}
        for request in plan["requests"]:
            folder = directory / request["data_request_id"]
            folder.mkdir(mode=0o700)
            for part in request["parts"]:
                grant = grants[part["partition_id"]]
                try:
                    cached = self.analysis.datasets.fetch(grant)
                except DatasetFailure as failure:
                    raise BundleError(failure.code, failure.message) from failure
                target = folder / f"{part['partition_id']}.parquet"
                digest = hashlib.sha256()
                with open(cached, "rb") as source, open(target, "wb") as sink:
                    while chunk := source.read(CHUNK):
                        digest.update(chunk)
                        sink.write(chunk)
                if digest.hexdigest() != grant.checksum:
                    raise BundleError("DATASET_INTEGRITY_ERROR", f"{part['dataset_id']}: the stored copy does not "
                                                                 "match its checksum.")
                os.chmod(target, 0o444)
                files[part["partition_id"]] = {"path": target, "cached": cached, "checksum_sha256": grant.checksum,
                                               "byte_count": grant.byte_count, "rows": grant.row_count,
                                               "relative": f"{request['data_request_id']}/{target.name}"}
        return files

    # ------------------------------------------------------------------ profiling

    def _profile(self, bundle_id: str, approved: dict[str, Any], plan: dict[str, Any],
                 files: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Run the Data Quality Profiler as the validator user over links to the verified cache copies."""
        s = self.settings
        executor = self.analysis.executor
        drop = executor.drop_privileges
        jobs = Path(s.jobs_dir)
        jobs.mkdir(parents=True, exist_ok=True)
        os.chmod(jobs, 0o711)
        job = jobs / f"{bundle_id}-profile"
        job.mkdir(mode=0o755)
        try:
            (job / "input").mkdir(mode=0o755)
            owned = [job / "result", job / "home", job / "home" / "tmp"]
            for path in owned:
                path.mkdir(mode=0o700)
                if drop:
                    os.chown(path, s.validator_uid, s.validator_uid)
            requests = []
            for request in plan["requests"]:
                entry = approved["requests"].get(request["data_request_id"])
                if entry is None:
                    continue
                parts = []
                for part in request["parts"]:
                    link = job / "input" / f"{part['partition_id']}.parquet"
                    DatasetProvider.link(files[part["partition_id"]]["cached"], link)
                    parts.append({"partition_id": part["partition_id"], "path": str(link), "window": part["window"],
                                  "entity_partition": part["entity_partition"]})
                reference = date.fromisoformat(approved["reference_date"])
                ranges = [{**w, "future_capped": bool(entry.get("future_buffer")) and date.fromisoformat(w["end"])
                           + timedelta(days=buffer_days(entry.get("future_buffer"))) > reference}
                          for w in entry.get("windows") or []]
                requests.append({
                    "data_request_id": entry["data_request_id"], "logical_name": entry["logical_name"],
                    "files": parts, "columns": entry["extract_columns"], "key_columns": entry.get("key_columns") or [],
                    "entity_column": entry.get("entity_column"), "time_column": entry.get("time_column"),
                    "source_frequency": entry.get("source_frequency"), "ranges": ranges,
                    "history_buffer": entry.get("history_buffer"), "future_buffer": entry.get("future_buffer"),
                    "order_by": self._order(entry), "explicit_entities": explicit_entities(
                        entry["scope"], entry.get("entity_column"))})
            request_file = job / "profile_request.json"
            request_file.write_text(json.dumps({
                "limits": s.validator_limits(), "cpus": sorted(os.sched_getaffinity(0))[:s.cpus_per_job],
                "require_seccomp": True, "reference_date": approved["reference_date"], "requests": requests,
                "duckdb": {"memory_limit_mb": max(128, s.validator_memory_mb // 2), "threads": s.threads_per_job,
                           "temp_directory": str(job / "home" / "tmp")}}, default=str), encoding="utf-8")
            os.chmod(request_file, 0o444)
            home = job / "home"
            outcome = executor.run(job, s.validator_uid, script="profiler.py", cwd=home, home=home, tmp=home / "tmp",
                                   quotas={home: 512 << 20, job / "result": 16 << 20},
                                   deadline_seconds=s.validator_runtime_seconds, memory_mb=s.validator_memory_mb,
                                   cpu_seconds=s.validator_limits()["cpu_seconds"], error_dir=job / "result",
                                   log_name="profiler")
            result = None
            if outcome.kind == "OK":
                try:
                    result = read_child_json(job / "result" / "quality.json", s.validator_uid if drop else None,
                                             16 << 20)
                except (OSError, ValueError):
                    result = None
            if not isinstance(result, dict) or result.get("profiler_error") or "requests" not in result:
                detail = (result or {}).get("profiler_error") if isinstance(result, dict) else outcome.kind
                raise BundleError("DATA_QUALITY_PROFILING_FAILED", f"The Data Quality Profiler did not complete "
                                                                   f"({detail}).", http_status=503)
            return {r["data_request_id"]: r for r in result["requests"]}
        finally:
            shutil.rmtree(job, ignore_errors=True)

    @staticmethod
    def _order(entry: dict[str, Any]) -> list[dict[str, str]]:
        """The order the Governor delivers: the requested ordering, then the key columns ascending."""
        order = [dict(item) for item in entry.get("ordering") or [] if item.get("column") in entry["extract_columns"]]
        present = {o["column"] for o in order}
        for column in [c for c in (entry.get("entity_column"), entry.get("time_column")) if c] + list(
                entry.get("primary_key_columns") or []):
            if column in entry["extract_columns"] and column not in present:
                order.append({"column": column, "direction": "ASC"})
                present.add(column)
        return order

    # ------------------------------------------------------------------ manifest

    def _manifest(self, bundle_id: str, request_id: str, need: dict[str, Any], approved: dict[str, Any],
                  plan: dict[str, Any], plan_sha: str, grants: dict[str, Any], files: dict[str, dict[str, Any]],
                  quality: dict[str, dict[str, Any]], coverage: dict[str, Any], size: int, rows: int) -> dict[str, Any]:
        created = datetime.now(timezone.utc).replace(microsecond=0)
        expires = created + timedelta(hours=self.settings.bundle_retention_hours)
        datasets = []
        planned = {r["data_request_id"]: r for r in plan["requests"]}
        for rid in sorted(approved["requests"]):
            entry = approved["requests"][rid]
            parts = (planned.get(rid) or {}).get("parts") or []
            profile = quality.get(rid) or {}
            quality_id = f"quality_{sha256_json(profile)[:24]}"
            columns = []
            if parts:
                columns = [{"name": c.get("name"), "type": c.get("type"), "source_type": c.get("source_type"),
                            "unit": c.get("unit")} for c in grants[parts[0]["partition_id"]].manifest.get("columns")
                           or []]
            datasets.append({
                "data_request_id": rid, "logical_name": entry["logical_name"], "source_table": entry["source_table"],
                "entity_column": entry.get("entity_column"), "time_column": entry.get("time_column"),
                "key_columns": entry.get("key_columns") or [], "columns": columns,
                "dataset_ids": [p["dataset_id"] for p in parts],
                "partitions": [{"partition_id": p["partition_id"], "dataset_id": p["dataset_id"],
                                "window": p["window"], "entity_partition": p["entity_partition"],
                                "rows": files[p["partition_id"]]["rows"],
                                "checksum_sha256": files[p["partition_id"]]["checksum_sha256"],
                                "file": files[p["partition_id"]]["relative"]} for p in parts],
                "rows": sum(files[p["partition_id"]]["rows"] for p in parts),
                "ranges": entry.get("windows") or [], "source_frequency": entry.get("source_frequency"),
                "analysis_frequency": entry.get("analysis_frequency"), "resample": entry.get("resample"),
                "resample_rules": entry.get("resample_rules") or {}, "scope_sha256": entry["scope_sha256"],
                "restricted_by": [r["relationship_id"] for r in entry.get("restrictions") or []],
                "quality_manifest_id": quality_id, "quality": profile})
        warnings = [w for w in (need.get("warnings") or [])]
        body = {
            "input_bundle_id": bundle_id, "request_id": request_id, "need_id": need["need_id"],
            "request_group_id": approved["request_group_id"], "revision": approved["revision"],
            "mode": approved.get("mode"), "reference_date": approved["reference_date"],
            "spec_sha256": approved["spec_sha256"], "catalog_sha256": approved.get("catalog_sha256"),
            "plan_id": plan["plan_id"], "plan_sha256": plan_sha, "plan_decisions": plan["decisions"],
            "status": "READY" if coverage["coverage_status"] == "PASS" else "REJECTED",
            "datasets": datasets, "relationships": approved.get("relationships") or [],
            "relationship_warnings": [{"relationship_id": w.get("relationship_id"), "code": w.get("code"),
                                       "message": w.get("message")} for w in warnings],
            "coverage": coverage, "byte_count": size, "row_count": rows, "sampling": False, "truncation": False,
            "immutable": True, "created_at": created.isoformat(), "expires_at": expires.isoformat()}
        body["checksum_sha256"] = sha256_json(body)
        return body

    # ------------------------------------------------------------------ lifecycle

    def get(self, bundle_id: str) -> dict[str, Any] | None:
        record = self.store.get_bundle(bundle_id)
        return record

    def path_of(self, bundle_id: str, relative: str) -> Path:
        return self.root / bundle_id / relative

    def evict(self, now: datetime | None = None) -> int:
        """Delete expired bundles, then the oldest READY ones while the store is above its byte budget."""
        now = now or datetime.now(timezone.utc)
        removed = 0
        ready = [b for b in self.store.all_bundles() if b["status"] == "READY"]
        for bundle in ready:
            try:
                expired = datetime.fromisoformat(bundle["expires_at"]) <= now
            except (TypeError, ValueError):
                expired = True
            if expired:
                shutil.rmtree(self.root / bundle["bundle_id"], ignore_errors=True)
                self.store.set_bundle_status(bundle["bundle_id"], "EXPIRED")
                removed += 1
        live = sorted((b for b in self.store.all_bundles() if b["status"] == "READY"), key=lambda b: b["created_at"])
        total = sum(b["manifest"].get("byte_count") or 0 for b in live)
        while live and total > self.settings.bundle_store_bytes:
            oldest = live.pop(0)
            shutil.rmtree(self.root / oldest["bundle_id"], ignore_errors=True)
            self.store.set_bundle_status(oldest["bundle_id"], "EVICTED")
            total -= oldest["manifest"].get("byte_count") or 0
            removed += 1
        return removed


def model_view(manifest: dict[str, Any]) -> dict[str, Any]:
    """The bundle as market-ai-orc returns it to the model: no file paths, no dataset internals."""
    datasets = []
    for d in manifest.get("datasets") or []:
        q = d.get("quality") or {}
        datasets.append({
            "data_request_id": d["data_request_id"], "logical_name": d["logical_name"],
            "source_table": d["source_table"], "rows": d["rows"], "entities": q.get("entities"),
            "min_date": q.get("min_date"), "max_date": q.get("max_date"),
            "columns": [c["name"] for c in d.get("columns") or []], "partitions": len(d.get("partitions") or []),
            "ranges": [{k: r.get(k) for k in ("range_id", "requested_start", "requested_end", "actual_start",
                                               "actual_end", "rows", "entities", "status")}
                       for r in q.get("requested_ranges") or []],
            "quality_manifest_id": d["quality_manifest_id"], "quality_flags": q.get("quality_flags") or [],
            "source_frequency": d.get("source_frequency"), "analysis_frequency": d.get("analysis_frequency"),
            "resample": d.get("resample")})
    coverage = manifest.get("coverage") or {}
    return {"status": manifest["status"], "input_bundle_id": manifest["input_bundle_id"],
            "need_id": manifest["need_id"], "request_group_id": manifest["request_group_id"],
            "revision": manifest["revision"], "datasets": datasets,
            "relationship_warnings": manifest.get("relationship_warnings") or [],
            "coverage_status": coverage.get("coverage_status"),
            "coverage_issues": [i for r in coverage.get("requests") or [] for i in r.get("issues") or []][:10]
            + (coverage.get("issues") or [])[:5],
            "sampling": False, "truncation": False, "expires_at": manifest["expires_at"],
            "replayed": manifest.get("replayed", False)}
