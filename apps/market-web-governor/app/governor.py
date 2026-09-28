from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import Settings
from .models import (
    CONTRACT_VERSION,
    CreateWebNeedRequest,
    EvidenceCriterion,
    EvidenceStandard,
    FastSearchRequest,
    FetchRequest,
    SourcePolicy,
    SourceTier,
    WebBudget,
    WebNeedSpec,
)
from .provider import OpenRouterProvider, ProviderError, ProviderResult
from .store import IdempotencyConflict, SqliteStore


TERMINAL = {"EVIDENCE_READY", "PARTIAL", "FAILED", "BLOCKED"}
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class GovernorValidationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class WebGovernor:
    def __init__(self, settings: Settings, store: SqliteStore, provider: OpenRouterProvider):
        self.settings = settings
        self.store = store
        self.provider = provider

    def capabilities(self) -> dict[str, Any]:
        return {
            "contract_versions": [CONTRACT_VERSION],
            "operations": ["PLAN_WEB_NEED", "EXECUTE_WEB_NEED", "SEARCH", "FETCH_URL"],
            "provider_adapters": [{"name": self.provider.name, "version": self.provider.adapter_version}],
            "features": {
                "criteria_coverage": True,
                "support_and_contradiction_search": True,
                "domain_policy": True,
                "primary_source_policy": True,
                "citation_ids": True,
                "durable_evidence": True,
                "idempotency": True,
                "exact_url_fetch": True,
            },
            "limits": {
                "max_criteria": self.settings.max_criteria,
                "max_searches": self.settings.max_searches,
                "max_results_per_search": self.settings.max_results_per_search,
                "max_evidence_items": self.settings.max_evidence_items,
                "max_output_characters": self.settings.max_output_characters,
                "max_excerpt_characters": self.settings.max_excerpt_characters,
            },
        }

    def create_need(self, request: CreateWebNeedRequest) -> dict[str, Any]:
        self._validate_limits(request.web_need)
        body = request.model_dump(mode="json")
        fingerprint = _sha256_json(body)
        now = _now()
        web_need_id = f"wn_{uuid.uuid4().hex}"
        plan = self._plan(request.web_need)
        row = {
            "web_need_id": web_need_id,
            "request_id": request.request_id,
            "request_fingerprint": fingerprint,
            "conversation_id": request.conversation_id,
            "status": "APPROVED",
            "spec": request.web_need.model_dump(mode="json"),
            "plan": plan,
            "created_at": now,
            "updated_at": now,
        }
        stored, created = self.store.create_need(row)
        if not created and stored.get("response"):
            return stored["response"]
        return self._plan_response(stored)

    def execute_need(self, web_need_id: str, request_id: str) -> dict[str, Any]:
        existing = self.store.get_need(web_need_id)
        if not existing:
            raise KeyError(web_need_id)
        if existing["request_id"] != request_id:
            raise GovernorValidationError("REQUEST_ID_MISMATCH", "request_id does not own this web need")
        if existing["status"] in TERMINAL and existing.get("response"):
            return existing["response"]
        need = self.store.begin_execution(web_need_id)
        if need["status"] in TERMINAL and need.get("response"):
            return need["response"]
        spec = WebNeedSpec.model_validate(need["spec"])
        return self._execute(web_need_id, need["request_id"], spec, need["plan"])

    def get_need(self, web_need_id: str) -> dict[str, Any] | None:
        need = self.store.get_need(web_need_id)
        if not need:
            return None
        if need.get("response"):
            return need["response"]
        return self._plan_response(need)

    def fast_search(self, request: FastSearchRequest) -> dict[str, Any]:
        criterion = EvidenceCriterion(
            criterion_id="fast_search",
            question=request.query,
            required=True,
            direction="BOTH",
            minimum_sources=max(1, min(request.source_policy.minimum_independent_sources, 5)),
        )
        budget = request.budget.model_copy(update={"max_searches": max(1, request.budget.max_searches)})
        spec = WebNeedSpec(
            objective=request.query,
            time_window=request.time_window,
            evidence_standard=EvidenceStandard.CORROBORATED,
            criteria=[criterion],
            source_policy=request.source_policy,
            budget=budget,
            locale=request.locale,
            timezone=request.timezone,
        )
        create = CreateWebNeedRequest(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            web_need=spec,
        )
        plan = self.create_need(create)
        if plan.get("status") in TERMINAL:
            return plan
        return self.execute_need(plan["web_need_id"], request.request_id)

    def fetch(self, request: FetchRequest) -> dict[str, Any]:
        criterion = EvidenceCriterion(
            criterion_id="fetch", question=request.objective, required=True, direction="SUPPORT", minimum_sources=1
        )
        spec = WebNeedSpec(
            objective=request.objective,
            evidence_standard=EvidenceStandard.SINGLE_SOURCE,
            criteria=[criterion],
            source_policy=SourcePolicy(allowed_domains=[urlsplit(request.url).hostname or "invalid.example"]),
            budget=WebBudget(max_searches=1, max_results_per_search=1, max_evidence_items=1),
            locale=request.locale,
        )
        body = {
            "contract_version": request.contract_version,
            "request_id": request.request_id,
            "operation": "FETCH_URL",
            "url": request.url,
            "objective": request.objective,
            "locale": request.locale,
        }
        fingerprint = _sha256_json(body)
        now = _now()
        web_need_id = f"wn_{uuid.uuid4().hex}"
        plan = {
            "operation": "FETCH_URL",
            "tasks": [{"task_id": "task_fetch", "criterion_id": "fetch", "url": request.url}],
            "stop_conditions": {"all_required_criteria_covered": True, "stop_on_primary_source": False},
        }
        row = {
            "web_need_id": web_need_id,
            "request_id": request.request_id,
            "request_fingerprint": fingerprint,
            "conversation_id": None,
            "status": "APPROVED",
            "spec": spec.model_dump(mode="json"),
            "plan": plan,
            "created_at": now,
            "updated_at": now,
        }
        stored, created = self.store.create_need(row)
        if not created and stored.get("response"):
            return stored["response"]
        if not created:
            web_need_id = stored["web_need_id"]
        self.store.begin_execution(web_need_id)
        call_id = f"pc_{uuid.uuid4().hex}"
        try:
            result = self.provider.fetch_url(request.url, request.objective, request.locale, call_id)
        except ProviderError as exc:
            return self._complete_provider_failure(web_need_id, request.request_id, spec, "fetch", call_id, exc)
        return self._complete_single_result(
            web_need_id, request.request_id, spec, criterion, result, expected_url=request.url
        )

    def _execute(
        self, web_need_id: str, request_id: str, spec: WebNeedSpec, plan: dict[str, Any]
    ) -> dict[str, Any]:
        provider_calls: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        links: list[tuple[str, str]] = []
        coverage: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        applied_policies: list[dict[str, Any]] = []
        evidence_by_key: dict[tuple[str, str], dict[str, Any]] = {}

        for criterion in spec.criteria:
            call_id = f"pc_{uuid.uuid4().hex}"
            try:
                result = self.provider.research_criterion(web_need_id, spec, criterion, call_id)
            except ProviderError as exc:
                now = _now()
                provider_calls.append(self._failed_call(call_id, criterion.criterion_id, "SEARCH", exc, now))
                warnings.append({"code": exc.code, "message": f"{criterion.criterion_id}: {exc}"})
                coverage.append({
                    "criterion_id": criterion.criterion_id,
                    "required": criterion.required,
                    "status": "BLOCKED",
                    "assessment": "INSUFFICIENT",
                    "summary": "Provider did not return usable evidence.",
                    "evidence_ids": [],
                    "citation_ids": [],
                    "gaps": [exc.code],
                })
                continue

            provider_calls.append(result.provider_call)
            applied_policies.append(result.applied_policy)
            criterion_evidence: list[dict[str, Any]] = []
            for annotation in result.annotations:
                if len(evidence) >= min(spec.budget.max_evidence_items, self.settings.max_evidence_items):
                    warnings.append({"code": "EVIDENCE_BUDGET_REACHED", "message": "Evidence item budget reached."})
                    break
                item = self._evidence_from_annotation(web_need_id, result.provider_call, annotation, spec.source_policy)
                if not item:
                    continue
                key = (item["canonical_url"], item["content_sha256"])
                existing = evidence_by_key.get(key)
                if existing:
                    item = existing
                else:
                    evidence_by_key[key] = item
                    evidence.append(item)
                if item not in criterion_evidence:
                    criterion_evidence.append(item)
                    links.append((criterion.criterion_id, item["evidence_id"]))
            coverage.append(self._coverage(criterion, result, criterion_evidence, spec))

        required = [entry for entry in coverage if entry["required"]]
        covered_states = {"SATISFIED", "CONTRADICTED"}
        all_required_covered = bool(required) and all(entry["status"] in covered_states for entry in required)
        if all_required_covered:
            status = "EVIDENCE_READY"
            next_action = "SYNTHESIZE"
        elif coverage and all(entry["status"] == "BLOCKED" for entry in coverage):
            status = "BLOCKED"
            next_action = "RETRY_PROVIDER"
        else:
            status = "PARTIAL"
            next_action = "REFINE_WEB_NEED"

        response = self._response(
            web_need_id, request_id, status, spec, plan, coverage, evidence, warnings, next_action, applied_policies,
            provider_calls,
        )
        self._fit_response(response, evidence, spec.budget.max_output_characters)
        self.store.complete_execution(web_need_id, status, response, provider_calls, evidence, links, _now())
        return response

    def _complete_single_result(
        self,
        web_need_id: str,
        request_id: str,
        spec: WebNeedSpec,
        criterion: EvidenceCriterion,
        result: ProviderResult,
        expected_url: str | None = None,
    ) -> dict[str, Any]:
        evidence = []
        links = []
        for annotation in result.annotations[:1]:
            if expected_url and _canonical_url(annotation["url"]) != _canonical_url(expected_url):
                continue
            item = self._evidence_from_annotation(web_need_id, result.provider_call, annotation, spec.source_policy)
            if item:
                evidence.append(item)
                links.append((criterion.criterion_id, item["evidence_id"]))
        coverage = [self._coverage(criterion, result, evidence, spec)]
        status = "EVIDENCE_READY" if coverage[0]["status"] in {"SATISFIED", "CONTRADICTED"} else "PARTIAL"
        response = self._response(
            web_need_id, request_id, status, spec, {"operation": "FETCH_URL"}, coverage, evidence, [],
            "SYNTHESIZE" if status == "EVIDENCE_READY" else "REVIEW_FETCH", [result.applied_policy],
            [result.provider_call],
        )
        self._fit_response(response, evidence, spec.budget.max_output_characters)
        self.store.complete_execution(
            web_need_id, status, response, [result.provider_call], evidence, links, _now()
        )
        return response

    def _complete_provider_failure(
        self,
        web_need_id: str,
        request_id: str,
        spec: WebNeedSpec,
        criterion_id: str,
        call_id: str,
        error: ProviderError,
    ) -> dict[str, Any]:
        now = _now()
        call = self._failed_call(call_id, criterion_id, "FETCH", error, now)
        response = self._response(
            web_need_id,
            request_id,
            "BLOCKED",
            spec,
            {"operation": "FETCH_URL"},
            [{
                "criterion_id": criterion_id,
                "required": True,
                "status": "BLOCKED",
                "assessment": "INSUFFICIENT",
                "summary": "Provider did not return usable evidence.",
                "evidence_ids": [],
                "citation_ids": [],
                "gaps": [error.code],
            }],
            [],
            [{"code": error.code, "message": str(error)}],
            "RETRY_PROVIDER",
            [],
            [call],
        )
        self.store.complete_execution(
            web_need_id, "BLOCKED", response, [call], [], [], now, error_code=error.code
        )
        return response

    def _validate_limits(self, spec: WebNeedSpec) -> None:
        if len(spec.criteria) > self.settings.max_criteria:
            raise GovernorValidationError("TOO_MANY_CRITERIA", "criteria exceed the service limit")
        if spec.budget.max_searches > self.settings.max_searches:
            raise GovernorValidationError("SEARCH_BUDGET_TOO_HIGH", "max_searches exceeds the service limit")
        if spec.budget.max_results_per_search > self.settings.max_results_per_search:
            raise GovernorValidationError(
                "RESULT_BUDGET_TOO_HIGH", "max_results_per_search exceeds the service limit"
            )
        if spec.budget.max_evidence_items > self.settings.max_evidence_items:
            raise GovernorValidationError("EVIDENCE_BUDGET_TOO_HIGH", "max_evidence_items exceeds the service limit")
        if spec.budget.max_output_characters > self.settings.max_output_characters:
            raise GovernorValidationError("OUTPUT_BUDGET_TOO_HIGH", "max_output_characters exceeds the service limit")

    @staticmethod
    def _plan(spec: WebNeedSpec) -> dict[str, Any]:
        tasks = []
        for index, criterion in enumerate(spec.criteria, start=1):
            tasks.append({
                "task_id": f"task_{index}",
                "criterion_id": criterion.criterion_id,
                "required": criterion.required,
                "search_intent": criterion.question,
                "direction": criterion.direction,
                "minimum_sources": criterion.minimum_sources,
            })
        return {
            "operation": "WEB_RESEARCH",
            "tasks": tasks,
            "stop_conditions": spec.stop_conditions.model_dump(mode="json"),
        }

    @staticmethod
    def _plan_response(need: dict[str, Any]) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "web_need_id": need["web_need_id"],
            "request_id": need["request_id"],
            "status": need["status"],
            "plan": need["plan"],
            "created_at": need["created_at"],
        }

    def _evidence_from_annotation(
        self,
        web_need_id: str,
        provider_call: dict[str, Any],
        annotation: dict[str, Any],
        policy: SourcePolicy,
    ) -> dict[str, Any] | None:
        canonical_url = _canonical_url(annotation["url"])
        parsed = urlsplit(canonical_url)
        domain = (parsed.hostname or "").lower()
        if not domain or not _domain_allowed(domain, policy):
            return None
        excerpt = annotation.get("content")
        if excerpt:
            excerpt = _sanitize_excerpt(excerpt, self.settings.max_excerpt_characters)
        content_hash = hashlib.sha256(
            (canonical_url + "\n" + (excerpt or "")).encode("utf-8", errors="replace")
        ).hexdigest()
        evidence_id = f"ev_{uuid.uuid4().hex}"
        citation_id = f"cit_{hashlib.sha256((web_need_id + canonical_url + content_hash).encode()).hexdigest()[:24]}"
        suffix = PurePosixPath(parsed.path).suffix.lower()
        content_type = "PDF" if suffix == ".pdf" else "WEB_PAGE"
        return {
            "evidence_id": evidence_id,
            "citation_id": citation_id,
            "provider_call_id": provider_call["provider_call_id"],
            "title": (annotation.get("title") or domain)[:500],
            "url": annotation["url"],
            "canonical_url": canonical_url,
            "domain": domain,
            "published_at": annotation.get("published_at"),
            "retrieved_at": provider_call["completed_at"],
            "source_tier": _source_tier(domain, policy),
            "content_type": content_type,
            "excerpt": excerpt,
            "excerpt_kind": "SOURCE_EXCERPT" if excerpt else "NOT_PROVIDED",
            "content_sha256": content_hash,
        }

    @staticmethod
    def _coverage(
        criterion: EvidenceCriterion,
        result: ProviderResult,
        evidence: list[dict[str, Any]],
        spec: WebNeedSpec,
    ) -> dict[str, Any]:
        unique_domains = {item["domain"] for item in evidence}
        primary_count = sum(item["source_tier"] == "PRIMARY" for item in evidence)
        required_sources = max(criterion.minimum_sources, spec.source_policy.minimum_independent_sources)
        if spec.evidence_standard in {EvidenceStandard.MULTI_SOURCE, EvidenceStandard.CORROBORATED}:
            required_sources = max(required_sources, 2)
        required_primary = spec.source_policy.minimum_primary_sources
        if spec.evidence_standard == EvidenceStandard.PRIMARY_REQUIRED:
            required_primary = max(1, required_primary)
        gaps = []
        if len(unique_domains) < required_sources:
            gaps.append(f"NEED_{required_sources}_INDEPENDENT_SOURCES")
        if primary_count < required_primary:
            gaps.append(f"NEED_{required_primary}_PRIMARY_SOURCES")
        if result.assessment == "NOT_FOUND" or not evidence:
            status = "NOT_FOUND"
        elif result.assessment == "CONTRADICTED" and not gaps:
            status = "CONTRADICTED"
        elif result.assessment == "SUPPORTED" and not gaps:
            status = "SATISFIED"
        else:
            status = "PARTIAL"
        return {
            "criterion_id": criterion.criterion_id,
            "required": criterion.required,
            "status": status,
            "assessment": result.assessment,
            "summary": result.summary,
            "evidence_ids": [item["evidence_id"] for item in evidence],
            "citation_ids": [item["citation_id"] for item in evidence],
            "gaps": gaps,
        }

    def _response(
        self,
        web_need_id: str,
        request_id: str,
        status: str,
        spec: WebNeedSpec,
        plan: dict[str, Any],
        coverage: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        warnings: list[dict[str, str]],
        next_action: str,
        applied_policies: list[dict[str, Any]],
        provider_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        unapplied = []
        if any(criterion.document_types for criterion in spec.criteria):
            unapplied.append({
                "constraint": "document_types",
                "application": "BEST_EFFORT",
                "reason": "The provider searches by intent; the governor checks returned metadata when available.",
            })
        if any(criterion.preferred_source_tiers for criterion in spec.criteria):
            unapplied.append({
                "constraint": "preferred_source_tiers",
                "application": "BEST_EFFORT",
                "reason": "Preference is sent in retrieval intent and verified after retrieval when domains identify a tier.",
            })
        return {
            "contract_version": CONTRACT_VERSION,
            "web_run_id": f"wr_{web_need_id[3:]}",
            "web_need_id": web_need_id,
            "request_id": request_id,
            "status": status,
            "decision": "ALLOW" if status in {"EVIDENCE_READY", "PARTIAL"} else "BLOCK",
            "plan": plan,
            "requested_policy": spec.source_policy.model_dump(mode="json"),
            "applied_policy": applied_policies,
            "unapplied_constraints": unapplied,
            "coverage": coverage,
            "evidence": evidence,
            "warnings": warnings,
            "next_action": next_action,
            "execution": {
                "provider": self.provider.name,
                "adapter_version": self.provider.adapter_version,
                "provider_call_count": len(provider_calls),
                "usage": _sum_usage(provider_calls),
                "completed_at": _now(),
            },
        }

    @staticmethod
    def _fit_response(response: dict[str, Any], evidence: list[dict[str, Any]], requested_limit: int) -> None:
        limit = requested_limit
        if len(json.dumps(response, ensure_ascii=False)) <= limit:
            return
        for max_chars in (800, 300, 0):
            for item in evidence:
                excerpt = item.get("excerpt")
                if excerpt:
                    item["excerpt"] = excerpt[:max_chars] if max_chars else None
                    item["excerpt_kind"] = "SOURCE_EXCERPT" if max_chars else "NOT_INCLUDED_IN_RESPONSE"
            if len(json.dumps(response, ensure_ascii=False)) <= limit:
                response["warnings"].append({
                    "code": "RESPONSE_COMPACTED", "message": "Evidence excerpts were shortened to fit the response budget."
                })
                return

    def _failed_call(
        self, call_id: str, criterion_id: str, operation: str, error: ProviderError, now: str
    ) -> dict[str, Any]:
        return {
            "provider_call_id": call_id,
            "criterion_id": criterion_id,
            "operation": operation,
            "provider": self.provider.name,
            "adapter_version": self.provider.adapter_version,
            "model": self.settings.openrouter_model,
            "provider_response_id": None,
            "status": "FAILED",
            "usage": {},
            "error_code": error.code,
            "response_sha256": None,
            "started_at": now,
            "completed_at": now,
        }


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower = key.lower()
        if lower in TRACKING_QUERY_KEYS or lower.startswith(TRACKING_QUERY_PREFIXES):
            continue
        query.append((key, value))
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), ""))


