"""Shadow-only level-three h-saturation contracts for Task035e.

The Task035e production controller is intentionally capped at dyadic level
two.  A leaf already at that cap therefore has no ordinary ``h-refine``
shadow, even though an unresolved h-error may still be present.  This module
provides a separate, fail-closed saturation probe:

* enumerate every level-two leaf in complete x/y periodic cell orbits;
* build one real balanced dyadic level-three forest for a selected orbit;
* optionally materialize the actual broken-hexa hanging/Floquet trace graph;
* expose a local child-restriction, Schur and 59-goal DWR lower-bound check.

Nothing here creates a production plan.  Level-three children remain
shadow-only, receive no production row numbers, and can never be selected as
the next controller state.  Geometry or local algebra alone never grants the
formal h-saturation stopping condition.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .dyadic_hexa_refinement import (
    BalancedDyadicHexForest,
    Box,
    DyadicHexKey,
    refine_balanced_dyadic_hexa_forest,
)
from .task035e_hp_transition import HPTransitionState


H_SATURATION_CATALOG_SCHEMA = "task035e.level3-h-saturation-catalog.v1"
H_SATURATION_PATCH_SCHEMA = "task035e.level3-h-saturation-patch.v1"
H_SATURATION_CONSTRAINT_SCHEMA = (
    "task035e.level3-h-saturation-constraints.v1"
)
H_SATURATION_LOWER_BOUND_SCHEMA = (
    "task035e.level3-h-saturation-local-lower-bound.v1"
)

PRODUCTION_MAXIMUM_LEVEL = 2
SHADOW_MAXIMUM_LEVEL = 3
FORMAL_GOAL_COUNT = 59
_ROUND_DIGITS = 12
_ALGEBRA_TOLERANCE = 5.0e-10


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    return hashlib.sha256(array.view(np.uint8)).hexdigest()


def _key_row(key: DyadicHexKey) -> dict[str, int]:
    return key.to_dict()


def _round(value: float) -> float:
    return round(float(value), _ROUND_DIGITS)


def _box_key(box: Box) -> tuple[float, ...]:
    return tuple(_round(value) for value in box)


def _state_gate(
    state: HPTransitionState,
) -> tuple[
    BalancedDyadicHexForest,
    Mapping[DyadicHexKey, int],
]:
    if not isinstance(state, HPTransitionState):
        raise ValueError("h-saturation input must be an HPTransitionState")
    forest = state.forest
    degrees = state.cell_degree_by_key
    if forest.audit.get("pass") is not True:
        raise ValueError("h-saturation requires a passing dyadic forest")
    if tuple(forest.periodic_axes) != ("x", "y"):
        raise ValueError("Task035e h-saturation requires x/y periodicity")
    periodic = forest.audit.get("periodic_boundary_audit")
    if not isinstance(periodic, Mapping) or set(periodic) != {"x", "y"}:
        raise ValueError("h-saturation forest has no complete periodic audit")
    if any(row.get("matching") is not True for row in periodic.values()):
        raise ValueError("h-saturation forest has unmatched periodic patches")
    if set(degrees) != set(forest.leaf_by_key):
        raise ValueError("h-saturation requires one degree for every leaf")
    if any(type(value) is not int or value not in {4, 5, 6} for value in degrees.values()):
        raise ValueError("h-saturation degrees must stay in p4/p5/p6")
    observed_maximum = max(
        (cell.key.level for cell in forest.leaves),
        default=-1,
    )
    if observed_maximum > PRODUCTION_MAXIMUM_LEVEL:
        raise ValueError("production state already exceeds dyadic level two")
    return forest, degrees


class _DisjointSet:
    def __init__(self, keys: Sequence[DyadicHexKey]) -> None:
        self._parent = {key: key for key in keys}

    def find(self, key: DyadicHexKey) -> DyadicHexKey:
        parent = self._parent[key]
        if parent != key:
            parent = self.find(parent)
            self._parent[key] = parent
        return parent

    def join(self, left: DyadicHexKey, right: DyadicHexKey) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root


@dataclass(frozen=True, slots=True)
class HLevel3PeriodicOrbit:
    """One complete periodic selection unit for a level-two h shadow."""

    orbit_id: str
    leaf_keys: tuple[DyadicHexKey, ...]
    boundary_axes: tuple[str, ...]
    orbit_sha256: str


@dataclass(frozen=True, slots=True)
class HLevel3SaturationCatalog:
    """All level-two leaves grouped into selectable shadow-only orbits."""

    state_sha256: str
    level_two_leaf_keys: tuple[DyadicHexKey, ...]
    periodic_orbits: tuple[HLevel3PeriodicOrbit, ...]
    audit: Mapping[str, Any]


def _periodic_level_two_orbits(
    forest: BalancedDyadicHexForest,
    level_two: tuple[DyadicHexKey, ...],
) -> tuple[tuple[DyadicHexKey, ...], ...]:
    cells = forest.leaf_by_key
    if len({_box_key(cells[key].box) for key in level_two}) != len(level_two):
        raise RuntimeError("level-two leaf boxes are not unique")
    bounds = forest.domain_bounds
    scale = max(
        bounds[axis + 3] - bounds[axis] for axis in range(3)
    )
    tolerance = max(scale, 1.0) * 1.0e-11
    groups = _DisjointSet(level_two)
    boundary: dict[
        tuple[int, int, int, float, float, float, float],
        DyadicHexKey,
    ] = {}
    for key in level_two:
        box = cells[key].box
        for axis_name in forest.periodic_axes:
            axis = {"x": 0, "y": 1, "z": 2}[axis_name]
            tangential = tuple(
                candidate for candidate in range(3) if candidate != axis
            )
            side: int | None = None
            if math.isclose(
                box[axis],
                bounds[axis],
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                side = 0
            elif math.isclose(
                box[axis + 3],
                bounds[axis + 3],
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                side = 1
            if side is None:
                continue
            signature = (
                axis,
                side,
                key.level,
                _round(box[tangential[0]]),
                _round(box[tangential[0] + 3]),
                _round(box[tangential[1]]),
                _round(box[tangential[1] + 3]),
            )
            if signature in boundary:
                raise RuntimeError(
                    "periodic level-two boundary signature is not unique"
                )
            boundary[signature] = key
    for key in level_two:
        box = cells[key].box
        for axis_name in forest.periodic_axes:
            axis = {"x": 0, "y": 1, "z": 2}[axis_name]
            tangential = tuple(
                candidate for candidate in range(3) if candidate != axis
            )
            side: int | None = None
            if math.isclose(
                box[axis],
                bounds[axis],
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                side = 0
            elif math.isclose(
                box[axis + 3],
                bounds[axis + 3],
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                side = 1
            if side is None:
                continue
            partner = boundary.get(
                (
                    axis,
                    1 - side,
                    key.level,
                    _round(box[tangential[0]]),
                    _round(box[tangential[0] + 3]),
                    _round(box[tangential[1]]),
                    _round(box[tangential[1] + 3]),
                )
            )
            if partner is None:
                raise RuntimeError(
                    "one periodic level-two leaf has no translated peer"
                )
            if cells[partner].material_tag != cells[key].material_tag:
                raise RuntimeError(
                    "one periodic level-two orbit mixes material tags"
                )
            groups.join(key, partner)
    components: dict[DyadicHexKey, list[DyadicHexKey]] = {}
    for key in level_two:
        components.setdefault(groups.find(key), []).append(key)
    return tuple(
        sorted(
            (tuple(sorted(values)) for values in components.values()),
            key=lambda values: values[0],
        )
    )


def build_level3_h_saturation_catalog(
    state: HPTransitionState,
) -> HLevel3SaturationCatalog:
    """Enumerate the level-two saturation probes without refining a cell."""

    forest, _degrees = _state_gate(state)
    level_two = tuple(
        cell.key
        for cell in forest.leaves
        if cell.key.level == PRODUCTION_MAXIMUM_LEVEL
    )
    if not level_two:
        raise ValueError(
            "h-saturation requires at least one dyadic level-two leaf"
        )
    orbit_keys = _periodic_level_two_orbits(forest, level_two)
    if set(key for orbit in orbit_keys for key in orbit) != set(level_two):
        raise RuntimeError("periodic h-saturation orbit partition is incomplete")
    if sum(map(len, orbit_keys)) != len(level_two):
        raise RuntimeError("periodic h-saturation orbits overlap")

    bounds = forest.domain_bounds
    scale = max(
        bounds[axis + 3] - bounds[axis] for axis in range(3)
    )
    tolerance = max(scale, 1.0) * 1.0e-11
    axes = ("x", "y")
    orbits: list[HLevel3PeriodicOrbit] = []
    for index, keys in enumerate(orbit_keys):
        touched = tuple(
            axis_name
            for axis_name, axis in zip(axes, (0, 1), strict=True)
            if any(
                math.isclose(
                    forest.leaf_by_key[key].box[axis],
                    bounds[axis],
                    rel_tol=0.0,
                    abs_tol=tolerance,
                )
                or math.isclose(
                    forest.leaf_by_key[key].box[axis + 3],
                    bounds[axis + 3],
                    rel_tol=0.0,
                    abs_tol=tolerance,
                )
                for key in keys
            )
        )
        identity = {
            "state_sha256": state.state_sha256,
            "leaf_keys": [_key_row(key) for key in keys],
            "boundary_axes": list(touched),
            "production_maximum_level": PRODUCTION_MAXIMUM_LEVEL,
            "shadow_maximum_level": SHADOW_MAXIMUM_LEVEL,
        }
        digest = _json_sha256(identity)
        orbits.append(
            HLevel3PeriodicOrbit(
                orbit_id=f"h3-orbit-{index:06d}-{digest[:12]}",
                leaf_keys=keys,
                boundary_axes=touched,
                orbit_sha256=digest,
            )
        )

    orbit_payload = [
        {
            "orbit_id": orbit.orbit_id,
            "leaf_keys": [_key_row(key) for key in orbit.leaf_keys],
            "boundary_axes": list(orbit.boundary_axes),
            "orbit_sha256": orbit.orbit_sha256,
        }
        for orbit in orbits
    ]
    audit_payload: dict[str, Any] = {
        "schema_version": H_SATURATION_CATALOG_SCHEMA,
        "status": "h_saturation_shadow_catalog_complete",
        "structural_catalog_pass": True,
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "freezing_credit": False,
        "state_sha256": state.state_sha256,
        "production_leaf_catalog_sha256": forest.audit[
            "leaf_catalog_sha256"
        ],
        "production_maximum_level": PRODUCTION_MAXIMUM_LEVEL,
        "shadow_maximum_level": SHADOW_MAXIMUM_LEVEL,
        "level_two_leaf_count": len(level_two),
        "periodic_orbit_count": len(orbits),
        "periodic_multi_leaf_orbit_count": sum(
            len(orbit.leaf_keys) > 1 for orbit in orbits
        ),
        "all_level_two_leaves_partitioned_once": True,
        "periodic_orbits_complete": True,
        "production_plan_mutated": False,
        "production_level_three_selectable": False,
        "production_level_three_rows_numbered": False,
        "stage4_production_plan_supports_level_three": False,
        "shadow_forest_supports_level_three": True,
        "orbit_catalog_sha256": _json_sha256(orbit_payload),
    }
    audit_payload["catalog_sha256"] = _json_sha256(audit_payload)
    return HLevel3SaturationCatalog(
        state_sha256=state.state_sha256,
        level_two_leaf_keys=level_two,
        periodic_orbits=tuple(orbits),
        audit=MappingProxyType(audit_payload),
    )


def _validate_catalog(
    state: HPTransitionState,
    catalog: HLevel3SaturationCatalog,
) -> None:
    if not isinstance(catalog, HLevel3SaturationCatalog):
        raise ValueError("h-saturation catalog has the wrong type")
    closed = dict(catalog.audit)
    digest = closed.pop("catalog_sha256", None)
    if digest != _json_sha256(closed):
        raise ValueError("h-saturation catalog identity drifted")
    expected = build_level3_h_saturation_catalog(state)
    if (
        catalog.state_sha256 != expected.state_sha256
        or catalog.level_two_leaf_keys != expected.level_two_leaf_keys
        or catalog.periodic_orbits != expected.periodic_orbits
        or dict(catalog.audit) != dict(expected.audit)
    ):
        raise ValueError("h-saturation catalog is not the canonical state catalog")


@dataclass(frozen=True, slots=True)
class HLevel3ShadowPatch:
    """One real level-three dyadic forest, excluded from production."""

    orbit: HLevel3PeriodicOrbit
    forest: BalancedDyadicHexForest
    cell_degree_by_key: Mapping[DyadicHexKey, int]
    requested_split_keys: tuple[DyadicHexKey, ...]
    closure_split_keys: tuple[DyadicHexKey, ...]
    removed_leaf_keys: tuple[DyadicHexKey, ...]
    added_leaf_keys: tuple[DyadicHexKey, ...]
    level_three_leaf_keys: tuple[DyadicHexKey, ...]
    audit: Mapping[str, Any]


def build_level3_h_saturation_patch(
    state: HPTransitionState,
    catalog: HLevel3SaturationCatalog,
    *,
    orbit_id: str,
) -> HLevel3ShadowPatch:
    """Refine one complete periodic orbit into a real level-three shadow."""

    forest, degrees = _state_gate(state)
    _validate_catalog(state, catalog)
    matches = tuple(
        orbit
        for orbit in catalog.periodic_orbits
        if orbit.orbit_id == str(orbit_id)
    )
    if len(matches) != 1:
        raise ValueError("h-saturation orbit_id is absent or ambiguous")
    orbit = matches[0]
    requested = orbit.leaf_keys
    if any(key.level != PRODUCTION_MAXIMUM_LEVEL for key in requested):
        raise RuntimeError("h-saturation orbit contains a non-level-two leaf")

    enriched = refine_balanced_dyadic_hexa_forest(
        forest,
        requested,
        maximum_level=SHADOW_MAXIMUM_LEVEL,
    )
    before = set(forest.leaf_by_key)
    after = set(enriched.leaf_by_key)
    removed = tuple(sorted(before - after))
    added = tuple(sorted(after - before))
    closure = tuple(sorted(set(removed) - set(requested)))
    level_three = tuple(
        key for key in added if key.level == SHADOW_MAXIMUM_LEVEL
    )
    expected_children = {
        child for key in requested for child in key.children()
    }
    if not expected_children.issubset(level_three):
        raise RuntimeError("selected level-two leaves lack level-three children")
    if not level_three:
        raise RuntimeError("h-saturation shadow created no level-three leaves")

    shadow_degrees: dict[DyadicHexKey, int] = {}
    for cell in enriched.leaves:
        key = cell.key
        if key in degrees:
            shadow_degrees[key] = int(degrees[key])
            continue
        parent = DyadicHexKey(
            key.root,
            key.level - 1,
            key.i // 2,
            key.j // 2,
            key.k // 2,
        )
        try:
            shadow_degrees[key] = int(degrees[parent])
        except KeyError as exc:
            raise RuntimeError(
                "one shadow child has no production parent degree"
            ) from exc
    if set(shadow_degrees) != after:
        raise RuntimeError("level-three shadow degree inheritance is incomplete")

    blockers = (
        "stage4_production_plan_rejects_maximum_level_3",
        "level3_patch_hcurl_constraints_not_materialized",
        "level3_patch_compiled_tensor_not_supplied",
        "level3_patch_59_goal_adjoints_not_supplied",
        "level3_global_shadow_endpoint_not_solved",
    )
    degree_payload = [
        {
            "key": _key_row(key),
            "degree": shadow_degrees[key],
        }
        for key in sorted(shadow_degrees)
    ]
    audit_payload: dict[str, Any] = {
        "schema_version": H_SATURATION_PATCH_SCHEMA,
        "status": "h_saturation_geometry_complete_algebra_unknown",
        "structural_geometry_pass": True,
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "freezing_credit": False,
        "state_sha256": state.state_sha256,
        "catalog_sha256": catalog.audit["catalog_sha256"],
        "orbit_id": orbit.orbit_id,
        "orbit_sha256": orbit.orbit_sha256,
        "production_leaf_catalog_sha256": forest.audit[
            "leaf_catalog_sha256"
        ],
        "shadow_leaf_catalog_sha256": enriched.audit[
            "leaf_catalog_sha256"
        ],
        "shadow_hanging_face_catalog_sha256": enriched.audit[
            "hanging_face_catalog_sha256"
        ],
        "shadow_cell_degree_plan_sha256": _json_sha256(degree_payload),
        "production_maximum_level": PRODUCTION_MAXIMUM_LEVEL,
        "shadow_maximum_level": SHADOW_MAXIMUM_LEVEL,
        "requested_split_keys": [_key_row(key) for key in requested],
        "closure_split_keys": [_key_row(key) for key in closure],
        "removed_leaf_keys": [_key_row(key) for key in removed],
        "added_leaf_keys": [_key_row(key) for key in added],
        "level_three_leaf_keys": [_key_row(key) for key in level_three],
        "pre_leaf_count": len(before),
        "post_leaf_count": len(after),
        "net_added_leaf_count": len(after) - len(before),
        "strong_2_to_1_balance": enriched.audit[
            "strong_2_to_1_balance"
        ],
        "maximum_adjacent_level_jump": enriched.audit[
            "maximum_adjacent_level_jump"
        ],
        "periodic_boundary_audit": dict(
            enriched.audit["periodic_boundary_audit"]
        ),
        "material_interface_hanging_face_count": enriched.audit[
            "material_interface_hanging_face_count"
        ],
        "true_dyadic_level_three_children": True,
        "complete_parent_degree_inheritance": True,
        "shadow_only": True,
        "production_plan_mutated": False,
        "production_level_three_selectable": False,
        "production_level_three_rows_numbered": False,
        "shadow_trace_rows_numbered_in_production": False,
        "mesh_contract_complete": True,
        "constraint_contract_complete": False,
        "tensor_contract_complete": False,
        "local_schur_contract_complete": False,
        "goal_count_required": FORMAL_GOAL_COUNT,
        "dwr_contract_complete": False,
        "structural_blockers": list(blockers),
    }
    audit_payload["patch_sha256"] = _json_sha256(audit_payload)
    return HLevel3ShadowPatch(
        orbit=orbit,
        forest=enriched,
        cell_degree_by_key=MappingProxyType(shadow_degrees),
        requested_split_keys=requested,
        closure_split_keys=closure,
        removed_leaf_keys=removed,
        added_leaf_keys=added,
        level_three_leaf_keys=level_three,
        audit=MappingProxyType(audit_payload),
    )


def _validate_patch(patch: HLevel3ShadowPatch) -> None:
    if not isinstance(patch, HLevel3ShadowPatch):
        raise ValueError("level3 shadow patch has the wrong type")
    closed = dict(patch.audit)
    digest = closed.pop("patch_sha256", None)
    if digest != _json_sha256(closed):
        raise ValueError("level3 shadow patch identity drifted")
    if (
        patch.forest.audit.get("pass") is not True
        or patch.forest.audit.get("leaf_catalog_sha256")
        != patch.audit.get("shadow_leaf_catalog_sha256")
        or set(patch.cell_degree_by_key) != set(patch.forest.leaf_by_key)
        or any(
            value not in {4, 5, 6}
            for value in patch.cell_degree_by_key.values()
        )
        or not patch.level_three_leaf_keys
        or any(key.level != SHADOW_MAXIMUM_LEVEL for key in patch.level_three_leaf_keys)
        or patch.audit.get("production_level_three_selectable") is not False
        or patch.audit.get("production_level_three_rows_numbered") is not False
    ):
        raise ValueError("level3 shadow patch structure drifted")


@dataclass(frozen=True, slots=True)
class HLevel3ConstraintEvidence:
    """Actual shadow-only hanging/Floquet rows on one level-three patch."""

    carrier: Any
    trace_authority: Any
    audit: Mapping[str, Any]


def materialize_level3_h_saturation_constraints(
    patch: HLevel3ShadowPatch,
    *,
    phase_x: complex,
    phase_y: complex,
    comm: Any = None,
) -> HLevel3ConstraintEvidence:
    """Build actual H(curl) shadow constraints without production numbering."""

    from mpi4py import MPI

    from .dyadic_hexa_broken_mesh import (
        build_broken_dyadic_hexa_carrier,
    )
    from .hcurl_broken_trace_graph import (
        build_broken_hexa_trace_constraint_authority,
    )

    _validate_patch(patch)
    if patch.audit.get("structural_geometry_pass") is not True:
        raise ValueError("level3 patch geometry has not passed")
    communicator = MPI.COMM_WORLD if comm is None else comm
    carrier = build_broken_dyadic_hexa_carrier(
        patch.forest,
        comm=communicator,
    )
    degree_by_box = {
        cell.box: int(patch.cell_degree_by_key[cell.key])
        for cell in patch.forest.leaves
    }
    authority = build_broken_hexa_trace_constraint_authority(
        patch.forest,
        carrier,
        degree=6,
        phase_x=complex(phase_x),
        phase_y=complex(phase_y),
        cell_degree_by_box=degree_by_box,
    )
    if carrier.audit.get("pass") is not True:
        raise RuntimeError("level3 shadow carrier did not pass")
    if authority.audit.get("pass") is not True:
        raise RuntimeError("level3 shadow trace constraints did not pass")
    audit_payload: dict[str, Any] = {
        "schema_version": H_SATURATION_CONSTRAINT_SCHEMA,
        "status": "level3_shadow_hcurl_constraints_complete",
        "structural_constraint_pass": True,
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "freezing_credit": False,
        "patch_sha256": patch.audit["patch_sha256"],
        "shadow_leaf_catalog_sha256": patch.audit[
            "shadow_leaf_catalog_sha256"
        ],
        "carrier_leaf_catalog_sha256": carrier.audit[
            "leaf_catalog_sha256"
        ],
        "physical_authority_sha256": authority.audit[
            "physical_authority_sha256"
        ],
        "hanging_relation_count": len(authority.hanging_relations),
        "periodic_relation_count": len(authority.periodic_relations),
        "independent_physical_trace_rows": authority.audit[
            "independent_trace_rows"
        ],
        "variable_trace_opt_in": authority.audit[
            "variable_trace_opt_in"
        ],
        "periodic_cycle_closure": authority.audit["checks"][
            "periodic_cycle_closure"
        ],
        "hanging_constraints_complete": authority.audit["checks"][
            "all_hanging_patches_have_relations"
        ],
        "shadow_only": True,
        "production_plan_mutated": False,
        "production_rows_numbered": False,
        "tensor_contract_complete": False,
        "dwr_contract_complete": False,
        "remaining_structural_blockers": [
            "stage4_production_plan_rejects_maximum_level_3",
            "level3_patch_compiled_tensor_not_supplied",
            "level3_patch_59_goal_adjoints_not_supplied",
            "level3_global_shadow_endpoint_not_solved",
        ],
    }
    audit_payload["constraint_evidence_sha256"] = _json_sha256(
        audit_payload
    )
    return HLevel3ConstraintEvidence(
        carrier=carrier,
        trace_authority=authority,
        audit=MappingProxyType(audit_payload),
    )


def _validate_constraints(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
) -> None:
    _validate_patch(patch)
    if not isinstance(constraints, HLevel3ConstraintEvidence):
        raise ValueError("level3 constraint evidence has the wrong type")
    closed = dict(constraints.audit)
    digest = closed.pop("constraint_evidence_sha256", None)
    if digest != _json_sha256(closed):
        raise ValueError("level3 constraint evidence identity drifted")
    if (
        constraints.audit.get("patch_sha256")
        != patch.audit.get("patch_sha256")
        or constraints.audit.get("structural_constraint_pass") is not True
        or constraints.carrier.audit.get("pass") is not True
        or constraints.trace_authority.audit.get("pass") is not True
        or constraints.trace_authority.audit.get("physical_authority_sha256")
        != constraints.audit.get("physical_authority_sha256")
    ):
        raise ValueError("level3 constraint evidence structure drifted")


@dataclass(frozen=True, slots=True)
class HLevel3LocalGoalLowerBound:
    """One local signed DWR value; it has no global stopping credit."""

    goal_id: str
    signed_dwr: float
    local_endpoint_delta: float
    algebraic_difference: float


@dataclass(frozen=True, slots=True)
class HLevel3LocalLowerBound:
    """Local child-restriction/Schur/adjoint evidence for one patch."""

    goals: tuple[HLevel3LocalGoalLowerBound, ...]
    trace_schur: np.ndarray
    trace_condensed_residual: np.ndarray
    local_correction: np.ndarray
    audit: Mapping[str, Any]


def _complex_matrix(values: Any, *, label: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 2 or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be one finite complex matrix")
    return result


def _complex_vector(values: Any, *, label: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim != 1 or not np.all(np.isfinite(result)):
        raise ValueError(f"{label} must be one finite complex vector")
    return result


def _index_partition(
    trace_dofs: Sequence[int],
    interior_dofs: Sequence[int],
    *,
    size: int,
) -> tuple[np.ndarray, np.ndarray]:
    trace = np.asarray(trace_dofs, dtype=np.int64)
    interior = np.asarray(interior_dofs, dtype=np.int64)
    if trace.ndim != 1 or interior.ndim != 1:
        raise ValueError("trace/interior dofs must be one-dimensional")
    combined = np.concatenate((trace, interior))
    if (
        len(trace) == 0
        or len(interior) == 0
        or len(combined) != size
        or np.any(combined < 0)
        or np.any(combined >= size)
        or len(set(map(int, combined))) != size
    ):
        raise ValueError(
            "trace/interior dofs must partition every local shadow row"
        )
    return trace, interior


def evaluate_level3_h_saturation_local_lower_bound(
    patch: HLevel3ShadowPatch,
    constraints: HLevel3ConstraintEvidence,
    *,
    goal_ids: Sequence[str],
    shadow_matrix: Any,
    shadow_rhs: Any,
    production_embedding: Any,
    production_coefficients: Any,
    goal_gradients: Any,
    trace_dofs: Sequence[int],
    interior_dofs: Sequence[int],
    tolerance: float = _ALGEBRA_TOLERANCE,
) -> HLevel3LocalLowerBound:
    """Evaluate a local 59-goal lower bound with exact Schur replay.

    The supplied matrix and gradients must be actual patch-local quantities
    for this result to be scientifically useful.  Even then, omitted global
    coupling means the result remains a lower-bound diagnostic and cannot
    change the formal saturation state from ``unknown``.
    """

    _validate_constraints(patch, constraints)
    ids = tuple(map(str, goal_ids))
    if len(ids) != FORMAL_GOAL_COUNT or len(set(ids)) != len(ids):
        raise ValueError("local h-saturation requires 59 unique goal IDs")
    if float(tolerance) <= 0.0:
        raise ValueError("local h-saturation tolerance must be positive")

    matrix = _complex_matrix(shadow_matrix, label="shadow matrix")
    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError("shadow matrix must be square")
    size = matrix.shape[0]
    rhs = _complex_vector(shadow_rhs, label="shadow RHS")
    embedding = _complex_matrix(
        production_embedding,
        label="production embedding",
    )
    coefficients = _complex_vector(
        production_coefficients,
        label="production coefficients",
    )
    gradients = _complex_matrix(
        goal_gradients,
        label="goal gradients",
    )
    if (
        rhs.shape != (size,)
        or embedding.shape[0] != size
        or embedding.shape[1] != len(coefficients)
        or gradients.shape != (FORMAL_GOAL_COUNT, size)
    ):
        raise ValueError("local h-saturation array shapes are inconsistent")
    if np.linalg.matrix_rank(embedding) != embedding.shape[1]:
        raise ValueError("production embedding is not full column rank")
    trace, interior = _index_partition(
        trace_dofs,
        interior_dofs,
        size=size,
    )

    embedded = embedding @ coefficients
    residual = rhs - matrix @ embedded
    matrix_tt = matrix[np.ix_(trace, trace)]
    matrix_ti = matrix[np.ix_(trace, interior)]
    matrix_it = matrix[np.ix_(interior, trace)]
    matrix_ii = matrix[np.ix_(interior, interior)]
    residual_t = residual[trace]
    residual_i = residual[interior]
    ii_inverse_it = np.linalg.solve(matrix_ii, matrix_it)
    ii_inverse_ri = np.linalg.solve(matrix_ii, residual_i)
    schur = matrix_tt - matrix_ti @ ii_inverse_it
    condensed_residual = residual_t - matrix_ti @ ii_inverse_ri
    trace_delta = np.linalg.solve(schur, condensed_residual)
    interior_delta = np.linalg.solve(
        matrix_ii,
        residual_i - matrix_it @ trace_delta,
    )
    correction = np.empty(size, dtype=np.complex128)
    correction[trace] = trace_delta
    correction[interior] = interior_delta
    full_correction = np.linalg.solve(matrix, residual)
    schur_replay_error = float(
        np.max(np.abs(correction - full_correction), initial=0.0)
    )
    residual_replay_error = float(
        np.max(
            np.abs(matrix @ correction - residual),
            initial=0.0,
        )
    )
    adjoints = np.linalg.solve(matrix.conj().T, gradients.T)
    signed_dwr = np.real(np.conj(adjoints).T @ residual)
    endpoint = np.real(np.conj(gradients) @ correction)
    difference = np.abs(signed_dwr - endpoint)
    maximum_dwr_difference = float(np.max(difference, initial=0.0))
    algebraic_pass = (
        schur_replay_error <= float(tolerance)
        and residual_replay_error <= float(tolerance)
        and maximum_dwr_difference <= float(tolerance)
    )
    if not algebraic_pass:
        raise RuntimeError(
            "local h-saturation Schur/DWR replay exceeds tolerance"
        )

    goals = tuple(
        HLevel3LocalGoalLowerBound(
            goal_id=goal_id,
            signed_dwr=float(estimate),
            local_endpoint_delta=float(observed),
            algebraic_difference=float(error),
        )
        for goal_id, estimate, observed, error in zip(
            ids,
            signed_dwr,
            endpoint,
            difference,
            strict=True,
        )
    )
    audit_payload: dict[str, Any] = {
        "schema_version": H_SATURATION_LOWER_BOUND_SCHEMA,
        "status": "measured_local_patch_lower_bound_only",
        "local_algebra_pass": True,
        "formal_h_saturation_status": "unknown",
        "measured_pass": False,
        "freezing_credit": False,
        "patch_sha256": patch.audit["patch_sha256"],
        "constraint_evidence_sha256": constraints.audit[
            "constraint_evidence_sha256"
        ],
        "goal_count": len(goals),
        "production_embedding_rank": int(
            np.linalg.matrix_rank(embedding)
        ),
        "production_embedding_columns": embedding.shape[1],
        "shadow_local_rows": size,
        "trace_rows": len(trace),
        "interior_rows": len(interior),
        "schur_rows": schur.shape[0],
        "schur_replay_error": schur_replay_error,
        "residual_replay_error": residual_replay_error,
        "maximum_dwr_endpoint_difference": maximum_dwr_difference,
        "algebra_tolerance": float(tolerance),
        "matrix_sha256": _array_sha256(matrix),
        "rhs_sha256": _array_sha256(rhs),
        "production_embedding_sha256": _array_sha256(embedding),
        "production_coefficients_sha256": _array_sha256(coefficients),
        "goal_gradients_sha256": _array_sha256(gradients),
        "trace_schur_sha256": _array_sha256(schur),
        "signed_dwr_sha256": _array_sha256(
            np.asarray(signed_dwr, dtype=np.float64)
        ),
        "actual_patch_local_tensor_consumed": True,
        "actual_patch_local_adjoints_solved": True,
        "global_shadow_coupling_included": False,
        "global_shadow_endpoint_solved": False,
        "production_plan_mutated": False,
        "production_level_three_rows_numbered": False,
        "remaining_structural_blockers": [
            "stage4_production_plan_rejects_maximum_level_3",
            "level3_global_shadow_coupling_not_included",
            "level3_global_shadow_endpoint_not_solved",
        ],
    }
    audit_payload["lower_bound_sha256"] = _json_sha256(audit_payload)
    schur.setflags(write=False)
    condensed_residual.setflags(write=False)
    correction.setflags(write=False)
    return HLevel3LocalLowerBound(
        goals=goals,
        trace_schur=schur,
        trace_condensed_residual=condensed_residual,
        local_correction=correction,
        audit=MappingProxyType(audit_payload),
    )


__all__ = [
    "FORMAL_GOAL_COUNT",
    "HLevel3ConstraintEvidence",
    "HLevel3LocalGoalLowerBound",
    "HLevel3LocalLowerBound",
    "HLevel3PeriodicOrbit",
    "HLevel3SaturationCatalog",
    "HLevel3ShadowPatch",
    "H_SATURATION_CATALOG_SCHEMA",
    "H_SATURATION_CONSTRAINT_SCHEMA",
    "H_SATURATION_LOWER_BOUND_SCHEMA",
    "H_SATURATION_PATCH_SCHEMA",
    "PRODUCTION_MAXIMUM_LEVEL",
    "SHADOW_MAXIMUM_LEVEL",
    "build_level3_h_saturation_catalog",
    "build_level3_h_saturation_patch",
    "evaluate_level3_h_saturation_local_lower_bound",
    "materialize_level3_h_saturation_constraints",
]
