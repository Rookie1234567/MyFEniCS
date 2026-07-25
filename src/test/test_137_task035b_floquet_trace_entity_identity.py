"""Focused tests for physical Floquet entity identity and orbit seeds."""

from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.constraints.high_order_floquet_trace import (
    FloquetTopologyKey,
    FloquetTraceTopology,
    PhaseIndependentConstraintBlock,
    build_missing_p6_trace_orbit_identity_input,
)


def _edge_key(x: int, y: int) -> tuple[tuple[int, int, int], ...]:
    return ((x, y, 0), (x, y, 10))


def _face_key(x: int) -> tuple[tuple[int, int, int], ...]:
    return (
        (x, 0, 0),
        (x, 0, 10),
        (x, 10, 0),
        (x, 10, 10),
    )


def _block(
    *,
    kind: str,
    entity_kind: str,
    slave_id: int,
    master_id: int,
    slave_key: tuple[tuple[int, int, int], ...],
    master_key: tuple[tuple[int, int, int], ...],
    permutation: tuple[int, ...],
) -> PhaseIndependentConstraintBlock:
    entity_dimension = 1 if entity_kind == "edge" else 2
    direction_code = {"x": 1, "y": 2, "corner": 3}[kind]
    return PhaseIndependentConstraintBlock(
        kind=kind,  # type: ignore[arg-type]
        slave_global_dofs=(1000 + slave_id,),
        master_global_dofs=(1000 + master_id,),
        coefficient_transform=np.ones((1, 1), dtype=np.complex128),
        entity_kind=entity_kind,  # type: ignore[arg-type]
        slave_entity_id=slave_id,
        master_entity_id=master_id,
        slave_entity_geometry_key=slave_key,
        master_entity_geometry_key=master_key,
        periodic_pair_key=(
            entity_dimension,
            direction_code,
            slave_key[0][0],
            slave_key[0][1],
            slave_key[0][2],
            entity_dimension,
        ),
        entity_vertex_permutation=permutation,
        cell_type="CellType.hexahedron",
    )


def _blocks() -> tuple[PhaseIndependentConstraintBlock, ...]:
    return (
        _block(
            kind="x",
            entity_kind="edge",
            slave_id=11,
            master_id=10,
            slave_key=_edge_key(10, 0),
            master_key=_edge_key(0, 0),
            permutation=(0, 1),
        ),
        _block(
            kind="y",
            entity_kind="edge",
            slave_id=12,
            master_id=10,
            slave_key=_edge_key(0, 10),
            master_key=_edge_key(0, 0),
            permutation=(1, 0),
        ),
        _block(
            kind="corner",
            entity_kind="edge",
            slave_id=13,
            master_id=10,
            slave_key=_edge_key(10, 10),
            master_key=_edge_key(0, 0),
            permutation=(0, 1),
        ),
        _block(
            kind="x",
            entity_kind="face",
            slave_id=11,
            master_id=10,
            slave_key=_face_key(10),
            master_key=_face_key(0),
            permutation=(0, 1, 2, 3),
        ),
    )


def _topology(
    blocks: tuple[PhaseIndependentConstraintBlock, ...],
) -> FloquetTraceTopology:
    return FloquetTraceTopology(
        key=FloquetTopologyKey(
            mesh_token="not-used-by-orbit-input",
            element_family="N1curl",
            degree=5,
            orientation_schema="basix-0.10-hexa-d4-dolfinx-global-v1",
        ),
        blocks=blocks,
        topology_build_seconds=0.0,
        bytes_sent=0,
        bytes_received=0,
    )


def test_phase_block_keeps_legacy_construction_backward_compatible() -> None:
    block = PhaseIndependentConstraintBlock(
        kind="x",
        slave_global_dofs=(9,),
        master_global_dofs=(3,),
        coefficient_transform=np.eye(1),
    )
    assert block.has_physical_entity_identity is False
    assert block.slave_entity_id is None
    assert block.periodic_pair_key == ()


def test_phase_block_rejects_partial_or_inconsistent_physical_identity() -> None:
    with pytest.raises(ValueError, match="must provide both entity IDs"):
        PhaseIndependentConstraintBlock(
            kind="x",
            slave_global_dofs=(9,),
            master_global_dofs=(3,),
            coefficient_transform=np.eye(1),
            slave_entity_id=4,
        )
    with pytest.raises(ValueError, match="direction disagrees"):
        PhaseIndependentConstraintBlock(
            kind="y",
            slave_global_dofs=(11,),
            master_global_dofs=(10,),
            coefficient_transform=np.eye(1),
            entity_kind="edge",
            slave_entity_id=11,
            master_entity_id=10,
            slave_entity_geometry_key=_edge_key(10, 0),
            master_entity_geometry_key=_edge_key(0, 0),
            periodic_pair_key=(1, 1, 10, 0, 0, 1),
            entity_vertex_permutation=(0, 1),
            cell_type="hexahedron",
        )


def test_orbit_identity_is_deterministic_mesh_bound_and_mpi_complete() -> None:
    comm = MPI.COMM_WORLD
    blocks = _blocks()
    local_blocks = tuple(
        block
        for index, block in enumerate(blocks)
        if index % int(comm.size) == int(comm.rank)
    )
    first = build_missing_p6_trace_orbit_identity_input(
        _topology(tuple(reversed(local_blocks))),
        mesh_sha256="a" * 64,
        comm=comm,
    )
    second = build_missing_p6_trace_orbit_identity_input(
        _topology(local_blocks),
        mesh_sha256="a" * 64,
        comm=comm,
    )
    assert first.input_sha256 == second.input_sha256
    assert first.relations == second.relations
    assert len(first.relations) == 4
    assert {
        (relation.entity_kind, relation.master_entity_id)
        for relation in first.relations
        if relation.master_entity_id == 10
    } == {("edge", 10), ("face", 10)}
    assert all(relation.cell_type == "hexahedron" for relation in first.relations)
    assert first.scope == "identity_only_no_basis_dwr_rows_or_matrix"
    assert len(set(comm.allgather(first.input_sha256))) == 1

    different_mesh = build_missing_p6_trace_orbit_identity_input(
        _topology(local_blocks),
        mesh_sha256="b" * 64,
        comm=comm,
    )
    assert different_mesh.input_sha256 != first.input_sha256


def test_orbit_identity_fails_closed_without_physical_ids() -> None:
    legacy = PhaseIndependentConstraintBlock(
        kind="x",
        slave_global_dofs=(9,),
        master_global_dofs=(3,),
        coefficient_transform=np.eye(1),
    )
    with pytest.raises(RuntimeError, match="lacks physical entity identity"):
        build_missing_p6_trace_orbit_identity_input(
            _topology((legacy,)),
            mesh_sha256="a" * 64,
            comm=MPI.COMM_WORLD,
        )
