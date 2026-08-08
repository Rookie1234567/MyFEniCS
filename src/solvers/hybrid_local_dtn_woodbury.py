r"""Research-only exact DtN Woodbury action for one local Hybrid endcap.

The carrier applies the fixed identity

```math
A^{-1}r = z + W K^{-1} D z,
\qquad z = F^{-1}r,\quad W = F^{-1}C,\quad K = H-DW.
```

``F``, ``C``, ``D``, ``H`` and the base inverse are borrowed.  Only the
distributed owned rows of ``W`` and the replicated small ``K``/LU data are
owned here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .condensed_dtn import gather_small_petsc_matrix
from .hybrid_local_dtn_action import create_hybrid_local_dtn_action_components
from .hybrid_local_iterative_inverse import (
    H5_ATOL,
    H5_MAX_IT,
    H5_RESTART,
    H5_RTOL,
    R3_PRECONDITIONER_PROFILE,
)


R4_MODAL_COUNT = 40

__all__ = (
    "R4_MODAL_COUNT",
    "HybridLocalDtnWoodburyOracle",
    "HybridLocalDtnWoodburyFixedAction",
    "HybridLocalDtnWoodburyLocalInverse",
    "HybridLocalDtnWoodburyLocalInverseResult",
    "build_hybrid_local_dtn_woodbury_local_inverse",
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
    """Exact fixed 40-mode Woodbury action over borrowed local components."""

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
        if self.n_aux != R4_MODAL_COUNT or self.H.getSize() != (
            R4_MODAL_COUNT,
            R4_MODAL_COUNT,
        ):
            raise ValueError("R4 Woodbury oracle requires exactly 40 auxiliary modes")
        if self.C.getSize() != (self.F.getSize()[0], self.n_aux):
            raise ValueError("borrowed C has incompatible active/modal dimensions")
        if self.D.getSize() != (self.n_aux, self.F.getSize()[0]):
            raise ValueError("borrowed D has incompatible modal/active dimensions")
        if self.F.getSize()[0] != self.D.getSize()[1]:
            raise ValueError("borrowed F and D have incompatible active dimensions")
        if not hasattr(base_inverse, "solve"):
            raise TypeError("R4 base inverse must expose solve(source, target)")

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
        W_local = np.empty((local_rows, self.n_aux), dtype=np.complex128)
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
            raise RuntimeError("R4 Woodbury K SVD is not finite")
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
            raise RuntimeError("R4 Woodbury oracle has been destroyed")
        if (
            source.getSize() != self.F.getSize()[1]
            or target.getSize() != self.F.getSize()[0]
        ):
            raise ValueError("R4 Woodbury source/target size does not match F")
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
    """Non-owning one-apply adapter around the fixed R5 Woodbury action.

    The supplied base action and action components are borrowed.  This carrier
    owns only the Oracle's W/K/LU data and scratch vectors; it never constructs
    a KSP and never calls a local-inverse ``solve`` method.
    """

    operator_identity = "r5_fixed_whole_endcap_woodbury_action"

    def __init__(
        self,
        base_action: Any,
        components: Any,
        *,
        base_identity: str = "whole_endcap_ilu0_fixed_smoother",
    ) -> None:
        self.base_action = base_action
        self.components = components
        self.operator = components.F
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
            "base_identity": woodbury["base_identity"],
            "base_factor_count": int(self._base_qualification["factor_count"]),
            "base_factor_borrowed": True,
            "local_direct_factor_count": 0,
            "local_direct_factor_count_owned": 0,
            "nested_ksp_created": bool(self._base_qualification["ksp_created"]),
            "base_diagnostics": base_diagnostics,
            "apply_count": int(woodbury["apply_count"]),
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
        self._destroyed = True


class _WholeEndcapSmootherBase:
    """Adapt only the retained R3 smoother action to the R4 base contract."""

    def __init__(self, inverse: Any) -> None:
        self.inverse = inverse

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        smoother = getattr(self.inverse, "smoother", None)
        if smoother is None:
            raise RuntimeError("R5 whole-endcap smoother is unavailable")
        smoother.solve(source, target)


class _R5WoodburyPcContext:
    """PETSc Python-PC bridge for the fixed R5 Woodbury action."""

    def __init__(self, woodbury: HybridLocalDtnWoodburyOracle) -> None:
        self.woodbury: HybridLocalDtnWoodburyOracle | None = woodbury

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.woodbury is None:
            raise RuntimeError("R5 Woodbury PC context has been destroyed")
        self.woodbury.apply(source, target)


@dataclass
class HybridLocalDtnWoodburyLocalInverseResult:
    """One R5 complete-action solve; its solution is owned by the result."""

    solution: PETSc.Vec
    iterations: int
    converged_reason: int
    reported_relative_residual: float
    true_relative_residual: float
    block_relative_residuals: dict[str, float]
    setup_seconds: float
    solve_seconds: float
    apply_seconds: float
    diagnostics: dict[str, Any]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if not self._destroyed:
            self.solution.destroy()
            self._destroyed = True


class HybridLocalDtnWoodburyLocalInverse:
    """R5 right-FGMRES using the fixed whole-endcap smoother Woodbury PC."""

    operator_identity = "complete_hybrid_action_with_whole_endcap_dtn_woodbury"
    base_identity = "whole_endcap_ilu0_smoother"

    def __init__(
        self,
        action_system: Any,
        base_inverse: Any,
        *,
        components: Any | None = None,
    ) -> None:
        self.action_system = action_system
        self.operator = action_system.A
        self.base_inverse = base_inverse
        self._components_owned = components is None
        self.components = (
            create_hybrid_local_dtn_action_components(action_system)
            if components is None
            else components
        )
        self._destroyed = False
        self.factors_released = False
        self.factor_count_before_destroy: int | None = None
        self.factor_count_after_destroy: int | None = None
        if getattr(base_inverse, "preconditioner_profile", None) != (
            R3_PRECONDITIONER_PROFILE
        ):
            raise ValueError(
                "R5 base inverse must use the fixed whole-endcap ILU(0) profile"
            )
        smoother = getattr(base_inverse, "smoother", None)
        if smoother is None or not hasattr(smoother, "solve"):
            raise TypeError("R5 base inverse must expose its smoother.solve action")
        if self.operator.getType() != "python":
            raise ValueError("R5 complete operator must be a MatPython action")
        if action_system.inventory.get("global_A_materialized") is not False:
            raise ValueError("R5 candidate cannot retain a materialized global A")
        if action_system.inventory.get("direct_factor_count") != 0:
            raise ValueError("R5 candidate cannot own a direct factor")
        self._base_smoother_diagnostics = dict(smoother.diagnostics)
        self._base_factor_count = int(
            self._base_smoother_diagnostics["global_subdomain_count"]
        )
        adapter = _WholeEndcapSmootherBase(base_inverse)
        started = perf_counter()
        self.woodbury = HybridLocalDtnWoodburyOracle(
            adapter,
            self.components,
            base_identity=self.base_identity,
        )
        self._pc_context = _R5WoodburyPcContext(self.woodbury)
        self.ksp = PETSc.KSP().create(self.operator.getComm())
        self.ksp.setOperators(self.operator)
        self.ksp.setType(PETSc.KSP.Type.FGMRES)
        self.ksp.setGMRESRestart(H5_RESTART)
        self.ksp.setPCSide(PETSc.PC.Side.RIGHT)
        self.ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        self.ksp.setTolerances(
            rtol=H5_RTOL,
            atol=H5_ATOL,
            max_it=H5_MAX_IT,
        )
        pc = self.ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(self._pc_context)
        self.ksp.setUp()
        self.setup_seconds = _max_over_comm(
            self.operator.getComm().tompi4py(), perf_counter() - started
        )

    def _true_relative_residual(
        self,
        rhs: PETSc.Vec,
        solution: PETSc.Vec,
        residual: PETSc.Vec,
    ) -> float:
        self.operator.mult(solution, residual)
        residual.scale(PETSc.ScalarType(-1.0))
        residual.axpy(PETSc.ScalarType(1.0), rhs)
        return float(residual.norm()) / max(float(rhs.norm()), 1.0e-30)

    def solve(
        self,
        rhs: PETSc.Vec,
    ) -> HybridLocalDtnWoodburyLocalInverseResult:
        if self._destroyed:
            raise RuntimeError("R5 local inverse has been destroyed")
        if rhs.getSize() != self.operator.getSize()[1]:
            raise ValueError("R5 RHS does not match the complete action")
        solution = rhs.duplicate()
        residual = rhs.duplicate()
        solution.set(0.0)
        apply_before = self.woodbury.apply_count
        apply_seconds_before = self.woodbury.diagnostics["apply_seconds"]
        started = perf_counter()
        try:
            self.ksp.solve(rhs, solution)
            solve_seconds = _max_over_comm(
                self.operator.getComm().tompi4py(), perf_counter() - started
            )
            rhs_norm = max(float(rhs.norm()), 1.0e-30)
            reported = float(self.ksp.getResidualNorm()) / rhs_norm
            true_relative = self._true_relative_residual(rhs, solution, residual)
            woodbury_diagnostics = self.woodbury.diagnostics
            return HybridLocalDtnWoodburyLocalInverseResult(
                solution=solution,
                iterations=int(self.ksp.getIterationNumber()),
                converged_reason=int(self.ksp.getConvergedReason()),
                reported_relative_residual=float(reported),
                true_relative_residual=float(true_relative),
                block_relative_residuals={"active": float(true_relative)},
                setup_seconds=float(self.setup_seconds),
                solve_seconds=float(solve_seconds),
                apply_seconds=float(
                    woodbury_diagnostics["apply_seconds"] - apply_seconds_before
                ),
                diagnostics={
                    "reported_residual_is_monitor": True,
                    "explicit_complete_action_residual_recomputed": True,
                    "pc_apply_count": int(self.woodbury.apply_count - apply_before),
                    "woodbury": woodbury_diagnostics,
                },
            )
        except Exception:
            solution.destroy()
            raise
        finally:
            residual.destroy()

    @property
    def diagnostics(self) -> dict[str, Any]:
        woodbury = self.woodbury.diagnostics
        return {
            "operator": {
                "identity": self.operator_identity,
                "base_identity": self.base_identity,
                "external_dtn_correction": "included",
                "matrix_type": str(self.operator.getType()),
                "matrix_free": True,
                "global_A_materialized": False,
                "direct_factor_count": 0,
                "global_size": int(self.operator.getSize()[0]),
                "local_size": [int(value) for value in self.operator.getLocalSize()],
            },
            "configuration": {
                "preconditioner_profile": R3_PRECONDITIONER_PROFILE,
                "num_subdomains": 1,
                "overlap_fraction": 0.0,
                "coordinate_axis": 0,
                "interpolation": "partition",
                "ilu_levels": 0,
                "factor_only": True,
                "one_apply_per_pc_apply": True,
                "two_step_action_operator": None,
                "outer_solver": "right_fgmres",
                "restart": H5_RESTART,
                "max_it": H5_MAX_IT,
                "rtol": H5_RTOL,
                "atol": H5_ATOL,
                "true_residual_limit": 1.0e-8,
            },
            "base": {
                "identity": self.base_identity,
                "source_matrix_nnz": int(
                    self._base_smoother_diagnostics["global_factor_nnz"]
                ),
                "factor_nnz": int(
                    self._base_smoother_diagnostics["global_stored_factor_nnz"]
                ),
                "factor_count": self._base_factor_count,
                "factor_csr_payload_estimate_bytes": int(
                    self._base_smoother_diagnostics.get(
                        "global_stored_factor_nnz",
                        self._base_smoother_diagnostics["global_factor_nnz"],
                    )
                    * (
                        np.dtype(PETSc.ScalarType).itemsize
                        + np.dtype(PETSc.IntType).itemsize
                    )
                    + (
                        self._base_smoother_diagnostics.get(
                            "global_factor_rows", self.operator.getSize()[0]
                        )
                        + 16
                    )
                    * np.dtype(PETSc.IntType).itemsize
                ),
                "factor_csr_payload_estimate_formula": (
                    "factor_nnz*(scalar_bytes+integer_bytes)"
                    "+(factor_rows+16)*integer_bytes"
                ),
                "smoother_diagnostics": dict(self._base_smoother_diagnostics),
            },
            "woodbury": woodbury,
            "no_direct_fallback": True,
            "lifecycle": {
                "candidate_direct_factor_count": 0,
                "factor_count_before_destroy": self.factor_count_before_destroy
                if self.factor_count_before_destroy is not None
                else self._base_factor_count,
                "factor_count_after_destroy": self.factor_count_after_destroy,
                "factors_released": self.factors_released,
                "components_borrowed": True,
            },
        }

    def destroy(self) -> None:
        """Release outer KSP, Woodbury data, then the whole-endcap smoother."""

        if self._destroyed:
            return
        self.factor_count_before_destroy = self._base_factor_count
        ksp = self.ksp
        self.ksp = None
        if ksp is not None:
            ksp.destroy()
        self._pc_context.woodbury = None
        self.woodbury.destroy()
        if self._components_owned:
            self.components.destroy()
        self.base_inverse.destroy()
        self.factor_count_after_destroy = int(
            getattr(self.base_inverse, "factor_count_after_destroy", 0)
        )
        self.factors_released = bool(
            getattr(self.base_inverse, "factors_released", False)
        )
        self._destroyed = True


def build_hybrid_local_dtn_woodbury_local_inverse(
    action_system: Any,
    base_inverse: Any,
    *,
    components: Any | None = None,
) -> HybridLocalDtnWoodburyLocalInverse:
    """Build the fixed R5 local-inverse Woodbury outer context."""

    return HybridLocalDtnWoodburyLocalInverse(
        action_system,
        base_inverse,
        components=components,
    )
