from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers import static_condensed_iterative as core
from src.solvers.dtn_port_3d import Stage4ExternalLinearSolverRequest
from src.solvers.physical_slab_two_level import compress_petsc_vector


def _build_request(monkeypatch, retained_schur=True):
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
        static_condensed_system=SimpleNamespace(
            retained_local_schur_by_class=(
                {"fixture": np.eye(4, dtype=PETSc.ScalarType)}
                if retained_schur
                else None
            )
        ),
        function_space=SimpleNamespace(mesh=SimpleNamespace()),
        config=SimpleNamespace(domain_z_min=0.0, domain_z_max=1.0),
        floquet_data=SimpleNamespace(),
    )
    return A, b, request


def test_assembled_fgmres_core_uses_real_petsc(monkeypatch):
    A, b, request = _build_request(monkeypatch)
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


def test_f5b_profile_releases_assembled_matrix(monkeypatch):
    A, b, request = _build_request(monkeypatch)
    monkeypatch.setattr(
        core,
        "create_static_local_schur_action",
        lambda _system, fine: (fine.copy(), None),
    )
    released = []
    lifecycle_events = []

    def release_assembled_matrix():
        released.append(True)
        A.destroy()

    snapshot, audit = core.solve_assembled_static_condensed_fgmres(
        request,
        screen_iterations=20,
        solver_profile="assembled_setup_then_static_local_schur_matrix_free_solve",
        release_assembled_matrix=release_assembled_matrix,
        lifecycle_observer=lambda event, payload: lifecycle_events.append(
            (event, payload)
        ),
    )
    try:
        assert released == [True]
        assert snapshot.x.getSize() == b.getSize()
        assert snapshot.x.getOwnershipRange() == b.getOwnershipRange()
        assert (
            snapshot.solver_profile
            == "assembled_setup_then_static_local_schur_matrix_free_solve"
        )
        assert snapshot.assembled_matrix_released_before_solve
        assert audit["assembled_matrix_released_before_solve"]
        assert audit["fine_action_relative_error"] <= 1.0e-11
        assert [event for event, _ in lifecycle_events] == [
            "F_C_D_H_extracted",
            "condensed_active_rhs_ready",
            "local_schur_action_ready",
            "basis_ready",
            "first_owned_slab_submatrix_allocated",
            "first_owned_slab_factor_ready",
            "all_slab_factors_ready",
            "coarse_operator_ready",
            "F_released",
            "A_released",
            "outer_ksp_setup",
            "outer_ksp_solved",
            "augmented_solution_recovered",
            "full_augmented_residual_complete",
            "solver_owned_objects_released",
        ]
        first_event = lifecycle_events[0][1]
        assert first_event["borrowed_A_already_finalized_at_port_entry"]
        assert first_event["global_matrix_shapes"]["F"] == [4, 4]
        first_live = first_event["rank_local_live_objects"]
        assert first_live["borrowed_augmented_rhs"]
        assert first_live["borrowed_retained_local_schur"]
        assert first_live["extracted_active_rhs"]
        action_event = lifecycle_events[2][1]
        assert action_event["rank_local_retained_schur_class_count"] == 1
        assert action_event["summed_rank_local_retained_schur_class_count"] == (
            MPI.COMM_WORLD.size
        )
        first_factor = lifecycle_events[5][1]
        assert first_factor["rank_local_has_first_factor"]
        assert (
            lifecycle_events[4][1]["rank_local_live_objects"]["slab_submatrices"] == 1
        )
        assert (
            lifecycle_events[5][1]["rank_local_live_objects"]["slab_submatrices"] == 0
        )
        assert lifecycle_events[6][1]["rank_local_live_objects"]["slab_factors"] >= 1
        assert lifecycle_events[-1][1]["normal_completion"]
        final_live = lifecycle_events[-1][1]["rank_local_live_objects"]
        assert final_live["borrowed_augmented_rhs"]
        assert final_live["borrowed_retained_local_schur"]
        assert not final_live["active_F"]
        assert not final_live["C"]
        assert not final_live["D"]
        assert not final_live["H"]
        assert final_live["slab_factors"] == 0
        assert not final_live["outer_ksp"]
    finally:
        snapshot.x.destroy()
        b.destroy()


def test_lifecycle_observer_handles_missing_retained_schur(monkeypatch):
    A, b, request = _build_request(monkeypatch, retained_schur=False)
    events = []
    snapshot, _audit = core.solve_assembled_static_condensed_fgmres(
        request,
        screen_iterations=20,
        solver_profile="assembled",
        lifecycle_observer=lambda event, payload: events.append((event, payload)),
    )
    try:
        first_live = events[0][1]["rank_local_live_objects"]
        action = events[2][1]
        assert not first_live["borrowed_retained_local_schur"]
        assert action["rank_local_retained_schur_class_count"] == 0
        assert action["summed_rank_local_retained_schur_class_count"] == 0
    finally:
        snapshot.x.destroy()
        A.destroy()
        b.destroy()


def test_lifecycle_observer_records_failed_setup_cleanup(monkeypatch):
    A, b, request = _build_request(monkeypatch)
    monkeypatch.setattr(
        core,
        "create_static_local_schur_action",
        lambda _system, fine: (fine.copy(), None),
    )

    def fail_basis(*_args):
        raise RuntimeError("fixture basis failure")

    monkeypatch.setattr(core, "build_active_trace_floquet_basis", fail_basis)
    events = []
    try:
        with pytest.raises(RuntimeError, match="fixture basis failure"):
            core.solve_assembled_static_condensed_fgmres(
                request,
                screen_iterations=20,
                solver_profile=(
                    "assembled_setup_then_static_local_schur_matrix_free_solve"
                ),
                release_assembled_matrix=lambda: None,
                lifecycle_observer=lambda event, payload: events.append(
                    (event, payload)
                ),
            )
        assert events[-1][0] == "solver_owned_objects_released"
        assert not events[-1][1]["normal_completion"]
    finally:
        A.destroy()
        b.destroy()
