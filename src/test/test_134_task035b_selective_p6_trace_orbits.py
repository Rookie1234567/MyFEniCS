"""Pure tests for Task035b selective missing-p6 trace orbit numbering."""

from __future__ import annotations

import numpy as np
import pytest

from src.adaptivity.selective_p6_trace_orbits import (
    MissingP6TraceEntity,
    PeriodicMissingTraceRelation,
    build_selective_p6_trace_numbering,
    validate_missing_trace_intertwining,
)


def _edge_identity_projection():
    return validate_missing_trace_intertwining(
        enriched_transform=np.eye(2, dtype=np.complex128),
        retained_transform=np.eye(1, dtype=np.complex128),
        retained_embedding=np.asarray([[1.0], [0.0]]),
        missing_embedding=np.asarray([[0.0], [1.0]]),
        expected_missing_transform=np.eye(1),
    )


def _edge_face_inventory():
    entities = (
        MissingP6TraceEntity(
            entity_id=0,
            entity_kind="edge",
            missing_mode_count=1,
            required_periodic_directions=("x",),
        ),
        MissingP6TraceEntity(
            entity_id=1,
            entity_kind="edge",
            missing_mode_count=1,
            required_periodic_directions=("x",),
        ),
        MissingP6TraceEntity(
            entity_id=2,
            entity_kind="face",
            missing_mode_count=20,
        ),
    )
    relations = (
        PeriodicMissingTraceRelation(
            slave_entity_id=1,
            master_entity_id=0,
            direction="x",
            intertwining_projection=_edge_identity_projection(),
            floquet_phase=np.exp(0.31j),
        ),
    )
    return entities, relations


def _number(
    selected_entity_ids,
):
    entities, relations = _edge_face_inventory()
    return build_selective_p6_trace_numbering(
        entities=entities,
        periodic_relations=relations,
        selected_entity_ids=selected_entity_ids,
        full3d_base_dofs=82_315,
        active_base_rows=19_700,
        full3d_dof_limit=90_000,
    )


def test_none_selection_numbers_no_missing_p6_rows() -> None:
    numbering = _number(())

    assert numbering.full3d_equivalent_increment == 0
    assert numbering.active_row_increment == 0
    assert numbering.full3d_equivalent_dofs == 82_315
    assert numbering.active_rows == 19_700
    assert numbering.selected_entity_ids == ()
    assert numbering.inactive_entity_ids == (0, 1, 2)
    assert dict(numbering.entity_active_row_ranges) == {}
    assert all(orbit.selected is False for orbit in numbering.orbits)
    assert numbering.audit["inactive_mode_numbering_policy"] == "no_active_rows"
    assert all(numbering.audit["checks"].values())


def test_all_selection_separates_physical_and_representative_cost() -> None:
    numbering = _number((0, 1, 2))

    # Two periodic edge modes cost two Full3D DoF but one active row.  The
    # non-periodic face costs twenty in both counts.
    assert numbering.full3d_equivalent_increment == 22
    assert numbering.active_row_increment == 21
    assert numbering.full3d_equivalent_dofs == 82_337
    assert numbering.active_rows == 19_721
    assert numbering.audit["selected_edge_entity_count"] == 2
    assert numbering.audit["selected_face_entity_count"] == 1
    assert numbering.audit["selected_orbit_count"] == 2
    assert numbering.audit["full3d_within_limit"] is True
    assert numbering.entity_to_representative[0] == 0
    assert numbering.entity_to_representative[1] == 0
    assert numbering.entity_active_row_ranges[0] == (19_700, 19_701)
    assert numbering.entity_active_row_ranges[1] == (19_700, 19_701)
    assert numbering.entity_active_row_ranges[2] == (19_701, 19_721)


def test_partial_selection_requires_a_complete_periodic_orbit() -> None:
    edge_only = _number((0, 1))

    assert edge_only.full3d_equivalent_increment == 2
    assert edge_only.active_row_increment == 1
    assert edge_only.inactive_entity_ids == (2,)
    assert 2 not in edge_only.entity_active_row_ranges
    assert edge_only.audit["selected_orbit_count"] == 1

    with pytest.raises(RuntimeError, match="not periodic-orbit closed"):
        _number((0,))


def test_missing_periodic_mate_fails_before_any_numbering() -> None:
    orphan = MissingP6TraceEntity(
        entity_id=7,
        entity_kind="edge",
        missing_mode_count=1,
        required_periodic_directions=("x",),
    )
    with pytest.raises(RuntimeError, match="missing periodic mate"):
        build_selective_p6_trace_numbering(
            entities=(orphan,),
            periodic_relations=(),
            selected_entity_ids=(),
            full3d_base_dofs=0,
            active_base_rows=0,
        )


