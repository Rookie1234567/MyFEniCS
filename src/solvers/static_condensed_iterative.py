from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, Literal

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .condensed_dtn import (
    combine_petsc_augmented_solution,
    condensed_rhs,
    create_matrix_free_condensed_operator,
    extract_petsc_condensed_blocks,
    full_augmented_relative_residual,
    recover_petsc_auxiliary,
    relative_action_error,
)
from .dtn_port_3d import (
    Stage4ExternalLinearSolverRequest,
    Stage4ExternalLinearSolverSnapshot,
)
from .physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    SparseGalerkinTwoLevelPc,
    build_active_trace_floquet_basis,
    build_trace_aware_physical_slab_partition,
)
from .static_local_schur_action import create_static_local_schur_action


__all__ = ("solve_assembled_static_condensed_fgmres",)
_TINY = np.finfo(float).tiny


class _ShiftedFineAction:
    """MatPython action borrowing F and owning its diagonal shift."""

    def __init__(self, fine: PETSc.Mat, shift: PETSc.Vec) -> None:
        self.fine = fine
        self.shift = shift
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.fine.mult(source, target)
        target.getArray()[:] += self.shift.getArray(readonly=True) * source.getArray(
            readonly=True
        )

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if not self.destroyed:
            self.shift.destroy()
            self.destroyed = True


def _relative_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    work: PETSc.Vec,
    rhs_norm: float,
) -> float:
    operator.mult(solution, work)
    work.axpy(PETSc.ScalarType(-1.0), rhs)
    return float(work.norm()) / max(rhs_norm, _TINY)


