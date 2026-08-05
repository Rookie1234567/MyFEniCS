import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    AssemblyTimeCondensedSystem,
    build_unconstrained_assembly_time_condensation,
)


def _build_p6_fixture(comm):
    mesh_3d = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = mesh_3d.topology.dim
    owned_cells = int(mesh_3d.topology.index_map(tdim).size_local)
    cell_tags = mesh.meshtags(
        mesh_3d,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    V = fem.functionspace(
        mesh_3d,
        element(
            "N1curl",
            mesh_3d.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    return mesh_3d, cell_tags, V, compiled


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    packets = comm.allgather(
        np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    )
    return np.concatenate(packets) if packets else np.empty(0, dtype=np.complex128)


def _set_global_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    start, end = map(int, vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values, dtype=np.complex128)[start:end]
    vector.assemble()


def _allreduce_dense(local: np.ndarray, comm: MPI.Intracomm) -> np.ndarray:
    result = np.zeros_like(local)
    comm.Allreduce(local, result, op=MPI.SUM)
    return result


def _relative(observed: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(observed) - np.asarray(expected))
        / max(float(np.linalg.norm(expected)), 1.0e-30)
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="R7b2a compiled-form integration uses serial or MPI2",
)
def test_compiled_form_retained_p4_core_system():
    comm = MPI.COMM_WORLD
    mesh_3d, cell_tags, V, compiled = _build_p6_fixture(comm)
    ordinary = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
    )
    retained = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        retained_p4_core_research=True,
    )
    assert isinstance(ordinary, AssemblyTimeCondensedSystem)
    assert not isinstance(retained, AssemblyTimeCondensedSystem)
    assert retained.audit["research_only"] is True
    assert retained.audit["ordinary_default_changed"] is False
    assert retained.audit["global_p6_matrix_or_factor_bytes"] == 0
    assert retained.audit["raw_p6_tensor_retained"] is False
    assert retained.audit["full_fe_reduction_available"] is True
    assert retained.audit["trace_block_rows"] == 432
    assert retained.audit["retained_block_rows"] == 540
    assert retained.audit["eliminated_complement_rows_per_cell"] == 342
    global_cells = int(mesh_3d.topology.index_map(mesh_3d.topology.dim).size_global)
    assert retained.retained_rows == (
        retained.numbering.active_trace_rows + 108 * global_cells
    )
    assert retained.numbering.retained_rank_offsets[0] == 0
    assert retained.numbering.retained_rank_offsets[-1] == retained.retained_rows
    assert all(
        factor.partial_schur.shape == (540, 540)
        and factor.p6_trace_dofs.size == 432
        and factor.core_basis.shape == (450, 108)
        and factor.eliminated_basis.shape == (450, 342)
        for factor in (cell.factor for cell in retained.cells)
    )

    expected_local = np.zeros(
        (retained.retained_rows, retained.retained_rows),
        dtype=np.complex128,
    )
    for cell in retained.cells:
        block = cell.expansion.conjugate().transpose() @ (
            cell.factor.partial_schur @ cell.expansion
        )
        expected_local[np.ix_(cell.retained_global_ids, cell.retained_global_ids)] += (
            block
        )
    expected_retained = _allreduce_dense(expected_local, comm)
    probe_values = np.sin(0.013 * np.arange(retained.retained_rows)) + 1j * np.cos(
        0.019 * (np.arange(retained.retained_rows) + 1)
    )
    retained_probe = retained.create_retained_vector()
    _set_global_values(retained_probe, probe_values)
    retained_action, retained_context = retained.create_retained_action()
    retained_result = retained.create_retained_vector()
    retained_action.mult(retained_probe, retained_result)
    retained_global = _global_values(retained_result)
    action_error = _relative(retained_global, expected_retained @ probe_values)
    assert action_error <= 1.0e-11

    full = PETSc.Vec().createMPI(
        (int(V.dofmap.index_map.size_local), retained.full_rows),
        comm=comm,
    )
    full_start, full_end = map(int, full.getOwnershipRange())
    full_values = np.cos(0.011 * np.arange(full_start, full_end)) + 1j * np.sin(
        0.017 * (np.arange(full_start, full_end) + 1)
    )
    full.getArray()[:] = full_values
    full.assemble()
    trace_only = full.duplicate()
    trace_only.set(0.0)
    trace_rows = np.asarray(
        retained.owned_trace_original_dofs,
        dtype=np.int64,
    )
    trace_only.getArray()[trace_rows - full_start] = full_values[
        trace_rows - full_start
    ]
    trace_only.assemble()
    trace_reduced = retained.reduce_full_fe_right_rhs(trace_only)
    trace_expected_local = np.zeros(retained.retained_rows, dtype=np.complex128)
    for original in trace_rows:
        old_id = retained.trace_constraints.original_to_active[int(original)]
        new_id = int(retained.numbering.map_active_ids(np.asarray([old_id]))[0])
        trace_expected_local[new_id] += full_values[int(original) - full_start]
    trace_expected = _allreduce_dense(trace_expected_local, comm)
    trace_error = _relative(_global_values(trace_reduced), trace_expected)
    assert trace_error <= 1.0e-11
    assert np.count_nonzero(trace_expected) > 0

    interior_only = full.duplicate()
    interior_only.set(0.0)
    expected_right_local = np.zeros(retained.retained_rows, dtype=np.complex128)
    expected_left_local = np.zeros(retained.retained_rows, dtype=np.complex128)
    left_values = np.sin(0.021 * np.arange(full_start, full_end)) + 1j * np.cos(
        0.015 * (np.arange(full_start, full_end) + 1)
    )
    left = full.duplicate()
    left.set(0.0)
    expected_bilinear = 0.0 + 0.0j
    for cell in retained.cells:
        rows = np.asarray(
            cell.cell_original_dofs[cell.factor.p6_interior_dofs],
            dtype=np.int64,
        )
        values = full_values[rows - full_start]
        interior_only.getArray()[rows - full_start] = values
        local = np.zeros(882, dtype=np.complex128)
        local[cell.factor.p6_interior_dofs] = values
        right_reduced = cell.factor.reduce_oriented_right_rhs(local)
        left_local = np.zeros(882, dtype=np.complex128)
        left_local[cell.factor.p6_interior_dofs] = left_values[rows - full_start]
        left_reduced = cell.factor.reduce_oriented_left_functional(left_local)
        expected_right_local[cell.retained_global_ids] += np.asarray(
            cell.expansion.conjugate().transpose() @ right_reduced
        )
        expected_left_local[cell.retained_global_ids] += np.asarray(
            cell.expansion.conjugate().transpose() @ left_reduced
        )
        expected_bilinear += cell.factor.eliminated_complement_bilinear(
            left_local,
            local,
        )
        left.getArray()[rows - full_start] = left_values[rows - full_start]
    interior_only.assemble()
    left.assemble()
    right_reduced = retained.reduce_full_fe_right_rhs(interior_only)
    left_reduced = retained.reduce_full_fe_left_functional(left)
    right_error = _relative(
        _global_values(right_reduced),
        _allreduce_dense(expected_right_local, comm),
    )
    left_error = _relative(
        _global_values(left_reduced),
        _allreduce_dense(expected_left_local, comm),
    )
    assert right_error <= 1.0e-11
    assert left_error <= 1.0e-11

    observed_bilinear = retained.eliminated_complement_bilinear_full_fe(
        left,
        interior_only,
    )
    bilinear_error = abs(observed_bilinear - comm.allreduce(expected_bilinear)) / max(
        abs(observed_bilinear), 1.0e-30
    )
    assert bilinear_error <= 1.0e-11

    retained_solution = retained.create_retained_vector()
    solution_values = np.cos(0.027 * np.arange(retained.retained_rows)) + 1j * np.sin(
        0.031 * (np.arange(retained.retained_rows) + 1)
    )
    _set_global_values(retained_solution, solution_values)
    recovered = retained.recover_owned_full_fe_interiors(
        retained_solution,
        interior_only,
    )
    recovery_error = 0.0
    for cell, (rows, values) in zip(retained.cells, recovered, strict=True):
        local_retained = cell.expansion @ solution_values[cell.retained_global_ids]
        local_rhs = np.zeros(882, dtype=np.complex128)
        local_rows = cell.cell_original_dofs[cell.factor.p6_interior_dofs]
        local_rhs[cell.factor.p6_interior_dofs] = full_values[local_rows - full_start]
        expected = cell.factor.recover_p6_coefficients(
            local_retained,
            oriented_rhs=local_rhs,
        )
        assert np.array_equal(rows, local_rows)
        recovery_error = max(
            recovery_error,
            _relative(values, expected[cell.factor.p6_interior_dofs]),
        )
    recovery_error = float(comm.allreduce(recovery_error, op=MPI.MAX))
    assert recovery_error <= 1.0e-11

    print(
        {
            "cells_global": global_cells,
            "active_trace_rows": retained.numbering.active_trace_rows,
            "retained_rows": retained.retained_rows,
            "action_error": action_error,
            "trace_once_error": trace_error,
            "right_reduction_error": right_error,
            "left_reduction_error": left_error,
            "bilinear_error": bilinear_error,
            "recovery_error": recovery_error,
            "byte_ledger": retained.audit["byte_ledger_global"],
        }
    )

    retained_solution.destroy()
    left_reduced.destroy()
    right_reduced.destroy()
    interior_only.destroy()
    left.destroy()
    trace_reduced.destroy()
    trace_only.destroy()
    full.destroy()
    retained_result.destroy()
    retained_probe.destroy()
    retained_action.destroy()
    retained_context.destroy()
    ordinary.destroy()
