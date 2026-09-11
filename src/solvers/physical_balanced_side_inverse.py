"""Minimal side-trace adapter for the reviewed BAL_H preconditioner.

The borrowed one-sided ``HybridLocalDtnActionSystem.A`` remains the Krylov
operator.  Its right preconditioner injects an active residual with ``J^H``,
applies the full-space BAL_H route, and extracts the active trace with ``J``.
The full p6 action, one p4 factor, p6/p4 owner transfer, and fixed H6 action
are all owned by one adapter instance; the side system and its mesh/MPC data
remain borrowed.
"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_local_dtn_action import HybridLocalDtnActionSystem
from .physical_balanced_coupling import PhysicalBalancedCoupling
from .physical_balanced_h6 import build_balanced_h6
from .physical_balanced_physical_operator import (
    build_fullspace_physical_dtn_action,
    build_p4_exact_factor,
)
from .physical_balanced_same_mesh_transfer import (
    build_same_mesh_hcurl_owner_transfer,
)
from .physical_balanced_trace_bridge import (
    extract_full_p6_to_active_trace,
    inject_active_residual_to_full_p6,
)

__all__ = (
    "SideBalancedInverse",
    "build_side_balanced_inverse",
)


_MAX_DENSE_COLUMNS = 32
_ALLOWED_KSP = ((128, 1.0e-2), (256, 1.0e-4))
# Native PETSc names the task's DIVERGED_ITS budget result DIVERGED_MAX_IT.
_DIVERGED_ITS = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)


def _dense_types(matrix: PETSc.Mat) -> bool:
    return str(matrix.getType()).lower() in {"seqdense", "dense", "mpidense"}


def _context_apply_count(matrix: PETSc.Mat) -> int | None:
    try:
        context = matrix.getPythonContext()
    except (AttributeError, PETSc.Error):
        return None
    value = getattr(context, "apply_count", None)
    return None if value is None else int(value)


def _same_handle(left: Any, right: Any) -> bool:
    if left is right:
        return True
    try:
        return int(left.handle) == int(right.handle)
    except (AttributeError, TypeError, ValueError):
        return False


def _classify_ksp_result(
    reason: int,
    iterations: int,
    max_it: int,
) -> tuple[str, bool]:
    """Keep PETSc's raw reason while admitting only the fixed ITS budget."""

    reason = int(reason)
    iterations = int(iterations)
    max_it = int(max_it)
    if iterations < 0 or iterations > max_it:
        raise RuntimeError(
            "BAL_H side KSP returned iterations outside its fixed budget: "
            f"{iterations} not in [0,{max_it}]"
        )
    if reason > 0:
        return "KSP_CONVERGED", True
    if reason == _DIVERGED_ITS and iterations == max_it:
        return "INNER_APPROXIMATE_RETURN", False
    raise RuntimeError(
        "BAL_H side KSP failed with non-iterative reason "
        f"{reason} after {iterations} iterations"
    )


