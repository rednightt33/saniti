from __future__ import annotations

from .registry import ToolError, ToolOutcome, ToolRegistry, ToolSpec, error_outcome
from .system import capabilities_spec


def build_default_registry() -> ToolRegistry:
    """Single place to register tools; the orchestration loop never changes when tools are added."""
    registry = ToolRegistry()
    registry.register(capabilities_spec(registry))
    return registry


__all__ = [
    "ToolError", "ToolOutcome", "ToolRegistry", "ToolSpec", "build_default_registry", "error_outcome",
]
