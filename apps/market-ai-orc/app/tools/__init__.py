from __future__ import annotations

from typing import Any

import os

from .analysis import SandboxClient, analysis_specs, manifest_spec
from .catalog import CatalogReader, catalog_specs
from .catalog_rows import catalog_rows_spec
from .data_need import data_need_specs
from .data_planner import ExecutionPlanner, feasibility_spec, prepare_bundle_spec
from .session import session_specs
from .data_compiler import BundleStore, DataRequestCompiler, prepare_spec
from .preview import preview_spec
from .registry import ToolError, ToolOutcome, ToolRegistry, ToolSpec, error_outcome
from .request_data import GovernorClient, dimension_values_spec, lookup_fact_spec, request_data_spec
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
    lookup_fact_enabled: bool = True,
    request_data_enabled: bool = False,
    bundles: BundleStore | None = None,
    dataneed_enabled: bool = False,
    session_timeout_seconds: float = 180.0,
    standard_period_return: bool = False,
    event_study: bool = False,
    hypothesis_plan: bool = False,
    method_guides: dict | None = None,
    catalog_discovery_v2: bool = False,
    plan_feasibility: bool = False,
    composite_keys: bool = False,
    point_in_time: bool = False,
    research_findings: bool = False,
    preflight_parts: bool = False,
    multi_angle: dict | None = None,
    bundle_limits: dict | None = None,
    planner_parallel_parts: int = 1,
    lineage_tool: bool = False,
    export: bool = False,
    metrics: list[dict] | None = None,
    evidence: bool = False,
    web_fact_client: Any | None = None,
) -> ToolRegistry:
    """Single place to register tools; the orchestration loop never changes when tools are added."""
    registry = ToolRegistry()
    registry.register(capabilities_spec(registry))
    # the same conditions as multi_angle_active below: while the research library is served, the catalog's RESEARCH
    # section says its reference methods cannot run
    library_served = bool(multi_angle and multi_angle.get("library")) and plan_feasibility and composite_keys \
        and dataneed_enabled and sandbox_client is not None and governor_client is not None
    if catalog_reader is not None:
        codec = CursorCodec(cursor_secret or os.urandom(32))
        for spec in catalog_specs(catalog_reader, timeout_seconds=catalog_timeout_seconds,
                                  discovery_v2=catalog_discovery_v2, codec=codec, point_in_time=point_in_time,
                                  research_library=library_served):
            registry.register(spec)
        registry.register(catalog_rows_spec(
            catalog_reader, codec,
            default_page_size=page_size_default, max_page_size=page_size_max,
            page_max_bytes=page_max_bytes, timeout_seconds=catalog_timeout_seconds,
        ))
        if preview_enabled:
            registry.register(preview_spec(catalog_reader, timeout_seconds=catalog_timeout_seconds))
    if governor_client is not None:
        # Model-written data requests are a rollback path only: the approved spec is compiled by the backend.
        if request_data_enabled:
            registry.register(request_data_spec(
                governor_client, timeout_seconds=governor_timeout_seconds, max_result_bytes=request_data_max_bytes))
        if lookup_fact_enabled:
            registry.register(lookup_fact_spec(
                governor_client, timeout_seconds=min(governor_timeout_seconds, 30.0),
                max_result_bytes=request_data_max_bytes))
        if not dataneed_enabled:  # governed datasets of the Analysis Spec path
            registry.register(manifest_spec(governor_client, timeout_seconds=min(governor_timeout_seconds, 20.0)))
        registry.register(dimension_values_spec(governor_client, timeout_seconds=min(governor_timeout_seconds, 30.0)))
    if sandbox_client is not None and not dataneed_enabled:
        # The Analysis Spec path (create_analysis_spec -> prepare_analysis_data -> run_python_analysis). The DataNeed
        # flow replaces it when AI_ENABLE_DATANEED is on; switching the flag off is the rollback.
        bundles = bundles if bundles is not None else BundleStore()
        registry.register(analysis_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                         max_result_bytes=python_analysis_max_bytes, bundles=bundles)[0])
        if governor_client is not None:
            # a partitioned extraction may take several Governor calls
            registry.register(prepare_spec(DataRequestCompiler(sandbox_client, governor_client, bundles),
                                           timeout_seconds=max(sandbox_timeout_seconds, governor_timeout_seconds) * 4,
                                           max_result_bytes=python_analysis_max_bytes))
        for spec in analysis_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                   max_result_bytes=python_analysis_max_bytes, bundles=bundles)[1:]:
            registry.register(spec)
    if sandbox_client is not None:
        if dataneed_enabled:
            for spec in data_need_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                        max_result_bytes=python_analysis_max_bytes, composite_keys=composite_keys,
                                        point_in_time=point_in_time, research_findings=research_findings):
                registry.register(spec)
            if governor_client is not None:
                # many Governor extractions plus the sandbox's verification and profiling
                registry.register(prepare_bundle_spec(
                    ExecutionPlanner(sandbox_client, governor_client, preflight=preflight_parts,
                                     limits=bundle_limits, parallel_parts=planner_parallel_parts),
                    timeout_seconds=max(sandbox_timeout_seconds, governor_timeout_seconds) * 6,
                    max_result_bytes=python_analysis_max_bytes))
                for spec in session_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                          execution_timeout_seconds=session_timeout_seconds,
                                          max_result_bytes=python_analysis_max_bytes,
                                          standard_period_return=standard_period_return,
                                          event_study=event_study):
                    registry.register(spec)
                if export:
                    # D4 (AI_ENABLE_EXPORT): a download file of an output, kept with the conversation
                    from .export import export_specs

                    for spec in export_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                             max_result_bytes=python_analysis_max_bytes):
                        registry.register(spec)
                if evidence:
                    # D6 (AI_ENABLE_EVIDENCE): claims recomputed by the Governor or from a released base table
                    from .evidence import evidence_specs

                    for spec in evidence_specs(sandbox_client, governor_client, timeout_seconds=sandbox_timeout_seconds,
                                               max_result_bytes=python_analysis_max_bytes):
                        registry.register(spec)
                if lineage_tool:
                    # D3 (AI_ENABLE_LINEAGE_TOOL): where an output's numbers came from
                    from .lineage import lineage_specs

                    for spec in lineage_specs(sandbox_client, timeout_seconds=sandbox_timeout_seconds,
                                              max_result_bytes=python_analysis_max_bytes):
                        registry.register(spec)
                multi_angle_active = multi_angle is not None and plan_feasibility and composite_keys
                if plan_feasibility and (not multi_angle_active or hypothesis_plan):
                    # validation plus one estimate-only Governor call per extraction envelope (with Multi-Angle
                    # Research check_research_feasibility replaces it, so the model sees one plan check; G3: a
                    # hypothesis plan beside it still checks its DataNeedSpec here)
                    registry.register(feasibility_spec(
                        sandbox_client, ExecutionPlanner(sandbox_client, governor_client, preflight=preflight_parts,
                                                         limits=bundle_limits,
                                                         parallel_parts=planner_parallel_parts),
                        timeout_seconds=max(sandbox_timeout_seconds, governor_timeout_seconds) * 3,
                        max_result_bytes=python_analysis_max_bytes, composite_keys=composite_keys,
                        point_in_time=point_in_time))
                if multi_angle_active:
                    _register_multi_angle(registry, sandbox_client, governor_client, multi_angle,
                                          timeout_seconds=max(sandbox_timeout_seconds, governor_timeout_seconds),
                                          session_timeout_seconds=session_timeout_seconds,
                                          max_result_bytes=python_analysis_max_bytes, point_in_time=point_in_time,
                                          preflight_parts=preflight_parts, bundle_limits=bundle_limits,
                                          planner_parallel_parts=planner_parallel_parts)
    if metrics and governor_client is not None:
        # D5 (AI_ENABLE_QUERY_METRIC): an official metric over periods in one Governor summary per period
        from .metric import menu, metric_specs

        for spec in metric_specs(governor_client, metrics, timeout_seconds=governor_timeout_seconds,
                                 max_result_bytes=python_analysis_max_bytes):
            registry.register(spec)
        registry.metric_menu = menu(metrics)
    if web_fact_client is not None:
        # S4b (AI_ENABLE_WEB_FACT): one fact that is not in the data, from market-web-governor /v1/fact
        from .web_fact import web_fact_spec

        registry.register(web_fact_spec(web_fact_client))
    if method_guides and dataneed_enabled:
        # 4b: the manual of each offered method; a research library method_id opens its library entry
        from .method_guides import method_guide_spec

        library = (multi_angle or {}).get("library") if multi_angle else None
        registry.register(method_guide_spec(method_guides["names"], library_rows=library))
        registry.method_guides = method_guides
    return registry


