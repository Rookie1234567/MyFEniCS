from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers import static_condensed_iterative as core
from src.solvers.dtn_port_3d import Stage4ExternalLinearSolverRequest
from src.solvers.physical_slab_two_level import compress_petsc_vector


def test_assembled_fgmres_core_uses_real_petsc(monkeypatch):
    comm = MPI.COMM_WORLD
    matrix_values = np.zeros((5, 5), dtype=PETSc.ScalarType)
    matrix_values[:4, :4] = np.diag([4.0, 5.0, 6.0, 7.0])
    matrix_values[:4, 4] = [0.2 + 0.1j, 0.1 - 0.05j, 0.15 + 0.02j, 0.05]
    matrix_values[4, :4] = [0.3, -0.1j, 0.2 + 0.05j, 0.1]
    matrix_values[4, 4] = 2.0
    exact = np.asarray([1.0, -0.5 + 0.2j, 0.75, -1.25j, 0.4 + 0.1j])
    rhs_values = matrix_values @ exact
    A = PETSc.Mat().createAIJ(size=(5, 5), nnz=5, comm=comm)
    b = A.createVecRight()
    columns = np.arange(5, dtype=PETSc.IntType)
    start, end = A.getOwnershipRange()
    for row in range(start, end):
        A.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            columns,
            matrix_values[row : row + 1, :],
        )
        b.setValues(
            np.asarray([row], dtype=PETSc.IntType),
            np.asarray([rhs_values[row]], dtype=PETSc.ScalarType),
        )
    A.assemble()
    b.assemble()

    def basis_builder(_system, _space, _config, _floquet, fine):
        basis = []
        local_start, local_end = fine.getOwnershipRange()
        for column in range(4):
            vector = fine.createVecRight()
            if local_start <= column < local_end:
                vector.setValues(
                    np.asarray([column], dtype=PETSc.IntType),
                    np.asarray([1.0], dtype=PETSc.ScalarType),
                )
            vector.assemble()
            basis.append(compress_petsc_vector(vector))
            vector.destroy()
        return tuple(basis)

    def partition_builder(*_args, **_kwargs):
        rows = np.arange(4, dtype=PETSc.IntType)
        return tuple(rows.copy() for _ in range(16)), {"coverage_pass": True}

    monkeypatch.setattr(core, "build_active_trace_floquet_basis", basis_builder)
    monkeypatch.setattr(
        core, "build_trace_aware_physical_slab_partition", partition_builder
    )
    request = Stage4ExternalLinearSolverRequest(
        A=A,
        b=b,
        n_fe=4,
        n_aux=1,
        static_condensed_system=SimpleNamespace(),
        function_space=SimpleNamespace(mesh=SimpleNamespace()),
        config=SimpleNamespace(domain_z_min=0.0, domain_z_max=1.0),
        floquet_data=SimpleNamespace(),
    )
    observed = []
    snapshot, audit = core.solve_assembled_static_condensed_fgmres(
        request,
        screen_iterations=20,
        residual_observer=lambda iteration, reported, condensed: observed.append(
            (iteration, reported, condensed)
        ),
    )
    work = A.createVecLeft()
    try:
        assert snapshot.x.getSize() == 5
        assert snapshot.x.getOwnershipRange() == A.getOwnershipRange()
        assert snapshot.no_global_factor
        assert snapshot.converged_reason > 0
        residuals = (
            snapshot.reported_relative_residual,
            snapshot.condensed_true_residual,
            snapshot.full_augmented_true_residual,
        )
        assert max(residuals) <= 1.0e-10
        A.mult(snapshot.x, work)
        work.axpy(PETSc.ScalarType(-1.0), b)
        assert float(work.norm()) / float(b.norm()) <= 1.0e-10
        assert audit["candidate"]["outer_ksp"] == "fgmres"
        assert audit["candidate"]["pc_side"] == "right"
        assert audit["candidate"]["max_it"] == 20
        assert audit["coarse"]["dimension"] == 4
        assert audit["no_global_factor_inventory"]["global_direct_factor_count"] == 0
        assert audit["smoother_diagnostics"]["factor_only_storage"]
        assert set(audit["smoother_diagnostics"]["local_solver_types"]) == {"ilu"}
        assert observed[0][0] == 0
        assert observed[-1][0] == snapshot.iterations
        assert all(np.isfinite(value) for item in observed for value in item[1:])
    finally:
        work.destroy()
        snapshot.x.destroy()
        A.destroy()
        b.destroy()
