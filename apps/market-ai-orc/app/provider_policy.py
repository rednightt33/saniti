"""Which OpenRouter providers the agent's model calls skip (AI_PROVIDER_MAX_CACHE_PRICE_RATIO).

A run re-sends the same instructions, tools and conversation on every model call, so most input tokens are cache reads
(about 90% in the 2026-10-03 golden test). A provider that charges almost the full input price for a cache read makes
the same run several times dearer: on 2026-10-04, xiaomi/mimo-v2.6-flash had one provider charging 96% of the input
price for a cache read while the other seven charged about 2%; deepseek/deepseek-v4.1-flash had three such providers.

The list is derived, not written by hand: OpenRouter's /models/{model}/endpoints publishes each endpoint's prompt and
input_cache_read prices. An endpoint whose cache-read price is more than the configured share of its prompt price (or
that publishes no cache-read price) is excluded; a provider is ignored only when every endpoint it serves is excluded.
The endpoints are re-read in the background once the list is older than its time to live, so a new provider or a price
change needs no deploy. When the metadata cannot be read, the last list is kept (none at startup: OpenRouter's default
routing); when every endpoint would be excluded, nothing is ignored, so the policy can never leave a model unreachable.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Protocol


class EndpointSource(Protocol):
    def model_endpoints(self, model: str) -> list[dict[str, Any]] | None: ...


def _price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def provider_slug(endpoint: dict[str, Any]) -> str | None:
    """The provider part of an endpoint tag ("inference-net/fp8" -> "inference-net"), the slug provider.ignore takes."""
    tag = endpoint.get("tag")
    if not isinstance(tag, str) or not tag.strip():
        return None
    return tag.strip().split("/", 1)[0].lower()


def cache_price_ratio(endpoint: dict[str, Any]) -> float | None:
    """Cache-read price as a share of the prompt price; 1.0 when no cache-read price is published (no discount);
    None when the prompt price is missing or zero (nothing to compare)."""
    pricing = endpoint.get("pricing") or {}
    prompt = _price(pricing.get("prompt"))
    if not prompt:
        return None
    cache = _price(pricing.get("input_cache_read"))
    return 1.0 if cache is None else cache / prompt


def excluded_providers(endpoints: list[dict[str, Any]], max_ratio: float) -> tuple[list[str], dict[str, float], bool]:
    """(providers to ignore, ratio per excluded endpoint tag, every endpoint excluded). The list is empty when every
    endpoint would be excluded, so the model stays reachable."""
    keep: set[str] = set()
    drop: set[str] = set()
    ratios: dict[str, float] = {}
    for endpoint in endpoints:
        slug = provider_slug(endpoint)
        if slug is None:
            continue
        ratio = cache_price_ratio(endpoint)
        if ratio is not None and ratio > max_ratio:
            drop.add(slug)
            ratios[str(endpoint.get("tag"))] = round(ratio, 3)
        else:
            keep.add(slug)
    if not keep:
        return [], ratios, bool(drop)
    return sorted(drop - keep), ratios, False


class CachePricePolicy:
    """The provider.ignore list for one model, refreshed in the background every ttl_seconds."""

    def __init__(self, source: EndpointSource, model: str, max_ratio: float, *, ttl_seconds: int = 3600,
                 log: Callable[..., None] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.source = source
        self.model = model
        self.max_ratio = max_ratio
        self.ttl_seconds = ttl_seconds
        self.log = log or (lambda event, **fields: None)
        self.clock = clock
        self._ignored: list[str] = []
        self._read_at: float | None = None
        self._lock = threading.Lock()
        self._refreshing = False

    def refresh(self) -> None:
        """Re-read the endpoints once; a failure keeps the previous list."""
        try:
            endpoints = self.source.model_endpoints(self.model)
        except Exception:  # noqa: BLE001 - routing falls back to the last list, never fails a run
            endpoints = None
        with self._lock:
            self._read_at = self.clock()
            self._refreshing = False
            if endpoints is None:
                self.log("ai_provider_policy", model=self.model, status="METADATA_UNAVAILABLE",
                         ignored=list(self._ignored))
                return
            ignored, ratios, all_excluded = excluded_providers(endpoints, self.max_ratio)
            changed = ignored != self._ignored
            self._ignored = ignored
        self.log("ai_provider_policy", model=self.model, status="OK", max_cache_price_ratio=self.max_ratio,
                 endpoints=len(endpoints), ignored=ignored, excluded_endpoint_ratios=ratios,
                 all_excluded=all_excluded, changed=changed)

    def start(self) -> None:
        """First read in the background, so startup and the first request never wait on OpenRouter."""
        self._start_refresh()

    def _start_refresh(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        threading.Thread(target=self.refresh, name="provider-policy", daemon=True).start()

    def ignored(self) -> list[str]:
        """The current list; a stale list is returned as is while a background refresh replaces it."""
        with self._lock:
            stale = self._read_at is not None and self.clock() - self._read_at >= self.ttl_seconds
            ignored = list(self._ignored)
        if stale:
            self._start_refresh()
        return ignored
