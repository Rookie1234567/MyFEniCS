"""Action-only Hybrid block-LDU preconditioner and tight iterative solve."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from mpi4py import MPI
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
        early_difference = sampled_first - sampled_second
        early_reference_norm = float(np.linalg.norm(sampled_first))
        early_difference_norm = float(np.linalg.norm(early_difference))
        early_column_absolute = [
            float(np.linalg.norm(early_difference[:, index]))
            for index in range(len(sampled))
        ]
        early_column_relative = [
            float(
                early_column_absolute[index]
                / max(float(np.linalg.norm(sampled_first[:, index])), _TINY)
            )
            for index in range(len(sampled))
        ]
        early_finite = bool(
            np.all(np.isfinite(sampled_first))
            and np.all(np.isfinite(sampled_second))
            and np.all(np.isfinite(early_difference))
        )
        early_sample_diagnostics = {
            "absolute_difference": early_difference_norm,
            "reference_norm": early_reference_norm,
            "difference_norm": early_difference_norm,
            "relative_error": early_difference_norm
            / max(early_reference_norm, _TINY),
            "max_abs": float(np.max(np.abs(early_difference))),
            "max_column_absolute_difference": max(early_column_absolute),
            "max_column_relative_error": max(early_column_relative),
            "finite": early_finite,
            "limit": 1.0e-10,
            "pass": bool(
                early_finite
                and early_difference_norm / max(early_reference_norm, _TINY)
                <= 1.0e-10
                and max(early_column_relative) <= 1.0e-10
            ),
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
        if str(self.ksp_type).lower() == "gmres":
            if not self.fixed_preconditioner or int(self.restart) != 10:
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
