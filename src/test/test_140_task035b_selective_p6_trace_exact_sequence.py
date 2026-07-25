"""Pure tests for periodic exact-sequence closure of selective p6 trace."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np
import pytest

from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
    ExactSequenceTraceBudgetExceeded,
    build_exact_sequence_closed_p6_trace_numbering,
    close_p6_trace_orbits_under_exact_sequence,
)
from src.adaptivity.selective_p6_trace_orbits import (
    MissingP6TraceEntity,
    PeriodicP6TraceOrbit,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _orbit(
    representative: int,
    members: tuple[int, ...],
    *,
    kind: str,
) -> PeriodicP6TraceOrbit:
    dimension = 1 if kind == "edge" else 20
    return PeriodicP6TraceOrbit(
        representative_entity_id=representative,
        member_entity_ids=members,
        entity_kind=kind,  # type: ignore[arg-type]
        missing_mode_count=dimension,
        representative_to_member_pullbacks={
            member: np.eye(dimension, dtype=np.complex128)
            for member in members
        },
        selected=False,
        active_row_start=None,
        active_row_stop=None,
    )


def _rule(
    scalar_id: str,
    anchor: int,
    required: tuple[int, ...],
    *,
    kind: str,
) -> DiscreteGradientOrbitRule:
    scalar_modes = 1 if kind == "edge" else 9
    return DiscreteGradientOrbitRule(
        scalar_orbit_id=scalar_id,
        anchor_trace_representative_id=anchor,
        required_trace_representative_ids=required,
        scalar_mode_count=scalar_modes,
        discrete_gradient_rank=scalar_modes,
        ordered_scalar_basis_sha256=_digest(f"{scalar_id}:scalar"),
        ordered_trace_basis_sha256=_digest(f"{scalar_id}:trace"),
        gradient_map_sha256=_digest(f"{scalar_id}:gradient-map"),
        periodic_orbit_closed=True,
        discrete_gradient_verified=True,
        gradient_map_binds_ordered_basis_identity=True,
    )


def _small_entities() -> tuple[MissingP6TraceEntity, ...]:
    return (
        MissingP6TraceEntity(0, "edge", 1),
        MissingP6TraceEntity(1, "face", 20),
        MissingP6TraceEntity(2, "face", 20),
        MissingP6TraceEntity(3, "edge", 1),
    )


def _small_rules() -> tuple[DiscreteGradientOrbitRule, ...]:
    return (
        _rule("scalar-edge-0", 0, (0, 1, 2), kind="edge"),
        _rule("scalar-face-1", 1, (1,), kind="face"),
        _rule("scalar-face-2", 2, (2,), kind="face"),
        _rule("scalar-edge-3", 3, (3,), kind="edge"),
    )


def test_zero_selected_allocates_no_missing_trace_rows() -> None:
    result = build_exact_sequence_closed_p6_trace_numbering(
        entities=_small_entities(),
        periodic_relations=(),
        gradient_rules=_small_rules(),
        seed_trace_representative_ids=(),
        full3d_base_dofs=100,
        active_base_rows=10,
        full3d_dof_limit=200,
    )

    assert result.closure.selected_trace_representative_ids == ()
    assert result.closure.closure_added_trace_representative_ids == ()
    assert result.closure.selected_physical_entity_ids == ()
    assert result.closure.full3d_equivalent_increment == 0
    assert result.closure.active_row_increment == 0
    assert result.numbering.active_rows == 10
    assert result.numbering.entity_active_row_ranges == {}
    assert result.numbering.inactive_entity_ids == (0, 1, 2, 3)
    assert result.audit["inactive_p6_rows_numbered"] is False


def test_all_selected_matches_complete_shell_cost_and_numbering() -> None:
    result = build_exact_sequence_closed_p6_trace_numbering(
        entities=_small_entities(),
        periodic_relations=(),
        gradient_rules=_small_rules(),
        seed_trace_representative_ids=(0, 1, 2, 3),
        full3d_base_dofs=100,
        active_base_rows=10,
        full3d_dof_limit=200,
    )

    assert result.closure.selected_trace_representative_ids == (0, 1, 2, 3)
    assert result.closure.closure_added_trace_representative_ids == ()
    assert result.closure.full3d_equivalent_increment == 42
    assert result.closure.active_row_increment == 42
    assert result.numbering.full3d_equivalent_dofs == 142
    assert result.numbering.active_rows == 52
    assert set(result.numbering.entity_active_row_ranges) == {0, 1, 2, 3}
    assert result.numbering.inactive_entity_ids == ()


def test_edge_seed_adds_gradient_incident_faces_and_reports_triggers() -> None:
    result = build_exact_sequence_closed_p6_trace_numbering(
        entities=_small_entities(),
        periodic_relations=(),
        gradient_rules=_small_rules(),
        seed_trace_representative_ids=(0,),
        full3d_base_dofs=100,
        active_base_rows=10,
        full3d_dof_limit=200,
    )

    assert result.closure.seed_trace_representative_ids == (0,)
    assert result.closure.selected_trace_representative_ids == (0, 1, 2)
    assert result.closure.closure_added_trace_representative_ids == (1, 2)
    assert dict(result.closure.closure_trigger_scalar_rules) == {
        1: ("scalar-edge-0",),
        2: ("scalar-edge-0",),
    }
    assert result.closure.activated_scalar_orbit_ids == (
        "scalar-edge-0",
        "scalar-face-1",
        "scalar-face-2",
    )
    assert result.closure.full3d_equivalent_increment == 41
    assert result.closure.active_row_increment == 41
    assert set(result.numbering.entity_active_row_ranges) == {0, 1, 2}
    assert result.numbering.inactive_entity_ids == (3,)
    assert 3 not in result.numbering.entity_active_row_ranges


def test_budget_excess_fails_before_selected_numbering() -> None:
    with pytest.raises(
        ExactSequenceTraceBudgetExceeded,
        match="closure exceeds the Full3D DoF limit",
    ):
        build_exact_sequence_closed_p6_trace_numbering(
            entities=_small_entities(),
            periodic_relations=(),
            gradient_rules=_small_rules(),
            seed_trace_representative_ids=(0,),
            full3d_base_dofs=100,
            active_base_rows=10,
            full3d_dof_limit=120,
        )


def test_gradient_rule_identity_rank_and_periodicity_fail_closed() -> None:
    valid = _rule("scalar-edge-0", 0, (0,), kind="edge")

    with pytest.raises(ValueError, match="64 hexadecimal"):
        replace(valid, gradient_map_sha256="not-a-sha")
    with pytest.raises(ValueError, match="full scalar-orbit column rank"):
        replace(valid, discrete_gradient_rank=0)
    with pytest.raises(RuntimeError, match="not periodic closed"):
        replace(valid, periodic_orbit_closed=False)
    with pytest.raises(RuntimeError, match="does not bind ordered basis"):
        replace(valid, gradient_map_binds_ordered_basis_identity=False)


def _h14_synthetic_catalog() -> tuple[PeriodicP6TraceOrbit, ...]:
    """Count-only catalog with the h14 physical/quotient inventory.

    It deliberately does not claim the actual mesh's entity identities,
    Floquet pullbacks, gradient incidence, or DWR.
    """

    orbits: list[PeriodicP6TraceOrbit] = []
    next_entity = 0
    for orbit_index in range(420):
        member_count = 2 if orbit_index < 195 else 1
        members = tuple(range(next_entity, next_entity + member_count))
        next_entity += member_count
        orbits.append(_orbit(members[0], members, kind="edge"))
    for orbit_index in range(408):
        member_count = 2 if orbit_index < 88 else 1
        members = tuple(range(next_entity, next_entity + member_count))
        next_entity += member_count
        orbits.append(_orbit(members[0], members, kind="face"))
    assert next_entity == 615 + 496
    return tuple(orbits)


def _self_rules(
    orbits: tuple[PeriodicP6TraceOrbit, ...],
) -> tuple[DiscreteGradientOrbitRule, ...]:
    return tuple(
        _rule(
            f"synthetic-scalar-{orbit.entity_kind}-{index}",
            orbit.representative_entity_id,
            (orbit.representative_entity_id,),
            kind=orbit.entity_kind,
        )
        for index, orbit in enumerate(orbits)
    )


def test_h14_synthetic_count_and_budget_contract_is_not_actual_authority() -> None:
    catalog = _h14_synthetic_catalog()
    rules = _self_rules(catalog)
    representatives = tuple(
        orbit.representative_entity_id for orbit in catalog
    )

    all_selected = close_p6_trace_orbits_under_exact_sequence(
        orbits=catalog,
        gradient_rules=rules,
        seed_trace_representative_ids=representatives,
        full3d_base_dofs=82_315,
        full3d_dof_limit=92_850,
    )
    assert all_selected.audit["catalog_full3d_equivalent_increment"] == 10_535
    assert all_selected.audit["catalog_active_row_increment"] == 8_580
    assert all_selected.full3d_equivalent_increment == 10_535
    assert all_selected.active_row_increment == 8_580
    assert all_selected.full3d_equivalent_dofs == 92_850
    assert all_selected.audit["actual_mesh_verified_by_this_layer"] is False
    assert all_selected.audit["actual_dwr_used_by_this_layer"] is False
    assert all_selected.audit["catalog_provenance"] == "caller_supplied"

    edge_orbits = [orbit for orbit in catalog if orbit.entity_kind == "edge"]
    face_orbits = [orbit for orbit in catalog if orbit.entity_kind == "face"]
    selected_edges = edge_orbits[:-10]
    selected_faces = face_orbits[: 88 + 178]
    budget_seeds = tuple(
        orbit.representative_entity_id
        for orbit in (*selected_edges, *selected_faces)
    )
    budget_selected = close_p6_trace_orbits_under_exact_sequence(
        orbits=catalog,
        gradient_rules=rules,
        seed_trace_representative_ids=budget_seeds,
        full3d_base_dofs=82_315,
        full3d_dof_limit=90_000,
    )
    assert budget_selected.full3d_equivalent_increment == 7_685
    assert budget_selected.full3d_equivalent_dofs == 90_000
    assert budget_selected.full3d_headroom == 0
    assert budget_selected.active_row_increment == 5_730
    assert budget_selected.closure_added_trace_representative_ids == ()

    with pytest.raises(ExactSequenceTraceBudgetExceeded):
        close_p6_trace_orbits_under_exact_sequence(
            orbits=catalog,
            gradient_rules=rules,
            seed_trace_representative_ids=representatives,
            full3d_base_dofs=82_315,
            full3d_dof_limit=90_000,
        )
