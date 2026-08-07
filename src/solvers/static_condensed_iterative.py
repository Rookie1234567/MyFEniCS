"""Static-condensed iterative authority for Case100 p6/h10; numerical qualification is established, while 0.7 nm resource scalability is not qualified."""

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
    Stage4NeverMaterializedLinearSolverRequest,
)
from .physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    SparseGalerkinTwoLevelPc,
    build_active_trace_floquet_basis,
    build_owner_local_slab_diagonal,
    build_owner_local_slab_plan,
    build_trace_aware_physical_slab_partition,
)
from .static_local_schur_action import create_static_local_schur_action


__all__ = (
    "solve_assembled_static_condensed_fgmres",
    "solve_never_materialized_static_condensed_fgmres",
    "solve_never_materialized_overlap0125_partition_fgmres",
)
_TINY = np.finfo(float).tiny
_TRUE_RESIDUAL_CARRIER_ITERATIONS = frozenset((0, 20, 100, 200))


def _local_matrix_nnz_used(matrix: PETSc.Mat) -> int | str:
    matrix_type = matrix.getType()
    if matrix_type in (PETSc.Mat.Type.PYTHON, PETSc.Mat.Type.SHELL):
        return "not_applicable"
    return int(matrix.getInfo(PETSc.Mat.InfoType.LOCAL)["nz_used"])


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
    _true_residual_vector(operator, rhs, solution, work)
    return float(work.norm()) / max(rhs_norm, _TINY)


def _true_residual_vector(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    target: PETSc.Vec,
) -> None:
    """Fill target with the condensed true residual b - A*x."""

    operator.mult(solution, target)
    target.scale(PETSc.ScalarType(-1.0))
    target.axpy(PETSc.ScalarType(1.0), rhs)


