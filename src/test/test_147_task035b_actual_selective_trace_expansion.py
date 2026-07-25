"""Actual full-p6-storage tests for selective physical trace expansion."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from mpi4py import MPI

from dolfinx import default_real_type, fem, mesh

from src.adaptivity.hcurl_regionwise_p import fixed_trace_hcurl_ufl_element
from src.adaptivity.p6_trace_complement_qualification import (
    qualify_p5_p6_nedelec_hexahedron_trace_complement,
)
from src.adaptivity.selective_p6_trace_exact_sequence import (
    DiscreteGradientOrbitRule,
    build_exact_sequence_closed_p6_trace_numbering,
)
from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)
from src.constraints.selective_p6_trace_3d import (
    build_selective_p6_trace_mpi_row_plan,
    canonical_selective_p6_trace_selection_sha256,
)
from src.constraints.selective_p6_trace_expansion import (
    build_actual_selective_p6_trace_expansion,
    constrain_physical_cell_schur,
)
from src.constraints.selective_p6_trace_mesh_catalog import (
    build_selected_p6_trace_orbit_owner_inputs,
    build_selective_p6_trace_mesh_catalog,
)


class _EmptyFacetTags:
    def find(self, _tag: int) -> np.ndarray:
        return np.empty(0, dtype=np.int32)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _gradient_rule(
    representative: int,
    *,
    entity_kind: str,
    ordered_trace_basis_sha256: str,
) -> DiscreteGradientOrbitRule:
    scalar_modes = 1 if entity_kind == "edge" else 9
    return DiscreteGradientOrbitRule(
        scalar_orbit_id=f"test-scalar-{entity_kind}-{representative}",
        anchor_trace_representative_id=representative,
        required_trace_representative_ids=(representative,),
        scalar_mode_count=scalar_modes,
        discrete_gradient_rank=scalar_modes,
        ordered_scalar_basis_sha256=_digest(
            f"test-scalar-basis-{representative}"
        ),
        ordered_trace_basis_sha256=ordered_trace_basis_sha256,
        gradient_map_sha256=_digest(
            f"test-gradient-map-{representative}"
        ),
        periodic_orbit_closed=True,
        discrete_gradient_verified=True,
        gradient_map_binds_ordered_basis_identity=True,
    )


@pytest.fixture(scope="module")
def actual_selective_expansion_fixture():
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    fixed_p5_trace_space = fem.functionspace(
        msh,
        fixed_trace_hcurl_ufl_element(5, 6),
    )
    full_p6_storage_space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    cfg = SimulationConfig3D(
        case_name="task035b_actual_selective_p6_expansion",
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=1.7,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        use_floquet_xy=True,
        incident_theta_deg=31.0,
        incident_phi_deg=19.0,
        polarization_kind="s",
        custom_polarization=None,
        nedelec_degree=6,
        nedelec_trace_degree=5,
        nedelec_interior_degree=6,
        mesh_cell_type="hexahedron",
    )
    floquet = build_double_floquet_mpc(
        fixed_p5_trace_space,
        SimpleNamespace(
            mesh=msh,
            facet_tags=_EmptyFacetTags(),
        ),
        cfg,
    )
    assert floquet.phase_independent_topology is not None
    topology = floquet.phase_independent_topology
    qualification = qualify_p5_p6_nedelec_hexahedron_trace_complement()
    catalog = build_selective_p6_trace_mesh_catalog(
        retained_trace_space=fixed_p5_trace_space,
        phase_independent_topology=topology,
        qualification=qualification,
        coordinate_tolerance=1.0e-8,
        floquet_phase_x=cfg.floquet_phase_x,
        floquet_phase_y=cfg.floquet_phase_y,
        expected_qualification_sha256=(
            qualification.qualification_sha256
        ),
    )

    catalog_orbits = catalog.all_inactive_orbit_numbering.orbits
    selected_orbit = next(
        orbit
        for orbit in catalog_orbits
        if orbit.entity_kind == "face" and len(orbit.member_entity_ids) > 1
    )
    base_active_rows = sum(
        5 if orbit.entity_kind == "edge" else 40
        for orbit in catalog_orbits
    )
    base_counts = [0] * comm.size
    for orbit in catalog_orbits:
        owner = catalog.representative_owner_ranks[
            orbit.representative_entity_id
        ]
        base_counts[owner] += (
            5 if orbit.entity_kind == "edge" else 40
        )
    full3d_base_dofs = int(
        fixed_p5_trace_space.dofmap.index_map.size_global
    )
    full3d_limit = (
        full3d_base_dofs
        + int(catalog.audit["physical_missing_shell_dofs"])
    )
    closed = build_exact_sequence_closed_p6_trace_numbering(
        entities=catalog.missing_trace_entities,
        periodic_relations=catalog.periodic_relations,
        gradient_rules=tuple(
            _gradient_rule(
                orbit.representative_entity_id,
                entity_kind=orbit.entity_kind,
                ordered_trace_basis_sha256=(
                    catalog.ordered_trace_basis_sha256
                ),
            )
            for orbit in catalog_orbits
        ),
        seed_trace_representative_ids=(
            selected_orbit.representative_entity_id,
        ),
        full3d_base_dofs=full3d_base_dofs,
        active_base_rows=base_active_rows,
        full3d_dof_limit=full3d_limit,
    )
    owner_inputs = build_selected_p6_trace_orbit_owner_inputs(
        catalog,
        selected_physical_entity_ids=(
            selected_orbit.member_entity_ids
        ),
    )
    selection_sha256 = canonical_selective_p6_trace_selection_sha256(
        closed_numbering=closed,
        geometry_key_sha256=catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=(
            catalog.ordered_trace_basis_sha256
        ),
    )
    row_plan = build_selective_p6_trace_mpi_row_plan(
        closed_numbering=closed,
        selected_orbit_owner_ranks=(
            owner_inputs.selected_orbit_owner_ranks
        ),
        owned_base_row_counts_by_rank=tuple(base_counts),
        owned_selected_trace_row_counts_by_rank=(
            owner_inputs.owned_selected_trace_row_counts_by_rank
        ),
        geometry_key_sha256=catalog.trace_geometry_sha256,
        ordered_trace_basis_sha256=(
            catalog.ordered_trace_basis_sha256
        ),
        selection_sha256=selection_sha256,
        expected_full3d_dof_limit=full3d_limit,
        caller_qualified_geometry_key=True,
        caller_qualified_ordered_basis_identity=True,
        caller_qualified_representative_owners=True,
    )
    bridge = build_actual_selective_p6_trace_expansion(
        full_p6_storage_space=full_p6_storage_space,
        phase_independent_topology=topology,
        catalog=catalog,
        qualification=qualification,
        row_plan=row_plan,
        coordinate_tolerance=1.0e-8,
    )
    return SimpleNamespace(
        mesh=msh,
        fixed_space=fixed_p5_trace_space,
        storage_space=full_p6_storage_space,
        topology=topology,
        qualification=qualification,
        catalog=catalog,
        selected_orbit=selected_orbit,
        row_plan=row_plan,
        bridge=bridge,
    )


def test_full_p6_storage_and_inactive_row_free_counts(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    bridge = fixture.bridge
    caller = bridge.caller_trace_expansion

    assert bridge.audit["pass"] is True
    assert bridge.full_p6_storage_trace_rows == 780
    assert bridge.p5_periodic_quotient_rows == 370
    assert bridge.selected_missing_rows == 20
    assert bridge.active_rows == 390
    assert bridge.audit["inactive_missing_petsc_rows"] == 0
    assert bridge.audit["matrix_constructed"] is False
    assert bridge.audit["local_tensor_constructed"] is False
    assert bridge.audit["actual_channel_dwr_computed"] is False
    assert all(bridge.audit["checks"].values())

    assert int(
        fixture.storage_space.dofmap.index_map.size_global
        - fixture.fixed_space.dofmap.index_map.size_global
    ) == 240
    assert len(bridge.storage_expansion_by_original) == 780
    assert caller.full_trace_rows == 780
    assert caller.active_rows == 390
    assert (
        caller.qualification_audit[
            "inactive_modes_have_no_petsc_rows"
        ]
        is True
    )
    assert (
        caller.qualification_audit["full_trace_matrix_constructed"]
        is False
    )
    assert len(bridge.selected_missing_logical_rows) == 20
    assert set(bridge.selected_missing_logical_rows) == {
        (fixture.selected_orbit.representative_entity_id, mode)
        for mode in range(20)
    }


def test_riesz_retained_and_selected_missing_blocks_are_physical(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    bridge = fixture.bridge
    qualification = fixture.qualification
    selected_representative = (
        fixture.selected_orbit.representative_entity_id
    )
    representative = bridge.entity_expansions[selected_representative]
    shell = qualification.face

    assert representative.representative_entity_id == selected_representative
    np.testing.assert_allclose(
        representative.retained_pullback,
        np.eye(40),
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        representative.missing_pullback,
        np.eye(20),
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        representative.coefficient_matrix[:, :40],
        shell.retained_embedding,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        representative.coefficient_matrix[:, 40:],
        shell.missing_basis,
        rtol=2.0e-13,
        atol=2.0e-13,
    )
    np.testing.assert_allclose(
        shell.retained_embedding.T
        @ shell.trace_l2_gram
        @ shell.missing_basis,
        0.0,
        rtol=0.0,
        atol=2.0e-10,
    )
    assert np.linalg.matrix_rank(
        representative.coefficient_matrix
    ) == 60

    unselected = next(
        entity
        for entity in bridge.entity_expansions
        if entity.representative_entity_id
        != selected_representative
    )
    assert unselected.selected_missing_active_rows.size == 0
    assert unselected.missing_pullback is None
    assert unselected.coefficient_matrix.shape[1] in {5, 40}


def test_actual_periodic_floquet_member_pullback_is_used(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    bridge = fixture.bridge
    selected = fixture.selected_orbit
    member_id = next(
        entity_id
        for entity_id in selected.member_entity_ids
        if entity_id != selected.representative_entity_id
    )
    member = bridge.entity_expansions[member_id]
    shell = fixture.qualification.face

    assert member.missing_pullback is not None
    assert member.representative_entity_id == (
        selected.representative_entity_id
    )
    np.testing.assert_allclose(
        member.coefficient_matrix[:, :40],
        shell.retained_embedding @ member.retained_pullback,
        rtol=3.0e-13,
        atol=3.0e-12,
    )
    np.testing.assert_allclose(
        member.coefficient_matrix[:, 40:],
        shell.missing_basis @ member.missing_pullback,
        rtol=3.0e-13,
        atol=3.0e-12,
    )
    assert not np.allclose(member.retained_pullback, np.eye(40))
    assert not np.allclose(member.missing_pullback, np.eye(20))


def test_full_p6_storage_expansion_satisfies_every_floquet_relation(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    by_entity = {
        entity.entity_id: entity
        for entity in fixture.bridge.entity_expansions
    }
    for metadata in fixture.catalog.relation_metadata:
        slave = by_entity[metadata.slave_entity_id]
        master = by_entity[metadata.master_entity_id]
        np.testing.assert_array_equal(slave.active_rows, master.active_rows)
        if slave.entity_kind == "edge":
            transform = edge_coefficient_transform(
                6,
                reversed_orientation=(
                    metadata.dolfinx_entity_vertex_permutation == (1, 0)
                ),
                cell_type="hexahedron",
            )
        else:
            transform = face_coefficient_transform(
                6,
                metadata.dolfinx_entity_vertex_permutation,
            )
        floquet_transform = metadata.floquet_phase * transform
        np.testing.assert_allclose(
            slave.coefficient_matrix,
            floquet_transform @ master.coefficient_matrix,
            rtol=3.0e-12,
            atol=3.0e-11,
        )


def test_cell_local_ch_s_c_uses_only_active_columns(
    actual_selective_expansion_fixture,
) -> None:
    bridge = actual_selective_expansion_fixture.bridge
    assert bridge.owned_cell_expansions
    cell = bridge.owned_cell_expansions[0]
    assert len(cell.storage_original_dofs) == 432
    assert cell.coefficient_matrix.shape[0] == 432
    assert len(cell.active_rows) < bridge.active_rows
    diagonal = np.asarray(
        [
            1.0
            + 0.003 * (index + 1)
            + 1j * 0.0007 * (index + 1)
            for index in range(432)
        ],
        dtype=np.complex128,
    )
    storage_schur = np.diag(diagonal)
    active_rows, constrained = constrain_physical_cell_schur(
        cell,
        storage_schur,
    )
    expected = (
        cell.coefficient_matrix.conj().T
        @ storage_schur
        @ cell.coefficient_matrix
    )

    np.testing.assert_array_equal(active_rows, cell.active_rows)
    np.testing.assert_allclose(
        constrained,
        expected,
        rtol=3.0e-13,
        atol=3.0e-12,
    )
    assert constrained.shape == (
        len(cell.active_rows),
        len(cell.active_rows),
    )
    assert set(map(int, cell.active_rows)).issubset(
        set(range(bridge.active_rows))
    )


def test_fixed_p5_trace_storage_is_rejected_not_enriched_afterward(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    with pytest.raises(
        ValueError,
        match="fixed-p5-trace storage cannot create missing p6 modes",
    ):
        build_actual_selective_p6_trace_expansion(
            full_p6_storage_space=fixture.fixed_space,
            phase_independent_topology=fixture.topology,
            catalog=fixture.catalog,
            qualification=fixture.qualification,
            row_plan=fixture.row_plan,
            coordinate_tolerance=1.0e-8,
        )


def test_owner_rows_match_actual_row_plan_and_basis_hash_is_fail_closed(
    actual_selective_expansion_fixture,
) -> None:
    fixture = actual_selective_expansion_fixture
    comm = MPI.COMM_WORLD
    bridge = fixture.bridge
    start, stop = fixture.row_plan.petsc_ownership_ranges[comm.rank]
    np.testing.assert_array_equal(
        bridge.caller_trace_expansion.owned_active_rows,
        np.arange(start, stop, dtype=bridge.caller_trace_expansion.owned_active_rows.dtype),
    )

    with pytest.raises(RuntimeError, match="ordered basis hashes differ"):
        build_actual_selective_p6_trace_expansion(
            full_p6_storage_space=fixture.storage_space,
            phase_independent_topology=fixture.topology,
            catalog=fixture.catalog,
            qualification=fixture.qualification,
            row_plan=replace(
                fixture.row_plan,
                ordered_trace_basis_sha256="0" * 64,
            ),
            coordinate_tolerance=1.0e-8,
        )
