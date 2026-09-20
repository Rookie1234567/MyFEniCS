"""Small, explicit capacity arithmetic for the opt-in V22 B trial.

The V11 symbolic request remains in :mod:`fullspace_bounded_mumps` and is
recorded by the V22 caller as a prediction only.  This module computes the
finite package that can be offered to a live MUMPS factor from measured
inventory and process-tree scopes.  Inventory objects coexist with the
factor, while the runtime's temporary pool is preserved as a separate gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_DECIMAL_MB = 1_000_000
_PHYSICAL_MEMORY_POLICY_V23 = "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"


def _nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _component_bytes(values: Mapping[str, Any], name: str) -> dict[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return {
        str(key): _nonnegative_int(value, f"{name}[{key!r}]")
        for key, value in values.items()
    }


def _workspace_phase_bytes(
    phases: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, int]], dict[str, int], int]:
    if not isinstance(phases, Mapping) or not phases:
        raise TypeError("future_workspace_phases must be a non-empty mapping")
    normalized: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for phase, components in phases.items():
        phase_name = str(phase)
        values = _component_bytes(
            components, f"future_workspace_phases[{phase_name!r}]"
        )
        if not values:
            raise ValueError(
                f"future_workspace_phases[{phase_name!r}] must not be empty"
            )
        normalized[phase_name] = values
        totals[phase_name] = int(sum(values.values()))
    return normalized, totals, max(totals.values())


def capacity_budget_v22(
    *,
    launch_cap_bytes: int,
    inventory_cap_bytes: int | None,
    current_tree_rss_bytes: int,
    current_inventory_bytes: int,
    future_inventory_components: Mapping[str, int],
    future_workspace_phases: Mapping[str, Mapping[str, int]],
    numeric_untouched_pool_bytes: int,
    workspace_pool_cap_bytes: int | None,
    memory_policy: str = "CAPACITY_CONTROLLED_LOCAL_MUMPS_V22",
    backend_quota_mb: int = 4687,
) -> dict[str, Any]:
    """Freeze one bounded numeric ICNTL(23) package.

    The numeric quota protects only the current object ledger and the
    runtime's untouched pre-numeric temporary pool.  Later H6/p6/Krylov and
    p4 recovery objects are declared separately.  Once numeric succeeds, the
    factor may continue only if ``continuation_max_allocated_bytes`` is still
    non-negative; that gate accounts for those resident objects and retains
    the full runtime workspace pool instead of replacing it with an optimistic
    stage estimate.
    """

    launch_cap_bytes = _nonnegative_int(launch_cap_bytes, "launch_cap_bytes")
    if memory_policy == _PHYSICAL_MEMORY_POLICY_V23:
        if inventory_cap_bytes is not None or workspace_pool_cap_bytes is not None:
            raise ValueError(
                "V23 physical-pressure budget must not receive static inventory/workspace caps"
            )
        backend_quota_mb = _nonnegative_int(backend_quota_mb, "backend_quota_mb")
        current_tree_rss_bytes = _nonnegative_int(
            current_tree_rss_bytes, "current_tree_rss_bytes"
        )
        current_inventory_bytes = _nonnegative_int(
            current_inventory_bytes, "current_inventory_bytes"
        )
        future_inventory = _component_bytes(
            future_inventory_components, "future_inventory_components"
        )
        future_workspace, future_workspace_phase_totals, future_workspace_peak_bytes = (
            _workspace_phase_bytes(future_workspace_phases)
        )
        physical_headroom_bytes = launch_cap_bytes - current_tree_rss_bytes
        safe_headroom_bytes = physical_headroom_bytes - 1
        icntl23_mb = min(backend_quota_mb, max(0, safe_headroom_bytes // _DECIMAL_MB))
        status = "capacity_available" if icntl23_mb >= 1 else "capacity_unavailable"
        return {
            "schema": "task039extra.v23.mumps-capacity-budget.v1",
            "policy": _PHYSICAL_MEMORY_POLICY_V23,
            "status": status,
            "reason": (
                "bounded native quota fits current physical headroom; future estimates "
                "are recorded and continuation is gated by live pressure"
                if status == "capacity_available"
                else "current physical headroom is below the minimum native quota"
            ),
            "limiting_scope": ("current_physical_headroom",),
            "unit": "bytes; ICNTL(23) uses decimal_MB",
            "launch_cap_bytes": launch_cap_bytes,
            "inventory_cap_bytes": None,
            "current_tree_rss_bytes": current_tree_rss_bytes,
            "current_inventory_bytes": current_inventory_bytes,
            "future_inventory_components": future_inventory,
            "future_inventory_bytes": int(sum(future_inventory.values())),
            "future_workspace_phases": future_workspace,
            "future_workspace_phase_totals": future_workspace_phase_totals,
            "future_workspace_peak_bytes": future_workspace_peak_bytes,
            "workspace_scope_valid": None,
            "numeric_untouched_pool_bytes": 0,
            "workspace_pool_cap_bytes": None,
            "physical_headroom_bytes": physical_headroom_bytes,
            "numeric_inventory_headroom_bytes": None,
            "numeric_tree_headroom_bytes": physical_headroom_bytes,
            "numeric_raw_headroom_bytes": physical_headroom_bytes,
            "numeric_safe_factor_bytes": safe_headroom_bytes,
            "continuation_inventory_headroom_bytes": None,
            "continuation_tree_headroom_bytes": None,
            "continuation_max_allocated_bytes": None,
            "continuation_status": "deferred_to_live_physical_pressure",
            "physical_pressure_gate": True,
            "minimum_icntl23_mb": 1,
            "backend_quota_mb": backend_quota_mb,
            "icntl23_mb": int(icntl23_mb),
            "formula": (
                "ICNTL23=min(previous_native_success_quota, "
                "floor((current_dynamic_cap-current_tree_rss-1)/1e6)); "
                "continuation uses a fresh postnumeric physical-pressure sample"
            ),
            "workspace_staging": (
                "future phase peaks are evidence only; no untouched workspace pool "
                "is added to a hard continuation gate"
            ),
        }
    if memory_policy != "CAPACITY_CONTROLLED_LOCAL_MUMPS_V22":
        raise ValueError(f"unsupported capacity budget policy: {memory_policy!r}")
    if inventory_cap_bytes is None or workspace_pool_cap_bytes is None:
        raise ValueError("V22 static capacity budget requires inventory and workspace caps")
    inventory_cap_bytes = _nonnegative_int(inventory_cap_bytes, "inventory_cap_bytes")
    current_tree_rss_bytes = _nonnegative_int(
        current_tree_rss_bytes, "current_tree_rss_bytes"
    )
    current_inventory_bytes = _nonnegative_int(
        current_inventory_bytes, "current_inventory_bytes"
    )
    numeric_untouched_pool_bytes = _nonnegative_int(
        numeric_untouched_pool_bytes, "numeric_untouched_pool_bytes"
    )
    workspace_pool_cap_bytes = _nonnegative_int(
        workspace_pool_cap_bytes,
        "workspace_pool_cap_bytes",
    )
    future_inventory = _component_bytes(
        future_inventory_components, "future_inventory_components"
    )
    future_workspace, future_workspace_phase_totals, future_workspace_peak_bytes = (
        _workspace_phase_bytes(future_workspace_phases)
    )
    future_inventory_bytes = int(sum(future_inventory.values()))
    # Each phase is a simultaneous set.  Mutually exclusive phases are not
    # added to one another; the largest simultaneous set is the bound.  The
    # original runtime workspace pool remains a separate, unchanged reserve.
    workspace_scope_valid = workspace_pool_cap_bytes >= future_workspace_peak_bytes

    numeric_inventory_headroom_bytes = inventory_cap_bytes - current_inventory_bytes
    numeric_tree_headroom_bytes = (
        launch_cap_bytes - current_tree_rss_bytes - numeric_untouched_pool_bytes
    )
    # Runtime projected RSS uses a strict ``<`` launch-cap check.  Keep one
    # byte of headroom before converting the quota to decimal megabytes so an
    # exact integer-MB boundary cannot be rejected after ICNTL(23) is set.
    numeric_raw_headroom_bytes = min(
        numeric_inventory_headroom_bytes, numeric_tree_headroom_bytes
    )
    numeric_safe_factor_bytes = numeric_raw_headroom_bytes - 1
    continuation_inventory_headroom_bytes = (
        inventory_cap_bytes - current_inventory_bytes - future_inventory_bytes
    )
    continuation_tree_headroom_bytes = (
        launch_cap_bytes
        - current_tree_rss_bytes
        - future_inventory_bytes
        - workspace_pool_cap_bytes
    )
    continuation_max_allocated_bytes = min(
        continuation_inventory_headroom_bytes,
        continuation_tree_headroom_bytes,
    )
    icntl23_mb = max(0, numeric_safe_factor_bytes // _DECIMAL_MB)

    limiting_scope = []
    if numeric_inventory_headroom_bytes <= numeric_tree_headroom_bytes:
        limiting_scope.append("numeric_inventory")
    if numeric_tree_headroom_bytes <= numeric_inventory_headroom_bytes:
        limiting_scope.append("numeric_process_tree")
    if not workspace_scope_valid:
        status = "capacity_unavailable"
        reason = (
            "declared continuation workspace exceeds the preserved runtime "
            f"pool ({future_workspace_peak_bytes} B > "
            f"{workspace_pool_cap_bytes} B)"
        )
    elif numeric_safe_factor_bytes < _DECIMAL_MB:
        status = "capacity_unavailable"
        reason = (
            "numeric safe factor package is below the frozen 1 MB "
            f"ICNTL(23) minimum ({numeric_safe_factor_bytes} B < {_DECIMAL_MB} B)"
        )
    else:
        status = "capacity_available"
        reason = "finite numeric factor package fits measured inventory and process-tree scopes"

    return {
        "schema": "task039extra.v22.mumps-capacity-budget.v1",
        "status": status,
        "reason": reason,
        "limiting_scope": tuple(limiting_scope),
        "unit": "bytes; ICNTL(23) uses decimal_MB",
        "launch_cap_bytes": launch_cap_bytes,
        "inventory_cap_bytes": inventory_cap_bytes,
        "current_tree_rss_bytes": current_tree_rss_bytes,
        "current_inventory_bytes": current_inventory_bytes,
        "future_inventory_components": future_inventory,
        "future_inventory_bytes": future_inventory_bytes,
        "future_workspace_phases": future_workspace,
        "future_workspace_phase_totals": future_workspace_phase_totals,
        "future_workspace_peak_bytes": future_workspace_peak_bytes,
        "workspace_scope_valid": workspace_scope_valid,
        "numeric_untouched_pool_bytes": numeric_untouched_pool_bytes,
        "workspace_pool_cap_bytes": workspace_pool_cap_bytes,
        "numeric_inventory_headroom_bytes": numeric_inventory_headroom_bytes,
        "numeric_tree_headroom_bytes": numeric_tree_headroom_bytes,
        "numeric_raw_headroom_bytes": numeric_raw_headroom_bytes,
        "numeric_safe_factor_bytes": numeric_safe_factor_bytes,
        "continuation_inventory_headroom_bytes": continuation_inventory_headroom_bytes,
        "continuation_tree_headroom_bytes": continuation_tree_headroom_bytes,
        "continuation_max_allocated_bytes": continuation_max_allocated_bytes,
        "continuation_status": (
            "capacity_available"
            if workspace_scope_valid and continuation_max_allocated_bytes >= 0
            else "capacity_unavailable"
        ),
        "minimum_icntl23_mb": 1,
        "icntl23_mb": int(icntl23_mb),
        "formula": (
            "numeric_limit=min(inventory_cap-current_inventory, "
            "launch_cap-current_tree_rss-numeric_untouched_pool); "
            "continuation_max_allocated=min(inventory_cap-current_inventory-"
            "future_inventory, launch_cap-current_tree_rss-future_inventory-"
            "workspace_pool_cap); future_workspace_peak=max(phase sums); "
            "ICNTL23=floor((numeric_limit-1)/1e6)"
        ),
        "workspace_staging": (
            "runtime_pool_preserved; phase_peaks_sum_only_simultaneous_components"
        ),
    }


__all__ = ["capacity_budget_v22"]
