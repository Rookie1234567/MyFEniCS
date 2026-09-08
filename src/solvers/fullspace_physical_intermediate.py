"""Small reusable building blocks for the Task039 physical middle level.

The module contains the numerical operation used by the candidate, but does
not choose a mesh, material, or production preconditioner.  A matrix-free
physical action is accepted as a callback, the p4/p2/p1 transfers are supplied
by the same-mesh owner-transfer layer, and only the bottom solve is injected.
This keeps the p4 experiment opt-in while making the complex MR formula and
the shifted auxiliary V-cycle independently testable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import ExitStack
from copy import deepcopy
import time
from typing import Any

import numpy as np


INTERMEDIATE_METHOD = "physical_intermediate_p4_shifted_aux_v1"
OUTER_RESTART = 32
OUTER_MAX_IT = 512
INTERMEDIATE_RESTART = 12
INTERMEDIATE_MAX_IT = 36
INTERMEDIATE_RESIDUAL_LIMIT = 1.0e-2
SHIFT_SIGMA = 0.5
SMOOTHING_STEPS = 3
LOCAL_FACTOR_MAX_ROWS = 4096
LOCAL_FACTOR_MAX_BYTES = 512 * 1024 * 1024


def _new_like(value: Any) -> Any:
    duplicate = getattr(value, "duplicate", None)
    if callable(duplicate):
        return duplicate()
    return np.empty_like(np.asarray(value))


def _copy(value: Any) -> Any:
    result = _new_like(value)
    _copy_into(result, value)
    return result


def _copy_into(target: Any, source: Any) -> None:
    if callable(getattr(source, "copy", None)) and hasattr(target, "set"):
        source.copy(target)
        return
    np.copyto(np.asarray(target), np.asarray(source))


def _zero(value: Any) -> None:
    setter = getattr(value, "set", None)
    if callable(setter):
        setter(0.0 + 0.0j)
    else:
        np.asarray(value).fill(0.0 + 0.0j)


def _destroy(value: Any) -> None:
    destroy = getattr(value, "destroy", None)
    if callable(destroy):
        destroy()


def _norm(value: Any) -> float:
    method = getattr(value, "norm", None)
    result = float(method()) if callable(method) else float(np.linalg.norm(value))
    if not np.isfinite(result):
        raise RuntimeError("physical intermediate vector is non-finite")
    return result


def _dot(left: Any, right: Any) -> complex:
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        return complex(np.vdot(np.asarray(left), np.asarray(right)))
    method = getattr(left, "dot", None)
    if callable(method):
        # petsc4py 3.19 Vec.dot conjugates its argument (verified against vdot).
        return complex(right.dot(left))
    return complex(np.vdot(np.asarray(left), np.asarray(right)))


def _axpy(target: Any, alpha: complex, source: Any) -> None:
    method = getattr(target, "axpy", None)
    if callable(method):
        target.axpy(alpha, source)
    else:
        np.asarray(target)[:] += alpha * np.asarray(source)


def _scale(value: Any, factor: complex) -> None:
    method = getattr(value, "scale", None)
    if callable(method):
        method(factor)
    else:
        np.asarray(value)[:] *= factor


def apply_owned(action: Any, source: Any, target: Any | None = None) -> Any:
    """Apply an action through the explicit ``source, target`` contract."""
    owned_target = target if target is not None else _new_like(source)
    try:
        function = getattr(action, "apply_into", None)
        if callable(function):
            # Existing S6 apply_into returns a facts mapping, not a Vec.
            function(source, owned_target)
        else:
            returned = action.apply(source, owned_target)
            if returned is not None and returned is not owned_target:
                raise TypeError("action must write target; adapt borrowed output explicitly")
        return owned_target
    except BaseException:
        if target is None:
            _destroy(owned_target)
        raise


class BorrowedActionAdapter:
    """Copy a split-volume/form action's borrowed buffer into caller storage."""

    def __init__(self, action: Any) -> None:
        self.action = action

    def apply(self, source: Any, target: Any) -> None:
        _copy_into(target, self.action.apply(source))


