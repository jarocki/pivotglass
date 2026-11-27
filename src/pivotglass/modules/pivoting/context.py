"""Wire a PivotRun to a ToolContext: the evidence path, readiness, and the pivot trail.

Every surface (cockpit, cyberdeck, classic REPL) builds its runs here, so the
three cannot disagree about how a hop is executed or recorded (DEC-PIVOT-RUN-001).
"""

from __future__ import annotations

from typing import Any

from pivotglass.core.module_config import ServiceDisabledError, resolve_module_credentials
from pivotglass.modules.pivoting.run import Listener, ModuleOutcome, PivotNode, PivotRun


def _object_ids(ctx: Any) -> set[str]:
    return {str(item["id"]) for item in ctx.workspace_mgr.get_stix_objects() if item.get("id")}


def build_context_run(
    ctx: Any,
    seeds: list[str],
    *,
    depth: int,
    budget: int,
    listener: Listener | None = None,
) -> PivotRun:
    """Return a PivotRun whose modules run through ``ctx.run_module`` with cascades off."""

    from pivotglass.core.document_library import PivotTrailAuthority
    from pivotglass.core.error_interpreter import interpret

    def execute(module: str, value: str) -> ModuleOutcome:
        # Hold the context's execution lock across the diff so another caller's
        # objects are never attributed to this request.
        with ctx.execution_lock:
            before = _object_ids(ctx)
            result = ctx.run_module(module, value, cascade=False)
            if "error" in result:
                raise RuntimeError(str(result["error"]))
            created = tuple(sorted(_object_ids(ctx) - before))
        return ModuleOutcome(results=list(result.get("results") or []), artifact_ids=created)

    instances: dict[str, Any] = {}

    def readiness(module: str) -> str | None:
        if module not in instances:
            instances[module] = ctx.plugin_mgr.get_module(module)
        instance = instances[module]
        if instance is None:
            return "module not installed"
        try:
            credentials = resolve_module_credentials(module, ctx.config_mgr)
        except ServiceDisabledError:
            return "disabled in Configuration"
        if getattr(instance, "requires_api_key", None) is False:
            return None
        if credentials and not any(str(item).strip() for item in credentials.values()):
            return "not configured (no credential)"
        return None

    trail = PivotTrailAuthority(ctx.workspace_mgr)

    def on_expand(node: PivotNode, parent: PivotNode | None) -> None:
        if parent is None:
            # The analyst named this seed: an explicit investigation action.
            trail.record_indicator(node.value)
            return
        trail.record_indicator(
            node.value,
            action="auto_pivoted",
            basis=(
                f"Automated pivot run {run.run_id} expanded this indicator at depth {node.depth}: "
                f"{node.source_module} returned it when asked about {parent.value}. Collection "
                "workflow, not an observed relationship."
            ),
            created_by="system",
            from_value=parent.value,
        )

    def describe_failure(exc: Exception, module: str) -> str:
        interpretation = interpret(exc, context={"surface": "pivot_run", "module": module})
        return f"{interpretation.category}: {interpretation.summary}"

    try:
        workspace = str(ctx.workspace_mgr.active)
    except RuntimeError:
        workspace = "default"
    run = PivotRun(
        seeds,
        executor=execute,
        policy_config=ctx.config.general.auto_pivot_policy,
        depth=depth,
        budget=budget,
        readiness=readiness,
        listener=listener,
        on_expand=on_expand,
        describe_failure=describe_failure,
        workspace=workspace,
    )
    return run