def test_intertwining_projection_rejects_cross_shell_leakage() -> None:
    retained_transform = np.asarray([[0.0, 1.0], [1.0, 0.0]])
    missing_transform = np.asarray([[-1.0]])
    enriched_transform = np.block(
        [
            [retained_transform, np.zeros((2, 1))],
            [np.zeros((1, 2)), missing_transform],
        ]
    )
    projection = validate_missing_trace_intertwining(
        enriched_transform=enriched_transform,
        retained_transform=retained_transform,
        retained_embedding=np.asarray(
            [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]
        ),
        missing_embedding=np.asarray([[0.0], [0.0], [1.0]]),
        expected_missing_transform=missing_transform,
    )
    np.testing.assert_allclose(
        projection.induced_missing_transform,
        missing_transform,
    )
    assert projection.audit["pass"] is True
    assert all(projection.audit["checks"].values())

    leaked = enriched_transform.copy()
    leaked[0, 2] = 0.125
    with pytest.raises(
        RuntimeError,
        match="missing_into_retained_leakage_absent",
    ):
        validate_missing_trace_intertwining(
            enriched_transform=leaked,
            retained_transform=retained_transform,
            retained_embedding=np.asarray(
                [[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]
            ),
            missing_embedding=np.asarray([[0.0], [0.0], [1.0]]),
        )


def _corner_entities():
    directions = {
        0: ("x", "y", "corner"),
        1: ("x", "y"),
        2: ("x", "y"),
        3: ("x", "y", "corner"),
    }
    return tuple(
        MissingP6TraceEntity(
            entity_id=entity_id,
            entity_kind="edge",
            missing_mode_count=1,
            required_periodic_directions=required,
        )
        for entity_id, required in directions.items()
    )


def _corner_relations(*, corrupt_corner: bool):
    projection = _edge_identity_projection()
    phase_x = np.exp(0.23j)
    phase_y = np.exp(-0.17j)
    phase_corner = phase_x * phase_y
    if corrupt_corner:
        phase_corner *= np.exp(0.04j)
    return (
        PeriodicMissingTraceRelation(
            slave_entity_id=1,
            master_entity_id=0,
            direction="x",
            intertwining_projection=projection,
            floquet_phase=phase_x,
        ),
        PeriodicMissingTraceRelation(
            slave_entity_id=2,
            master_entity_id=0,
            direction="y",
            intertwining_projection=projection,
            floquet_phase=phase_y,
        ),
        PeriodicMissingTraceRelation(
            slave_entity_id=3,
            master_entity_id=2,
            direction="x",
            intertwining_projection=projection,
            floquet_phase=phase_x,
        ),
        PeriodicMissingTraceRelation(
            slave_entity_id=3,
            master_entity_id=1,
            direction="y",
            intertwining_projection=projection,
            floquet_phase=phase_y,
        ),
        PeriodicMissingTraceRelation(
            slave_entity_id=3,
            master_entity_id=0,
            direction="corner",
            intertwining_projection=projection,
            floquet_phase=phase_corner,
        ),
    )


def test_corner_cycle_closes_to_one_representative_or_fails_closed() -> None:
    numbering = build_selective_p6_trace_numbering(
        entities=_corner_entities(),
        periodic_relations=_corner_relations(corrupt_corner=False),
        selected_entity_ids=(0, 1, 2, 3),
        full3d_base_dofs=0,
        active_base_rows=0,
    )

    assert len(numbering.orbits) == 1
    orbit = numbering.orbits[0]
    assert orbit.representative_entity_id == 0
    assert orbit.member_entity_ids == (0, 1, 2, 3)
    assert orbit.full3d_equivalent_dof_cost == 4
    assert orbit.active_row_cost == 1
    assert numbering.full3d_equivalent_increment == 4
    assert numbering.active_row_increment == 1
    assert all(
        not pullback.flags.writeable
        for pullback in orbit.representative_to_member_pullbacks.values()
    )

    with pytest.raises(RuntimeError, match="corner/cycle pullback"):
        build_selective_p6_trace_numbering(
            entities=_corner_entities(),
            periodic_relations=_corner_relations(corrupt_corner=True),
            selected_entity_ids=(),
            full3d_base_dofs=0,
            active_base_rows=0,
        )


def test_p5_to_p6_shell_dimensions_are_explicit_and_fail_closed() -> None:
    assert (
        MissingP6TraceEntity(
            entity_id=10,
            entity_kind="edge",
            missing_mode_count=1,
        ).full3d_equivalent_dof_cost
        == 1
    )
    assert (
        MissingP6TraceEntity(
            entity_id=11,
            entity_kind="face",
            missing_mode_count=20,
        ).full3d_equivalent_dof_cost
        == 20
    )
    with pytest.raises(ValueError, match="face shell must have 20 modes"):
        MissingP6TraceEntity(
            entity_id=12,
            entity_kind="face",
            missing_mode_count=19,
        )
