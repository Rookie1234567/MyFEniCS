"""Real-MUMPS and fail-closed tests for the direct setup event split."""

from __future__ import annotations

import json

from mpi4py import MPI
from petsc4py import PETSc
import pytest

from src.solvers import dtn_port_3d
from src.solvers.dtn_port_3d import _solve_augmented_system


def _distributed_tridiagonal(n: int) -> tuple[PETSc.Mat, PETSc.Vec]:
    matrix = PETSc.Mat().createAIJ(
        [n, n],
        nnz=3,
        comm=PETSc.COMM_WORLD,
    )
    row_start, row_end = matrix.getOwnershipRange()
    for row in range(row_start, row_end):
        matrix.setValue(row, row, 4.0)
        if row:
            matrix.setValue(row, row - 1, -1.0)
        if row + 1 < n:
            matrix.setValue(row, row + 1, -1.0)
    matrix.assemble()
    rhs = matrix.createVecRight()
    rhs.set(PETSc.ScalarType(1.0))
    return matrix, rhs


@pytest.mark.skipif(
    not PETSc.Sys.hasExternalPackage("mumps"),
    reason="the qualified PETSc build does not expose MUMPS",
)
def test_real_mumps_symbolic_numeric_events_are_rank_bound(
    tmp_path,
) -> None:
    matrix, rhs = _distributed_tridiagonal(8)
    solution = None
    ksp = None
    progress_dir = tmp_path if MPI.COMM_WORLD.size == 1 else None
    try:
        solution, ksp, telemetry = _solve_augmented_system(
            matrix,
            rhs,
            {
                "ksp_type": "preonly",
                "pc_type": "lu",
                "pc_factor_mat_solver_type": "mumps",
            },
            "task035b_factor_event_real_mumps_",
            out_dir=progress_dir,
            comm=MPI.COMM_WORLD,
            dofs=8,
            constraints=0,
            petsc_factor_event_timing=True,
        )
        audit = telemetry["petsc_factor_event_timing"]
        assert audit["status"] == "measured_symbolic_numeric_split"
        assert audit["split_available"] is True
        assert audit["factor_solver_type"] == "mumps"
        assert audit["rank_count"] == MPI.COMM_WORLD.size
        assert audit["ordered_world_ranks"] == list(
            range(MPI.COMM_WORLD.size)
        )
        assert all(audit["checks"].values())
        assert telemetry["mumps_symbolic_seconds"] > 0.0
        assert telemetry["mumps_numeric_seconds"] > 0.0
        for role in ("symbolic", "numeric", "pc_setup"):
            event = audit["events"][role]
            assert event["count_consistent_across_ranks"] is True
            assert event["count_positive_on_all_ranks"] is True
            assert (
                event["seconds_finite_nonnegative_on_all_ranks"]
                is True
            )
        residual = rhs.duplicate()
        matrix.mult(solution, residual)
        residual.axpy(PETSc.ScalarType(-1.0), rhs)
        assert residual.norm() / rhs.norm() < 1.0e-12
        residual.destroy()

        if progress_dir is not None:
            events = [
                json.loads(line)
                for line in (
                    progress_dir / "progress_3d.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]
            completed = next(
                event
                for event in events
                if event["stage"] == "after_ksp_setup_factorized"
            )
            assert completed["mumps_symbolic_seconds"] > 0.0
            assert completed["mumps_numeric_seconds"] > 0.0
            assert (
                completed["petsc_factor_event_timing"][
                    "split_available"
                ]
                is True
            )
    finally:
        if ksp is not None:
            ksp.destroy()
        if solution is not None:
            solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_zero_count_or_missing_events_are_not_reported_as_a_split(
    monkeypatch,
) -> None:
    zero_snapshot = {
        role: {
            "count": 0,
            "seconds": 0.0,
        }
        for role in dtn_port_3d.PETSC_DIRECT_FACTOR_EVENT_NAMES
    }
    monkeypatch.setattr(
        dtn_port_3d,
        "_petsc_factor_event_snapshot",
        lambda: (zero_snapshot, []),
    )
    audit = dtn_port_3d._finish_petsc_direct_factor_event_timing(
        {
            "requested": True,
            "iterative_profile": None,
            "factor_solver_type": "mumps",
            "logging_active_before": False,
            "logging_started_by_profile": True,
            "logging_active_after_begin": True,
            "before": zero_snapshot,
            "errors": [],
        },
        MPI.COMM_SELF,
        local_setup_wall_seconds=1.0,
    )
    assert audit["status"] == "factor_event_split_unavailable"
    assert audit["split_available"] is False
    assert audit["symbolic_seconds_max"] is None
    assert audit["numeric_seconds_max"] is None
    assert (
        audit["checks"]["event_counts_positive_on_all_ranks"]
        is False
    )


def test_factor_event_timing_rejects_iterative_profile_before_setup() -> None:
    matrix, rhs = _distributed_tridiagonal(4)
    try:
        with pytest.raises(ValueError, match="direct-only"):
            _solve_augmented_system(
                matrix,
                rhs,
                {},
                "task035b_factor_event_iterative_reject_",
                comm=MPI.COMM_WORLD,
                dofs=4,
                constraints=0,
                iterative_profile="gmres_jacobi",
                petsc_factor_event_timing=True,
            )
    finally:
        rhs.destroy()
        matrix.destroy()
