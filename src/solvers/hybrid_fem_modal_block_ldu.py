"""Exact block-LDU oracle for the Task037b Hybrid action operator.

The global operator remains the H2b MatPython action.  This module temporarily
uses explicit-condensed bottom/top matrices and their MUMPS factors only to
verify the exact right block-LDU algebra on a small oracle problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

import numpy as np
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from .hybrid_fem_modal_schur_direct import (
    HybridModalSchurDirectSystem,
    build_hybrid_modal_schur_direct_system,
    modal_coupling_action,
)

__all__ = (
    "HybridBlockLduPreconditioner",
    "HybridBlockLduSolveResult",
    "HybridBlockActionSystem",
    "HybridBlockLduPhysicalSolution",
    "HybridBlockLduDirectAction",
    "HybridActionModalSchurSystem",
    "HybridBlockLduScreenResult",
    "HybridBlockLduFullSolveResult",
    "build_hybrid_action_modal_schur",
    "create_action_block_ldu_preconditioner",
    "screen_action_block_ldu",
    "solve_action_block_ldu_full",
    "multimetric_true_residual_decision",
    "action_block_screen_gate",
    "action_block_v3_progressive_gate",
    "create_exact_block_ldu_preconditioner",
    "create_g_only_block_ldu_preconditioner",
    "modal_block_diagnostic",
    "solve_exact_block_ldu",
)

_TINY = np.finfo(float).tiny


def _replicated_modal_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    owner = comm.size - 1
    local = None
    if comm.rank == owner:
        local = np.asarray(
            vector.getValues(np.arange(vector.getSize(), dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(local, root=owner), dtype=np.complex128)


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


def _action_diagnostics(action: Any) -> dict[str, Any]:
    diagnostics = getattr(action, "diagnostics", None)
    if callable(diagnostics):
        diagnostics = diagnostics()
    if not isinstance(diagnostics, dict):
        raise TypeError("A block-LDU side action must expose diagnostics.")
    return dict(diagnostics)


def _action_operator(action: Any) -> PETSc.Mat:
    operator = getattr(action, "operator", None)
    if operator is None:
        operator = getattr(action, "A", None)
    if operator is None:
        raise TypeError("A block-LDU side action must expose operator or A.")
    return operator


def _action_factor_counts(diagnostics: dict[str, Any]) -> tuple[int, int]:
    direct = diagnostics.get(
        "direct_factor_count",
        diagnostics.get("local_direct_factor_count", 0),
    )
    ilu = diagnostics.get(
        "ilu_factor_count",
        diagnostics.get("base_factor_count", 0),
    )
    return int(direct), int(ilu)


@dataclass
class HybridBlockLduDirectAction:
    """One borrowed-layout direct local factor action.

    The factor is owned by this small carrier, while a block-LDU context only
    borrows the carrier and never destroys it.
    """

    operator: PETSc.Mat
    factor: Any
    factor_inventory: dict[str, Any] = field(default_factory=dict)
    _apply_count: int = field(default=0, init=False, repr=False)
    _destroyed: bool = field(default=False, init=False, repr=False)

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("Direct block-LDU action has been destroyed")
        self.factor.solve(source, target)
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "operator_identity": "exact_local_direct_action",
            "direct_factor_count": 0 if self._destroyed else 1,
            "ilu_factor_count": 0,
            "factor_count": 0 if self._destroyed else 1,
            "factor_inventory": dict(self.factor_inventory),
            "apply_count": int(self._apply_count),
            "factors_released": bool(self._destroyed),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.factor.destroy()
        self.factor = None
        self._destroyed = True


@dataclass
class HybridActionModalSchurSystem:
    """Fixed-LU modal Schur assembled from two borrowed side actions."""

    modal_schur: np.ndarray
    modal_constraint: np.ndarray
    lu: np.ndarray
    pivots: np.ndarray
    rank: int
    condition: float
    matrix_repeat_error: float
    lu_repeat_solve_error: float
    build_apply_count: dict[str, int]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._shape = tuple(self.modal_schur.shape)
        self._array_bytes = {
            "modal_schur_bytes": int(self.modal_schur.nbytes),
            "modal_constraint_bytes": int(self.modal_constraint.nbytes),
            "lu_bytes": int(self.lu.nbytes),
            "pivots_bytes": int(self.pivots.nbytes),
        }
        self._finite = bool(
            np.all(np.isfinite(self.modal_schur))
            and np.all(np.isfinite(self.lu))
            and np.all(np.isfinite(self.pivots))
        )

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("Action modal Schur has been destroyed")
        values = np.asarray(rhs, dtype=np.complex128)
        if values.shape != (self.modal_schur.shape[0],):
            raise ValueError("Action modal Schur RHS has the wrong shape.")
        return np.asarray(
            lu_solve((self.lu, self.pivots), values, check_finite=True),
            dtype=np.complex128,
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        finite = (
            self._finite
            if self._destroyed
            else bool(
                np.all(np.isfinite(self.modal_schur))
                and np.all(np.isfinite(self.lu))
                and np.all(np.isfinite(self.pivots))
            )
        )
        return {
            "shape": list(self._shape),
            "dtype": "complex128",
            "rank": int(self.rank),
            "condition": float(self.condition),
            "finite": finite,
            "normal_equations": False,
            "matrix_repeat_error": float(self.matrix_repeat_error),
            "lu_repeat_solve_error": float(self.lu_repeat_solve_error),
            "build_apply_count": dict(self.build_apply_count),
            **self._array_bytes,
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.modal_schur = None
        self.modal_constraint = None
        self.lu = None
        self.pivots = None
        self._destroyed = True


def _build_action_modal_contribution(
    side: str,
    coupling: HybridInternalModeCoupling,
    action: Any,
    modal_count: int,
) -> np.ndarray:
    operator = _action_operator(action)
    projection = (
        coupling.bottom.projection if side == "bottom" else coupling.top.projection
    )
    contribution = np.empty((modal_count * 2, modal_count * 2), dtype=np.complex128)
    for column in range(modal_count * 2):
        modal = np.zeros(modal_count * 2, dtype=np.complex128)
        modal[column] = 1.0
        traction = modal_coupling_action(side, coupling, modal)
        response = operator.createVecLeft()
        projected = projection.createVecLeft()
        try:
            action.apply(traction, response)
            projection.mult(response, projected)
            values = _replicated_modal_values(projected)
            row_slice = (
                slice(0, modal_count)
                if side == "bottom"
                else slice(modal_count, 2 * modal_count)
            )
            contribution[row_slice, column] = values
            other_slice = (
                slice(modal_count, 2 * modal_count)
                if side == "bottom"
                else slice(0, modal_count)
            )
            contribution[other_slice, column] = 0.0
        finally:
            projected.destroy()
            response.destroy()
            traction.destroy()
    return contribution


def build_hybrid_action_modal_schur(
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
) -> HybridActionModalSchurSystem:
    """Build two complete approximate modal Schur matrices and one LU."""

    modal_count = int(coupling.mode_count_per_direction)
    internal_count = 2 * modal_count
    constraint = np.asarray(
        internal_modal_constraint_matrix(coupling), dtype=np.complex128
    )
    before = {
        "bottom": int(_action_diagnostics(bottom_action).get("apply_count", 0)),
        "top": int(_action_diagnostics(top_action).get("apply_count", 0)),
    }
    first = constraint.copy()
    first -= _build_action_modal_contribution(
        "bottom", coupling, bottom_action, modal_count
    )
    first -= _build_action_modal_contribution("top", coupling, top_action, modal_count)
    second = constraint.copy()
    second -= _build_action_modal_contribution(
        "bottom", coupling, bottom_action, modal_count
    )
    second -= _build_action_modal_contribution("top", coupling, top_action, modal_count)
    after = {
        "bottom": int(_action_diagnostics(bottom_action).get("apply_count", 0)),
        "top": int(_action_diagnostics(top_action).get("apply_count", 0)),
    }
    expected = 2 * internal_count
    build_apply_count = {side: after[side] - before[side] for side in ("bottom", "top")}
    if any(value != expected for value in build_apply_count.values()):
        raise RuntimeError(
            "Action modal Schur build did not use exactly two complete matrices."
        )
    matrix_repeat_error = float(
        np.linalg.norm(first - second) / max(float(np.linalg.norm(first)), _TINY)
    )
    expected_shape = (internal_count, internal_count)
    for name, matrix in (
        ("constraint", constraint),
        ("modal Schur", first),
        ("modal Schur repeat", second),
    ):
        if matrix.shape != expected_shape:
            raise ValueError(
                f"Action {name} has shape {matrix.shape}, expected {expected_shape}."
            )
        if matrix.dtype != np.dtype(np.complex128):
            raise TypeError(f"Action {name} must have complex128 dtype.")
        if not np.all(np.isfinite(matrix)):
            raise ValueError(f"Action {name} contains non-finite values.")
    if not np.isfinite(matrix_repeat_error) or matrix_repeat_error > 1e-13:
        raise ValueError("Action modal Schur repeat error exceeds 1e-13.")
    singular_values = np.linalg.svd(first, compute_uv=False)
    rank_scale = (
        np.finfo(float).eps * max(first.shape) * float(singular_values[0])
        if singular_values.size
        else 0.0
    )
    rank = int(np.count_nonzero(singular_values > rank_scale))
    condition = float(np.linalg.cond(first))
    if rank != internal_count:
        raise ValueError("Action modal Schur is not full rank.")
    if not np.isfinite(condition) or condition > 1e12:
        raise ValueError("Action modal Schur condition exceeds 1e12.")
    lu, pivots = lu_factor(first, check_finite=True)
    if not np.all(np.isfinite(lu)) or not np.all(np.isfinite(pivots)):
        raise ValueError("Action modal Schur LU contains non-finite values.")
    test_rhs = np.arange(1, internal_count + 1, dtype=np.float64).astype(np.complex128)
    first_solution = lu_solve((lu, pivots), test_rhs, check_finite=True)
    second_solution = lu_solve((lu, pivots), test_rhs, check_finite=True)
    if not np.all(np.isfinite(first_solution)) or not np.all(
        np.isfinite(second_solution)
    ):
        raise ValueError("Action modal Schur LU solve contains non-finite values.")
    lu_repeat_solve_error = float(
        np.linalg.norm(first_solution - second_solution)
        / max(float(np.linalg.norm(first_solution)), _TINY)
    )
    if not np.isfinite(lu_repeat_solve_error) or lu_repeat_solve_error > 1e-13:
        raise ValueError("Action modal Schur LU repeat error exceeds 1e-13.")
    return HybridActionModalSchurSystem(
        modal_schur=first,
        modal_constraint=constraint,
        lu=np.asarray(lu, dtype=np.complex128),
        pivots=np.asarray(pivots, dtype=np.int32),
        rank=rank,
        condition=condition,
        matrix_repeat_error=matrix_repeat_error,
        lu_repeat_solve_error=lu_repeat_solve_error,
        build_apply_count=build_apply_count,
    )


@dataclass
class HybridBlockLduPreconditioner:
    """Reusable exact right block-LDU application context.

    ``bottom_system`` and ``top_system`` are explicit-condensed oracle views;
    the operator being preconditioned can still be the H2b action-only matrix.
    Exact mode owns two direct factors and the dense modal Schur; action mode
    borrows side actions and owns only its modal Schur/workspace.
    """

    layout: HybridAugmentedLayout
    coupling: HybridInternalModeCoupling
    bottom_system: object
    top_system: object
    modal_schur_system: HybridModalSchurDirectSystem | None
    modal_block_override: np.ndarray | None = None
    modal_block_name: str = "exact_s_m"
    bottom_action: Any | None = None
    top_action: Any | None = None
    action_modal_schur_system: HybridActionModalSchurSystem | None = None
    defer_action_modal_schur_release: bool = False
    _destroyed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._action_mode = self.action_modal_schur_system is not None
        self._action_modal_schur_released = False
        if self._action_mode:
            if self.bottom_action is None or self.top_action is None:
                raise ValueError("Action block-LDU requires both side actions.")
            if self.modal_schur_system is not None:
                raise ValueError(
                    "Action block-LDU cannot retain a direct Schur system."
                )
            self.bottom_factor = None
            self.top_factor = None
            modal_block = self.action_modal_schur_system.modal_schur
        else:
            if self.modal_schur_system is None:
                raise ValueError("Direct block-LDU requires a modal Schur system.")
            bottom_factor = self.modal_schur_system.bottom_factor
            top_factor = self.modal_schur_system.top_factor
            if bottom_factor is None or top_factor is None:
                raise RuntimeError("H3 exact block-LDU requires both direct factors.")
            self.bottom_factor = bottom_factor
            self.top_factor = top_factor
            modal_block = (
                self.modal_schur_system.modal_schur
                if self.modal_block_override is None
                else self.modal_block_override
            )
        self.modal_schur = np.asarray(modal_block, dtype=np.complex128)
        self._modal_block_condition = float(np.linalg.cond(self.modal_schur))
        self.mode_count = int(self.coupling.mode_count_per_direction)
        self._forward_factors = np.asarray(
            self.coupling.propagation.forward.factors, dtype=np.complex128
        )
        self._backward_factors = np.asarray(
            self.coupling.propagation.backward.factors, dtype=np.complex128
        )
        self._bottom_rhs = self.bottom_system.A.createVecRight()
        self._top_rhs = self.top_system.A.createVecRight()
        self._bottom_first = self.bottom_system.A.createVecLeft()
        self._top_first = self.top_system.A.createVecLeft()
        self._bottom_delta = self.bottom_system.A.createVecLeft()
        self._top_delta = self.top_system.A.createVecLeft()
        self._bottom_coupling = self.bottom_system.A.createVecLeft()
        self._top_coupling = self.top_system.A.createVecLeft()
        self._bottom_projection = self.coupling.bottom.projection.createVecLeft()
        self._top_projection = self.coupling.top.projection.createVecLeft()
        self._bottom_positive_source = (
            self.coupling.bottom.positive_traction.createVecRight()
        )
        self._bottom_negative_source = (
            self.coupling.bottom.negative_traction.createVecRight()
        )
        self._top_positive_source = self.coupling.top.positive_traction.createVecRight()
        self._top_negative_source = self.coupling.top.negative_traction.createVecRight()
        self._bottom_positive_target = (
            self.coupling.bottom.positive_traction.createVecLeft()
        )
        self._bottom_negative_target = (
            self.coupling.bottom.negative_traction.createVecLeft()
        )
        self._top_positive_target = self.coupling.top.positive_traction.createVecLeft()
        self._top_negative_target = self.coupling.top.negative_traction.createVecLeft()
        self._modal_rhs = np.empty(2 * self.mode_count, dtype=np.complex128)
        self._modal_solution = np.empty_like(self._modal_rhs)
        self._pc_apply_count = 0
        self._pc_apply_seconds = 0.0
        self._check_layouts()

    @property
    def direct_factor_count(self) -> int:
        if self._action_mode:
            bottom_direct, _ = _action_factor_counts(
                _action_diagnostics(self.bottom_action)
            )
            top_direct, _ = _action_factor_counts(_action_diagnostics(self.top_action))
            return bottom_direct + top_direct
        return 2

    @property
    def factors_released(self) -> bool:
        return False if self._action_mode else self._destroyed

    @property
    def inventory(self) -> dict[str, object]:
        if self._action_mode:
            bottom_diagnostics = _action_diagnostics(self.bottom_action)
            top_diagnostics = _action_diagnostics(self.top_action)
            bottom_direct, bottom_ilu = _action_factor_counts(bottom_diagnostics)
            top_direct, top_ilu = _action_factor_counts(top_diagnostics)
            borrowed_direct = bottom_direct + top_direct
            borrowed_ilu = bottom_ilu + top_ilu
            modal_diagnostics = self.action_modal_schur_system.diagnostics
            return {
                "global_A_materialized": False,
                "direct_factor_count": borrowed_direct,
                "oracle_local_direct_factor_count": borrowed_direct,
                "borrowed_direct_factor_count": borrowed_direct,
                "borrowed_ilu_factor_count": borrowed_ilu,
                "borrowed_local_factor_count": borrowed_direct + borrowed_ilu,
                "pc_owned_local_factor_count": 0,
                "bottom_direct_factor_count": bottom_direct,
                "top_direct_factor_count": top_direct,
                "bottom_ilu_factor_count": bottom_ilu,
                "top_ilu_factor_count": top_ilu,
                "bottom_action_apply_count": int(
                    bottom_diagnostics.get("apply_count", 0)
                ),
                "top_action_apply_count": int(top_diagnostics.get("apply_count", 0)),
                "pc_apply_count": int(self._pc_apply_count),
                "pc_apply_seconds": float(self._pc_apply_seconds),
                "borrowed_side_actions": True,
                "modal_block_name": self.modal_block_name,
                "modal_block_condition": self._modal_block_condition,
                "modal_schur": modal_diagnostics,
                "action_modal_schur_released": bool(self._action_modal_schur_released),
                "destroyed": bool(self._destroyed),
            }
        return {
            "global_A_materialized": False,
            "oracle_local_direct_factor_count": self.direct_factor_count
            if not self._destroyed
            else 0,
            "bottom_factor_released": self._destroyed,
            "top_factor_released": self._destroyed,
            "modal_block_name": self.modal_block_name,
            "modal_block_condition": self._modal_block_condition,
            "modal_schur_condition": float(
                self.modal_schur_system.modal_schur_condition
            ),
            "pc_apply_count": int(self._pc_apply_count),
            "pc_apply_seconds": float(self._pc_apply_seconds),
        }

    def _check_layouts(self) -> None:
        expected_bottom = sum(self.layout.bottom_local_sizes)
        if self.bottom_system.A.getSize() != (expected_bottom, expected_bottom):
            raise ValueError("H3 bottom oracle matrix does not match layout.")
        expected_top = sum(self.layout.top_local_sizes)
        if self.top_system.A.getSize() != (expected_top, expected_top):
            raise ValueError("H3 top oracle matrix does not match layout.")
        if self.modal_schur.shape != (self.layout.modal_count, self.layout.modal_count):
            raise ValueError("H3 modal Schur does not match the Hybrid layout.")

    def _source_parts(self, source: PETSc.Vec) -> np.ndarray:
        local = np.asarray(source.getArray(readonly=True))
        self._bottom_rhs.getArray()[:] = local[self.layout.local_bottom_slice]
        self._top_rhs.getArray()[:] = local[self.layout.local_top_slice]
        if self.layout.comm.rank == self.layout.modal_owner:
            modal_local = np.asarray(
                local[self.layout.local_modal_slice], dtype=np.complex128
            ).copy()
        else:
            modal_local = None
        return np.asarray(
            self.layout.comm.bcast(modal_local, root=self.layout.modal_owner),
            dtype=np.complex128,
        )

    def _apply_modal_tractions(self, modal: np.ndarray) -> None:
        count = self.mode_count
        _set_owned_values(self._bottom_positive_source, modal[:count])
        _set_owned_values(
            self._bottom_negative_source,
            self._backward_factors * modal[count:],
        )
        _set_owned_values(
            self._top_positive_source,
            self._forward_factors * modal[:count],
        )
        _set_owned_values(self._top_negative_source, modal[count:])
        self.coupling.bottom.positive_traction.mult(
            self._bottom_positive_source, self._bottom_positive_target
        )
        self.coupling.bottom.negative_traction.mult(
            self._bottom_negative_source, self._bottom_negative_target
        )
        self._bottom_coupling.getArray()[:] = self._bottom_positive_target.getArray(
            readonly=True
        ) + self._bottom_negative_target.getArray(readonly=True)
        self.coupling.top.positive_traction.mult(
            self._top_positive_source, self._top_positive_target
        )
        self.coupling.top.negative_traction.mult(
            self._top_negative_source, self._top_negative_target
        )
        self._top_coupling.getArray()[:] = self._top_positive_target.getArray(
            readonly=True
        ) + self._top_negative_target.getArray(readonly=True)

    def apply(self, _pc: PETSc.PC | None, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("H3 block-LDU preconditioner has been destroyed")
        apply_started = time.perf_counter()
        modal = self._source_parts(source)
        if self._action_mode:
            self.bottom_action.apply(self._bottom_rhs, self._bottom_first)
            self.top_action.apply(self._top_rhs, self._top_first)
        else:
            self.bottom_factor.solve(self._bottom_rhs, self._bottom_first)
            self.top_factor.solve(self._top_rhs, self._top_first)
        self.coupling.bottom.projection.mult(
            self._bottom_first, self._bottom_projection
        )
        self.coupling.top.projection.mult(self._top_first, self._top_projection)
        self._modal_rhs[:] = modal
        count = self.mode_count
        self._modal_rhs[:count] -= _replicated_modal_values(self._bottom_projection)
        self._modal_rhs[count:] -= _replicated_modal_values(self._top_projection)
        if self._action_mode:
            self._modal_solution[:] = self.action_modal_schur_system.solve(
                self._modal_rhs
            )
        else:
            self._modal_solution[:] = np.linalg.solve(self.modal_schur, self._modal_rhs)
        self._apply_modal_tractions(self._modal_solution)
        if self._action_mode:
            self.bottom_action.apply(self._bottom_coupling, self._bottom_delta)
            self.top_action.apply(self._top_coupling, self._top_delta)
        else:
            self.bottom_factor.solve(self._bottom_coupling, self._bottom_delta)
            self.top_factor.solve(self._top_coupling, self._top_delta)
        self._bottom_first.axpy(PETSc.ScalarType(-1.0), self._bottom_delta)
        self._top_first.axpy(PETSc.ScalarType(-1.0), self._top_delta)
        target_local = target.getArray()
        target_local[self.layout.local_bottom_slice] = self._bottom_first.getArray(
            readonly=True
        )
        target_local[self.layout.local_top_slice] = self._top_first.getArray(
            readonly=True
        )
        if self.layout.comm.rank == self.layout.modal_owner:
            target_local[self.layout.local_modal_slice] = self._modal_solution
        self._pc_apply_seconds += time.perf_counter() - apply_started
        self._pc_apply_count += 1

    def release_deferred_action_modal_schur(self) -> None:
        if not self._action_mode:
            return
        if self._action_modal_schur_released:
            return
        if self.action_modal_schur_system is None:
            raise RuntimeError("Deferred action modal Schur is unavailable.")
        self.action_modal_schur_system.destroy()
        self.modal_schur = None
        self._action_modal_schur_released = True

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        if self._destroyed:
            return
        for vector in (
            self._top_negative_target,
            self._top_positive_target,
            self._bottom_negative_target,
            self._bottom_positive_target,
            self._top_negative_source,
            self._top_positive_source,
            self._bottom_negative_source,
            self._bottom_positive_source,
            self._top_projection,
            self._bottom_projection,
            self._top_coupling,
            self._bottom_coupling,
            self._top_delta,
            self._bottom_delta,
            self._top_first,
            self._bottom_first,
            self._top_rhs,
            self._bottom_rhs,
        ):
            vector.destroy()
        if self._action_mode:
            if not self.defer_action_modal_schur_release:
                self.release_deferred_action_modal_schur()
        else:
            self.modal_schur_system.destroy()
        self._destroyed = True


@dataclass
class HybridBlockLduSolveResult:
    solution: PETSc.Vec
    iterations: int
    converged_reason: int
    reported_relative_residual: float
    true_relative_residual: float
    block_relative_residuals: dict[str, float]
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if not self._destroyed:
            self.solution.destroy()
            self._destroyed = True


@dataclass
class HybridBlockActionSystem:
    """The H3 candidate global action and its explicit inventory contract."""

    A: PETSc.Mat
    b: PETSc.Vec
    layout: HybridAugmentedLayout
    context: Any
    inventory: dict[str, Any]
    matrix_stats: dict[str, Any]
    block_shapes: dict[str, tuple[int, int]]
    inserted_nnz_by_block: dict[str, Any]
    dense_interface_square_formed: bool = False
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.context.destroy()
        self.b.destroy()
        self._destroyed = True


@dataclass
class _HybridBlockLduOracleLocalSystem:
    """One explicit-condensed local oracle view used only by the H3 factor."""

    side: str
    local_mesh: Any
    A: PETSc.Mat
    b: PETSc.Vec
    global_size: int
    static_condensation: Any = None
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A.destroy()
        self.b.destroy()
        self._destroyed = True


@dataclass
class HybridBlockLduPhysicalSolution:
    """Small H3 carrier for active solutions, recovery and lifecycle fields."""

    bottom: PETSc.Vec
    top: PETSc.Vec
    modal_amplitudes: np.ndarray
    bottom_auxiliary: np.ndarray
    top_auxiliary: np.ndarray
    bottom_recovered: Any
    top_recovered: Any
    factor_solver: str
    converged_reason: int
    reported_relative_residual: float
    relative_residual: float
    block_relative_residuals: dict[str, float]
    iterations: int
    setup_seconds: float = 0.0
    solve_seconds: float = 0.0
    recovery_seconds: float = 0.0
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def bottom_physical(self):
        return self.bottom_recovered.electric_field

    @property
    def top_physical(self):
        return self.top_recovered.electric_field

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.bottom.destroy()
        self.top.destroy()
        self._destroyed = True


def create_exact_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: object,
    top_system: object,
    coupling: HybridInternalModeCoupling,
) -> HybridBlockLduPreconditioner:
    """Create the H3 exact right block-LDU oracle and retain two local factors."""

    modal_schur = build_hybrid_modal_schur_direct_system(
        bottom_system,
        top_system,
        coupling,
    )
    return HybridBlockLduPreconditioner(
        layout=layout,
        coupling=coupling,
        bottom_system=bottom_system,
        top_system=top_system,
        modal_schur_system=modal_schur,
    )


def create_g_only_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: object,
    top_system: object,
    coupling: HybridInternalModeCoupling,
) -> HybridBlockLduPreconditioner:
    """Create the bounded H4 diagnostic using the modal constraint block G."""

    modal_schur = build_hybrid_modal_schur_direct_system(
        bottom_system,
        top_system,
        coupling,
    )
    try:
        modal_constraint = np.asarray(modal_schur.modal_constraint, dtype=np.complex128)
        if not np.all(np.isfinite(modal_constraint)):
            raise RuntimeError("H4 G-only modal block is non-finite.")
        return HybridBlockLduPreconditioner(
            layout=layout,
            coupling=coupling,
            bottom_system=bottom_system,
            top_system=top_system,
            modal_schur_system=modal_schur,
            modal_block_override=modal_constraint,
            modal_block_name="g_only",
        )
    except Exception:
        modal_schur.destroy()
        raise


def create_action_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: object,
    top_system: object,
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
) -> HybridBlockLduPreconditioner:
    """Create an action-backed block-LDU context with one fixed modal LU."""

    modal_schur = build_hybrid_action_modal_schur(
        coupling,
        bottom_action,
        top_action,
    )
    try:
        return HybridBlockLduPreconditioner(
            layout=layout,
            coupling=coupling,
            bottom_system=bottom_system,
            top_system=top_system,
            modal_schur_system=None,
            modal_block_name="approximate_action_schur",
            bottom_action=bottom_action,
            top_action=top_action,
            action_modal_schur_system=modal_schur,
        )
    except Exception:
        modal_schur.destroy()
        raise


def modal_block_diagnostic(
    modal_schur_system: HybridModalSchurDirectSystem,
) -> dict[str, object]:
    """Summarize exact S_m, G, and their feedback without a new candidate."""

    exact = np.asarray(modal_schur_system.modal_schur, dtype=np.complex128)
    constraint = np.asarray(modal_schur_system.modal_constraint, dtype=np.complex128)
    if exact.shape != constraint.shape or exact.ndim != 2:
        raise ValueError("H4 modal blocks have incompatible shapes.")
    feedback = constraint - exact
    exact_norm = float(np.linalg.norm(exact, ord="fro"))
    constraint_norm = float(np.linalg.norm(constraint, ord="fro"))
    feedback_norm = float(np.linalg.norm(feedback, ord="fro"))
    tiny = np.finfo(float).tiny
    return {
        "shape": list(exact.shape),
        "exact_s_m_shape": list(exact.shape),
        "g_shape": list(constraint.shape),
        "exact_s_m_dtype": str(exact.dtype),
        "g_dtype": str(constraint.dtype),
        "exact_s_m_condition": float(np.linalg.cond(exact)),
        "g_condition": float(np.linalg.cond(constraint)),
        "feedback_frobenius_norm": feedback_norm,
        "feedback_relative_to_s_m": feedback_norm / max(exact_norm, tiny),
        "feedback_relative_to_g": feedback_norm / max(constraint_norm, tiny),
    }


def _residual_metrics(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
) -> tuple[float, dict[str, float]]:
    residual = rhs.duplicate()
    operator.mult(solution, residual)
    residual.scale(PETSc.ScalarType(-1.0))
    residual.axpy(PETSc.ScalarType(1.0), rhs)
    rhs_bottom, rhs_top, rhs_modal = context.layout.split(
        rhs,
        context.bottom_system.b,
        context.top_system.b,
    )
    residual_bottom, residual_top, residual_modal = context.layout.split(
        residual,
        context.bottom_system.b,
        context.top_system.b,
    )
    solution_bottom, solution_top, solution_modal = context.layout.split(
        solution,
        context.bottom_system.b,
        context.top_system.b,
    )
    bottom_action = context.bottom_system.A.createVecLeft()
    top_action = context.top_system.A.createVecLeft()
    modal_constraint = (
        context.action_modal_schur_system.modal_constraint
        if context._action_mode
        else context.modal_schur_system.modal_constraint
    )
    try:
        context.bottom_system.A.mult(solution_bottom, bottom_action)
        context.top_system.A.mult(solution_top, top_action)
        context._apply_modal_tractions(solution_modal)
        context.coupling.bottom.projection.mult(
            solution_bottom, context._bottom_projection
        )
        context.coupling.top.projection.mult(solution_top, context._top_projection)
        bottom_scale = max(
            float(rhs_bottom.norm()),
            float(bottom_action.norm()),
            float(context._bottom_coupling.norm()),
            1.0e-30,
        )
        top_scale = max(
            float(rhs_top.norm()),
            float(top_action.norm()),
            float(context._top_coupling.norm()),
            1.0e-30,
        )
        modal_scale = max(
            float(np.linalg.norm(rhs_modal)),
            float(np.linalg.norm(_replicated_modal_values(context._bottom_projection))),
            float(np.linalg.norm(_replicated_modal_values(context._top_projection))),
            float(np.linalg.norm(modal_constraint @ solution_modal)),
            1.0e-30,
        )
        block = {
            "bottom": float(residual_bottom.norm() / bottom_scale),
            "top": float(residual_top.norm() / top_scale),
            "modal": float(np.linalg.norm(residual_modal) / modal_scale),
        }
        global_relative = float(residual.norm() / max(float(rhs.norm()), _TINY))
    finally:
        top_action.destroy()
        bottom_action.destroy()
        solution_top.destroy()
        solution_bottom.destroy()
        residual_top.destroy()
        residual_bottom.destroy()
        rhs_top.destroy()
        rhs_bottom.destroy()
        residual.destroy()
    return global_relative, block


@dataclass
class HybridBlockLduScreenResult:
    """True-residual history from one bounded action-backed outer solve."""

    history: list[dict[str, Any]]
    converged_reason: int
    iterations: int
    final_true_relative_residual: float
    minimum_true_relative_residual: float
    last5: list[dict[str, Any]]
    last40: list[dict[str, Any]]
    inventory: dict[str, Any]
    pc_apply_seconds: float
    progressive_stop_cause: str | None = None


@dataclass
class HybridBlockLduFullSolveResult:
    """Retained V4 full-solve snapshot after KSP/PC release."""

    solution: PETSc.Vec
    history: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]
    converged_reason: int
    iterations: int
    final_reported_relative_residual: float
    final_true_relative_residual: float
    block_relative_residuals: dict[str, float]
    inventory: dict[str, Any]
    release: dict[str, Any]
    pc_apply_seconds: float
    postsolve_audit: dict[str, Any] = field(default_factory=dict)
    history_evaluation_count: int = 0
    postsolve_evaluation_count: int = 0
    _destroyed: bool = field(default=False, init=False, repr=False)

    def destroy(self) -> None:
        if not self._destroyed:
            self.solution.destroy()
            self._destroyed = True


def screen_action_block_ldu(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
    *,
    max_it: int,
    v3_progressive: bool = False,
    checkpoint_callback=None,
) -> HybridBlockLduScreenResult:
    """Run the fixed, bounded right-FGMRES screen and retain true residual rows."""

    if int(max_it) not in {20, 100, 200}:
        raise ValueError("V2 screen max_it must be one of 20, 100, or 200.")
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution.set(0.0)
    history: list[dict[str, Any]] = []
    notified_checkpoints: set[int] = set()
    rhs_norm = max(float(rhs.norm()), _TINY)
    solve_started = time.perf_counter()
    progressive_stop_cause: str | None = None

    def snapshot(iteration: int, reported: float, current: PETSc.KSP | None) -> None:
        if v3_progressive and history and history[-1]["iteration"] == int(iteration):
            return
        if current is None:
            solution.copy(monitor_solution)
            current_solution = monitor_solution
        else:
            current_solution = current.buildSolution(monitor_solution)
        global_true, block = _residual_metrics(operator, rhs, current_solution, context)
        inventory = context.inventory
        row = {
            "iteration": int(iteration),
            "reported_relative_residual": float(reported),
            "global_true_relative_residual": float(global_true),
            "bottom_true_relative_residual": float(block["bottom"]),
            "top_true_relative_residual": float(block["top"]),
            "modal_true_relative_residual": float(block["modal"]),
            "pc_apply_count": int(inventory.get("pc_apply_count", 0)),
            "bottom_action_apply_count": int(
                inventory.get("bottom_action_apply_count", 0)
            ),
            "top_action_apply_count": int(inventory.get("top_action_apply_count", 0)),
            "elapsed_seconds": float(time.perf_counter() - solve_started),
        }
        if history and history[-1]["iteration"] == int(iteration):
            history[-1] = row
        else:
            history.append(row)
        if (
            v3_progressive
            and checkpoint_callback is not None
            and int(iteration) in (20, 60, 100, 200)
            and int(iteration) not in notified_checkpoints
        ):
            notified_checkpoints.add(int(iteration))
            checkpoint_callback(dict(row))

    ksp = PETSc.KSP().create(operator.getComm())
    try:
        snapshot(0, 1.0 if rhs_norm > _TINY else 0.0, None)
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setGMRESRestart(90)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=int(max_it))
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(context)
        ksp.setUp()

        def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
            if not v3_progressive:
                snapshot(
                    int(iteration),
                    float(residual_norm) / rhs_norm,
                    current,
                )

        def convergence_test(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            nonlocal progressive_stop_cause
            if v3_progressive:
                snapshot(
                    int(iteration),
                    float(residual_norm) / rhs_norm,
                    current,
                )
                row = history[-1]
                if any(
                    not np.isfinite(float(row[key])) or float(row[key]) < 0.0
                    for key in _V3_RESIDUAL_KEYS
                ):
                    progressive_stop_cause = "v3_nonfinite"
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_NANORINF)
                true_residual = float(row["global_true_relative_residual"])
                if true_residual <= 1.0e-6:
                    return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
                live_gate = action_block_v3_progressive_gate(
                    history,
                    converged_reason=0,
                    final=False,
                )
                if live_gate["hard_stop"]:
                    progressive_stop_cause = live_gate["stop_cause"]
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_DTOL)
                if int(iteration) >= 200:
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
                if live_gate["failed_stage"] is not None:
                    progressive_stop_cause = live_gate["stop_cause"]
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_DTOL)
            if float(residual_norm) <= 1.0e-6 * rhs_norm:
                return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
            return int(PETSc.KSP.ConvergedReason.ITERATING)

        ksp.setMonitor(monitor)
        if v3_progressive:
            ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        reported = float(ksp.getResidualNorm()) / rhs_norm
        snapshot(iterations, reported, None)
        inventory = dict(context.inventory)
        final_true = float(history[-1]["global_true_relative_residual"])
        minimum_true = float(
            min(row["global_true_relative_residual"] for row in history)
        )
        return HybridBlockLduScreenResult(
            history=history,
            converged_reason=reason,
            iterations=iterations,
            final_true_relative_residual=final_true,
            minimum_true_relative_residual=minimum_true,
            last5=[dict(row) for row in history[-5:]],
            last40=[dict(row) for row in history[-40:]],
            inventory=inventory,
            pc_apply_seconds=float(inventory.get("pc_apply_seconds", 0.0)),
            progressive_stop_cause=progressive_stop_cause,
        )
    finally:
        ksp.destroy()
        monitor_solution.destroy()
        solution.destroy()
        context.destroy()


def solve_action_block_ldu_full(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
    *,
    max_it: int = 700,
    checkpoint_callback=None,
    v5_multimetric: bool = False,
    v6_traction_aligned: bool = False,
) -> HybridBlockLduFullSolveResult:
    """Run the V4 fixed double-action solve and retain only the solution.

    This deliberately remains separate from ``screen_action_block_ldu`` so the
    V2/V3 bounded-screen limits and progressive-stop behavior cannot change.
    The returned solution is an owned snapshot; the borrowed side actions are
    not destroyed here and remain available for recovery/audit by the caller.
    """

    if v6_traction_aligned and not v5_multimetric:
        raise ValueError("V6 multimetric solve requires the V5 frozen profile.")
    if v6_traction_aligned:
        if int(max_it) != 1000:
            raise ValueError("V6 traction-aligned solve requires max_it=1000.")
    elif int(max_it) != 700:
        raise ValueError("V4/V5 full solve requires max_it=700.")
    multimetric = bool(v5_multimetric)
    profile_threshold = 5.0e-9 if v6_traction_aligned else 1.0e-6
    profile_identity = (
        "traction_aligned_multimetric_true_residual_gate"
        if v6_traction_aligned
        else "multimetric_true_residual_gate"
    )
    context.defer_action_modal_schur_release = True
    checkpoints = {
        0,
        1,
        2,
        5,
        10,
        20,
        40,
        60,
        80,
        90,
        100,
        120,
        150,
        180,
        200,
        270,
        360,
        450,
        540,
        630,
        700,
    }
    if v5_multimetric:
        checkpoints.update({500, 520, 534, 540, 550, 560, 580, 600})
    if v6_traction_aligned:
        checkpoints.update(
            {
                0,
                1,
                2,
                5,
                10,
                20,
                60,
                100,
                200,
                500,
                534,
                557,
                600,
                630,
                700,
                750,
                800,
                850,
                900,
                950,
                1000,
            }
        )
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    retained_solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution.set(0.0)
    retained_solution.set(0.0)
    history: list[dict[str, Any]] = []
    history_cache: dict[int, dict[str, Any]] = {}
    decision_cache: dict[int, dict[str, Any]] = {}
    history_evaluation_count = 0
    notified_checkpoints: set[int] = set()
    rhs_norm = max(float(rhs.norm()), _TINY)
    solve_started = time.perf_counter()
    ksp = PETSc.KSP().create(operator.getComm())
    ksp_restart = 90
    returned = False

    def notify_checkpoint(row: dict[str, Any], *, force: bool = False) -> None:
        iteration = int(row["iteration"])
        if checkpoint_callback is None or iteration in notified_checkpoints:
            return
        if not force and iteration not in checkpoints:
            return
        notified_checkpoints.add(iteration)
        checkpoint_callback(dict(row))

    def snapshot(
        iteration: int,
        reported: float,
        current: PETSc.KSP | None,
    ) -> dict[str, Any]:
        nonlocal history_evaluation_count
        if multimetric and int(iteration) in history_cache:
            return history_cache[int(iteration)]
        if current is None:
            solution.copy(monitor_solution)
            current_solution = monitor_solution
        else:
            current_solution = current.buildSolution(monitor_solution)
        global_true, block = _residual_metrics(operator, rhs, current_solution, context)
        inventory = context.inventory
        row = {
            "iteration": int(iteration),
            "reported_relative_residual": float(reported),
            "global_true_relative_residual": float(global_true),
            "bottom_true_relative_residual": float(block["bottom"]),
            "top_true_relative_residual": float(block["top"]),
            "modal_true_relative_residual": float(block["modal"]),
            "pc_apply_count": int(inventory.get("pc_apply_count", 0)),
            "bottom_action_apply_count": int(
                inventory.get("bottom_action_apply_count", 0)
            ),
            "top_action_apply_count": int(inventory.get("top_action_apply_count", 0)),
            "elapsed_seconds": float(time.perf_counter() - solve_started),
        }
        if history and history[-1]["iteration"] == int(iteration):
            history[-1] = row
        else:
            history.append(row)
        if multimetric:
            history_cache[int(iteration)] = row
            history_evaluation_count += 1
        if not multimetric:
            notify_checkpoint(row)
        return row

    try:
        if multimetric:
            initial_row = snapshot(0, 1.0 if rhs_norm > _TINY else 0.0, None)
            initial_decision = multimetric_true_residual_decision(
                0,
                initial_row,
                max_it=max_it,
                threshold=profile_threshold,
                identity=profile_identity,
            )
            initial_row.update(
                {
                    "multimetric_max_true_residual": initial_decision[
                        "max_true_residual"
                    ],
                    "multimetric_decision": initial_decision["decision"],
                    "multimetric_reason": initial_decision["reason"],
                    "multimetric_identity": initial_decision["identity"],
                }
            )
            decision_cache[0] = initial_decision
            notify_checkpoint(initial_row)
        else:
            snapshot(0, 1.0 if rhs_norm > _TINY else 0.0, None)
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setGMRESRestart(ksp_restart)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setTolerances(
            rtol=profile_threshold if multimetric else 1.0e-6,
            atol=0.0,
            max_it=max_it,
        )
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(context)
        ksp.setUp()

        def monitor(current: PETSc.KSP, iteration: int, residual_norm: float) -> None:
            if not multimetric:
                snapshot(
                    int(iteration),
                    float(residual_norm) / rhs_norm,
                    current,
                )

        def convergence_test(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            row = snapshot(
                int(iteration),
                float(residual_norm) / rhs_norm,
                current,
            )
            if int(iteration) not in decision_cache:
                decision = multimetric_true_residual_decision(
                    int(iteration),
                    row,
                    max_it=max_it,
                    threshold=profile_threshold,
                    identity=profile_identity,
                )
                row.update(
                    {
                        "multimetric_max_true_residual": decision["max_true_residual"],
                        "multimetric_decision": decision["decision"],
                        "multimetric_reason": decision["reason"],
                        "multimetric_identity": decision["identity"],
                    }
                )
                decision_cache[int(iteration)] = decision
                notify_checkpoint(row)
            return int(decision_cache[int(iteration)]["reason"])

        if not multimetric:
            ksp.setMonitor(monitor)
        else:
            ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        reported = float(ksp.getResidualNorm()) / rhs_norm
        if multimetric and iterations not in decision_cache:
            final_row = snapshot(iterations, reported, None)
            final_decision = multimetric_true_residual_decision(
                iterations,
                final_row,
                max_it=max_it,
                threshold=profile_threshold,
                identity=profile_identity,
            )
            final_row.update(
                {
                    "multimetric_max_true_residual": final_decision[
                        "max_true_residual"
                    ],
                    "multimetric_decision": final_decision["decision"],
                    "multimetric_reason": final_decision["reason"],
                    "multimetric_identity": final_decision["identity"],
                }
            )
            decision_cache[iterations] = final_decision
            notify_checkpoint(final_row, force=True)
        else:
            snapshot(iterations, reported, None)
        notify_checkpoint(history[-1], force=True)
        solution.copy(retained_solution)
        release: dict[str, Any] = {
            "ksp_destroyed": False,
            "pc_context_destroyed": False,
            "action_modal_schur_retained_after_pc_destroyed": False,
            "action_modal_schur_released": False,
            "solution_snapshot_retained": True,
            "borrowed_side_actions_retained": False,
        }
        if multimetric:
            post_global, post_block = _residual_metrics(
                operator, rhs, retained_solution, context
            )
            postsolve_values = {
                "ksp_reported_relative_residual": reported,
                "global_true_relative_residual": float(post_global),
                "bottom_true_relative_residual": float(post_block["bottom"]),
                "top_true_relative_residual": float(post_block["top"]),
                "modal_true_relative_residual": float(post_block["modal"]),
            }
            postsolve_decision_values = {
                "reported_relative_residual": reported,
                **{
                    key: value
                    for key, value in postsolve_values.items()
                    if key != "ksp_reported_relative_residual"
                },
            }
            postsolve_decision = multimetric_true_residual_decision(
                iterations,
                postsolve_decision_values,
                max_it=max_it,
                threshold=profile_threshold,
                identity=profile_identity,
            )
            postsolve_pass = bool(reason > 0 and postsolve_decision["positive"])
            postsolve_audit = {
                **postsolve_values,
                "identity": profile_identity,
                "profile": "v6_traction_aligned"
                if v6_traction_aligned
                else "v5_multimetric",
                "threshold": profile_threshold,
                "restart": int(ksp_restart),
                "restart_source": (
                    "configured PETSc.KSP.setGMRESRestart(90); "
                    "qualified petsc4py exposes no getGMRESRestart()"
                ),
                "reported_residual_source": "ksp.getResidualNorm()",
                "explicit_recomputed_residuals": {
                    key: value
                    for key, value in postsolve_values.items()
                    if key != "ksp_reported_relative_residual"
                },
                "decision": postsolve_decision["decision"],
                "reason": reason,
                "all_finite_nonnegative": postsolve_decision["all_finite_nonnegative"],
                "max_true_residual": postsolve_decision["max_true_residual"],
                "pass": postsolve_pass,
                "custom_convergence_false_positive": bool(
                    reason > 0 and not postsolve_pass
                ),
            }
            final_true = float(post_global)
            block = {key: float(value) for key, value in post_block.items()}
        else:
            postsolve_audit = {}
            final_true = float(history[-1]["global_true_relative_residual"])
            block = {
                "bottom": float(history[-1]["bottom_true_relative_residual"]),
                "top": float(history[-1]["top_true_relative_residual"]),
                "modal": float(history[-1]["modal_true_relative_residual"]),
            }
        inventory = dict(context.inventory)
        ksp.destroy()
        ksp = None
        release["ksp_destroyed"] = True
        context.destroy()
        release["pc_context_destroyed"] = bool(context.inventory.get("destroyed"))
        modal_after_pc = dict(context.inventory.get("modal_schur", {}))
        release["action_modal_schur_retained_after_pc_destroyed"] = bool(
            modal_after_pc.get("destroyed") is False
        )
        borrowed_actions = [
            action
            for action in (context.bottom_action, context.top_action)
            if action is not None
        ]
        release["borrowed_side_actions_retained"] = bool(borrowed_actions) and all(
            not bool(_action_diagnostics(action).get("destroyed"))
            for action in borrowed_actions
        )
        result = HybridBlockLduFullSolveResult(
            solution=retained_solution,
            history=[dict(row) for row in history],
            checkpoints=[
                dict(row)
                for row in history
                if int(row["iteration"]) in checkpoints
                or int(row["iteration"]) == iterations
            ],
            converged_reason=reason,
            iterations=iterations,
            final_reported_relative_residual=float(reported),
            final_true_relative_residual=final_true,
            block_relative_residuals=block,
            inventory=inventory,
            release=release,
            pc_apply_seconds=float(inventory.get("pc_apply_seconds", 0.0)),
            postsolve_audit=postsolve_audit,
            history_evaluation_count=(history_evaluation_count if multimetric else 0),
            postsolve_evaluation_count=1 if multimetric else 0,
        )
        returned = True
        return result
    finally:
        if ksp is not None:
            ksp.destroy()
        if not context._destroyed:
            context.destroy()
        if not returned and context._action_mode:
            context.release_deferred_action_modal_schur()
        monitor_solution.destroy()
        solution.destroy()
        if not returned:
            retained_solution.destroy()


def action_block_screen_gate(
    history: list[dict[str, Any]],
    *,
    profile: str,
    max_it: int,
    converged_reason: int,
) -> dict[str, Any]:
    """Evaluate only the frozen bounded-screen numerical gate."""

    if profile not in {"bottom-approx", "top-approx", "double"}:
        raise ValueError("Unknown V2 action-screen profile.")
    if profile != "double" and int(max_it) != 20:
        raise ValueError("One-sided V2 screens require max_it=20.")
    if profile == "double" and int(max_it) not in {20, 100, 200}:
        raise ValueError("Double V2 screens require max_it=20, 100, or 200.")
    threshold = 0.35
    strict_threshold = True
    recent_window = 5
    if profile == "double" and int(max_it) == 100:
        threshold = 0.12
        strict_threshold = False
        recent_window = 40
    elif profile == "double" and int(max_it) == 200:
        threshold = 0.05
        strict_threshold = False
        recent_window = 40
    residual_keys = (
        "reported_relative_residual",
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    finite = bool(
        history
        and all(
            all(np.isfinite(float(row[key])) for key in residual_keys)
            for row in history
        )
    )
    final = float(history[-1]["global_true_relative_residual"]) if history else np.inf
    minimum = (
        float(min(row["global_true_relative_residual"] for row in history))
        if history
        else np.inf
    )
    window = history[-recent_window:] if history else []
    net_descent = bool(
        len(window) >= 2
        and float(window[-1]["global_true_relative_residual"])
        < float(window[0]["global_true_relative_residual"])
    )
    iterations = int(history[-1]["iteration"]) if history else int(max_it) + 1
    predicted_iterations: int | None = None
    predicted_wall_seconds: float | None = None
    recent_log_slope: float | None = None
    if profile == "double" and int(max_it) == 200 and len(window) >= 2:
        x = np.asarray([row["iteration"] for row in window], dtype=float)
        y = np.log(
            np.maximum(
                np.asarray(
                    [row["global_true_relative_residual"] for row in window],
                    dtype=float,
                ),
                _TINY,
            )
        )
        recent_log_slope = float(np.polyfit(x, y, 1)[0])
        prediction_target = 1.0e-6
        if final <= prediction_target:
            predicted_iterations = iterations
            predicted_wall_seconds = float(window[-1]["elapsed_seconds"])
        elif recent_log_slope < 0.0:
            predicted_iterations = int(
                iterations
                + np.ceil(np.log(prediction_target / final) / recent_log_slope)
            )
            elapsed = np.asarray(
                [row["elapsed_seconds"] for row in window], dtype=float
            )
            wall_slope = float(np.polyfit(x, elapsed, 1)[0])
            predicted_wall_seconds = float(
                elapsed[-1]
                + max(predicted_iterations - iterations, 0) * max(wall_slope, 0.0)
            )
        else:
            predicted_iterations = None
            predicted_wall_seconds = None
    predicted_ok = bool(
        profile != "double"
        or int(max_it) != 200
        or (
            predicted_iterations is not None
            and predicted_wall_seconds is not None
            and predicted_iterations <= 3000
        )
    )
    threshold_ok = bool(
        final < threshold and minimum < threshold
        if strict_threshold
        else final <= threshold and minimum <= threshold
    )
    boundary_or_earlier = bool(
        iterations == int(max_it)
        or (iterations < int(max_it) and int(converged_reason) > 0)
    )
    gate_pass = bool(
        finite and boundary_or_earlier and threshold_ok and net_descent and predicted_ok
    )
    return {
        "pass": gate_pass,
        "profile": profile,
        "max_it": int(max_it),
        "threshold": float(threshold),
        "finite": finite,
        "final": final,
        "minimum": minimum,
        "iterations": iterations,
        "converged_reason": int(converged_reason),
        "boundary_or_earlier": boundary_or_earlier,
        "net_descent": net_descent,
        "recent_window": int(recent_window),
        "prediction_target": 1.0e-6
        if profile == "double" and int(max_it) == 200
        else None,
        "predicted_iterations": predicted_iterations,
        "predicted_wall_seconds": predicted_wall_seconds,
        "recent_log_slope": recent_log_slope,
    }


_V3_CHECKPOINTS = (0, 1, 2, 5, 10, 20, 30, 40, 60, 80, 90, 100, 120, 150, 160, 180, 200)
_V3_RESIDUAL_KEYS = (
    "reported_relative_residual",
    "global_true_relative_residual",
    "bottom_true_relative_residual",
    "top_true_relative_residual",
    "modal_true_relative_residual",
)


def multimetric_true_residual_decision(
    iteration: int,
    residuals: dict[str, Any],
    *,
    max_it: int = 700,
    threshold: float = 1.0e-6,
    identity: str = "multimetric_true_residual_gate",
) -> dict[str, Any]:
    """Apply the frozen five-residual convergence decision."""

    profile = (int(max_it), float(threshold), identity)
    if profile not in {
        (700, 1.0e-6, "multimetric_true_residual_gate"),
        (1000, 5.0e-9, "traction_aligned_multimetric_true_residual_gate"),
    }:
        raise ValueError("Unsupported frozen multimetric convergence profile.")
    values: dict[str, float] = {}
    try:
        values = {key: float(residuals[key]) for key in _V3_RESIDUAL_KEYS}
    except (KeyError, TypeError, ValueError):
        values = {key: float("nan") for key in _V3_RESIDUAL_KEYS}
    finite_nonnegative = bool(
        all(np.isfinite(value) and value >= 0.0 for value in values.values())
    )
    max_true = float(max(values.values(), default=float("nan")))
    positive = bool(
        int(iteration) > 0
        and finite_nonnegative
        and all(value <= float(threshold) for value in values.values())
    )
    if not finite_nonnegative:
        reason = int(PETSc.KSP.ConvergedReason.DIVERGED_NANORINF)
        decision = "DIVERGED_NANORINF"
    elif positive:
        user_reason = getattr(PETSc.KSP.ConvergedReason, "CONVERGED_USER", None)
        reason = int(
            PETSc.KSP.ConvergedReason.CONVERGED_RTOL
            if user_reason is None
            else user_reason
        )
        decision = "CONVERGED_USER" if user_reason is not None else "CONVERGED_RTOL"
    elif int(iteration) >= int(max_it):
        reason = int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
        decision = "DIVERGED_MAX_IT"
    else:
        reason = int(PETSc.KSP.ConvergedReason.ITERATING)
        decision = "ITERATING"
    return {
        "identity": identity,
        "iteration": int(iteration),
        "threshold": float(threshold),
        "residuals": values,
        "max_true_residual": max_true,
        "all_finite_nonnegative": finite_nonnegative,
        "positive": positive,
        "decision": decision,
        "reason": reason,
    }


def _v3_history_by_iteration(
    history: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in history:
        iteration = int(row["iteration"])
        rows[iteration] = row
    return rows


def _v3_endpoint_slope(
    rows: dict[int, dict[str, Any]], start: int, end: int
) -> float | None:
    if start not in rows or end not in rows:
        return None
    first = float(rows[start]["global_true_relative_residual"])
    last = float(rows[end]["global_true_relative_residual"])
    if first <= 0.0 or last <= 0.0 or end <= start:
        return None
    return float(np.exp((np.log(last) - np.log(first)) / float(end - start)))


def _v3_window_net_decrease(
    rows: dict[int, dict[str, Any]], start: int, end: int
) -> bool:
    window = [
        rows[iteration]["global_true_relative_residual"]
        for iteration in sorted(rows)
        if start <= iteration <= end
    ]
    return bool(len(window) >= 2 and float(window[-1]) < float(window[0]))


def action_block_v3_progressive_gate(
    history: list[dict[str, Any]],
    *,
    converged_reason: int,
    final: bool = True,
) -> dict[str, Any]:
    """Evaluate the fixed V3 double-screen checkpoints in one history.

    This is deliberately separate from the historical V2 gate: V3 owns a
    fixed max_it=200 and progressively admits the same single outer solve at
    20, 60, 100, and 200 iterations.
    """

    rows = _v3_history_by_iteration(history)
    ordered_iterations = sorted(rows)
    finite = bool(
        history
        and all(
            np.isfinite(float(row[key])) and float(row[key]) >= 0.0
            for row in history
            for key in _V3_RESIDUAL_KEYS
        )
    )
    reported_true_agree = bool(
        finite
        and all(
            abs(
                float(row["reported_relative_residual"])
                - float(row["global_true_relative_residual"])
            )
            <= 1.0e-6
            * max(
                float(row["reported_relative_residual"]),
                float(row["global_true_relative_residual"]),
            )
            for row in history
        )
    )
    iterations = ordered_iterations[-1] if ordered_iterations else 0
    boundary_or_earlier = bool(
        not final
        or iterations == 200
        or (iterations < 200 and int(converged_reason) > 0)
    )
    hard_stop = bool(not finite or (final and not boundary_or_earlier))
    if len(ordered_iterations) >= 6:
        for start in range(len(ordered_iterations) - 5):
            sample = ordered_iterations[start : start + 6]
            values = [
                float(rows[iteration]["global_true_relative_residual"])
                for iteration in sample
            ]
            if all(values[index + 1] > values[index] for index in range(5)):
                later = [
                    float(rows[iteration]["global_true_relative_residual"])
                    for iteration in ordered_iterations[start + 6 :]
                ]
                if not later or min(later) >= values[-1]:
                    hard_stop = True
                    break
    for start in range(max(0, len(ordered_iterations) - 4)):
        sample = ordered_iterations[start : start + 5]
        if len(sample) == 5 and all(
            float(rows[sample[index]]["global_true_relative_residual"]) > 1.25
            for index in range(5)
        ):
            hard_stop = True
            break

    stage = next(
        (candidate for candidate in (200, 100, 60, 20) if candidate in rows),
        None,
    )
    required = (
        tuple(iteration for iteration in _V3_CHECKPOINTS if iteration <= stage)
        if stage is not None
        else ()
    )
    checkpoints_complete = bool(stage is not None and all(i in rows for i in required))
    r20 = float(rows[20]["global_true_relative_residual"]) if 20 in rows else None
    r10 = float(rows[10]["global_true_relative_residual"]) if 10 in rows else None
    r40 = float(rows[40]["global_true_relative_residual"]) if 40 in rows else None
    r60 = float(rows[60]["global_true_relative_residual"]) if 60 in rows else None
    r90 = float(rows[90]["global_true_relative_residual"]) if 90 in rows else None
    r100 = float(rows[100]["global_true_relative_residual"]) if 100 in rows else None
    r160 = float(rows[160]["global_true_relative_residual"]) if 160 in rows else None
    r200 = float(rows[200]["global_true_relative_residual"]) if 200 in rows else None
    q10_20 = _v3_endpoint_slope(rows, 10, 20)
    q40_60 = _v3_endpoint_slope(rows, 40, 60)
    q160_200 = _v3_endpoint_slope(rows, 160, 200)
    last20_net_decrease = _v3_window_net_decrease(rows, 41, 60)
    last40_net_decrease = _v3_window_net_decrease(rows, 161, 200)
    gates = {
        "20": bool(
            checkpoints_complete
            and 20 <= int(stage)
            and r20 is not None
            and r10 is not None
            and r20 < 0.65
            and r20 / max(r10, _TINY) < 0.85
            and q10_20 is not None
            and q10_20 < 0.98
            and all(np.isfinite(float(rows[20][key])) for key in _V3_RESIDUAL_KEYS[1:])
        ),
        "60": bool(
            checkpoints_complete
            and 60 <= int(stage)
            and r60 is not None
            and r40 is not None
            and r60 < 0.30
            and r60 < r40
            and q40_60 is not None
            and q40_60 < 0.99
            and last20_net_decrease
        ),
        "100": bool(
            checkpoints_complete
            and 100 <= int(stage)
            and r100 is not None
            and r60 is not None
            and r90 is not None
            and r100 <= 0.12
            and r100 < r60
            and r100 <= r90
            and _v3_window_net_decrease(rows, 61, 100)
        ),
        "200": False,
    }
    predicted_iterations: int | None = None
    predicted_wall_seconds: float | None = None
    prediction_slope: float | None = None
    prediction_intercept: float | None = None
    prediction_q_fit: float | None = None
    prediction_rows = [
        row for iteration, row in sorted(rows.items()) if 120 <= iteration <= 200
    ]
    if len(prediction_rows) >= 2:
        x = np.asarray([row["iteration"] for row in prediction_rows], dtype=float)
        y = np.log(
            np.maximum(
                np.asarray(
                    [row["global_true_relative_residual"] for row in prediction_rows],
                    dtype=float,
                ),
                _TINY,
            )
        )
        prediction_slope, prediction_intercept = (
            float(value) for value in np.polyfit(x, y, 1)
        )
        prediction_q_fit = float(np.exp(prediction_slope))
        if prediction_slope < 0.0 and r200 is not None:
            predicted_iterations = max(
                200,
                int(
                    np.ceil((np.log(1.0e-6) - prediction_intercept) / prediction_slope)
                ),
            )
            elapsed = np.asarray(
                [row.get("elapsed_seconds", 0.0) for row in prediction_rows],
                dtype=float,
            )
            wall_slope = float(np.polyfit(x, elapsed, 1)[0])
            predicted_wall_seconds = float(
                elapsed[-1] + max(predicted_iterations - 200, 0) * max(wall_slope, 0.0)
            )
    gates["200"] = bool(
        checkpoints_complete
        and stage == 200
        and r200 is not None
        and r160 is not None
        and r200 <= 0.05
        and r200 < r160
        and last40_net_decrease
        and q160_200 is not None
        and q160_200 < 0.997
        and len(prediction_rows) == 81
        and [int(row["iteration"]) for row in prediction_rows] == list(range(120, 201))
        and reported_true_agree
        and predicted_iterations is not None
        and predicted_iterations <= 3000
    )
    failed_stage = next(
        (
            name
            for name in ("20", "60", "100", "200")
            if stage is not None and int(name) <= stage and not gates[name]
        ),
        None,
    )
    final_true = (
        float(rows[iterations]["global_true_relative_residual"])
        if iterations in rows
        else np.inf
    )
    bounded_convergence = bool(
        final
        and iterations < 200
        and int(converged_reason) > 0
        and np.isfinite(final_true)
        and final_true <= 1.0e-6
    )
    not_reached_due_to_convergence = (
        [candidate for candidate in _V3_CHECKPOINTS if candidate > iterations]
        if bounded_convergence
        else []
    )
    stop_required = bool(hard_stop or failed_stage is not None)
    return {
        "pass": bool(all(gates.values()) and not hard_stop),
        "finite": finite,
        "reported_true_agree": reported_true_agree,
        "boundary_or_earlier": boundary_or_earlier,
        "hard_stop": hard_stop,
        "stop_required": stop_required,
        "failed_stage": failed_stage,
        "stop_cause": (
            "v3_hard_stop"
            if hard_stop
            else f"v3_{failed_stage}_admission_failed"
            if failed_stage is not None
            else None
        ),
        "bounded_convergence": bounded_convergence,
        "not_reached_due_to_convergence": not_reached_due_to_convergence,
        "stage": stage,
        "required_checkpoints": list(required),
        "checkpoints_complete": checkpoints_complete,
        "gates": gates,
        "r20": r20,
        "r60": r60,
        "r100": r100,
        "r200": r200,
        "q10_20": q10_20,
        "q40_60": q40_60,
        "q160_200": q160_200,
        "last20_net_decrease": last20_net_decrease,
        "last40_net_decrease": last40_net_decrease,
        "prediction_interval": [120, 200],
        "prediction_sample_count": len(prediction_rows),
        "prediction_slope": prediction_slope,
        "prediction_intercept": prediction_intercept,
        "prediction_q_fit": prediction_q_fit,
        "predicted_iterations": predicted_iterations,
        "predicted_wall_seconds": predicted_wall_seconds,
    }


def solve_exact_block_ldu(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
) -> HybridBlockLduSolveResult:
    """Solve one RHS with fixed right FGMRES and the exact block-LDU PC."""

    ksp = PETSc.KSP().create(operator.getComm())
    ksp.setOperators(operator)
    ksp.setType(PETSc.KSP.Type.FGMRES)
    ksp.setGMRESRestart(90)
    ksp.setPCSide(PETSc.PC.Side.RIGHT)
    ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
    ksp.setTolerances(rtol=1.0e-6, atol=0.0, max_it=3)
    pc = ksp.getPC()
    pc.setType(PETSc.PC.Type.PYTHON)
    pc.setPythonContext(context)
    ksp.setUp()
    solution = rhs.duplicate()
    solution.set(0.0)
    try:
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        reported = float(ksp.getResidualNorm()) / max(float(rhs.norm()), _TINY)
        true_residual, block_residuals = _residual_metrics(
            operator, rhs, solution, context
        )
    except Exception:
        solution.destroy()
        raise
    finally:
        ksp.destroy()
        context.destroy()
    return HybridBlockLduSolveResult(
        solution=solution,
        iterations=iterations,
        converged_reason=reason,
        reported_relative_residual=reported,
        true_relative_residual=true_residual,
        block_relative_residuals=block_residuals,
    )
