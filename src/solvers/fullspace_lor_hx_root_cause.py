"""Small M0-only diagnostics for the multiplicative LOR-HX route.

This module deliberately does not alter :class:`NativeComplexLORHX`.  It
replays the already frozen sequential-v1 component order with either the
existing scalar PCGAMG solve or one fixed diagnostic LU/MUMPS solve, and it
provides the exact low-order edge reference used by the M0 oracle.
"""

from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

import numpy as np
from petsc4py import PETSc

from .fullspace_lor_native_hx import LOR_HX_EDGE_JACOBI_OMEGA


M0_DIRECT_BACKEND = "petsc-preonly-lu-mumps"
M0_OUTER_GMRES_RESTART = 20
M0_OUTER_GMRES_MAX_IT = 200
M0_OUTER_GMRES_RTOL = 1.0e-8
M0_OUTER_GMRES_ATOL = 0.0
M0_OUTER_CYCLE_MAX_IT = 20
M0_OUTER_MAX_CYCLES = 10
M0_OUTER_EXPLICIT_CHECKPOINTS = (0, 1, 2, 5, 10)
M0_OUTER_CHECKPOINTS = (0, 1, 2, 5, 10, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200)
M0_TRACE_NAMES = (
    "edge_jacobi_pre",
    "gradient",
    "pi_x",
    "pi_y",
    "pi_z",
    "edge_jacobi_post",
)


def _residual_ratio(residual: PETSc.Vec, rhs: PETSc.Vec) -> float:
    return float(residual.norm()) / max(float(rhs.norm()), np.finfo(float).tiny)


def _apply(matrix: Any, vector: PETSc.Vec) -> PETSc.Vec:
    result = matrix.createVecLeft()
    matrix.mult(vector, result)
    return result


