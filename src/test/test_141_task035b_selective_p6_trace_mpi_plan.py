"""Pure tests for the owner-aware selective-p6-trace MPI row plan."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np
import pytest

from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
    ExactSequenceClosedP6TraceNumbering,
    build_exact_sequence_closed_p6_trace_numbering,
)
from src.adaptivity.selective_p6_trace_orbits import (
    MissingP6TraceEntity,
    MissingTraceIntertwiningProjection,
    PeriodicMissingTraceRelation,
)
from src.constraints.selective_p6_trace_3d import (
    SelectiveP6TraceMPIRowPlan,
    build_selective_p6_trace_mpi_row_plan,
    canonical_selective_p6_trace_selection_sha256,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _rule(
    *,
    representative: int,
    kind: str,
) -> DiscreteGradientOrbitRule:
    scalar_mode_count = 1 if kind == "edge" else 9
    return DiscreteGradientOrbitRule(
        scalar_orbit_id=f"scalar-{kind}-{representative}",
        anchor_trace_representative_id=representative,
        required_trace_representative_ids=(representative,),
        scalar_mode_count=scalar_mode_count,
        discrete_gradient_rank=scalar_mode_count,
        ordered_scalar_basis_sha256=_digest(
            f"scalar-basis-{kind}-{representative}"
        ),
        ordered_trace_basis_sha256=_digest(
            f"trace-basis-{kind}-{representative}"
        ),
        gradient_map_sha256=_digest(
            f"gradient-map-{kind}-{representative}"
        ),
        periodic_orbit_closed=True,
        discrete_gradient_verified=True,
        gradient_map_binds_ordered_basis_identity=True,
    )


def _projection(dimension: int) -> MissingTraceIntertwiningProjection:
    return MissingTraceIntertwiningProjection(
        enriched_dimension=dimension + 1,
        retained_dimension=1,
        missing_dimension=dimension,
        induced_missing_transform=np.eye(
            dimension,
            dtype=np.complex128,
        ),
        direct_sum_condition_number=1.0,
        enriched_transform_condition_number=1.0,
        missing_transform_condition_number=1.0,
        audit={"pass": True},
    )


def _small_closed(
    *,
    selected_representatives: tuple[int, ...],
) -> ExactSequenceClosedP6TraceNumbering:
    entities = (
        MissingP6TraceEntity(0, "edge", 1),
        MissingP6TraceEntity(1, "face", 20),
    )
    rules = (
        _rule(representative=0, kind="edge"),
        _rule(representative=1, kind="face"),
    )
    return build_exact_sequence_closed_p6_trace_numbering(
        entities=entities,
        periodic_relations=(),
        gradient_rules=rules,
        seed_trace_representative_ids=selected_representatives,
        full3d_base_dofs=100,
        active_base_rows=5,
        full3d_dof_limit=200,
    )


def _selection_hash(
    closed: ExactSequenceClosedP6TraceNumbering,
) -> str:
    return canonical_selective_p6_trace_selection_sha256(
        closed_numbering=closed,
        geometry_key_sha256=_digest("geometry"),
        ordered_trace_basis_sha256=_digest("ordered-trace-basis"),
    )


def _build_small_plan(
    closed: ExactSequenceClosedP6TraceNumbering,
    *,
    owners: dict[int, int],
    selected_counts: tuple[int, int],
) -> SelectiveP6TraceMPIRowPlan:
    return build_selective_p6_trace_mpi_row_plan(
        closed_numbering=closed,
        selected_orbit_owner_ranks=owners,
        owned_base_row_counts_by_rank=(3, 2),
        owned_selected_trace_row_counts_by_rank=selected_counts,
        geometry_key_sha256=_digest("geometry"),
        ordered_trace_basis_sha256=_digest("ordered-trace-basis"),
        selection_sha256=_selection_hash(closed),
        expected_full3d_dof_limit=200,
    )


def test_zero_selected_has_only_base_rows_and_no_trace_descriptors() -> None:
    closed = _small_closed(selected_representatives=())
    plan = _build_small_plan(closed, owners={}, selected_counts=(0, 0))

    assert plan.petsc_ownership_ranges == ((0, 3), (3, 5))
    assert plan.rank_base_row_ranges == ((0, 3), (3, 5))
    assert plan.rank_selected_trace_row_ranges == ((3, 3), (5, 5))
    assert plan.selected_row_descriptors == ()
    assert plan.canonical_logical_orbit_modes == ()
    assert plan.petsc_rows_in_canonical_logical_order == ()
    assert dict(plan.logical_orbit_mode_to_petsc_row) == {}
    assert dict(plan.petsc_row_to_logical_orbit_mode) == {}
    assert plan.full3d_equivalent_increment == 0
    assert plan.quotient_active_increment == 0
    assert plan.actual_mesh is False
    assert plan.audit["inactive_p6_rows_numbered"] is False


def test_all_selected_uses_owned_base_then_whole_owned_orbits() -> None:
    closed = _small_closed(selected_representatives=(0, 1))
    plan = _build_small_plan(
        closed,
        owners={0: 0, 1: 1},
        selected_counts=(1, 20),
    )

    assert plan.petsc_ownership_ranges == ((0, 4), (4, 26))
    assert plan.rank_base_row_ranges == ((0, 3), (4, 6))
    assert plan.rank_selected_trace_row_ranges == ((3, 4), (6, 26))
    assert plan.owned_selected_orbit_representatives_by_rank == ((0,), (1,))
    assert plan.logical_orbit_mode_to_petsc_row[(0, 0)] == 3
    assert plan.logical_orbit_mode_to_petsc_row[(1, 0)] == 6
    assert plan.logical_orbit_mode_to_petsc_row[(1, 19)] == 25
    assert len(plan.selected_row_descriptors) == 21
    assert plan.full3d_equivalent_increment == 21
    assert plan.quotient_active_increment == 21
    assert plan.active_rows == 26
    assert all(plan.audit["checks"].values())


def test_owner_counts_hash_budget_and_serial_ranges_fail_closed() -> None:
    closed = _small_closed(selected_representatives=(0, 1))

    with pytest.raises(RuntimeError, match="whole selected orbits"):
        _build_small_plan(
            closed,
            owners={0: 0},
            selected_counts=(1, 20),
        )
    with pytest.raises(ValueError, match="outside the MPI communicator"):
        _build_small_plan(
            closed,
            owners={0: 0, 1: 2},
            selected_counts=(1, 20),
        )
    with pytest.raises(RuntimeError, match="allgather-like selected"):
        _build_small_plan(
            closed,
            owners={0: 0, 1: 1},
            selected_counts=(20, 1),
        )
    with pytest.raises(RuntimeError, match="selection SHA256"):
        build_selective_p6_trace_mpi_row_plan(
            closed_numbering=closed,
            selected_orbit_owner_ranks={0: 0, 1: 1},
            owned_base_row_counts_by_rank=(3, 2),
            owned_selected_trace_row_counts_by_rank=(1, 20),
            geometry_key_sha256=_digest("geometry"),
            ordered_trace_basis_sha256=_digest("ordered-trace-basis"),
            selection_sha256=_digest("wrong-selection"),
            expected_full3d_dof_limit=200,
        )
    with pytest.raises(RuntimeError, match="budget disagrees"):
        build_selective_p6_trace_mpi_row_plan(
            closed_numbering=closed,
            selected_orbit_owner_ranks={0: 0, 1: 1},
            owned_base_row_counts_by_rank=(3, 2),
            owned_selected_trace_row_counts_by_rank=(1, 20),
            geometry_key_sha256=_digest("geometry"),
            ordered_trace_basis_sha256=_digest("ordered-trace-basis"),
            selection_sha256=_selection_hash(closed),
            expected_full3d_dof_limit=199,
        )

    first, second = closed.numbering.orbits
    overlapping_second = replace(
        second,
        active_row_start=first.active_row_start,
        active_row_stop=(
            int(first.active_row_start or 0) + second.missing_mode_count
        ),
    )
    corrupt_numbering = replace(
        closed.numbering,
        orbits=(first, overlapping_second),
    )
    corrupt_closed = replace(closed, numbering=corrupt_numbering)
    with pytest.raises(RuntimeError, match="overlap"):
        _selection_hash(corrupt_closed)

    incomplete_closure = replace(
        closed.closure,
        selected_physical_entity_ids=(0,),
    )
    incomplete_closed = replace(closed, closure=incomplete_closure)
    with pytest.raises(RuntimeError, match="complete periodic orbits"):
        _selection_hash(incomplete_closed)


def _h14_closed() -> ExactSequenceClosedP6TraceNumbering:
    """Synthetic count authority only; no actual mesh/DWR is claimed."""

    entities: list[MissingP6TraceEntity] = []
    relations: list[PeriodicMissingTraceRelation] = []
    rules: list[DiscreteGradientOrbitRule] = []
    representatives: list[tuple[int, str, int]] = []
    next_entity = 0
    edge_projection = _projection(1)
    face_projection = _projection(20)
    for orbit_index in range(420):
        member_count = 2 if orbit_index < 195 else 1
        representative = next_entity
        representatives.append((representative, "edge", member_count))
        for offset in range(member_count):
            entities.append(
                MissingP6TraceEntity(
                    entity_id=next_entity + offset,
                    entity_kind="edge",
                    missing_mode_count=1,
                    required_periodic_directions=(
                        ("x",) if member_count == 2 else ()
                    ),
                )
            )
        if member_count == 2:
            relations.append(
                PeriodicMissingTraceRelation(
                    slave_entity_id=next_entity + 1,
                    master_entity_id=next_entity,
                    direction="x",
                    intertwining_projection=edge_projection,
                )
            )
        rules.append(_rule(representative=representative, kind="edge"))
        next_entity += member_count
    for orbit_index in range(408):
        member_count = 2 if orbit_index < 88 else 1
        representative = next_entity
        representatives.append((representative, "face", member_count))
        for offset in range(member_count):
            entities.append(
                MissingP6TraceEntity(
                    entity_id=next_entity + offset,
                    entity_kind="face",
                    missing_mode_count=20,
                    required_periodic_directions=(
                        ("x",) if member_count == 2 else ()
                    ),
                )
            )
        if member_count == 2:
            relations.append(
                PeriodicMissingTraceRelation(
                    slave_entity_id=next_entity + 1,
                    master_entity_id=next_entity,
                    direction="x",
                    intertwining_projection=face_projection,
                )
            )
        rules.append(_rule(representative=representative, kind="face"))
        next_entity += member_count
    assert next_entity == 615 + 496

    edge_representatives = [
        representative
        for representative, kind, _members in representatives
        if kind == "edge"
    ]
    face_representatives = [
        representative
        for representative, kind, _members in representatives
        if kind == "face"
    ]
    selected_representatives = tuple(
        (*edge_representatives[:-10], *face_representatives[: 88 + 178])
    )
    return build_exact_sequence_closed_p6_trace_numbering(
        entities=entities,
        periodic_relations=relations,
        gradient_rules=rules,
        seed_trace_representative_ids=selected_representatives,
        full3d_base_dofs=82_315,
        active_base_rows=18_420,
        full3d_dof_limit=90_000,
    )


def _rank_selected_counts(
    closed: ExactSequenceClosedP6TraceNumbering,
    owners: dict[int, int],
    mpi_size: int,
) -> tuple[int, ...]:
    counts = [0] * mpi_size
    for orbit in closed.numbering.orbits:
        if orbit.selected:
            counts[owners[orbit.representative_entity_id]] += (
                orbit.missing_mode_count
            )
    return tuple(counts)


def _h14_plan(
    closed: ExactSequenceClosedP6TraceNumbering,
    *,
    mpi_size: int,
) -> SelectiveP6TraceMPIRowPlan:
    selected_representatives = (
        closed.closure.selected_trace_representative_ids
    )
    owners = {
        representative: index % mpi_size
        for index, representative in enumerate(selected_representatives)
    }
    base, remainder = divmod(closed.numbering.active_base_rows, mpi_size)
    base_counts = tuple(
        base + (rank < remainder) for rank in range(mpi_size)
    )
    selection_hash = canonical_selective_p6_trace_selection_sha256(
        closed_numbering=closed,
        geometry_key_sha256=_digest("synthetic-h14-geometry"),
        ordered_trace_basis_sha256=_digest(
            "synthetic-h14-ordered-trace-basis"
        ),
    )
    return build_selective_p6_trace_mpi_row_plan(
        closed_numbering=closed,
        selected_orbit_owner_ranks=owners,
        owned_base_row_counts_by_rank=base_counts,
        owned_selected_trace_row_counts_by_rank=_rank_selected_counts(
            closed,
            owners,
            mpi_size,
        ),
        geometry_key_sha256=_digest("synthetic-h14-geometry"),
        ordered_trace_basis_sha256=_digest(
            "synthetic-h14-ordered-trace-basis"
        ),
        selection_sha256=selection_hash,
        expected_full3d_dof_limit=90_000,
    )


def _canonical_values(
    plan: SelectiveP6TraceMPIRowPlan,
) -> tuple[complex, ...]:
    petsc_values = np.zeros(plan.active_rows, dtype=np.complex128)
    logical_values = {
        key: complex(index + 1, -(index + 1))
        for index, key in enumerate(plan.canonical_logical_orbit_modes)
    }
    for key, row in plan.logical_orbit_mode_to_petsc_row.items():
        petsc_values[row] = logical_values[key]
    return tuple(
        petsc_values[row]
        for row in plan.petsc_rows_in_canonical_logical_order
    )


def test_h14_counts_and_mpi2_mpi4_canonical_repartition_invariance() -> None:
    closed = _h14_closed()
    mpi2 = _h14_plan(closed, mpi_size=2)
    mpi4 = _h14_plan(closed, mpi_size=4)

    assert closed.closure.full3d_equivalent_increment == 7_685
    assert closed.closure.full3d_equivalent_dofs == 90_000
    assert closed.closure.active_row_increment == 5_730
    assert mpi2.full3d_equivalent_increment == 7_685
    assert mpi2.quotient_active_increment == 5_730
    assert mpi2.active_rows == 24_150
    assert mpi4.active_rows == 24_150
    assert mpi2.selection_sha256 == mpi4.selection_sha256
    assert mpi2.canonical_logical_orbit_modes == (
        mpi4.canonical_logical_orbit_modes
    )
    assert _canonical_values(mpi2) == _canonical_values(mpi4)
    assert mpi2.petsc_rows_in_canonical_logical_order != (
        mpi4.petsc_rows_in_canonical_logical_order
    )
    assert mpi2.actual_mesh is False
    assert mpi2.audit["actual_dwr_used_by_this_layer"] is False


def test_actual_mesh_audit_requires_all_caller_qualification_flags() -> None:
    closed = _small_closed(selected_representatives=(0,))
    selection_hash = _selection_hash(closed)
    partial = build_selective_p6_trace_mpi_row_plan(
        closed_numbering=closed,
        selected_orbit_owner_ranks={0: 0},
        owned_base_row_counts_by_rank=(3, 2),
        owned_selected_trace_row_counts_by_rank=(1, 0),
        geometry_key_sha256=_digest("geometry"),
        ordered_trace_basis_sha256=_digest("ordered-trace-basis"),
        selection_sha256=selection_hash,
        expected_full3d_dof_limit=200,
        caller_qualified_geometry_key=True,
    )
    qualified = build_selective_p6_trace_mpi_row_plan(
        closed_numbering=closed,
        selected_orbit_owner_ranks={0: 0},
        owned_base_row_counts_by_rank=(3, 2),
        owned_selected_trace_row_counts_by_rank=(1, 0),
        geometry_key_sha256=_digest("geometry"),
        ordered_trace_basis_sha256=_digest("ordered-trace-basis"),
        selection_sha256=selection_hash,
        expected_full3d_dof_limit=200,
        caller_qualified_geometry_key=True,
        caller_qualified_ordered_basis_identity=True,
        caller_qualified_representative_owners=True,
    )

    assert partial.actual_mesh is False
    assert partial.audit["actual_mesh_claim_authority"] == (
        "not_caller_qualified"
    )
    assert qualified.actual_mesh is True
    assert qualified.audit["actual_mesh_verified_by_this_pure_layer"] is False