class PositiveDiagonalJacobi:
    """Divide by supplied positive curl-plus-mass diagonal; borrow its Vec.

    The FE builder must supply the corresponding level's positive operator
    diagonal. This class validates positivity, not that physical provenance.
    """

    def __init__(self, diagonal: Any) -> None:
        from mpi4py import MPI

        values = diagonal.array
        valid = bool(np.all(np.isfinite(values)) and np.all(values.real > 0)
                     and np.all(values.imag == 0))
        if not diagonal.getComm().tompi4py().allreduce(valid, op=MPI.LAND):
            raise ValueError("Jacobi requires a finite strictly positive real diagonal")
        self.diagonal = diagonal

    def __call__(self, source: Any) -> Any:
        result = source.duplicate()
        try:
            result.pointwiseDivide(source, self.diagonal)
            return result
        except BaseException:
            result.destroy()
            raise


def modified_residual_accept(
    residual: Any,
    direction: Any,
    action: Any,
    *,
    correction: Any | None = None,
    capture: Callable[[Any, Any], None] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Accept one direction with the complex one-dimensional MR formula.

    ``alpha = (A d)^H r / (A d)^H (A d)`` is evaluated with the PETSc/global
    dot product when vectors are PETSc objects. Normalize the action before
    the dot product, with an exact zero check before division and no clamp.
    """

    residual_norm_before = _norm(residual)
    direction_norm = _norm(direction)
    owns_correction = correction is None
    if owns_correction:
        correction = _new_like(direction)
        _zero(correction)
    facts: dict[str, Any] = {
        "direction_norm": direction_norm,
        "residual_norm_before": residual_norm_before,
        "accepted": False,
        "alpha": [0.0, 0.0],
        "denominator": 0.0,
        "denominator_floor": 0.0,
        "residual_norm_after": residual_norm_before,
        "finite": True,
        "raw_unit_rho": 1.0,
        "rho": 1.0,
        "fine_action_count": 0,
    }
    if residual_norm_before == 0.0 or direction_norm == 0.0:
        if capture is not None:
            capture(direction, None)
        facts["reason"] = "zero_residual_or_direction"
        return correction, facts

    applied = None
    applied_unit = None
    try:
        applied = apply_owned(action, direction)
        facts["fine_action_count"] = 1
        applied_norm = _norm(applied)
        if capture is not None:
            capture(direction, applied)
        facts["applied_norm"] = applied_norm
        facts["raw_unit_rho"] = 1.0
        facts["rho"] = 1.0
        if applied_norm == 0.0:
            facts["reason"] = "zero_action_direction"
            return correction, facts
        raw = _copy(residual)
        try:
            _axpy(raw, -1.0, applied)
            facts["raw_unit_rho"] = _norm(raw) / residual_norm_before
        finally:
            _destroy(raw)
        applied_unit = _copy(applied)
        _scale(applied_unit, 1.0 / applied_norm)
        scaled_denominator = float(np.real(_dot(applied_unit, applied_unit)))
        denominator = (
            float(applied_norm * applied_norm)
            if np.isfinite(applied_norm * applied_norm)
            else None
        )
        facts["applied_norm"] = applied_norm
        facts["denominator"] = denominator
        facts["scaled_denominator"] = scaled_denominator
        facts["denominator_floor"] = 0.0
        if not np.isfinite(scaled_denominator) or scaled_denominator <= 0.0:
            facts["reason"] = "numerically_zero_action_direction"
            return correction, facts
        alpha = _dot(applied_unit, residual) / (applied_norm * scaled_denominator)
        if not np.isfinite(alpha.real) or not np.isfinite(alpha.imag):
            raise RuntimeError("MR coefficient is non-finite")
        _axpy(correction, alpha, direction)
        _axpy(residual, -alpha, applied)
        residual_norm_after = _norm(residual)
        _norm(correction)
        facts.update(
            {
                "accepted": True,
                "alpha": [float(alpha.real), float(alpha.imag)],
                "residual_norm_after": residual_norm_after,
                "rho": residual_norm_after / residual_norm_before,
            }
        )
        return correction, facts
    except BaseException:
        if owns_correction:
            _destroy(correction)
        raise
    finally:
        _destroy(applied_unit)
        _destroy(applied)


def _bounded_right_fgmres(
    rhs: Any,
    action: Any,
    preconditioner: Any | None,
    steps: int,
) -> tuple[Any, Any, list[dict[str, Any]]]:
    """Run one zero-start, right-preconditioned bounded FGMRES solve."""

    from petsc4py import PETSc

    if not isinstance(rhs, PETSc.Vec):
        raise TypeError("bounded FGMRES requires a PETSc Vec")
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext

    steps = int(steps)
    if steps != SMOOTHING_STEPS:
        raise ValueError("auxiliary smoothing requires exactly three steps")
    if not isinstance(preconditioner, PositiveDiagonalJacobi):
        raise TypeError("smoothing requires the level's positive diagonal Jacobi")
    rhs_norm = _norm(rhs)
    with ExitStack() as resources:
        solution = rhs.duplicate()
        resources.callback(solution.destroy)
        solution.set(0.0)
        residual = rhs.copy()
        resources.callback(residual.destroy)
        started = time.perf_counter()
        action_context = _ActionContext(lambda source: apply_owned(action, source))
        pc_context = _PCContext(preconditioner)
        iterations, reason = 0, 0
        if rhs_norm != 0.0:
            sizes = (rhs.getLocalSize(), rhs.getSize())
            operator = PETSc.Mat().createPython(
                (sizes, sizes), context=action_context, comm=rhs.getComm())
            resources.callback(operator.destroy)
            operator.setUp()
            ksp = PETSc.KSP().create(rhs.getComm())
            resources.callback(ksp.destroy)
            ksp.setOperators(operator)
            ksp.setType("fgmres")
            ksp.setGMRESRestart(steps)
            ksp.setPCSide(PETSc.PC.Side.RIGHT)
            ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            ksp.setInitialGuessNonzero(False)
            ksp.setTolerances(rtol=0.0, atol=0.0, max_it=steps)
            pc = ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(pc_context)
            ksp.setUp()
            ksp.solve(rhs, solution)
            iterations, reason = int(ksp.getIterationNumber()), int(ksp.getConvergedReason())
            if reason < 0 and reason != -3:
                raise RuntimeError(f"auxiliary smoother breakdown: {reason}")
            action_value = apply_owned(action, solution)
            try:
                residual.axpy(-1.0, action_value)
            finally:
                action_value.destroy()
        explicit = _norm(residual) / rhs_norm if rhs_norm else 0.0
        _norm(solution)
        facts = [{
            "ksp_type": "fgmres", "pc_side": "right",
            "preconditioner": "positive_diagonal_jacobi",
            "restart": steps, "iterations": iterations, "reason": reason,
            "explicit_true_residual": explicit,
            "pc_apply_count": int(pc_context.apply_count),
            "matvec_count": int(action_context.matvec_count),
            "explicit_action_count": int(rhs_norm != 0.0),
            "finite": True, "wall_seconds": time.perf_counter() - started,
        }]
        result = solution.copy()
        try:
            return result, residual.copy(), facts
        except BaseException:
            result.destroy()
            raise


def _transfer(transfer: Any, operation: str, source: Any) -> Any:
    method = getattr(transfer, operation, None)
    if not callable(method):
        raise TypeError(f"transfer lacks {operation}")
    result = method(source)
    if result is None:
        raise TypeError(f"transfer {operation} must return its caller-owned vector")
    return result


def _take_solution(result: Any) -> tuple[Any, Callable[[], None]]:
    if isinstance(result, Mapping) and "final_solution" in result:
        solution = result["final_solution"]

        def release() -> None:
            from .fullspace_memory_first_krylov import destroy_krylov_result

            destroy_krylov_result(result)

        return solution, release
    if isinstance(result, tuple) and result:
        solution = result[0]
        return solution, lambda: _destroy(solution)
    return result, lambda: _destroy(result)


class ShiftedAuxiliaryCycle:
    """One bounded p4->p2->p1 shifted auxiliary V-cycle."""
    solver_identity = 'FGMRES12_A4_shifted'

    def __init__(
        self,
        shifted_p4_action: Any,
        p4_action: Any,
        p2_action: Any,
        p4_to_p2: Any,
        p2_to_p1: Any,
        p1_to_p2: Any,
        p2_to_p4: Any,
        p1_solve: Callable[[Any], Any],
        *,
        p4_preconditioner: PositiveDiagonalJacobi,
        p2_preconditioner: PositiveDiagonalJacobi,
        sigma: float = SHIFT_SIGMA,
        smoothing_steps: int = SMOOTHING_STEPS,
        stage_callback: Callable[[str, dict], None] | None = None,
    ) -> None:
        if float(sigma) != SHIFT_SIGMA:
            raise ValueError("Task039 fixes the auxiliary shift to sigma=0.5")
        if int(smoothing_steps) != SMOOTHING_STEPS:
            raise ValueError("Task039 fixes three pre/post smoothing steps")
        if not callable(p1_solve):
            raise TypeError("the shifted cycle requires an injected p1 solve")
        if not all(isinstance(pc, PositiveDiagonalJacobi) for pc in
                   (p4_preconditioner, p2_preconditioner)):
            raise TypeError("both auxiliary levels require positive diagonal Jacobi")
        self.shifted_p4_action = shifted_p4_action
        self.p4_action = p4_action
        self.p2_action = p2_action
        self.p4_to_p2 = p4_to_p2
        self.p2_to_p1 = p2_to_p1
        self.p1_to_p2 = p1_to_p2
        self.p2_to_p4 = p2_to_p4
        self.p1_solve = p1_solve
        self.p4_preconditioner = p4_preconditioner
        self.p2_preconditioner = p2_preconditioner
        self.sigma = float(sigma)
        self.smoothing_steps = int(smoothing_steps)
        self.apply_count = 0
        self.last_apply_facts: dict[str, Any] = {}
        self.stage_callback = stage_callback

    def apply_with_facts(self, rhs: Any) -> tuple[Any, dict[str, Any]]:
        started = time.perf_counter()
        facts: dict[str, Any] = {
            "schema": "task039.shifted_auxiliary_cycle.v1",
            "sigma": self.sigma, "smoothing_steps": self.smoothing_steps,
        }
        with ExitStack() as resources:
            def own(vector: Any) -> Any:
                resources.callback(_destroy, vector)
                return vector

            def smooth(rhs: Any, action: Any, pc: Any, label: str) -> tuple[Any, Any]:
                if self.stage_callback is not None:
                    self.stage_callback(label + "_started", {"shifted_apply": self.apply_count + 1})
                solution, residual, ledger = _bounded_right_fgmres(
                    rhs, action, pc, self.smoothing_steps)
                own(solution)
                own(residual)
                facts[label + "_facts"] = ledger
                facts[label + "_steps"] = ledger[0]["iterations"]
                return solution, residual

            p4_solution, p4_residual = smooth(
                rhs, self.shifted_p4_action, self.p4_preconditioner, "p4_pre")
            p2_rhs = own(_transfer(self.p4_to_p2, "apply_adjoint", p4_residual))
            p2_solution, p2_residual = smooth(
                p2_rhs, self.p2_action, self.p2_preconditioner, "p2_pre")
            p1_rhs = own(_transfer(self.p2_to_p1, "apply_adjoint", p2_residual))
            bottom_started = time.perf_counter()
            if self.stage_callback is not None:
                self.stage_callback("shifted_p1_solve_started", {})
            p1_result = self.p1_solve(p1_rhs)
            p1_solution, release_p1 = _take_solution(p1_result)
            resources.callback(release_p1)
            _norm(p1_solution)
            facts["p1_wall_seconds"] = time.perf_counter() - bottom_started
            facts["p1_solve_facts"] = (
                {k: deepcopy(v) for k, v in p1_result.items() if k != "final_solution"}
                if isinstance(p1_result, Mapping) else
                deepcopy(getattr(self.p1_solve, "last_apply_facts", {})))
            p2_coarse = own(_transfer(self.p1_to_p2, "apply_primal", p1_solution))
            _axpy(p2_solution, 1.0, p2_coarse)
            p2_action_value = own(apply_owned(self.p2_action, p2_solution))
            p2_post_rhs = own(_copy(p2_rhs))
            _axpy(p2_post_rhs, -1.0, p2_action_value)
            p2_post, _ = smooth(p2_post_rhs, self.p2_action, self.p2_preconditioner, "p2_post")
            _axpy(p2_solution, 1.0, p2_post)
            p4_coarse = own(_transfer(self.p2_to_p4, "apply_primal", p2_solution))
            _axpy(p4_solution, 1.0, p4_coarse)
            p4_action_value = own(apply_owned(self.shifted_p4_action, p4_solution))
            p4_post_rhs = own(_copy(rhs))
            _axpy(p4_post_rhs, -1.0, p4_action_value)
            p4_post, _ = smooth(
                p4_post_rhs, self.shifted_p4_action, self.p4_preconditioner, "p4_post")
            _axpy(p4_solution, 1.0, p4_post)
            _norm(p4_solution)
            self.apply_count += 1
            facts.update({
                "p1_solve_count": 1,
                "p4_to_p2_adjoint_count": 1, "p2_to_p1_adjoint_count": 1,
                "p1_to_p2_primal_count": 1, "p2_to_p4_primal_count": 1,
                "p4_residual_action_count": 1, "p2_residual_action_count": 1,
                "apply_count": self.apply_count, "finite": True,
                "wall_seconds": time.perf_counter() - started,
            })
            self.last_apply_facts = facts
            return _copy(p4_solution), facts

    def apply(self, rhs: Any) -> Any:
        return self.apply_with_facts(rhs)[0]

    __call__ = apply

    def solve_intermediate(
        self,
        rhs: Any,
        *,
        resource_sample: Callable[[], Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Solve the true p4 equation with one bounded right-FGMRES call."""

        from .fullspace_memory_first_krylov import run_fixed_restart_cycles

        sample = resource_sample or (lambda: {"sampled": False})
        if _norm(rhs) == 0.0:
            solution = _copy(rhs)
            _zero(solution)
            return {"final_solution": solution, "status": "ZERO_RHS",
                    "iterations": 0, "final_true_residual": 0.0, "reason": 0,
                    "cycles": [], "shifted_cycles": [], "pc_apply_count": 0,
                    "matvec_count": 0, "explicit_action_count": 0,
                    "elapsed_seconds": 0.0}
        shifted_cycles: list[dict[str, Any]] = []

        def apply_cycle(source: Any) -> Any:
            solution, facts = self.apply_with_facts(source)
            shifted_cycles.append(deepcopy(facts))
            return solution

        result = run_fixed_restart_cycles(
            rhs,
            lambda source: apply_owned(self.p4_action, source),
            apply_cycle,
            max_it=INTERMEDIATE_MAX_IT,
            residual_limit=INTERMEDIATE_RESIDUAL_LIMIT,
            resource_sample=sample,
            initial_solution=None,
            start_iteration=0,
            checkpoint_writer=None,
            first_checkpoint_iteration=None,
            checkpoint_interval=INTERMEDIATE_RESTART,
            stop_on_true_residual=True,
            ksp_type="fgmres",
            restart=INTERMEDIATE_RESTART,
            cycle_max_it=INTERMEDIATE_RESTART,
        )

        try:
            residual = float(result["final_true_residual"])
            _norm(result["final_solution"])
            if not np.isfinite(residual):
                raise RuntimeError("nonfinite physical intermediate residual")
            if result["reason"] < 0 and result["reason"] != -3:
                raise RuntimeError(f"physical intermediate breakdown: {result['reason']}")
            result["status"] = ("CONVERGED_INTERMEDIATE" if
                                residual <= INTERMEDIATE_RESIDUAL_LIMIT else
                                "INEXACT_INTERMEDIATE")
            result["shifted_cycles"] = shifted_cycles
            # Fixed max36 bounds this ledger. Only scalar facts survive; no Vecs.
            result["shifted_cost_totals"] = {
                "cycle_count": len(shifted_cycles),
                "p1_solve_count": sum(f["p1_solve_count"] for f in shifted_cycles),
                "p1_wall_seconds": sum(f["p1_wall_seconds"] for f in shifted_cycles),
                "wall_seconds": sum(f["wall_seconds"] for f in shifted_cycles),
            }
            for transfer in ("p4_to_p2_adjoint", "p2_to_p1_adjoint",
                             "p1_to_p2_primal", "p2_to_p4_primal"):
                result["shifted_cost_totals"][transfer + "_count"] = sum(
                    f[transfer + "_count"] for f in shifted_cycles)
            for level in ("p4", "p2"):
                smoothers = [entry for f in shifted_cycles for side in ("pre", "post")
                             for entry in f[level + "_" + side + "_facts"]]
                for field in ("iterations", "pc_apply_count", "matvec_count",
                              "explicit_action_count", "wall_seconds"):
                    result["shifted_cost_totals"][level + "_smoothing_" + field] = sum(
                        f[field] for f in smoothers)
                result["shifted_cost_totals"][level + "_residual_action_count"] = sum(
                    f[level + "_residual_action_count"] for f in shifted_cycles)
            return result
        except BaseException:
            from .fullspace_memory_first_krylov import destroy_krylov_result
            destroy_krylov_result(result)
            raise


class PhysicalIntermediatePreconditioner:
    """The three-direction nonlinear outer-PC composition from Task039."""

    def __init__(
        self,
        fine_action: Any,
        positive_cycle: Any,
        p6_to_p4: Any,
        intermediate_cycle: ShiftedAuxiliaryCycle,
        *, stage_callback: Callable[[str, dict], None] | None = None,
        positive_identity: str = 'S6', outer_max_it: int = OUTER_MAX_IT,
        joint_mr: bool = False,
        diagnostic_before_middle=None,
    ) -> None:
        self.fine_action = fine_action
        self.positive_identity = positive_identity
        self.outer_max_it = outer_max_it
        self.positive_cycle = positive_cycle
        self.p6_to_p4 = p6_to_p4
        self.intermediate_cycle = intermediate_cycle
        self.intermediate_identity = getattr(intermediate_cycle, 'solver_identity', 'FGMRES12_A4_shifted')
        if joint_mr and (positive_identity != 'H6' or self.intermediate_identity != 'exact_augmented_A4_reference'):
            raise ValueError('joint MR3 requires the frozen LIGHT reference directions')
        self.joint_mr = joint_mr
        self.diagnostic_before_middle = diagnostic_before_middle
        self.stage_callback = stage_callback
        self.apply_count = 0
        self.last_apply_facts: dict[str, Any] = {}

    def _accept(
        self,
        residual: Any,
        correction: Any,
        direction: Any,
        label: str,
        facts: list[dict[str, Any]],
        capture: Callable[[Any, Any], None] | None = None,
    ) -> None:
        correction, mr_facts = modified_residual_accept(
            residual,
            direction,
            self.fine_action,
            correction=correction,
            **({'capture': capture} if capture is not None else {}),
        )
        facts.append({"stage": label, **mr_facts})

    def apply(self, rhs: Any) -> Any:
        started = time.perf_counter()
        with ExitStack() as resources:
            def own(vector: Any) -> Any:
                resources.callback(_destroy, vector)
                return vector

            correction = own(_new_like(rhs))
            _zero(correction)
            residual = own(_copy(rhs))
            direction_facts: list[dict[str, Any]] = []
            inner_facts: dict[str, Any] = {}
            joint = None
            joint_facts = None
            if self.joint_mr:
                from .physical_joint_mr import JointMR3
                joint = JointMR3(rhs)
                resources.callback(joint.close)
            if _norm(rhs) != 0.0:
                for label in ("positive_pre", "physical_middle", "positive_post"):
                    if self.stage_callback is not None:
                        self.stage_callback(label + "_started", {"outer_pc_apply": self.apply_count + 1})
                    stage_started = time.perf_counter()
                    with ExitStack() as stage:
                        if label == "physical_middle":
                            p4_rhs = _transfer(self.p6_to_p4, "apply_adjoint", residual)
                            stage.callback(_destroy, p4_rhs)
                            if self.diagnostic_before_middle is not None:
                                self.diagnostic_before_middle(rhs, residual, p4_rhs)
                            inner = self.intermediate_cycle.solve_intermediate(p4_rhs)
                            inner_solution, release = _take_solution(inner)
                            stage.callback(release)
                            inner_facts = {k: deepcopy(v) for k, v in inner.items()
                                           if k != "final_solution"}
                            direction = _transfer(self.p6_to_p4, "apply_primal", inner_solution)
                        else:
                            direction = apply_owned(self.positive_cycle, residual)
                        stage.callback(_destroy, direction)
                        self._accept(residual, correction, direction, label, direction_facts,
                            **({'capture': joint.capture} if joint is not None else {}))
                        direction_facts[-1]["wall_seconds"] = time.perf_counter() - stage_started
                        if label != "physical_middle":
                            direction_facts[-1]["positive_cycle_facts"] = deepcopy(
                                getattr(self.positive_cycle, "last_apply_facts", {}))
            selected_residual_norm = _norm(residual)
            if joint is not None:
                if self.stage_callback is not None:
                    self.stage_callback('joint_mr3_started', {'outer_pc_apply':self.apply_count+1})
                sequential_norm = selected_residual_norm
                candidate, joint_facts = joint.candidate(rhs)
                joint_facts.update(sequential_residual_norm=sequential_norm, rhs_norm=_norm(rhs),
                    sequential_solution_norm=_norm(correction), joint_solution_norm=None,
                    joint_residual_norm=None, selected_residual_norm=sequential_norm)
                if self.apply_count < 3:
                    import hashlib
                    from .physical_joint_mr import array_view
                    joint_facts['same_input_sha256'] = hashlib.sha256(array_view(rhs).tobytes()).hexdigest()
                if candidate is not None and _norm(rhs) != 0:
                    proposed = own(_new_like(rhs))
                    target = proposed.array if hasattr(proposed,'array') else proposed
                    np.copyto(target, candidate)
                    joint_facts['joint_solution_norm'] = _norm(proposed)
                    del candidate
                    extra_started = time.perf_counter()
                    value = own(apply_owned(self.fine_action, proposed))
                    _norm(value)  # Physical nonfinite/action errors must propagate.
                    joint_facts['extra_A6_seconds'] = time.perf_counter()-extra_started
                    joint_facts['extra_A6_count'] = 1
                    checked = own(_copy(rhs))
                    _axpy(checked, -1., value)
                    measured = _norm(checked)
                    joint_facts['joint_residual_norm'] = measured
                    if measured > sequential_norm+1e-10*_norm(rhs):
                        joint_facts.update(fallback=True, fallback_reason='explicit_joint_residual_safeguard')
                    else:
                        _copy_into(correction, proposed)
                        selected_residual_norm = measured
                        joint_facts['selected_residual_norm'] = measured
                joint_facts['selected_over_sequential'] = (selected_residual_norm/sequential_norm if sequential_norm else None)
            self.apply_count += 1
            self.last_apply_facts = {
                "schema": "task039.physical_intermediate_pc.v1",
                "formula": (self.positive_identity + "-MR -> P64^H -> " + self.intermediate_identity
                            + " -> P64-MR -> " + self.positive_identity + "-MR"),
                "positive_identity": self.positive_identity,
                "direction_count": len(direction_facts),
                "direction_facts": direction_facts, "intermediate": inner_facts,
                "input_norm": _norm(rhs), "output_norm": _norm(correction),
                "remaining_residual_norm": selected_residual_norm, "finite": True,
                "apply_count": self.apply_count,
                "wall_seconds": time.perf_counter() - started,
            }
            if joint_facts is not None:
                self.last_apply_facts['joint_mr3'] = joint_facts
                self.last_apply_facts['formula'] += ' -> normalized QR/small SVD joint MR3 with explicit safeguard'
            return _copy(correction)

    __call__ = apply

    @property
    def audit(self) -> Mapping[str, Any]:
        if self.intermediate_identity == 'exact_augmented_A4_reference':
            return dict(schema='task039.physical_intermediate_pc.v1',
                method=self.intermediate_identity, diagnostic_only=True,
                outer_restart=OUTER_RESTART, outer_max_it=self.outer_max_it,
                inner_residual_limit=1e-10, apply_count=self.apply_count)
        return {
            "schema": "task039.physical_intermediate_pc.v1",
            "method": INTERMEDIATE_METHOD,
            "outer_restart": OUTER_RESTART,
            "outer_max_it": self.outer_max_it,
            "inner_restart": INTERMEDIATE_RESTART,
            "inner_max_it": INTERMEDIATE_MAX_IT,
            "inner_residual_limit": INTERMEDIATE_RESIDUAL_LIMIT,
            "sigma": SHIFT_SIGMA,
            "smoothing_steps": SMOOTHING_STEPS,
            "nonlinear": True,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "local_factor_max_rows": LOCAL_FACTOR_MAX_ROWS,
            "local_factor_max_bytes": LOCAL_FACTOR_MAX_BYTES,
            "apply_count": self.apply_count,
        }


class ShiftedPhysicalAction:
    """Apply ``A_physical - i*sigma*k0**2 W`` without assembling a matrix."""

    def __init__(self, physical_action: Any, mass_action: Any, k0: float) -> None:
        self.physical_action = physical_action
        self.mass_action = mass_action
        self.k0 = float(k0)
        self.apply_count = 0

    def apply(self, source: Any, target: Any | None = None) -> Any:
        owns_target = target is None
        target = _new_like(source) if owns_target else target
        try:
            apply_owned(self.physical_action, source, target)
            mass = apply_owned(self.mass_action, source)
            try:
                _axpy(target, -1j * SHIFT_SIGMA * self.k0**2, mass)
            finally:
                _destroy(mass)
        except BaseException:
            if owns_target:
                _destroy(target)
            raise
        self.apply_count += 1
        return target

    @property
    def audit(self) -> Mapping[str, Any]:
        return {
            "schema": "task039.shifted_physical_action.v1",
            "operator": "A_physical_minus_i_sigma_k0_squared_W",
            "sigma": SHIFT_SIGMA,
            "mass_action": "matrix_free",
            "global_matrix": False,
            "apply_count": self.apply_count,
        }


__all__ = (
    "INTERMEDIATE_MAX_IT",
    "INTERMEDIATE_METHOD",
    "INTERMEDIATE_RESIDUAL_LIMIT",
    "INTERMEDIATE_RESTART",
    "LOCAL_FACTOR_MAX_BYTES",
    "LOCAL_FACTOR_MAX_ROWS",
    "OUTER_MAX_IT",
    "OUTER_RESTART",
    "SHIFT_SIGMA",
    "SMOOTHING_STEPS",
    "BorrowedActionAdapter",
    "PositiveDiagonalJacobi",
    "PhysicalIntermediatePreconditioner",
    "ShiftedAuxiliaryCycle",
    "ShiftedPhysicalAction",
    "apply_owned",
    "modified_residual_accept",
)