class _SidePythonPcContext:
    """Borrow the side adapter from PETSc's Python right-PC context."""

    def __init__(self, owner: SideBalancedInverse) -> None:
        self.owner: SideBalancedInverse | None = owner

    def apply(
        self,
        _pc: PETSc.PC,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        owner = self.owner
        if owner is None:
            raise RuntimeError("BAL_H side Python PC has been destroyed")
        owner._apply_balanced_pc(source, target)

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.owner = None


class SideBalancedInverse:
    """Right FGMRES inverse of one borrowed condensed side operator.

    ``apply`` returns through the caller-provided target Vec.  The internal
    callbacks used by BAL_H always return fresh owned Vec objects, so the
    coupling can release every temporary independently of the side input.
    """

    operator_identity = "borrowed_side_A_right_fgmres_J_BAL_H_JH"

    def __init__(
        self,
        side_system: HybridLocalDtnActionSystem,
        full_action: Any,
        p4_factor: Any,
        owner_transfer: Any,
        h6: Any,
        *,
        max_it: int = 128,
        rtol: float = 1.0e-2,
        checkpoint_callback: Callable[[], None] | None = None,
        audit_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        _validate_ksp_pair(max_it, rtol)
        operator = side_system.A
        condensed = side_system.static_condensation.condensed
        if not isinstance(operator, PETSc.Mat):
            raise TypeError("BAL_H side inverse requires a PETSc side operator")
        if int(side_system.cfg.nedelec_degree) != 6:
            raise ValueError("BAL_H side inverse requires the p6 side system")
        if int(operator.getSize()[0]) != int(condensed.active_rows):
            raise ValueError("side operator and condensed active rows do not match")
        if int(full_action.full_rows) != int(condensed.full_rows):
            raise ValueError("full p6 action and condensed FE rows do not match")

        self._side_system: HybridLocalDtnActionSystem | None = side_system
        self._condensed: Any | None = condensed
        self._operator: PETSc.Mat | None = operator
        self._full_action: Any | None = full_action
        self._p4_factor: Any | None = p4_factor
        self._owner_transfer: Any | None = owner_transfer
        self._h6: Any | None = h6
        self._checkpoint_callback = checkpoint_callback or (lambda: None)
        self._audit_callback = audit_callback
        self._comm = operator.getComm().tompi4py()
        self._max_it = int(max_it)
        self._rtol = float(rtol)
        self._destroyed = False
        self._p4_factor_created_count = 1
        self._p4_factor_destroy_count = 0
        self._nested_ksp_created_count = 1
        self._nested_ksp_destroy_count = 0
        self._checkpoint_count = 0
        self._pc_apply_count = 0
        self._q_count = 0
        self._h6_count = 0
        self._a6_count = 0
        self._j_count = 0
        self._jh_count = 0
        self._ph_audit_count = 0
        self._ph_total_count = 0
        self._p_count = 0
        self._p4_backsolve_count = 0
        self._p4_refinement_count = 0
        self._apply_count = 0
        self._total_iterations = 0
        self._total_apply_seconds = 0.0
        self._last_apply: dict[str, Any] = {}
        self._cumulative_counts: dict[str, int | None] = {
            "side_A": _context_apply_count(operator),
            "pc": 0,
            "Q": 0,
            "p4_backsolve": 0,
            "p4_refinement": 0,
            "H6": 0,
            "A6": 0,
            "J": 0,
            "JH": 0,
            "P": 0,
            "PH_audit": 0,
            "PH_total": 0,
        }
        self._pre_destroy_component_diagnostics: dict[str, Any] | None = None

        self._coupling = PhysicalBalancedCoupling(
            self._apply_a6_callback,
            self._apply_q_callback,
            self._apply_h6_callback,
            self._apply_ph_callback,
            checkpoint=self._checkpoint,
        )
        self._pc_context = _SidePythonPcContext(self)
        self._ksp: PETSc.KSP | None = PETSc.KSP().create(operator.getComm())
        try:
            self._ksp.setOperators(operator)
            self._ksp.setType("fgmres")
            self._ksp.setPCSide(PETSc.PC.Side.RIGHT)
            self._ksp.setGMRESRestart(32)
            self._ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            self._ksp.setInitialGuessNonzero(False)
            self._ksp.setTolerances(
                rtol=self._rtol,
                atol=0.0,
                max_it=self._max_it,
            )
            pc = self._ksp.getPC()
            pc.setType("python")
            pc.setPythonContext(self._pc_context)
            self._ksp.setMonitor(self._monitor)
            self._ksp.setUp()
        except BaseException:
            self._pc_context.owner = None
            self._ksp.destroy()
            self._ksp = None
            raise

    @property
    def operator(self) -> PETSc.Mat:
        if self._destroyed or self._operator is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        return self._operator

    def _monitor(
        self,
        _ksp: PETSc.KSP,
        _iteration: int,
        _reported_residual: float,
    ) -> None:
        self._checkpoint()

    def _checkpoint(self) -> None:
        self._checkpoint_count += 1
        self._checkpoint_callback()

    def _apply_a6_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._full_action is None:
            raise RuntimeError("BAL_H full p6 action has been destroyed")
        target = self._full_action.matrix.createVecLeft()
        try:
            self._full_action.matrix.mult(source, target)
            self._a6_count += 1
            return target
        except BaseException:
            target.destroy()
            raise

    def _apply_ph_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._owner_transfer is None:
            raise RuntimeError("BAL_H owner transfer has been destroyed")
        self._ph_audit_count += 1
        self._ph_total_count += 1
        return self._owner_transfer.apply_adjoint(source)

    def _apply_h6_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._h6 is None:
            raise RuntimeError("BAL_H H6 action has been destroyed")
        self._h6_count += 1
        return self._h6.apply(source)

    def _apply_q_callback(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._owner_transfer is None or self._p4_factor is None:
            raise RuntimeError("BAL_H coarse components have been destroyed")
        self._q_count += 1
        self._ph_total_count += 1
        coarse_rhs = self._owner_transfer.apply_adjoint(source)
        augmented_rhs = None
        augmented_solution = None
        coarse_solution = None
        factor_solve_before = int(
            self._p4_factor.diagnostics["research_factor"]["solve_count"]
        )
        try:
            augmented_rhs = self._p4_factor.create_rhs(coarse_rhs)
            augmented_solution = augmented_rhs.duplicate()
            augmented_solution.set(0.0)
            self._p4_factor.solve_with_refinement(
                augmented_rhs,
                augmented_solution,
                residual_tolerance=1.0e-10,
            )
            coarse_solution = self._p4_factor.extract_fe_solution(
                augmented_solution
            )
            result = self._owner_transfer.apply_primal(coarse_solution)
            self._p_count += 1
            return result
        finally:
            factor_solve_after = int(
                self._p4_factor.diagnostics["research_factor"]["solve_count"]
            )
            actual_backsolves = max(factor_solve_after - factor_solve_before, 0)
            self._p4_backsolve_count += actual_backsolves
            self._p4_refinement_count += max(actual_backsolves - 1, 0)
            coarse_rhs.destroy()
            if augmented_rhs is not None:
                augmented_rhs.destroy()
            if augmented_solution is not None:
                augmented_solution.destroy()
            if coarse_solution is not None:
                coarse_solution.destroy()

    def _apply_balanced_pc(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed or self._full_action is None or self._condensed is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if source.getSize() != self.operator.getSize()[1]:
            raise ValueError("BAL_H side PC source has the wrong active size")
        if target.getSize() != self.operator.getSize()[0]:
            raise ValueError("BAL_H side PC target has the wrong active size")
        self._pc_apply_count += 1
        full_source = self._full_action.matrix.createVecRight()
        full_output = None
        active_output = None
        try:
            self._jh_count += 1
            inject_active_residual_to_full_p6(
                self._condensed,
                source,
                full_source,
            )
            if self._coupling is None:
                raise RuntimeError("BAL_H coupling has been destroyed")
            full_output = self._coupling.apply(full_source)
            self._j_count += 1
            active_output = extract_full_p6_to_active_trace(
                self._condensed,
                full_output,
            )
            active_output.copy(target)
        finally:
            full_source.destroy()
            if full_output is not None:
                full_output.destroy()
            if active_output is not None:
                active_output.destroy()

    def _explicit_residual(self, source: PETSc.Vec, target: PETSc.Vec) -> dict[str, Any]:
        if self._operator is None:
            raise RuntimeError("BAL_H side operator has been destroyed")
        operator_output = self._operator.createVecLeft()
        residual = source.duplicate()
        try:
            self._operator.mult(target, operator_output)
            source.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), operator_output)
            rhs_norm = float(source.norm())
            residual_norm = float(residual.norm())
            solution_norm = float(target.norm())
            if not all(
                np.isfinite(value)
                for value in (rhs_norm, residual_norm, solution_norm)
            ):
                raise RuntimeError("BAL_H side true residual is non-finite")
            relative = (
                residual_norm / rhs_norm if rhs_norm > 0.0 else residual_norm
            )
            if not np.isfinite(relative):
                raise RuntimeError("BAL_H side true residual ratio is non-finite")
            return {
                "rhs_norm": rhs_norm,
                "solution_norm": solution_norm,
                "residual_norm": residual_norm,
                "relative_residual": relative,
            }
        finally:
            operator_output.destroy()
            residual.destroy()

    def _count_snapshot(self) -> dict[str, int | None]:
        if self._operator is None:
            return dict(self._cumulative_counts)
        snapshot = {
            "side_A": _context_apply_count(self.operator),
            "pc": int(self._pc_apply_count),
            "Q": int(self._q_count),
            "p4_backsolve": int(self._p4_backsolve_count),
            "p4_refinement": int(self._p4_refinement_count),
            "H6": int(self._h6_count),
            "A6": int(self._a6_count),
            "J": int(self._j_count),
            "JH": int(self._jh_count),
            "P": int(self._p_count),
            "PH_audit": int(self._ph_audit_count),
            "PH_total": int(self._ph_total_count),
            "checkpoint": int(self._checkpoint_count),
        }
        self._cumulative_counts = dict(snapshot)
        return snapshot

    @staticmethod
    def _count_delta(
        before: dict[str, int | None],
        after: dict[str, int | None],
    ) -> dict[str, int | None]:
        result: dict[str, int | None] = {}
        for name, value in after.items():
            old = before[name]
            result[name] = None if value is None or old is None else value - old
        return result

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the side inverse into ``target`` and record one RHS audit."""

        if self._destroyed or self._operator is None or self._ksp is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if _same_handle(source, target):
            raise ValueError("BAL_H side inverse does not allow source/target aliasing")
        if source.getSize() != self._operator.getSize()[1]:
            raise ValueError("BAL_H side inverse source has the wrong size")
        if target.getSize() != self._operator.getSize()[0]:
            raise ValueError("BAL_H side inverse target has the wrong size")
        target.set(0.0)
        self._apply_count += 1
        before = self._count_snapshot()
        started = perf_counter()
        rhs_norm: Any = "not_measured"
        reason: int | None = None
        iterations = 0
        solve_started = False
        ksp_positive = False
        zero_rhs = False
        residual_audit: dict[str, Any] = {
            "rhs_norm": "not_measured",
            "solution_norm": "not_measured",
            "residual_norm": "not_measured",
            "relative_residual": "not_measured",
        }
        try:
            rhs_norm = float(source.norm())
            if not np.isfinite(rhs_norm):
                raise RuntimeError("BAL_H side RHS norm is non-finite")
            residual_audit["rhs_norm"] = rhs_norm
            zero_rhs = rhs_norm == 0.0
            if not zero_rhs:
                solve_started = True
                self._ksp.solve(source, target)
                reason = int(self._ksp.getConvergedReason())
                iterations = int(self._ksp.getIterationNumber())
                status, ksp_positive = _classify_ksp_result(
                    reason,
                    iterations,
                    self._max_it,
                )
            else:
                status = "ZERO_RHS_EXACT"

            residual_audit = self._explicit_residual(source, target)
            true_target_reached = bool(
                residual_audit["relative_residual"] <= self._rtol
                if not zero_rhs
                else residual_audit["residual_norm"] == 0.0
            )
            elapsed = float(
                self._comm.allreduce(perf_counter() - started, op=MPI.MAX)
            )
            after = self._count_snapshot()
            record = {
                "status": status,
                "reason": reason,
                "iterations": int(iterations),
                "ksp_positive": bool(ksp_positive),
                "explicit_true_target_reached": true_target_reached,
                "ksp_rtol": self._rtol,
                "ksp_max_it": self._max_it,
                "elapsed_seconds": elapsed,
                "counts": {
                    "delta": self._count_delta(before, after),
                    "cumulative": after,
                },
                **residual_audit,
            }
        except BaseException as exc:
            if solve_started and self._ksp is not None:
                try:
                    reason = int(self._ksp.getConvergedReason())
                    iterations = int(self._ksp.getIterationNumber())
                except (AttributeError, PETSc.Error):
                    pass
            self._total_iterations += int(iterations)
            elapsed = float(perf_counter() - started)
            self._total_apply_seconds += elapsed
            after = self._count_snapshot()
            record = {
                "status": "FAILED",
                "reason": reason,
                "iterations": int(iterations),
                "ksp_positive": bool(ksp_positive),
                "explicit_true_target_reached": "not_measured",
                "ksp_rtol": self._rtol,
                "ksp_max_it": self._max_it,
                "elapsed_seconds": elapsed,
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            "counts": {
                    "delta": self._count_delta(before, after),
                    "cumulative": after,
                },
                **residual_audit,
            }
            self._last_apply = dict(record)
            if self._audit_callback is not None:
                self._audit_callback(dict(record))
            raise

        self._total_iterations += int(iterations)
        self._total_apply_seconds += elapsed
        self._last_apply = dict(record)
        if self._audit_callback is not None:
            self._audit_callback(dict(record))

    def apply_many(self, sources: PETSc.Mat, targets: PETSc.Mat) -> None:
        """Apply columns one at a time with the fixed 32-column bound."""

        if self._destroyed or self._operator is None:
            raise RuntimeError("BAL_H side inverse has been destroyed")
        if not isinstance(sources, PETSc.Mat) or not isinstance(targets, PETSc.Mat):
            raise TypeError("BAL_H side inverse batches require PETSc dense matrices")
        if _same_handle(sources, targets):
            raise ValueError("BAL_H side inverse does not allow batch aliasing")
        if not _dense_types(sources) or not _dense_types(targets):
            raise TypeError("BAL_H side inverse batches require dense matrices")
        source_size = tuple(map(int, sources.getSize()))
        target_size = tuple(map(int, targets.getSize()))
        width = source_size[1]
        if source_size[0] != self._operator.getSize()[1]:
            raise ValueError("BAL_H source batch has the wrong row count")
        if target_size != (self._operator.getSize()[0], width):
            raise ValueError("BAL_H target batch has the wrong shape")
        if width <= 0 or width > _MAX_DENSE_COLUMNS:
            raise ValueError("BAL_H batches require one to 32 columns")
        ownership = tuple(map(int, self._operator.getOwnershipRange()))
        if tuple(map(int, sources.getOwnershipRange())) != ownership:
            raise ValueError("BAL_H source batch ownership does not match side A")
        if tuple(map(int, targets.getOwnershipRange())) != ownership:
            raise ValueError("BAL_H target batch ownership does not match side A")

        source = self._operator.createVecRight()
        target = self._operator.createVecLeft()
        try:
            source_array = sources.getDenseArray()
            target_array = targets.getDenseArray()
            for column in range(width):
                source.getArray()[:] = source_array[:, column]
                source.assemble()
                self.apply(source, target)
                target_array[:, column] = target.getArray(readonly=True)
            targets.assemble()
        finally:
            source.destroy()
            target.destroy()

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._p4_factor is None:
            p4_diagnostics = dict(
                (self._pre_destroy_component_diagnostics or {}).get(
                    "p4_factor", {}
                )
            )
        else:
            p4_diagnostics = dict(self._p4_factor.diagnostics)
        p4_live = int(self._p4_factor is not None)
        nested_ksp_live = int(self._ksp is not None)
        return {
            "schema": "task041.h1e.side_balanced_inverse.v1",
            "operator_identity": self.operator_identity,
            "research_only": True,
            "ksp_type": "fgmres",
            "pc_side": "right",
            "restart": 32,
            "norm_type": "unpreconditioned",
            "zero_initial_guess": True,
            "ksp_rtol": self._rtol,
            "ksp_max_it": self._max_it,
            "preconditioner": "J BAL_H JH",
            "apply_count": int(self._apply_count),
            "total_iterations": int(self._total_iterations),
            "total_apply_seconds": float(self._total_apply_seconds),
            "direct_factor_count": p4_live,
            "local_direct_factor_count": p4_live,
            "local_direct_factor_count_owned": p4_live,
            "p4_factor_count": p4_live,
            "p4_factor_live": p4_live,
            "p4_factor_created_count": int(self._p4_factor_created_count),
            "p4_factor_destroy_count": int(self._p4_factor_destroy_count),
            "p6_factor_count": 0,
            "global_direct_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
            "factor_free_qualification": False,
            "exact_side_qualification": False,
            "nested_iterative_ksp_count": int(nested_ksp_live),
            "nested_ksp_created_count": int(self._nested_ksp_created_count),
            "nested_ksp_destroy_count": int(self._nested_ksp_destroy_count),
            "nested_ksp_current_live": bool(nested_ksp_live),
            "approximate_nonlinear_inverse": True,
            "counts": self._count_snapshot(),
            "last_apply": dict(self._last_apply),
            "p4_factor": p4_diagnostics,
            "destroyed": bool(self._destroyed),
            "ksp_destroyed": not bool(nested_ksp_live),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        ksp = self._ksp
        self._ksp = None
        try:
            if ksp is not None:
                ksp.destroy()
                self._nested_ksp_destroy_count = 1
        finally:
            if self._pc_context is not None:
                self._pc_context.owner = None
            self._pc_context = None
            self._coupling = None
            p4_component = self._p4_factor
            owned = (
                ("h6", self._h6),
                ("owner_transfer", self._owner_transfer),
                ("p4_factor", p4_component),
                ("full_action", self._full_action),
            )
            p4_diagnostics: dict[str, Any] | None = None
            for _name, component in owned:
                if component is not None:
                    component.destroy()
                if _name == "p4_factor" and component is not None:
                    p4_diagnostics = dict(component.diagnostics)
            self._p4_factor_destroy_count = 1
            if p4_diagnostics is None:
                p4_diagnostics = {}
            p4_diagnostics["factor_destroy_count"] = 1
            p4_diagnostics["destroyed"] = True
            self._pre_destroy_component_diagnostics = {
                "p4_factor": p4_diagnostics,
            }
            self._h6 = None
            self._owner_transfer = None
            self._p4_factor = None
            self._full_action = None
            self._operator = None
            self._condensed = None
            self._side_system = None


def _validate_ksp_pair(max_it: int, rtol: float) -> None:
    pair = (int(max_it), float(rtol))
    if pair not in _ALLOWED_KSP:
        raise ValueError(
            "BAL_H side inverse accepts only (max_it, rtol)=(128,1e-2) "
            "or (256,1e-4)"
        )


def build_side_balanced_inverse(
    side_system: HybridLocalDtnActionSystem,
    *,
    max_it: int = 128,
    rtol: float = 1.0e-2,
    checkpoint_callback: Callable[[], None] | None = None,
    audit_callback: Callable[[dict[str, Any]], None] | None = None,
) -> SideBalancedInverse:
    """Build one side adapter and release all partial owned state on failure."""

    _validate_ksp_pair(max_it, rtol)
    if not isinstance(side_system, HybridLocalDtnActionSystem):
        raise TypeError("BAL_H side inverse requires a HybridLocalDtnActionSystem")
    full_action = None
    p4_factor = None
    owner_transfer = None
    h6 = None
    try:
        full_action = build_fullspace_physical_dtn_action(side_system)
        p4_factor = build_p4_exact_factor(side_system)
        owner_transfer = build_same_mesh_hcurl_owner_transfer(
            full_action.V,
            full_action.floquet_data,
            p4_factor.physical_action.V,
            p4_factor.physical_action.floquet_data,
        )
        h6 = build_balanced_h6(side_system)
        return SideBalancedInverse(
            side_system,
            full_action,
            p4_factor,
            owner_transfer,
            h6,
            max_it=max_it,
            rtol=rtol,
            checkpoint_callback=checkpoint_callback,
            audit_callback=audit_callback,
        )
    except BaseException:
        if h6 is not None:
            h6.destroy()
        if owner_transfer is not None:
            owner_transfer.destroy()
        if p4_factor is not None:
            p4_factor.destroy()
        if full_action is not None:
            full_action.destroy()
        raise
