"""Action-only Hybrid block-LDU preconditioner and tight iterative solve."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve, solve_triangular
from scipy.linalg import qr as pivoted_qr

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from .hybrid_fem_modal_schur_direct import modal_coupling_action

__all__ = (
    "HybridActionModalSchurApply",
    "HybridActionModalSchurSystem",
    "HybridBlockLduIterativeConfig",
    "HybridBlockLduIterativeResult",
    "HybridBlockLduPreconditioner",
    "build_hybrid_action_modal_schur",
    "create_action_block_ldu_preconditioner",
    "create_research_exact_side_lu_block_ldu_preconditioner",
    "create_side_balh_block_ldu_preconditioner",
    "multimetric_true_residual_decision",
    "solve_action_modal_schur_anderson",
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
_MODAL_ANDERSON_S_EVALUATION_LIMIT = 16
_MODAL_SOLVE_TRACE_SOLVE_LIMIT = 2
_MODAL_SOLVE_TRACE_EVALUATION_LIMIT = 16
_MODAL_SOLVE_TRACE_HISTORY_LIMIT = 4
_MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES = 640 * 1024


def _modal_trace_array_limit_bytes(modal_count: int) -> int:
    values_per_solve = (
        (1 + 3 * _MODAL_SOLVE_TRACE_EVALUATION_LIMIT) * modal_count
        + 14 * _MODAL_SOLVE_TRACE_HISTORY_LIMIT
    )
    return int(
        _MODAL_SOLVE_TRACE_SOLVE_LIMIT
        * values_per_solve
        * np.dtype(np.complex128).itemsize
    )


def _capture_modal_array(
    record: dict[str, Any],
    key: str,
    values: np.ndarray,
) -> dict[str, Any] | None:
    array = np.asarray(values)
    current = int(record.get("captured_array_bytes", 0))
    modal_count = int(record.get("modal_count", array.size))
    if (
        key not in {"g", "m", "raw", "scaled", "gamma"}
        or array.dtype != np.dtype(np.complex128)
        or array.ndim != 1
        or array.size > (
            _MODAL_SOLVE_TRACE_HISTORY_LIMIT if key == "gamma" else modal_count
        )
        or (key != "gamma" and array.size != modal_count)
    ):
        record["capture_complete"] = False
        record["capture_incomplete_reason"] = "unexpected_array_shape_or_dtype"
        return None
    if current + int(array.nbytes) > _modal_trace_array_limit_bytes(modal_count) // 2:
        record["capture_complete"] = False
        record["capture_incomplete_reason"] = "array_payload_limit_exceeded"
        return None
    raw = np.ascontiguousarray(array).tobytes(order="C")
    record["captured_array_bytes"] = current + int(array.nbytes)
    return {
        "dtype": "complex128",
        "shape": list(array.shape),
        "order": "C",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "encoding": "base64",
        "data": base64.b64encode(raw).decode("ascii"),
    }


def _modal_trace_side_apply_record(action: Any) -> dict[str, Any]:
    source = getattr(action, "_last_apply", None)
    source = source if isinstance(source, Mapping) else {}
    last_apply = {}
    for key in (
        "status",
        "reason",
        "iterations",
        "elapsed_seconds",
        "rhs_norm",
        "residual_norm",
        "relative_residual",
    ):
        if key not in source:
            continue
        value = source[key]
        if isinstance(value, np.generic):
            value = value.item()
        if value is None or isinstance(value, (str, int, float, bool)):
            last_apply[key] = value
    counts = source.get("counts", {})
    delta = counts.get("delta") if isinstance(counts, Mapping) else None
    if isinstance(delta, Mapping):
        last_apply["count_delta"] = {
            key: int(delta[key])
            for key in (
                "Q", "H6", "A6", "p4_backsolve", "p4_refinement", "P", "PH_total"
            )
            if isinstance(delta.get(key), (int, np.integer))
        }
    apply_count = getattr(action, "_apply_count", None)
    return {
        "apply_count": int(apply_count)
        if isinstance(apply_count, (int, np.integer))
        else None,
        "apply_count_source": "action_apply_count",
        "audit_index": "unknown",
        "last_apply": last_apply,
    }


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


def _encode_modal_real_coordinates(values: np.ndarray) -> np.ndarray:
    """Store complex modal values as real-valued ``[Re, Im]`` coordinates."""

    modal_values = np.asarray(values, dtype=np.complex128)
    if modal_values.ndim != 1:
        raise ValueError("Modal values must be a one-dimensional vector.")
    coordinates = np.empty(2 * modal_values.size, dtype=np.complex128)
    coordinates[: modal_values.size] = modal_values.real
    coordinates[modal_values.size :] = modal_values.imag
    return coordinates


def _decode_modal_real_coordinates(
    coordinates: np.ndarray, modal_count: int
) -> np.ndarray:
    """Restore real-valued ``[Re, Im]`` coordinates to complex modal values."""

    values = np.asarray(coordinates, dtype=np.complex128)
    if values.shape != (2 * modal_count,):
        raise ValueError("Real modal coordinates have the wrong shape.")
    return np.asarray(
        values[:modal_count].real + 1j * values[modal_count:].real,
        dtype=np.complex128,
    )


def _action_diagnostics(action: Any) -> dict[str, Any]:
    diagnostics = getattr(action, "diagnostics", None)
    if callable(diagnostics):
        diagnostics = diagnostics()
    if not isinstance(diagnostics, dict):
        raise TypeError("Borrowed action must expose diagnostics.")
    return dict(diagnostics)


def _action_apply_count(action: Any) -> int | None:
    try:
        value = _action_diagnostics(action).get("apply_count")
    except (TypeError, ValueError):
        return None
    if isinstance(value, (int, np.integer)) and int(value) >= 0:
        return int(value)
    return None


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


def _factor_modal_constraint(
    constraint_values: np.ndarray, modal_count: int
) -> tuple[np.ndarray, np.ndarray, float]:
    constraint = np.asarray(constraint_values, dtype=np.complex128)
    if constraint.shape != (modal_count, modal_count):
        raise ValueError("C has the wrong modal shape")
    if not bool(np.all(np.isfinite(constraint))):
        raise ValueError("C contains non-finite values")
    condition = float(np.linalg.cond(constraint))
    if not np.isfinite(condition) or condition * np.finfo(float).eps >= 1.0:
        raise np.linalg.LinAlgError("C is singular at complex128 working precision")
    lu, pivots = lu_factor(constraint, check_finite=True)
    diagonal = np.diag(lu)
    if not bool(np.all(np.isfinite(diagonal))) or bool(np.any(diagonal == 0.0)):
        raise np.linalg.LinAlgError("C LU has a zero or non-finite pivot")
    return (
        np.asarray(lu, dtype=np.complex128),
        np.asarray(pivots),
        condition,
    )


def _complex_anderson_qr_coefficients(
    delta_f: np.ndarray, current_f: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve a small complex Anderson least-squares problem by pivoted QR.

    The returned coefficients are mapped back from the pivoted column order.
    Numerically dependent trailing columns are omitted using a scale-relative
    working-precision cutoff; no normal equations or pseudoinverse are used.
    """

    matrix = np.asarray(delta_f, dtype=np.complex128)
    vector = np.asarray(current_f, dtype=np.complex128)
    if matrix.ndim != 2 or vector.shape != (matrix.shape[0],):
        raise ValueError("Complex Anderson history has incompatible shapes.")
    if matrix.shape[1] < 1:
        raise ValueError("Complex Anderson QR requires at least one history column.")
    if not bool(np.all(np.isfinite(matrix))) or not bool(np.all(np.isfinite(vector))):
        raise FloatingPointError("Complex Anderson history is non-finite.")

    q_matrix, r_matrix, pivots = pivoted_qr(
        matrix,
        mode="economic",
        pivoting=True,
        check_finite=False,
    )
    diagonal = np.abs(np.diag(r_matrix))
    qr_scale = float(np.max(diagonal)) if diagonal.size else 0.0
    cutoff = (
        np.finfo(np.float64).eps * max(matrix.shape) * qr_scale
    )
    rank = 0
    for value in diagonal:
        if float(value) <= cutoff:
            break
        rank += 1

    coefficients = np.zeros(matrix.shape[1], dtype=np.complex128)
    if rank:
        projected = q_matrix[:, :rank].conj().T @ vector
        pivoted_coefficients = solve_triangular(
            r_matrix[:rank, :rank],
            projected,
            lower=False,
            check_finite=False,
        )
        coefficients[np.asarray(pivots[:rank], dtype=np.intp)] = (
            pivoted_coefficients
        )
    if not bool(np.all(np.isfinite(coefficients))):
        raise FloatingPointError("Complex Anderson QR coefficients are non-finite.")
    fit_residual = matrix @ coefficients - vector
    if not bool(np.all(np.isfinite(fit_residual))):
        raise FloatingPointError("Complex Anderson QR fit is non-finite.")
    fit_residual_norm = float(np.linalg.norm(fit_residual))
    if not np.isfinite(fit_residual_norm):
        raise FloatingPointError("Complex Anderson QR fit norm is non-finite.")
    return coefficients, {
        "effective_rank": int(rank),
        "history_column_count": int(matrix.shape[1]),
        "discarded_column_count": int(matrix.shape[1] - rank),
        "qr_scale": qr_scale,
        "rank_cutoff": float(cutoff),
        "fit_residual_norm": fit_residual_norm,
    }


