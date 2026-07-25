"""Actual-mesh tests for the Task035b selective p6 trace catalog."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

from dolfinx import fem, mesh

from src.adaptivity.hcurl_regionwise_p import fixed_trace_hcurl_ufl_element
from src.adaptivity.p6_trace_complement_qualification import (
    qualify_p5_p6_nedelec_hexahedron_trace_complement,
)
from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.selective_p6_trace_mesh_catalog import (
    build_selected_p6_trace_orbit_owner_inputs,
    build_selective_p6_trace_mesh_catalog,
)


class _EmptyFacetTags:
    def find(self, _tag: int) -> np.ndarray:
        return np.empty(0, dtype=np.int32)


@pytest.fixture(scope="module")
def actual_mesh_catalog_fixture():
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    retained_space = fem.functionspace(
        msh,
        fixed_trace_hcurl_ufl_element(
            5,
            6,
        ),
    )
    cfg = SimulationConfig3D(
        case_name="task035b_actual_trace_catalog",
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
    mesh_data = SimpleNamespace(
        mesh=msh,
        facet_tags=_EmptyFacetTags(),
    )
    floquet = build_double_floquet_mpc(
        retained_space,
        mesh_data,
        cfg,
    )
    assert floquet.phase_independent_topology is not None
    topology = floquet.phase_independent_topology
    qualification = qualify_p5_p6_nedelec_hexahedron_trace_complement()
    catalog = build_selective_p6_trace_mesh_catalog(
        retained_trace_space=retained_space,
        phase_independent_topology=topology,
        qualification=qualification,
        coordinate_tolerance=1.0e-8,
        floquet_phase_x=cfg.floquet_phase_x,
        floquet_phase_y=cfg.floquet_phase_y,
        expected_qualification_sha256=(
            qualification.qualification_sha256
        ),
    )
    return retained_space, topology, qualification, cfg, catalog


def _block_identity(block) -> tuple:
    return (
        block.entity_kind,
        block.kind,
        block.slave_entity_geometry_key,
        block.master_entity_geometry_key,
    )


def test_actual_mesh_catalog_counts_hashes_and_no_hidden_rows(
    actual_mesh_catalog_fixture,
) -> None:
    _space, _topology, _qualification, _cfg, catalog = (
        actual_mesh_catalog_fixture
    )
    comm = MPI.COMM_WORLD

    assert catalog.audit["pass"] is True
    assert catalog.audit["physical_edge_count"] == 20
    assert catalog.audit["physical_face_count"] == 11
    assert catalog.audit["physical_entity_count"] == 31
    assert catalog.audit["periodic_relation_count"] == 13
    assert catalog.audit["periodic_orbit_count"] == 18
    assert catalog.audit["singleton_orbit_count"] == 7
    assert catalog.audit["physical_missing_shell_dofs"] == 240
    assert catalog.audit["quotient_missing_shell_dofs"] == 170
    assert catalog.audit["active_rows_allocated"] == 0
    assert catalog.audit["actual_channel_dwr_computed"] is False
    assert catalog.audit["matrix_constructed"] is False
    assert all(catalog.audit["checks"].values())

    numbering = catalog.all_inactive_orbit_numbering
    assert numbering.active_row_increment == 0
    assert numbering.entity_active_row_ranges == {}
    assert numbering.inactive_entity_ids == tuple(range(31))
    assert all(orbit.selected is False for orbit in numbering.orbits)
    assert len(catalog.representative_owner_ranks) == 18
    assert all(
        0 <= owner < comm.size
        for owner in catalog.representative_owner_ranks.values()
    )

    for name in (
        "trace_geometry_sha256",
        "ordered_trace_basis_sha256",
        "catalog_sha256",
        "qualification_sha256",
    ):
        value = getattr(catalog, name)
        assert len(value) == 64
        assert len(set(comm.allgather(value))) == 1


def test_canonical_catalog_hashes_are_partition_independent(
    actual_mesh_catalog_fixture,
) -> None:
    _space, _topology, _qualification, _cfg, catalog = (
        actual_mesh_catalog_fixture
    )

    # These hashes are generated from canonical geometry, basis, relation, and
    # orbit metadata only.  DOLFINx global IDs and owner ranks are excluded, so
    # this same test file gives the same values under serial and MPI2.
    assert catalog.trace_geometry_sha256 == (
        "df583dcdb48c3e2f91546ea4cdc1b87d2ba26ea0be57c593899dec699479a4c5"
    )
    assert catalog.ordered_trace_basis_sha256 == (
        "f0896e2030af72ab64d6628f3ee4c9c9499727242b4de3407adc5d10d43a5561"
    )
    assert catalog.catalog_sha256 == (
        "acdd4f818f91573a0b6122cf7421a20c6e8771378c369095bdb734d6749ed852"
    )


def test_periodic_pullbacks_cover_complete_actual_orbits(
    actual_mesh_catalog_fixture,
) -> None:
    _space, _topology, _qualification, cfg, catalog = (
        actual_mesh_catalog_fixture
    )
    phase_by_direction = {
        "x": cfg.floquet_phase_x,
        "y": cfg.floquet_phase_y,
        "corner": cfg.floquet_phase_x * cfg.floquet_phase_y,
    }

    assert len(catalog.periodic_relations) == len(catalog.relation_metadata)
    for relation, metadata in zip(
        catalog.periodic_relations,
        catalog.relation_metadata,
        strict=True,
    ):
        assert relation.direction == metadata.direction
        assert relation.slave_entity_id == metadata.slave_entity_id
        assert relation.master_entity_id == metadata.master_entity_id
        assert relation.floquet_phase == pytest.approx(
            phase_by_direction[relation.direction],
            abs=2.0e-14,
            rel=2.0e-14,
        )
        assert relation.coefficient_pullback.shape in {(1, 1), (20, 20)}
        assert len(metadata.coefficient_pullback_sha256) == 64
        assert metadata.entity_vertex_permutation == tuple(
            range(len(metadata.entity_vertex_permutation))
        )
        assert (
            metadata.dolfinx_coefficient_pullback.shape
            == relation.coefficient_pullback.shape
        )
        assert not metadata.dolfinx_coefficient_pullback.flags.writeable
        assert len(metadata.dolfinx_coefficient_pullback_sha256) == 64

    if MPI.COMM_WORLD.size == 2:
        assert any(
            metadata.dolfinx_entity_vertex_permutation
            != metadata.entity_vertex_permutation
            for metadata in catalog.relation_metadata
        )

    member_ids = [
        member
        for orbit in catalog.all_inactive_orbit_numbering.orbits
        for member in orbit.member_entity_ids
    ]
    assert sorted(member_ids) == list(range(31))
    assert len(member_ids) == len(set(member_ids))
    assert any(
        len(orbit.member_entity_ids) == 4
        for orbit in catalog.all_inactive_orbit_numbering.orbits
        if orbit.entity_kind == "edge"
    )
    assert all(
        set(orbit.representative_to_member_pullbacks)
        == set(orbit.member_entity_ids)
        for orbit in catalog.all_inactive_orbit_numbering.orbits
    )


def test_whole_orbit_owner_inputs_are_ready_for_mpi_row_plan(
    actual_mesh_catalog_fixture,
) -> None:
    _space, _topology, _qualification, _cfg, catalog = (
        actual_mesh_catalog_fixture
    )
    multiple_member_orbit = next(
        orbit
        for orbit in catalog.all_inactive_orbit_numbering.orbits
        if len(orbit.member_entity_ids) > 1
    )
    owner_inputs = build_selected_p6_trace_orbit_owner_inputs(
        catalog,
        selected_physical_entity_ids=(
            multiple_member_orbit.member_entity_ids
        ),
    )

    representative = multiple_member_orbit.representative_entity_id
    assert owner_inputs.selected_representative_entity_ids == (
        representative,
    )
    assert dict(owner_inputs.selected_orbit_owner_ranks) == {
        representative: catalog.representative_owner_ranks[representative]
    }
    assert sum(
        owner_inputs.owned_selected_trace_row_counts_by_rank
    ) == multiple_member_orbit.missing_mode_count

    with pytest.raises(RuntimeError, match="not a union of whole"):
        build_selected_p6_trace_orbit_owner_inputs(
            catalog,
            selected_physical_entity_ids=(
                multiple_member_orbit.member_entity_ids[:1]
            ),
        )


def test_catalog_fails_closed_on_basis_hash_mismatch(
    actual_mesh_catalog_fixture,
) -> None:
    space, topology, qualification, cfg, catalog = (
        actual_mesh_catalog_fixture
    )
    with pytest.raises(RuntimeError, match="basis hash mismatch"):
        build_selective_p6_trace_mesh_catalog(
            retained_trace_space=space,
            phase_independent_topology=topology,
            qualification=qualification,
            coordinate_tolerance=1.0e-8,
            floquet_phase_x=cfg.floquet_phase_x,
            floquet_phase_y=cfg.floquet_phase_y,
            expected_qualification_sha256="0" * 64,
        )
    with pytest.raises(RuntimeError, match="ordered physical"):
        build_selective_p6_trace_mesh_catalog(
            retained_trace_space=space,
            phase_independent_topology=topology,
            qualification=qualification,
            coordinate_tolerance=1.0e-8,
            floquet_phase_x=cfg.floquet_phase_x,
            floquet_phase_y=cfg.floquet_phase_y,
            expected_qualification_sha256=(
                qualification.qualification_sha256
            ),
            expected_ordered_trace_basis_sha256="0" * 64,
        )
    assert catalog.qualification_sha256 == (
        qualification.qualification_sha256
    )


def test_catalog_fails_closed_on_missing_periodic_mate(
    actual_mesh_catalog_fixture,
) -> None:
    space, topology, qualification, cfg, _catalog = (
        actual_mesh_catalog_fixture
    )
    comm = MPI.COMM_WORLD
    local_keys = tuple(_block_identity(block) for block in topology.blocks)
    global_keys = sorted(
        {
            key
            for packet in comm.allgather(local_keys)
            for key in packet
        }
    )
    target = global_keys[0]
    broken_topology = replace(
        topology,
        blocks=tuple(
            block
            for block in topology.blocks
            if _block_identity(block) != target
        ),
    )

    with pytest.raises(RuntimeError, match="coverage is incomplete"):
        build_selective_p6_trace_mesh_catalog(
            retained_trace_space=space,
            phase_independent_topology=broken_topology,
            qualification=qualification,
            coordinate_tolerance=1.0e-8,
            floquet_phase_x=cfg.floquet_phase_x,
            floquet_phase_y=cfg.floquet_phase_y,
            expected_qualification_sha256=(
                qualification.qualification_sha256
            ),
        )


def test_catalog_fails_closed_on_bad_orientation_transform(
    actual_mesh_catalog_fixture,
) -> None:
    space, topology, qualification, cfg, _catalog = (
        actual_mesh_catalog_fixture
    )
    comm = MPI.COMM_WORLD
    local_keys = tuple(_block_identity(block) for block in topology.blocks)
    target = sorted(
        {
            key
            for packet in comm.allgather(local_keys)
            for key in packet
        }
    )[0]
    broken_blocks = tuple(
        replace(
            block,
            coefficient_transform=-block.coefficient_transform,
        )
        if _block_identity(block) == target
        else block
        for block in topology.blocks
    )
    broken_topology = replace(topology, blocks=broken_blocks)

    with pytest.raises(
        RuntimeError,
        match="coefficient transform disagrees",
    ):
        build_selective_p6_trace_mesh_catalog(
            retained_trace_space=space,
            phase_independent_topology=broken_topology,
            qualification=qualification,
            coordinate_tolerance=1.0e-8,
            floquet_phase_x=cfg.floquet_phase_x,
            floquet_phase_y=cfg.floquet_phase_y,
            expected_qualification_sha256=(
                qualification.qualification_sha256
            ),
        )
