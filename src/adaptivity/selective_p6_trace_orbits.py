"""Pure data layer for periodic-closed selective p6 trace shells.

This module does not inspect a DOLFINx mesh and does not assemble a matrix.
Callers provide explicit physical edge/face identities, already computed
entity transformations, and periodic mate relations.  The resulting active
numbering therefore has two useful fail-closed properties:

* selection is possible only in complete periodic orbits;
* inactive missing-p6 modes never receive active row numbers.

The p5-to-p6 missing shell contains one mode per hexahedral edge and twenty
modes per hexahedral face.  Full3D-equivalent cost counts every selected
physical entity, while active-row cost counts one representative per periodic
orbit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

import numpy as np


MissingTraceEntityKind = Literal["edge", "face"]
PeriodicDirection = Literal["x", "y", "corner"]

_MISSING_P6_MODES = {"edge": 1, "face": 20}
_DIRECTION_ORDER = {"x": 0, "y": 1, "corner": 2}


def _relative_matrix_error(left: np.ndarray, right: np.ndarray) -> float:
    left_array = np.asarray(left, dtype=np.complex128)
    right_array = np.asarray(right, dtype=np.complex128)
    difference = float(np.linalg.norm(left_array - right_array, ord="fro"))
    scale = max(
        1.0,
        float(np.linalg.norm(left_array, ord="fro")),
        float(np.linalg.norm(right_array, ord="fro")),
    )
    return difference / scale


def _readonly_complex_matrix(
    values: np.ndarray,
    *,
    label: str,
) -> np.ndarray:
    matrix = np.array(values, dtype=np.complex128, copy=True)
    if matrix.ndim != 2:
        raise ValueError(f"{label} must be a matrix")
    if not np.all(np.isfinite(matrix)):
        raise FloatingPointError(f"{label} contains NaN or Inf")
    matrix.setflags(write=False)
    return matrix


def _validate_nonsingular(
    matrix: np.ndarray,
    *,
    label: str,
    tolerance: float,
) -> float:
    if matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
        raise ValueError(f"{label} must be nonempty and square")
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    maximum = float(np.max(singular_values))
    minimum = float(np.min(singular_values))
    if (
        not np.all(np.isfinite(singular_values))
        or maximum <= 0.0
        or minimum <= tolerance * maximum
    ):
        raise ValueError(f"{label} is numerically singular")
    return maximum / minimum


@dataclass(frozen=True)
class MissingTraceIntertwiningProjection:
    """Validated restriction of an enriched transform to the missing shell."""

    enriched_dimension: int
    retained_dimension: int
    missing_dimension: int
    induced_missing_transform: np.ndarray
    direct_sum_condition_number: float
    enriched_transform_condition_number: float
    missing_transform_condition_number: float
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        matrix = _readonly_complex_matrix(
            self.induced_missing_transform,
            label="induced missing transform",
        )
        if matrix.shape != (
            int(self.missing_dimension),
            int(self.missing_dimension),
        ):
            raise ValueError(
                "induced missing transform shape disagrees with its dimension"
            )
        if self.audit.get("pass") is not True:
            raise ValueError("intertwining projection audit did not pass")
        object.__setattr__(self, "induced_missing_transform", matrix)


def validate_missing_trace_intertwining(
    *,
    enriched_transform: np.ndarray,
    retained_transform: np.ndarray,
    retained_embedding: np.ndarray,
    missing_embedding: np.ndarray,
    expected_missing_transform: np.ndarray | None = None,
    tolerance: float = 5.0e-12,
) -> MissingTraceIntertwiningProjection:
    """Project one full entity transform onto an invariant missing shell.

    ``retained_embedding`` and ``missing_embedding`` must form a square,
    nonsingular change of coordinates for the enriched entity space.  Both
    subspaces must be invariant.  Any retained-to-missing or
    missing-to-retained leakage is a hard error rather than a dropped block.
    """

    tolerance = float(tolerance)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("intertwining tolerance must be positive and finite")

    enriched = _readonly_complex_matrix(
        enriched_transform,
        label="enriched entity transform",
    )
    retained = _readonly_complex_matrix(
        retained_transform,
        label="retained entity transform",
    )
    retained_map = _readonly_complex_matrix(
        retained_embedding,
        label="retained embedding",
    )
    missing_map = _readonly_complex_matrix(
        missing_embedding,
        label="missing embedding",
    )
    if enriched.shape[0] != enriched.shape[1] or enriched.shape[0] == 0:
        raise ValueError("enriched entity transform must be nonempty and square")
    enriched_dimension = int(enriched.shape[0])
    if retained.shape[0] != retained.shape[1] or retained.shape[0] == 0:
        raise ValueError("retained entity transform must be nonempty and square")
    retained_dimension = int(retained.shape[0])
    if retained_map.shape != (enriched_dimension, retained_dimension):
        raise ValueError("retained embedding has the wrong shape")
    if missing_map.shape[0] != enriched_dimension:
        raise ValueError("missing embedding has the wrong row count")
    missing_dimension = int(missing_map.shape[1])
    if missing_dimension <= 0:
        raise ValueError("missing embedding must contain at least one mode")
    if retained_dimension + missing_dimension != enriched_dimension:
        raise ValueError(
            "retained and missing dimensions do not close the enriched space"
        )

    direct_sum = np.concatenate((retained_map, missing_map), axis=1)
    direct_sum_condition = _validate_nonsingular(
        direct_sum,
        label="retained/missing direct sum",
        tolerance=tolerance,
    )
    enriched_condition = _validate_nonsingular(
        enriched,
        label="enriched entity transform",
        tolerance=tolerance,
    )
    transformed_coordinates = np.linalg.solve(
        direct_sum,
        enriched @ direct_sum,
    )
    retained_stop = retained_dimension
    observed_retained = transformed_coordinates[
        :retained_stop, :retained_stop
    ]
    retained_to_missing = transformed_coordinates[
        retained_stop:, :retained_stop
    ]
    missing_to_retained = transformed_coordinates[
        :retained_stop, retained_stop:
    ]
    induced_missing = transformed_coordinates[
        retained_stop:, retained_stop:
    ]
    missing_condition = _validate_nonsingular(
        induced_missing,
        label="induced missing transform",
        tolerance=tolerance,
    )

    retained_intertwining_error = _relative_matrix_error(
        enriched @ retained_map,
        retained_map @ retained,
    )
    retained_coordinate_error = _relative_matrix_error(
        observed_retained,
        retained,
    )
    retained_to_missing_leakage = _relative_matrix_error(
        retained_to_missing,
        np.zeros_like(retained_to_missing),
    )
    missing_to_retained_leakage = _relative_matrix_error(
        missing_to_retained,
        np.zeros_like(missing_to_retained),
    )
    missing_intertwining_error = _relative_matrix_error(
        enriched @ missing_map,
        missing_map @ induced_missing,
    )
    expected_error = 0.0
    if expected_missing_transform is not None:
        expected = _readonly_complex_matrix(
            expected_missing_transform,
            label="expected missing transform",
        )
        if expected.shape != induced_missing.shape:
            raise ValueError("expected missing transform has the wrong shape")
        expected_error = _relative_matrix_error(induced_missing, expected)

    checks = {
        "direct_sum_full_rank": True,
        "enriched_transform_nonsingular": True,
        "retained_transform_intertwines": (
            retained_intertwining_error <= tolerance
        ),
        "retained_coordinate_block_matches": (
            retained_coordinate_error <= tolerance
        ),
        "retained_into_missing_leakage_absent": (
            retained_to_missing_leakage <= tolerance
        ),
        "missing_into_retained_leakage_absent": (
            missing_to_retained_leakage <= tolerance
        ),
        "missing_transform_intertwines": (
            missing_intertwining_error <= tolerance
        ),
        "expected_missing_transform_matches": (
            expected_missing_transform is None
            or expected_error <= tolerance
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "missing-trace intertwining projection failed: "
            + ", ".join(failed)
        )

    induced_missing = np.array(
        induced_missing,
        dtype=np.complex128,
        copy=True,
    )
    induced_missing.setflags(write=False)
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.missing-p6-trace-intertwining-projection.v1"
            ),
            "status": "missing_trace_intertwining_projection_pass",
            "pass": True,
            "enriched_dimension": enriched_dimension,
            "retained_dimension": retained_dimension,
            "missing_dimension": missing_dimension,
            "direct_sum_condition_number": direct_sum_condition,
            "enriched_transform_condition_number": enriched_condition,
            "missing_transform_condition_number": missing_condition,
            "retained_intertwining_relative_error": (
                retained_intertwining_error
            ),
            "retained_coordinate_relative_error": retained_coordinate_error,
            "retained_into_missing_leakage_relative_error": (
                retained_to_missing_leakage
            ),
            "missing_into_retained_leakage_relative_error": (
                missing_to_retained_leakage
            ),
            "missing_intertwining_relative_error": (
                missing_intertwining_error
            ),
            "expected_missing_transform_relative_error": expected_error,
            "checks": checks,
            "fail_closed_on_cross_subspace_leakage": True,
            "ordinary_default_changed": False,
        }
    )
    return MissingTraceIntertwiningProjection(
        enriched_dimension=enriched_dimension,
        retained_dimension=retained_dimension,
        missing_dimension=missing_dimension,
        induced_missing_transform=induced_missing,
        direct_sum_condition_number=direct_sum_condition,
        enriched_transform_condition_number=enriched_condition,
        missing_transform_condition_number=missing_condition,
        audit=audit,
    )


@dataclass(frozen=True)
class MissingP6TraceEntity:
    """One physical mesh entity carrying the p5-to-p6 missing shell."""

    entity_id: int
    entity_kind: MissingTraceEntityKind
    missing_mode_count: int
    required_periodic_directions: tuple[PeriodicDirection, ...] = ()

    def __post_init__(self) -> None:
        entity_id = int(self.entity_id)
        if entity_id < 0:
            raise ValueError("missing-trace entity id must be nonnegative")
        if self.entity_kind not in _MISSING_P6_MODES:
            raise ValueError(
                f"unsupported missing-trace entity kind {self.entity_kind!r}"
            )
        expected = _MISSING_P6_MODES[self.entity_kind]
        if int(self.missing_mode_count) != expected:
            raise ValueError(
                f"p5-to-p6 {self.entity_kind} shell must have "
                f"{expected} modes"
            )
        directions = tuple(self.required_periodic_directions)
        if len(set(directions)) != len(directions):
            raise ValueError("periodic direction requirements are duplicated")
        if any(direction not in _DIRECTION_ORDER for direction in directions):
            raise ValueError("unsupported periodic direction requirement")
        normalized = tuple(
            sorted(directions, key=_DIRECTION_ORDER.__getitem__)
        )
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "missing_mode_count", expected)
        object.__setattr__(
            self,
            "required_periodic_directions",
            normalized,
        )

    @property
    def full3d_equivalent_dof_cost(self) -> int:
        return int(self.missing_mode_count)


@dataclass(frozen=True)
class PeriodicMissingTraceRelation:
    """A directed relation ``slave = phase * T_missing * master``."""

    slave_entity_id: int
    master_entity_id: int
    direction: PeriodicDirection
    intertwining_projection: MissingTraceIntertwiningProjection
    floquet_phase: complex = 1.0 + 0.0j
    phase_tolerance: float = 5.0e-12
    coefficient_pullback: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        slave = int(self.slave_entity_id)
        master = int(self.master_entity_id)
        if slave < 0 or master < 0:
            raise ValueError("periodic entity ids must be nonnegative")
        if slave == master:
            raise ValueError("periodic relation cannot pair an entity to itself")
        if self.direction not in _DIRECTION_ORDER:
            raise ValueError(f"unsupported periodic direction {self.direction!r}")
        if self.intertwining_projection.audit.get("pass") is not True:
            raise ValueError("periodic relation projection is unqualified")
        tolerance = float(self.phase_tolerance)
        if not np.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("phase tolerance must be positive and finite")
        phase = complex(self.floquet_phase)
        if not np.isfinite(phase.real) or not np.isfinite(phase.imag):
            raise FloatingPointError("Floquet phase contains NaN or Inf")
        if abs(abs(phase) - 1.0) > tolerance:
            raise ValueError("Floquet phase must have unit magnitude")
        pullback = np.array(
            phase
            * self.intertwining_projection.induced_missing_transform,
            dtype=np.complex128,
            copy=True,
        )
        _validate_nonsingular(
            pullback,
            label="periodic missing-trace pullback",
            tolerance=tolerance,
        )
        pullback.setflags(write=False)
        object.__setattr__(self, "slave_entity_id", slave)
        object.__setattr__(self, "master_entity_id", master)
        object.__setattr__(self, "floquet_phase", phase)
        object.__setattr__(self, "phase_tolerance", tolerance)
        object.__setattr__(self, "coefficient_pullback", pullback)


@dataclass(frozen=True)
class PeriodicP6TraceOrbit:
    """One transitive periodic orbit and its representative numbering."""

    representative_entity_id: int
    member_entity_ids: tuple[int, ...]
    entity_kind: MissingTraceEntityKind
    missing_mode_count: int
    representative_to_member_pullbacks: Mapping[int, np.ndarray]
    selected: bool
    active_row_start: int | None
    active_row_stop: int | None

    @property
    def full3d_equivalent_dof_cost(self) -> int:
        return len(self.member_entity_ids) * int(self.missing_mode_count)

    @property
    def active_row_cost(self) -> int:
        return int(self.missing_mode_count) if self.selected else 0


@dataclass(frozen=True)
class SelectiveP6TraceNumbering:
    """Periodic-closed active numbering and two distinct DoF costs."""

    entities: tuple[MissingP6TraceEntity, ...]
    orbits: tuple[PeriodicP6TraceOrbit, ...]
    selected_entity_ids: tuple[int, ...]
    inactive_entity_ids: tuple[int, ...]
    entity_to_representative: Mapping[int, int]
    entity_active_row_ranges: Mapping[int, tuple[int, int]]
    full3d_base_dofs: int
    active_base_rows: int
    full3d_equivalent_increment: int
    active_row_increment: int
    full3d_equivalent_dofs: int
    active_rows: int
    full3d_dof_limit: int | None
    audit: Mapping[str, Any]


def _freeze_pullbacks(
    pullbacks: Mapping[int, np.ndarray],
) -> Mapping[int, np.ndarray]:
    frozen: dict[int, np.ndarray] = {}
    for entity_id, values in pullbacks.items():
        matrix = np.array(values, dtype=np.complex128, copy=True)
        matrix.setflags(write=False)
        frozen[int(entity_id)] = matrix
    return MappingProxyType(frozen)


def _discover_orbits(
    entities: tuple[MissingP6TraceEntity, ...],
    relations: tuple[PeriodicMissingTraceRelation, ...],
    *,
    tolerance: float,
) -> tuple[
    list[
        tuple[
            int,
            tuple[int, ...],
            MissingTraceEntityKind,
            int,
            Mapping[int, np.ndarray],
        ]
    ],
    dict[int, int],
]:
    by_id: dict[int, MissingP6TraceEntity] = {}
    for entity in entities:
        if entity.entity_id in by_id:
            raise ValueError(
                f"duplicate missing-trace entity id {entity.entity_id}"
            )
        by_id[entity.entity_id] = entity
    if not by_id:
        return [], {}

    adjacency: dict[int, list[tuple[int, np.ndarray, str]]] = {
        entity_id: [] for entity_id in by_id
    }
    incident_directions: dict[int, set[str]] = {
        entity_id: set() for entity_id in by_id
    }
    relation_keys: set[tuple[int, int, str]] = set()
    for relation in relations:
        key = (
            relation.slave_entity_id,
            relation.master_entity_id,
            relation.direction,
        )
        if key in relation_keys:
            raise ValueError(f"duplicate periodic relation {key}")
        relation_keys.add(key)
        if relation.slave_entity_id not in by_id:
            raise RuntimeError(
                "periodic relation has a missing slave entity mate: "
                f"{relation.slave_entity_id}"
            )
        if relation.master_entity_id not in by_id:
            raise RuntimeError(
                "periodic relation has a missing master entity mate: "
                f"{relation.master_entity_id}"
            )
        slave = by_id[relation.slave_entity_id]
        master = by_id[relation.master_entity_id]
        if (
            slave.entity_kind != master.entity_kind
            or slave.missing_mode_count != master.missing_mode_count
        ):
            raise RuntimeError(
                "periodic relation connects incompatible missing-trace shells"
            )
        if relation.intertwining_projection.missing_dimension != (
            slave.missing_mode_count
        ):
            raise RuntimeError(
                "periodic relation projection dimension disagrees with shell"
            )
        for endpoint in (slave, master):
            if relation.direction not in endpoint.required_periodic_directions:
                raise RuntimeError(
                    "periodic relation direction was not declared by entity "
                    f"{endpoint.entity_id}: {relation.direction}"
                )
        pullback = relation.coefficient_pullback
        inverse = np.linalg.solve(
            pullback,
            np.eye(pullback.shape[0], dtype=np.complex128),
        )
        adjacency[master.entity_id].append(
            (slave.entity_id, pullback, relation.direction)
        )
        adjacency[slave.entity_id].append(
            (master.entity_id, inverse, relation.direction)
        )
        incident_directions[slave.entity_id].add(relation.direction)
        incident_directions[master.entity_id].add(relation.direction)

    for entity in entities:
        missing_directions = set(
            entity.required_periodic_directions
        ) - incident_directions[entity.entity_id]
        if missing_directions:
            raise RuntimeError(
                "missing periodic mate for entity "
                f"{entity.entity_id}: directions={sorted(missing_directions)}"
            )

    visited: set[int] = set()
    discovered: list[
        tuple[
            int,
            tuple[int, ...],
            MissingTraceEntityKind,
            int,
            Mapping[int, np.ndarray],
        ]
    ] = []
    entity_to_representative: dict[int, int] = {}
    for seed in sorted(by_id):
        if seed in visited:
            continue
        stack = [seed]
        component: set[int] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(
                neighbor
                for neighbor, _pullback, _direction in adjacency[current]
            )
        representative = min(component)
        dimension = by_id[representative].missing_mode_count
        transforms: dict[int, np.ndarray] = {
            representative: np.eye(dimension, dtype=np.complex128)
        }
        queue = [representative]
        while queue:
            current = queue.pop(0)
            for neighbor, neighbor_from_current, direction in sorted(
                adjacency[current],
                key=lambda item: (
                    item[0],
                    _DIRECTION_ORDER[item[2]],
                ),
            ):
                candidate = neighbor_from_current @ transforms[current]
                if neighbor not in transforms:
                    transforms[neighbor] = candidate
                    queue.append(neighbor)
                    continue
                error = _relative_matrix_error(
                    transforms[neighbor],
                    candidate,
                )
                if error > tolerance:
                    raise RuntimeError(
                        "periodic corner/cycle pullback is inconsistent: "
                        f"representative={representative}, "
                        f"entity={neighbor}, direction={direction}, "
                        f"relative_error={error:.3e}"
                    )
        if set(transforms) != component:
            raise RuntimeError("periodic orbit traversal did not close")
        members = tuple(sorted(component))
        kind = by_id[representative].entity_kind
        if any(
            by_id[member].entity_kind != kind
            or by_id[member].missing_mode_count != dimension
            for member in members
        ):
            raise RuntimeError("periodic orbit contains incompatible entities")
        frozen = _freeze_pullbacks(transforms)
        discovered.append(
            (representative, members, kind, dimension, frozen)
        )
        for member in members:
            entity_to_representative[member] = representative
        visited.update(component)
    return discovered, entity_to_representative


def build_selective_p6_trace_numbering(
    *,
    entities: Sequence[MissingP6TraceEntity],
    periodic_relations: Sequence[PeriodicMissingTraceRelation],
    selected_entity_ids: Sequence[int],
    full3d_base_dofs: int,
    active_base_rows: int,
    full3d_dof_limit: int | None = None,
    tolerance: float = 5.0e-12,
) -> SelectiveP6TraceNumbering:
    """Build deterministic active rows for a closed set of periodic orbits."""

    tolerance = float(tolerance)
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("orbit tolerance must be positive and finite")
    full3d_base_dofs = int(full3d_base_dofs)
    active_base_rows = int(active_base_rows)
    if full3d_base_dofs < 0 or active_base_rows < 0:
        raise ValueError("base DoF/row counts must be nonnegative")
    if full3d_dof_limit is not None:
        full3d_dof_limit = int(full3d_dof_limit)
        if full3d_dof_limit < 0:
            raise ValueError("Full3D DoF limit must be nonnegative")

    entity_tuple = tuple(entities)
    relation_tuple = tuple(periodic_relations)
    discovered, entity_to_representative = _discover_orbits(
        entity_tuple,
        relation_tuple,
        tolerance=tolerance,
    )
    known_ids = set(entity_to_representative)
    selected_ids = tuple(sorted(map(int, selected_entity_ids)))
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("selected entity ids are duplicated")
    unknown = set(selected_ids) - known_ids
    if unknown:
        raise ValueError(f"selected entity ids are unknown: {sorted(unknown)}")
    selected_set = set(selected_ids)

    for representative, members, _kind, _dimension, _pullbacks in discovered:
        intersection = selected_set.intersection(members)
        if intersection and intersection != set(members):
            raise RuntimeError(
                "selective p6 trace set is not periodic-orbit closed: "
                f"representative={representative}, "
                f"selected={sorted(intersection)}, members={list(members)}"
            )

    active_cursor = active_base_rows
    orbits: list[PeriodicP6TraceOrbit] = []
    active_ranges: dict[int, tuple[int, int]] = {}
    full3d_increment = 0
    active_increment = 0
    for representative, members, kind, dimension, pullbacks in discovered:
        selected = bool(selected_set.intersection(members))
        if selected:
            start = active_cursor
            stop = start + dimension
            active_cursor = stop
            for member in members:
                active_ranges[member] = (start, stop)
            full3d_increment += len(members) * dimension
            active_increment += dimension
        else:
            start = None
            stop = None
        orbits.append(
            PeriodicP6TraceOrbit(
                representative_entity_id=representative,
                member_entity_ids=members,
                entity_kind=kind,
                missing_mode_count=dimension,
                representative_to_member_pullbacks=pullbacks,
                selected=selected,
                active_row_start=start,
                active_row_stop=stop,
            )
        )

    full3d_total = full3d_base_dofs + full3d_increment
    active_total = active_base_rows + active_increment
    inactive = tuple(sorted(known_ids - selected_set))
    selected_orbits = [orbit for orbit in orbits if orbit.selected]
    full3d_within_limit = (
        None
        if full3d_dof_limit is None
        else full3d_total <= full3d_dof_limit
    )
    checks = {
        "unique_physical_entity_ids": True,
        "all_required_periodic_mates_present": True,
        "periodic_pullback_cycles_consistent": True,
        "selection_is_union_of_complete_periodic_orbits": True,
        "selected_entities_have_active_representative_rows": (
            set(active_ranges) == selected_set
        ),
        "inactive_entities_have_no_active_rows": (
            not set(active_ranges).intersection(inactive)
        ),
        "active_row_increment_matches_selected_representatives": (
            active_increment
            == sum(orbit.missing_mode_count for orbit in selected_orbits)
        ),
        "full3d_increment_matches_selected_physical_entities": (
            full3d_increment
            == sum(
                orbit.full3d_equivalent_dof_cost
                for orbit in selected_orbits
            )
        ),
        "candidate_matrix_not_constructed": True,
        "inactive_p6_rows_not_numbered": True,
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "selective p6 trace numbering audit failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.selective-p6-trace-periodic-numbering.v1"
            ),
            "status": "selective_p6_trace_periodic_numbering_pass",
            "pass": True,
            "actual_mesh_entity_independent_data_layer": True,
            "physical_entity_count": len(entity_tuple),
            "periodic_relation_count": len(relation_tuple),
            "periodic_orbit_count": len(orbits),
            "selected_orbit_count": len(selected_orbits),
            "selected_physical_entity_count": len(selected_set),
            "selected_edge_entity_count": sum(
                entity.entity_kind == "edge"
                and entity.entity_id in selected_set
                for entity in entity_tuple
            ),
            "selected_face_entity_count": sum(
                entity.entity_kind == "face"
                and entity.entity_id in selected_set
                for entity in entity_tuple
            ),
            "full3d_base_dofs": full3d_base_dofs,
            "active_base_rows": active_base_rows,
            "full3d_equivalent_increment": full3d_increment,
            "active_row_increment": active_increment,
            "full3d_equivalent_dofs": full3d_total,
            "active_rows": active_total,
            "full3d_dof_limit": full3d_dof_limit,
            "full3d_within_limit": full3d_within_limit,
            "inactive_mode_numbering_policy": "no_active_rows",
            "candidate_matrix_constructed": False,
            "inactive_p6_rows_retained_in_candidate_matrix": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return SelectiveP6TraceNumbering(
        entities=entity_tuple,
        orbits=tuple(orbits),
        selected_entity_ids=selected_ids,
        inactive_entity_ids=inactive,
        entity_to_representative=MappingProxyType(
            dict(entity_to_representative)
        ),
        entity_active_row_ranges=MappingProxyType(dict(active_ranges)),
        full3d_base_dofs=full3d_base_dofs,
        active_base_rows=active_base_rows,
        full3d_equivalent_increment=full3d_increment,
        active_row_increment=active_increment,
        full3d_equivalent_dofs=full3d_total,
        active_rows=active_total,
        full3d_dof_limit=full3d_dof_limit,
        audit=audit,
    )


__all__ = [
    "MissingP6TraceEntity",
    "MissingTraceIntertwiningProjection",
    "PeriodicMissingTraceRelation",
    "PeriodicP6TraceOrbit",
    "SelectiveP6TraceNumbering",
    "build_selective_p6_trace_numbering",
    "validate_missing_trace_intertwining",
]
