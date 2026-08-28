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
    audit_owner_local_basis_round_trip,
    make_gamma_entity_block,
    reconstruct_owner_local_basis,
)
from src.solvers.hybrid_full_spectrum_trace import (
    CanonicalModalArray,
    build_canonical_full_spectrum_trace_transform,
)
from src.solvers.hybrid_full_spectrum_continuation import (
    apply_owner_local_gamma_mass_covector,
)
from src.solvers.hybrid_full_spectrum_screen import (
    _PairSpectralPC,
    _classify,
    _face_families,
    _kernel,
    _pairs,
    _row_reorder,
    _symbol,
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
    audit = audit_owner_local_basis_round_trip(
        target_layout,
        rebuilt.U,
        rebuilt.V,
        finalized,
    )
    assert audit["pass"] is True
    assert audit["max_relative_error"] <= 1.0e-12
    tampered_u = rebuilt.U.copy()
    tampered_u[0, 0] += 1.0e-5
    tampered = audit_owner_local_basis_round_trip(
        target_layout,
        tampered_u,
        rebuilt.V,
        finalized,
    )
    assert tampered["pass"] is False


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


def _full_spectrum_fixture(comm):
    nx, ny, channels = 15, 7, 72
    total = nx * ny * channels
    x_levels = [1000]
    y_levels = [2000]
    for index in range(nx):
        x_levels.append(x_levels[-1] + 1000 + (1 if index % 2 == 0 else -1))
    for index in range(ny):
        y_levels.append(y_levels[-1] + 1000 + (1 if index % 2 == 0 else -1))
    first_cell = ny * nx * comm.rank // comm.size
    last_cell = ny * nx * (comm.rank + 1) // comm.size
    first, last = first_cell * channels, last_cell * channels
    owned_rows = np.arange(first, last, dtype=np.int64)
    gamma_rows = np.roll(owned_rows, 1) if len(owned_rows) > 1 else owned_rows
    blocks = []
    for cell in range(first_cell, last_cell):
        ix, iy = cell % nx, cell // nx
        geometry = {
            "x_edge": ((x_levels[ix], y_levels[iy], 0), (x_levels[ix + 1], y_levels[iy], 0)),
            "y_edge": ((x_levels[ix], y_levels[iy], 0), (x_levels[ix], y_levels[iy + 1], 0)),
            "face": (
                (x_levels[ix], y_levels[iy], 0),
                (x_levels[ix + 1], y_levels[iy], 0),
                (x_levels[ix], y_levels[iy + 1], 0),
                (x_levels[ix + 1], y_levels[iy + 1], 0),
            ),
        }
        for kind, count, dimension, offset in (
            ("x_edge", 6, 1, 0), ("y_edge", 6, 1, 6), ("face", 60, 2, 12)
        ):
            transform = np.eye(count, dtype=np.complex128)
            phase = 1.0 + 0.0j
            orientation = "canonical"
            if cell == first_cell == 0 and kind == "x_edge":
                transform += 0.07 * np.diag(np.ones(count - 1), 1)
                phase = 0.73 + 0.29j
                orientation = "reversed-test"
            rows = np.arange(cell * channels + offset, cell * channels + offset + count)
            blocks.append(
                make_gamma_entity_block(
                    name=f"{kind}-{cell}",
                    entity_dimension=dimension,
                    physical_entity=geometry[kind],
                    raw_row_ids=rows,
                    canonical_to_raw=phase * transform,
                    orientation_state=orientation,
                    floquet_coefficient=phase,
                )
            )
    layout = build_gamma_canonical_layout(
        blocks,
        gamma_rows,
        plane_identity={"mesh_cells": [nx, ny], "test": "full-spectrum"},
        comm=comm,
    )
    raw = np.empty(len(gamma_rows), dtype=np.complex128)
    nontrivial = False
    x_index = {value: index for index, value in enumerate(x_levels)}
    y_index = {value: index for index, value in enumerate(y_levels)}
    for placement in layout.blocks:
        block = placement.block
        points = np.asarray(block.physical_entity, dtype=np.int64)
        spans = np.ptp(points[:, :2], axis=0)
        offset = 12 if block.entity_dimension == 2 else 0 if spans[0] > 0 else 6
        ix = x_index[int(np.min(points[:, 0]))]
        iy = y_index[int(np.min(points[:, 1]))]
        canonical = np.asarray(
            [
                0.5
                + 0.01
                * (offset + int(json.loads(key)["entity_local_basis_index"]))
                + 0.003j * (1 + ix + 2 * iy)
                for key in block.canonical_keys
            ],
            dtype=np.complex128,
        )
        raw[placement.positions] = block.canonical_to_raw @ canonical
        nontrivial = nontrivial or block.orientation_state == "reversed-test"
    system = SimpleNamespace(local_mesh=SimpleNamespace(mesh_cells=(nx, ny)))
    mass = PETSc.Mat().createAIJ(
        size=((last - first, total), (last - first, total)), nnz=3, comm=comm
    )
    for row in range(first, last):
        mass.setValue(row, row, PETSc.ScalarType(2.0 + 0.001 * (row % 11)))
        if row + 1 < total:
            mass.setValue(row, row + 1, PETSc.ScalarType(0.07))
        if row:
            mass.setValue(row, row - 1, PETSc.ScalarType(0.07))
    mass.assemble()
    dual, mass_audit = apply_owner_local_gamma_mass_covector(mass, layout, raw)
    return layout, system, raw, dual, mass, mass_audit, nontrivial


def test_canonical_full_spectrum_trace_transform_identity() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("run the canonical full-spectrum identity with serial or MPI2")
    layout, system, raw, dual, mass, mass_audit, nontrivial = _full_spectrum_fixture(comm)
    transform = build_canonical_full_spectrum_trace_transform(system, layout, comm)
    try:
        assert comm.allreduce(nontrivial, op=MPI.LOR)
        assert comm.allreduce(
            any(abs(block.block.floquet_coefficient - 1.0) > 1.0e-12 for block in layout.blocks),
            op=MPI.LOR,
        )
        assert comm.allreduce(int(mass.getInfo()["nz_used"]), op=MPI.SUM) > raw.size
        assert mass_audit["matmult_count"] == 1
        assert mass_audit["dense"] is False
        assert mass_audit["numeric_allgather"] is False
        assert mass_audit["local_gamma_count"] == len(layout.gamma_rows_local)
        assert np.isfinite(mass_audit["source_norm"])
        assert np.isfinite(mass_audit["output_norm"])
        diagnostics = transform.identity_diagnostics(raw, dual)
        assert diagnostics["coverage"] == {
            "channel_count": 72,
            "grid": [15, 7],
            "global_plane_entries": 7560,
            "modal_bound_entries": 105 * ((72 + comm.size - 1) // comm.size),
        }
        assert len(diagnostics["channel_inventory"]) == 72
        assert len(diagnostics["harmonic_inventory"]) == 105
        assert diagnostics["fft_norm"] == "ortho"
        assert diagnostics["phase_once"] is True
        assert diagnostics["phase_once_audit"]["fft_phase_applications"] == 0
        assert diagnostics["numeric_allgather"] is False
        assert diagnostics["full_plane_numeric_replica"] is False
        if comm.size == 2:
            assert diagnostics["max_numeric_buffer_entries"] < 7560
        assert diagnostics["numeric_route"] == "bounded_channel_owner_alltoallv"
        assert diagnostics["block_roundtrip_max"] <= 1.0e-10
        assert diagnostics["primal_roundtrip_max"] <= 1.0e-10
        assert diagnostics["dual_roundtrip_max"] <= 1.0e-10
        assert diagnostics["dft_roundtrip_max"] <= 1.0e-10
        assert diagnostics["parseval_pairing_relative_error"] <= 1.0e-10
        primal = transform.forward_primal(raw)
        expected_modal = []
        for channel in primal.channel_ids:
            canonical_grid = np.asarray(
                [
                    [
                        0.5 + 0.01 * channel + 0.003j * (1 + ix + 2 * iy)
                        for iy in range(7)
                    ]
                    for ix in range(15)
                ],
                dtype=np.complex128,
            )
            expected_modal.append(np.fft.fft2(canonical_grid, norm="ortho"))
        assert np.allclose(
            primal.values, np.asarray(expected_modal), rtol=0.0, atol=1.0e-10
        )
        for direction in ("forward", "inverse"):
            route = diagnostics["numeric_collectives"][direction]
            assert route["numeric_collective_count"] == 1
            assert route["numeric_collective_types"] == ["Alltoallv"]
            if comm.size == 2:
                for field in (
                    "local_send_entries",
                    "local_receive_entries",
                    "max_send_entries",
                    "max_receive_entries",
                ):
                    assert route[field] < 7560
                assert route["max_modal_entries"] <= diagnostics["coverage"]["modal_bound_entries"]
                assert route["max_modal_entries"] < 7560
        dual_modal = transform.forward_dual(dual)
        assert np.allclose(transform.inverse_primal(primal), raw, rtol=0.0, atol=1.0e-10)
        assert np.allclose(transform.inverse_dual(dual_modal), dual, rtol=0.0, atol=1.0e-10)
    finally:
        transform.close()
        mass.destroy()


def test_c3c_full_spectrum_pair_kernel_and_screen_contract() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("run the C3c screen contract with serial or MPI2")
    msh = mesh.create_unit_cube(
        comm, 1, 1, 1, cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    function_space = fem.functionspace(
        msh, element("N1curl", msh.basix_cell(), 6, dtype=default_real_type)
    )
    system = SimpleNamespace(V=function_space)
    pc = None
    try:
        families = _face_families(system)
        assert set(families.values()) == {"x", "y"}
        assert sum(name == "x" for name in families.values()) == 30
        assert sum(name == "y" for name in families.values()) == 30
        pairs = _pairs(system)
        assert len(pairs) == 36
        assert len({channel for pair in pairs for channel in pair}) == 72
        rows = np.asarray([17, 3, 11])
        reordered = _row_reorder(np.asarray([1, 2, 3]), rows, [11, 17, 3])
        assert np.array_equal(_row_reorder(reordered, [11, 17, 3], rows), [1, 2, 3])
        cfg = SimpleNamespace(
            k0=1.3, substrate_index=1.1 + 0.0j, period_x=15.0, period_y=7.0,
            kx=0.2, ky=0.3,
        )
        spectral = SimpleNamespace(
            cfg=cfg, local_mesh=SimpleNamespace(z_values=np.asarray([0, 0, 0, 0, 1]))
        )
        q, phases, symbol = _symbol(spectral, (1.0, 1.1))
        assert symbol["harmonic_count"] == 105 and np.all(np.isfinite(q))
        assert np.any(np.abs(phases - 1.0) > 1.0e-12)
        lower, upper = np.asarray([1 + 2j, 2 - 1j]), np.asarray([3 - 1j, -1 + 4j])
        result = _kernel(lower, upper, q[0], phases[0], (1.0, 1.1), 0.2, 0.3)
        doubled = _kernel(2 * lower, 2 * upper, q[0], phases[0], (1.0, 1.1), 0.2, 0.3)
        assert all(np.all(np.isfinite(value)) for value in result)
        assert np.allclose(doubled[0], 2 * result[0]) and np.allclose(doubled[1], 2 * result[1])
        channels = tuple(range(comm.rank, 72, comm.size))
        values = np.ones((len(channels), 15, 7), dtype=np.complex128)
        pc = _PairSpectralPC(
            None, None, None, (), (), pairs, (1.0, 1.1), q, phases, spectral, comm
        )
        routed = pc._route(
            CanonicalModalArray(values, channels, (15, 7), True),
            CanonicalModalArray(2 * values, channels, (15, 7), True),
        )
        assert all(np.all(np.isfinite(item.values)) for item in routed)
        assert pc.audit["sequence"] == [0, 1, 2, 1, 0]
        assert pc.audit["numeric_collective_count"] == 2
        assert pc.audit["numeric_allgather"] is False
        assert pc.audit["numeric_collective_types"] == ["Alltoallv", "Alltoallv"]
        if comm.size == 2:
            assert pc.audit["max_numeric_buffer_entries"] < 15120
        def records(values):
            return {label: {"residuals": dict(zip(("8", "16", "32", "64"), values))} for label in ("external_dtn_coupling", "fixed_random_repeat_0")}
        assert _classify(records((1.0, 0.9, 0.5, 0.4)))[1] == "five_source_required"
        assert _classify(records((1.0, 0.95, 0.9, 0.9)))[0] == "FULL_SPECTRUM_SWEEP_NO_SIGNAL"
        assert _classify(records((1.0, 0.91, 0.9, 0.75)))[1] == "moving_pml_required"
    finally:
        if pc is not None:
            pc.close()
        del function_space, msh