def _complex_anderson_candidate_update(
    modal: np.ndarray,
    fixed_point_residual: np.ndarray,
    delta_m: np.ndarray | None,
    delta_f: np.ndarray | None,
    *,
    capture_coefficients: bool = False,
    mixing_metric: str = "C_scaled_residual",
    raw_residual: np.ndarray | None = None,
    delta_raw_residual: np.ndarray | None = None,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Make one beta=1 complex Type-II update or report rank zero."""

    current = np.asarray(modal, dtype=np.complex128)
    fixed_point = np.asarray(fixed_point_residual, dtype=np.complex128)
    if current.ndim != 1 or fixed_point.shape != current.shape:
        raise ValueError("Complex Anderson update vectors have incompatible shapes.")
    if not bool(np.all(np.isfinite(current))) or not bool(
        np.all(np.isfinite(fixed_point))
    ):
        raise FloatingPointError("Complex Anderson update vectors are non-finite.")
    if mixing_metric not in {"C_scaled_residual", "raw_residual"}:
        raise ValueError("Unknown complex Anderson least-squares metric.")
    if mixing_metric == "C_scaled_residual":
        if raw_residual is not None or delta_raw_residual is not None:
            raise ValueError("Raw residual data requires the raw mixing metric.")
        mixing_vector = fixed_point
    else:
        if raw_residual is None:
            raise ValueError("Raw Anderson mixing requires the current raw residual.")
        mixing_vector = np.asarray(raw_residual, dtype=np.complex128)
        if mixing_vector.shape != current.shape:
            raise ValueError("Raw Anderson residual has an incompatible shape.")
        if not bool(np.all(np.isfinite(mixing_vector))):
            raise FloatingPointError("Raw Anderson residual is non-finite.")
    delta_f_values = (
        None if delta_f is None else np.asarray(delta_f, dtype=np.complex128)
    )
    if delta_f_values is not None and delta_f_values.ndim != 2:
        raise ValueError("Complex Anderson residual history must be a matrix.")
    if (delta_m is None) != (delta_f_values is None):
        raise ValueError("Complex Anderson iterate and residual histories must match.")
    if delta_f_values is None or delta_f_values.shape[1] == 0:
        if delta_raw_residual is not None:
            raise ValueError("Raw Anderson differences require a history column.")
        candidate = current + fixed_point
        if not bool(np.all(np.isfinite(candidate))):
            raise FloatingPointError("Complex Anderson startup step is non-finite.")
        return candidate, {
            "update": "fixed_point_startup",
            "history_column_count": 0,
            "effective_rank": 0,
            "discarded_column_count": 0,
            "qr_scale": 0.0,
            "rank_cutoff": 0.0,
            "fit_residual_norm": None,
            "mixing_metric": mixing_metric,
        }
    delta_m_values = np.asarray(delta_m, dtype=np.complex128)
    delta_f_values = np.asarray(delta_f_values, dtype=np.complex128)
    if (
        delta_m_values.ndim != 2
        or delta_f_values.ndim != 2
        or delta_m_values.shape != delta_f_values.shape
        or delta_m_values.shape[0] != current.size
    ):
        raise ValueError("Complex Anderson difference histories have incompatible shapes.")
    if mixing_metric == "raw_residual":
        if delta_raw_residual is None:
            raise ValueError("Raw Anderson mixing requires raw residual history.")
        delta_mixing = np.asarray(delta_raw_residual, dtype=np.complex128)
        if delta_mixing.shape != delta_f_values.shape:
            raise ValueError("Raw and scaled Anderson histories must align.")
        coefficients, diagnostics = _complex_anderson_qr_coefficients(
            delta_mixing, mixing_vector
        )
    else:
        coefficients, diagnostics = _complex_anderson_qr_coefficients(
            delta_f_values, mixing_vector
        )
    diagnostics["mixing_metric"] = mixing_metric
    if capture_coefficients:
        diagnostics["_capture_gamma"] = coefficients
    if diagnostics["effective_rank"] == 0:
        return None, {"update": "rank_zero_history", **diagnostics}
    candidate = current + fixed_point - (delta_m_values + delta_f_values) @ coefficients
    if not bool(np.all(np.isfinite(candidate))):
        raise FloatingPointError("Complex Anderson candidate is non-finite.")
    return candidate, {"update": "complex_qr_type_ii", **diagnostics}


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
    sampled_column_diagnostics: dict[str, Any] = field(default_factory=dict)
    batch_diagnostics: dict[str, Any] = field(default_factory=dict)
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

    @property
    def modal_count(self) -> int:
        return int(self._shape[0])

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
            "sampled_column_diagnostics": dict(self.sampled_column_diagnostics),
            "batch_diagnostics": dict(self.batch_diagnostics),
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


@dataclass
class HybridActionModalSchurApply:
    """Apply one modal Schur action without assembling its columns.

    The side actions and coupling are borrowed.  This object does not assert
    that they define a fixed linear map: adaptive side actions may make each
    call nonlinear or call-dependent, so this is not itself a PETSc Mat/KSP.
    """

    coupling: HybridInternalModeCoupling
    bottom_action: Any
    top_action: Any
    modal_constraint: np.ndarray = field(init=False, repr=False)
    _destroyed: bool = field(default=False, init=False, repr=False)
    _modal_constraint_matvec_count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.mode_count = int(self.coupling.mode_count_per_direction)
        self.modal_count = 2 * self.mode_count
        self.modal_constraint = np.asarray(
            internal_modal_constraint_matrix(self.coupling), dtype=np.complex128
        )
        if self.modal_constraint.shape != (self.modal_count, self.modal_count):
            raise ValueError("Modal constraint has the wrong shape.")

    def _subtract_side_response(self, side: str, modal: np.ndarray, result: np.ndarray) -> None:
        action = self.bottom_action if side == "bottom" else self.top_action
        projection = (
            self.coupling.bottom.projection
            if side == "bottom"
            else self.coupling.top.projection
        )
        traction = modal_coupling_action(side, self.coupling, modal)
        response = projected = None
        try:
            response = _action_operator(action).createVecLeft()
            projected = projection.createVecLeft()
            action.apply(traction, response)
            projection.mult(response, projected)
            start = 0 if side == "bottom" else self.mode_count
            result[start : start + self.mode_count] -= _replicated_modal_values(
                projected
            )
        finally:
            if projected is not None:
                projected.destroy()
            if response is not None:
                response.destroy()
            traction.destroy()

    def apply(self, modal: np.ndarray) -> np.ndarray:
        """Return ``C modal - projected(bottom) - projected(top)``."""

        if self._destroyed:
            raise RuntimeError("On-demand modal Schur action has been destroyed.")
        values = np.asarray(modal, dtype=np.complex128)
        if values.shape != (self.modal_count,):
            raise ValueError("Modal Schur input has the wrong shape.")
        result = np.asarray(self.modal_constraint @ values, dtype=np.complex128)
        self._modal_constraint_matvec_count += 1
        self._subtract_side_response("bottom", values, result)
        self._subtract_side_response("top", values, result)
        return result

    def destroy(self) -> None:
        """Release owned modal data without destroying borrowed actions."""

        if self._destroyed:
            return
        self.modal_constraint = None
        self._destroyed = True


class _FixedH6ModalMatContext:
    def __init__(self, owner: _FixedH6ModalKrylovSystem) -> None:
        self.owner: _FixedH6ModalKrylovSystem | None = owner

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.owner is None:
            raise RuntimeError("Fixed-H6 modal Mat context was destroyed")
        self.owner._mat_mult(source, target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.owner = None


class _FixedH6ModalConstraintPcContext:
    def __init__(self, owner: _FixedH6ModalKrylovSystem) -> None:
        self.owner: _FixedH6ModalKrylovSystem | None = owner

    def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self.owner is None:
            raise RuntimeError("Fixed-H6 modal C-PC context was destroyed")
        self.owner._apply_constraint_pc(_pc, source, target)

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.owner = None


class _FixedH6ModalKrylovSystem:
    """Bounded fixed-H6 modal solve used only by its explicit research branch."""

    rtol = 1.0e-3
    max_it = 8
    solver_matmult_limit = 9
    total_matmult_limit = 10
    modal_schur = None
    requires_right_fgmres = True

    def __init__(
        self,
        coupling: HybridInternalModeCoupling,
        bottom_action: Any,
        top_action: Any,
        *,
        modal_owner: int,
    ) -> None:
        from .physical_balanced_side_inverse import FixedH6ActiveTraceAction

        self._bottom_action = bottom_action
        self._top_action = top_action
        self._modal_action: HybridActionModalSchurApply | None = None
        # The coupling projection is the shared communicator anchor.  No PETSc
        # solver object or modal action is allocated before the first collective
        # validation has rejected rank-local metadata errors.
        petsc_comm = coupling.bottom.projection.getComm()
        self._comm = petsc_comm.tompi4py()
        self._modal_owner = -1
        self.modal_count = 0
        self.mode_count = 0
        self._constraint_lu = self._constraint_pivots = None
        self._constraint_lu_solve_attempts = 0
        self._constraint_lu_solve_successes = 0
        self._constraint_lu_factorizations_local = 0
        self._constraint_lu_factorizations_owner = 0
        self._solver_matmult_calls = self._total_matmult_calls = 0
        self._modal_constraint_matvec_calls_at_destroy = 0
        self._blocked_matmult_attempts = 0
        self._budget_exhausted = False
        self._in_final_check = False
        self._pc_failure_error: str | None = None
        self._mat_preflight_failure: str | None = None
        self._destroyed = False
        self._last_solve: dict[str, Any] | None = None
        self._solve_count = 0
        self._not_converged_count = 0
        self._cumulative_solver_matmult_calls = 0
        self._cumulative_total_matmult_calls = 0
        self._cumulative_constraint_lu_solve_attempts = 0
        self._cumulative_constraint_lu_solve_successes = 0
        self.modal_constraint_local_bytes = 0
        self._matrix = self._ksp = None
        self._rhs = self._solution = self._image = self._residual = None

        local_error = None
        local_signature = None
        requested_owner = -1
        mode_count = 0
        constraint = None
        try:
            requested_owner = int(modal_owner)
            mode_count = int(coupling.mode_count_per_direction)
            modal_count = 2 * mode_count
            if requested_owner != self._comm.size - 1:
                raise ValueError("Modal ownership must be on the final MPI rank")
            if mode_count <= 0:
                raise ValueError("Fixed-H6 modal system requires nonempty modes")
            if not all(
                isinstance(action, FixedH6ActiveTraceAction)
                for action in (bottom_action, top_action)
            ):
                raise TypeError("S_H requires two FixedH6ActiveTraceAction inputs")
            constraint = np.asarray(
                internal_modal_constraint_matrix(coupling), dtype=np.complex128
            )
            if constraint.shape != (modal_count, modal_count) or not np.all(
                np.isfinite(constraint)
            ):
                raise ValueError("S_H modal constraint is malformed or non-finite")
            side_shapes = []
            for side, action, interface in (
                ("bottom", bottom_action, coupling.bottom),
                ("top", top_action, coupling.top),
            ):
                if action._destroyed or action._condensed is None or action._h6 is None:
                    raise ValueError(f"{side} Fixed-H6 action is not live")
                operator = action.operator
                condensed = action._condensed
                h6_matrix = action._h6.matrix
                active_rows = int(condensed.active_rows)
                full_rows = int(condensed.full_rows)
                if operator.getSize() != (active_rows, active_rows):
                    raise ValueError(f"{side} active operator shape is inconsistent")
                if h6_matrix.getSize() != (full_rows, full_rows):
                    raise ValueError(f"{side} Fixed-H6 shape is inconsistent")
                if interface.projection.getSize() != (mode_count, active_rows):
                    raise ValueError(f"{side} modal projection shape is inconsistent")
                for matrix in (operator, h6_matrix, interface.projection):
                    relation = MPI.Comm.Compare(
                        self._comm, matrix.getComm().tompi4py()
                    )
                    if relation not in (MPI.IDENT, MPI.CONGRUENT):
                        raise ValueError(f"{side} action communicator differs")
                side_shapes.append((active_rows, full_rows))
            local_signature = (
                mode_count,
                modal_count,
                hashlib.sha256(np.ascontiguousarray(constraint).tobytes()).hexdigest(),
                tuple(side_shapes),
            )
        except Exception as exc:  # noqa: BLE001 - synchronize rank-local setup errors
            local_error = f"{type(exc).__name__}: {exc}"
        preflight = self._comm.allgather((local_error, local_signature))
        failures = [
            f"rank {rank}: {error}"
            for rank, (error, _signature) in enumerate(preflight)
            if error is not None
        ]
        signatures = [signature for error, signature in preflight if error is None]
        if signatures and any(signature != signatures[0] for signature in signatures[1:]):
            failures.extend(
                f"rank {rank}: modal/action layout metadata differs"
                for rank, (error, signature) in enumerate(preflight)
                if error is None and signature != signatures[0]
            )
        if failures:
            raise RuntimeError("Fixed-H6 modal input preflight failed; " + "; ".join(failures))

        self._modal_owner = requested_owner
        self.mode_count = mode_count
        self.modal_count = 2 * mode_count
        expected_constraint_sha = local_signature[2]

        construction_error = None
        try:
            self._modal_action = HybridActionModalSchurApply(
                coupling, bottom_action, top_action
            )
            constraint_sha = hashlib.sha256(
                np.ascontiguousarray(self._modal_action.modal_constraint).tobytes()
            ).hexdigest()
            if constraint_sha != expected_constraint_sha:
                raise ValueError("modal action constraint differs from validated input")
        except Exception as exc:  # noqa: BLE001 - synchronize local construction errors
            construction_error = f"{type(exc).__name__}: {exc}"
        constructions = self._comm.allgather(construction_error)
        construction_failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(constructions)
            if error is not None
        ]
        if construction_failures:
            if self._modal_action is not None:
                self._modal_action.destroy()
                self._modal_action = None
            raise RuntimeError(
                "Fixed-H6 modal action construction failed; "
                + "; ".join(construction_failures)
            )
        self.modal_constraint_local_bytes = int(
            self._modal_action.modal_constraint.nbytes
        )

        factor_result = None
        if self._comm.rank == self._modal_owner:
            try:
                lu, pivots, condition = _factor_modal_constraint(constraint, self.modal_count)
                self._constraint_lu = lu
                self._constraint_pivots = pivots
                self._constraint_lu_factorizations_local += 1
                factor_result = (True, condition, None, 1)
            except Exception as exc:  # noqa: BLE001 - owner result is broadcast below
                factor_result = (False, None, f"{type(exc).__name__}: {exc}", 0)
        factor_ok, condition, factor_error, owner_factorizations = self._comm.bcast(
            factor_result, root=self._modal_owner
        )
        self._constraint_lu_factorizations_owner = int(owner_factorizations)
        if not factor_ok:
            self.destroy()
            raise RuntimeError(f"Fixed-H6 modal C factorization failed: {factor_error}")
        self.constraint_condition = float(condition)

        local_size = self.modal_count if self._comm.rank == self._modal_owner else 0
        try:
            self._matrix = PETSc.Mat().createPython(
                ((local_size, self.modal_count), (local_size, self.modal_count)),
                comm=petsc_comm,
            )
            self._matrix.setPythonContext(_FixedH6ModalMatContext(self))
            self._matrix.setUp()
            self._rhs = self._matrix.createVecRight()
            self._solution = self._matrix.createVecRight()
            self._image = self._matrix.createVecLeft()
            self._residual = self._matrix.createVecLeft()
            self._ksp = PETSc.KSP().create(petsc_comm)
            self._ksp.setOperators(self._matrix)
            self._ksp.setType(PETSc.KSP.Type.GMRES)
            self._ksp.setGMRESRestart(self.max_it)
            self._ksp.setPCSide(PETSc.PC.Side.RIGHT)
            self._ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            self._ksp.setInitialGuessNonzero(False)
            self._ksp.setTolerances(rtol=self.rtol, atol=0.0, max_it=self.max_it)
            pc = self._ksp.getPC()
            pc.setType(PETSc.PC.Type.PYTHON)
            pc.setPythonContext(_FixedH6ModalConstraintPcContext(self))
            self._ksp.setUp()
            pc.setFailedReason(PETSc.PC.FailedReason.NOERROR)
        except BaseException:
            self.destroy()
            raise

    @property
    def modal_constraint(self) -> np.ndarray | None:
        if self._destroyed or self._modal_action is None:
            return None
        return self._modal_action.modal_constraint

    @property
    def constraint_lu_factorizations(self) -> int:
        return int(self._constraint_lu_factorizations_owner)

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("Fixed-H6 modal system has been destroyed")
        actions = (("bottom", self._bottom_action), ("top", self._top_action))
        before = {
            side: int(action.audit["apply_count"])
            for side, action in actions
        }
        try:
            return self._solve_once(rhs)
        finally:
            self._solve_count += 1
            self._cumulative_solver_matmult_calls += int(
                self._solver_matmult_calls
            )
            self._cumulative_total_matmult_calls += int(self._total_matmult_calls)
            self._cumulative_constraint_lu_solve_attempts += int(
                self._constraint_lu_solve_attempts
            )
            self._cumulative_constraint_lu_solve_successes += int(
                self._constraint_lu_solve_successes
            )
            if self._last_solve is not None:
                self._last_solve["fixed_h6_side_action_apply_calls"] = {
                    side: int(action.audit["apply_count"]) - before[side]
                    for side, action in actions
                }
                self._last_solve["fixed_h6_side_action_count_scope"] = (
                    "per_rank_replicated; do_not_sum_across_ranks"
                )
                self._last_solve["cumulative_solve_count"] = self._solve_count
                self._last_solve["cumulative_solver_matmult_calls"] = (
                    self._cumulative_solver_matmult_calls
                )
                self._last_solve["cumulative_total_matmult_calls"] = (
                    self._cumulative_total_matmult_calls
                )
                if self._last_solve.get("status") not in {
                    "converged",
                    "zero_rhs_exact",
                }:
                    self._not_converged_count += 1

    def _raise_collective_error(self, local_error: str | None, stage: str) -> None:
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            raise RuntimeError(f"Fixed-H6 modal {stage} failed; " + "; ".join(failures))

    def _mat_mult(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        local_error = None
        owner = self._modal_owner
        expected = self.modal_count if self._comm.rank == owner else 0
        try:
            if self._destroyed:
                raise RuntimeError("Fixed-H6 modal system was destroyed")
            if source.getLocalSize() != expected or target.getLocalSize() != expected:
                raise ValueError("S_H MatMult ownership differs from modal layout")
            if self._in_final_check:
                if self._total_matmult_calls >= self.total_matmult_limit:
                    self._budget_exhausted = True
                    raise RuntimeError("S_H total MatMult budget exhausted")
            elif self._solver_matmult_calls >= self.solver_matmult_limit:
                self._budget_exhausted = True
                raise RuntimeError("S_H solver MatMult budget exhausted")
        except Exception as exc:  # noqa: BLE001 - all ranks reject before action calls
            local_error = f"{type(exc).__name__}: {exc}"
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            detail = "; ".join(failures)
            if self._budget_exhausted:
                self._blocked_matmult_attempts += 1
                self._last_solve.update(
                    status="budget_exhausted",
                    final_residual_evaluated=False,
                    final_residual_status="not_evaluated",
                    final_residual_not_evaluated_reason=(
                        "solver_matmult_budget_exhausted_before_trusted_iterate"
                    ),
                    budget_used_solver_matmult_calls=self._solver_matmult_calls,
                    budget_used_total_matmult_calls=self._total_matmult_calls,
                    blocked_matmult_attempts=self._blocked_matmult_attempts,
                )
            else:
                self._mat_preflight_failure = detail
                self._last_solve.update(
                    status="mat_preflight_failed",
                    final_residual_evaluated=False,
                    final_residual_status="not_evaluated",
                    final_residual_not_evaluated_reason=(
                        "MatMult_vector_layout_rejected_before_S_H"
                    ),
                )
            raise RuntimeError(f"Fixed-H6 modal MatMult preflight failed; {detail}")

        self._total_matmult_calls += 1
        if not self._in_final_check:
            self._solver_matmult_calls += 1
        local_values = (
            np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
            if self._comm.rank == owner
            else None
        )
        values = np.asarray(self._comm.bcast(local_values, root=owner), dtype=np.complex128)
        # The action itself contains multiple PETSc collectives.  Do not wrap it
        # in a local try/allgather: an arbitrary rank-local callback exception
        # cannot safely be synchronized after those collectives have diverged.
        result = self._modal_action.apply(values)
        local_error = None
        if result.shape != (self.modal_count,) or not np.all(np.isfinite(result)):
            local_error = "FloatingPointError: S_H returned a malformed or non-finite vector"
        self._raise_collective_error(local_error, "MatMult result")
        if self._comm.rank == owner:
            target.getArray()[:] = result
        if self._in_final_check:
            self._last_solve["final_residual_evaluated"] = True

    def _apply_constraint_pc(
        self, pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self._pc_failure_error is not None:
            pc.setFailedReason(PETSc.PC.FailedReason.SUBPC_ERROR)
            target.set(PETSc.ScalarType(np.inf))
            return
        owner = self._modal_owner
        expected = self.modal_count if self._comm.rank == owner else 0
        local_error = None
        values = solved = None
        try:
            if source.getLocalSize() != expected or target.getLocalSize() != expected:
                raise ValueError("C-LU PC ownership differs from modal layout")
            if self._comm.rank == owner:
                values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
                if not np.all(np.isfinite(values)):
                    raise FloatingPointError("C-LU PC input is non-finite")
                self._constraint_lu_solve_attempts += 1
                solved = lu_solve(
                    (self._constraint_lu, self._constraint_pivots),
                    values,
                    check_finite=True,
                )
                if not np.all(np.isfinite(solved)):
                    raise FloatingPointError("C-LU PC result is non-finite")
                self._constraint_lu_solve_successes += 1
        except Exception as exc:  # noqa: BLE001 - synchronize owner solve failures
            local_error = f"{type(exc).__name__}: {exc}"
        errors = self._comm.allgather(local_error)
        failures = [
            f"rank {rank}: {error}"
            for rank, error in enumerate(errors)
            if error is not None
        ]
        if failures:
            # Keep the local latch for result classification and also report
            # failure through PETSc's Python-PC channel.  The non-finite
            # output cannot be mistaken for a valid preconditioned vector.
            self._pc_failure_error = "; ".join(failures)
            pc.setFailedReason(PETSc.PC.FailedReason.SUBPC_ERROR)
            target.set(PETSc.ScalarType(np.inf))
            return
        if self._comm.rank == owner:
            target.getArray()[:] = solved

    def _reset_attempt(self) -> None:
        self._solver_matmult_calls = self._total_matmult_calls = 0
        self._blocked_matmult_attempts = 0
        self._constraint_lu_solve_attempts = 0
        self._constraint_lu_solve_successes = 0
        self._budget_exhausted = False
        self._pc_failure_error = None
        self._mat_preflight_failure = None
        # Match the existing BAL_H KSP lifecycle: clear the prior callback
        # failure before each new solve, then latch SUBPC_ERROR on a new one.
        self._ksp.getPC().setFailedReason(PETSc.PC.FailedReason.NOERROR)
        self._last_solve = {
            "status": "running",
            "ksp_reason": None,
            "zero_initial_guess": True,
            "solver_matmult_calls": 0,
            "total_matmult_calls": 0,
            "final_residual_evaluated": False,
            "final_residual_status": "not_evaluated",
            "local_constraint_lu_solve_attempts": 0,
            "local_constraint_lu_solve_successes": 0,
            "owner_constraint_lu_solve_attempts": 0,
            "owner_constraint_lu_solve_successes": 0,
            "constraint_lu_solve_count_scope": (
                "owner_authoritative_replicated_report_after_KSP_return"
            ),
        }

    def _final_residual(self, rhs_norm: float) -> tuple[float | None, bool]:
        if self._budget_exhausted or self._total_matmult_calls >= self.total_matmult_limit:
            self._budget_exhausted = True
            self._last_solve.update(
                status="budget_exhausted",
                final_residual_evaluated=False,
                final_residual_status="not_evaluated",
                final_residual_not_evaluated_reason="S_H_matmult_budget_reserved_or_exhausted",
                budget_used_solver_matmult_calls=self._solver_matmult_calls,
                budget_used_total_matmult_calls=self._total_matmult_calls,
                blocked_matmult_attempts=self._blocked_matmult_attempts,
            )
            return None, False
        self._in_final_check = True
        try:
            self._matrix.mult(self._solution, self._image)
        finally:
            self._in_final_check = False
        self._rhs.copy(self._residual)
        self._residual.axpy(PETSc.ScalarType(-1.0), self._image)
        residual_norm = float(self._residual.norm())
        finite = bool(np.isfinite(residual_norm) and np.isfinite(rhs_norm))
        relative = (
            residual_norm / rhs_norm if finite and rhs_norm > 0.0 else None
        )
        self._last_solve.update(
            final_residual_norm=residual_norm if finite else None,
            final_relative_residual=relative,
            final_residual_evaluated=True,
            final_residual_status="evaluated",
            final_residual_not_evaluated_reason=None,
        )
        return relative, finite and (residual_norm == 0.0 if rhs_norm == 0.0 else True)

    def _solve_once(self, rhs: np.ndarray) -> np.ndarray:
        self._reset_attempt()
        local_error = None
        values = None
        rhs_norm = float("nan")
        try:
            values = np.asarray(rhs, dtype=np.complex128)
            if values.shape != (self.modal_count,) or not np.all(np.isfinite(values)):
                raise ValueError("S_H RHS has the wrong shape or non-finite values")
            rhs_norm = float(np.linalg.norm(values))
            if not np.isfinite(rhs_norm):
                raise FloatingPointError("S_H RHS norm is non-finite")
        except Exception as exc:  # noqa: BLE001 - synchronize RHS rejection
            local_error = f"{type(exc).__name__}: {exc}"
        self._raise_collective_error(local_error, "RHS")
        digests = self._comm.allgather(hashlib.sha256(values.tobytes()).hexdigest())
        if len(set(digests)) != 1:
            self._raise_collective_error("modal RHS differs across ranks", "RHS")

        self._rhs.set(0.0)
        self._solution.set(0.0)
        if self._comm.rank == self._modal_owner:
            self._rhs.getArray()[:] = values
        self._rhs.assemble()
        self._solution.assemble()
        initial_solution_norm = float(self._solution.norm())
        self._last_solve["initial_solution_norm"] = initial_solution_norm
        if rhs_norm == 0.0:
            relative, finite = self._final_residual(rhs_norm)
            passed = bool(finite and relative is None and not self._budget_exhausted)
            status = (
                "budget_exhausted"
                if self._budget_exhausted
                else "zero_rhs_exact"
                if passed
                else "zero_rhs_failed"
            )
            self._last_solve.update(
                status=status,
                ksp_reason=None,
                ksp_status="not_run_zero_rhs",
                rhs_norm=0.0,
                s_h_rtol=self.rtol,
                solver_matmult_calls=self._solver_matmult_calls,
                total_matmult_calls=self._total_matmult_calls,
                local_constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_local
                ),
                constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_owner
                ),
                local_constraint_lu_solve_attempts=0,
                local_constraint_lu_solve_successes=0,
                owner_constraint_lu_solve_attempts=0,
                owner_constraint_lu_solve_successes=0,
                constraint_lu_solve_count_scope=(
                    "owner_authoritative_replicated_report"
                ),
            )
            if not passed:
                raise RuntimeError(f"Fixed-H6 modal zero-RHS solve failed: {status}")
            return np.zeros(self.modal_count, dtype=np.complex128)

        try:
            self._ksp.solve(self._rhs, self._solution)
        except Exception as exc:
            # Local petsc4py files identify PETSC_ERR_PYTHON but do not promise
            # cross-rank callback-exception synchronization.  Do not start a
            # new MPI collective here after an arbitrary callback exception.
            # Explicit preflight and owner-PC failures use separate protocols.
            try:
                reason = int(self._ksp.getConvergedReason())
            except PETSc.Error:
                reason = None
            try:
                iterations = int(self._ksp.getIterationNumber())
            except PETSc.Error:
                iterations = None
            if self._budget_exhausted:
                status = "budget_exhausted"
                not_evaluated_reason = (
                    "budget_exhausted_before_trusted_KSP_iterate"
                )
                ksp_status = "raised_after_budget_exhaustion"
            elif self._pc_failure_error is not None:
                status = "pc_apply_failed"
                not_evaluated_reason = "PC_failure_no_trusted_KSP_iterate"
                ksp_status = "raised_after_synchronized_pc_failure"
            elif self._mat_preflight_failure is not None:
                status = "mat_preflight_failed"
                not_evaluated_reason = "Mat_preflight_rejected_before_S_H"
                ksp_status = "raised_after_mat_preflight_failure"
            else:
                status = "ksp_callback_failed"
                not_evaluated_reason = "KSP_callback_exception_no_trusted_iterate"
                ksp_status = "raised_local_sync_unverified"
            self._last_solve.update(
                status=status,
                ksp_reason=reason,
                ksp_status=ksp_status,
                error=f"{type(exc).__name__}: {exc}",
                iterations=iterations,
                rhs_norm=rhs_norm,
                solver_matmult_calls=self._solver_matmult_calls,
                total_matmult_calls=self._total_matmult_calls,
                final_residual_evaluated=False,
                final_residual_status="not_evaluated",
                final_residual_not_evaluated_reason=not_evaluated_reason,
                pc_failure=self._pc_failure_error,
                budget_used_solver_matmult_calls=self._solver_matmult_calls,
                budget_used_total_matmult_calls=self._total_matmult_calls,
                local_constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_local
                ),
                constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_owner
                ),
                local_constraint_lu_solve_attempts=self._constraint_lu_solve_attempts,
                local_constraint_lu_solve_successes=self._constraint_lu_solve_successes,
                owner_constraint_lu_solve_attempts=(
                    self._constraint_lu_solve_attempts
                    if self._comm.rank == self._modal_owner
                    else None
                ),
                owner_constraint_lu_solve_successes=(
                    self._constraint_lu_solve_successes
                    if self._comm.rank == self._modal_owner
                    else None
                ),
                constraint_lu_solve_count_scope=(
                    "owner_value_unavailable_without_post_callback_collective"
                ),
            )
            raise RuntimeError(
                f"Fixed-H6 modal KSP failed: {self._last_solve['error']}"
            ) from exc

        reason = int(self._ksp.getConvergedReason())
        iterations = int(self._ksp.getIterationNumber())
        states = self._comm.allgather((reason, iterations, self._solver_matmult_calls))
        if len(set(states)) != 1:
            raise RuntimeError("Fixed-H6 modal KSP state differs across ranks")
        owner_lu_solve_attempts = int(
            self._comm.bcast(
                self._constraint_lu_solve_attempts
                if self._comm.rank == self._modal_owner
                else None,
                root=self._modal_owner,
            )
        )
        owner_lu_solve_successes = int(
            self._comm.bcast(
                self._constraint_lu_solve_successes
                if self._comm.rank == self._modal_owner
                else None,
                root=self._modal_owner,
            )
        )
        if self._pc_failure_error is not None:
            status = "budget_exhausted" if self._budget_exhausted else "pc_apply_failed"
            not_evaluated_reason = (
                "budget_exhausted_before_trusted_KSP_iterate"
                if self._budget_exhausted
                else "PC_failure_no_trusted_KSP_iterate"
            )
            self._last_solve.update(
                status=status,
                ksp_reason=reason,
                ksp_status="returned_after_marked_pc_failure",
                iterations=iterations,
                rhs_norm=rhs_norm,
                initial_solution_norm=initial_solution_norm,
                solver_matmult_calls=self._solver_matmult_calls,
                total_matmult_calls=self._total_matmult_calls,
                final_residual_evaluated=False,
                final_residual_status="not_evaluated",
                final_residual_not_evaluated_reason=not_evaluated_reason,
                pc_failure=self._pc_failure_error,
                local_constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_local
                ),
                constraint_lu_factorizations=(
                    self._constraint_lu_factorizations_owner
                ),
                local_constraint_lu_solve_attempts=self._constraint_lu_solve_attempts,
                local_constraint_lu_solve_successes=self._constraint_lu_solve_successes,
                owner_constraint_lu_solve_attempts=owner_lu_solve_attempts,
                owner_constraint_lu_solve_successes=owner_lu_solve_successes,
                constraint_lu_solve_count_scope=(
                    "owner_authoritative_replicated_report"
                ),
            )
            raise RuntimeError(f"Fixed-H6 modal solve failed: {status}")

        relative, finite = self._final_residual(rhs_norm)
        raw_pass = bool(relative is not None and finite and relative <= self.rtol)
        if self._budget_exhausted:
            status = "budget_exhausted"
        elif reason <= 0:
            status = "ksp_not_converged"
        elif not raw_pass:
            status = "final_residual_failed"
        else:
            status = "converged"
        self._last_solve.update(
            status=status,
            ksp_reason=reason,
            ksp_status="returned",
            iterations=iterations,
            rhs_norm=rhs_norm,
            initial_solution_norm=initial_solution_norm,
            s_h_rtol=self.rtol,
            raw_residual_pass=raw_pass,
            solver_matmult_calls=self._solver_matmult_calls,
            total_matmult_calls=self._total_matmult_calls,
            constraint_lu_factorizations=self._constraint_lu_factorizations_owner,
            local_constraint_lu_factorizations=self._constraint_lu_factorizations_local,
            local_constraint_lu_solve_attempts=self._constraint_lu_solve_attempts,
            local_constraint_lu_solve_successes=self._constraint_lu_solve_successes,
            owner_constraint_lu_solve_attempts=owner_lu_solve_attempts,
            owner_constraint_lu_solve_successes=owner_lu_solve_successes,
            constraint_lu_solve_count_scope="owner_authoritative_replicated_report",
            budget_used_solver_matmult_calls=self._solver_matmult_calls,
            budget_used_total_matmult_calls=self._total_matmult_calls,
        )
        if status != "converged":
            raise RuntimeError(f"Fixed-H6 modal solve did not converge: {status}")
        local_solution = (
            np.asarray(self._solution.getArray(readonly=True), dtype=np.complex128).copy()
            if self._comm.rank == self._modal_owner
            else None
        )
        result = np.asarray(
            self._comm.bcast(local_solution, root=self._modal_owner),
            dtype=np.complex128,
        )
        return result

    @property
    def diagnostics(self) -> dict[str, Any]:
        last_solve = self._last_solve
        modal_action = self._modal_action
        lu_solve_scope = (
            "rank_local_counter; owner aggregate unavailable before a completed solve"
            if last_solve is None
            else last_solve.get(
                "constraint_lu_solve_count_scope",
                "rank_local_attempt/success counters; no owner aggregate recorded",
            )
        )
        return {
            "method": "fixed_h6_modal_gmres_research",
            "operator": "C-PbJbH6bJb^H Tb-PtJtH6tJt^H Tt",
            "operator_fixed_condition": (
                "side adapters, H6 runtime matrices, condensed maps, and modal "
                "coupling remain frozen for the modal solver lifetime"
            ),
            "rtol": self.rtol,
            "restart": self.max_it,
            "max_it": self.max_it,
            "solver_matmult_limit": self.solver_matmult_limit,
            "total_matmult_limit_including_final": self.total_matmult_limit,
            "modal_owner": self._modal_owner,
            "rank": int(self._comm.rank),
            "rank_count": int(self._comm.size),
            "solver_matmult_calls": self._solver_matmult_calls,
            "total_matmult_calls": self._total_matmult_calls,
            "solve_count": self._solve_count,
            "s_evaluation_count": self._cumulative_total_matmult_calls,
            "not_converged_count": self._not_converged_count,
            "cumulative_solver_matmult_calls": (
                self._cumulative_solver_matmult_calls
            ),
            "cumulative_total_matmult_calls": (
                self._cumulative_total_matmult_calls
            ),
            "cumulative_constraint_lu_solve_attempts": (
                self._cumulative_constraint_lu_solve_attempts
            ),
            "cumulative_constraint_lu_solve_successes": (
                self._cumulative_constraint_lu_solve_successes
            ),
            "modal_schur_materialized": False,
            "modal_schur_column_count": 0,
            "modal_schur_condition": "not_measured",
            "modal_constraint_local_bytes": self.modal_constraint_local_bytes,
            "modal_constraint_matvec_calls_total": (
                self._modal_constraint_matvec_calls_at_destroy
                if modal_action is None
                else int(modal_action._modal_constraint_matvec_count)
            ),
            "modal_constraint_matvec_count_scope": (
                "rank-local action counter; do_not_sum_across_ranks"
            ),
            "modal_constraint_condition": float(self.constraint_condition),
            "constraint_lu_factorizations": int(
                self._constraint_lu_factorizations_owner
            ),
            "constraint_lu_owner_rank": int(self._modal_owner),
            "blocked_matmult_attempts": self._blocked_matmult_attempts,
            "local_constraint_lu_factorizations": self._constraint_lu_factorizations_local,
            "owner_constraint_lu_factorizations": self._constraint_lu_factorizations_owner,
            "local_constraint_lu_solve_attempts": self._constraint_lu_solve_attempts,
            "local_constraint_lu_solve_successes": self._constraint_lu_solve_successes,
            "owner_constraint_lu_solve_attempts": (
                None
                if self._last_solve is None
                else self._last_solve.get("owner_constraint_lu_solve_attempts")
            ),
            "owner_constraint_lu_solve_successes": (
                None
                if self._last_solve is None
                else self._last_solve.get("owner_constraint_lu_solve_successes")
            ),
            "constraint_lu_solve_count_scope": lu_solve_scope,
            "constraint_lu_factorizations_scope": "rank_local_and_owner_authoritative",
            "pc_failure": self._pc_failure_error,
            "mat_preflight_failure": self._mat_preflight_failure,
            "budget_exhausted": self._budget_exhausted,
            "last_solve": None if last_solve is None else dict(last_solve),
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        ksp, self._ksp = self._ksp, None
        matrix, self._matrix = self._matrix, None
        for vector_name in ("_residual", "_image", "_solution", "_rhs"):
            vector = getattr(self, vector_name)
            if vector is not None:
                vector.destroy()
                setattr(self, vector_name, None)
        if ksp is not None:
            ksp.destroy()
        if matrix is not None:
            matrix.destroy()
        if self._modal_action is not None:
            self._modal_constraint_matvec_calls_at_destroy = int(
                self._modal_action._modal_constraint_matvec_count
            )
            self._modal_action.destroy()
            self._modal_action = None
        # Side adapters and their FixedH6/layout objects are borrowed.
        self._bottom_action = None
        self._top_action = None
        self._constraint_lu = self._constraint_pivots = None


class _FixedH6ModalGmresResearchBundle:
    """Own one fixed-H6 modal solver and its two borrowed-side adapters."""

    modal_schur = None
    requires_right_fgmres = True

    def __init__(
        self,
        solver: _FixedH6ModalKrylovSystem,
        bottom_action: Any,
        top_action: Any,
    ) -> None:
        self._solver: _FixedH6ModalKrylovSystem | None = solver
        self._side_actions: tuple[Any, Any] = (bottom_action, top_action)
        self.modal_count = int(solver.modal_count)
        self.mode_count = int(solver.mode_count)
        self.modal_constraint_local_bytes = int(solver.modal_constraint_local_bytes)
        self._destroyed = False

    @property
    def modal_constraint(self) -> np.ndarray | None:
        if self._destroyed or self._solver is None:
            return None
        return self._solver.modal_constraint

    @property
    def constraint_condition(self) -> float:
        if self._solver is None:
            return float("nan")
        return float(self._solver.constraint_condition)

    @property
    def diagnostics(self) -> dict[str, Any]:
        solver = {} if self._solver is None else self._solver.diagnostics
        actions = {
            side: dict(action.audit)
            for side, action in zip(
                ("bottom", "top"), self._side_actions, strict=True
            )
        }
        return {
            **solver,
            "method": "fixed_h6_modal_gmres_research",
            "fixed_h6_actions": actions,
            "fixed_h6_action_count_scope": (
                "per-rank replicated; do_not_sum_across_ranks"
            ),
            "fixed_h6_modal_apply_calls": {
                side: int(action["apply_count"])
                for side, action in actions.items()
            },
            "fixed_h6_modal_matrix_mult_calls": {
                side: int(action["matrix_mult_count"])
                for side, action in actions.items()
            },
            "modal_schur_materialized": False,
            "modal_schur_column_count": 0,
            "modal_schur_condition": "not_measured",
            "destroyed": self._destroyed,
        }

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed or self._solver is None:
            raise RuntimeError("Fixed-H6 modal research bundle was destroyed")
        return self._solver.solve(rhs)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        error: Exception | None = None
        # Keep the destroyed solver's bounded scalar diagnostics readable to
        # the caller's existing exception/failure-evidence boundary.
        solver = self._solver
        if solver is not None:
            try:
                solver.destroy()
            except Exception as exc:  # noqa: BLE001 - release owned adapters below
                error = exc
        for action in reversed(self._side_actions):
            try:
                action.destroy()
            except Exception as exc:  # noqa: BLE001 - try both owned adapters
                if error is None:
                    error = exc
        if error is not None:
            raise error


def solve_action_modal_schur_anderson(
    modal_action: HybridActionModalSchurApply,
    rhs: np.ndarray,
    *,
    scale_residual_by_constraint: bool = False,
    real_coordinate_embedding: bool = False,
    max_iterations: int = 8,
    _borrowed_constraint_factor: Any | None = None,
) -> dict[str, Any]:
    """Solve a bounded nonlinear modal equation with PETSc SNESANDERSON.

    The borrowed action is evaluated as ``S(m) - rhs`` on every SNES function
    call.  No fixed Schur Mat or side-action ownership is introduced.  The
    raw function norm is used directly by default: nonzero RHS uses a 1e-2
    relative target, while zero RHS uses a 1e-2 absolute target. The opt-in
    constraint scaling changes the Anderson residual, but convergence is
    still decided from the matching unscaled residual. A caller may lend an
    owner-only C LU; standalone calls continue to factor and release their
    own C LU. The optional real-coordinate embedding represents each complex
    modal value by two real-valued PETSc scalars; its Anderson trajectory is
    a real-coefficient candidate, not the complex-coefficient trajectory.
    """

    if modal_action._destroyed:
        raise RuntimeError("On-demand modal Schur action has been destroyed.")
    modal_count = int(modal_action.modal_count)
    operator = _action_operator(modal_action.bottom_action)
    petsc_comm = operator.getComm()
    comm = petsc_comm.tompi4py()
    root = comm.size - 1

    try:
        rhs_values = np.asarray(rhs, dtype=np.complex128)
        rhs_valid = (
            rhs_values.shape == (modal_count,)
            and bool(np.all(np.isfinite(rhs_values)))
        )
    except (TypeError, ValueError):
        rhs_values = np.empty(0, dtype=np.complex128)
        rhs_valid = False
    if not comm.allreduce(rhs_valid, op=MPI.LAND):
        raise ValueError("Modal Anderson RHS must be a finite modal vector.")
    rhs_hashes = comm.allgather(hashlib.sha256(rhs_values.tobytes()).hexdigest())
    if len(set(rhs_hashes)) != 1:
        raise ValueError("Modal Anderson RHS differs across MPI ranks.")
    rhs_values = rhs_values.copy()
    rhs_norm = float(np.linalg.norm(rhs_values))
    if not np.isfinite(rhs_norm):
        raise ValueError("Modal Anderson RHS norm is non-finite.")
    absolute_tolerance = 1.0e-2 * rhs_norm if rhs_norm != 0.0 else 1.0e-2
    if not isinstance(scale_residual_by_constraint, (bool, np.bool_)):
        raise TypeError("Constraint residual scaling must be an explicit boolean.")
    scale_residual_by_constraint = bool(scale_residual_by_constraint)
    if not isinstance(real_coordinate_embedding, (bool, np.bool_)):
        raise TypeError("Real modal coordinate embedding must be an explicit boolean.")
    real_coordinate_embedding = bool(real_coordinate_embedding)
    if isinstance(max_iterations, (bool, np.bool_)):
        raise TypeError("Modal Anderson max_iterations must be an integer.")
    max_iterations = int(max_iterations)
    if max_iterations < 1:
        raise ValueError("Modal Anderson max_iterations must be positive.")
    coordinate_count = 2 * modal_count if real_coordinate_embedding else modal_count
    coordinate_extra_bytes_per_vec = (
        modal_count * np.dtype(PETSc.ScalarType).itemsize
        if real_coordinate_embedding
        else 0
    )

    options = PETSc.Options()
    option_prefix = "task041_modal_inner_"
    history_option = f"{option_prefix}snes_anderson_m"
    try:
        previous_history_option = options.getString(history_option)
    except KeyError:
        previous_history_option = None

    local_modal_size = coordinate_count if comm.rank == root else 0
    solution = None
    function_value = None
    snes = None
    function_evaluations = 0
    function_callbacks = 0
    convergence_callbacks = 0
    budget_exhausted = False
    budget_callback_skipped = False
    nonfinite_evaluation = False
    raw_cache_iteration_mismatch = False
    real_coordinate_subspace_violation = False
    callback_target_reached = False
    callback_reason = int(PETSc.SNES.ConvergedReason.ITERATING)
    last_snes_function_norm = None
    final_evaluations = 0
    residual_history: list[dict[str, Any]] = []
    latest_raw_cache: dict[str, Any] = {
        "iterate": None,
        "residual": None,
        "raw_norm": None,
        "raw_metric": None,
        "scaled_norm": None,
        "finite": False,
    }
    constraint_lu = None
    constraint_pivots = None
    constraint_condition_number = None
    constraint_lu_factorizations = 0
    constraint_lu_solve_calls = 0
    actions = {
        "bottom": modal_action.bottom_action,
        "top": modal_action.top_action,
    }
    action_counts_before = {
        side: _action_apply_count(action) for side, action in actions.items()
    }

    def scale_raw_residual(raw_residual: np.ndarray) -> np.ndarray:
        nonlocal constraint_lu_solve_calls
        if not scale_residual_by_constraint:
            return np.asarray(raw_residual, dtype=np.complex128).copy()
        owner_result = None
        if comm.rank == root:
            try:
                scaled = lu_solve(
                    (constraint_lu, constraint_pivots),
                    np.asarray(raw_residual, dtype=np.complex128),
                    check_finite=True,
                )
                if not bool(np.all(np.isfinite(scaled))):
                    owner_result = (False, None, "C solve produced non-finite values")
                else:
                    owner_result = (
                        True,
                        np.asarray(scaled, dtype=np.complex128),
                        None,
                    )
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                owner_result = (
                    False,
                    None,
                    f"C solve failed: {type(exc).__name__}: {exc}",
                )
        success, scaled_values, error = comm.bcast(owner_result, root=root)
        if not success:
            if error == "C solve produced non-finite values":
                return np.full(modal_count, np.nan, dtype=np.complex128)
            raise RuntimeError(str(error))
        constraint_lu_solve_calls += 1
        return np.asarray(scaled_values, dtype=np.complex128)

    def decode_coordinates(coordinate_values: np.ndarray) -> np.ndarray:
        nonlocal real_coordinate_subspace_violation
        if not real_coordinate_embedding:
            return np.asarray(coordinate_values, dtype=np.complex128)
        # The coordinate vector is owner-read and broadcast by
        # _replicated_modal_values, so every rank checks the same values.
        if not bool(np.all(coordinate_values.imag == 0.0)):
            real_coordinate_subspace_violation = True
        return _decode_modal_real_coordinates(coordinate_values, modal_count)

    try:
        if scale_residual_by_constraint and _borrowed_constraint_factor is not None:
            factor = _borrowed_constraint_factor
            local_factor_valid = bool(
                getattr(factor, "modal_action", None) is modal_action
                and int(getattr(factor, "modal_count", -1)) == modal_count
                and int(getattr(factor, "constraint_lu_owner_rank", -1)) == root
                and np.isfinite(float(getattr(factor, "constraint_condition", np.nan)))
            )
            factor_lu = getattr(factor, "constraint_lu", None)
            factor_pivots = getattr(factor, "constraint_pivots", None)
            if comm.rank == root:
                local_factor_valid = bool(
                    local_factor_valid
                    and isinstance(factor_lu, np.ndarray)
                    and factor_lu.shape == (modal_count, modal_count)
                    and isinstance(factor_pivots, np.ndarray)
                    and factor_pivots.shape == (modal_count,)
                )
            else:
                local_factor_valid = bool(
                    local_factor_valid and factor_lu is None and factor_pivots is None
                )
            if not comm.allreduce(local_factor_valid, op=MPI.LAND):
                raise ValueError("Borrowed C LU must be valid only on the modal owner.")
            constraint_lu = factor_lu
            constraint_pivots = factor_pivots
            constraint_condition_number = float(factor.constraint_condition)
        elif scale_residual_by_constraint:
            owner_factor_result = None
            if comm.rank == root:
                try:
                    lu, pivots, condition = _factor_modal_constraint(
                        modal_action.modal_constraint, modal_count
                    )
                    constraint_lu = lu
                    constraint_pivots = pivots
                    constraint_condition_number = condition
                    owner_factor_result = (True, condition, None)
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    owner_factor_result = (
                        False,
                        None,
                        f"C factorization rejected: {type(exc).__name__}: {exc}",
                    )
            factor_ok, factor_condition, factor_error = comm.bcast(
                owner_factor_result, root=root
            )
            if not factor_ok:
                raise RuntimeError(str(factor_error))
            constraint_condition_number = float(factor_condition)
            constraint_lu_factorizations = 1
        elif _borrowed_constraint_factor is not None:
            raise ValueError("A borrowed C LU requires constraint residual scaling.")

        solution = PETSc.Vec().createMPI(
            (local_modal_size, coordinate_count), comm=petsc_comm
        )
        function_value = solution.duplicate()
        snes = PETSc.SNES().create(comm=petsc_comm)
        solution.set(PETSc.ScalarType(0.0))

        def function(_snes, modal_vector, residual_vector) -> None:
            nonlocal function_evaluations, function_callbacks
            nonlocal budget_callback_skipped
            nonlocal nonfinite_evaluation
            function_callbacks += 1
            if function_evaluations >= _MODAL_ANDERSON_S_EVALUATION_LIMIT - 1:
                budget_callback_skipped = True
                return
            coordinate_values = _replicated_modal_values(modal_vector)
            modal_values = decode_coordinates(coordinate_values)
            if real_coordinate_subspace_violation:
                latest_raw_cache.update(
                    iterate=coordinate_values.copy(),
                    residual=None,
                    raw_norm=None,
                    raw_metric=None,
                    scaled_norm=None,
                    finite=False,
                )
                residual_history.append(
                    {
                        "evaluation": function_evaluations,
                        "source": "real_coordinate_subspace_violation",
                        "raw_residual_norm": None,
                        "raw_target_metric": None,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )
                residual_vector.set(PETSc.ScalarType(np.nan))
                return
            raw_residual = np.asarray(
                modal_action.apply(modal_values) - rhs_values,
                dtype=np.complex128,
            )
            function_evaluations += 1
            local_finite = raw_residual.shape == (modal_count,) and bool(
                np.all(np.isfinite(raw_residual))
            )
            globally_finite = comm.allreduce(local_finite, op=MPI.LAND)
            if not globally_finite:
                nonfinite_evaluation = True
                latest_raw_cache.update(
                    iterate=coordinate_values.copy(),
                    residual=None,
                    raw_norm=None,
                    raw_metric=None,
                    scaled_norm=None,
                    finite=False,
                )
                residual_history.append(
                    {
                        "evaluation": function_evaluations,
                        "source": "snes_function",
                        "raw_residual_norm": None,
                        "raw_target_metric": None,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )
                residual_vector.set(PETSc.ScalarType(np.nan))
                return
            raw_norm = float(np.linalg.norm(raw_residual))
            raw_metric = raw_norm / rhs_norm if rhs_norm != 0.0 else raw_norm
            scaled_residual = scale_raw_residual(raw_residual)
            if not bool(np.all(np.isfinite(scaled_residual))):
                nonfinite_evaluation = True
                latest_raw_cache.update(
                    iterate=coordinate_values.copy(),
                    residual=raw_residual.copy(),
                    raw_norm=raw_norm,
                    raw_metric=raw_metric,
                    scaled_norm=None,
                    finite=False,
                )
                residual_history.append(
                    {
                        "evaluation": function_evaluations,
                        "source": "snes_function",
                        "raw_residual_norm": raw_norm,
                        "raw_target_metric": raw_metric,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )
                residual_vector.set(PETSc.ScalarType(np.nan))
                return
            scaled_norm = float(np.linalg.norm(scaled_residual))
            solver_residual = (
                _encode_modal_real_coordinates(scaled_residual)
                if real_coordinate_embedding
                else scaled_residual
            )
            latest_raw_cache.update(
                iterate=coordinate_values.copy(),
                residual=raw_residual.copy(),
                raw_norm=raw_norm,
                raw_metric=raw_metric,
                scaled_norm=scaled_norm,
                finite=True,
            )
            residual_history.append(
                {
                    "evaluation": function_evaluations,
                    "source": "snes_function",
                    "raw_residual_norm": raw_norm,
                    "raw_target_metric": raw_metric,
                    "scaled_residual_norm": scaled_norm,
                    "finite": True,
                }
            )
            _set_owned_values(residual_vector, solver_residual)

        def convergence_test(_snes, iteration, norms):
            nonlocal convergence_callbacks, callback_target_reached
            nonlocal callback_reason, last_snes_function_norm
            nonlocal raw_cache_iteration_mismatch, budget_exhausted
            convergence_callbacks += 1
            _xnorm, _ynorm, fnorm = norms
            last_snes_function_norm = float(fnorm)
            if nonfinite_evaluation:
                reason = PETSc.SNES.ConvergedReason.DIVERGED_FNORM_NAN
            elif real_coordinate_subspace_violation:
                reason = PETSc.SNES.ConvergedReason.DIVERGED_FUNCTION_DOMAIN
            elif budget_callback_skipped:
                reason = PETSc.SNES.ConvergedReason.DIVERGED_FUNCTION_COUNT
            elif not latest_raw_cache["finite"]:
                raw_cache_iteration_mismatch = True
                reason = PETSc.SNES.ConvergedReason.DIVERGED_INNER
            else:
                current_solution = _snes.getSolution()
                try:
                    current_values = _replicated_modal_values(current_solution)
                finally:
                    current_solution.destroy()
                cached_values = latest_raw_cache["iterate"]
                if not np.array_equal(current_values, cached_values):
                    raw_cache_iteration_mismatch = True
                    reason = PETSc.SNES.ConvergedReason.DIVERGED_INNER
                elif float(latest_raw_cache["raw_metric"]) <= 1.0e-2:
                    callback_target_reached = True
                    reason = PETSc.SNES.ConvergedReason.CONVERGED_FNORM_ABS
                elif (
                    function_evaluations
                    >= _MODAL_ANDERSON_S_EVALUATION_LIMIT - 1
                ):
                    budget_exhausted = True
                    reason = PETSc.SNES.ConvergedReason.DIVERGED_FUNCTION_COUNT
                elif int(iteration) >= max_iterations:
                    reason = PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT
                else:
                    reason = PETSc.SNES.ConvergedReason.ITERATING
            callback_reason = int(reason)
            return reason

        snes.setOptionsPrefix(option_prefix)
        snes.setType(PETSc.SNES.Type.ANDERSON)
        options.setValue(history_option, "4")
        snes.setFromOptions()
        if str(snes.getType()) != str(PETSc.SNES.Type.ANDERSON):
            raise RuntimeError("PETSc changed the requested SNESANDERSON type.")
        snes.setFunction(function, function_value)
        snes.setTolerances(
            rtol=0.0,
            atol=absolute_tolerance,
            stol=0.0,
            max_it=max_iterations,
        )
        snes.setConvergenceTest(convergence_test)
        # Reserve one of the sixteen allowed S evaluations for an independent
        # raw-residual check after SNES returns.
        snes.setMaxFunctionEvaluations(_MODAL_ANDERSON_S_EVALUATION_LIMIT)
        snes.solve(None, solution)

        iterations = int(snes.getIterationNumber())
        snes_reason = int(snes.getConvergedReason())
        coordinate_values = _replicated_modal_values(solution)
        modal_values = decode_coordinates(coordinate_values)
        residual_norm = float("inf")
        target_value = float("inf")
        final_target_reached = False
        final_scaled_norm = float("inf")
        if (
            not nonfinite_evaluation
            and not real_coordinate_subspace_violation
            and bool(np.all(np.isfinite(modal_values)))
        ):
            final_residual = np.asarray(
                modal_action.apply(modal_values) - rhs_values,
                dtype=np.complex128,
            )
            final_evaluations = 1
            local_finite = final_residual.shape == (modal_count,) and bool(
                np.all(np.isfinite(final_residual))
            )
            globally_finite = comm.allreduce(local_finite, op=MPI.LAND)
            if globally_finite:
                residual_norm = float(np.linalg.norm(final_residual))
                if np.isfinite(residual_norm):
                    target_value = (
                        residual_norm / rhs_norm
                        if rhs_norm != 0.0
                        else residual_norm
                    )
                    final_scaled_residual = scale_raw_residual(final_residual)
                    if bool(np.all(np.isfinite(final_scaled_residual))):
                        final_solver_residual = (
                            _encode_modal_real_coordinates(final_scaled_residual)
                            if real_coordinate_embedding
                            else final_scaled_residual
                        )
                        final_scaled_norm = float(
                            np.linalg.norm(final_solver_residual)
                        )
                        final_target_reached = target_value <= 1.0e-2
                        residual_history.append(
                            {
                                "evaluation": function_evaluations + final_evaluations,
                                "source": "final_validation",
                                "raw_residual_norm": residual_norm,
                                "raw_target_metric": target_value,
                                "scaled_residual_norm": final_scaled_norm,
                                "finite": True,
                            }
                        )
                    else:
                        nonfinite_evaluation = True
                        residual_history.append(
                            {
                                "evaluation": function_evaluations + final_evaluations,
                                "source": "final_validation",
                                "raw_residual_norm": residual_norm,
                                "raw_target_metric": target_value,
                                "scaled_residual_norm": None,
                                "finite": False,
                            }
                        )
                else:
                    nonfinite_evaluation = True
                    residual_history.append(
                        {
                            "evaluation": function_evaluations + final_evaluations,
                            "source": "final_validation",
                            "raw_residual_norm": None,
                            "raw_target_metric": None,
                            "scaled_residual_norm": None,
                            "finite": False,
                        }
                    )
            else:
                nonfinite_evaluation = True
                residual_history.append(
                    {
                        "evaluation": function_evaluations + final_evaluations,
                        "source": "final_validation",
                        "raw_residual_norm": None,
                        "raw_target_metric": None,
                        "scaled_residual_norm": None,
                        "finite": False,
                    }
                )

        total_evaluations = function_evaluations + final_evaluations
        if total_evaluations > _MODAL_ANDERSON_S_EVALUATION_LIMIT:
            raise RuntimeError("Modal Anderson exceeded its S-evaluation budget.")
        if (
            callback_target_reached
            and final_target_reached
            and not nonfinite_evaluation
            and not budget_exhausted
            and not budget_callback_skipped
            and not raw_cache_iteration_mismatch
            and not real_coordinate_subspace_violation
            and snes_reason > 0
        ):
            status = "converged"
            stop_reason = "unscaled_residual_target"
        else:
            status = "not_converged"
            if budget_exhausted or budget_callback_skipped:
                stop_reason = "budget_exhausted"
            elif nonfinite_evaluation:
                stop_reason = "nonfinite_residual"
            elif raw_cache_iteration_mismatch:
                stop_reason = "raw_cache_iteration_mismatch"
            elif real_coordinate_subspace_violation:
                stop_reason = "real_coordinate_subspace_violation"
            elif snes_reason == int(PETSc.SNES.ConvergedReason.DIVERGED_MAX_IT):
                stop_reason = "max_iterations"
            elif function_evaluations >= _MODAL_ANDERSON_S_EVALUATION_LIMIT - 1:
                stop_reason = "function_evaluation_budget"
            else:
                stop_reason = "snes_nonconvergence"

        side_action_calls = {}
        for side, action in actions.items():
            before = action_counts_before[side]
            after = _action_apply_count(action)
            delta = None if before is None or after is None else after - before
            if delta is not None and delta < 0:
                delta = None
            rank_deltas = comm.allgather(delta)
            side_action_calls[side] = (
                int(delta)
                if delta is not None and all(value == delta for value in rank_deltas)
                else None
            )
        rank_state = (
            function_evaluations,
            function_callbacks,
            convergence_callbacks,
            final_evaluations,
            iterations,
            status,
            stop_reason,
            float(residual_norm),
            float(target_value),
            total_evaluations,
            constraint_lu_solve_calls,
            real_coordinate_embedding,
            real_coordinate_subspace_violation,
            tuple(sorted(side_action_calls.items())),
        )
        if any(value != rank_state for value in comm.allgather(rank_state)):
            raise RuntimeError("Modal Anderson control flow differs across MPI ranks.")
        return {
            "status": status,
            "stop_reason": stop_reason,
            "mixing_method": "petsc_snes_anderson_default",
            "solution": modal_values.copy(),
            "target_reached": bool(callback_target_reached and final_target_reached),
            "convergence_callback_target_reached": bool(callback_target_reached),
            "final_unscaled_target_reached": bool(final_target_reached),
            "unscaled_residual_norm": residual_norm,
            "rhs_norm": rhs_norm,
            "relative_residual": target_value,
            "scaled_residual_norm": final_scaled_norm,
            "last_snes_function_norm": last_snes_function_norm,
            "residual_evaluation_history": residual_history,
            "constraint_scale_enabled": scale_residual_by_constraint,
            "real_coordinate_embedding": real_coordinate_embedding,
            "modal_coordinate_representation": (
                "real_parts_then_imag_parts_in_complex128"
                if real_coordinate_embedding
                else "complex128_modal_values"
            ),
            "modal_coordinate_count": coordinate_count,
            "modal_coordinate_extra_bytes_per_explicit_vec": int(
                coordinate_extra_bytes_per_vec
            ),
            "modal_coordinate_extra_bytes_two_explicit_vecs": int(
                2 * coordinate_extra_bytes_per_vec
            ),
            "real_coordinate_subspace_violation": bool(
                real_coordinate_subspace_violation
            ),
            "constraint_condition_2": constraint_condition_number,
            "constraint_lu_owner_rank": root if scale_residual_by_constraint else None,
            "constraint_lu_factorizations": constraint_lu_factorizations,
            "constraint_lu_solve_calls": constraint_lu_solve_calls,
            "constraint_lu_borrowed": _borrowed_constraint_factor is not None,
            "zero_rhs_absolute_residual": rhs_norm == 0.0,
            "iterations": iterations,
            "function_evaluations": function_evaluations,
            "function_callbacks": function_callbacks,
            "convergence_callbacks": convergence_callbacks,
            "final_validation_evaluations": final_evaluations,
            "s_evaluation_count": total_evaluations,
            "s_evaluation_limit": _MODAL_ANDERSON_S_EVALUATION_LIMIT,
            "snes_function_evaluation_limit": _MODAL_ANDERSON_S_EVALUATION_LIMIT,
            "budget_callback_skipped": bool(budget_callback_skipped),
            "budget_callback_residual_state": (
                "not_evaluated" if budget_callback_skipped else None
            ),
            "budget_reason": (
                "DIVERGED_FUNCTION_COUNT"
                if budget_exhausted or budget_callback_skipped
                else None
            ),
            "budget_exhausted": bool(budget_exhausted),
            "anderson_history": 4,
            "max_iterations": max_iterations,
            "snes_converged_reason": snes_reason,
            "callback_converged_reason": callback_reason,
            "raw_cache_iteration_mismatch": bool(raw_cache_iteration_mismatch),
            "side_action_calls": side_action_calls,
        }
    finally:
        if snes is not None:
            snes.destroy()
        if function_value is not None:
            function_value.destroy()
        if solution is not None:
            solution.destroy()
        options.delValue(history_option)
        if previous_history_option is not None:
            options.setValue(history_option, previous_history_option)
        constraint_lu = None
        constraint_pivots = None


def solve_action_modal_schur_anderson_complex_qr_research(
    modal_action: HybridActionModalSchurApply,
    rhs: np.ndarray,
    *,
    _borrowed_constraint_factor: Any,
    raw_metric_mixing: bool = False,
    _capture_trace_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded full-S complex QR path with an optional raw gamma metric."""

    if modal_action._destroyed:
        raise RuntimeError("On-demand modal Schur action has been destroyed.")
    modal_count = int(modal_action.modal_count)
    comm = _action_operator(modal_action.bottom_action).getComm().tompi4py()
    root = comm.size - 1
    max_iterations, history_limit = 14, 4
    evaluation_limit = _MODAL_ANDERSON_S_EVALUATION_LIMIT
    beta = 1.0
    if not isinstance(raw_metric_mixing, (bool, np.bool_)):
        raise TypeError("Raw-metric Anderson selection must be an explicit boolean.")
    mixing_metric = "raw_residual" if raw_metric_mixing else "C_scaled_residual"
    rhs_values = np.asarray(rhs, dtype=np.complex128)
    rhs_valid = rhs_values.shape == (modal_count,) and bool(np.all(np.isfinite(rhs_values)))
    if not comm.allreduce(rhs_valid, op=MPI.LAND):
        raise ValueError("Modal Anderson RHS must be a finite modal vector.")
    rhs_hashes = comm.allgather(hashlib.sha256(rhs_values.tobytes()).hexdigest())
    if len(set(rhs_hashes)) != 1:
        raise ValueError("Modal Anderson RHS differs across MPI ranks.")
    rhs_values = rhs_values.copy()
    if _capture_trace_record is not None:
        _capture_trace_record["rhs_sha256"] = rhs_hashes[root]
        _capture_trace_record["g"] = _capture_modal_array(
            _capture_trace_record, "g", rhs_values
        )
    with np.errstate(over="ignore", invalid="ignore"):
        rhs_norm = float(np.linalg.norm(rhs_values))
    if not comm.allreduce(bool(np.isfinite(rhs_norm)), op=MPI.LAND):
        raise ValueError("Modal Anderson RHS norm is non-finite.")

    factor = _borrowed_constraint_factor
    factor_lu = getattr(factor, "constraint_lu", None)
    factor_pivots = getattr(factor, "constraint_pivots", None)
    factor_valid = bool(
        getattr(factor, "modal_action", None) is modal_action
        and int(getattr(factor, "modal_count", -1)) == modal_count
        and int(getattr(factor, "constraint_lu_owner_rank", -1)) == root
        and np.isfinite(float(getattr(factor, "constraint_condition", np.nan)))
    )
    if comm.rank == root:
        factor_valid = bool(
            factor_valid
            and isinstance(factor_lu, np.ndarray)
            and factor_lu.shape == (modal_count, modal_count)
            and isinstance(factor_pivots, np.ndarray)
            and factor_pivots.shape == (modal_count,)
        )
    else:
        factor_valid = bool(factor_valid and factor_lu is None and factor_pivots is None)
    if not comm.allreduce(factor_valid, op=MPI.LAND):
        raise ValueError("Borrowed C LU must be valid only on the modal owner.")

    actions = {"bottom": modal_action.bottom_action, "top": modal_action.top_action}
    counts_before = {side: _action_apply_count(action) for side, action in actions.items()}
    residual_history: list[dict[str, Any]] = []
    if _capture_trace_record is not None and comm.rank == root:
        _capture_trace_record["evaluations"] = residual_history
    mixing_history: list[dict[str, Any]] = []
    owner_states: list[tuple[np.ndarray, np.ndarray]] = []
    owner_raw_residuals: list[np.ndarray] = []
    modal_values = np.zeros(modal_count, dtype=np.complex128)
    function_evaluations = total_evaluations = c_solves = iterations = 0
    final_evaluations = 0
    callback_target = final_target = evaluation_failed = False
    budget_exhausted = False
    stop_reason = "max_iterations"
    last_raw_norm = last_raw_metric = last_scaled_norm = float("inf")

    def evaluate(current: np.ndarray, source: str):
        nonlocal function_evaluations, total_evaluations, c_solves
        capture_evaluation = None
        if _capture_trace_record is not None and comm.rank == root:
            capture_evaluation = {
                "evaluation": total_evaluations + 1,
                "source": source,
                "finite": False,
            }
            residual_history.append(capture_evaluation)
            if len(residual_history) <= evaluation_limit:
                capture_evaluation["m"] = _capture_modal_array(
                    _capture_trace_record, "m", current
                )
            else:
                _capture_trace_record["capture_incomplete_reason"] = (
                    "evaluation_count_exceeded_capture_limit"
                )
        action_values = modal_action.apply(current)
        raw = np.asarray(action_values - rhs_values, dtype=np.complex128)
        total_evaluations += 1
        if source == "complex_qr_iteration":
            function_evaluations += 1
        if capture_evaluation is not None and comm.rank == root:
            capture_evaluation["side_actions"] = {
                side: _modal_trace_side_apply_record(action)
                for side, action in actions.items()
            }
            capture_evaluation["raw"] = _capture_modal_array(
                _capture_trace_record, "raw", raw
            )
        finite = raw.shape == (modal_count,) and bool(np.all(np.isfinite(raw)))
        finite = bool(comm.allreduce(finite, op=MPI.LAND))
        payload = None
        if comm.rank == root:
            if not finite:
                payload = (False, None, "nonfinite_residual")
            else:
                try:
                    raw_norm = float(np.linalg.norm(raw))
                    raw_metric = raw_norm / rhs_norm if rhs_norm else raw_norm
                    scaled = lu_solve((factor_lu, factor_pivots), raw, check_finite=True)
                    if capture_evaluation is not None:
                        capture_evaluation["scaled"] = _capture_modal_array(
                            _capture_trace_record,
                            "scaled",
                            np.asarray(scaled, dtype=np.complex128),
                        )
                    fixed_point = -np.asarray(scaled, dtype=np.complex128)
                    scaled_norm = float(np.linalg.norm(scaled))
                    if (
                        not np.isfinite(raw_norm)
                        or not np.isfinite(raw_metric)
                        or not np.isfinite(scaled_norm)
                        or not np.all(np.isfinite(fixed_point))
                    ):
                        payload = (False, None, "nonfinite_residual")
                    else:
                        payload = (
                            True,
                            (raw_norm, raw_metric, scaled_norm, fixed_point),
                            None,
                        )
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    payload = (False, None, f"constraint_solve_failure: {exc}")
        success, values, error = comm.bcast(payload, root=root)
        if not success:
            if capture_evaluation is not None:
                row = capture_evaluation
                row.update(finite=False, capture_complete=False)
                _capture_trace_record["capture_incomplete_reason"] = (
                    "residual_evaluation_failed"
                )
            else:
                row = {
                    "evaluation": total_evaluations,
                    "source": source,
                    "raw_residual_norm": None,
                    "raw_target_metric": None,
                    "scaled_residual_norm": None,
                    "finite": False,
                }
                residual_history.append(row)
            return None, row, error, None
        c_solves += 1
        raw_norm, raw_metric, scaled_norm, fixed_point = values
        if capture_evaluation is None:
            row = {
                "evaluation": total_evaluations,
                "source": source,
                "raw_residual_norm": float(raw_norm),
                "raw_target_metric": float(raw_metric),
                "scaled_residual_norm": float(scaled_norm),
                "finite": True,
            }
            residual_history.append(row)
        else:
            row = capture_evaluation
            row.update(
                {
                    "raw_residual_norm": float(raw_norm),
                    "raw_target_metric": float(raw_metric),
                    "scaled_residual_norm": float(scaled_norm),
                    "finite": True,
                    "capture_complete": all(
                        row.get(key) is not None for key in ("m", "raw", "scaled")
                    ),
                }
            )
            if not row["capture_complete"]:
                _capture_trace_record["capture_incomplete_reason"] = (
                    "evaluation_vector_not_captured"
                )
        return (
            np.asarray(fixed_point, dtype=np.complex128),
            row,
            None,
            raw if raw_metric_mixing and comm.rank == root else None,
        )

    for _ in range(max_iterations + 1):
        if total_evaluations >= evaluation_limit - 1:
            budget_exhausted = True
            stop_reason = "budget_exhausted"
            break
        fixed_point, row, error, raw_residual = evaluate(
            modal_values, "complex_qr_iteration"
        )
        if error is not None:
            evaluation_failed = True
            stop_reason = error.split(":", 1)[0]
            break
        last_raw_norm = row["raw_residual_norm"]
        last_raw_metric = row["raw_target_metric"]
        last_scaled_norm = row["scaled_residual_norm"]
        if last_raw_metric <= 1.0e-2:
            callback_target = True
            stop_reason = "unscaled_residual_target"
            break
        if iterations == max_iterations:
            stop_reason = "max_iterations"
            break

        update_payload = None
        if comm.rank == root:
            owner_states.append((modal_values.copy(), fixed_point.copy()))
            if len(owner_states) > history_limit + 1:
                del owner_states[0]
            if raw_metric_mixing:
                if len(owner_raw_residuals) >= history_limit + 1:
                    del owner_raw_residuals[0]
                owner_raw_residuals.append(raw_residual)
            delta_m = delta_f = None
            delta_raw_residual = None
            if len(owner_states) > 1:
                delta_m = np.column_stack(
                    [owner_states[i + 1][0] - owner_states[i][0] for i in range(len(owner_states) - 1)]
                )
                delta_f = np.column_stack(
                    [owner_states[i + 1][1] - owner_states[i][1] for i in range(len(owner_states) - 1)]
                )
                if raw_metric_mixing:
                    delta_raw_residual = np.column_stack(
                        [
                            owner_raw_residuals[i + 1] - owner_raw_residuals[i]
                            for i in range(len(owner_raw_residuals) - 1)
                        ]
                    )
            try:
                candidate, mix = _complex_anderson_candidate_update(
                    modal_values,
                    fixed_point,
                    delta_m,
                    delta_f,
                    capture_coefficients=_capture_trace_record is not None,
                    mixing_metric=mixing_metric,
                    raw_residual=raw_residual if raw_metric_mixing else None,
                    delta_raw_residual=delta_raw_residual,
                )
                gamma = mix.pop("_capture_gamma", None)
                if _capture_trace_record is not None:
                    update_capture = {
                        "update_index": iterations + 1,
                        "source_evaluation_index": total_evaluations,
                        "candidate_accepted": candidate is not None,
                        "mixing_scalars": dict(mix),
                    }
                    if isinstance(gamma, np.ndarray):
                        update_capture["gamma"] = _capture_modal_array(
                            _capture_trace_record, "gamma", gamma
                        )
                    else:
                        update_capture["gamma"] = None
                        update_capture["gamma_status"] = "not_applicable_startup"
                    _capture_trace_record["updates"].append(update_capture)
                update_payload = (candidate is not None, candidate, mix, None)
            except (FloatingPointError, ValueError, np.linalg.LinAlgError) as exc:
                if _capture_trace_record is not None:
                    _capture_trace_record["updates"].append(
                        {
                            "update_index": iterations + 1,
                            "source_evaluation_index": total_evaluations,
                            "candidate_accepted": False,
                            "mixing_scalars": {},
                            "gamma": None,
                        }
                    )
                    _capture_trace_record["capture_incomplete_reason"] = (
                        "anderson_update_failed"
                    )
                update_payload = (False, None, {}, str(exc))
        update_ok, candidate, mix, update_error = comm.bcast(update_payload, root=root)
        mixing_history.append(dict(mix))
        if not update_ok:
            stop_reason = (
                "rank_zero_history"
                if mix.get("update") == "rank_zero_history"
                else "invalid_anderson_update"
            )
            if update_error:
                stop_reason = "nonfinite_or_invalid_anderson_update"
            break
        modal_values = np.asarray(candidate, dtype=np.complex128)
        iterations += 1

    if not evaluation_failed and bool(np.all(np.isfinite(modal_values))):
        _final_fixed_point, final_row, error, _final_raw_residual = evaluate(
            modal_values, "final_validation"
        )
        final_evaluations = 1
        if error is None:
            last_raw_norm = final_row["raw_residual_norm"]
            last_raw_metric = final_row["raw_target_metric"]
            last_scaled_norm = final_row["scaled_residual_norm"]
            final_target = last_raw_metric <= 1.0e-2
        else:
            evaluation_failed = True
            stop_reason = "final_validation_failure"

    if total_evaluations > evaluation_limit:
        raise RuntimeError("Complex modal Anderson exceeded its S-evaluation budget.")
    status = (
        "converged"
        if callback_target and final_target and not evaluation_failed
        and not budget_exhausted
        and stop_reason == "unscaled_residual_target"
        else "not_converged"
    )
    if status != "converged" and callback_target and final_evaluations:
        stop_reason = "final_validation_failed"

    side_calls = {}
    for side, action in actions.items():
        before, after = counts_before[side], _action_apply_count(action)
        delta = None if before is None or after is None else after - before
        rank_deltas = comm.allgather(delta if delta is not None and delta >= 0 else None)
        side_calls[side] = int(delta) if delta is not None and all(x == delta for x in rank_deltas) else None
    rank_state = (
        function_evaluations,
        total_evaluations,
        c_solves,
        iterations,
        status,
        stop_reason,
        budget_exhausted,
        last_raw_metric,
        tuple(sorted(side_calls.items())),
    )
    if any(item != rank_state for item in comm.allgather(rank_state)):
        raise RuntimeError("Complex modal Anderson control flow differs across MPI ranks.")

    if _capture_trace_record is not None and comm.rank == root:
        evaluations = _capture_trace_record.get("evaluations", [])
        capture_complete = bool(
            _capture_trace_record.get("g") is not None
            and len(evaluations) == total_evaluations
            and total_evaluations <= evaluation_limit
            and all(row.get("capture_complete") is True for row in evaluations)
            and not _capture_trace_record.get("capture_incomplete_reason")
        )
        _capture_trace_record.update(
            solver_status=status,
            solver_stop_reason=stop_reason,
            s_evaluation_count=total_evaluations,
            anderson_iterations=iterations,
            capture_complete=capture_complete,
        )
        if not capture_complete:
            _capture_trace_record.setdefault(
                "capture_incomplete_reason", "evaluation_trace_incomplete"
            )

    return {
        "status": status,
        "stop_reason": stop_reason,
        "solution": modal_values.copy(),
        "target_reached": bool(callback_target and final_target),
        "convergence_callback_target_reached": bool(callback_target),
        "final_unscaled_target_reached": bool(final_target),
        "invalid_failure": bool(evaluation_failed),
        "unscaled_residual_norm": last_raw_norm,
        "rhs_norm": rhs_norm,
        "relative_residual": last_raw_metric,
        "scaled_residual_norm": last_scaled_norm,
        "last_snes_function_norm": None,
        "residual_evaluation_history": residual_history,
        "complex_qr_mixing_history": mixing_history,
        "mixing_method": "complex_qr_type_ii_research",
        "mixing_metric": mixing_metric,
        "mixing_beta": beta,
        "constraint_scale_enabled": True,
        "real_coordinate_embedding": False,
        "modal_coordinate_representation": "complex128_modal_values",
        "modal_coordinate_count": modal_count,
        "modal_coordinate_extra_bytes_per_explicit_vec": 0,
        "modal_coordinate_extra_bytes_two_explicit_vecs": 0,
        "real_coordinate_subspace_violation": False,
        "constraint_condition_2": float(factor.constraint_condition),
        "constraint_lu_owner_rank": root,
        "constraint_lu_factorizations": 0,
        "constraint_lu_solve_calls": c_solves,
        "constraint_lu_borrowed": True,
        "zero_rhs_absolute_residual": rhs_norm == 0.0,
        "iterations": iterations,
        "max_iterations": max_iterations,
        "function_evaluations": function_evaluations,
        "s_evaluation_count": total_evaluations,
        "s_evaluation_limit": evaluation_limit,
        "final_validation_evaluations": final_evaluations,
        "budget_callback_skipped": False,
        "budget_callback_residual_state": None,
        "budget_reason": "S_EVALUATION_LIMIT" if budget_exhausted else None,
        "budget_exhausted": budget_exhausted,
        "anderson_history": history_limit,
        "snes_converged_reason": None,
        "callback_converged_reason": None,
        "raw_cache_iteration_mismatch": False,
        "side_action_calls": side_calls,
    }


class HybridActionModalSchurAndersonSystem:
    """Owner-factored C scaling for a borrowed nonlinear modal action."""

    def __init__(
        self,
        modal_action: HybridActionModalSchurApply,
        *,
        modal_owner: int,
        complex_qr_research: bool = False,
        raw_metric_mixing: bool = False,
        capture_modal_solve_trace: bool = False,
    ) -> None:
        if not isinstance(complex_qr_research, (bool, np.bool_)):
            raise TypeError("Complex QR research selection must be an explicit boolean.")
        if not isinstance(capture_modal_solve_trace, (bool, np.bool_)):
            raise TypeError("Modal solve trace capture must be an explicit boolean.")
        if not isinstance(raw_metric_mixing, (bool, np.bool_)):
            raise TypeError("Raw-metric Anderson selection must be an explicit boolean.")
        if raw_metric_mixing and not complex_qr_research:
            raise ValueError("Raw-metric mixing requires the complex QR research path.")
        if capture_modal_solve_trace and not complex_qr_research:
            raise ValueError(
                "Modal solve trace capture requires the complex QR research path."
            )
        self.modal_action = modal_action
        self.modal_count = int(modal_action.modal_count)
        self.complex_qr_research = bool(complex_qr_research)
        self.raw_metric_mixing = bool(raw_metric_mixing)
        self.capture_modal_solve_trace = bool(capture_modal_solve_trace)
        self.mixing_method = (
            "complex_qr_type_ii_research"
            if self.complex_qr_research
            else "petsc_snes_anderson_default"
        )
        self.mixing_metric = (
            "raw_residual" if self.raw_metric_mixing else "C_scaled_residual"
        )
        self.modal_schur = None
        self.constraint_lu_owner_rank = int(modal_owner)
        self.constraint_lu: np.ndarray | None = None
        self.constraint_pivots: np.ndarray | None = None
        self.constraint_condition = float("nan")
        self.modal_constraint_local_bytes = int(
            modal_action.modal_constraint.nbytes
        )
        self._destroyed = False
        self._solve_count = 0
        self._s_evaluation_count = 0
        self._anderson_iteration_count = 0
        self._constraint_lu_solve_calls = 0
        self._not_converged_count = 0
        self._side_action_call_count = {"bottom": 0, "top": 0}
        self._side_action_call_count_known = {"bottom": True, "top": True}
        self._last_solve: dict[str, Any] | None = None
        self._modal_solve_trace_records: list[dict[str, Any]] = []

        operator = _action_operator(modal_action.bottom_action)
        comm = operator.getComm().tompi4py()
        owner_valid = self.constraint_lu_owner_rank == comm.size - 1
        if not comm.allreduce(owner_valid, op=MPI.LAND):
            raise ValueError("The modal C LU must use the final-rank modal owner.")
        owner_result = None
        if comm.rank == self.constraint_lu_owner_rank:
            try:
                (
                    self.constraint_lu,
                    self.constraint_pivots,
                    condition,
                ) = _factor_modal_constraint(
                    modal_action.modal_constraint,
                    self.modal_count,
                )
                owner_result = (True, condition, None)
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                owner_result = (
                    False,
                    None,
                    f"C factorization rejected: {type(exc).__name__}: {exc}",
                )
        factor_ok, condition, error = comm.bcast(
            owner_result, root=self.constraint_lu_owner_rank
        )
        if not factor_ok:
            self.destroy()
            raise RuntimeError(str(error))
        self.constraint_condition = float(condition)

    @property
    def modal_constraint(self) -> np.ndarray | None:
        if self._destroyed:
            return None
        return self.modal_action.modal_constraint

    @property
    def requires_right_fgmres(self) -> bool:
        return True

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "method": (
                "bounded_C_scaled_complex_QR_Anderson_research"
                if self.complex_qr_research
                else "bounded_C_scaled_SNESANDERSON"
            ),
            "mixing_method": self.mixing_method,
            "mixing_metric": self.mixing_metric,
            "status": "destroyed" if self._destroyed else "ready",
            "modal_count": self.modal_count,
            "real_coordinate_embedding": not self.complex_qr_research,
            "modal_coordinate_representation": (
                "complex128_modal_values"
                if self.complex_qr_research
                else "real_parts_then_imag_parts_in_complex128"
            ),
            "modal_coordinate_count": (
                self.modal_count if self.complex_qr_research else 2 * self.modal_count
            ),
            "modal_coordinate_extra_bytes_per_explicit_vec": int(
                0
                if self.complex_qr_research
                else self.modal_count * np.dtype(PETSc.ScalarType).itemsize
            ),
            "modal_coordinate_extra_bytes_two_explicit_vecs": int(
                0
                if self.complex_qr_research
                else 2 * self.modal_count * np.dtype(PETSc.ScalarType).itemsize
            ),
            "modal_schur_materialized": False,
            "modal_schur_column_count": 0,
            "modal_constraint_local_bytes": self.modal_constraint_local_bytes,
            "modal_constraint_condition": float(self.constraint_condition),
            "constraint_lu_owner_rank": self.constraint_lu_owner_rank,
            "constraint_lu_factorizations": 1,
            "constraint_lu_local_bytes": int(
                0
                if self.constraint_lu is None
                else self.constraint_lu.nbytes + self.constraint_pivots.nbytes
            ),
            "constraint_lu_solve_calls": int(self._constraint_lu_solve_calls),
            "solve_count": int(self._solve_count),
            "anderson_iteration_count": int(self._anderson_iteration_count),
            "s_evaluation_count": int(self._s_evaluation_count),
            "not_converged_count": int(self._not_converged_count),
            "side_action_call_count": {
                side: (
                    int(self._side_action_call_count[side])
                    if self._side_action_call_count_known[side]
                    else None
                )
                for side in ("bottom", "top")
            },
            "last_solve": (
                None if self._last_solve is None else dict(self._last_solve)
            ),
            "destroyed": bool(self._destroyed),
        }

    def export_modal_solve_capture(
        self,
        comm: Any,
        *,
        writer_rank: int = 0,
        side_audit_path: str | None = None,
        trace_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Gather the bounded owner trace at an explicit all-rank boundary."""
        if not self.capture_modal_solve_trace:
            return None
        owner = self.constraint_lu_owner_rank
        payload = None
        traces = None
        if int(comm.rank) == owner:
            traces = (
                list(self._modal_solve_trace_records)
                if trace_records is None
                else trace_records
            )
            array_bytes = sum(trace["captured_array_bytes"] for trace in traces)
            complete = [trace["solve_id"] for trace in traces] == [1, 2] and all(
                trace["capture_complete"] for trace in traces
            )
            payload = {
                "schema": "task041.modal_inner.solve_trace_capture.v1",
                "capture_status": "complete" if complete else "incomplete",
                "capture_complete": complete,
                "capture_incomplete_reason": (
                    None
                    if complete
                    else next(
                        (
                            trace["capture_incomplete_reason"]
                            for trace in traces
                            if trace.get("capture_incomplete_reason")
                        ),
                        "two_complete_solve_traces_not_available",
                    )
                ),
                "owner_rank": int(owner),
                "writer_rank": int(writer_rank),
                "modal_count": self.modal_count,
                "array_payload_bytes": array_bytes,
                "array_payload_limit_bytes": _modal_trace_array_limit_bytes(
                    self.modal_count
                ),
                "serialized_payload_limit_bytes": _MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES,
                "serialized_payload_size_basis": "compact_utf8_json",
                "solve_count_observed": self._solve_count,
                "side_rhs_audit_path": side_audit_path,
                "traces": traces,
            }
            try:
                serialized_size = len(
                    json.dumps(
                        payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                )
            except (TypeError, ValueError):
                serialized_size = _MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES + 1
                payload["capture_incomplete_reason"] = "trace_serialization_failed"
            if serialized_size > _MODAL_SOLVE_TRACE_JSON_LIMIT_BYTES:
                payload.update(
                    capture_status="incomplete",
                    capture_complete=False,
                    capture_incomplete_reason=payload.get(
                        "capture_incomplete_reason"
                    )
                    or "serialized_payload_limit_exceeded",
                    traces=[],
                    trace_arrays_omitted=True,
                )
        try:
            gathered = comm.gather(payload, root=writer_rank)
        except BaseException:
            if int(comm.rank) == owner:
                self._modal_solve_trace_records.clear()
                if trace_records is not None:
                    trace_records.clear()
            raise
        if int(comm.rank) == writer_rank:
            result = gathered[owner] if owner < len(gathered) else None
            if result is None:
                result = {
                    "schema": "task041.modal_inner.solve_trace_capture.v1",
                    "capture_status": "incomplete",
                    "capture_complete": False,
                    "capture_incomplete_reason": "owner_payload_missing",
                    "owner_rank": int(owner),
                    "writer_rank": int(writer_rank),
                }
        else:
            result = None
        if int(comm.rank) == owner:
            self._modal_solve_trace_records.clear()
            if trace_records is not None and (
                int(comm.rank) != int(writer_rank)
                or payload is None
                or payload.get("traces") is not trace_records
            ):
                trace_records.clear()
        return result

    def take_modal_solve_trace_records(self) -> list[dict[str, Any]] | None:
        """Transfer the owner-only encoded trace list without copying it."""
        if not self.capture_modal_solve_trace:
            return None
        records = self._modal_solve_trace_records
        self._modal_solve_trace_records = []
        return records if records else None

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("On-demand modal Anderson system has been destroyed.")
        self._solve_count += 1
        trace_record = None
        if self.capture_modal_solve_trace and self._solve_count <= 2:
            comm = _action_operator(self.modal_action.bottom_action).getComm().tompi4py()
            if comm.rank == self.constraint_lu_owner_rank:
                trace_record = {
                    "solve_id": int(self._solve_count),
                    "modal_count": self.modal_count,
                    "captured_array_bytes": 0,
                    "capture_complete": True,
                    "capture_incomplete_reason": None,
                    "evaluations": [],
                    "updates": [],
                }
                self._modal_solve_trace_records.append(trace_record)
        try:
            if self.complex_qr_research:
                result = solve_action_modal_schur_anderson_complex_qr_research(
                    self.modal_action,
                    rhs,
                    _borrowed_constraint_factor=self,
                    raw_metric_mixing=self.raw_metric_mixing,
                    _capture_trace_record=trace_record,
                )
            else:
                result = solve_action_modal_schur_anderson(
                    self.modal_action,
                    rhs,
                    scale_residual_by_constraint=True,
                    real_coordinate_embedding=True,
                    max_iterations=14,
                    _borrowed_constraint_factor=self,
                )
        except BaseException:
            if trace_record is not None:
                trace_record.update(
                    capture_complete=False,
                    capture_incomplete_reason="solver_raised_before_trace_completion",
                )
                if trace_record["evaluations"]:
                    trace_record["evaluations"][-1]["side_actions"] = {
                        side: _modal_trace_side_apply_record(action)
                        for side, action in (
                            ("bottom", self.modal_action.bottom_action),
                            ("top", self.modal_action.top_action),
                        )
                    }
            raise
        side_calls = dict(result["side_action_calls"])
        for side in ("bottom", "top"):
            delta = side_calls.get(side)
            if delta is None:
                self._side_action_call_count_known[side] = False
            elif self._side_action_call_count_known[side]:
                self._side_action_call_count[side] += int(delta)
        self._s_evaluation_count += int(result["s_evaluation_count"])
        self._anderson_iteration_count += int(result["iterations"])
        self._constraint_lu_solve_calls += int(result["constraint_lu_solve_calls"])
        summary_keys = (
            "status",
            "stop_reason",
            "anderson_history",
            "unscaled_residual_norm",
            "rhs_norm",
            "relative_residual",
            "max_iterations",
            "iterations",
            "function_evaluations",
            "final_validation_evaluations",
            "s_evaluation_count",
            "constraint_lu_factorizations",
            "constraint_lu_solve_calls",
            "constraint_lu_borrowed",
            "zero_rhs_absolute_residual",
            "target_reached",
            "convergence_callback_target_reached",
            "final_unscaled_target_reached",
            "invalid_failure",
            "budget_reason",
            "budget_callback_skipped",
            "snes_converged_reason",
            "callback_converged_reason",
            "budget_exhausted",
            "side_action_calls",
            "residual_evaluation_history",
            "real_coordinate_embedding",
            "modal_coordinate_representation",
            "modal_coordinate_count",
            "modal_coordinate_extra_bytes_per_explicit_vec",
            "modal_coordinate_extra_bytes_two_explicit_vecs",
            "real_coordinate_subspace_violation",
            "mixing_method",
            "mixing_metric",
            "mixing_beta",
            "complex_qr_mixing_history",
        )
        self._last_solve = {
            key: result[key] for key in summary_keys if key in result
        }
        if self.capture_modal_solve_trace:
            self._last_solve["residual_evaluation_history"] = [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"m", "raw", "scaled", "side_actions", "capture_complete"}
                }
                for row in result["residual_evaluation_history"]
            ]
        solution = result.pop("solution")
        if result["status"] != "converged":
            self._not_converged_count += 1
            message = (
                "Modal Anderson inner solve did not converge: "
                f"stop_reason={result['stop_reason']}, "
                f"raw_residual_norm={result['unscaled_residual_norm']:.17g}, "
                f"relative_residual={result['relative_residual']:.17g}, "
                f"iterations={result['iterations']}, "
                f"S_evaluations={result['s_evaluation_count']}, "
                f"side_action_calls={side_calls}"
            )
            del solution
            raise RuntimeError(message)
        return np.asarray(solution, dtype=np.complex128)

    def destroy(self) -> None:
        self._modal_solve_trace_records.clear()
        if self._destroyed:
            return
        self.constraint_lu = None
        self.constraint_pivots = None
        modal_action = self.modal_action
        modal_action.destroy()
        self.modal_action = None
        self._destroyed = True


def _build_action_modal_contribution(
    side: str,
    coupling: HybridInternalModeCoupling,
    action: Any,
    modal_count: int,
    columns: Sequence[int] | None = None,
    *,
    batch_size: int | None = None,
    progress_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> np.ndarray:
    operator = _action_operator(action)
    projection = (
        coupling.bottom.projection if side == "bottom" else coupling.top.projection
    )
    selected_columns = (
        tuple(range(2 * modal_count))
        if columns is None
        else tuple(int(i) for i in columns)
    )
    contribution = np.zeros(
        (2 * modal_count, len(selected_columns)), dtype=np.complex128
    )
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
    if batch_size is not None:
        batch_size = int(batch_size)
        if batch_size != 32:
            raise ValueError("Modal batch size is fixed to 32")
        if not hasattr(action, "apply_many"):
            raise TypeError("Modal batching requires an action apply_many API")
        comm = operator.getComm().tompi4py()
        row_first, row_last = map(int, operator.getOwnershipRange())
        global_rows = int(operator.getSize()[0])
        batch_total = (len(selected_columns) + batch_size - 1) // batch_size
        started = time.perf_counter()
        batch_durations: list[tuple[float, int]] = []
        for batch_number, batch_start in enumerate(
            range(0, len(selected_columns), batch_size), start=1
        ):
            batch_columns = selected_columns[batch_start : batch_start + batch_size]
            batch_width = len(batch_columns)
            batch_started = time.perf_counter()
            before_diagnostics = _action_diagnostics(action)
            before_mat_solve_calls = int(
                before_diagnostics.get("mat_solve_call_count", 0)
            )
            if progress_callback is not None:
                progress_callback(
                    "modal_batch_begin",
                    {
                        "side": side,
                        "stage": "modal_action",
                        "index": batch_start,
                        "total": len(selected_columns),
                        "batch_total": batch_total,
                        "batch_index": batch_number,
                        "width": batch_width,
                        "logical_completed": batch_start,
                        "mat_solve_calls": before_mat_solve_calls,
                        "stage_wall_seconds": batch_started - started,
                    },
                )
            right_hand_sides = solved = None
            try:
                right_hand_sides = PETSc.Mat().createDense(
                    size=((row_last - row_first, global_rows), batch_width),
                    comm=comm,
                )
                right_hand_sides.setUp()
                local_rhs = right_hand_sides.getDenseArray()
                for offset, column in enumerate(batch_columns):
                    modal = np.zeros(2 * modal_count, dtype=np.complex128)
                    modal[column] = 1.0
                    traction = modal_coupling_action(side, coupling, modal)
                    try:
                        if tuple(map(int, traction.getOwnershipRange())) != (
                            row_first,
                            row_last,
                        ):
                            raise ValueError(
                                "Modal batch traction ownership does not match factor"
                            )
                        local_rhs[:, offset] = traction.getArray(readonly=True)
                    finally:
                        traction.destroy()
                right_hand_sides.assemble()
                solved = right_hand_sides.duplicate(copy=False)
                action.apply_many(right_hand_sides, solved)
                for offset in range(batch_width):
                    response = solved.getColumnVector(offset)
                    projected = projection.createVecLeft()
                    try:
                        projection.mult(response, projected)
                        values = _replicated_modal_values(projected)
                        contribution[row_slice, batch_start + offset] = values
                        contribution[other_slice, batch_start + offset] = 0.0
                    finally:
                        projected.destroy()
                        response.destroy()
            finally:
                if solved is not None:
                    solved.destroy()
                if right_hand_sides is not None:
                    right_hand_sides.destroy()
            batch_elapsed = float(
                comm.allreduce(time.perf_counter() - batch_started, op=MPI.MAX)
            )
            batch_durations.append((batch_elapsed, batch_width))
            after_diagnostics = _action_diagnostics(action)
            after_mat_solve_calls = int(
                after_diagnostics.get("mat_solve_call_count", 0)
            )
            detail: dict[str, Any] = {
                "side": side,
                "stage": "modal_action",
                "index": batch_start,
                "total": len(selected_columns),
                "batch_total": batch_total,
                "batch_index": batch_number,
                "width": batch_width,
                "logical_completed": batch_start + batch_width,
                "mat_solve_calls": after_mat_solve_calls,
                "mat_solve_calls_delta": after_mat_solve_calls
                - before_mat_solve_calls,
                "stage_wall_seconds": time.perf_counter() - started,
            }
            if len(batch_durations) == 2:
                observed = batch_durations[:2]
                completed = sum(width for _, width in observed)
                elapsed = sum(duration for duration, _ in observed)
                throughput = completed / max(elapsed, _TINY)
                remaining = len(selected_columns) - (batch_start + batch_width)
                upper_per_column = max(
                    duration / width for duration, width in observed
                )
                detail.update(
                    {
                        "throughput_logical_per_second": throughput,
                        "eta_seconds_central": remaining / max(throughput, _TINY),
                        "eta_seconds_upper": remaining * upper_per_column,
                        "eta_basis": "first_two_completed_batches",
                    }
                )
            if progress_callback is not None:
                progress_callback("modal_batch_end", detail)
        return contribution

    for local_column, column in enumerate(selected_columns):
        modal = np.zeros(2 * modal_count, dtype=np.complex128)
        modal[column] = 1.0
        traction = modal_coupling_action(side, coupling, modal)
        response = operator.createVecLeft()
        projected = projection.createVecLeft()
        try:
            action.apply(traction, response)
            projection.mult(response, projected)
            contribution[row_slice, local_column] = _replicated_modal_values(projected)
            contribution[other_slice, local_column] = 0.0
        finally:
            projected.destroy()
            response.destroy()
            traction.destroy()
    return contribution


def _sampled_modal_column_contract(
    sampled_columns: Sequence[int] | None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None,
    sampled_column_contract_sha256: str | None,
    internal_count: int,
    modal_count: int,
) -> dict[str, Any] | None:
    if sampled_columns is None:
        if (
            sampled_column_roles is not None
            or sampled_column_contract_sha256 is not None
        ):
            raise ValueError("Sampled modal roles/hash require sampled columns.")
        return None
    if sampled_column_roles is None or sampled_column_contract_sha256 is None:
        raise ValueError("Sampled modal columns require roles and a contract hash.")
    columns = [int(column) for column in sampled_columns]
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("Sampled modal columns must be non-empty and unique.")
    if any(column < 0 or column >= internal_count for column in columns):
        raise ValueError("Sampled modal column is outside the internal Schur range.")
    expected_role_keys = {str(column) for column in columns}
    if set(sampled_column_roles) != expected_role_keys:
        raise ValueError("Sampled modal roles must cover exactly the frozen columns.")
    roles = {
        str(column): [str(role) for role in sampled_column_roles[str(column)]]
        for column in columns
    }
    contract = {
        "columns": columns,
        "mode_count_per_direction": int(modal_count),
        "roles": roles,
    }
    actual_hash = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if actual_hash != str(sampled_column_contract_sha256):
        raise ValueError(
            "Sampled modal column contract hash does not match the frozen contract."
        )
    return {**contract, "sha256": actual_hash}


def _compare_modal_sample_repeat(
    first: np.ndarray,
    second: np.ndarray,
    *,
    finite_reducer: Callable[[bool], bool] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply the existing finite, aggregate, and per-column sample repeat gate."""

    difference = first - second
    finite = bool(
        np.all(np.isfinite(first))
        and np.all(np.isfinite(second))
        and np.all(np.isfinite(difference))
    )
    if finite_reducer is not None:
        finite = bool(finite_reducer(finite))
    reference_norm = float(np.linalg.norm(first))
    difference_norm = float(np.linalg.norm(difference))
    column_absolute = [
        float(np.linalg.norm(difference[:, index]))
        for index in range(first.shape[1])
    ]
    column_relative = [
        column_absolute[index]
        / max(float(np.linalg.norm(first[:, index])), _TINY)
        for index in range(first.shape[1])
    ]
    relative_error = difference_norm / max(reference_norm, _TINY)
    limit = 1.0e-10
    diagnostics = {
        "absolute_difference": difference_norm,
        "reference_norm": reference_norm,
        "difference_norm": difference_norm,
        "relative_error": relative_error,
        "max_abs": float(np.max(np.abs(difference))),
        "max_column_absolute_difference": max(column_absolute),
        "max_column_relative_error": max(column_relative),
        "finite": finite,
        "limit": limit,
        "pass": bool(
            finite
            and relative_error <= limit
            and max(column_relative) <= limit
        ),
    }
    return difference, diagnostics


def build_hybrid_action_modal_schur(
    coupling: HybridInternalModeCoupling,
    bottom_action: Any,
    top_action: Any,
    *,
    matrix_repeat_tolerance: float = 1.0e-13,
    sampled_columns: Sequence[int] | None = None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None = None,
    sampled_column_contract_sha256: str | None = None,
    modal_batch_size: int | None = None,
    early_sample_first: bool = False,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> HybridActionModalSchurSystem:
    """Build the modal Schur, optionally with one frozen sampled reconstruction."""

    if (
        not np.isfinite(float(matrix_repeat_tolerance))
        or float(matrix_repeat_tolerance) <= 0.0
    ):
        raise ValueError("Modal-Schur repeat tolerance must be finite and positive.")
    if modal_batch_size is not None:
        modal_batch_size = int(modal_batch_size)
        if modal_batch_size != 32:
            raise ValueError("Modal batch size is fixed to 32")
    if early_sample_first:
        if sampled_columns is None or modal_batch_size != 32:
            raise ValueError(
                "Early modal sampling requires frozen columns and batch size 32"
            )
        if float(matrix_repeat_tolerance) != 1.0e-10:
            raise ValueError("Early modal sampling requires the fixed 1e-10 Gate")
    modal_count = int(coupling.mode_count_per_direction)
    internal_count = 2 * modal_count
    sampled_contract = _sampled_modal_column_contract(
        sampled_columns,
        sampled_column_roles,
        sampled_column_contract_sha256,
        internal_count,
        modal_count,
    )
    constraint = np.asarray(
        internal_modal_constraint_matrix(coupling), dtype=np.complex128
    )
    before = {
        "bottom": int(_action_diagnostics(bottom_action).get("apply_count", 0)),
        "top": int(_action_diagnostics(top_action).get("apply_count", 0)),
    }

    def total_mat_solve_calls() -> int:
        return sum(
            int(_action_diagnostics(action).get("mat_solve_call_count", 0))
            for action in (bottom_action, top_action)
        )

    def build_contribution(
        side: str,
        action: Any,
        columns: Sequence[int] | None = None,
    ) -> np.ndarray:
        if modal_batch_size is None:
            if columns is None:
                return _build_action_modal_contribution(
                    side, coupling, action, modal_count
                )
            return _build_action_modal_contribution(
                side, coupling, action, modal_count, columns=columns
            )
        return _build_action_modal_contribution(
            side,
            coupling,
            action,
            modal_count,
            columns=columns,
            batch_size=modal_batch_size,
            progress_callback=marker_callback,
        )

    sampled_column_errors: list[float] = []
    early_sample_diagnostics: dict[str, Any] | None = None
    full_sample_diagnostics: dict[str, Any] | None = None
    sampled_reconstruction = None
    if sampled_contract is None:
        first = constraint.copy()
        first -= build_contribution("bottom", bottom_action)
        first -= build_contribution("top", top_action)
        second = constraint.copy()
        second -= build_contribution("bottom", bottom_action)
        second -= build_contribution("top", top_action)
    elif early_sample_first:
        sampled = np.asarray(sampled_contract["columns"], dtype=np.int64)
        sample_started = time.perf_counter()
        if marker_callback is not None:
            marker_callback(
                "modal_sample_begin",
                {
                    "side": "both",
                    "stage": "modal_sample_repeat",
                    "index": 0,
                    "total": len(sampled),
                    "width": len(sampled),
                    "logical_completed": 0,
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": 0.0,
                },
            )
        sampled_first = constraint[:, sampled].copy()
        sampled_first -= build_contribution(
            "bottom", bottom_action, columns=sampled
        )
        sampled_first -= build_contribution("top", top_action, columns=sampled)
        sampled_second = constraint[:, sampled].copy()
        sampled_second -= build_contribution(
            "bottom", bottom_action, columns=sampled
        )
        sampled_second -= build_contribution("top", top_action, columns=sampled)
        early_difference, repeat_metrics = _compare_modal_sample_repeat(
            sampled_first, sampled_second
        )
        early_reference_norm = repeat_metrics["reference_norm"]
        early_difference_norm = repeat_metrics["difference_norm"]
        early_finite = repeat_metrics["finite"]
        early_sample_diagnostics = {
            **repeat_metrics,
            "mode": "two_batched_sample_builds_before_full_build",
        }
        if not early_sample_diagnostics["pass"]:
            raise ValueError(
                "Early sampled modal repeat Gate failed: "
                f"absolute={early_difference_norm:.6e}, "
                f"reference_norm={early_reference_norm:.6e}, "
                f"relative={early_sample_diagnostics['relative_error']:.6e}, "
                f"max_column={early_sample_diagnostics['max_column_relative_error']:.6e}, "
                f"finite={early_finite}, limit=1.000000e-10"
            )
        if marker_callback is not None:
            marker_callback(
                "modal_sample_ready",
                {
                    "side": "both",
                    "stage": "modal_sample_repeat",
                    "index": len(sampled),
                    "total": len(sampled),
                    "width": len(sampled),
                    "logical_completed": len(sampled),
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": time.perf_counter() - sample_started,
                    **early_sample_diagnostics,
                },
            )
        if marker_callback is not None:
            full_started = time.perf_counter()
            marker_callback(
                "modal_full_build_begin",
                {
                    "side": "both",
                    "stage": "modal_full_build",
                    "index": 0,
                    "total": internal_count,
                    "width": modal_batch_size,
                    "logical_completed": 0,
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": 0.0,
                },
            )
        first = constraint.copy()
        first -= build_contribution("bottom", bottom_action)
        first -= build_contribution("top", top_action)
        second = None
        sampled_reconstruction = sampled_first
        full_difference = first[:, sampled] - sampled_first
        full_reference_norm = float(np.linalg.norm(sampled_first))
        full_difference_norm = float(np.linalg.norm(full_difference))
        full_column_absolute = [
            float(np.linalg.norm(full_difference[:, index]))
            for index in range(len(sampled))
        ]
        sampled_column_errors = [
            float(
                full_column_absolute[index]
                / max(float(np.linalg.norm(sampled_first[:, index])), _TINY)
            )
            for index in range(len(sampled))
        ]
        full_sample_finite = bool(
            np.all(np.isfinite(first[:, sampled]))
            and np.all(np.isfinite(sampled_first))
            and np.all(np.isfinite(full_difference))
        )
        full_sample_diagnostics = {
            "absolute_difference": full_difference_norm,
            "reference_norm": full_reference_norm,
            "difference_norm": full_difference_norm,
            "relative_error": full_difference_norm
            / max(full_reference_norm, _TINY),
            "max_abs": float(np.max(np.abs(full_difference))),
            "max_column_absolute_difference": max(full_column_absolute),
            "max_column_relative_error": max(sampled_column_errors),
            "finite": full_sample_finite,
            "limit": 1.0e-10,
            "pass": bool(
                full_sample_finite
                and full_difference_norm / max(full_reference_norm, _TINY)
                <= 1.0e-10
                and max(sampled_column_errors) <= 1.0e-10
            ),
            "mode": "full_build_against_first_sample_without_third_action",
        }
        if not full_sample_diagnostics["pass"]:
            raise ValueError(
                "Full modal build differs from early sample: "
                f"absolute={full_difference_norm:.6e}, "
                f"reference_norm={full_reference_norm:.6e}, "
                f"relative={full_sample_diagnostics['relative_error']:.6e}, "
                f"max_column={full_sample_diagnostics['max_column_relative_error']:.6e}, "
                f"finite={full_sample_finite}, limit=1.000000e-10"
            )
        if marker_callback is not None:
            marker_callback(
                "modal_full_build_ready",
                {
                    "side": "both",
                    "stage": "modal_full_build",
                    "index": internal_count,
                    "total": internal_count,
                    "width": modal_batch_size,
                    "logical_completed": internal_count,
                    "mat_solve_calls": total_mat_solve_calls(),
                    "stage_wall_seconds": time.perf_counter() - full_started,
                },
            )
        matrix_difference = early_difference
        matrix_reference_norm = early_reference_norm
        matrix_difference_norm = early_difference_norm
    else:
        first = constraint.copy()
        first -= build_contribution("bottom", bottom_action)
        first -= build_contribution("top", top_action)
        second = None
        sampled = np.asarray(sampled_contract["columns"], dtype=np.int64)
        sampled_reconstruction = constraint[:, sampled].copy()
        sampled_reconstruction -= build_contribution(
            "bottom", bottom_action, columns=sampled
        )
        sampled_reconstruction -= build_contribution(
            "top", top_action, columns=sampled
        )
    after = {
        "bottom": int(_action_diagnostics(bottom_action).get("apply_count", 0)),
        "top": int(_action_diagnostics(top_action).get("apply_count", 0)),
    }
    build_apply_count = {side: after[side] - before[side] for side in ("bottom", "top")}
    expected = (
        internal_count + 2 * len(sampled_contract["columns"])
        if early_sample_first
        else (
            internal_count + len(sampled_contract["columns"])
            if sampled_contract is not None
            else 2 * internal_count
        )
    )
    if any(value != expected for value in build_apply_count.values()):
        raise RuntimeError(
            "Action modal Schur apply count does not match the selected build mode: "
            f"expected={expected}, actual={build_apply_count}."
        )
    expected_shape = (internal_count, internal_count)
    matrices = (constraint, first) if second is None else (constraint, first, second)
    for matrix in matrices:
        if matrix.shape != expected_shape or matrix.dtype != np.dtype(np.complex128):
            raise ValueError("Action modal Schur has an unexpected shape or dtype.")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("Action modal Schur contains non-finite values.")
    if sampled_contract is None:
        matrix_difference = first - second
        matrix_reference_norm = float(np.linalg.norm(first))
        matrix_difference_norm = float(np.linalg.norm(matrix_difference))
        sampled_column_errors = []
    elif not early_sample_first:
        reference = first[:, np.asarray(sampled_contract["columns"], dtype=np.int64)]
        matrix_difference = reference - sampled_reconstruction
        matrix_reference_norm = float(np.linalg.norm(reference))
        matrix_difference_norm = float(np.linalg.norm(matrix_difference))
        sampled_column_errors = [
            float(
                np.linalg.norm(sampled_reconstruction[:, index] - reference[:, index])
                / max(float(np.linalg.norm(reference[:, index])), _TINY)
            )
            for index in range(len(sampled_contract["columns"]))
        ]
    max_column_relative_error = (
        float(early_sample_diagnostics["max_column_relative_error"])
        if early_sample_first
        else max(sampled_column_errors, default=0.0)
    )
    matrix_repeat_error = matrix_difference_norm / max(matrix_reference_norm, _TINY)
    matrix_repeat_finite = bool(np.all(np.isfinite(matrix_difference)))
    matrix_repeat_diagnostics = {
        "relative_error": float(matrix_repeat_error),
        "limit": float(matrix_repeat_tolerance),
        "reference_norm": matrix_reference_norm,
        "difference_norm": matrix_difference_norm,
        "absolute_difference": matrix_difference_norm,
        "max_abs": float(np.max(np.abs(matrix_difference))),
        "max_column_relative_error": float(max_column_relative_error),
        "finite": matrix_repeat_finite,
        "mode": (
            "double_full_build"
            if sampled_contract is None
            else (
                "early_sample_before_full_build"
                if early_sample_first
                else "single_full_build_sampled_reconstruction"
            )
        ),
        "pass": bool(
            matrix_repeat_finite
            and np.isfinite(matrix_repeat_error)
            and matrix_repeat_error <= float(matrix_repeat_tolerance)
            and max_column_relative_error <= float(matrix_repeat_tolerance)
        ),
    }
    if early_sample_first:
        matrix_repeat_diagnostics["early_sample"] = dict(early_sample_diagnostics)
        matrix_repeat_diagnostics["full_vs_first_sample"] = dict(
            full_sample_diagnostics
        )
    if not matrix_repeat_diagnostics["pass"]:
        raise ValueError(
            "Action modal Schur repeat error exceeds tolerance: "
            f"actual={matrix_repeat_error:.6e}, "
            f"limit={float(matrix_repeat_tolerance):.6e}, "
            f"reference_norm={matrix_reference_norm:.6e}, "
            f"difference_norm={matrix_difference_norm:.6e}, "
            f"max_abs={matrix_repeat_diagnostics['max_abs']:.6e}, "
            f"max_column={max_column_relative_error:.6e}."
        )
    singular_values = np.linalg.svd(first, compute_uv=False)
    rank_scale = (
        np.finfo(float).eps * max(first.shape) * float(singular_values[0])
        if singular_values.size
        else 0.0
    )
    rank = int(np.count_nonzero(singular_values > rank_scale))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if (
            singular_values.size
            and np.all(np.isfinite(singular_values))
            and singular_values[-1] > 0.0
        )
        else float("inf")
    )
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
        sampled_column_diagnostics={
            "single_build": sampled_contract is not None,
            "columns": []
            if sampled_contract is None
            else list(sampled_contract["columns"]),
            "roles": {}
            if sampled_contract is None
            else dict(sampled_contract["roles"]),
            "contract_sha256": None
            if sampled_contract is None
            else sampled_contract["sha256"],
            "early_sample_first": bool(early_sample_first),
            "modal_batch_size": modal_batch_size,
            "full_build_apply_count": {
                "bottom": internal_count,
                "top": internal_count,
            },
            "sample_build_apply_count": {
                "bottom": 0
                if sampled_contract is None
                else (
                    2 * len(sampled_contract["columns"])
                    if early_sample_first
                    else len(sampled_contract["columns"])
                ),
                "top": 0
                if sampled_contract is None
                else (
                    2 * len(sampled_contract["columns"])
                    if early_sample_first
                    else len(sampled_contract["columns"])
                ),
            },
            "column_relative_errors": sampled_column_errors,
        },
        batch_diagnostics={
            "enabled": modal_batch_size is not None,
            "batch_size": modal_batch_size,
            "early_sample_first": bool(early_sample_first),
            "early_sample": (
                None
                if early_sample_diagnostics is None
                else dict(early_sample_diagnostics)
            ),
            "full_vs_first_sample": (
                None
                if full_sample_diagnostics is None
                else dict(full_sample_diagnostics)
            ),
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
        action_modal_schur_system: (
            HybridActionModalSchurSystem
            | HybridActionModalSchurAndersonSystem
            | _FixedH6ModalGmresResearchBundle
        ),
        research_inventory: dict[str, Any] | None = None,
        dynamic_side_inventory: bool = False,
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
        self._dynamic_side_inventory = bool(dynamic_side_inventory)
        self._fixed_h6_pc_side_apply_counts = (
            {
                side: {"first": 0, "delta": 0}
                for side in ("bottom", "top")
            }
            if isinstance(
                action_modal_schur_system, _FixedH6ModalGmresResearchBundle
            )
            else None
        )
        self.modal_schur = getattr(action_modal_schur_system, "modal_schur", None)
        self.modal_count = int(action_modal_schur_system.modal_count)
        self.defer_action_modal_schur_release = False
        self._modal_solve_trace_handoff: list[dict[str, Any]] | None = None
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
    def modal_constraint(self) -> np.ndarray:
        constraint = self.action_modal_schur_system.modal_constraint
        if constraint is None:
            raise RuntimeError("Modal constraint was released before the LDU context.")
        return constraint

    @property
    def requires_right_fgmres(self) -> bool:
        return bool(
            getattr(self.action_modal_schur_system, "requires_right_fgmres", False)
        )

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
        on_demand_modal = isinstance(
            self.action_modal_schur_system, HybridActionModalSchurAndersonSystem
        )
        fixed_h6_modal = isinstance(
            self.action_modal_schur_system, _FixedH6ModalGmresResearchBundle
        )
        nonmaterialized_modal = on_demand_modal or fixed_h6_modal
        system_diagnostics = self.action_modal_schur_system.diagnostics
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
            "modal_block_name": (
                "on_demand_nonlinear_modal_inner"
                if on_demand_modal
                else "fixed_h6_surrogate_on_demand_modal_gmres"
                if fixed_h6_modal
                else "approximate_action_schur"
            ),
            "modal_block_condition": (
                None
                if nonmaterialized_modal
                else float(self.action_modal_schur_system.condition)
            ),
            "modal_block_condition_status": (
                "not_measured" if fixed_h6_modal else "measured" if not on_demand_modal else None
            ),
            "modal_schur": None if nonmaterialized_modal else system_diagnostics,
            "action_modal_schur_released": bool(self._action_modal_schur_released),
            "destroyed": bool(self._destroyed),
        }
        if on_demand_modal:
            result.update(
                {
                    "modal_count": int(self.modal_count),
                    "modal_schur_materialized": False,
                    "modal_schur_storage_bytes": 0,
                    "modal_inner_solver": system_diagnostics,
                    "modal_constraint_condition": float(
                        self.action_modal_schur_system.constraint_condition
                    ),
                    "modal_constraint_local_bytes": int(
                        self.action_modal_schur_system.modal_constraint_local_bytes
                    ),
                }
            )
        if fixed_h6_modal:
            result.update(
                {
                    "modal_count": int(self.modal_count),
                    "modal_schur_scope": "not_materialized",
                    "modal_schur_materialized": False,
                    "modal_schur_column_count": 0,
                    "modal_schur_storage_bytes": 0,
                    "modal_schur_condition": "not_measured",
                    "modal_inner_solver": system_diagnostics,
                    "fixed_h6_modal_solver": system_diagnostics,
                    "modal_constraint_condition": float(
                        self.action_modal_schur_system.constraint_condition
                    ),
                    "modal_constraint_local_bytes": int(
                        self.action_modal_schur_system.modal_constraint_local_bytes
                    ),
                    "fixed_h6_pc_side_apply_counts": {
                        side: dict(counts)
                        for side, counts in self._fixed_h6_pc_side_apply_counts.items()
                    },
                    "fixed_h6_pc_side_apply_count_scope": (
                        "successful direct side apply calls; per-rank replicated"
                    ),
                    "side_h6_callback_counts": {
                        "bottom": int(bottom.get("counts", {}).get("H6", 0)),
                        "top": int(top.get("counts", {}).get("H6", 0)),
                    },
                }
            )
            local_rank = system_diagnostics.get("rank")
            if not isinstance(local_rank, int) or isinstance(local_rank, bool):
                local_rank = int(
                    _action_operator(self.bottom_action).getComm().tompi4py().rank
                )
            early_gate = (
                self._research_inventory.get("early_sample_gate", {})
                if self._research_inventory is not None
                else {}
            )
            gate_rows = early_gate.get("rank_results", [])
            gate_row = next(
                (
                    row
                    for row in gate_rows
                    if row.get("rank") == local_rank
                ),
                None,
            )
            setup_s_h = (
                None
                if gate_row is None
                else gate_row.get("operator_action_completions")
            )
            solver_s_h = system_diagnostics.get("cumulative_total_matmult_calls")

            def valid_counts(value: Any) -> int | None:
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
                return None

            setup_s_h = valid_counts(setup_s_h)
            solver_s_h = valid_counts(solver_s_h)
            total_s_h = (
                None
                if setup_s_h is None or solver_s_h is None
                else setup_s_h + solver_s_h
            )
            result["fixed_h6_whole_run_work"] = {
                "rank": local_rank,
                "count_scope": "rank-local; do_not_sum_across_ranks",
                "setup_gate_s_h_actions": setup_s_h,
                "gmres_solver_and_final_check_s_h_actions": solver_s_h,
                "total_s_h_actions_including_setup_gate": total_s_h,
                "setup_gate_c_matvec_calls": (
                    None
                    if gate_row is None
                    else valid_counts(
                        gate_row.get("modal_constraint_matvec_calls")
                    )
                ),
                "total_c_matvec_calls_including_setup_gate": valid_counts(
                    system_diagnostics.get("modal_constraint_matvec_calls_total")
                ),
                "setup_gate_h6_calls_by_side": (
                    None
                    if gate_row is None
                    else gate_row.get("fixed_h6_side_counts")
                ),
                "total_h6_apply_calls_by_side": system_diagnostics.get(
                    "fixed_h6_modal_apply_calls"
                ),
                "total_h6_matrix_mult_calls_by_side": system_diagnostics.get(
                    "fixed_h6_modal_matrix_mult_calls"
                ),
                "owner_c_lu_factorizations": system_diagnostics.get(
                    "constraint_lu_factorizations"
                ),
                "gmres_c_lu_solve_attempts": system_diagnostics.get(
                    "cumulative_constraint_lu_solve_attempts"
                ),
            }
        if self._research_inventory is not None:
            result.update(self._research_inventory)
        if self._dynamic_side_inventory:
            nested_live = sum(
                int(diagnostics.get("nested_iterative_ksp_count", 0))
                for diagnostics in (bottom, top)
            )
            nested_created = sum(
                int(diagnostics.get("nested_ksp_created_count", 0))
                for diagnostics in (bottom, top)
            )
            nested_destroyed = sum(
                int(diagnostics.get("nested_ksp_destroy_count", 0))
                for diagnostics in (bottom, top)
            )
            p4_live = sum(
                int(diagnostics.get("p4_factor_count", 0))
                for diagnostics in (bottom, top)
            )
            p4_created = sum(
                int(diagnostics.get("p4_factor_created_count", 0))
                for diagnostics in (bottom, top)
            )
            p4_destroyed = sum(
                int(diagnostics.get("p4_factor_destroy_count", 0))
                for diagnostics in (bottom, top)
            )
            result.update(
                {
                    "p4_factor_count": p4_live,
                    "p4_factor_created_count": p4_created,
                    "p4_factor_destroy_count": p4_destroyed,
                    "p6_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "global_hybrid_direct_factor_count": 0,
                    "nested_iterative_ksp_count": nested_live,
                    "nested_iterative_ksp_created_count": nested_created,
                    "nested_iterative_ksp_destroy_count": nested_destroyed,
                }
            )
        return result

    def _check_layouts(self) -> None:
        expected_bottom = self.layout.bottom_local_sizes[self.layout.comm.rank]
        expected_top = self.layout.top_local_sizes[self.layout.comm.rank]
        if self._bottom_rhs.getLocalSize() != expected_bottom:
            raise ValueError("Bottom action ownership does not match layout.")
        if self._top_rhs.getLocalSize() != expected_top:
            raise ValueError("Top action ownership does not match layout.")
        if self.modal_schur is None:
            if self.modal_count != self.layout.modal_count:
                raise ValueError("Modal solver count does not match layout.")
            constraint = self.modal_constraint
            if constraint.shape != (
                self.layout.modal_count,
                self.layout.modal_count,
            ):
                raise ValueError("Modal constraint does not match layout.")
        elif self.modal_schur.shape != (
            self.layout.modal_count,
            self.layout.modal_count,
        ):
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
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["bottom"]["first"] += 1
        self.top_action.apply(self._top_rhs, self._top_first)
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["top"]["first"] += 1
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
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["bottom"]["delta"] += 1
        self.top_action.apply(self._top_coupling, self._top_delta)
        if self._fixed_h6_pc_side_apply_counts is not None:
            self._fixed_h6_pc_side_apply_counts["top"]["delta"] += 1
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

    def release_modal_solve_trace_handoff(self) -> None:
        handoff = self._modal_solve_trace_handoff
        if isinstance(handoff, list):
            handoff.clear()
        self._modal_solve_trace_handoff = None

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


def _check_on_demand_modal_sample_repeat(
    modal_action: HybridActionModalSchurApply,
    *,
    sampled_columns: Sequence[int] | None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None,
    sampled_column_contract_sha256: str | None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Repeat the frozen sample basis through S without materializing S."""

    contract = _sampled_modal_column_contract(
        sampled_columns,
        sampled_column_roles,
        sampled_column_contract_sha256,
        modal_action.modal_count,
        modal_action.mode_count,
    )
    if contract is None:
        return {
            "status": "not_run",
            "pass": None,
            "reason": "sampled_column_contract_not_supplied",
            "full_vs_sample": "not_applicable_full_schur_not_materialized",
        }

    columns = list(contract["columns"])
    comm = _action_operator(modal_action.bottom_action).getComm().tompi4py()
    marker_detail = {
        "side": "both",
        "stage": "modal_sample_repeat",
        "columns": columns,
        "sample_count": len(columns),
        "contract_sha256": contract["sha256"],
    }
    if marker_callback is not None:
        marker_callback(
            "modal_sample_begin",
            {
                **marker_detail,
                "index": 0,
                "total": len(columns),
                "width": len(columns),
                "logical_completed": 0,
                "stage_wall_seconds": 0.0,
            },
        )

    sample_started = time.perf_counter()
    first = np.empty((modal_action.modal_count, len(columns)), dtype=np.complex128)
    second = np.empty_like(first)
    for target in (first, second):
        for index, column in enumerate(columns):
            basis = np.zeros(modal_action.modal_count, dtype=np.complex128)
            basis[column] = 1.0
            target[:, index] = modal_action.apply(basis)

    _, repeat_metrics = _compare_modal_sample_repeat(
        first,
        second,
        finite_reducer=lambda finite: bool(comm.allreduce(finite, op=MPI.LAND)),
    )
    passed = repeat_metrics["pass"]
    diagnostics = {
        **contract,
        "status": "passed" if passed else "failed",
        "pass": passed,
        "mode": "on_demand_modal_action_two_sample_basis_repeats",
        "early_sample_repeat": {
            **repeat_metrics,
        },
        "full_vs_sample": "not_applicable_full_schur_not_materialized",
    }
    if not passed:
        raise ValueError(
            "Early sampled modal repeat Gate failed: "
            f"relative={repeat_metrics['relative_error']:.6e}, "
            f"max_column={repeat_metrics['max_column_relative_error']:.6e}, "
            f"finite={repeat_metrics['finite']}, limit=1.000000e-10"
        )
    if marker_callback is not None:
        marker_callback(
            "modal_sample_ready",
            {
                **marker_detail,
                "index": len(columns),
                "total": len(columns),
                "width": len(columns),
                "logical_completed": len(columns),
                "stage_wall_seconds": time.perf_counter() - sample_started,
                **diagnostics["early_sample_repeat"],
            },
        )
    return diagnostics


_FIXED_H6_FEEDBACK_GATE_TOLERANCE = 1.0e-10
_FIXED_H6_FEEDBACK_GATE_ALPHA = 0.5 + 0.75j
_FIXED_H6_FEEDBACK_GATE_EPSILON = 1.0e-12


def _fixed_h6_gate_norm(
    values: np.ndarray | None, modal_count: int
) -> tuple[float | None, str | None]:
    if values is None:
        return None, "dependent_output_unavailable"
    vector = np.asarray(values, dtype=np.complex128)
    if vector.shape != (modal_count,):
        return None, "shape_mismatch"
    if not np.all(np.isfinite(vector)):
        return None, "nonfinite_vector"
    norm = float(np.linalg.norm(vector))
    return (norm, None) if np.isfinite(norm) else (None, "nonfinite_norm")


def _fixed_h6_gate_metric(
    actual: np.ndarray | None,
    reference: np.ndarray | None,
    modal_count: int,
    *,
    relative_denominator: str | None = None,
    reference_norm_scale: float | None = None,
    reference_norm_parts: tuple[float | None, ...] = (),
    absolute_branch: str | None = None,
    input_norm: float | None = None,
) -> dict[str, Any]:
    actual_norm, actual_error = _fixed_h6_gate_norm(actual, modal_count)
    reference_norm, reference_error = _fixed_h6_gate_norm(reference, modal_count)
    errors = [error for error in (actual_error, reference_error) if error is not None]
    numerator = None
    denominator = None
    measured: float | None = None
    branch = "not_evaluated"
    if not errors:
        difference = np.asarray(actual - reference, dtype=np.complex128)
        if np.all(np.isfinite(difference)):
            candidate_numerator = float(np.linalg.norm(difference))
            if np.isfinite(candidate_numerator):
                numerator = candidate_numerator
            else:
                errors.append("nonfinite_difference_norm")
        else:
            errors.append("nonfinite_difference_norm")
    if not errors and absolute_branch is not None:
        measured = float(numerator)
        branch = absolute_branch
    elif not errors:
        if relative_denominator == "pair":
            denominator = max(float(actual_norm), float(reference_norm))
        elif relative_denominator == "scaled_reference":
            if reference_norm_scale is None or not np.isfinite(reference_norm_scale):
                errors.append("nonfinite_scaled_reference_norm")
            else:
                denominator = max(float(actual_norm), float(reference_norm_scale))
        elif relative_denominator == "reference_sum":
            if len(reference_norm_parts) != 2 or not all(
                part is not None and np.isfinite(part) for part in reference_norm_parts
            ):
                errors.append("nonfinite_reference_norm_sum")
            else:
                denominator = max(
                    float(actual_norm), sum(float(part) for part in reference_norm_parts)
                )
        else:
            errors.append("unknown_relative_denominator")
        if not errors:
            if not np.isfinite(denominator):
                denominator = None
                errors.append("nonfinite_denominator")
            elif denominator > 0.0:
                candidate_measure = float(numerator / denominator)
                if np.isfinite(candidate_measure):
                    measured = candidate_measure
                    branch = "relative"
                else:
                    errors.append("nonfinite_error_metric")
            else:
                measured = float(numerator)
                branch = "absolute_zero_denominator"
    finite = bool(not errors and measured is not None and np.isfinite(measured))
    if not finite and not errors:
        errors.append("nonfinite_error_metric")
    if errors:
        branch = "not_evaluated_invalid_intermediate"
    metric_pass = bool(
        finite
        and measured is not None
        and measured <= _FIXED_H6_FEEDBACK_GATE_TOLERANCE
    )
    return {
        "status": "evaluated" if finite else "not_evaluated",
        "numerator": numerator,
        "denominator": denominator,
        "branch": branch if finite else (branch or "nonfinite_or_invalid_intermediate"),
        "relative_error": measured if finite and branch == "relative" else None,
        "absolute_error": numerator,
        "measured_error": measured if finite else None,
        "actual_norm": actual_norm,
        "reference_norm": reference_norm,
        "input_norm": input_norm,
        "finite": finite,
        "errors": errors,
        "limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
        "pass": metric_pass,
    }


def _check_fixed_h6_modal_feedback_repeat_linearity(
    modal_solver: _FixedH6ModalKrylovSystem,
    *,
    original_side_actions: Mapping[str, Any],
    original_side_apply_counts_before: Mapping[str, int | None],
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
) -> dict[str, Any]:
    """Check the same fixed H6 feedback on bounded complex mixed vectors."""

    modal_action = modal_solver._modal_action
    if modal_action is None:
        raise RuntimeError("Fixed-H6 modal action is unavailable for its gate")
    modal_count = int(modal_solver.modal_count)
    mode_count = int(modal_solver.mode_count)
    k = np.arange(1, modal_count + 1, dtype=np.float64)
    x_raw = k + 1j * k[::-1]
    x_norm = float(np.linalg.norm(x_raw))
    x = np.asarray(x_raw / x_norm, dtype=np.complex128)
    y_raw = k[::-1] + 1j * (k + 0.5)
    y_orthogonal = y_raw - np.vdot(x, y_raw) * x
    y_norm = float(np.linalg.norm(y_orthogonal))
    y = np.asarray(y_orthogonal / y_norm, dtype=np.complex128)
    alpha, epsilon = _FIXED_H6_FEEDBACK_GATE_ALPHA, _FIXED_H6_FEEDBACK_GATE_EPSILON
    inputs = {
        "zero": np.zeros(modal_count, dtype=np.complex128),
        "x": x,
        "x_repeat": x,
        "alpha_x": alpha * x,
        "y": y,
        "y_repeat": y,
        "x_plus_y": x + y,
        "near_zero_x": epsilon * x,
    }
    input_norms = {name: float(np.linalg.norm(value)) for name, value in inputs.items()}
    input_hashes = {
        name: hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
        for name, value in inputs.items()
    }
    block_support = {
        name: [
            bool(np.linalg.norm(value[:mode_count]) > 0.0),
            bool(np.linalg.norm(value[mode_count:]) > 0.0),
        ]
        for name, value in (("x", x), ("y", y))
    }
    xy_inner_product_abs = float(abs(np.vdot(x, y)))
    input_definition = {
        "formula": (
            "k=1..modal_count; x=normalize(k+i*reverse(k)); "
            "y=normalize(reverse(k)+i*(k+0.5)-vdot(x,y_raw)*x)"
        ),
        "modal_count": modal_count,
        "mode_count_per_direction": mode_count,
        "x_norm": input_norms["x"],
        "y_norm": input_norms["y"],
        "x_sha256": input_hashes["x"],
        "y_sha256": input_hashes["y"],
        "x_y_inner_product_abs": xy_inner_product_abs,
        "x_y_noncollinear": bool(np.isfinite(xy_inner_product_abs) and xy_inner_product_abs < 1.0e-12),
        "x_y_complex": bool(np.any(x.imag != 0.0) and np.any(y.imag != 0.0)),
        "positive_negative_block_support": block_support,
        "alpha": [float(alpha.real), float(alpha.imag)],
        "epsilon": epsilon,
        "epsilon_x_norm": input_norms["near_zero_x"],
    }
    local_input_error = None
    if (
        x_norm == 0.0
        or y_norm == 0.0
        or not all(np.all(np.isfinite(value)) for value in inputs.values())
        or not all(np.isfinite(value) for value in input_norms.values())
        or not all(all(support) for support in block_support.values())
        or not np.isfinite(xy_inner_product_abs)
        or xy_inner_product_abs >= 1.0e-12
        or not input_definition["x_y_complex"]
    ):
        local_input_error = "gate_inputs_are_nonfinite_or_not_mixed"
    started = time.perf_counter()
    if marker_callback is not None:
        marker_callback(
            "modal_sample_begin",
            {
                "side": "both",
                "stage": "fixed_h6_modal_feedback_repeat_linearity",
                "mode": "complex_repeat_homogeneity_additivity_and_near_zero",
                "input_definition": input_definition,
                "maximum_s_h_actions": len(inputs),
                "limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
            },
        )

    comm = modal_solver._comm
    input_records = comm.allgather((local_input_error, input_hashes))
    input_errors = [
        f"rank {rank}: {error}"
        for rank, (error, _hashes) in enumerate(input_records)
        if error is not None
    ]
    hash_sets = [
        tuple(sorted(hashes.items()))
        for error, hashes in input_records
        if error is None
    ]
    if hash_sets and any(value != hash_sets[0] for value in hash_sets[1:]):
        input_errors.append("deterministic gate inputs differ across ranks")
    if input_errors:
        elapsed = float(time.perf_counter() - started)
        rank_results = [
            {
                "rank": rank,
                "pass": False,
                "input_hashes": hashes,
                "operator_action_attempts": 0,
                "operator_action_completions": 0,
                "modal_constraint_matvec_calls": 0,
                "constraint_lu_solve_attempts": 0,
                "fixed_h6_side_counts": None,
                "input_unchanged_by_action": {},
                "original_side_apply_count_delta": None,
                "setup_wall_seconds": elapsed,
                "errors": [error] if error is not None else input_errors,
            }
            for rank, (error, hashes) in enumerate(input_records)
        ]
        failed_gate = {
            "status": "failed",
            "pass": False,
            "mode": "fixed_h6_modal_feedback_complex_repeat_linearity",
            "requested_s_h_actions": len(inputs),
            "input_definition": input_definition,
            "rank_results": rank_results,
            "rank_count": int(comm.size),
            "rank_action_counts_scope": "per-rank local; do_not_sum_across_ranks",
            "input_preflight_allgathers": 1,
            "result_consensus_allgathers": 0,
            "full_schur_materialized": False,
            "fallback_used": False,
        }
        if marker_callback is not None:
            marker_callback(
                "modal_sample_ready",
                {
                    "side": "both",
                    "stage": "fixed_h6_modal_feedback_repeat_linearity",
                    "status": "failed",
                    "pass": False,
                    "early_sample_gate": failed_gate,
                },
            )
        raise ValueError(
            "Fixed-H6 modal feedback gate input preflight failed; "
            + "; ".join(input_errors)
        )

    side_before = {
        side: dict(action.audit)
        for side, action in zip(
            ("bottom", "top"), (modal_solver._bottom_action, modal_solver._top_action), strict=True
        )
    }
    constraint_before = int(modal_action._modal_constraint_matvec_count)
    lu_attempts_before = int(modal_solver._constraint_lu_solve_attempts)
    outputs: dict[str, np.ndarray | None] = {}
    output_norms: dict[str, float | None] = {}
    output_errors: dict[str, str | None] = {}
    input_unchanged_by_action: dict[str, bool] = {}
    metrics: dict[str, dict[str, Any]] = {}
    attempts = completions = 0

    for name, values in inputs.items():
        attempts += 1
        result = np.asarray(modal_action.apply(values), dtype=np.complex128)
        completions += 1
        norm, error = _fixed_h6_gate_norm(result, modal_count)
        input_unchanged = (
            hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
            == input_hashes[name]
        )
        input_unchanged_by_action[name] = input_unchanged
        if error is None and not input_unchanged:
            error = "input_mutated_during_action"
        output_norms[name] = norm
        output_errors[name] = error
        outputs[name] = result if error is None else None
        if name == "zero":
            metrics["zero_absolute"] = _fixed_h6_gate_metric(
                outputs[name], np.zeros(modal_count, dtype=np.complex128), modal_count,
                absolute_branch="absolute_zero_input", input_norm=input_norms[name],
            )
        elif name == "x_repeat":
            metrics["repeat_x"] = _fixed_h6_gate_metric(
                outputs[name], outputs.get("x"), modal_count, relative_denominator="pair"
            )
        elif name == "alpha_x":
            fx_norm = output_norms.get("x")
            metrics["complex_homogeneity"] = _fixed_h6_gate_metric(
                outputs[name], None if outputs.get("x") is None else alpha * outputs["x"], modal_count,
                relative_denominator="scaled_reference",
                reference_norm_scale=None if fx_norm is None else abs(alpha) * fx_norm,
            )
        elif name == "y_repeat":
            metrics["repeat_y"] = _fixed_h6_gate_metric(
                outputs[name], outputs.get("y"), modal_count, relative_denominator="pair"
            )
        elif name == "x_plus_y":
            fx, fy = outputs.get("x"), outputs.get("y")
            metrics["additivity"] = _fixed_h6_gate_metric(
                outputs[name], None if fx is None or fy is None else fx + fy, modal_count,
                relative_denominator="reference_sum",
                reference_norm_parts=(output_norms.get("x"), output_norms.get("y")),
            )
        elif name == "near_zero_x":
            fx = outputs.get("x")
            metrics["near_zero_absolute"] = _fixed_h6_gate_metric(
                outputs[name], None if fx is None else epsilon * fx, modal_count,
                absolute_branch="absolute_near_zero_input",
                input_norm=input_norms[name],
            )
            metrics["near_zero_absolute"].update(
                {
                    "output_norm": output_norms.get(name),
                }
            )

    side_counts = {}
    for side, action in zip(
        ("bottom", "top"), (modal_solver._bottom_action, modal_solver._top_action), strict=True
    ):
        audit = action.audit
        apply_calls = int(audit["apply_count"]) - int(side_before[side]["apply_count"])
        matrix_mult_calls = int(audit["matrix_mult_count"]) - int(
            side_before[side]["matrix_mult_count"]
        )
        h6_degree = audit.get("h6_degree")
        degree_valid = (
            isinstance(h6_degree, int)
            and not isinstance(h6_degree, bool)
            and h6_degree > 1
        )
        expected_matrix_mult_calls = (
            (h6_degree - 1) * apply_calls if degree_valid else None
        )
        side_counts[side] = {
            "fixed_h6_apply_calls": apply_calls,
            "fixed_h6_h6_degree": h6_degree if degree_valid else None,
            "fixed_h6_matrix_mult_calls": matrix_mult_calls,
            "expected_matrix_mult_calls_from_degree": expected_matrix_mult_calls,
            "matrix_mult_matches_h6_degree": bool(
                expected_matrix_mult_calls is not None
                and matrix_mult_calls == expected_matrix_mult_calls
            ),
        }
    original_after = {
        side: _action_apply_count(action) for side, action in original_side_actions.items()
    }
    original_delta = {
        side: (
            None
            if original_side_apply_counts_before.get(side) is None
            or original_after[side] is None
            else int(original_after[side]) - int(original_side_apply_counts_before[side])
        )
        for side in ("bottom", "top")
    }
    c_matvecs = int(modal_action._modal_constraint_matvec_count) - constraint_before
    c_lu_attempts = int(modal_solver._constraint_lu_solve_attempts) - lu_attempts_before
    local_pass = bool(
        attempts == len(inputs)
        and completions == len(inputs)
        and len(metrics) == 6
        and all(error is None for error in output_errors.values())
        and all(input_unchanged_by_action.values())
        and all(metric["pass"] for metric in metrics.values())
        and all(value == 0 for value in original_delta.values())
        and c_matvecs == completions
        and c_lu_attempts == 0
        and all(
            row["fixed_h6_apply_calls"] == completions
            and row["matrix_mult_matches_h6_degree"]
            for row in side_counts.values()
        )
    )
    local_result = {
        "rank": int(comm.rank),
        "pass": local_pass,
        "input_hashes": input_hashes,
        "operator_action_attempts": attempts,
        "operator_action_completions": completions,
        "modal_constraint_matvec_calls": c_matvecs,
        "constraint_lu_solve_attempts": c_lu_attempts,
        "fixed_h6_side_counts": side_counts,
        "input_unchanged_by_action": input_unchanged_by_action,
        "original_side_apply_count_delta": original_delta,
        "output_norms": output_norms,
        "output_errors": output_errors,
        "metrics": metrics,
        "setup_wall_seconds": float(time.perf_counter() - started),
    }
    rank_results = comm.allgather(local_result)
    gathered_input_hashes = [
        tuple(sorted(row["input_hashes"].items())) for row in rank_results
    ]
    global_pass = bool(
        [row.get("rank") for row in rank_results] == list(range(comm.size))
        and all(row.get("pass") is True for row in rank_results)
        and len(set(gathered_input_hashes)) == 1
    )
    metric_formulas = {
        "zero_absolute": "||F(0)||",
        "repeat_x": "||F(x)_1-F(x)_2||/max(||F(x)_1||,||F(x)_2||)",
        "complex_homogeneity": (
            "||F(alpha*x)-alpha*F(x)||/"
            "max(||F(alpha*x)||,|alpha|*||F(x)||)"
        ),
        "repeat_y": "||F(y)_1-F(y)_2||/max(||F(y)_1||,||F(y)_2||)",
        "additivity": (
            "||F(x+y)-F(x)-F(y)||/"
            "max(||F(x+y)||,||F(x)||+||F(y)||)"
        ),
        "near_zero_absolute": "||F(epsilon*x)-epsilon*F(x)||",
    }
    for row in rank_results:
        for name, formula in metric_formulas.items():
            if name in row["metrics"]:
                row["metrics"][name]["formula"] = formula
    wall_values = [float(row["setup_wall_seconds"]) for row in rank_results]
    diagnostics = {
        "status": "passed" if global_pass else "failed",
        "pass": global_pass,
        "mode": "fixed_h6_modal_feedback_complex_repeat_linearity",
        "operator": "S_H=C-PbJbH6bJb^H Tb-PtJtH6tJt^H Tt",
        "requested_s_h_actions": len(inputs),
        "operator_actions_maximum": len(inputs),
        "relative_limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
        "absolute_limit": _FIXED_H6_FEEDBACK_GATE_TOLERANCE,
        "input_definition": input_definition,
        "metric_formulas": metric_formulas,
        "metrics": rank_results[0]["metrics"],
        "rank_results": rank_results,
        "rank_count": int(comm.size),
        "rank_action_counts_scope": "per-rank local; do_not_sum_across_ranks",
        "input_preflight_allgathers": 1,
        "result_consensus_allgathers": 1,
        "max_rank_setup_wall_seconds": max(wall_values),
        "constraint_lu_factorizations_owner": int(
            modal_solver._constraint_lu_factorizations_owner
        ),
        "constraint_lu_solve_attempts_by_rank": {
            str(row["rank"]): row["constraint_lu_solve_attempts"] for row in rank_results
        },
        "constraint_lu_solve_attempts_at_owner_during_gate": next(
            row["constraint_lu_solve_attempts"]
            for row in rank_results
            if row["rank"] == modal_solver._modal_owner
        ),
        "gmres_solver_and_final_check_budget_unchanged": {
            "solver_matmult_limit": int(modal_solver.solver_matmult_limit),
            "total_matmult_limit_including_final": int(modal_solver.total_matmult_limit),
        },
        "original_side_apply_count_scope": (
            "per-side rank-local SideBalancedInverse; fixed-H6 gate must not call it"
        ),
        "full_schur_materialized": False,
        "fallback_used": False,
    }
    if marker_callback is not None:
        marker_callback(
            "modal_sample_ready",
            {
                "side": "both",
                "stage": "fixed_h6_modal_feedback_repeat_linearity",
                "status": diagnostics["status"],
                "pass": global_pass,
                "early_sample_gate": diagnostics,
            },
        )
    if not global_pass:
        failures = [
            f"rank {row.get('rank')}: pass={row.get('pass')} "
            f"attempts={row.get('operator_action_attempts')} "
            f"completions={row.get('operator_action_completions')}"
            for row in rank_results
            if row.get("pass") is not True
        ]
        raise ValueError(
            "Fixed-H6 modal feedback repeat/linearity Gate failed; "
            + "; ".join(failures)
        )
    return diagnostics

def create_side_balh_block_ldu_preconditioner(
    layout: HybridAugmentedLayout,
    bottom_system: Any,
    top_system: Any,
    coupling: HybridInternalModeCoupling,
    bottom_side_inverse: Any,
    top_side_inverse: Any,
    *,
    sampled_columns: Sequence[int] | None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None,
    sampled_column_contract_sha256: str | None,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    use_anderson_modal_inner: bool = False,
    complex_qr_research: bool = False,
    raw_metric_mixing: bool = False,
    capture_modal_solve_trace: bool = False,
    fixed_h6_modal_gmres_research: bool = False,
) -> HybridBlockLduPreconditioner:
    """Build the sampled Schur or one explicitly selected BAL_H research path.

    The side inverses are nonlinear finite-response operators from the H1e
    candidate path.  The default sampled response columns define only an
    approximate preconditioner Schur. The Anderson and fixed-H6 research
    branches require right FGMRES and remain mutually exclusive. The caller
    owns both side inverses and all side systems.
    """

    from .physical_balanced_side_inverse import SideBalancedInverse

    side_entries = (
        ("bottom", bottom_system, bottom_side_inverse),
        ("top", top_system, top_side_inverse),
    )
    for side, system, side_inverse in side_entries:
        if not isinstance(side_inverse, SideBalancedInverse):
            raise TypeError(
                f"BAL_H block factory requires a SideBalancedInverse for {side}"
            )
        system_operator = getattr(system, "A", None)
        if not isinstance(system_operator, PETSc.Mat):
            raise TypeError(f"BAL_H {side} system must expose PETSc A")
        if int(side_inverse.operator.handle) != int(system_operator.handle):
            raise ValueError(f"BAL_H {side} inverse operator is not side.A")
        diagnostics = dict(side_inverse.diagnostics)
        if diagnostics.get("p4_factor_count") != 1:
            raise ValueError(f"BAL_H {side} inverse p4 factor count is not one")
        if diagnostics.get("p6_factor_count") != 0:
            raise ValueError(f"BAL_H {side} inverse cannot own a p6 factor")
        if diagnostics.get("global_direct_factor_count") != 0:
            raise ValueError(f"BAL_H {side} inverse cannot own a global factor")
        if diagnostics.get("nested_iterative_ksp_count") != 1:
            raise ValueError(
                f"BAL_H {side} inverse must expose one live nested KSP"
            )

    if not isinstance(use_anderson_modal_inner, (bool, np.bool_)):
        raise TypeError("Anderson modal inner opt-in must be an explicit boolean.")
    use_anderson_modal_inner = bool(use_anderson_modal_inner)
    if not isinstance(complex_qr_research, (bool, np.bool_)):
        raise TypeError("Complex QR research selection must be an explicit boolean.")
    complex_qr_research = bool(complex_qr_research)
    if not isinstance(raw_metric_mixing, (bool, np.bool_)):
        raise TypeError("Raw-metric Anderson selection must be an explicit boolean.")
    raw_metric_mixing = bool(raw_metric_mixing)
    if not isinstance(capture_modal_solve_trace, (bool, np.bool_)):
        raise TypeError("Modal solve trace capture must be an explicit boolean.")
    capture_modal_solve_trace = bool(capture_modal_solve_trace)
    if not isinstance(fixed_h6_modal_gmres_research, (bool, np.bool_)):
        raise TypeError("Fixed-H6 modal GMRES research must be an explicit boolean.")
    fixed_h6_modal_gmres_research = bool(fixed_h6_modal_gmres_research)
    if fixed_h6_modal_gmres_research and any(
        (
            use_anderson_modal_inner,
            complex_qr_research,
            raw_metric_mixing,
            capture_modal_solve_trace,
        )
    ):
        raise ValueError(
            "Fixed-H6 modal GMRES research is mutually exclusive with all "
            "Anderson modal-inner options."
        )
    if complex_qr_research and not use_anderson_modal_inner:
        raise ValueError(
            "Complex QR research requires the on-demand Anderson modal inner."
        )
    if raw_metric_mixing and not complex_qr_research:
        raise ValueError("Raw-metric mixing requires the complex QR research path.")
    if capture_modal_solve_trace and not (
        use_anderson_modal_inner and complex_qr_research
    ):
        raise ValueError(
            "Modal solve trace capture requires complex QR modal inner research."
        )
    if not use_anderson_modal_inner and not fixed_h6_modal_gmres_research and not all(
        value is not None
        for value in (
            sampled_columns,
            sampled_column_roles,
            sampled_column_contract_sha256,
        )
    ):
        raise ValueError("Sampled Schur metadata is required by the default BAL_H path.")

    modal_schur = None
    modal_system = None
    modal_action = None
    fixed_h6_solver = None
    fixed_h6_adapters: list[Any] = []
    try:
        if use_anderson_modal_inner:
            modal_action = HybridActionModalSchurApply(
                coupling,
                bottom_side_inverse,
                top_side_inverse,
            )
            early_sample_gate = _check_on_demand_modal_sample_repeat(
                modal_action,
                sampled_columns=sampled_columns,
                sampled_column_roles=sampled_column_roles,
                sampled_column_contract_sha256=sampled_column_contract_sha256,
                marker_callback=marker_callback,
            )
            modal_system = HybridActionModalSchurAndersonSystem(
                modal_action,
                modal_owner=layout.modal_owner,
                complex_qr_research=complex_qr_research,
                raw_metric_mixing=raw_metric_mixing,
                capture_modal_solve_trace=capture_modal_solve_trace,
            )
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": "BAL_H_on_demand_modal_anderson",
                "modal_block_name": "on_demand_nonlinear_modal_inner",
                "modal_schur_scope": "not_materialized",
                "not_original_global_operator": True,
                "not_original_reduced_operator": True,
                "borrowed_side_actions": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
                "modal_schur_materialized": False,
                "modal_schur_column_count": 0,
                "full_vs_sample": {
                    "status": "not_applicable",
                    "reason": "full_modal_schur_not_materialized",
                },
                "schur_lu_repeat": {
                    "status": "not_applicable",
                    "reason": "modal_schur_lu_not_constructed",
                },
                "early_sample_gate": early_sample_gate,
            }
        elif fixed_h6_modal_gmres_research:
            original_side_actions = {
                "bottom": bottom_side_inverse,
                "top": top_side_inverse,
            }
            side_counts_before = {
                side: _action_diagnostics(action).get("apply_count")
                for side, action in original_side_actions.items()
            }
            fixed_h6_adapters.append(
                bottom_side_inverse.create_fixed_h6_active_trace_action()
            )
            fixed_h6_adapters.append(
                top_side_inverse.create_fixed_h6_active_trace_action()
            )
            fixed_h6_solver = _FixedH6ModalKrylovSystem(
                coupling,
                fixed_h6_adapters[0],
                fixed_h6_adapters[1],
                modal_owner=layout.modal_owner,
            )
            early_sample_gate = _check_fixed_h6_modal_feedback_repeat_linearity(
                fixed_h6_solver,
                original_side_actions=original_side_actions,
                original_side_apply_counts_before=side_counts_before,
                marker_callback=marker_callback,
            )
            modal_system = _FixedH6ModalGmresResearchBundle(
                fixed_h6_solver,
                fixed_h6_adapters[0],
                fixed_h6_adapters[1],
            )
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": "fixed_h6_modal_gmres_research",
                "modal_block_name": "fixed_h6_surrogate_on_demand_modal_gmres",
                "modal_schur_scope": "not_materialized",
                "modal_block_condition_status": "not_measured",
                "not_original_global_operator": True,
                "not_original_reduced_operator": True,
                "borrowed_side_actions": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
                "modal_schur_materialized": False,
                "modal_schur_column_count": 0,
                "modal_schur_condition": "not_measured",
                "full_vs_sample": {
                    "status": "not_applicable",
                    "reason": "full_modal_schur_not_materialized",
                },
                "schur_lu_repeat": {
                    "status": "not_applicable",
                    "reason": "modal_schur_lu_not_constructed",
                },
                "early_sample_gate": early_sample_gate,
                "setup_gate_included_in_whole_run_work": True,
                "side_apply_counts_before_fixed_h6_branch": side_counts_before,
            }
        else:
            modal_schur = build_hybrid_action_modal_schur(
                coupling,
                bottom_side_inverse,
                top_side_inverse,
                matrix_repeat_tolerance=1.0e-10,
                sampled_columns=sampled_columns,
                sampled_column_roles=sampled_column_roles,
                sampled_column_contract_sha256=sampled_column_contract_sha256,
                modal_batch_size=32,
                early_sample_first=True,
                marker_callback=marker_callback,
            )
            modal_system = modal_schur
            research_inventory = {
                "research_only": True,
                "preconditioner_identity": "BAL_H_side_inverse_response_schur",
                "modal_block_name": (
                    "finite_nonlinear_side_inverse_response_columns"
                ),
                "modal_schur_scope": "approximate_preconditioner_only",
                "not_original_global_operator": True,
                "not_original_reduced_operator": True,
                "borrowed_side_actions": True,
                "global_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "p6_factor_count": 0,
            }
        return HybridBlockLduPreconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            bottom_side_inverse,
            top_side_inverse,
            modal_system,
            research_inventory=research_inventory,
            dynamic_side_inventory=True,
        )
    except BaseException:
        if modal_system is not None:
            modal_system.destroy()
        elif modal_schur is not None:
            modal_schur.destroy()
        elif modal_action is not None:
            modal_action.destroy()
        elif fixed_h6_solver is not None:
            fixed_h6_solver.destroy()
        for action in reversed(fixed_h6_adapters):
            if not action.audit["destroyed"]:
                action.destroy()
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
    sampled_columns: Sequence[int] | None = None,
    sampled_column_roles: Mapping[str, Sequence[str]] | None = None,
    sampled_column_contract_sha256: str | None = None,
    modal_batch_size: int | None = None,
    early_sample_first: bool = False,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
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
    if (
        (modal_batch_size is not None or early_sample_first)
        and not explicit_opt_in
    ):
        raise ValueError("Modal batching requires explicit case opt-in")
    modal_schur = build_hybrid_action_modal_schur(
        coupling,
        bottom_action,
        top_action,
        matrix_repeat_tolerance=matrix_repeat_tolerance,
        sampled_columns=sampled_columns,
        sampled_column_roles=sampled_column_roles,
        sampled_column_contract_sha256=sampled_column_contract_sha256,
        modal_batch_size=modal_batch_size,
        early_sample_first=early_sample_first,
        marker_callback=marker_callback,
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
    """Frozen outer-KSP settings; default FGMRES, opt-in fixed GMRES10."""

    restart: int = 90
    max_it: int = 1000
    threshold: float = 5.0e-9
    initial_guess: str = "zero"
    ksp_type: str = "fgmres"
    fixed_preconditioner: bool = False

    def __post_init__(self) -> None:
        if int(self.restart) <= 0 or int(self.max_it) <= 0:
            raise ValueError("Iterative restart and max_it must be positive.")
        if not np.isfinite(float(self.threshold)) or float(self.threshold) <= 0.0:
            raise ValueError("Iterative threshold must be finite and positive.")
        if self.initial_guess != "zero":
            raise ValueError("Only the zero initial guess is supported.")
        if str(self.ksp_type).lower() not in {"fgmres", "gmres"}:
            raise ValueError("Only FGMRES and GMRES outer KSP types are supported.")
        if str(self.ksp_type).lower() == "gmres" and (
            not self.fixed_preconditioner or int(self.restart) != 10
        ):
            raise ValueError(
                "GMRES is reserved for the fixed-preconditioner restart-10 profile."
            )


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
    timing: dict[str, Any]
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
        modal_constraint = context.modal_constraint
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
    if context.requires_right_fgmres and str(config.ksp_type).lower() != "fgmres":
        raise ValueError(
            "The selected modal inner requires right-preconditioned FGMRES."
        )
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
        inventory = context.inventory
        row = {
            "iteration": int(iteration),
            "reported_relative_residual": float(reported),
            "global_true_relative_residual": float(global_true),
            "bottom_true_relative_residual": float(block["bottom"]),
            "top_true_relative_residual": float(block["top"]),
            "modal_true_relative_residual": float(block["modal"]),
            "pc_apply_count": int(inventory["pc_apply_count"]),
            "bottom_action_apply_count": int(
                inventory["bottom_action_apply_count"]
            ),
            "top_action_apply_count": int(inventory["top_action_apply_count"]),
            "elapsed_seconds": float(time.perf_counter() - started),
        }
        modal_inner = inventory.get("modal_inner_solver")
        if isinstance(modal_inner, dict):
            last_inner = modal_inner.get("last_solve") or {}
            row.update(
                {
                    "modal_inner_solve_count": int(modal_inner["solve_count"]),
                    "modal_inner_s_evaluation_count": int(
                        modal_inner["s_evaluation_count"]
                    ),
                    "modal_inner_not_converged_count": int(
                        modal_inner["not_converged_count"]
                    ),
                    "modal_inner_last_stop_reason": last_inner.get("stop_reason"),
                    "modal_inner_last_raw_residual_norm": last_inner.get(
                        "unscaled_residual_norm"
                    ),
                }
            )
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
        ksp.setType(
            PETSc.KSP.Type.GMRES
            if str(config.ksp_type).lower() == "gmres"
            else PETSc.KSP.Type.FGMRES
        )
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
        actual_ksp_type = str(ksp.getType())

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
            "ksp_type": actual_ksp_type,
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
        inventory.update({"ksp_type": actual_ksp_type, "restart": int(config.restart)})
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
            "ksp_type": actual_ksp_type,
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
    except BaseException:
        modal_system = context.action_modal_schur_system
        if getattr(modal_system, "capture_modal_solve_trace", False):
            context._modal_solve_trace_handoff = (
                modal_system.take_modal_solve_trace_records()
            )
        raise
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
