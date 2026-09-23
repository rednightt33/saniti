from __future__ import annotations

import os

from .analysis import SandboxClient, analysis_specs, manifest_spec
from .catalog import CatalogReader, catalog_specs
from .catalog_rows import catalog_rows_spec
from .preview import preview_spec
from .registry import ToolError, ToolOutcome, ToolRegistry, ToolSpec, error_outcome
from .request_data import GovernorClient, lookup_fact_spec, request_data_spec
from .rows import CursorCodec
from .system import capabilities_spec


def build_default_registry(
    catalog_reader: CatalogReader | None = None,
    *,
    catalog_timeout_seconds: float = 12.0,
    cursor_secret: bytes | None = None,
    page_size_default: int = 100,
    page_size_max: int = 200,
    page_max_bytes: int = 16000,
    preview_enabled: bool = True,
    governor_client: GovernorClient | None = None,
    governor_timeout_seconds: float = 95.0,
    request_data_max_bytes: int = 40000,
    sandbox_client: SandboxClient | None = None,
    sandbox_timeout_seconds: float = 50.0,
    python_analysis_max_bytes: int = 40000,
) -> ToolRegistry:
    """Single place to register tools; the orchestration loop never changes when tools are added."""
    registry = ToolRegistry()
    registry.register(capabilities_spec(registry))
    if catalog_reader is not None:
        for spec in catalog_specs(catalog_reader, timeout_seconds=catalog_timeout_seconds):
            registry.register(spec)
        registry.register(catalog_rows_spec(
            catalog_reader, CursorCodec(cursor_secret or os.urandom(32)),
            default_page_size=page_size_default, max_page_size=page_size_max,
            page_max_bytes=page_max_bytes, timeout_seconds=catalog_timeout_seconds,
        ))
        if preview_enabled:
            registry.register(preview_spec(catalog_reader, timeout_seconds=catalog_timeout_seconds))
    if governor_client is not None:
        registry.register(request_data_spec(
            governor_client, timeout_seconds=governor_timeout_seconds, max_result_bytes=request_data_max_bytes))
        registry.register(lookup_fact_spec(
            governor_client, timeout_seconds=min(governor_timeout_seconds, 30.0), max_result_bytes=request_data_max_bytes))
        registry.register(manifest_spec(governor_client, timeout_seconds=min(governor_timeout_seconds, 20.0)))
    if sandbox_client is not None:
        for spec in analysis_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                   max_result_bytes=python_analysis_max_bytes):
            registry.register(spec)
    return registry


__all__ = [
    "ToolError", "ToolOutcome", "ToolRegistry", "ToolSpec", "build_default_registry", "error_outcome",
]
