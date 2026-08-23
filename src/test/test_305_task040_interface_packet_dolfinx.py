"""Focused Task040 canonical-plane and producer-detach contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import cpp, default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_packet_dolfinx import (
    build_dolfinx_plane_gamma_layout,
    build_gamma_canonical_layout,
    canonicalize_owner_local_basis_in_place,
    make_gamma_entity_block,
    reconstruct_owner_local_basis,
)
from src.solvers.hybrid_interface_schur import build_distributed_petrov_action
from src.solvers.hcurl_canonical_vector import canonical_key


def _json_to_tuple(value):
    if isinstance(value, list):
        return tuple(_json_to_tuple(item) for item in value)
    if isinstance(value, dict):
        return {key: _json_to_tuple(item) for key, item in value.items()}
    return value


def _canonical_records() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "role": "active_trace",
            "entity_dimension": 1,
            "physical_entity": {"axis": "x", "index": 7},
            "entity_local_basis_index": index,
            "orientation_state": "canonical",
            "floquet_master": None,
            "floquet_coefficient": [1.0, 0.0],
        }
        for index in range(2)
    )


def test_canonical_block_round_trip_uses_fresh_raw_order_and_transform() -> None:
    records = _canonical_records()
    source_transform = np.asarray(
        [
            [1.1 + 0.2j, 0.3 - 0.1j],
            [-0.2 + 0.4j, 0.8 + 0.3j],
        ],
        dtype=np.complex128,
    )
    target_transform = np.asarray(
        [
            [0.7 - 0.4j, -0.2 + 0.5j],
            [0.6 + 0.1j, 1.3 + 0.2j],
        ],
        dtype=np.complex128,
    )
    source = make_gamma_entity_block(
        name="source",
        entity_dimension=1,
        physical_entity={"axis": "x", "index": 7},
        raw_row_ids=(10, 20),
        canonical_to_raw=(0.4 + 0.6j) * source_transform,
        orientation_state="source",
        canonical_key_records=records,
    )
    source_layout = build_gamma_canonical_layout(
        (source,), (10, 20), plane_identity={"plane": "source"}
    )
    canonical_u = np.asarray(
        [[1.0 + 0.2j, -0.3 + 0.5j], [0.4 - 0.1j, 0.7 + 0.6j]],
        dtype=np.complex128,
    )
    canonical_v = np.asarray(
        [[-0.2 + 0.8j, 0.9 - 0.4j], [0.5 + 0.1j, -0.6 + 0.3j]],
        dtype=np.complex128,
    )
    raw_u = source.canonical_to_raw @ canonical_u
    raw_v = source.canonical_to_raw @ canonical_v
    finalized = canonicalize_owner_local_basis_in_place(source_layout, raw_u, raw_v)
    assert finalized.U is raw_u
    assert finalized.V is raw_v
    assert np.allclose(finalized.U, canonical_u, rtol=0.0, atol=1.0e-12)
    assert np.allclose(finalized.V, canonical_v, rtol=0.0, atol=1.0e-12)

    target = make_gamma_entity_block(
        name="fresh-target",
        entity_dimension=1,
        physical_entity={"axis": "x", "index": 7},
        raw_row_ids=(20, 10),
        canonical_to_raw=(0.8 - 0.2j) * target_transform,
        orientation_state="fresh",
        canonical_key_records=records,
    )
    target_layout = build_gamma_canonical_layout(
        (target,), (20, 10), plane_identity={"plane": "fresh"}
    )
    rebuilt = reconstruct_owner_local_basis(
        target_layout,
        finalized.keys,
        finalized.U,
        finalized.V,
    )
    expected_u = target.canonical_to_raw @ canonical_u
    expected_v = target.canonical_to_raw @ canonical_v
    assert np.allclose(rebuilt.U, expected_u, rtol=0.0, atol=1.0e-12)
    assert np.allclose(rebuilt.V, expected_v, rtol=0.0, atol=1.0e-12)


def _plane_owned_rows(function_space, plane_z: float) -> np.ndarray:
    topology = function_space.mesh.topology
    tdim = topology.dim
    for dimension in (1, 2):
        topology.create_entities(dimension)
        topology.create_connectivity(tdim, dimension)
        topology.create_connectivity(dimension, tdim)
    topology.create_entity_permutations()
    layout = function_space.dofmap.dof_layout
    index_map = function_space.dofmap.index_map
    first, last = map(int, index_map.local_range)
    rows: set[int] = set()
    for cell in range(int(topology.index_map(tdim).size_local)):
        cell_dofs = np.asarray(function_space.dofmap.cell_dofs(cell), dtype=np.int32)
        for dimension in (1, 2):
            links = topology.connectivity(tdim, dimension).links(cell)
            for local_entity, entity in enumerate(links):
                geometry = cpp.mesh.entities_to_geometry(
                    function_space.mesh._cpp_object,
                    dimension,
                    np.asarray([entity], dtype=np.int32),
                    True,
                )
                coords = np.asarray(
                    function_space.mesh.geometry.x[
                        np.asarray(geometry[0], dtype=np.int64)
                    ],
                    dtype=np.float64,
                )
                if not np.allclose(coords[:, 2], plane_z, rtol=0.0, atol=1.0e-12):
                    continue
                positions = np.asarray(
                    layout.entity_dofs(dimension, local_entity), dtype=np.int32
                )
                global_rows = np.asarray(
                    index_map.local_to_global(cell_dofs[positions]), dtype=np.int64
                )
                if np.all((global_rows >= first) & (global_rows < last)):
                    rows.update(int(row) for row in global_rows)
    return np.asarray(sorted(rows), dtype=np.int64)


def test_real_dolfinx_plane_layout_has_owner_local_identity_and_round_trip() -> None:
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        2,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    function_space = fem.functionspace(
        msh, element("N1curl", msh.basix_cell(), 1, dtype=default_real_type)
    )
    plane = _plane_owned_rows(function_space, 0.5)
    constraints = SimpleNamespace(
        original_to_active={int(row): int(row) for row in plane}
    )
    condensed = SimpleNamespace(trace_constraints=constraints)
    layout = build_dolfinx_plane_gamma_layout(
        function_space=function_space,
        condensed=condensed,
        floquet_data=None,
        interface_z_nm=0.5,
        plane_cell_side="lower",
        plane_original_dofs=plane,
        gamma_rows_local=plane,
    )
    try:
        assert comm.allreduce(len(plane), op=MPI.SUM) > 0
        assert len(layout.gamma_rows_local) == len(
            set(layout.gamma_rows_local.tolist())
        )
        assert layout.audit["basis_global_replicated"] is False
        assert layout.audit["fe_numeric_allgather"] is False
        has_block = bool(layout.blocks)
        assert comm.allreduce(has_block, op=MPI.LOR)
        if has_block:
            encoded = layout.blocks[0].block.canonical_keys[0]
            record = json.loads(encoded)
            authority = canonical_key(
                role=record["role"],
                entity_dimension=record["entity_dimension"],
                physical_entity=_json_to_tuple(record["physical_entity"]),
                entity_local_basis_index=record["entity_local_basis_index"],
                orientation_state=_json_to_tuple(record["orientation_state"]),
                floquet_master=_json_to_tuple(record["floquet_master"]),
                floquet_coefficient=complex(
                    *_json_to_tuple(record["floquet_coefficient"])
                ),
            )
            assert record["role"] == authority[0]
            assert record["entity_dimension"] == authority[1]
            assert _json_to_tuple(record["physical_entity"]) == authority[2]
            assert record["entity_local_basis_index"] == authority[3]
            assert _json_to_tuple(record["orientation_state"]) == authority[4]
            assert _json_to_tuple(record["floquet_master"]) == authority[5]
            assert _json_to_tuple(record["floquet_coefficient"]) == authority[6]
        raw_u = np.asarray(
            [[1.0 + 0.1j * int(row)] for row in plane], dtype=np.complex128
        )
        raw_v = np.asarray(
            [[-0.4 + 0.2j * int(row)] for row in plane], dtype=np.complex128
        )
        expected_u = raw_u.copy()
        expected_v = raw_v.copy()
        finalized = canonicalize_owner_local_basis_in_place(layout, raw_u, raw_v)
        rebuilt = reconstruct_owner_local_basis(
            layout, finalized.keys, finalized.U, finalized.V
        )
        assert np.allclose(rebuilt.U, expected_u, rtol=0.0, atol=1.0e-12)
        assert np.allclose(rebuilt.V, expected_v, rtol=0.0, atol=1.0e-12)
    finally:
        del layout, condensed, function_space, msh


def test_real_plane_layout_rank_local_error_is_collective() -> None:
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        2,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    function_space = fem.functionspace(
        msh, element("N1curl", msh.basix_cell(), 1, dtype=default_real_type)
    )
    plane = tuple(int(row) for row in _plane_owned_rows(function_space, 0.5))
    if comm.rank == 0:
        broken_plane = plane + (10_000_000,)
        broken_gamma = plane
    else:
        broken_plane = plane
        broken_gamma = plane
    condensed = SimpleNamespace(
        trace_constraints=SimpleNamespace(
            original_to_active={row: row for row in plane}
        )
    )
    try:
        with pytest.raises(ValueError, match="Gamma layout construction failed"):
            build_dolfinx_plane_gamma_layout(
                function_space=function_space,
                condensed=condensed,
                floquet_data=None,
                interface_z_nm=0.5,
                plane_cell_side="lower",
                plane_original_dofs=broken_plane,
                gamma_rows_local=broken_gamma,
            )
    finally:
        del condensed, function_space, msh


def _collect_rows(vector: PETSc.Vec) -> np.ndarray:
    first, _last = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.array, dtype=np.complex128).copy()
    pieces = MPI.COMM_WORLD.allgather((first, local))
    result = np.empty(int(vector.getSize()), dtype=np.complex128)
    for start, values in pieces:
        result[start : start + values.size] = values
    return result


def test_petrov_detach_transfers_u_without_copy_and_releases_resident_state() -> None:
    comm = MPI.COMM_WORLD
    layout = PETSc.Vec().createMPI(3, comm=comm)
    first, last = map(int, layout.getOwnershipRange())
    z_global = np.asarray(
        [
            [1.0 + 0.1j, 0.2 - 0.3j],
            [0.4 - 0.2j, 1.1 + 0.2j],
            [0.3 + 0.5j, -0.4 + 0.1j],
        ],
        dtype=np.complex128,
    )
    y_global = z_global @ np.asarray(
        [[1.2 + 0.1j, 0.2 - 0.3j], [-0.4 + 0.2j, 0.9 + 0.4j]],
        dtype=np.complex128,
    )

    def scalar_apply(source: PETSc.Vec, target: PETSc.Vec) -> None:
        rows = np.arange(first, last, dtype=np.float64)
        target.array[:] = (1.1 + 0.03j * rows) * source.array

    def exact_apply(source: PETSc.Vec, target: PETSc.Vec) -> None:
        scalar_apply(source, target)
        target.array[:] += (0.35 - 0.2j) * source.array

    action = build_distributed_petrov_action(
        layout,
        scalar_apply,
        exact_apply,
        z_global[first:last],
        y_global[first:last],
    )
    source = layout.duplicate()
    target = layout.duplicate()
    direct = layout.duplicate()
    try:
        coefficients = np.asarray([0.7 - 0.1j, -0.3 + 0.4j])
        source.array[:] = np.asarray(
            (z_global @ coefficients)[first:last], dtype=PETSc.ScalarType
        )
        original_delta = action._delta_local
        original_y = action._local_y
        action.apply(source, target)
        exact_apply(source, direct)
        assert np.allclose(_collect_rows(target), _collect_rows(direct), atol=1.0e-12)
        factors = action.detach_projected_woodbury_factors()
        assert factors["U"] is original_delta
        assert factors["V"] is original_y
        if factors["U"].size:
            assert np.shares_memory(factors["U"], original_delta)
        assert np.allclose(factors["G"], y_global.conj().T @ z_global)
        gathered_v = np.vstack(comm.allgather(factors["V"]))
        expected_v = y_global @ np.linalg.inv(factors["G"]).conj().T
        assert np.allclose(gathered_v, expected_v, atol=1.0e-12)
        diagnostics = action.diagnostics
        assert diagnostics["destroyed"] is True
        assert diagnostics["detached"] is True
        assert diagnostics["resident_local_rows"] == 0
        with pytest.raises(RuntimeError, match="destroyed"):
            action.apply(source, target)
    finally:
        action.destroy()
        direct.destroy()
        target.destroy()
        source.destroy()
        layout.destroy()
