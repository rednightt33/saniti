from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import ModelSlot, Settings
from .fetcher import DocumentFetcher, FetchError, FetchedDocument, verify_quotes
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
    def __init__(
        self,
        settings: Settings,
        store: SqliteStore,
        provider: OpenRouterProvider,
        fetcher: DocumentFetcher | None = None,
    ):
        self.settings = settings
        self.store = store
        self.provider = provider
        self.fetcher = fetcher or DocumentFetcher(settings)

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
                "governor_side_fetch": True,
                "verified_quotes": True,
                "model_slots": True,
            },
            "default_model_slot": self.settings.default_slot,
            "model_slots": [slot.public() for slot in self.settings.slots],
            "limits": {
                "max_criteria": self.settings.max_criteria,
                "max_searches": self.settings.max_searches,
                "max_results_per_search": self.settings.max_results_per_search,
                "max_evidence_items": self.settings.max_evidence_items,
                "max_output_characters": self.settings.max_output_characters,
                "max_excerpt_characters": self.settings.max_excerpt_characters,
                "fetch_max_bytes": self.settings.fetch_max_bytes,
                "fetch_max_redirects": self.settings.fetch_max_redirects,
                "fetch_max_pdf_pages": self.settings.fetch_max_pdf_pages,
                "fetch_max_characters": self.settings.fetch_max_characters,
                "fetch_model_characters": self.settings.fetch_model_characters,
                "fetch_max_quotes": self.settings.fetch_max_quotes,
            },
        }

    def create_need(self, request: CreateWebNeedRequest) -> dict[str, Any]:
        self._validate_limits(request.web_need)
        slot = self._resolve_slot(request.web_need.model_slot)
        body = request.model_dump(mode="json")
        if body["web_need"].get("model_slot") is None:
            body["web_need"].pop("model_slot", None)  # keeps fingerprints of requests made before model slots
        fingerprint = _sha256_json(body)
        now = _now()
        web_need_id = f"wn_{uuid.uuid4().hex}"
        plan = self._plan(request.web_need)
        plan.update({"model_slot": slot.slot, "model": slot.model})
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
        try:
            slot = self._slot_for_plan(need["plan"])
        except GovernorValidationError as exc:
            return self._complete_blocked(
                web_need_id, need["request_id"], spec, need["plan"], [c.criterion_id for c in spec.criteria],
                exc.code, str(exc), "REFINE_WEB_NEED",
            )
        return self._execute(web_need_id, need["request_id"], spec, need["plan"], slot)

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
            model_slot=request.model_slot,
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
        slot = self._resolve_slot(request.model_slot)
        criterion = EvidenceCriterion(
            criterion_id="fetch", question=request.objective, required=True, direction="SUPPORT", minimum_sources=1
        )
        host = (urlsplit(request.url).hostname or "invalid.example").lower()
        spec = WebNeedSpec(
            objective=request.objective,
            evidence_standard=EvidenceStandard.SINGLE_SOURCE,
            criteria=[criterion],
            source_policy=SourcePolicy(allowed_domains=[host[4:] if host.startswith("www.") else host]),
            budget=WebBudget(max_searches=1, max_results_per_search=1, max_evidence_items=1),
            locale=request.locale,
            model_slot=request.model_slot,
        )
        body = {
            "contract_version": request.contract_version,
            "request_id": request.request_id,
            "operation": "FETCH_URL",
            "url": request.url,
            "objective": request.objective,
            "locale": request.locale,
        }
        if request.model_slot is not None:
            body["model_slot"] = request.model_slot
        fingerprint = _sha256_json(body)
        now = _now()
        web_need_id = f"wn_{uuid.uuid4().hex}"
        plan = {
            "operation": "FETCH_URL",
            "tasks": [{"task_id": "task_fetch", "criterion_id": "fetch", "url": request.url}],
            "stop_conditions": {"all_required_criteria_covered": True, "stop_on_primary_source": False},
            "fetched_by": "governor",
            "model_slot": slot.slot,
            "model": slot.model,
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
            plan = stored["plan"]
        self.store.begin_execution(web_need_id)
        try:
            document = self.fetcher.fetch(request.url)
        except FetchError as exc:
            return self._complete_blocked(
                web_need_id, request.request_id, spec, plan, ["fetch"], exc.code, str(exc), "REVIEW_FETCH",
                applied=[{"exact_url": request.url, "fetched_by": "governor", "model_slot": slot.slot,
                          "model": slot.model}],
            )
        return self._read_fetched_document(web_need_id, request, spec, criterion, plan, slot, document)

    def _read_fetched_document(
        self,
        web_need_id: str,
        request: FetchRequest,
        spec: WebNeedSpec,
        criterion: EvidenceCriterion,
        plan: dict[str, Any],
        slot: ModelSlot,
        document: FetchedDocument,
    ) -> dict[str, Any]:
        document_id = f"doc_{uuid.uuid4().hex}"
        document_row = {"document_id": document_id, "text": document.text, **document.metadata()}
        document_public = {"document_id": document_id, **document.metadata()}
        final_domain = (urlsplit(document.final_url).hostname or "").lower()
        applied = {
            "exact_url": request.url,
            "fetched_by": "governor",
            "final_url": document.final_url,
            "http_status": document.http_status,
            "media_type": document.media_type,
            "model_slot": slot.slot,
            "model": slot.model,
        }
        warnings: list[dict[str, str]] = []
        if document.truncated:
            warnings.append({
                "code": "DOCUMENT_TRUNCATED",
                "message": f"Stored text was cut to {len(document.text)} characters"
                           + (f" and {document.pages_read} of {document.page_count} PDF pages" if document.page_count
                              and document.pages_read is not None and document.pages_read < document.page_count
                              else "") + ".",
            })
        if not _domain_allowed(final_domain, spec.source_policy):
            warnings.append({
                "code": "REDIRECTED_TO_OTHER_DOMAIN",
                "message": f"The URL redirected to {final_domain}; the document is stored but not used as evidence.",
            })
            return self._complete_fetch_without_evidence(
                web_need_id, request.request_id, spec, plan, criterion, document_row, document_public, applied,
                warnings, "REDIRECTED_TO_OTHER_DOMAIN",
            )
        if not document.useful:
            warnings.append({
                "code": "DYNAMIC_PAGE_OR_EMPTY",
                "message": "The fetched document has almost no text (a script-rendered page or an empty file); "
                           "no model call was made.",
            })
            return self._complete_fetch_without_evidence(
                web_need_id, request.request_id, spec, plan, criterion, document_row, document_public, applied,
                warnings, "DYNAMIC_PAGE_OR_EMPTY",
            )
        model_text = document.text[: self.settings.fetch_model_characters]
        if len(document.text) > len(model_text):
            warnings.append({
                "code": "DOCUMENT_TRUNCATED_FOR_MODEL",
                "message": f"The model read the first {len(model_text)} of {len(document.text)} stored characters.",
            })
        call_id = f"pc_{uuid.uuid4().hex}"
        try:
            result = self.provider.read_document(
                request.url, request.objective, request.locale, model_text, call_id, slot,
                max_quotes=self.settings.fetch_max_quotes,
            )
        except ProviderError as exc:
            call = self._failed_call(call_id, "fetch", "READ_DOCUMENT", exc, _now(), slot)
            return self._complete_blocked(
                web_need_id, request.request_id, spec, plan, ["fetch"], exc.code, str(exc), "RETRY_PROVIDER",
                applied=[applied], calls=[call], documents=[document_row], document_public=[document_public],
            )
        if not result.output_complete:
            warnings.append(_incomplete_warning("fetch", result))
        verified, rejected = verify_quotes(model_text, result.quotes, limit=self.settings.fetch_max_quotes)
        if rejected:
            warnings.append({
                "code": "QUOTE_NOT_IN_SOURCE",
                "message": f"{len(rejected)} quote(s) from the model were not found verbatim in the document "
                           "and were discarded.",
            })
        canonical_url = _canonical_url(document.final_url)
        evidence = []
        for quote in verified:
            excerpt = str(quote["text"])[: self.settings.max_excerpt_characters]
            content_hash = hashlib.sha256((canonical_url + "\n" + excerpt).encode("utf-8")).hexdigest()
            evidence.append({
                "evidence_id": f"ev_{uuid.uuid4().hex}",
                "citation_id": f"cit_{hashlib.sha256((web_need_id + canonical_url + content_hash).encode()).hexdigest()[:24]}",
                "provider_call_id": call_id,
                "title": (document.title or final_domain)[:500],
                "url": request.url,
                "canonical_url": canonical_url,
                "domain": final_domain,
                "published_at": None,
                "retrieved_at": document.retrieved_at,
                "source_tier": _source_tier(final_domain, spec.source_policy),
                "content_type": document.content_type,
                "excerpt": excerpt,
                "excerpt_kind": "VERIFIED_QUOTE",
                "content_sha256": content_hash,
                "document_id": document_id,
                "quote_start": quote["start"],
                "quote_end": quote["end"],
            })
        links = [("fetch", item["evidence_id"]) for item in evidence]
        coverage = [self._coverage(criterion, result, evidence, spec)]
        status = "EVIDENCE_READY" if coverage[0]["status"] in {"SATISFIED", "CONTRADICTED"} else "PARTIAL"
        if coverage[0]["status"] == "BLOCKED":
            next_action = "RETRY_PROVIDER"
        else:
            next_action = "SYNTHESIZE" if status == "EVIDENCE_READY" else "REVIEW_FETCH"
        response = self._response(
            web_need_id, request.request_id, status, spec, plan, coverage, evidence, warnings, next_action,
            [applied], [result.provider_call], slot,
        )
        response["documents"] = [document_public]
        return self._persist(web_need_id, status, response, [result.provider_call], evidence, links, spec,
                             documents=[document_row])

    def _complete_fetch_without_evidence(
        self,
        web_need_id: str,
        request_id: str,
        spec: WebNeedSpec,
        plan: dict[str, Any],
        criterion: EvidenceCriterion,
        document_row: dict[str, Any],
        document_public: dict[str, Any],
        applied: dict[str, Any],
        warnings: list[dict[str, str]],
        gap: str,
    ) -> dict[str, Any]:
        coverage = [{
            "criterion_id": criterion.criterion_id,
            "required": True,
            "status": "NOT_FOUND",
            "assessment": "INSUFFICIENT",
            "summary": "The document was fetched and stored, but it gives no usable text for this objective.",
            "evidence_ids": [],
            "citation_ids": [],
            "gaps": [gap],
        }]
        slot = self._slot_for_plan(plan)
        response = self._response(
            web_need_id, request_id, "PARTIAL", spec, plan, coverage, [], warnings, "REVIEW_FETCH", [applied], [],
            slot,
        )
        response["documents"] = [document_public]
        return self._persist(web_need_id, "PARTIAL", response, [], [], [], spec, documents=[document_row])

    def _complete_blocked(
        self,
        web_need_id: str,
        request_id: str,
        spec: WebNeedSpec,
        plan: dict[str, Any],
        criterion_ids: list[str],
        code: str,
        message: str,
        next_action: str,
        *,
        applied: list[dict[str, Any]] | None = None,
        calls: list[dict[str, Any]] | None = None,
        documents: list[dict[str, Any]] | None = None,
        document_public: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        coverage = [{
            "criterion_id": criterion_id,
            "required": True,
            "status": "BLOCKED",
            "assessment": "INSUFFICIENT",
            "summary": "No evidence could be gathered.",
            "evidence_ids": [],
            "citation_ids": [],
            "gaps": [code],
        } for criterion_id in criterion_ids]
        try:
            slot = self._slot_for_plan(plan)
        except GovernorValidationError:
            slot = None
        response = self._response(
            web_need_id, request_id, "BLOCKED", spec, plan, coverage, [], [{"code": code, "message": message}],
            next_action, applied or [], calls or [], slot,
        )
        if document_public:
            response["documents"] = document_public
        self.store.complete_execution(
            web_need_id, "BLOCKED", response, calls or [], [], [], _now(), error_code=code, documents=documents,
        )
        return response

    def _execute(
        self, web_need_id: str, request_id: str, spec: WebNeedSpec, plan: dict[str, Any], slot: ModelSlot
    ) -> dict[str, Any]:
        provider_calls: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        applied_policies: list[dict[str, Any]] = []
        failures: dict[str, dict[str, Any]] = {}
        results: dict[str, ProviderResult] = {}
        candidates: dict[str, list[dict[str, Any]]] = {}

        for criterion in spec.criteria:
            call_id = f"pc_{uuid.uuid4().hex}"
            try:
                result = self.provider.research_criterion(web_need_id, spec, criterion, call_id, slot)
            except ProviderError as exc:
                provider_calls.append(self._failed_call(call_id, criterion.criterion_id, "SEARCH", exc, _now(), slot))
                warnings.append({"code": exc.code, "message": f"{criterion.criterion_id}: {exc}"})
                failures[criterion.criterion_id] = {
                    "criterion_id": criterion.criterion_id,
                    "required": criterion.required,
                    "status": "BLOCKED",
                    "assessment": "INSUFFICIENT",
                    "summary": "Provider did not return usable evidence.",
                    "evidence_ids": [],
                    "citation_ids": [],
                    "gaps": [exc.code],
                }
                continue
            provider_calls.append(result.provider_call)
            applied_policies.append(result.applied_policy)
            results[criterion.criterion_id] = result
            if not result.output_complete:
                warnings.append(_incomplete_warning(criterion.criterion_id, result))
            overrun = _search_overrun(criterion.criterion_id, result)
            if overrun:
                warnings.append(overrun)
            queue = []
            rejected = 0
            for annotation in result.annotations:
                item = self._evidence_from_annotation(web_need_id, result.provider_call, annotation, spec.source_policy)
                if item:
                    queue.append(item)
                else:
                    rejected += 1
            candidates[criterion.criterion_id] = queue
            if rejected:
                warnings.append({
                    "code": "CITATIONS_REJECTED_BY_POLICY",
                    "message": f"{criterion.criterion_id}: {rejected} provider citation(s) failed the domain policy "
                               "and were not used as evidence.",
                })

        evidence, links, per_criterion, dropped = _allocate_evidence(
            candidates, min(spec.budget.max_evidence_items, self.settings.max_evidence_items)
        )
        if dropped:
            detail = ", ".join(f"{criterion_id} {count}" for criterion_id, count in dropped.items())
            warnings.append({
                "code": "EVIDENCE_BUDGET_REACHED",
                "message": f"Evidence item budget reached; citations not kept per criterion: {detail}. The budget "
                           "is shared across criteria in turn.",
            })

        coverage = []
        for criterion in spec.criteria:
            if criterion.criterion_id in failures:
                coverage.append(failures[criterion.criterion_id])
            else:
                coverage.append(self._coverage(
                    criterion, results[criterion.criterion_id], per_criterion.get(criterion.criterion_id, []), spec
                ))

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
            blocked_required = any(entry["status"] == "BLOCKED" for entry in required)
            next_action = "RETRY_PROVIDER" if blocked_required else "REFINE_WEB_NEED"

        response = self._response(
            web_need_id, request_id, status, spec, plan, coverage, evidence, warnings, next_action, applied_policies,
            provider_calls, slot,
        )
        return self._persist(web_need_id, status, response, provider_calls, evidence, links, spec)

    def _persist(
        self,
        web_need_id: str,
        status: str,
        response: dict[str, Any],
        provider_calls: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        links: list[tuple[str, str]],
        spec: WebNeedSpec,
        documents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # The store keeps the full excerpts; only the response copy is shortened to its character budget.
        stored = [dict(item) for item in evidence]
        response["evidence"] = [dict(item) for item in evidence]
        self._fit_response(response, response["evidence"], spec.budget.max_output_characters)
        self.store.complete_execution(
            web_need_id, status, response, provider_calls, stored, links, _now(), documents=documents
        )
        return response

    def _resolve_slot(self, number: int | None) -> ModelSlot:
        try:
            slot = self.settings.slot(number)
        except KeyError:
            raise GovernorValidationError("MODEL_SLOT_UNAVAILABLE", f"model slot {number} does not exist") from None
        if not slot.enabled or not slot.model:
            raise GovernorValidationError("MODEL_SLOT_UNAVAILABLE", f"model slot {slot.slot} is not enabled")
        return slot

    def _slot_for_plan(self, plan: dict[str, Any]) -> ModelSlot:
        """Run with the slot and model recorded when the plan was approved; a plan made before slots uses the
        default slot."""
        slot = self._resolve_slot(plan.get("model_slot"))
        recorded = plan.get("model")
        if recorded and recorded != slot.model:
            slot = ModelSlot(slot.slot, recorded, slot.label, slot.enabled, slot.max_output_tokens,
                             slot.reasoning_effort, slot.engine)
        return slot

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
        summary = result.summary
        if not result.output_complete:
            gaps.append("PROVIDER_OUTPUT_INCOMPLETE")
            reason = result.provider_call.get("diagnostics", {}).get("incomplete_reason") or "missing labelled output"
            return {
                "criterion_id": criterion.criterion_id,
                "required": criterion.required,
                "status": "BLOCKED",
                "assessment": "INSUFFICIENT",
                "summary": f"Provider output was incomplete ({reason}); no finding is reported for this criterion.",
                "evidence_ids": [item["evidence_id"] for item in evidence],
                "citation_ids": [item["citation_id"] for item in evidence],
                "gaps": gaps,
            }
        if not evidence and result.assessment in {"SUPPORTED", "CONTRADICTED", "MIXED"}:
            gaps.append("NO_USABLE_CITATION")
            summary = "Provider summary withheld: none of its citations could be recorded as evidence."
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
            "summary": summary,
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
        slot: ModelSlot | None = None,
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
                "model_slot": slot.slot if slot else None,
                "model": slot.model if slot else None,
                "provider_call_count": len(provider_calls),
                "usage": _sum_usage(provider_calls),
                "provider_calls": [_call_summary(call) for call in provider_calls],
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
                if excerpt and len(excerpt) > max_chars:
                    item["excerpt"] = excerpt[:max_chars] if max_chars else None
                    item["excerpt_kind"] = "TRUNCATED_IN_RESPONSE" if max_chars else "NOT_INCLUDED_IN_RESPONSE"
            if len(json.dumps(response, ensure_ascii=False)) <= limit:
                break
        response["warnings"].append({
            "code": "RESPONSE_COMPACTED",
            "message": "Evidence excerpts were shortened in this response to fit its budget; the full excerpt of each "
                       "item stays available at GET /v1/evidence/{evidence_id}.",
        })
        size = len(json.dumps(response, ensure_ascii=False))
        if size > limit:
            response["warnings"].append({
                "code": "RESPONSE_BUDGET_EXCEEDED",
                "message": f"The response is {size} characters, above max_output_characters {limit}, even without "
                           "excerpts.",
            })

    def _failed_call(
        self, call_id: str, criterion_id: str, operation: str, error: ProviderError, now: str,
        slot: ModelSlot | None = None,
    ) -> dict[str, Any]:
        return {
            "provider_call_id": call_id,
            "criterion_id": criterion_id,
            "operation": operation,
            "provider": self.provider.name,
            "adapter_version": self.provider.adapter_version,
            "model": slot.model if slot else self.settings.openrouter_model,
            "model_slot": slot.slot if slot else None,
            "provider_response_id": None,
            "status": "FAILED",
            "usage": {},
            "error_code": error.code,
            "response_sha256": None,
            "started_at": now,
            "completed_at": now,
        }


def _allocate_evidence(
    candidates: dict[str, list[dict[str, Any]]], cap: int
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Share the evidence budget across criteria in turn, so an early criterion cannot use all of it. A citation
    already kept for another criterion is linked again without using budget."""
    evidence: list[dict[str, Any]] = []
    links: list[tuple[str, str]] = []
    per_criterion: dict[str, list[dict[str, Any]]] = {criterion_id: [] for criterion_id in candidates}
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    positions = {criterion_id: 0 for criterion_id in candidates}
    while True:
        progressed = False
        for criterion_id, queue in candidates.items():
            while positions[criterion_id] < len(queue):
                item = queue[positions[criterion_id]]
                key = (item["canonical_url"], item["content_sha256"])
                existing = by_key.get(key)
                if existing is None and len(evidence) >= cap:
                    break
                positions[criterion_id] += 1
                progressed = True
                if existing is None:
                    by_key[key] = item
                    evidence.append(item)
                    existing = item
                if existing not in per_criterion[criterion_id]:
                    per_criterion[criterion_id].append(existing)
                    links.append((criterion_id, existing["evidence_id"]))
                if existing is item:
                    break  # one new item per criterion per turn
        if not progressed:
            break
    dropped = {
        criterion_id: len(queue) - positions[criterion_id]
        for criterion_id, queue in candidates.items()
        if positions[criterion_id] < len(queue)
    }
    return evidence, links, per_criterion, dropped


def _incomplete_warning(criterion_id: str, result: ProviderResult) -> dict[str, str]:
    diagnostics = result.provider_call.get("diagnostics", {})
    return {
        "code": "PROVIDER_OUTPUT_INCOMPLETE",
        "message": f"{criterion_id}: provider response status {diagnostics.get('response_status')!s}, "
                   f"incomplete reason {diagnostics.get('incomplete_reason')!s}; the criterion has no verdict.",
    }


def _search_overrun(criterion_id: str, result: ProviderResult) -> dict[str, str] | None:
    """The provider may run more searches than max_uses allows; report it instead of passing it silently."""
    allowed = result.applied_policy.get("max_uses")
    usage = result.provider_call.get("usage") or {}
    server = usage.get("server_tool_use_details") or usage.get("server_tool_use") or {}
    reported = server.get("web_search_requests") if isinstance(server, dict) else None
    if not isinstance(reported, int):
        reported = (result.provider_call.get("diagnostics") or {}).get("tool_calls_observed")
    if not isinstance(allowed, int) or not isinstance(reported, int) or reported <= allowed:
        return None
    return {
        "code": "PROVIDER_SEARCH_LIMIT_EXCEEDED",
        "message": f"{criterion_id}: the provider ran {reported} web searches although max_uses was {allowed}.",
    }


def _call_summary(call: dict[str, Any]) -> dict[str, Any]:
    usage = call.get("usage") or {}
    return {
        "provider_call_id": call["provider_call_id"],
        "criterion_id": call["criterion_id"],
        "operation": call["operation"],
        "status": call["status"],
        "error_code": call.get("error_code"),
        "diagnostics": call.get("diagnostics", {}),
        "usage": {key: value for key, value in usage.items() if isinstance(value, (int, float, dict))},
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
        "tool_calls_observed": 0,
        "cost": 0.0,
    }
    for call in calls:
        usage = call.get("usage") or {}
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                totals[key] += value
        observed = (call.get("diagnostics") or {}).get("tool_calls_observed")
        if isinstance(observed, int) and observed >= 0:
            totals["tool_calls_observed"] += observed
        # OpenRouter's Responses API reports server_tool_use_details; server_tool_use is the older shape.
        server = usage.get("server_tool_use_details") or usage.get("server_tool_use")
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
