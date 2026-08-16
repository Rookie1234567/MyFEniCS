"""Exact dynamic-mode DtN Woodbury action over borrowed local components."""

from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .condensed_dtn import gather_small_petsc_matrix


HYBRID_DTN_WOODBURY_MODE_COUNT = 40

__all__ = (
    "HYBRID_DTN_WOODBURY_MODE_COUNT",
    "HybridLocalDtnWoodburyOracle",
    "HybridLocalDtnWoodburyFixedAction",
    "ResearchExactFactorInverse",
    "ResearchExactSideLuAction",
    "create_research_exact_side_lu_action",
    "HybridLocalDtnWoodburyFixedBudgetKrylovAction",
)


def _max_over_comm(comm: MPI.Comm, value: float) -> float:
    return float(comm.allreduce(float(value), op=MPI.MAX))


def _gather_owned_small_vector(vector: PETSc.Vec) -> np.ndarray:
    """Replicate a small distributed vector without using matrix columns."""

    comm = vector.getComm().tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = np.asarray(
        vector.getArray(readonly=True),
        dtype=np.complex128,
    ).copy()
    packets = comm.allgather((first, last, local))
    values = np.empty(int(vector.getSize()), dtype=np.complex128)
    for packet_first, packet_last, packet_values in packets:
        values[packet_first:packet_last] = packet_values
    return values


