"""Focused D1 trace-harmonic definition and real-fixture contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from dolfinx import fem
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI

from src.solvers.common_3d_fields import incident_air_plane_wave_field
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.fullspace_slab_interface import build_fullspace_slab_interface
from src.solvers.fullspace_trace_harmonic import (
    D1_FIXED_TRACE_RANK,
    D1_PROFILE,
    build_trace_harmonic_definition,
    generalized_trace_eigenpairs,
    harmonic_extension_from_blocks,
)
from src.test.stage2_test_utils import stage4_block_config
from src.constraints.floquet_3d import build_double_floquet_mpc


def _real_fixture(tmp_path: Path, degree: int):
    comm = MPI.COMM_WORLD
    root = Path(comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0))
    cfg = replace(
        stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=50.0,
            stage4_dtn_order_policy="zero_order",
            incident_theta_deg=21.131,
            incident_phi_deg=33.690,
        ),
        nedelec_degree=degree,
    )
    mesh_data = build_airbox_mesh_3d(
        cfg, root / f"mesh-d1-p{degree}-n{comm.size}"
    )
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    space = floquet_data.mpc.function_space
    topology = build_fullspace_slab_interface(
        space, mesh_data, floquet_data, cfg
    )
    return cfg, mesh_data, raw_space, space, floquet_data, topology


def _assemble_dense(ufl_form):
    assembled = fem_petsc.assemble_matrix(fem.form(ufl_form), bcs=[])
    assembled.assemble()
    dense = assembled.convert("dense")
    values = np.asarray(dense.getDenseArray(), dtype=np.complex128).copy()
    dense.destroy()
    assembled.destroy()
    return values


def _constrained_dense(ufl_form, raw_space, constrained_space, mpc):
    """Build a small independent constrained oracle through finalized MPC."""

    raw_matrix = _assemble_dense(ufl_form)
    index_map = constrained_space.dofmap.index_map
    local_size = int(index_map.size_local)
    if int(index_map.num_ghosts) != 0:
        raise RuntimeError("serial constrained oracle unexpectedly has ghosts")
    slave_rows = {int(row) for row in np.asarray(mpc.slaves, dtype=np.int32)}
    free_rows = np.asarray(
        [row for row in range(local_size) if row not in slave_rows],
        dtype=np.int64,
    )
    transform = np.empty((local_size, free_rows.size), dtype=np.complex128)
    field = fem.Function(constrained_space)
    for column, row in enumerate(free_rows):
        field.x.array[:] = 0.0
        field.x.array[int(row)] = 1.0 + 0.0j
        field.x.scatter_forward()
        mpc.homogenize(field)
        mpc.backsubstitution(field)
        field.x.scatter_forward()
        transform[:, column] = np.asarray(field.x.array, dtype=np.complex128)
    if transform.shape[0] != raw_matrix.shape[0]:
        raise RuntimeError("raw and finalized-MPC oracle layouts differ")
    constrained = transform.conj().T @ raw_matrix @ transform
    return constrained, free_rows


def _support_rows(space, topology, floquet_data, slab_id: int):
    cells = np.flatnonzero(
        np.asarray(topology.owned_slab_ids, dtype=np.int8) == int(slab_id)
    )
    rows = {
        int(row)
        for cell in cells
        for row in space.dofmap.cell_dofs(int(cell))
    }
    slaves = {int(row) for row in floquet_data.local_slave_dofs}
    active = np.asarray(sorted(rows - slaves), dtype=np.int64)
    trace_set = set(int(row) for row in topology.owned_trace_local_rows)
    trace = np.asarray(sorted(set(active.tolist()) & trace_set), dtype=np.int64)
    interior = np.asarray(
        sorted(set(active.tolist()) - set(trace.tolist())), dtype=np.int64
    )
    return active, trace, interior


def _relative_hermitian(matrix: np.ndarray) -> float:
    return float(
        np.linalg.norm(matrix - matrix.conj().T)
        / max(float(np.linalg.norm(matrix)), 1.0e-300)
    )


def _relative_eigen_residual(
    stiffness: np.ndarray,
    mass: np.ndarray,
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
) -> float:
    residuals = []
    for index, eigenvalue in enumerate(eigenvalues):
        left = stiffness @ eigenvectors[:, index]
        right = eigenvalue * (mass @ eigenvectors[:, index])
        residuals.append(
            np.linalg.norm(left - right)
            / max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-300)
        )
    return float(max(residuals, default=0.0))


def _slave_relation_error(field, floquet_data) -> float:
    coefficients, offsets = floquet_data.mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    values = np.asarray(field.x.array, dtype=np.complex128)
    local_error = 0.0
    for slave in np.asarray(floquet_data.mpc.slaves, dtype=np.int32):
        row = int(slave)
        masters = np.asarray(floquet_data.mpc.masters.links(row), dtype=np.int32)
        start, stop = int(offsets[row]), int(offsets[row + 1])
        local_error = max(
            local_error,
            abs(values[row] - np.dot(coefficients[start:stop], values[masters])),
        )
    return float(
        field.function_space.mesh.comm.allreduce(local_error, op=MPI.MAX)
    )


def _run_serial_algebra(tmp_path: Path, degree: int):
    cfg, mesh_data, raw_space, space, floquet_data, topology = _real_fixture(
        tmp_path, degree
    )
    assert topology.audit["numeric_allgather"] is False
    assert topology.audit["lower_upper_trace_maps"] is True
    assert topology.audit["phase_application"] == "finalized_floquet_mpc_once"
    assert topology.audit["slave_rows_excluded"] is True

    field = incident_air_plane_wave_field(space, cfg)
    field.x.scatter_forward()
    floquet_data.mpc.homogenize(field)
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    assert _slave_relation_error(field, floquet_data) <= 1.0e-11

    for slab_id in (0, 1):
        definition = build_trace_harmonic_definition(
            topology, mesh_data, raw_space, floquet_data.mpc, slab_id
        )
        assert definition.audit["profile"] == D1_PROFILE
        assert definition.audit["coercive_coefficient"] == (
            "k0**2*abs(epsilon_r(x))"
        )
        assert definition.audit["source_independent"] is True
        assert definition.audit["fixture_assembled_oracle"] == "p2_p3_only"
        assert definition.audit["future_p6_backend"] == "owner_local_matrix_free"
        assert definition.audit["global_numeric_allgather"] is False

        auxiliary, interface_mass = definition.build_actions()
        try:
            assert auxiliary.audit["slave_row_identity"] is False
            assert interface_mass.audit["slave_row_identity"] is False
            assert auxiliary.audit["phase_application"] == (
                "finalized_floquet_mpc_once"
            )
            assert interface_mass.audit["phase_application"] == (
                "finalized_floquet_mpc_once"
            )
        finally:
            auxiliary.destroy()
            interface_mass.destroy()

        auxiliary_matrix, free_rows = _constrained_dense(
            definition.auxiliary_form,
            raw_space,
            space,
            floquet_data.mpc,
        )
        interface_matrix, interface_free_rows = _constrained_dense(
            definition.interface_mass_form,
            raw_space,
            space,
            floquet_data.mpc,
        )
        assert np.array_equal(free_rows, interface_free_rows)
        active, trace, interior = _support_rows(
            space, topology, floquet_data, slab_id
        )
        positions = {int(row): index for index, row in enumerate(free_rows)}
        active = np.asarray([positions[int(row)] for row in active], dtype=np.int64)
        trace = np.asarray([positions[int(row)] for row in trace], dtype=np.int64)
        interior = np.asarray([positions[int(row)] for row in interior], dtype=np.int64)
        assert active.size > trace.size > 0
        block = auxiliary_matrix[np.ix_(active, active)]
        trace_positions = np.asarray(
            [int(np.flatnonzero(active == row)[0]) for row in trace],
            dtype=np.int64,
        )
        interior_positions = np.asarray(
            [int(np.flatnonzero(active == row)[0]) for row in interior],
            dtype=np.int64,
        )
        mass = interface_matrix[np.ix_(trace, trace)]
        harmonic_columns = []
        for column in range(trace.size):
            values = np.zeros(trace.size, dtype=np.complex128)
            values[column] = 1.0 + 0.0j
            harmonic_columns.append(
                harmonic_extension_from_blocks(
                    block,
                    trace_positions,
                    values,
                    interior_positions,
                )
            )
        harmonic = np.column_stack(harmonic_columns)
        stiffness = harmonic.conj().T @ block @ harmonic
        assert _relative_hermitian(block) <= 1.0e-12
        assert _relative_hermitian(mass) <= 1.0e-12
        assert _relative_hermitian(stiffness) <= 1.0e-12
        eigenvalues, eigenvectors = generalized_trace_eigenpairs(
            stiffness, mass
        )
        assert eigenvectors.shape[1] == min(D1_FIXED_TRACE_RANK, trace.size)
        assert np.all(np.isfinite(eigenvalues))
        assert np.all(np.isfinite(eigenvectors))
        assert _relative_eigen_residual(
            stiffness, mass, eigenvalues, eigenvectors
        ) <= 1.0e-10
        assert np.allclose(
            eigenvectors.conj().T @ mass @ eigenvectors,
            np.eye(eigenvectors.shape[1]),
            rtol=0.0,
            atol=1.0e-12,
        )

        rng = np.random.default_rng(280000 + degree * 10 + slab_id)
        volume = rng.normal(size=space.dofmap.index_map.size_local) + 1j * rng.normal(
            size=space.dofmap.index_map.size_local
        )
        trace_values = rng.normal(size=trace.size) + 1j * rng.normal(
            size=trace.size
        )
        restricted = volume[trace]
        prolongated = np.zeros_like(volume, dtype=np.complex128)
        prolongated[trace] = trace_values
        assert abs(np.vdot(restricted, trace_values) - np.vdot(volume, prolongated)) <= 1.0e-11

        first = harmonic_extension_from_blocks(
            block, trace_positions, trace_values, interior_positions
        )
        second = harmonic_extension_from_blocks(
            block, trace_positions, trace_values, interior_positions
        )
        assert np.array_equal(first, second)
        assert np.array_equal(first[trace_positions], trace_values)
        assert np.all(np.isfinite(first))


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial p2/p3 D1 assembled algebra fixture",
)
@pytest.mark.parametrize("degree", [2, 3])
def test_d1_real_p2_p3_auxiliary_eigen_and_extension_serial(
    tmp_path: Path, degree: int
):
    _run_serial_algebra(tmp_path, degree)


def _canonical_trace_repeat(topology):
    packets = []
    for facet in topology.facets:
        for ordinal, (global_row, owner) in enumerate(
            zip(facet.trace_global_rows, facet.trace_owners, strict=True)
        ):
            if int(owner) != MPI.COMM_WORLD.rank:
                continue
            key = (tuple(tuple(point) for point in facet.key), int(ordinal))
            value = complex(1.0 + 0.01 * ordinal, -0.02 * ordinal)
            packets.append((key, value))
    packets.sort(key=lambda item: repr(item[0]))
    return tuple(packets)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 D1 owner/ghost and canonical repeat fixture",
)
@pytest.mark.parametrize("degree", [2, 3])
def test_d1_real_p2_p3_owner_ghost_canonical_repeat_mpi2(
    tmp_path: Path, degree: int
):
    _cfg, mesh_data, raw_space, _space, floquet_data, topology = _real_fixture(
        tmp_path, degree
    )
    comm = MPI.COMM_WORLD
    assert topology.audit["numeric_allgather"] is False
    assert topology.audit["global_aij_materialized"] is False
    assert topology.audit["dense_interface_mass_materialized"] is False
    assert topology.audit["lower_upper_trace_maps"] is True
    assert topology.audit["phase_application"] == "finalized_floquet_mpc_once"
    assert set(topology.owned_trace_global_rows).isdisjoint(
        set(topology.ghost_trace_global_rows)
    )
    assert all(
        int(local) not in set(int(row) for row in floquet_data.local_slave_dofs)
        for local in topology.owned_trace_local_rows
    )
    assert all(
        int(owner) in {0, 1} for owner in topology.ghost_trace_owners
    )
    assert len(set(comm.allgather(topology.canonical_sha256))) == 1
    assert len(set(comm.allgather(topology.canonical_global_count))) == 1

    definitions = [
        build_trace_harmonic_definition(
            topology, mesh_data, raw_space, floquet_data.mpc, slab_id
        )
        for slab_id in (0, 1)
    ]
    for definition in definitions:
        assert definition.audit["future_p6_backend"] == "owner_local_matrix_free"
        assert definition.audit["global_numeric_allgather"] is False

    first = _canonical_trace_repeat(topology)
    second = _canonical_trace_repeat(topology)
    assert first == second
    local_norm = sum(abs(value) ** 2 for _key, value in first)
    assert comm.allreduce(local_norm, op=MPI.SUM) > 0.0
    local_count = len(first)
    assert comm.allreduce(local_count, op=MPI.SUM) > 0
