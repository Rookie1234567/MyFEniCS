"""Exact block-LDU oracle for the Task037b Hybrid action operator.

The global operator remains the H2b MatPython action.  This module temporarily
uses explicit-condensed bottom/top matrices and their MUMPS factors only to
verify the exact right block-LDU algebra on a small oracle problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    "build_hybrid_action_modal_schur",
    "create_action_block_ldu_preconditioner",
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
    _destroyed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._action_mode = self.action_modal_schur_system is not None
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
                "borrowed_side_actions": True,
                "modal_block_name": self.modal_block_name,
                "modal_block_condition": self._modal_block_condition,
                "modal_schur": modal_diagnostics,
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
        self._pc_apply_count += 1

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
            self.action_modal_schur_system.destroy()
            self.modal_schur = None
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
