"""Physics-guarded exact-sequence variable-p recovery proposals.

The policies in this module are deliberately conservative recovery proposals,
not adjoint or DWR selectors.  They turn already measured field-error
localization into geometry-bound p4/p5/p6 plans while retaining the same
inactive-row-free exact-sequence machinery used by Task035d.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from .variable_p_degree_plan import (
    CellBoxKey,
    VariablePCellDegreePlan,
    build_variable_p_cell_degree_plan,
    cell_box_catalog,
)
from .variable_p_periodic_orbits import (
    build_variable_p_periodic_constraint_map,
)


@dataclass(frozen=True)
class PhysicsGuardVariablePPlan:
    """Two legal p-down cycles ending in a physics-guarded proposal."""

    cycle1: VariablePCellDegreePlan
    cycle2: VariablePCellDegreePlan
    p6_canonical_cell_ids: tuple[int, ...]
    p5_canonical_cell_ids: tuple[int, ...]
    p4_canonical_cell_ids: tuple[int, ...]
    audit: Mapping[str, Any]


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _active_rows_by_dimension(
    plan: VariablePCellDegreePlan,
) -> dict[str, int]:
    return {
        "edge": int(
            sum(
                len(rows)
                for rows in plan.entity_map.global_entity_rows[1]
            )
        ),
        "face": int(
            sum(
                len(rows)
                for rows in plan.entity_map.global_entity_rows[2]
            )
        ),
        "cell_interior": int(
            sum(
                len(rows)
                for rows in plan.entity_map.global_entity_rows[3]
            )
        ),
    }


def _is_outer_air_strip(box: CellBoxKey) -> bool:
    left = box[0] == 0.0 and box[3] == 8.25
    right = box[0] == 41.75 and box[3] == 50.0
    return bool(
        (left or right)
        and 0.0 <= box[2]
        and box[5] <= 120.0
    )


def _is_lower_grating_recovery(box: CellBoxKey) -> bool:
    return bool(
        16.5 <= box[0]
        and box[3] <= 33.5
        and 0.0 <= box[2]
        and box[5] <= 20.0
    )


def build_sidewall_z0_guard_plan(
    msh: Any,
    *,
    appended_dtn_rows: int = 80,
) -> PhysicsGuardVariablePPlan:
    """Recover lower grating p6 modes and lower only remote air to p4.

    Cycle 1 keeps p6 in the two lower grating slabs and lowers every other
    cell from p6 to p5.  Cycle 2 lowers only the two remote homogeneous-air
    strips to p4.  A p5 corridor therefore separates every p6 cell from every
    p4 cell, so the adjacent one-level rule is explicit rather than inferred.
    """

    boxes = cell_box_catalog(msh)
    if len(boxes) != 252:
        raise ValueError(
            "sidewall-z0 guard is qualified only on the 252-cell h10 mesh"
        )
    minimum = tuple(min(box[axis] for box in boxes) for axis in range(3))
    maximum = tuple(
        max(box[axis + 3] for box in boxes) for axis in range(3)
    )
    if minimum != (0.0, 0.0, -10.0) or maximum != (50.0, 25.0, 130.0):
        raise ValueError(
            "sidewall-z0 guard requires the Task034 rectangular airbox"
        )

    cycle1_degrees = {
        box: 6 if _is_lower_grating_recovery(box) else 5
        for box in boxes
    }
    cycle2_degrees = {
        box: (
            6
            if _is_lower_grating_recovery(box)
            else 4
            if _is_outer_air_strip(box)
            else 5
        )
        for box in boxes
    }
    cycle1 = build_variable_p_cell_degree_plan(msh, cycle1_degrees)
    cycle2 = build_variable_p_cell_degree_plan(
        msh,
        cycle2_degrees,
        previous_cell_degree_by_box=cycle1_degrees,
    )
    periodic = build_variable_p_periodic_constraint_map(
        cycle2.entity_map,
        axes=("x", "y"),
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )

    p6_ids = tuple(
        index
        for index, box in enumerate(boxes)
        if cycle2_degrees[box] == 6
    )
    p5_ids = tuple(
        index
        for index, box in enumerate(boxes)
        if cycle2_degrees[box] == 5
    )
    p4_ids = tuple(
        index
        for index, box in enumerate(boxes)
        if cycle2_degrees[box] == 4
    )
    independent_trace = int(periodic.independent_trace_rows)
    row_breakdown = _active_rows_by_dimension(cycle2)
    audit_payload = {
        "schema_version": "task035d.physics-guard-variable-p-plan.v1",
        "status": "sidewall_z0_guard_two_cycle_plan_pass",
        "pass": True,
        "selector": "sidewall_z0_guard_v1",
        "selection_class": "conservative_field_localization_recovery",
        "diagnostic_only_selector": True,
        "actual_channel_dwr": False,
        "formal_accuracy_credit": False,
        "cycle1_rule": (
            "keep lower two grating slabs at p6; lower every other p6 cell "
            "to p5"
        ),
        "cycle2_rule": (
            "keep lower-grating p6 and p5 guard; lower only the two remote "
            "homogeneous-air strips to p4"
        ),
        "p6_region": {
            "x_nm": [16.5, 33.5],
            "y_nm": [0.0, 25.0],
            "z_nm": [0.0, 20.0],
            "reason": (
                "protect the measured sidewall and z=0 error concentration"
            ),
        },
        "p4_region": {
            "x_nm": [[0.0, 8.25], [41.75, 50.0]],
            "y_nm": [0.0, 25.0],
            "z_nm": [0.0, 120.0],
            "reason": (
                "lower only remote homogeneous air while retaining a p5 "
                "corridor around every material interface and p6 cell"
            ),
        },
        "p6_canonical_cell_ids": list(p6_ids),
        "p5_canonical_cell_ids": list(p5_ids),
        "p4_canonical_cell_ids": list(p4_ids),
        "cycle1_cell_degree_counts": dict(
            cycle1.audit["cell_degree_counts"]
        ),
        "cell_degree_counts": dict(cycle2.audit["cell_degree_counts"]),
        "cycle1_plan_sha256": cycle1.audit[
            "cell_degree_plan_sha256"
        ],
        "cycle2_plan_sha256": cycle2.audit[
            "cell_degree_plan_sha256"
        ],
        "maximum_adjacent_cell_degree_jump": cycle2.audit[
            "maximum_adjacent_cell_degree_jump"
        ],
        "active_rows_by_dimension": row_breakdown,
        "actual_conforming_active_fe_dofs": cycle2.entity_map.active_rows,
        "active_trace_rows_before_periodic_elimination": (
            cycle2.entity_map.active_trace_rows
        ),
        "periodic_independent_trace_rows": independent_trace,
        "appended_dtn_rows": int(appended_dtn_rows),
        "predicted_direct_solve_rows": (
            independent_trace + int(appended_dtn_rows)
        ),
        "active_fe_dof_gate_limit": 90_000,
        "active_fe_dof_gate_pass": (
            cycle2.entity_map.active_rows <= 90_000
        ),
        "periodic_constraint_audit": dict(periodic.audit),
        "fresh_12_channel_pde_required": True,
        "ordinary_default_changed": False,
    }
    audit_payload["decision_identity_sha256"] = _json_sha256(
        audit_payload
    )
    return PhysicsGuardVariablePPlan(
        cycle1=cycle1,
        cycle2=cycle2,
        p6_canonical_cell_ids=p6_ids,
        p5_canonical_cell_ids=p5_ids,
        p4_canonical_cell_ids=p4_ids,
        audit=MappingProxyType(audit_payload),
    )


__all__ = [
    "PhysicsGuardVariablePPlan",
    "build_sidewall_z0_guard_plan",
]