def solve_assembled_static_condensed_fgmres(
    request: Stage4ExternalLinearSolverRequest,
    *,
    screen_iterations: Literal[20],
    residual_observer: Callable[[int, float, float], None] | None = None,
    solver_profile: Literal[
        "assembled", "assembled_setup_then_static_local_schur_matrix_free_solve"
    ] = "assembled",
    release_assembled_matrix: Callable[[], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    if solver_profile not in (
        "assembled",
        "assembled_setup_then_static_local_schur_matrix_free_solve",
    ):
        raise ValueError("unsupported assembled FGMRES solver profile")
    exact_profile = (
        solver_profile == "assembled_setup_then_static_local_schur_matrix_free_solve"
    )
    if exact_profile and release_assembled_matrix is None:
        raise ValueError(
            "exact F5b profile requires an assembled-matrix release callback"
        )
    started = perf_counter()
    owned: list[Any] = []
    try:
        blocks = extract_petsc_condensed_blocks(
            request.A, request.b, n_fe=request.n_fe, n_aux=request.n_aux
        )
        owned.append(blocks)
        rhs = condensed_rhs(blocks)
        owned.append(rhs)
        fine = blocks.require_f()
        fine_action = fine
        fine_action_error = None
        if exact_profile:
            fine_action, _ = create_static_local_schur_action(
                request.static_condensed_system, fine
            )
            owned.append(fine_action)
            probe = fine.createVecRight()
            owned.append(probe)
            start, end = map(int, fine.getOwnershipRange())
            probe.getArray()[:] = np.asarray(
                [1.0 + 0.1 * row + 0.2j * (row + 1) for row in range(start, end)],
                dtype=PETSc.ScalarType,
            )
            fine_action_error = relative_action_error(fine, fine_action, probe)
            probe.destroy()
            owned.remove(probe)
            if fine_action_error > 1.0e-11:
                raise ValueError(
                    "retained local Schur action failed the fine-action gate"
                )
        operator, operator_context = create_matrix_free_condensed_operator(
            blocks, fine_operator=fine_action
        )
        owned.append(operator)
        basis = build_active_trace_floquet_basis(
            request.static_condensed_system,
            request.function_space,
            request.config,
            request.floquet_data,
            fine,
        )
        subdomains, partition_audit = build_trace_aware_physical_slab_partition(
            request.static_condensed_system,
            request.function_space.mesh,
            domain_z=(request.config.domain_z_min, request.config.domain_z_max),
            num_slabs=16,
            overlap_fraction=0.25,
        )
        diagonal = fine.createVecLeft()
        owned.append(diagonal)
        fine.getDiagonal(diagonal)
        absolute = np.abs(diagonal.getArray(readonly=True))
        comm = fine.getComm().tompi4py()
        global_scale = float(
            comm.allreduce(float(absolute.max(initial=0.0)), op=MPI.MAX)
        )
        shift = diagonal.duplicate()
        owned.append(shift)
        shift.getArray()[:] = -1j * 0.1 * np.maximum(absolute, 1.0e-12 * global_scale)
        diagonal.destroy()
        owned.remove(diagonal)
        shifted_context = _ShiftedFineAction(fine_action, shift)
        shifted_fine = PETSc.Mat().createPython(
            fine.getSizes(), context=shifted_context, comm=fine.getComm()
        )
        owned.append(shifted_fine)
        owned.remove(shift)
        shifted_fine.setUp()
        smoother = DistributedPhysicalSlabSmoother(
            fine,
            subdomains,
            ilu_levels=0,
            local_ksp_iterations=1,
            local_ksp_type="gmres",
            smoother_iterations=2,
            smoother_ksp_type="gmres",
            action_operator=shifted_fine,
            diagonal_shift=shift,
            factor_only_storage=True,
            interpolation="basic",
            assembly_order="two_color",
        )
        owned.append(smoother)
        coarse = SparseGalerkinTwoLevelPc(operator, smoother, basis, post_smooth=True)
        owned.append(coarse)
        assembled_matrix_released = False
        if exact_profile:
            blocks.release_f()
            release_assembled_matrix()
            assembled_matrix_released = True
        solution = operator.createVecRight()
        monitor_solution = operator.createVecRight()
        residual_work = operator.createVecLeft()
        owned.extend((solution, monitor_solution, residual_work))
        solution.set(0.0)
        rhs_norm = float(rhs.norm())
        reported_history: list[tuple[int, float]] = []
        condensed_samples: list[tuple[int, float]] = []
        sampled_iterations = {0}
        initial_condensed = _relative_residual(
            operator, rhs, solution, residual_work, rhs_norm
        )
        reported_history.append((0, 1.0))
        condensed_samples.append((0, initial_condensed))
        if residual_observer is not None:
            residual_observer(0, 1.0, initial_condensed)
        ksp = PETSc.KSP().create(comm)
        owned.append(ksp)
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(90)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=int(screen_iterations))
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(coarse)
        ksp.setUp()
        setup_seconds = perf_counter() - started

        def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
            reported = float(residual_norm) / max(rhs_norm, _TINY)
            if not reported_history or reported_history[-1][0] != iteration:
                reported_history.append((int(iteration), reported))
            if iteration in (10, 20) and iteration not in sampled_iterations:
                current_solution = current.buildSolution(monitor_solution)
                condensed = _relative_residual(
                    operator, rhs, current_solution, residual_work, rhs_norm
                )
                condensed_samples.append((int(iteration), condensed))
                sampled_iterations.add(iteration)
                if residual_observer is not None:
                    residual_observer(int(iteration), reported, condensed)

        ksp.setMonitor(monitor)
        solve_started = perf_counter()
        ksp.solve(rhs, solution)
        solve_seconds = perf_counter() - solve_started
        reason = int(ksp.getConvergedReason())
        iterations = int(ksp.getIterationNumber())
        reported = float(ksp.getResidualNorm()) / max(rhs_norm, _TINY)
        condensed = _relative_residual(operator, rhs, solution, residual_work, rhs_norm)
        if iterations not in sampled_iterations:
            condensed_samples.append((iterations, condensed))
            if residual_observer is not None:
                residual_observer(iterations, reported, condensed)

        recovery_started = perf_counter()
        auxiliary = recover_petsc_auxiliary(blocks, solution)
        owned.append(auxiliary)
        augmented = (
            request.b.duplicate() if exact_profile else request.A.createVecRight()
        )
        owned.append(augmented)
        combine_petsc_augmented_solution(blocks, solution, auxiliary, augmented)
        full_augmented = full_augmented_relative_residual(
            blocks, solution, auxiliary, fine_operator=fine_action
        )
        recovery_seconds = perf_counter() - recovery_started
        smoother_audit = smoother.diagnostics
        factor_nnz = int(smoother_audit["global_stored_factor_nnz"])
        factor_rows = int(smoother_audit["global_factor_rows"])
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        integer_bytes = np.dtype(PETSc.IntType).itemsize
        factor_csr_payload_estimate_bytes = int(
            factor_nnz * (scalar_bytes + integer_bytes)
            + (factor_rows + 16) * integer_bytes
        )
        audit = {
            "candidate": {
                "outer_ksp": str(ksp.getType()),
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": int(screen_iterations),
                "num_slabs": 16,
                "overlap_fraction": 0.25,
                "absorption_shift": 0.1,
            },
            "solver_profile": solver_profile,
            "assembled_matrix_released_before_solve": assembled_matrix_released,
            "fine_action_relative_error": fine_action_error,
            "reported_history": reported_history,
            "condensed_true_samples": condensed_samples,
            "final": {
                "converged_reason": reason,
                "iterations": iterations,
                "reported_relative_residual": reported,
                "condensed_true_residual": condensed,
                "full_augmented_true_residual": full_augmented,
            },
            "timings_seconds": {
                "setup": float(setup_seconds),
                "solve": float(solve_seconds),
                "recovery": float(recovery_seconds),
                "total": float(perf_counter() - started),
            },
            "operator_apply_count": int(operator_context.apply_count),
            "coarse": {
                "dimension": len(basis),
                "rank": int(coarse.coarse_rank),
                "condition": float(coarse.coarse_condition),
                "basis_storage_bytes": int(coarse.basis_storage_bytes),
                "apply_count": int(coarse.apply_count),
            },
            "partition_audit": partition_audit,
            "smoother_diagnostics": smoother_audit,
            "factor_csr_payload_estimate_bytes": factor_csr_payload_estimate_bytes,
            "no_global_factor_inventory": {
                "global_direct_factor_count": 0,
                "global_schur_matrix_materialized": False,
                "n_aux": int(request.n_aux),
                "coarse_dimension": len(basis),
                "allowed_factor_scope": [
                    "SmallDenseInverse(H)",
                    "dense coarse LU",
                    "COMM_SELF factor_only ILU(0)",
                ],
            },
        }
        snapshot = Stage4ExternalLinearSolverSnapshot(
            x=augmented,
            converged_reason=reason,
            iterations=iterations,
            reported_relative_residual=reported,
            condensed_true_residual=condensed,
            full_augmented_true_residual=full_augmented,
            ksp_type=str(ksp.getType()),
            pc_type=str(pc.getType()),
            residual_limit=1.0e-6,
            no_global_factor=True,
            solver_profile=solver_profile,
            assembled_matrix_released_before_solve=assembled_matrix_released,
            reduced_residual_norm=condensed * rhs_norm,
        )
        owned.remove(augmented)
        return snapshot, audit
    finally:
        for item in reversed(owned):
            item.destroy()