class HybridLocalDtnWoodburyOracle:
    """Exact mode-count-preserving Woodbury action over borrowed components."""

    def __init__(
        self,
        base_inverse: Any,
        components: Any,
        *,
        base_identity: str = "exact_F_direct",
    ) -> None:
        self.base_inverse = base_inverse
        self.components = components
        self.F = components.F
        self.C = components.C
        self.D = components.D
        self.H = components.H
        self.base_identity = str(base_identity)
        self.comm = self.F.getComm().tompi4py()
        self.n_aux = int(self.H.getSize()[0])
        if self.n_aux <= 0 or self.H.getSize() != (self.n_aux, self.n_aux):
            raise ValueError("Woodbury oracle requires a non-empty square modal block")
        if self.C.getSize() != (self.F.getSize()[0], self.n_aux):
            raise ValueError("borrowed C has incompatible active/modal dimensions")
        if self.D.getSize() != (self.n_aux, self.F.getSize()[0]):
            raise ValueError("borrowed D has incompatible modal/active dimensions")
        if self.F.getSize()[0] != self.D.getSize()[1]:
            raise ValueError("borrowed F and D have incompatible active dimensions")
        if not hasattr(base_inverse, "solve"):
            raise TypeError("Woodbury base inverse must expose solve(source, target)")

        self._destroyed = False
        self._z = self.F.createVecLeft()
        self._d_work = self.D.createVecLeft()
        self._W_local: np.ndarray | None = None
        self._K: np.ndarray | None = None
        self._lu: np.ndarray | None = None
        self._piv: np.ndarray | None = None
        self._K_rank: int | None = None
        self._K_condition: float | None = None
        self._arrays_finite = False
        self._setup_seconds = 0.0
        self._apply_seconds = 0.0
        self.apply_count = 0
        self._build()

    def _build(self) -> None:
        started = perf_counter()
        H_dense = np.asarray(gather_small_petsc_matrix(self.H), dtype=np.complex128)
        local_rows = int(self.F.getLocalSize()[0])
        W_local = np.empty(
            (local_rows, self.n_aux),
            dtype=np.complex128,
        )
        D_times_W = np.empty((self.n_aux, self.n_aux), dtype=np.complex128)
        modal_basis = self.C.createVecRight()
        c_column = self.C.createVecLeft()
        w_column = self.F.createVecLeft()
        d_column = self.D.createVecLeft()
        try:
            first, last = (int(value) for value in modal_basis.getOwnershipRange())
            for column in range(self.n_aux):
                modal_basis.set(0.0)
                if first <= column < last:
                    modal_basis.getArray()[column - first] = PETSc.ScalarType(1.0)
                modal_basis.assemble()
                self.C.mult(modal_basis, c_column)
                self.base_inverse.solve(c_column, w_column)
                W_local[:, column] = np.asarray(
                    w_column.getArray(readonly=True),
                    dtype=np.complex128,
                )
                self.D.mult(w_column, d_column)
                D_times_W[:, column] = _gather_owned_small_vector(d_column)
        finally:
            d_column.destroy()
            w_column.destroy()
            c_column.destroy()
            modal_basis.destroy()

        K = H_dense - D_times_W
        singular_values = np.linalg.svd(K, compute_uv=False)
        if singular_values.size == 0 or not np.all(np.isfinite(singular_values)):
            raise RuntimeError("Woodbury K SVD is not finite")
        scale = float(singular_values[0])
        rank_tolerance = np.finfo(np.float64).eps * max(K.shape) * scale
        rank = int(np.count_nonzero(singular_values > rank_tolerance))
        condition = (
            float(singular_values[0] / singular_values[-1])
            if singular_values[-1] > 0.0
            else float("inf")
        )
        lu, piv = lu_factor(K, check_finite=True)
        local_arrays_finite = bool(
            np.all(np.isfinite(H_dense))
            and np.all(np.isfinite(W_local))
            and np.all(np.isfinite(D_times_W))
            and np.all(np.isfinite(K))
            and np.all(np.isfinite(lu))
            and np.all(np.isfinite(piv))
        )
        self._arrays_finite = bool(
            self.comm.allreduce(local_arrays_finite, op=MPI.LAND)
        )
        self._W_local = W_local
        self._K = K
        self._lu = np.asarray(lu, dtype=np.complex128)
        self._piv = np.asarray(piv, dtype=np.int32)
        self._K_rank = rank
        self._K_condition = condition
        self._setup_seconds = _max_over_comm(
            self.comm,
            perf_counter() - started,
        )

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the exact Woodbury inverse without touching borrowed objects."""

        if self._destroyed:
            raise RuntimeError("Woodbury oracle has been destroyed")
        if (
            source.getSize() != self.F.getSize()[1]
            or target.getSize() != self.F.getSize()[0]
        ):
            raise ValueError("Woodbury source/target size does not match F")
        started = perf_counter()
        self.base_inverse.solve(source, self._z)
        self.D.mult(self._z, self._d_work)
        d_values = _gather_owned_small_vector(self._d_work)
        q = lu_solve((self._lu, self._piv), d_values, check_finite=True)
        self._z.copy(target)
        target.getArray()[:] += self._W_local @ q
        local_apply_finite = bool(
            np.all(np.isfinite(self._z.getArray(readonly=True)))
            and np.all(np.isfinite(self._d_work.getArray(readonly=True)))
            and np.all(np.isfinite(q))
            and np.all(np.isfinite(target.getArray(readonly=True)))
        )
        self._arrays_finite = bool(
            self._arrays_finite and self.comm.allreduce(local_apply_finite, op=MPI.LAND)
        )
        self.apply_count += 1
        self._apply_seconds += _max_over_comm(
            self.comm,
            perf_counter() - started,
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        W_local = self._W_local
        K = self._K
        lu = self._lu
        piv = self._piv
        return {
            "base_identity": self.base_identity,
            "n_aux": self.n_aux,
            "normal_equations": False,
            "W_local_shape": None if W_local is None else list(W_local.shape),
            "W_local_nbytes": None if W_local is None else int(W_local.nbytes),
            "K_shape": None if K is None else list(K.shape),
            "K_dtype": None if K is None else str(K.dtype),
            "K_nbytes": None if K is None else int(K.nbytes),
            "K_rank": self._K_rank,
            "K_condition_number": self._K_condition,
            "arrays_finite": bool(self._arrays_finite),
            "LU_shape": None if lu is None else list(lu.shape),
            "LU_nbytes": (
                None if lu is None or piv is None else int(lu.nbytes + piv.nbytes)
            ),
            "setup_seconds": float(self._setup_seconds),
            "apply_count": int(self.apply_count),
            "apply_seconds": float(self._apply_seconds),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        """Release owned scratch and dense data; borrowed components survive."""

        if self._destroyed:
            return
        self._z.destroy()
        self._d_work.destroy()
        self._z = None
        self._d_work = None
        self._W_local = None
        self._K = None
        self._lu = None
        self._piv = None
        self._destroyed = True


class ResearchExactFactorInverse:
    """Research-only PETSc LU factor that borrows, but never destroys, ``F``."""

    def __init__(
        self,
        matrix: PETSc.Mat,
        *,
        factor_solver_type: str | None = "mumps",
    ) -> None:
        if not isinstance(matrix, PETSc.Mat):
            raise TypeError("Exact research factor requires a PETSc matrix")
        if str(matrix.getType()).lower() == "python":
            raise ValueError("Exact research factor requires an explicit F matrix")
        if matrix.getSize()[0] != matrix.getSize()[1]:
            raise ValueError("Exact research factor requires square F")
        self.matrix = matrix
        self.factor_solver_type = factor_solver_type
        self.ksp = PETSc.KSP().create(matrix.getComm())
        self.ksp.setOperators(matrix)
        self.ksp.setType("preonly")
        pc = self.ksp.getPC()
        pc.setType("lu")
        if factor_solver_type is not None:
            pc.setFactorSolverType(str(factor_solver_type))
        self.ksp.setUp()
        self._destroyed = False
        self._solve_count = 0

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Exact research factor has been destroyed")
        if source.getSize() != self.matrix.getSize()[1]:
            raise ValueError("Exact research factor source has the wrong size")
        if target.getSize() != self.matrix.getSize()[0]:
            raise ValueError("Exact research factor target has the wrong size")
        self.ksp.solve(source, target)
        reason = int(self.ksp.getConvergedReason())
        if reason < 0:
            raise RuntimeError(f"Exact research LU solve failed with reason {reason}")
        self._solve_count += 1

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.solve(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "research_only": True,
            "operator_identity": "research_exact_side_lu",
            "factor_solver_type": self.factor_solver_type,
            "ksp_created": True,
            "direct_factor_count": 0 if self._destroyed else 1,
            "direct_factor_count_owned": 0 if self._destroyed else 1,
            "global_hybrid_direct_factor_count": 0,
            "solve_count": int(self._solve_count),
            "factor_destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.ksp.destroy()
        self.ksp = None
        self._destroyed = True


class ResearchExactSideLuAction:
    """Research-only exact F inverse plus the existing DtN Woodbury correction."""

    def __init__(
        self,
        explicit_f: PETSc.Mat,
        components: Any,
        *,
        factor_solver_type: str | None = "mumps",
    ) -> None:
        if getattr(components, "F", None) is not explicit_f:
            raise ValueError("Research exact-side action must use components.F itself")
        self.factor = ResearchExactFactorInverse(
            explicit_f,
            factor_solver_type=factor_solver_type,
        )
        try:
            self.woodbury = HybridLocalDtnWoodburyOracle(
                self.factor,
                components,
                base_identity="research_exact_F_direct",
            )
        except Exception:
            self.factor.destroy()
            raise
        self.operator = components.F
        self.components = components
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Research exact-side action has been destroyed")
        self.woodbury.apply(source, target)

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        factor = self.factor.diagnostics
        woodbury = self.woodbury.diagnostics
        return {
            "research_only": True,
            "operator_identity": "research_exact_side_lu_woodbury",
            "factor_solver_type": factor["factor_solver_type"],
            "ksp_created": True,
            "direct_factor_count": factor["direct_factor_count"],
            "direct_factor_count_owned": factor["direct_factor_count_owned"],
            "ilu_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
            "woodbury": woodbury,
            "apply_count": int(woodbury["apply_count"]),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.woodbury.destroy()
        self.factor.destroy()
        self._destroyed = True


def create_research_exact_side_lu_action(
    explicit_f: PETSc.Mat,
    components: Any,
    *,
    factor_solver_type: str | None = "mumps",
) -> ResearchExactSideLuAction:
    """Create one exact-side LU plus DtN Woodbury action for research only."""

    if getattr(components, "F", None) is not explicit_f:
        raise ValueError("Research exact-side factor must use components.F itself")
    return ResearchExactSideLuAction(
        explicit_f,
        components,
        factor_solver_type=factor_solver_type,
    )


class _FixedBaseApplyAdapter:
    """Adapt one borrowed fixed smoother callback to the Oracle solve contract."""

    def __init__(self, base_action: Any) -> None:
        if not hasattr(base_action, "apply"):
            raise TypeError(
                "Fixed Woodbury base action must expose apply(source, target)"
            )
        self.base_action = base_action

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.base_action.apply(source, target)


class HybridLocalDtnWoodburyFixedAction:
    """Non-owning one-apply adapter around the fixed Woodbury action."""

    operator_identity = "whole_endcap_ilu0_woodbury_fixed_action"

    def __init__(
        self,
        base_action: Any,
        components: Any,
        *,
        base_identity: str = "whole_endcap_ilu0_fixed_smoother",
        residual_operator: PETSc.Mat | None = None,
        residual_correction_steps: int = 1,
    ) -> None:
        if residual_correction_steps not in (1, 2, 4, 8):
            raise ValueError("Residual correction steps must be one of 1, 2, 4, or 8")
        if residual_correction_steps > 1 and residual_operator is None:
            raise ValueError(
                "Multi-pass correction requires a borrowed residual operator"
            )
        if residual_correction_steps == 1 and residual_operator is not None:
            raise ValueError(
                "A residual operator is only valid for two-pass correction"
            )
        self.base_action = base_action
        self.components = components
        self.operator = components.F
        self.operator_identity = (
            "whole_endcap_ilu0_woodbury_fixed_action_two_pass_residual_correction"
            if residual_correction_steps == 2
            else (
                f"whole_endcap_ilu0_woodbury_fixed_action_{residual_correction_steps}_pass_residual_correction"
                if residual_correction_steps > 2
                else self.operator_identity
            )
        )
        self.residual_operator = residual_operator
        self._residual_operator_borrowed = residual_operator is not None
        self.residual_correction_steps = int(residual_correction_steps)
        self._logical_apply_count = 0
        self._residual: PETSc.Vec | None = None
        self._correction: PETSc.Vec | None = None
        self._correction_operator_matrix_free = bool(
            residual_operator is not None
            and str(residual_operator.getType()).lower() == "python"
        )
        base_diagnostics = getattr(base_action, "diagnostics", None)
        if callable(base_diagnostics):
            base_diagnostics = base_diagnostics()
        if not isinstance(base_diagnostics, dict):
            raise TypeError("Fixed Woodbury base action needs diagnostics")
        if (
            "factor_count" not in base_diagnostics
            or "ksp_created" not in base_diagnostics
        ):
            raise ValueError(
                "Fixed Woodbury base diagnostics need factor_count and ksp_created"
            )
        self._base_qualification = {
            "factor_count": int(base_diagnostics["factor_count"]),
            "ksp_created": bool(base_diagnostics["ksp_created"]),
        }
        self._base_adapter = _FixedBaseApplyAdapter(base_action)
        self.woodbury = HybridLocalDtnWoodburyOracle(
            self._base_adapter,
            components,
            base_identity=base_identity,
        )
        if self.residual_correction_steps > 1:
            self._residual = self.operator.createVecLeft()
            self._correction = self.operator.createVecLeft()
        self._destroyed = False
        self._pre_destroy_diagnostics: dict[str, Any] | None = None
        self._base_pre_destroy_diagnostics: dict[str, Any] | None = None

    def _base_diagnostics_now(self) -> dict[str, Any]:
        diagnostics = getattr(self.base_action, "diagnostics", None)
        if callable(diagnostics):
            diagnostics = diagnostics()
        if not isinstance(diagnostics, dict):
            raise RuntimeError("Fixed Woodbury base diagnostics are unavailable")
        return dict(diagnostics)

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Fixed Woodbury action has been destroyed")
        self.woodbury.apply(source, target)
        for _ in range(self.residual_correction_steps - 1):
            self.residual_operator.mult(target, self._residual)
            self._residual.scale(PETSc.ScalarType(-1.0))
            self._residual.axpy(PETSc.ScalarType(1.0), source)
            self.woodbury.apply(self._residual, self._correction)
            target.axpy(PETSc.ScalarType(1.0), self._correction)
        self._logical_apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        woodbury = (
            self._pre_destroy_diagnostics
            if self._pre_destroy_diagnostics is not None
            else self.woodbury.diagnostics
        )
        base_diagnostics = (
            self._base_pre_destroy_diagnostics
            if self._base_pre_destroy_diagnostics is not None
            else self._base_diagnostics_now()
        )
        return {
            "operator_identity": self.operator_identity,
            "residual_correction_steps": int(self.residual_correction_steps),
            "residual_correction_operator_borrowed": self._residual_operator_borrowed,
            "correction_operator_matrix_free": self._correction_operator_matrix_free,
            "logical_apply_count": int(self._logical_apply_count),
            "base_identity": woodbury["base_identity"],
            "base_factor_count": int(self._base_qualification["factor_count"]),
            "base_factor_borrowed": True,
            "local_direct_factor_count": 0,
            "local_direct_factor_count_owned": 0,
            "global_hybrid_direct_factor_count": 0,
            "nested_ksp_created": bool(self._base_qualification["ksp_created"]),
            "base_diagnostics": base_diagnostics,
            "apply_count": int(self._logical_apply_count),
            "raw_apply_count": int(woodbury["apply_count"]),
            "woodbury": dict(woodbury),
            "components_borrowed": True,
            "owned_action_data_released": bool(self._destroyed),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._base_pre_destroy_diagnostics = self._base_diagnostics_now()
        self._pre_destroy_diagnostics = dict(self.woodbury.diagnostics)
        self.woodbury.destroy()
        if self._residual is not None:
            self._residual.destroy()
            self._residual = None
        if self._correction is not None:
            self._correction.destroy()
            self._correction = None
        self.residual_operator = None
        self._destroyed = True


class _FixedBudgetPythonPcContext:
    """Borrow one fixed side action as a PETSc Python right-preconditioner."""

    def __init__(self, action: Any) -> None:
        self.action: Any | None = action

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.action is None:
            raise RuntimeError("fixed-budget Python PC has been destroyed")
        self.action.apply(source, target)

    def destroy(self, _pc: PETSc.PC) -> None:
        self.action = None


class HybridLocalDtnWoodburyFixedBudgetKrylovAction:
    """Apply a fixed-budget side Krylov inverse with a borrowed one-pass PC.

    This research-only action owns only its inner KSP and Python-PC context.
    The side operator and the fixed Woodbury action are borrowed.  The returned
    vector is intentionally judged by an external true residual; this class
    records the KSP outcome but does not turn it into a convergence claim.
    """

    _ALLOWED_BUDGETS = (8, 16, 32)
    operator_identity = "fixed_budget_side_fgmres_right_fixed_woodbury"

    def __init__(
        self,
        operator: PETSc.Mat,
        right_preconditioner: Any,
        *,
        budget: int,
    ) -> None:
        if budget not in self._ALLOWED_BUDGETS:
            raise ValueError("Fixed-budget side Krylov budget must be 8, 16, or 32")
        if (
            not isinstance(operator, PETSc.Mat)
            or str(operator.getType()).lower() != "python"
        ):
            raise TypeError(
                "Fixed-budget side Krylov requires a matrix-free MatPython operator"
            )
        if not isinstance(right_preconditioner, HybridLocalDtnWoodburyFixedAction):
            raise TypeError(
                "Fixed-budget side Krylov requires HybridLocalDtnWoodburyFixedAction"
            )
        right_diagnostics = right_preconditioner.diagnostics
        if (
            right_diagnostics.get("residual_correction_steps") != 1
            or right_diagnostics.get("local_direct_factor_count") != 0
            or right_diagnostics.get("global_hybrid_direct_factor_count") != 0
        ):
            raise ValueError(
                "Fixed-budget side Krylov requires one-pass factor-free right PC"
            )

        self.operator = operator
        self.right_preconditioner = right_preconditioner
        self.budget = int(budget)
        self._right_diagnostics = dict(right_diagnostics)
        self._direct_factor_count = int(right_diagnostics["local_direct_factor_count"])
        self._global_direct_factor_count = int(
            right_diagnostics["global_hybrid_direct_factor_count"]
        )
        self._comm = operator.getComm().tompi4py()
        self._right_preconditioner_identity = str(
            self._right_diagnostics.get(
                "operator_identity", type(right_preconditioner).__name__
            )
        )
        self._pc_context = _FixedBudgetPythonPcContext(right_preconditioner)
        self._inner_ksp = PETSc.KSP().create(operator.getComm())
        self._inner_ksp.setOperators(operator)
        self._inner_ksp.setType("fgmres")
        self._inner_ksp.setPCSide(PETSc.PC.Side.RIGHT)
        self._inner_ksp.setGMRESRestart(self.budget)
        self._inner_ksp.setNormType(PETSc.KSP.NormType.NONE)
        self._inner_ksp.setInitialGuessNonzero(False)
        self._inner_ksp.setTolerances(max_it=self.budget)
        pc = self._inner_ksp.getPC()
        pc.setType("python")
        pc.setPythonContext(self._pc_context)
        self._inner_ksp.setUp()
        self._apply_count = 0
        self._total_iterations = 0
        self._last_iterations: int | None = None
        self._last_reason: int | None = None
        self._last_seconds: float | None = None
        self._total_seconds = 0.0
        self._inner_ksp_destroyed = False
        self._pc_context_destroyed = False
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Fixed-budget side Krylov action has been destroyed")
        if source.getSize() != self.operator.getSize()[1]:
            raise ValueError("Fixed-budget side Krylov source has the wrong size")
        if target.getSize() != self.operator.getSize()[0]:
            raise ValueError("Fixed-budget side Krylov target has the wrong size")
        target.set(0.0)
        started = perf_counter()
        self._inner_ksp.solve(source, target)
        elapsed = _max_over_comm(self._comm, perf_counter() - started)
        iterations = int(self._inner_ksp.getIterationNumber())
        reason = int(self._inner_ksp.getConvergedReason())
        self._apply_count += 1
        self._total_iterations += iterations
        self._last_iterations = iterations
        self._last_reason = reason
        self._last_seconds = float(elapsed)
        self._total_seconds += float(elapsed)

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "research_only": True,
            "operator_identity": self.operator_identity,
            "requested_budget": int(self.budget),
            "ksp_type": "fgmres",
            "pc_side": "right",
            "restart": int(self.budget),
            "norm_type": "none",
            "zero_initial_guess": True,
            "right_preconditioner_identity": self._right_preconditioner_identity,
            "right_preconditioner_borrowed": True,
            "direct_factor_count": self._direct_factor_count,
            "global_hybrid_direct_factor_count": self._global_direct_factor_count,
            "apply_count": int(self._apply_count),
            "total_inner_iterations": int(self._total_iterations),
            "last_inner_iterations": self._last_iterations,
            "last_converged_reason": self._last_reason,
            "last_apply_seconds": self._last_seconds,
            "total_apply_seconds": float(self._total_seconds),
            "inner_ksp_created": True,
            "inner_ksp_destroyed": bool(self._inner_ksp_destroyed),
            "pc_context_destroyed": bool(self._pc_context_destroyed),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._inner_ksp.destroy()
        self._inner_ksp = None
        self._inner_ksp_destroyed = True
        self._pc_context = None
        self._pc_context_destroyed = True
        self.right_preconditioner = None
        self.operator = None
        self._destroyed = True
