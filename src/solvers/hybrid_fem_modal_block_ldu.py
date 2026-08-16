"""Action-only Hybrid block-LDU preconditioner and tight iterative solve."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from .hybrid_fem_modal_schur_direct import modal_coupling_action

__all__ = (
    "HybridActionModalSchurSystem",
    "HybridBlockLduPreconditioner",
    "HybridBlockLduIterativeConfig",
    "HybridBlockLduIterativeResult",
    "build_hybrid_action_modal_schur",
    "create_action_block_ldu_preconditioner",
    "create_research_exact_side_lu_block_ldu_preconditioner",
    "multimetric_true_residual_decision",
    "solve_hybrid_block_ldu_iterative",
)

_TINY = np.finfo(float).tiny
_RESIDUAL_KEYS = (
    "reported_relative_residual",
    "global_true_relative_residual",
    "bottom_true_relative_residual",
    "top_true_relative_residual",
    "modal_true_relative_residual",
)


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


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


def _action_diagnostics(action: Any) -> dict[str, Any]:
    diagnostics = getattr(action, "diagnostics", None)
    if callable(diagnostics):
        diagnostics = diagnostics()
    if not isinstance(diagnostics, dict):
        raise TypeError("Borrowed action must expose diagnostics.")
    return dict(diagnostics)


def _action_operator(action: Any) -> PETSc.Mat:
    operator = getattr(action, "operator", None)
    if operator is None:
        operator = getattr(action, "A", None)
    if operator is None:
        raise TypeError("Borrowed action must expose operator or A.")
    return operator


def _direct_factor_count(diagnostics: dict[str, Any]) -> int:
    return int(
        diagnostics.get(
            "direct_factor_count",
            diagnostics.get("local_direct_factor_count", 0),
        )
    )


@dataclass
class HybridActionModalSchurSystem:
    """Small modal Schur system assembled from two borrowed actions."""

    modal_schur: np.ndarray
    modal_constraint: np.ndarray
    lu: np.ndarray
    pivots: np.ndarray
    rank: int
    condition: float
    matrix_repeat_error: float
    lu_repeat_solve_error: float
    build_apply_count: dict[str, int]
    repeat_diagnostics: dict[str, Any] = field(default_factory=dict)
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
            "repeat_diagnostics": dict(self.repeat_diagnostics),
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
    contribution = np.empty((2 * modal_count, 2 * modal_count), dtype=np.complex128)
    row_slice = (
        slice(0, modal_count)
        if side == "bottom"
        else slice(modal_count, 2 * modal_count)
    )
    other_slice = (
        slice(modal_count, 2 * modal_count)
        if side == "bottom"
        else slice(0, modal_count)
    )
    for column in range(2 * modal_count):
        modal = np.zeros(2 * modal_count, dtype=np.complex128)
        modal[column] = 1.0
        traction = modal_coupling_action(side, coupling, modal)
        response = operator.createVecLeft()
        projected = projection.createVecLeft()
        try:
            action.apply(traction, response)
            projection.mult(response, projected)
            contribution[row_slice, column] = _replicated_modal_values(projected)
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
    *,
    matrix_repeat_tolerance: float = 1.0e-13,
) -> HybridActionModalSchurSystem:
    """Build two complete action modal Schur matrices and one LU."""

    if (
        not np.isfinite(float(matrix_repeat_tolerance))
        or float(matrix_repeat_tolerance) <= 0.0
    ):
        raise ValueError("Modal-Schur repeat tolerance must be finite and positive.")
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
    build_apply_count = {side: after[side] - before[side] for side in ("bottom", "top")}
    expected = 2 * internal_count
    if any(value != expected for value in build_apply_count.values()):
        raise RuntimeError("Action modal Schur build count is not exactly two builds.")
    expected_shape = (internal_count, internal_count)
    for matrix in (constraint, first, second):
        if matrix.shape != expected_shape or matrix.dtype != np.dtype(np.complex128):
            raise ValueError("Action modal Schur has an unexpected shape or dtype.")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Action modal Schur contains non-finite values.")
    matrix_difference = first - second
    matrix_reference_norm = float(np.linalg.norm(first))
    matrix_difference_norm = float(np.linalg.norm(matrix_difference))
    matrix_repeat_error = matrix_difference_norm / max(matrix_reference_norm, _TINY)
    matrix_repeat_diagnostics = {
        "relative_error": float(matrix_repeat_error),
        "limit": float(matrix_repeat_tolerance),
        "reference_norm": matrix_reference_norm,
        "difference_norm": matrix_difference_norm,
        "max_abs": float(np.max(np.abs(matrix_difference))),
        "pass": bool(
            np.isfinite(matrix_repeat_error)
            and matrix_repeat_error <= float(matrix_repeat_tolerance)
        ),
    }
    if not matrix_repeat_diagnostics["pass"]:
        raise ValueError(
            "Action modal Schur matrix repeat error exceeds tolerance: "
            f"actual={matrix_repeat_error:.6e}, "
            f"limit={float(matrix_repeat_tolerance):.6e}, "
            f"reference_norm={matrix_reference_norm:.6e}, "
            f"difference_norm={matrix_difference_norm:.6e}, "
            f"max_abs={matrix_repeat_diagnostics['max_abs']:.6e}."
        )
    singular_values = np.linalg.svd(first, compute_uv=False)
    rank_scale = (
        np.finfo(float).eps * max(first.shape) * float(singular_values[0])
        if singular_values.size
        else 0.0
    )
    rank = int(np.count_nonzero(singular_values > rank_scale))
    condition = float(np.linalg.cond(first))
    if rank != internal_count or not np.isfinite(condition) or condition > 1.0e12:
        raise ValueError("Action modal Schur is not a finite full-rank system.")
    lu, pivots = lu_factor(first, check_finite=True)
    if not np.all(np.isfinite(lu)) or not np.all(np.isfinite(pivots)):
        raise ValueError("Action modal Schur LU contains non-finite values.")
    test_rhs = np.arange(1, internal_count + 1, dtype=np.complex128)
    first_solution = lu_solve((lu, pivots), test_rhs, check_finite=True)
    second_solution = lu_solve((lu, pivots), test_rhs, check_finite=True)
    lu_difference = first_solution - second_solution
    lu_reference_norm = float(np.linalg.norm(first_solution))
    lu_difference_norm = float(np.linalg.norm(lu_difference))
    lu_repeat_solve_error = lu_difference_norm / max(lu_reference_norm, _TINY)
    lu_repeat_diagnostics = {
        "relative_error": float(lu_repeat_solve_error),
        "limit": 1.0e-13,
        "reference_norm": lu_reference_norm,
        "difference_norm": lu_difference_norm,
        "max_abs": float(np.max(np.abs(lu_difference))),
        "pass": bool(
            np.isfinite(lu_repeat_solve_error) and lu_repeat_solve_error <= 1.0e-13
        ),
    }
    if not lu_repeat_diagnostics["pass"]:
        raise ValueError(
            "Action modal Schur LU repeat error exceeds tolerance: "
            f"actual={lu_repeat_solve_error:.6e}, "
            "limit=1.000000e-13, "
            f"reference_norm={lu_reference_norm:.6e}, "
            f"difference_norm={lu_difference_norm:.6e}, "
            f"max_abs={lu_repeat_diagnostics['max_abs']:.6e}."
        )
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
        repeat_diagnostics={
            "matrix": matrix_repeat_diagnostics,
            "lu_solve": lu_repeat_diagnostics,
        },
    )


class HybridBlockLduPreconditioner:
    """Right block-LDU action with borrowed side actions and no owned factors."""

    def __init__(
        self,
        layout: HybridAugmentedLayout,
        bottom_system: Any,
        top_system: Any,
        coupling: HybridInternalModeCoupling,
        bottom_action: Any,
        top_action: Any,
        action_modal_schur_system: HybridActionModalSchurSystem,
        research_inventory: dict[str, Any] | None = None,
    ) -> None:
        self.layout = layout
        self.bottom_system = bottom_system
        self.top_system = top_system
        self.coupling = coupling
        self.bottom_action = bottom_action
        self.top_action = top_action
        self.action_modal_schur_system = action_modal_schur_system
        self._research_inventory = (
            None if research_inventory is None else dict(research_inventory)
        )
        self.modal_schur = action_modal_schur_system.modal_schur
        self.defer_action_modal_schur_release = False
        self._action_modal_schur_released = False
        self._destroyed = False
        self.mode_count = int(coupling.mode_count_per_direction)
        self._bottom_rhs = bottom_system.A.createVecRight()
        self._top_rhs = top_system.A.createVecRight()
        self._bottom_first = bottom_system.A.createVecLeft()
        self._top_first = top_system.A.createVecLeft()
        self._bottom_delta = bottom_system.A.createVecLeft()
        self._top_delta = top_system.A.createVecLeft()
        self._bottom_projection = coupling.bottom.projection.createVecLeft()
        self._top_projection = coupling.top.projection.createVecLeft()
        self._bottom_coupling = bottom_system.A.createVecLeft()
        self._top_coupling = top_system.A.createVecLeft()
        self._bottom_positive_source = (
            coupling.bottom.positive_traction.createVecRight()
        )
        self._bottom_negative_source = (
            coupling.bottom.negative_traction.createVecRight()
        )
        self._top_positive_source = coupling.top.positive_traction.createVecRight()
        self._top_negative_source = coupling.top.negative_traction.createVecRight()
        self._bottom_positive_target = coupling.bottom.positive_traction.createVecLeft()
        self._bottom_negative_target = coupling.bottom.negative_traction.createVecLeft()
        self._top_positive_target = coupling.top.positive_traction.createVecLeft()
        self._top_negative_target = coupling.top.negative_traction.createVecLeft()
        self._modal_rhs = np.empty(2 * self.mode_count, dtype=np.complex128)
        self._modal_solution = np.empty_like(self._modal_rhs)
        self._pc_apply_count = 0
        self._pc_apply_seconds = 0.0
        self._check_layouts()

    @property
    def direct_factor_count(self) -> int:
        return _direct_factor_count(
            _action_diagnostics(self.bottom_action)
        ) + _direct_factor_count(_action_diagnostics(self.top_action))

    @property
    def factors_released(self) -> bool:
        return False

    @property
    def inventory(self) -> dict[str, Any]:
        bottom = _action_diagnostics(self.bottom_action)
        top = _action_diagnostics(self.top_action)
        bottom_direct = _direct_factor_count(bottom)
        top_direct = _direct_factor_count(top)
        bottom_ilu = int(
            bottom.get(
                "base_factor_count",
                bottom.get("ilu_factor_count", bottom.get("factor_count", 0)),
            )
        )
        top_ilu = int(
            top.get(
                "base_factor_count",
                top.get("ilu_factor_count", top.get("factor_count", 0)),
            )
        )
        result = {
            "global_A_materialized": False,
            "direct_factor_count": bottom_direct + top_direct,
            "borrowed_direct_factor_count": bottom_direct + top_direct,
            "borrowed_ilu_factor_count": bottom_ilu + top_ilu,
            "pc_owned_local_factor_count": 0,
            "bottom_direct_factor_count": bottom_direct,
            "top_direct_factor_count": top_direct,
            "bottom_ilu_factor_count": bottom_ilu,
            "top_ilu_factor_count": top_ilu,
            "bottom_action_apply_count": int(bottom.get("apply_count", 0)),
            "top_action_apply_count": int(top.get("apply_count", 0)),
            "pc_apply_count": int(self._pc_apply_count),
            "pc_apply_seconds": float(self._pc_apply_seconds),
            "borrowed_side_actions": True,
            "modal_block_name": "approximate_action_schur",
            "modal_block_condition": float(self.action_modal_schur_system.condition),
            "modal_schur": self.action_modal_schur_system.diagnostics,
            "action_modal_schur_released": bool(self._action_modal_schur_released),
            "destroyed": bool(self._destroyed),
        }
        if self._research_inventory is not None:
            result.update(self._research_inventory)
        return result

    def _check_layouts(self) -> None:
        expected_bottom = self.layout.bottom_local_sizes[self.layout.comm.rank]
        expected_top = self.layout.top_local_sizes[self.layout.comm.rank]
        if self._bottom_rhs.getLocalSize() != expected_bottom:
            raise ValueError("Bottom action ownership does not match layout.")
        if self._top_rhs.getLocalSize() != expected_top:
            raise ValueError("Top action ownership does not match layout.")
        if self.modal_schur.shape != (self.layout.modal_count, self.layout.modal_count):
            raise ValueError("Action modal Schur does not match layout.")

    def _source_parts(self, source: PETSc.Vec) -> np.ndarray:
        local = np.asarray(source.getArray(readonly=True))
        self._bottom_rhs.getArray()[:] = local[self.layout.local_bottom_slice]
        self._top_rhs.getArray()[:] = local[self.layout.local_top_slice]
        modal = (
            np.asarray(local[self.layout.local_modal_slice], dtype=np.complex128).copy()
            if self.layout.comm.rank == self.layout.modal_owner
            else None
        )
        return np.asarray(
            self.layout.comm.bcast(modal, root=self.layout.modal_owner),
            dtype=np.complex128,
        )

    def _apply_modal_tractions(self, modal: np.ndarray) -> None:
        count = self.mode_count
        _set_owned_values(self._bottom_positive_source, modal[:count])
        _set_owned_values(
            self._bottom_negative_source,
            np.asarray(self.coupling.propagation.backward.factors) * modal[count:],
        )
        _set_owned_values(
            self._top_positive_source,
            np.asarray(self.coupling.propagation.forward.factors) * modal[:count],
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
            raise RuntimeError("Block-LDU preconditioner has been destroyed")
        started = time.perf_counter()
        modal = self._source_parts(source)
        self.bottom_action.apply(self._bottom_rhs, self._bottom_first)
        self.top_action.apply(self._top_rhs, self._top_first)
        self.coupling.bottom.projection.mult(
            self._bottom_first, self._bottom_projection
        )
        self.coupling.top.projection.mult(self._top_first, self._top_projection)
        self._modal_rhs[:] = modal
        self._modal_rhs[: self.mode_count] -= _replicated_modal_values(
            self._bottom_projection
        )
        self._modal_rhs[self.mode_count :] -= _replicated_modal_values(
            self._top_projection
        )
        self._modal_solution[:] = self.action_modal_schur_system.solve(self._modal_rhs)
        self._apply_modal_tractions(self._modal_solution)
        self.bottom_action.apply(self._bottom_coupling, self._bottom_delta)
        self.top_action.apply(self._top_coupling, self._top_delta)
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
        self._pc_apply_count += 1
        self._pc_apply_seconds += time.perf_counter() - started

    def release_deferred_action_modal_schur(self) -> None:
        if self._action_modal_schur_released:
            return
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
        if not self.defer_action_modal_schur_release:
            self.release_deferred_action_modal_schur()
        self._destroyed = True


def create_action_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: Any,
    top_system: Any,
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
) -> HybridBlockLduPreconditioner:
    """Create a fixed action-backed block-LDU context."""

    if (
        _direct_factor_count(_action_diagnostics(bottom_action)) != 0
        or _direct_factor_count(_action_diagnostics(top_action)) != 0
    ):
        raise ValueError("Action block-LDU requires zero borrowed direct factors.")
    modal_schur = build_hybrid_action_modal_schur(coupling, bottom_action, top_action)
    try:
        return HybridBlockLduPreconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            bottom_action,
            top_action,
            modal_schur,
        )
    except Exception:
        modal_schur.destroy()
        raise


def create_research_exact_side_lu_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: Any,
    top_system: Any,
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
    *,
    matrix_repeat_tolerance: float = 1.0e-13,
    qualification_scope: str | None = None,
    explicit_opt_in: bool = False,
) -> HybridBlockLduPreconditioner:
    """Build historical research LDU or an explicit case-qualified context.

    The default remains research-only; a fixed qualification scope and
    explicit opt-in are required for the case-qualified context.
    """

    actions = {"bottom": bottom_action, "top": top_action}
    for side, action in actions.items():
        diagnostics = _action_diagnostics(action)
        if diagnostics.get("research_only") is not True and not (
            explicit_opt_in and diagnostics.get("case_qualification_opt_in") is True
        ):
            raise ValueError(f"Research exact-side {side} action is not opted in")
        if _direct_factor_count(diagnostics) != 1:
            raise ValueError(
                f"Research exact-side {side} action needs one direct factor"
            )
        if diagnostics.get("global_hybrid_direct_factor_count") != 0:
            raise ValueError("Research exact-side action cannot own a global factor")
        if explicit_opt_in and (
            diagnostics.get("qualification_scope") != qualification_scope
            or diagnostics.get("explicit_opt_in") is not True
            or diagnostics.get("case_qualification_opt_in") is not True
            or diagnostics.get("general_production") is not False
            or diagnostics.get("ordinary_default") is not False
            or diagnostics.get("ordinary_default_changed") is not False
            or diagnostics.get("nested_iterative_ksp_count") != 0
            or diagnostics.get("local_direct_preonly_ksp_count") != 1
        ):
            raise ValueError("Case-qualified exact-side action diagnostics are invalid")
    modal_schur = build_hybrid_action_modal_schur(
        coupling,
        bottom_action,
        top_action,
        matrix_repeat_tolerance=matrix_repeat_tolerance,
    )
    research_inventory = {
        "global_hybrid_direct_factor_count": 0,
    }
    if not explicit_opt_in:
        research_inventory["research_only_exact_side_lu"] = True
    if explicit_opt_in:
        research_inventory.update(
            {
                "qualification_scope": qualification_scope,
                "explicit_opt_in": True,
                "case_qualification_opt_in": True,
                "ordinary_default": False,
                "ordinary_default_changed": False,
                "general_production": False,
                "nested_iterative_ksp_count": 0,
                "local_direct_preonly_ksp_count": 2,
            }
        )
    try:
        return HybridBlockLduPreconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            bottom_action,
            top_action,
            modal_schur,
            research_inventory=research_inventory,
        )
    except Exception:
        modal_schur.destroy()
        raise


@dataclass(frozen=True)
class HybridBlockLduIterativeConfig:
    """Frozen right-FGMRES settings for the iterative Hybrid solve."""

    restart: int = 90
    max_it: int = 1000
    threshold: float = 5.0e-9
    initial_guess: str = "zero"

    def __post_init__(self) -> None:
        if int(self.restart) <= 0 or int(self.max_it) <= 0:
            raise ValueError("Iterative restart and max_it must be positive.")
        if not np.isfinite(float(self.threshold)) or float(self.threshold) <= 0.0:
            raise ValueError("Iterative threshold must be finite and positive.")
        if self.initial_guess != "zero":
            raise ValueError("Only the zero initial guess is supported.")


@dataclass
class HybridBlockLduIterativeResult:
    """Retained solution and lifecycle evidence after the outer solve."""

    solution: PETSc.Vec
    history: list[dict[str, Any]]
    converged_reason: int
    iterations: int
    final_reported_relative_residual: float
    final_true_relative_residual: float
    block_relative_residuals: dict[str, float]
    postsolve_audit: dict[str, Any]
    release: dict[str, Any]
    inventory: dict[str, Any]
    timing: dict[str, float]
    _preconditioner: HybridBlockLduPreconditioner | None = field(
        default=None, repr=False
    )
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def history_evaluation_count(self) -> int:
        return int(self.timing.get("history_evaluation_count", len(self.history)))

    @property
    def postsolve_evaluation_count(self) -> int:
        return int(self.timing.get("postsolve_evaluation_count", 1))

    def release_deferred_action_modal_schur(self) -> None:
        if self._preconditioner is None:
            return
        self._preconditioner.release_deferred_action_modal_schur()
        self.release["action_modal_schur_released"] = True

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.release_deferred_action_modal_schur()
        self.solution.destroy()
        self._destroyed = True


def multimetric_true_residual_decision(
    iteration: int,
    residuals: dict[str, Any],
    *,
    max_it: int = 1000,
    threshold: float = 5.0e-9,
    identity: str = "tight_multimetric_true_residual_gate",
) -> dict[str, Any]:
    """Apply the five-residual finite, nonnegative, tight convergence rule."""

    try:
        values = {key: float(residuals[key]) for key in _RESIDUAL_KEYS}
    except (KeyError, TypeError, ValueError):
        values = {key: float("nan") for key in _RESIDUAL_KEYS}
    finite_nonnegative = bool(
        all(np.isfinite(value) and value >= 0.0 for value in values.values())
    )
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
        "max_true_residual": float(max(values.values(), default=float("nan"))),
        "all_finite_nonnegative": finite_nonnegative,
        "positive": positive,
        "decision": decision,
        "reason": reason,
    }


def _true_residual_metrics(
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
        rhs, context.bottom_system.b, context.top_system.b
    )
    residual_bottom, residual_top, residual_modal = context.layout.split(
        residual, context.bottom_system.b, context.top_system.b
    )
    solution_bottom, solution_top, solution_modal = context.layout.split(
        solution, context.bottom_system.b, context.top_system.b
    )
    bottom_value = context.bottom_system.A.createVecLeft()
    top_value = context.top_system.A.createVecLeft()
    try:
        context.bottom_system.A.mult(solution_bottom, bottom_value)
        context.top_system.A.mult(solution_top, top_value)
        context._apply_modal_tractions(solution_modal)
        context.coupling.bottom.projection.mult(
            solution_bottom, context._bottom_projection
        )
        context.coupling.top.projection.mult(solution_top, context._top_projection)
        bottom_scale = max(
            float(rhs_bottom.norm()),
            float(bottom_value.norm()),
            float(context._bottom_coupling.norm()),
            1.0e-30,
        )
        top_scale = max(
            float(rhs_top.norm()),
            float(top_value.norm()),
            float(context._top_coupling.norm()),
            1.0e-30,
        )
        modal_constraint = context.action_modal_schur_system.modal_constraint
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
        top_value.destroy()
        bottom_value.destroy()
        solution_top.destroy()
        solution_bottom.destroy()
        residual_modal = None
        residual_top.destroy()
        residual_bottom.destroy()
        rhs_top.destroy()
        rhs_bottom.destroy()
        residual.destroy()
    return global_relative, block


def solve_hybrid_block_ldu_iterative(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    context: HybridBlockLduPreconditioner,
    *,
    config: HybridBlockLduIterativeConfig | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> HybridBlockLduIterativeResult:
    """Run right FGMRES with one cached true-residual row per iteration."""

    config = HybridBlockLduIterativeConfig() if config is None else config
    if context._destroyed:
        raise RuntimeError("Cannot solve with a destroyed block-LDU context.")
    solution = operator.createVecRight()
    monitor_solution = operator.createVecRight()
    retained_solution = operator.createVecRight()
    solution.set(0.0)
    monitor_solution.set(0.0)
    retained_solution.set(0.0)
    history: list[dict[str, Any]] = []
    history_cache: dict[int, dict[str, Any]] = {}
    history_evaluations = 0
    started = time.perf_counter()
    rhs_norm = max(float(rhs.norm()), _TINY)
    ksp = PETSc.KSP().create(operator.getComm())
    returned = False

    def snapshot(
        iteration: int,
        reported: float,
        current: PETSc.KSP | None,
    ) -> dict[str, Any]:
        nonlocal history_evaluations
        if int(iteration) in history_cache:
            return history_cache[int(iteration)]
        if current is None:
            solution.copy(monitor_solution)
            current_solution = monitor_solution
        else:
            current_solution = current.buildSolution(monitor_solution)
        global_true, block = _true_residual_metrics(
            operator, rhs, current_solution, context
        )
        row = {
            "iteration": int(iteration),
            "reported_relative_residual": float(reported),
            "global_true_relative_residual": float(global_true),
            "bottom_true_relative_residual": float(block["bottom"]),
            "top_true_relative_residual": float(block["top"]),
            "modal_true_relative_residual": float(block["modal"]),
            "pc_apply_count": int(context.inventory["pc_apply_count"]),
            "bottom_action_apply_count": int(
                context.inventory["bottom_action_apply_count"]
            ),
            "top_action_apply_count": int(context.inventory["top_action_apply_count"]),
            "elapsed_seconds": float(time.perf_counter() - started),
        }
        decision = multimetric_true_residual_decision(
            int(iteration),
            row,
            max_it=config.max_it,
            threshold=config.threshold,
        )
        row.update(
            {
                "multimetric_decision": decision["decision"],
                "multimetric_reason": decision["reason"],
                "multimetric_max_true_residual": decision["max_true_residual"],
            }
        )
        history.append(row)
        history_cache[int(iteration)] = row
        history_evaluations += 1
        if progress_callback is not None:
            progress_callback(dict(row))
        return row

    try:
        snapshot(0, 1.0 if rhs_norm > _TINY else 0.0, None)
        ksp.setOperators(operator)
        ksp.setType(PETSc.KSP.Type.FGMRES)
        ksp.setGMRESRestart(int(config.restart))
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(
            rtol=float(config.threshold), atol=0.0, max_it=int(config.max_it)
        )
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(context)
        ksp.setUp()

        def convergence_test(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            row = snapshot(int(iteration), float(residual_norm) / rhs_norm, current)
            return int(row["multimetric_reason"])

        ksp.setConvergenceTest(convergence_test)
        ksp.solve(rhs, solution)
        iterations = int(ksp.getIterationNumber())
        reason = int(ksp.getConvergedReason())
        reported = float(ksp.getResidualNorm()) / rhs_norm
        if iterations not in history_cache:
            snapshot(iterations, reported, None)
        solution.copy(retained_solution)
        post_global, post_block = _true_residual_metrics(
            operator, rhs, retained_solution, context
        )
        post_values = {
            "reported_relative_residual": reported,
            "global_true_relative_residual": float(post_global),
            "bottom_true_relative_residual": float(post_block["bottom"]),
            "top_true_relative_residual": float(post_block["top"]),
            "modal_true_relative_residual": float(post_block["modal"]),
        }
        post_decision = multimetric_true_residual_decision(
            iterations,
            post_values,
            max_it=config.max_it,
            threshold=config.threshold,
        )
        post_pass = bool(reason > 0 and post_decision["positive"])
        postsolve = {
            **post_values,
            "identity": post_decision["identity"],
            "threshold": float(config.threshold),
            "restart": int(config.restart),
            "explicit_recomputed_residuals": dict(post_values),
            "decision": post_decision["decision"],
            "reason": reason,
            "all_finite_nonnegative": post_decision["all_finite_nonnegative"],
            "max_true_residual": post_decision["max_true_residual"],
            "pass": post_pass,
        }
        inventory = dict(context.inventory)
        release = {
            "ksp_destroyed": False,
            "pc_context_destroyed": False,
            "action_modal_schur_retained_after_pc_destroyed": False,
            "action_modal_schur_released": False,
            "solution_snapshot_retained": True,
            "borrowed_side_actions_retained": False,
        }
        context.defer_action_modal_schur_release = bool(post_pass)
        ksp.destroy()
        ksp = None
        release["ksp_destroyed"] = True
        context.destroy()
        release["pc_context_destroyed"] = True
        release["action_modal_schur_retained_after_pc_destroyed"] = bool(
            not context.action_modal_schur_system.diagnostics["destroyed"]
        )
        release["borrowed_side_actions_retained"] = all(
            not bool(_action_diagnostics(action).get("destroyed"))
            for action in (context.bottom_action, context.top_action)
        )
        timing = {
            "total_seconds": float(time.perf_counter() - started),
            "restart": float(config.restart),
            "max_it": float(config.max_it),
            "threshold": float(config.threshold),
            "history_evaluation_count": float(history_evaluations),
            "postsolve_evaluation_count": 1.0,
        }
        result = HybridBlockLduIterativeResult(
            solution=retained_solution,
            history=[dict(row) for row in history],
            converged_reason=reason,
            iterations=iterations,
            final_reported_relative_residual=reported,
            final_true_relative_residual=float(post_global),
            block_relative_residuals={
                key: float(value) for key, value in post_block.items()
            },
            postsolve_audit=postsolve,
            release=release,
            inventory=inventory,
            timing=timing,
            _preconditioner=context,
        )
        returned = True
        return result
    finally:
        if ksp is not None:
            ksp.destroy()
        if not context._destroyed:
            context.defer_action_modal_schur_release = False
            context.destroy()
        monitor_solution.destroy()
        solution.destroy()
        if not returned:
            retained_solution.destroy()