def solve_exact(matrix: Any, rhs: PETSc.Vec, *, label: str) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Solve one small diagnostic system with the single frozen direct backend."""

    ksp = PETSc.KSP().create(matrix.getComm())
    solution = matrix.createVecRight()
    action = matrix.createVecLeft()
    residual = matrix.createVecLeft()
    try:
        ksp.setOperators(matrix)
        ksp.setType("preonly")
        pc = ksp.getPC()
        pc.setType("lu")
        pc.setFactorSolverType("mumps")
        ksp.setUp()
        solution.set(0.0 + 0.0j)
        ksp.solve(rhs, solution)
        matrix.mult(solution, action)
        rhs.copy(residual)
        residual.axpy(PETSc.ScalarType(-1.0), action)
        reason = int(ksp.getConvergedReason())
        facts = {
            "label": label,
            "backend": M0_DIRECT_BACKEND,
            "ksp_type": "preonly",
            "pc_type": "lu",
            "factor_solver_type": "mumps",
            "reason": reason,
            "iterations": int(ksp.getIterationNumber()),
            "rhs_norm": float(rhs.norm()),
            "solution_norm": float(solution.norm()),
            "residual_norm": float(residual.norm()),
            "relative_residual": _residual_ratio(residual, rhs),
            "finite": bool(
                np.all(np.isfinite(np.asarray(solution.array)))
                and np.all(np.isfinite(np.asarray(residual.array)))
            ),
        }
        if reason <= 0 or not facts["finite"]:
            raise RuntimeError(f"{label} diagnostic direct solve failed: {facts}")
        return solution, facts
    finally:
        action.destroy()
        residual.destroy()
        ksp.destroy()


class DiagnosticDirectSolver:
    """Reusable small diagnostic PREONLY+LU/MUMPS factor."""

    def __init__(self, matrix: Any, *, label: str) -> None:
        self.matrix = matrix
        self.label = label
        self.ksp = PETSc.KSP().create(matrix.getComm())
        self.ksp.setOperators(matrix)
        self.ksp.setType("preonly")
        pc = self.ksp.getPC()
        pc.setType("lu")
        pc.setFactorSolverType("mumps")
        self.ksp.setUp()
        self.solve_count = 0

    def solve(self, rhs: PETSc.Vec) -> tuple[PETSc.Vec, dict[str, Any]]:
        solution = self.matrix.createVecRight()
        action = self.matrix.createVecLeft()
        residual = self.matrix.createVecLeft()
        try:
            solution.set(0.0 + 0.0j)
            self.ksp.solve(rhs, solution)
            self.matrix.mult(solution, action)
            rhs.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), action)
            reason = int(self.ksp.getConvergedReason())
            facts = {
                "label": self.label,
                "backend": M0_DIRECT_BACKEND,
                "ksp_type": "preonly",
                "pc_type": "lu",
                "factor_solver_type": "mumps",
                "reason": reason,
                "iterations": int(self.ksp.getIterationNumber()),
                "solve_count": int(self.solve_count + 1),
                "rhs_norm": float(rhs.norm()),
                "solution_norm": float(solution.norm()),
                "residual_norm": float(residual.norm()),
                "relative_residual": _residual_ratio(residual, rhs),
                "finite": bool(
                    np.all(np.isfinite(np.asarray(solution.array)))
                    and np.all(np.isfinite(np.asarray(residual.array)))
                ),
            }
            self.solve_count += 1
            if reason <= 0 or not facts["finite"]:
                raise RuntimeError(f"{self.label} diagnostic direct solve failed: {facts}")
            return solution, facts
        finally:
            action.destroy()
            residual.destroy()

    def solve_lean(self, rhs: PETSc.Vec) -> tuple[PETSc.Vec, dict[str, Any]]:
        """Apply the reused direct factor without retaining diagnostic traces."""

        solution = self.matrix.createVecRight()
        solution.set(0.0 + 0.0j)
        self.ksp.solve(rhs, solution)
        reason = int(self.ksp.getConvergedReason())
        self.solve_count += 1
        finite = bool(np.all(np.isfinite(np.asarray(solution.array))))
        facts = {
            "label": self.label,
            "backend": M0_DIRECT_BACKEND,
            "ksp_type": "preonly",
            "pc_type": "lu",
            "factor_solver_type": "mumps",
            "reason": reason,
            "solve_count": int(self.solve_count),
            "finite": finite,
        }
        if reason <= 0 or not finite:
            solution.destroy()
            raise RuntimeError(f"{self.label} diagnostic direct solve failed: {facts}")
        return solution, facts

    def destroy(self) -> None:
        if self.ksp is not None:
            self.ksp.destroy()
            self.ksp = None


class _OuterActionContext:
    def __init__(self, apply_action: Callable[[PETSc.Vec], PETSc.Vec]) -> None:
        self.apply_action = apply_action
        self.matvec_count = 0

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        action = self.apply_action(source)
        try:
            action.copy(target)
        finally:
            action.destroy()
        self.matvec_count += 1


class _OuterPCContext:
    def __init__(self, apply_preconditioner: Callable[[PETSc.Vec], PETSc.Vec]) -> None:
        self.apply_preconditioner = apply_preconditioner
        self.solver_pc_apply_count = 0
        self.monitor_reconstruction_pc_applies = 0
        self.phase = "solver"

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        correction = self.apply_preconditioner(source)
        try:
            correction.copy(target)
        finally:
            correction.destroy()
        if self.phase == "monitor_reconstruction":
            self.monitor_reconstruction_pc_applies += 1
        else:
            self.solver_pc_apply_count += 1


def run_outer_right_gmres(
    rhs: PETSc.Vec,
    apply_action: Callable[[PETSc.Vec], PETSc.Vec],
    apply_preconditioner: Callable[[PETSc.Vec], PETSc.Vec],
    *,
    label: str,
) -> dict[str, Any]:
    """Run diagnostic right-GMRES in explicit twenty-step replacement cycles."""

    comm = rhs.getComm()
    sizes = (rhs.getLocalSize(), rhs.getSize())
    action_context = _OuterActionContext(apply_action)
    operator = PETSc.Mat().createPython(
        (sizes, sizes), context=action_context, comm=comm
    )
    operator.setUp()
    pc_context = _OuterPCContext(apply_preconditioner)
    solution = operator.createVecRight()
    monitor_work = operator.createVecRight()
    solution.set(0.0 + 0.0j)
    monitor_work.set(0.0 + 0.0j)
    rhs_norm = max(float(rhs.norm()), np.finfo(float).tiny)
    history: list[dict[str, Any]] = []
    explicit_by_iteration: dict[int, float] = {}
    monitor_action_count = 0
    final_action_count = 0
    cycles: list[dict[str, Any]] = []
    active_ksp: PETSc.KSP | None = None
    started = time.perf_counter()

    def row_for(iteration: int, reported: float) -> dict[str, Any]:
        iteration = int(iteration)
        for row in history:
            if int(row["iteration"]) == iteration:
                row["reported_residual"] = float(reported)
                row["reported_relative"] = float(reported / rhs_norm)
                row["matvec_count"] = int(action_context.matvec_count)
                row["solver_pc_apply_count"] = int(pc_context.solver_pc_apply_count)
                row["monitor_reconstruction_pc_applies"] = int(
                    pc_context.monitor_reconstruction_pc_applies
                )
                row["monitor_action_count"] = int(monitor_action_count)
                return row
        row = {
            "iteration": iteration,
            "reported_residual": float(reported),
            "reported_relative": float(reported / rhs_norm),
            "explicit_true_residual": None,
            "matvec_count": int(action_context.matvec_count),
            "solver_pc_apply_count": int(pc_context.solver_pc_apply_count),
            "monitor_reconstruction_pc_applies": int(
                pc_context.monitor_reconstruction_pc_applies
            ),
            "monitor_action_count": int(monitor_action_count),
            "elapsed_seconds": float(time.perf_counter() - started),
        }
        history.append(row)
        return row

    def record_explicit(iteration: int, current_solution: PETSc.Vec) -> float:
        nonlocal monitor_action_count
        iteration = int(iteration)
        if iteration in explicit_by_iteration:
            return explicit_by_iteration[iteration]
        action = apply_action(current_solution)
        monitor_action_count += 1
        true_residual = rhs.copy()
        true_residual.axpy(PETSc.ScalarType(-1.0), action)
        true_relative = float(true_residual.norm() / rhs_norm)
        row = next(
            row for row in history if int(row["iteration"]) == iteration
        )
        row["explicit_true_residual"] = true_relative
        row["matvec_count"] = int(action_context.matvec_count)
        row["solver_pc_apply_count"] = int(pc_context.solver_pc_apply_count)
        row["monitor_reconstruction_pc_applies"] = int(
            pc_context.monitor_reconstruction_pc_applies
        )
        row["monitor_action_count"] = int(monitor_action_count)
        explicit_by_iteration[iteration] = true_relative
        action.destroy()
        true_residual.destroy()
        return true_relative

    row_for(0, rhs_norm)
    record_explicit(0, solution)

    try:
        cumulative_iteration = 0
        final_reason = 0
        for cycle_index in range(M0_OUTER_MAX_CYCLES):
            cycle_start = cumulative_iteration
            cycle_solver_pc_start = pc_context.solver_pc_apply_count
            cycle_monitor_pc_start = pc_context.monitor_reconstruction_pc_applies
            cycle_monitor_action_start = monitor_action_count
            active_ksp = PETSc.KSP().create(comm)
            active_ksp.setOperators(operator)
            active_ksp.setType("gmres")
            active_ksp.setGMRESRestart(M0_OUTER_GMRES_RESTART)
            active_ksp.setPCSide(PETSc.PC.Side.RIGHT)
            active_ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            active_ksp.setInitialGuessNonzero(cycle_index != 0)
            active_ksp.setTolerances(
                rtol=M0_OUTER_GMRES_RTOL,
                atol=M0_OUTER_GMRES_ATOL,
                max_it=M0_OUTER_CYCLE_MAX_IT,
            )
            pc = active_ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(pc_context)
            active_ksp.setUp()

            def monitor(_current: Any, iteration: int, reported: float) -> None:
                global_iteration = cycle_start + int(iteration)
                row_for(global_iteration, float(reported))
                if (
                    cycle_index == 0
                    and int(iteration) in M0_OUTER_EXPLICIT_CHECKPOINTS
                    and global_iteration not in explicit_by_iteration
                ):
                    pc_context.phase = "monitor_reconstruction"
                    try:
                        borrowed_solution = active_ksp.buildSolution(monitor_work)
                        if borrowed_solution is None:
                            raise RuntimeError("PETSc KSP buildSolution returned None")
                        monitor_solution = borrowed_solution.copy()
                    finally:
                        pc_context.phase = "solver"
                    try:
                        record_explicit(global_iteration, monitor_solution)
                    finally:
                        monitor_solution.destroy()

            active_ksp.setMonitor(monitor)
            active_ksp.solve(rhs, solution)
            local_iterations = int(active_ksp.getIterationNumber())
            final_reason = int(active_ksp.getConvergedReason())
            cumulative_iteration = cycle_start + local_iterations
            row = row_for(cumulative_iteration, float(active_ksp.getResidualNorm()))
            explicit_final = record_explicit(cumulative_iteration, solution)
            cycles.append(
                {
                    "cycle_index": int(cycle_index),
                    "start_iteration": int(cycle_start),
                    "iterations": int(local_iterations),
                    "cumulative_end_iteration": int(cumulative_iteration),
                    "reason": int(final_reason),
                    "initial_guess_nonzero": bool(cycle_index != 0),
                    "reported_final_relative": float(row["reported_relative"]),
                    "explicit_true_residual": float(explicit_final),
                    "solver_pc_apply_count": int(
                        pc_context.solver_pc_apply_count - cycle_solver_pc_start
                    ),
                    "monitor_reconstruction_pc_applies": int(
                        pc_context.monitor_reconstruction_pc_applies
                        - cycle_monitor_pc_start
                    ),
                    "monitor_action_count": int(
                        monitor_action_count - cycle_monitor_action_start
                    ),
                }
            )
            active_ksp.destroy()
            active_ksp = None
            true_pass = explicit_final <= M0_OUTER_GMRES_RTOL
            if true_pass or cumulative_iteration >= M0_OUTER_GMRES_MAX_IT:
                break
            if final_reason < 0 and final_reason != -3:
                break
            if local_iterations == 0:
                break

        first_true_pass = next(
            (
                int(row["iteration"])
                for row in history
                if row["explicit_true_residual"] is not None
                and float(row["explicit_true_residual"]) <= M0_OUTER_GMRES_RTOL
            ),
            None,
        )
        reported_first_pass = next(
            (
                int(row["iteration"])
                for row in history
                if float(row["reported_relative"]) <= M0_OUTER_GMRES_RTOL
            ),
            None,
        )
        statuses = {}
        for checkpoint in M0_OUTER_CHECKPOINTS:
            if checkpoint in explicit_by_iteration:
                statuses[str(checkpoint)] = "measured"
            elif checkpoint > cumulative_iteration and final_reason < 0:
                statuses[str(checkpoint)] = "not_reached"
            else:
                statuses[str(checkpoint)] = "not_run_after_convergence"
        final_solution = solution.copy()
        final_action = apply_action(final_solution)
        final_action_count = 1
        final_true_residual = rhs.copy()
        final_true_residual.axpy(PETSc.ScalarType(-1.0), final_action)
        return {
            "label": label,
            "settings": {
                "ksp_type": "gmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": M0_OUTER_GMRES_RESTART,
                "cycle_max_it": M0_OUTER_CYCLE_MAX_IT,
                "max_cycles": M0_OUTER_MAX_CYCLES,
                "max_it": M0_OUTER_GMRES_MAX_IT,
                "rtol": M0_OUTER_GMRES_RTOL,
                "atol": M0_OUTER_GMRES_ATOL,
                "zero_initial_guess": True,
                "residual_replacement": True,
            },
            "history": history,
            "checkpoint_status": statuses,
            "cycles": cycles,
            "cycle_count": len(cycles),
            "reason": final_reason,
            "iterations": cumulative_iteration,
            "first_true_pass_iteration": first_true_pass,
            "reported_first_pass_iteration": reported_first_pass,
            "matvec_count": int(action_context.matvec_count),
            "solver_pc_apply_count": int(pc_context.solver_pc_apply_count),
            "monitor_reconstruction_pc_applies": int(
                pc_context.monitor_reconstruction_pc_applies
            ),
            "monitor_action_count": int(monitor_action_count),
            "final_action_count": int(final_action_count),
            "total_pc_apply_count": int(
                pc_context.solver_pc_apply_count
                + pc_context.monitor_reconstruction_pc_applies
            ),
            "final_solution": final_solution,
            "final_action": final_action,
            "final_true_residual": final_true_residual,
        }
    finally:
        if active_ksp is not None:
            active_ksp.destroy()
        monitor_work.destroy()
        solution.destroy()
        operator.destroy()


def destroy_outer_right_gmres(result: dict[str, Any]) -> None:
    for key in (
        "final_solution",
        "final_action",
        "final_true_residual",
    ):
        vector = result.pop(key, None)
        if vector is not None:
            vector.destroy()


def _production_nodal_solver(fixture: Any) -> Callable[[PETSc.Vec], tuple[PETSc.Vec, dict[str, Any]]]:
    def solve(rhs: PETSc.Vec) -> tuple[PETSc.Vec, dict[str, Any]]:
        delta = rhs.duplicate()
        delta.set(0.0 + 0.0j)
        fixture.hx._nodal_ksp.solve(rhs, delta)
        return delta, {
            "backend": "existing-production-pcgamg",
            "ksp_type": "preonly",
            "pc_type": "gamg",
        }

    return solve


def replay_multiplicative_components(
    fixture: Any,
    low_residual: PETSc.Vec,
    nodal_solver: Callable[[PETSc.Vec], tuple[PETSc.Vec, dict[str, Any]]],
    *,
    capture_traces: bool = True,
) -> dict[str, Any]:
    """Replay sequential-v1 using the supplied nodal solve, once per component."""

    hx = fixture.hx
    remaining = low_residual.copy()
    result = low_residual.duplicate()
    result.set(0.0 + 0.0j)
    traces: list[dict[str, Any]] = []

    def save_trace(
        name: str,
        rhs: PETSc.Vec | None,
        nodal_delta: PETSc.Vec | None,
        edge_delta: PETSc.Vec,
        solver_facts: dict[str, Any] | None,
        update_residual: bool,
    ) -> None:
        edge_action = _apply(fixture.edge_matrix, edge_delta)
        if update_residual:
            remaining.axpy(PETSc.ScalarType(-1.0), edge_action)
        if capture_traces:
            traces.append(
                {
                    "name": name,
                    "rhs": None if rhs is None else rhs.copy(),
                    "nodal_delta": None if nodal_delta is None else nodal_delta.copy(),
                    "edge_delta": edge_delta.copy(),
                    "edge_action": edge_action.copy(),
                    "remaining": remaining.copy(),
                    "result": result.copy(),
                    "solver": dict(solver_facts or {}),
                }
            )
        edge_action.destroy()

    try:
        edge_delta = remaining.duplicate()
        edge_delta.array[:] = (
            LOR_HX_EDGE_JACOBI_OMEGA
            * np.asarray(low_residual.array)
            * hx._edge_diagonal_inverse
        )
        result.axpy(PETSc.ScalarType(1.0), edge_delta)
        save_trace("edge_jacobi_pre", None, None, edge_delta, None, True)
        edge_delta.destroy()

        for name, restriction, prolongation in (
            ("gradient", hx._gradient_adjoint, hx._gradient),
            ("pi_x", hx._vector_restrictions[0], hx._vector_prolongations[0]),
            ("pi_y", hx._vector_restrictions[1], hx._vector_prolongations[1]),
            ("pi_z", hx._vector_restrictions[2], hx._vector_prolongations[2]),
        ):
            rhs = fixture.node_matrix.createVecRight()
            restriction.mult(remaining, rhs)
            nodal_delta, solver_facts = nodal_solver(rhs)
            edge_delta = fixture.edge_matrix.createVecRight()
            prolongation.mult(nodal_delta, edge_delta)
            result.axpy(PETSc.ScalarType(1.0), edge_delta)
            save_trace(name, rhs, nodal_delta, edge_delta, solver_facts, True)
            rhs.destroy()
            nodal_delta.destroy()
            edge_delta.destroy()

        edge_delta = remaining.duplicate()
        edge_delta.array[:] = (
            LOR_HX_EDGE_JACOBI_OMEGA
            * np.asarray(remaining.array)
            * hx._edge_diagonal_inverse
        )
        result.axpy(PETSc.ScalarType(1.0), edge_delta)
        save_trace("edge_jacobi_post", None, None, edge_delta, None, False)
        edge_delta.destroy()
        return {"result": result, "remaining": remaining, "traces": traces}
    except BaseException:
        result.destroy()
        remaining.destroy()
        for trace in traces:
            for vector in trace.values():
                if hasattr(vector, "destroy"):
                    vector.destroy()
        raise


def low_input_from_high_dual(fixture: Any, high_residual: PETSc.Vec) -> tuple[PETSc.Vec, tuple[np.ndarray, np.ndarray]]:
    owner_ids, owner_values = fixture._restrict_high_dual(high_residual)
    low_input = fixture._full_lor_dual_vector_from_high_owner_packet(
        owner_ids, owner_values
    )
    return low_input, (owner_ids, owner_values)


def low_dual_owner_packet(
    fixture: Any, vector: PETSc.Vec
) -> tuple[np.ndarray, np.ndarray]:
    """Build one additive owner packet for a low-order dual trace."""

    from dolfinx import fem

    work_space = fixture.lor_edge_floquet.mpc.function_space
    field = fem.Function(work_space)
    owned = int(work_space.dofmap.index_map.size_local)
    field.x.petsc_vec.set(0.0 + 0.0j)
    field.x.petsc_vec.array[:owned] = np.asarray(
        vector.array[:owned], dtype=np.complex128
    )
    field.x.scatter_forward()
    fixture.lor_edge_floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    cell_count = int(fixture.lor_mesh.topology.index_map(3).size_local)
    cell_info = np.asarray(
        fixture.lor_mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )

    def chunks():
        batch_start = 0
        batch: list[np.ndarray] = []
        for cell in range(cell_count):
            local_dofs = np.asarray(
                work_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            values = np.asarray(field.x.array[local_dofs], dtype=np.complex128).copy()
            work_space.element.Tt_apply(
                values, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            batch.append(values[fixture._lor_p1_transfer_local_indices[cell]])
            if len(batch) == 32 or cell + 1 == cell_count:
                yield batch_start, np.asarray(batch, dtype=np.complex128)
                batch_start = cell + 1
                batch = []

    owner_packet = fixture.lor_raw_topology.route_owner_cell_chunks_additive(chunks())
    del field
    return owner_packet


def lift_low_primal(fixture: Any, low_vector: PETSc.Vec) -> PETSc.Vec:
    owner_ids, owner_values = fixture._route_low_owner_packet(low_vector)
    expected_ids = np.asarray(fixture.lor_topology.owned_edge_ids, dtype=np.uint32)
    if not np.array_equal(owner_ids, expected_ids):
        raise RuntimeError("M0 low/high owner inventories differ")
    unique_values = fixture.lor_topology.pull_owner_unique_values(
        owner_ids, owner_values
    )
    return fixture._reconstruct_high_from_unique(unique_values)


def exact_edge_reference(
    fixture: Any, high_residual: PETSc.Vec
) -> dict[str, Any]:
    """Run the M0 exact LOR edge inverse reference pipeline."""

    low_input, owner_packet = low_input_from_high_dual(fixture, high_residual)
    low_solution, direct_facts = solve_exact(
        fixture.edge_matrix, low_input, label="edge"
    )
    high_correction = lift_low_primal(fixture, low_solution)
    high_action = fixture.apply_high_action_copy(high_correction)
    return {
        "low_input": low_input,
        "low_solution": low_solution,
        "high_correction": high_correction,
        "high_action": high_action,
        "owner_packet_ids": owner_packet[0],
        "owner_packet_values": owner_packet[1],
        "direct_facts": direct_facts,
    }


def destroy_replay(result: dict[str, Any]) -> None:
    for key in ("result", "remaining"):
        vector = result.pop(key, None)
        if vector is not None:
            vector.destroy()
    for trace in result.pop("traces", ()):
        for vector in trace.values():
            if hasattr(vector, "destroy"):
                vector.destroy()


__all__ = (
    "M0_DIRECT_BACKEND",
    "M0_OUTER_CHECKPOINTS",
    "M0_OUTER_CYCLE_MAX_IT",
    "M0_OUTER_EXPLICIT_CHECKPOINTS",
    "M0_OUTER_GMRES_ATOL",
    "M0_OUTER_GMRES_MAX_IT",
    "M0_OUTER_GMRES_RESTART",
    "M0_OUTER_GMRES_RTOL",
    "M0_OUTER_MAX_CYCLES",
    "M0_TRACE_NAMES",
    "DiagnosticDirectSolver",
    "destroy_outer_right_gmres",
    "destroy_replay",
    "exact_edge_reference",
    "lift_low_primal",
    "low_dual_owner_packet",
    "low_input_from_high_dual",
    "replay_multiplicative_components",
    "run_outer_right_gmres",
    "solve_exact",
)