def _entity_checker(governor_client: GovernorClient):
    """G13: whether a token of the question is an entity of a table (the Governor's dimension values, exact match)."""
    def check(table: str, column: str, token: str) -> bool:
        result = governor_client.dimension_values(table, column, token)
        return any(str(value).upper() == token for value in result.get("values") or [])
    return check


def _register_multi_angle(registry: ToolRegistry, sandbox_client: SandboxClient, governor_client: GovernorClient,
                          multi_angle: dict, *, timeout_seconds: float, session_timeout_seconds: float,
                          max_result_bytes: int, point_in_time: bool, preflight_parts: bool,
                          bundle_limits: dict | None = None, planner_parallel_parts: int = 1) -> None:
    """AI_ENABLE_MULTI_ANGLE_RESEARCH: check_research_feasibility for the plan turn and the grouped executor's tools for
    the approved turn; the orchestrator creates one executor per approved plan through registry.multi_angle."""
    from ..research_run_executor import ResearchRunExecutor, executor_specs, remember_feasibility
    from .library import research_library_spec
    from .research_planner import ResearchDataPlanner, research_feasibility_spec

    planner = ResearchDataPlanner(sandbox_client, ExecutionPlanner(sandbox_client, governor_client,
                                                                   preflight=preflight_parts, limits=bundle_limits,
                                                                   parallel_parts=planner_parallel_parts),
                                  max_groups=multi_angle["max_groups"], min_angles=multi_angle["min_angles"],
                                  max_angles=multi_angle["max_angles"],
                                  limits={**(multi_angle.get("limits") or {}), **(bundle_limits or {})},
                                  min_families=int(multi_angle.get("min_families") or 0),
                                  entity_checker=_entity_checker(governor_client))
    if multi_angle.get("library"):
        registry.register(research_library_spec(multi_angle["library"]))
    registry.register(research_feasibility_spec(planner, timeout_seconds=timeout_seconds * 4 * multi_angle["max_groups"],
                                                max_result_bytes=max_result_bytes, point_in_time=point_in_time,
                                                on_result=remember_feasibility))
    for spec in executor_specs(timeout_seconds=timeout_seconds, execution_timeout_seconds=session_timeout_seconds,
                               max_result_bytes=max_result_bytes):
        registry.register(spec)
    bundle_planner = ExecutionPlanner(sandbox_client, governor_client, preflight=preflight_parts,
                                      limits=bundle_limits, parallel_parts=planner_parallel_parts)

    def factory(verified, request_id: str) -> ResearchRunExecutor:
        return ResearchRunExecutor(sandbox_client, bundle_planner, verified, request_id,
                                   execution_timeout=session_timeout_seconds, timeout=timeout_seconds,
                                   max_result_bytes=max_result_bytes,
                                   max_session_restarts=int(multi_angle.get("max_session_restarts", 1)))

    registry.multi_angle = {**multi_angle, "factory": factory}


__all__ = [
    "ToolError", "ToolOutcome", "ToolRegistry", "ToolSpec", "build_default_registry", "error_outcome",
]
