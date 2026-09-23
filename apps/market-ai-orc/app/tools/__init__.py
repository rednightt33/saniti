from __future__ import annotations

from .catalog import CatalogReader, catalog_specs
from .registry import ToolError, ToolOutcome, ToolRegistry, ToolSpec, error_outcome
from .system import capabilities_spec


def build_default_registry(
    catalog_reader: CatalogReader | None = None, *, catalog_timeout_seconds: float = 12.0
) -> ToolRegistry:
    """Single place to register tools; the orchestration loop never changes when tools are added."""
    registry = ToolRegistry()
    registry.register(capabilities_spec(registry))
    if catalog_reader is not None:
        for spec in catalog_specs(catalog_reader, timeout_seconds=catalog_timeout_seconds):
            registry.register(spec)
    return registry


__all__ = [
    "ToolError", "ToolOutcome", "ToolRegistry", "ToolSpec", "build_default_registry", "error_outcome",
]