def _domain_matches(domain: str, rule: str) -> bool:
    rule = rule.lower()
    if rule.startswith("*."):
        suffix = rule[2:]
        return domain == suffix or domain.endswith("." + suffix)
    return domain == rule or domain.endswith("." + rule)


def _domain_allowed(domain: str, policy: SourcePolicy) -> bool:
    if policy.allowed_domains and not any(_domain_matches(domain, rule) for rule in policy.allowed_domains):
        return False
    if any(_domain_matches(domain, rule) for rule in policy.excluded_domains):
        return False
    return True


def _source_tier(domain: str, policy: SourcePolicy) -> str:
    built_in_primary = ("idx.co.id", "ojk.go.id", "bi.go.id", "bps.go.id", "sec.gov")
    if domain.endswith(".go.id") or domain.endswith(".gov") or any(
        _domain_matches(domain, rule) for rule in (*built_in_primary, *policy.primary_domains)
    ):
        return SourceTier.PRIMARY.value
    if any(_domain_matches(domain, rule) for rule in policy.trusted_secondary_domains):
        return SourceTier.TRUSTED_SECONDARY.value
    return SourceTier.SECONDARY.value


def _sanitize_excerpt(value: str, limit: int) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def _sum_usage(calls: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "web_search_requests": 0,
        "cost": 0.0,
    }
    for call in calls:
        usage = call.get("usage") or {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
        server = usage.get("server_tool_use")
        if isinstance(server, dict) and isinstance(server.get("web_search_requests"), int):
            totals["web_search_requests"] += max(0, server["web_search_requests"])
        cost = usage.get("cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            totals["cost"] += float(cost)
    return totals


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