def _solve_static_condensed_fgmres_core(
    request: Stage4ExternalLinearSolverRequest
    | Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: int,
    residual_observer: Callable[[int, float, float], None] | None = None,
    true_residual_vector_observer: Callable[[int, PETSc.Vec, float], None]
    | None = None,
    solver_profile: Literal[
        "assembled",
        "assembled_setup_then_static_local_schur_matrix_free_solve",
        "never_materialized_owner_local",
        "never_materialized_owner_local_overlap0125_partition",
    ] = "assembled",
    release_assembled_matrix: Callable[[], None] | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    action_only = isinstance(request, Stage4NeverMaterializedLinearSolverRequest)
    if solver_profile not in (
        "assembled",
        "assembled_setup_then_static_local_schur_matrix_free_solve",
        "never_materialized_owner_local",
        "never_materialized_owner_local_overlap0125_partition",
    ):
        raise ValueError("unsupported static-condensed FGMRES solver profile")
    exact_profile = (
        solver_profile == "assembled_setup_then_static_local_schur_matrix_free_solve"
    )
    action_only_profile = solver_profile in {
        "never_materialized_owner_local",
        "never_materialized_owner_local_overlap0125_partition",
    }
    m3a_profile = (
        solver_profile == "never_materialized_owner_local_overlap0125_partition"
    )
    if action_only != action_only_profile:
        raise ValueError("solver profile does not match the request type")
    if exact_profile and not action_only and release_assembled_matrix is None:
        raise ValueError(
            "exact F5b profile requires an assembled-matrix release callback"
        )
    if action_only and release_assembled_matrix is not None:
        raise ValueError(
            "never-materialized request cannot release an assembled matrix"
        )
    started = perf_counter()
    request_operator = request.operator if action_only else request.A
    request_rhs = request.b
    request_operator_size = tuple(map(int, request_operator.getSize()))
    request_operator_columns = tuple(
        map(int, request_operator.getOwnershipRangeColumn())
    )
    comm = request_operator.getComm().tompi4py()
    returned_solution_transferred = False
    live_state: dict[str, bool | int] = {
        "borrowed_augmented_A": not action_only,
        "active_F": False,
        "C": False,
        "D": False,
        "H": False,
        "borrowed_augmented_rhs": True,
        "extracted_active_rhs": False,
        "extracted_aux_rhs": False,
        "condensed_active_rhs": False,
        "borrowed_retained_local_schur": False,
        "fine_action": False,
        "matrix_free_operator": False,
        "basis": False,
        "shifted_action": False,
        "shift": False,
        "slab_submatrices": 0,
        "slab_factors": 0,
        "coarse": False,
        "solution": False,
        "monitor_solution": False,
        "residual_work": False,
        "outer_ksp": False,
        "outer_pc": False,
        "recovered_auxiliary": False,
        "augmented_solution": False,
        "returned_augmented_solution": False,
    }
    if lifecycle_observer is not None:
        live_state["borrowed_retained_local_schur"] = (
            request.static_condensed_system.retained_local_schur_by_class is not None
        )

    def emit_lifecycle(event: str, **payload: Any) -> None:
        if lifecycle_observer is not None:
            payload["rank_local_live_objects"] = dict(live_state)
            lifecycle_observer(
                event,
                {
                    "rank_local_rank": int(comm.rank),
                    "rank_count": int(comm.size),
                    **payload,
                },
            )

    def smoother_setup_observer(event: str, payload: dict[str, Any]) -> None:
        if event == "first_owned_slab_submatrix_allocated":
            live_state["slab_submatrices"] = int(
                bool(payload["rank_local_has_first_submatrix"])
            )
        elif event == "first_owned_slab_factor_ready":
            live_state["slab_submatrices"] = 0
            live_state["slab_factors"] = int(
                bool(payload["rank_local_has_first_factor"])
            )
        elif event == "all_slab_factors_ready":
            live_state["slab_submatrices"] = 0
            live_state["slab_factors"] = int(payload["rank_local_factor_count"])
        emit_lifecycle(event, **payload)

    owned: list[Any] = []
    try:
        if action_only:
            blocks = request.blocks
            if blocks.F is not None:
                raise ValueError(
                    "never-materialized request must provide blocks.F=None"
                )
            fine = request.fine_operator
            matrix_blocks = {"C": blocks.C, "D": blocks.D, "H": blocks.H}
        else:
            blocks = extract_petsc_condensed_blocks(
                request.A, request.b, n_fe=request.n_fe, n_aux=request.n_aux
            )
            owned.append(blocks)
            fine = blocks.require_f()
            matrix_blocks = {
                "F": fine,
                "C": blocks.C,
                "D": blocks.D,
                "H": blocks.H,
            }
        live_state.update(
            active_F=not action_only,
            C=True,
            D=True,
            H=True,
            extracted_active_rhs=not action_only,
            extracted_aux_rhs=not action_only,
        )
        emit_lifecycle(
            "F_C_D_H_extracted",
            blocks_source=("borrowed_action_only" if action_only else "extracted"),
            borrowed_A_already_finalized_at_port_entry=not action_only,
            global_active_rows=int(blocks.n_fe),
            global_aux_rows=int(blocks.n_aux),
            global_augmented_rows=request_operator_size[0],
            global_A_materialized=not action_only,
            global_F_materialized=not action_only,
            global_matrix_shapes={
                name: [int(matrix.getSize()[0]), int(matrix.getSize()[1])]
                for name, matrix in matrix_blocks.items()
            },
            rank_local_matrix_nnz_used={
                name: _local_matrix_nnz_used(matrix)
                for name, matrix in matrix_blocks.items()
            },
        )
        rhs = condensed_rhs(blocks)
        owned.append(rhs)
        live_state["condensed_active_rhs"] = True
        emit_lifecycle(
            "condensed_active_rhs_ready",
            global_condensed_rhs_size=int(rhs.getSize()),
        )
        fine_action = fine
        fine_action_error = None
        if exact_profile and not action_only:
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
        retained_schur_class_count = 0
        retained_schur_bytes = 0
        if lifecycle_observer is not None:
            retained_schurs = (
                request.static_condensed_system.retained_local_schur_by_class
            )
            if retained_schurs is None:
                retained_schur_class_count = 0
                retained_schur_bytes = 0
            else:
                retained_schur_class_count = len(retained_schurs)
                retained_schur_bytes = sum(
                    int(np.asarray(value).nbytes) for value in retained_schurs.values()
                )
            summed_rank_local_retained_schur_class_count = int(
                comm.allreduce(retained_schur_class_count, op=MPI.SUM)
            )
            summed_rank_local_retained_schur_bytes = int(
                comm.allreduce(retained_schur_bytes, op=MPI.SUM)
            )
        else:
            summed_rank_local_retained_schur_class_count = None
            summed_rank_local_retained_schur_bytes = None
        live_state.update(
            fine_action=True,
        )
        emit_lifecycle(
            "local_schur_action_ready",
            fine_action_relative_error=fine_action_error,
            rank_local_retained_schur_class_count=retained_schur_class_count,
            rank_local_retained_schur_bytes=retained_schur_bytes,
            summed_rank_local_retained_schur_class_count=(
                summed_rank_local_retained_schur_class_count
            ),
            summed_rank_local_retained_schur_bytes=summed_rank_local_retained_schur_bytes,
        )
        operator, operator_context = create_matrix_free_condensed_operator(
            blocks, fine_operator=fine_action
        )
        owned.append(operator)
        live_state["matrix_free_operator"] = True
        basis = build_active_trace_floquet_basis(
            request.static_condensed_system,
            request.function_space,
            request.config,
            request.floquet_data,
            fine_action,
        )
        live_state["basis"] = True
        emit_lifecycle(
            "basis_ready",
            global_basis_dimension=len(basis),
        )
        if action_only:
            owner_plan = build_owner_local_slab_plan(
                request.static_condensed_system,
                request.function_space.mesh,
                domain_z=(request.config.domain_z_min, request.config.domain_z_max),
                num_slabs=16,
                overlap_fraction=0.125 if m3a_profile else 0.25,
            )
            partition_audit = {
                "matrix_materialized": False,
                "coverage_pass": True,
                "num_slabs": len(owner_plan.slab_owners),
                "slab_row_counts": list(owner_plan.slab_row_counts),
                "subdomain_owners": list(owner_plan.slab_owners),
            }
            if m3a_profile:
                partition_audit.update(
                    {
                        "overlap_fraction": 0.125,
                        "interpolation": "partition",
                    }
                )
            diagonal, diagonal_audit = build_owner_local_slab_diagonal(
                request.static_condensed_system
            )
            owned.append(diagonal)
            global_scale = float(diagonal_audit["global_diagonal_max_abs"])
            shift = diagonal
            absolute = np.abs(shift.getArray(readonly=True))
            shift.getArray()[:] = (
                -1j * 0.1 * np.maximum(absolute, 1.0e-12 * global_scale)
            )
        else:
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
            shift.getArray()[:] = (
                -1j * 0.1 * np.maximum(absolute, 1.0e-12 * global_scale)
            )
            diagonal.destroy()
            owned.remove(diagonal)
        live_state["shift"] = True
        shifted_context = _ShiftedFineAction(fine_action, shift)
        shifted_fine = PETSc.Mat().createPython(
            fine_action.getSizes(), context=shifted_context, comm=fine_action.getComm()
        )
        owned.append(shifted_fine)
        owned.remove(shift)
        shifted_fine.setUp()
        live_state["shifted_action"] = True
        if action_only:
            smoother = DistributedPhysicalSlabSmoother.from_owner_local_plan(
                request.static_condensed_system,
                owner_plan,
                ilu_levels=0,
                interpolation=("partition" if m3a_profile else "basic"),
                precomputed_diagonal_shift=shift,
                two_step_action_operator=shifted_fine,
                progress=None,
                setup_observer=(
                    smoother_setup_observer if lifecycle_observer is not None else None
                ),
            )
        else:
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
                setup_observer=(
                    smoother_setup_observer if lifecycle_observer is not None else None
                ),
            )
        owned.append(smoother)
        if m3a_profile:
            smoother_setup = smoother.diagnostics
            partition_audit.update(
                {
                    "partition_weight_sum_error": smoother_setup[
                        "partition_weight_sum_error"
                    ],
                    "partition_weight_min": smoother_setup["partition_weight_min"],
                    "partition_weight_max": smoother_setup["partition_weight_max"],
                }
            )
        live_state["slab_factors"] = len(smoother.local_subdomains)
        coarse = SparseGalerkinTwoLevelPc(operator, smoother, basis, post_smooth=True)
        owned.append(coarse)
        live_state["coarse"] = True
        emit_lifecycle(
            "coarse_operator_ready",
            global_coarse_dimension=len(basis),
        )
        assembled_matrix_released = False
        if exact_profile and not action_only:
            blocks.release_f()
            live_state["active_F"] = False
            emit_lifecycle(
                "F_released",
            )
            release_assembled_matrix()
            assembled_matrix_released = True
            live_state["borrowed_augmented_A"] = False
            emit_lifecycle(
                "A_released",
            )
        solution = operator.createVecRight()
        monitor_solution = operator.createVecRight()
        residual_work = operator.createVecLeft()
        owned.extend((solution, monitor_solution, residual_work))
        live_state.update(solution=True, monitor_solution=True, residual_work=True)
        solution.set(0.0)
        rhs_norm = float(rhs.norm())
        reported_history: list[tuple[int, float]] = []
        condensed_samples: list[tuple[int, float]] = []
        sampled_iterations = {0}
        true_residual_sampled_iterations: set[int] = set()
        initial_condensed = _relative_residual(
            operator, rhs, solution, residual_work, rhs_norm
        )
        reported_history.append((0, 1.0))
        condensed_samples.append((0, initial_condensed))
        if residual_observer is not None:
            residual_observer(0, 1.0, initial_condensed)
        if true_residual_vector_observer is not None:
            true_residual_vector_observer(0, residual_work, rhs_norm)
            true_residual_sampled_iterations.add(0)
        ksp = PETSc.KSP().create(comm)
        owned.append(ksp)
        live_state["outer_ksp"] = True
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setGMRESRestart(90)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=int(screen_iterations))
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(coarse)
        live_state["outer_pc"] = True
        ksp.setUp()
        emit_lifecycle(
            "outer_ksp_setup",
            ksp_type=str(ksp.getType()),
        )
        setup_seconds = perf_counter() - started

        def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
            reported = float(residual_norm) / max(rhs_norm, _TINY)
            if not reported_history or reported_history[-1][0] != iteration:
                reported_history.append((int(iteration), reported))
            should_sample = iteration in (10, 20) or (
                true_residual_vector_observer is not None
                and iteration in _TRUE_RESIDUAL_CARRIER_ITERATIONS
            )
            if should_sample and iteration not in sampled_iterations:
                current_solution = current.buildSolution(monitor_solution)
                condensed = _relative_residual(
                    operator, rhs, current_solution, residual_work, rhs_norm
                )
                condensed_samples.append((int(iteration), condensed))
                sampled_iterations.add(iteration)
                if residual_observer is not None:
                    residual_observer(int(iteration), reported, condensed)
                if (
                    true_residual_vector_observer is not None
                    and iteration in _TRUE_RESIDUAL_CARRIER_ITERATIONS
                ):
                    true_residual_vector_observer(
                        int(iteration), residual_work, rhs_norm
                    )
                    true_residual_sampled_iterations.add(int(iteration))

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
        if (
            true_residual_vector_observer is not None
            and iterations in _TRUE_RESIDUAL_CARRIER_ITERATIONS
            and iterations not in true_residual_sampled_iterations
        ):
            true_residual_vector_observer(iterations, residual_work, rhs_norm)
            true_residual_sampled_iterations.add(iterations)
        emit_lifecycle(
            "outer_ksp_solved",
            converged_reason=reason,
            iterations=iterations,
            reported_relative_residual=reported,
        )

        recovery_started = perf_counter()
        auxiliary = recover_petsc_auxiliary(blocks, solution)
        owned.append(auxiliary)
        live_state["recovered_auxiliary"] = True
        augmented = (
            request_rhs.duplicate()
            if action_only or exact_profile
            else request_operator.createVecRight()
        )
        owned.append(augmented)
        live_state["augmented_solution"] = True
        combine_petsc_augmented_solution(blocks, solution, auxiliary, augmented)
        if (
            augmented.getSize() != request_rhs.getSize()
            or augmented.getSize() != request_operator_size[1]
            or augmented.getOwnershipRange() != request_rhs.getOwnershipRange()
            or augmented.getOwnershipRange() != request_operator_columns
        ):
            raise ValueError(
                "returned augmented solution layout does not match the borrowed "
                "RHS and operator columns"
            )
        emit_lifecycle(
            "augmented_solution_recovered",
        )
        full_augmented = full_augmented_relative_residual(
            blocks, solution, auxiliary, fine_operator=fine_action
        )
        emit_lifecycle(
            "full_augmented_residual_complete",
            full_augmented_true_residual=float(full_augmented),
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
            "matrix_type": "python_action_only" if action_only else "assembled",
            "global_A_materialized": not action_only,
            "global_F_materialized": not action_only and not exact_profile,
            "candidate": {
                "outer_ksp": str(ksp.getType()),
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": int(screen_iterations),
                **(
                    {
                        "num_slabs": 16,
                        "overlap_fraction": 0.125,
                        "interpolation": "partition",
                        "absorption_shift": 0.1,
                    }
                    if m3a_profile
                    else {
                        "num_slabs": 16,
                        "overlap_fraction": 0.25,
                        "absorption_shift": 0.1,
                    }
                ),
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
                "global_A_materialized": not action_only,
                "global_F_materialized": not action_only and not exact_profile,
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
        returned_solution_transferred = True
        live_state["returned_augmented_solution"] = True
        return snapshot, audit
    finally:
        for item in reversed(owned):
            item.destroy()
        for name in (
            "active_F",
            "C",
            "D",
            "H",
            "extracted_active_rhs",
            "extracted_aux_rhs",
            "condensed_active_rhs",
            "fine_action",
            "matrix_free_operator",
            "basis",
            "shifted_action",
            "shift",
            "coarse",
            "solution",
            "monitor_solution",
            "residual_work",
            "outer_ksp",
            "outer_pc",
            "recovered_auxiliary",
            "augmented_solution",
        ):
            live_state[name] = False
        live_state["slab_factors"] = 0
        emit_lifecycle(
            "solver_owned_objects_released",
            normal_completion=returned_solution_transferred,
            returned_solution_transferred=returned_solution_transferred,
        )


def solve_assembled_static_condensed_fgmres(
    request: Stage4ExternalLinearSolverRequest,
    *,
    screen_iterations: Literal[20],
    residual_observer: Callable[[int, float, float], None] | None = None,
    solver_profile: Literal[
        "assembled", "assembled_setup_then_static_local_schur_matrix_free_solve"
    ] = "assembled",
    release_assembled_matrix: Callable[[], None] | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Provide the assembled/released static-local-Schur authority."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        solver_profile=solver_profile,
        release_assembled_matrix=release_assembled_matrix,
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_static_condensed_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: Literal[20] = 20,
    residual_observer: Callable[[int, float, float], None] | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Provide the borrowed action-only authority."""

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        solver_profile="never_materialized_owner_local",
        lifecycle_observer=lifecycle_observer,
    )


def solve_never_materialized_overlap0125_partition_fgmres(
    request: Stage4NeverMaterializedLinearSolverRequest,
    *,
    screen_iterations: Literal[20, 100, 200, 3000] = 20,
    residual_observer: Callable[[int, float, float], None] | None = None,
    true_residual_vector_observer: Callable[[int, PETSc.Vec, float], None]
    | None = None,
    lifecycle_observer: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[Stage4ExternalLinearSolverSnapshot, dict[str, Any]]:
    """Run the opt-in overlap-0.125 partition-weighted slab profile.

    Numerically qualified on Case100 p6/h10; resource-scalability is not
    qualified for 0.7 nm.
    """

    return _solve_static_condensed_fgmres_core(
        request,
        screen_iterations=screen_iterations,
        residual_observer=residual_observer,
        true_residual_vector_observer=true_residual_vector_observer,
        solver_profile="never_materialized_owner_local_overlap0125_partition",
        lifecycle_observer=lifecycle_observer,
    )
