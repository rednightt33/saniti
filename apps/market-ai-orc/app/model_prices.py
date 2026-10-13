"""EXEC-MODELS: the input and output price of each offered model, read from OpenRouter's public model list and
refreshed in the background every hour (user: "informasi in dan out of each model updated on hourly basis").

The list price per token (OpenRouter /models pricing.prompt, pricing.completion, pricing.input_cache_read) is shown per
one million tokens. The first read starts at startup in the background; a stale list is returned as is while a
background read replaces it, and a failed read keeps the last prices (pattern of provider_policy.CachePricePolicy).
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Callable, Protocol

from .model_choices import MODEL_CHOICES

MODEL_PRICES_TTL_SECONDS = 3600  # user: "updated on hourly basis"


class ModelListSource(Protocol):
    def models(self) -> list[dict[str, Any]] | None: ...


def per_million(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return round(price * 1_000_000, 6) if price >= 0 else None


class ModelPrices:
    """The prices of MODEL_CHOICES, refreshed every ttl_seconds."""

    def __init__(self, source: ModelListSource, *, ttl_seconds: int = 3600,
                 log: Callable[..., None] | None = None, clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)) -> None:
        self.source = source
        self.ttl_seconds = ttl_seconds
        self.log = log or (lambda event, **fields: None)
        self.clock = clock
        self.wall_clock = wall_clock
        self._prices: dict[str, dict[str, float | None]] = {}
        self._fetched_at: str | None = None
        self._read_at: float | None = None
        self._lock = threading.Lock()
        self._refreshing = False

    def refresh(self) -> None:
        """Read the model list once; a failure keeps the last prices."""
        try:
            listed = self.source.models()
        except Exception:  # noqa: BLE001 - prices are information only, never a run's failure
            listed = None
        wanted = {option.model for option in MODEL_CHOICES}
        found: dict[str, dict[str, float | None]] = {}
        for item in listed or []:
            if isinstance(item, dict) and item.get("id") in wanted:
                pricing = item.get("pricing") or {}
                found[item["id"]] = {"input_per_million": per_million(pricing.get("prompt")),
                                     "output_per_million": per_million(pricing.get("completion")),
                                     "cache_read_per_million": per_million(pricing.get("input_cache_read"))}
        with self._lock:
            self._read_at = self.clock()
            self._refreshing = False
            if listed is None:
                self.log("ai_model_prices_refreshed", status="UNAVAILABLE", models=len(self._prices),
                         fetched_at=self._fetched_at)
                return
            self._prices = {**self._prices, **found}
            self._fetched_at = self.wall_clock().isoformat(timespec="seconds")
            fetched_at = self._fetched_at
        self.log("ai_model_prices_refreshed", status="OK", models=len(found), fetched_at=fetched_at,
                 missing=sorted(wanted - set(found)))

    def start(self) -> None:
        self._start_refresh()

    def _start_refresh(self) -> None:
        with self._lock:
            if self._refreshing:
                return
            self._refreshing = True
        threading.Thread(target=self.refresh, name="model-prices", daemon=True).start()

    def snapshot(self) -> tuple[dict[str, dict[str, float | None]], str | None]:
        """(prices per model, when they were read); a stale list starts a background read."""
        with self._lock:
            stale = self._read_at is None or self.clock() - self._read_at >= self.ttl_seconds
            prices, fetched_at = dict(self._prices), self._fetched_at
        if stale:
            self._start_refresh()
        return prices, fetched_at
