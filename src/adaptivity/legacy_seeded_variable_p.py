"""Historical multi-goal seeds for true Task035d variable-p plans.

The seed is deliberately weaker than a formal Task035d estimator: it combines
the accepted Task035b R00 and normalized R/T cell indicators, while the
12 significant powers, complex amplitudes, and field probes still require a
fresh direct solve.  This module only turns that hash-bound seed into a
periodic, one-level-at-a-time p4/p5/p6 proposal.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)

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
class LegacyMultigoalCellSeed:
    """One partition-independent historical cell-score vector."""

    score_by_canonical_cell_id: np.ndarray
    mesh_geometry_sha256: str
    payload_sha256: str
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class LegacySeededVariablePPlan:
    """Two legal cycles ending in a periodic p4/p5/p6 proposal."""

    seed: LegacyMultigoalCellSeed
    cycle1: VariablePCellDegreePlan
    cycle2: VariablePCellDegreePlan
    p6_canonical_cell_ids: tuple[int, ...]
    p5_canonical_cell_ids: tuple[int, ...]
    p4_canonical_cell_ids: tuple[int, ...]
    audit: Mapping[str, Any]


def _json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _score_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        b"".join(struct.pack("<d", float(value)) for value in values)
    ).hexdigest()


def load_legacy_multigoal_cell_seed(
    msh: Any,
    path: str | Path,
) -> LegacyMultigoalCellSeed:
    """Load the compact Task035b seed and bind it to the actual mesh."""

    resolved = Path(path).expanduser().resolve()
    raw = resolved.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema_version") != (
        "task035d.legacy-multigoal-seed.v1"
    ):
        raise ValueError("legacy multi-goal seed has an unknown schema")
    if payload.get("production_qualified") is not False:
        raise ValueError(
            "historical Task035b seed must not claim production authority"
        )
    values = np.asarray(
        payload.get("score_by_canonical_cell_id"),
        dtype=np.float64,
    )
    cell_count = int(payload.get("cell_count", -1))
    if values.shape != (cell_count,) or cell_count <= 0:
        raise ValueError("historical score vector has the wrong length")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("historical score vector must be finite/nonnegative")
    if not np.isclose(
        float(np.sum(values)),
        float(payload.get("score_sum", np.nan)),
        rtol=2.0e-14,
        atol=2.0e-14,
    ):
        raise ValueError("historical score sum is inconsistent")
    observed_score_sha = _score_sha256(values)
    if observed_score_sha != payload.get("score_sha256_f64le"):
        raise ValueError("historical score vector SHA is invalid")

    _ids, _records, keys = canonical_owned_cell_ids(msh)
    geometry_sha = geometry_key_sha256(keys)
    if len(keys) != cell_count:
        raise ValueError("historical seed and actual mesh cell counts differ")
    if geometry_sha != payload.get("mesh_geometry_sha256"):
        raise ValueError(
            "historical seed geometry differs from the actual mesh"
        )
    values.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": "task035d.legacy-multigoal-seed-audit.v1",
            "status": "historical_seed_geometry_and_hash_pass",
            "pass": True,
            "payload_path": str(resolved),
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "score_sha256_f64le": observed_score_sha,
            "mesh_geometry_sha256": geometry_sha,
            "cell_count": cell_count,
            "score_sum": float(np.sum(values)),
            "production_qualified": False,
            "formal_selector_authority": False,
            "fresh_12_channel_pde_required": True,
            "ordinary_default_changed": False,
        }
    )
    return LegacyMultigoalCellSeed(
        score_by_canonical_cell_id=values,
        mesh_geometry_sha256=geometry_sha,
        payload_sha256=audit["payload_sha256"],
        audit=audit,
    )


class _DisjointSet:
    def __init__(self, count: int):
        self.parent = list(range(int(count)))

    def find(self, value: int) -> int:
        value = int(value)
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def periodic_cell_components(
    boxes: tuple[CellBoxKey, ...],
    *,
    axes: tuple[str, ...] = ("x", "y"),
) -> tuple[tuple[int, ...], ...]:
    """Close cells touching opposite periodic faces into common components."""

    normalized_axes = tuple(dict.fromkeys(axis.lower() for axis in axes))
    if not normalized_axes or any(axis not in {"x", "y"} for axis in normalized_axes):
        raise ValueError("periodic cell axes must be a nonempty subset of x/y")
    if not boxes:
        raise ValueError("periodic cell closure requires at least one cell")
    minimum = tuple(min(box[axis] for box in boxes) for axis in range(3))
    maximum = tuple(max(box[axis + 3] for box in boxes) for axis in range(3))
    disjoint = _DisjointSet(len(boxes))
    for axis_name in normalized_axes:
        axis = {"x": 0, "y": 1}[axis_name]
        tangential = tuple(value for value in range(3) if value != axis)
        low: dict[tuple[float, ...], int] = {}
        high: dict[tuple[float, ...], int] = {}
        for canonical_id, box in enumerate(boxes):
            key = tuple(box[value] for value in tangential) + tuple(
                box[value + 3] for value in tangential
            )
            if box[axis] == minimum[axis]:
                low[key] = canonical_id
            if box[axis + 3] == maximum[axis]:
                high[key] = canonical_id
        if set(low) != set(high):
            raise RuntimeError(
                f"periodic {axis_name}-boundary cell catalogs differ"
            )
        for key in sorted(low):
            disjoint.union(low[key], high[key])
    groups: dict[int, list[int]] = {}
    for canonical_id in range(len(boxes)):
        groups.setdefault(disjoint.find(canonical_id), []).append(
            canonical_id
        )
    return tuple(
        sorted(
            (tuple(sorted(group)) for group in groups.values()),
            key=lambda group: group,
        )
    )


def _face_neighbor_sets(
    boxes: tuple[CellBoxKey, ...],
) -> tuple[frozenset[int], ...]:
    neighbors = [set() for _box in boxes]
    for left in range(len(boxes)):
        left_box = boxes[left]
        for right in range(left + 1, len(boxes)):
            right_box = boxes[right]
            touching_axes = 0
            matching_axes = 0
            for axis in range(3):
                left_interval = (
                    left_box[axis],
                    left_box[axis + 3],
                )
                right_interval = (
                    right_box[axis],
                    right_box[axis + 3],
                )
                if left_interval == right_interval:
                    matching_axes += 1
                elif (
                    left_interval[1] == right_interval[0]
                    or right_interval[1] == left_interval[0]
                ):
                    touching_axes += 1
            if matching_axes == 2 and touching_axes == 1:
                neighbors[left].add(right)
                neighbors[right].add(left)
    return tuple(frozenset(values) for values in neighbors)


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


def build_legacy_seeded_variable_p_plan(
    msh: Any,
    seed: LegacyMultigoalCellSeed,
    *,
    target_score_mass: float,
    appended_dtn_rows: int = 80,
) -> LegacySeededVariablePPlan:
    """Build a p6 core, p5 face ring, and p4 exterior in two legal cycles."""

    target = float(target_score_mass)
    if not 0.0 < target <= 1.0:
        raise ValueError("target score mass must lie in (0, 1]")
    boxes = cell_box_catalog(msh)
    scores = seed.score_by_canonical_cell_id
    if len(boxes) != len(scores):
        raise ValueError("seed score count differs from cell-box catalog")
    components = periodic_cell_components(boxes)
    component_score = {
        component: float(np.sum(scores[np.asarray(component)]))
        for component in components
    }
    ranked = sorted(
        components,
        key=lambda component: (-component_score[component], component),
    )
    p6: set[int] = set()
    captured = 0.0
    selected_components: list[tuple[int, ...]] = []
    for component in ranked:
        selected_components.append(component)
        p6.update(component)
        captured += component_score[component]
        if captured >= target:
            break
    if not p6:
        raise RuntimeError("multi-goal seed selected no p6 cells")

    component_by_cell = {
        canonical_id: component
        for component in components
        for canonical_id in component
    }
    neighbors = _face_neighbor_sets(boxes)
    p5_raw = {
        neighbor
        for canonical_id in p6
        for neighbor in neighbors[canonical_id]
        if neighbor not in p6
    }
    p5 = {
        member
        for canonical_id in p5_raw
        for member in component_by_cell[canonical_id]
        if member not in p6
    }
    p4 = set(range(len(boxes))) - p6 - p5
    if not p4:
        raise ValueError(
            "selected seed leaves no p4 region; lower target score mass"
        )

    cycle1_degrees = {
        box: 6 if canonical_id in p6 else 5
        for canonical_id, box in enumerate(boxes)
    }
    cycle2_degrees = {
        box: (
            6
            if canonical_id in p6
            else 5
            if canonical_id in p5
            else 4
        )
        for canonical_id, box in enumerate(boxes)
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
    p6_ids = tuple(sorted(p6))
    p5_ids = tuple(sorted(p5))
    p4_ids = tuple(sorted(p4))
    row_breakdown = _active_rows_by_dimension(cycle2)
    independent_trace = int(periodic.independent_trace_rows)
    audit_payload = {
        "schema_version": "task035d.legacy-seeded-variable-p-plan.v1",
        "status": "legacy_seeded_two_cycle_variable_p_plan_pass",
        "pass": True,
        "target_score_mass": target,
        "captured_score_mass": captured,
        "selected_periodic_component_count": len(selected_components),
        "periodic_component_count_total": len(components),
        "p6_canonical_cell_ids": list(p6_ids),
        "p5_canonical_cell_ids": list(p5_ids),
        "p4_canonical_cell_ids": list(p4_ids),
        "cell_degree_counts": dict(cycle2.audit["cell_degree_counts"]),
        "cycle1_cell_degree_counts": dict(
            cycle1.audit["cell_degree_counts"]
        ),
        "cycle1_plan_sha256": cycle1.audit[
            "cell_degree_plan_sha256"
        ],
        "cycle2_plan_sha256": cycle2.audit[
            "cell_degree_plan_sha256"
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
        "transition_rule": (
            "cycle1 p6->p5 only; cycle2 keeps p6/p5 or lowers p5->p4"
        ),
        "p5_buffer_rule": (
            "physical face one-ring around p6 cells, then x/y periodic "
            "component closure"
        ),
        "periodic_constraint_audit": dict(periodic.audit),
        "seed_audit": dict(seed.audit),
        "historical_seed_only": True,
        "fresh_12_channel_pde_required": True,
        "ordinary_default_changed": False,
    }
    audit_payload["decision_identity_sha256"] = _json_sha256(
        audit_payload
    )
    return LegacySeededVariablePPlan(
        seed=seed,
        cycle1=cycle1,
        cycle2=cycle2,
        p6_canonical_cell_ids=p6_ids,
        p5_canonical_cell_ids=p5_ids,
        p4_canonical_cell_ids=p4_ids,
        audit=MappingProxyType(audit_payload),
    )


__all__ = [
    "LegacyMultigoalCellSeed",
    "LegacySeededVariablePPlan",
    "build_legacy_seeded_variable_p_plan",
    "load_legacy_multigoal_cell_seed",
    "periodic_cell_components",
]
