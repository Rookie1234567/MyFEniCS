"""Opt-in constrained block smoother for the Task037 H2B slice.

The R2 factor store already contains factors in the reduced independent/master
coordinates of each constrained cell.  This module only supplies the fixed
full-space sweep around those factors: deterministic coloring, multiplicity
weights, identity-row handling, and one exact action after each color
aggregate.  It never materializes a cell expansion or a global matrix.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import hashlib
from typing import Any

import numpy as np


__all__ = (
    "H2BConstrainedBlockSmoother",
    "build_h2b_constrained_block_smoother",
)


_H2B_SCHEMA = "task037.extra.h2b.constrained-block-smoother.v1"
_COMPLEX128_BYTES = np.dtype(np.complex128).itemsize


def _require_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _array_digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(repr(tuple(int(value) for value in contiguous.shape)).encode("ascii"))
        digest.update(memoryview(contiguous).cast("B"))
    return digest.hexdigest()


def _as_rows(value: object, global_row_count: int, cell_id: int) -> np.ndarray:
    rows = np.asarray(value, dtype=np.int64)
    if rows.ndim != 1 or rows.size == 0:
        raise ValueError(f"H2B cell {cell_id} has no independent rows")
    if np.any(rows < 0) or np.any(rows >= global_row_count):
        raise ValueError(f"H2B cell {cell_id} has an out-of-range row")
    if np.unique(rows).size != rows.size:
        raise ValueError(f"H2B cell {cell_id} repeats an independent row")
    return rows


def _fixed_identity() -> dict[str, Any]:
    return {
        "fine_space": "uncondensed_fullspace",
        "condensation": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "B2_B4_local_krylov_used": False,
        "fullspace_patch_pc_used": True,
        "interior_recovery_required": False,
        "ordinary_default_changed": False,
    }


class H2BConstrainedBlockSmoother:
    """One fixed forward/reverse color sweep over R2 constrained factors.

    ``action`` is intentionally a plain in-place callback.  It receives a
    full-space correction with zero slave entries and writes the exact B0
    action to ``target``.  No plugin interface or alternate backend is
    introduced in this stage.
    """

    def __init__(
        self,
        factor_store: Any,
        *,
        global_row_count: int,
        owned_slave_identity_rows: Sequence[int],
        action: Callable[[np.ndarray, np.ndarray], None],
        task037_extra_h2b: bool,
    ) -> None:
        if not bool(task037_extra_h2b):
            raise ValueError("H2B smoother requires explicit task037 opt-in")
        if not callable(action):
            raise TypeError("H2B action must be an in-place callable")
        if isinstance(global_row_count, bool) or int(global_row_count) <= 0:
            raise ValueError("H2B global row count must be positive")
        self._global_row_count = int(global_row_count)
        self._action = action
        self._factor_store = factor_store
        self._cells = tuple(factor_store.cells)
        if not self._cells:
            raise ValueError("H2B smoother needs at least one cell reference")

        self._cell_rows = tuple(
            _as_rows(cell.independent_global_rows, self._global_row_count, cell_id)
            for cell_id, cell in enumerate(self._cells)
        )
        self._slave_rows = np.asarray(
            owned_slave_identity_rows, dtype=np.int64
        )
        if self._slave_rows.ndim != 1:
            raise ValueError("H2B slave identity rows must be one-dimensional")
        if np.any(self._slave_rows < 0) or np.any(
            self._slave_rows >= self._global_row_count
        ):
            raise ValueError("H2B slave identity row is out of range")
        if np.unique(self._slave_rows).size != self._slave_rows.size:
            raise ValueError("H2B slave identity rows must be unique")
        self._slave_rows = np.unique(self._slave_rows)
        self._independent_rows = np.unique(np.concatenate(self._cell_rows))
        if np.intersect1d(self._independent_rows, self._slave_rows).size:
            raise ValueError("H2B cell coverage contains a slave identity row")
        expected_slaves = np.setdiff1d(
            np.arange(self._global_row_count, dtype=np.int64),
            self._independent_rows,
        )
        if not np.array_equal(expected_slaves, self._slave_rows):
            raise ValueError(
                "H2B cell coverage complement does not equal slave identity rows"
            )

        factor_audit = factor_store.audit
        factor_payload = factor_audit["factor_plus_metadata_bytes"]
        self._factor_payload_bytes = _require_nonnegative_int(
            factor_payload, "factor_plus_metadata_bytes"
        )
        for key, expected in (
            ("per_cell_factor_count", 0),
            ("slab_factor_count", 0),
            ("global_matrix_materialized", False),
            ("global_constraint_matrix_materialized", False),
            ("schur_materialized", False),
        ):
            if factor_audit[key] is not expected:
                raise ValueError(f"H2B factor store has forbidden {key}")

        self._color_of_cell, self._color_offsets, self._color_cells = (
            self._build_coloring()
        )
        self._multiplicity, pou_error = self._build_multiplicity()
        if not np.isfinite(pou_error) or pou_error > 1.0e-14:
            raise ValueError("H2B partition-of-unity closure failed")
        self._pou_closure_error = float(pou_error)

        self._max_independent_count = max(rows.size for rows in self._cell_rows)
        self._working_residual = np.empty(
            self._global_row_count, dtype=np.complex128
        )
        self._correction = np.empty(self._global_row_count, dtype=np.complex128)
        self._color_delta = np.empty(self._global_row_count, dtype=np.complex128)
        self._action_output = np.empty(
            self._global_row_count, dtype=np.complex128
        )
        self._last_action_count = 0
        self._total_action_count = 0
        self._apply_count = 0
        self._last_strategy = "symmetric"

    def _build_coloring(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        row_color_mask = np.zeros(self._global_row_count, dtype=np.uint64)
        colors = np.empty(len(self._cell_rows), dtype=np.int32)
        for cell_id, rows in enumerate(self._cell_rows):
            blocked = np.bitwise_or.reduce(row_color_mask[rows])
            available = (~int(blocked)) & ((1 << 64) - 1)
            if available == 0:
                raise ValueError("H2B deterministic coloring needs more than 64 colors")
            color = (available & -available).bit_length() - 1
            colors[cell_id] = color
            row_color_mask[rows] |= np.uint64(1) << np.uint64(color)
        del row_color_mask

        color_count = int(np.max(colors)) + 1
        color_counts = np.bincount(colors, minlength=color_count).astype(
            np.int32, copy=False
        )
        offsets = np.empty(color_count + 1, dtype=np.int32)
        offsets[0] = 0
        np.cumsum(color_counts, dtype=np.int32, out=offsets[1:])
        cells = np.argsort(colors, kind="stable").astype(np.int32, copy=False)
        for color in range(color_count):
            cell_ids = cells[offsets[color] : offsets[color + 1]]
            if cell_ids.size < 2:
                continue
            rows = np.concatenate(tuple(self._cell_rows[int(cell)] for cell in cell_ids))
            if np.unique(rows).size != rows.size:
                raise ValueError("H2B coloring contains an overlapping color")
        colors.setflags(write=False)
        offsets.setflags(write=False)
        cells.setflags(write=False)
        return colors, offsets, cells

    def _build_multiplicity(self) -> tuple[np.ndarray, float]:
        multiplicity = np.zeros(self._global_row_count, dtype=np.int32)
        for rows in self._cell_rows:
            np.add.at(multiplicity, rows, 1)
        if np.any(multiplicity[self._independent_rows] <= 0):
            raise ValueError("H2B independent row has zero multiplicity")
        partition_sum = np.zeros(self._global_row_count, dtype=np.float64)
        for rows in self._cell_rows:
            np.add.at(partition_sum, rows, 1.0 / multiplicity[rows])
        closure = float(
            np.max(np.abs(partition_sum[self._independent_rows] - 1.0))
        )
        multiplicity.setflags(write=False)
        return multiplicity, closure

    @property
    def color_of_cell(self) -> np.ndarray:
        return self._color_of_cell.copy()

    @property
    def color_offsets(self) -> np.ndarray:
        return self._color_offsets.copy()

    @property
    def color_cells(self) -> np.ndarray:
        return self._color_cells.copy()

    @property
    def multiplicity(self) -> np.ndarray:
        return self._multiplicity.copy()

    @property
    def last_residual(self) -> np.ndarray:
        return self._working_residual.copy()

    @property
    def last_correction(self) -> np.ndarray:
        return self._correction.copy()

    def _prepare_rhs(self, rhs: np.ndarray) -> None:
        if not isinstance(rhs, np.ndarray):
            raise TypeError("H2B residual must be a NumPy array")
        values = rhs
        if values.dtype != np.dtype(np.complex128) or not values.flags.c_contiguous:
            raise ValueError(
                "H2B residual must be a C-contiguous complex128 array"
            )
        if values.shape != (self._global_row_count,):
            raise ValueError("H2B residual has the wrong full-space row count")
        if not np.all(np.isfinite(values)):
            raise ValueError("H2B residual must be finite")

        self._working_residual[:] = values
        self._working_residual[self._slave_rows] = 0.0
        self._correction.fill(0.0)
        self._correction[self._slave_rows] = values[self._slave_rows]
        self._last_action_count = 0

    def _apply_strategy(self, rhs: np.ndarray, strategy: str) -> np.ndarray:
        self._prepare_rhs(rhs)
        color_count = self._color_offsets.size - 1
        if strategy == "additive":
            color_ranges = (range(1),)
        elif strategy == "forward":
            color_ranges = (range(color_count),)
        elif strategy == "symmetric":
            color_ranges = (
                range(color_count),
                range(color_count - 1, -1, -1),
            )
        else:
            raise ValueError("H2B S0 strategy must be additive, forward, or symmetric")

        initial_residual = (
            self._working_residual.copy() if strategy == "additive" else None
        )
        for color_range in color_ranges:
            for color in color_range:
                self._color_delta.fill(0.0)
                if strategy == "additive":
                    cell_positions = range(len(self._cells))
                else:
                    start = int(self._color_offsets[color])
                    stop = int(self._color_offsets[color + 1])
                    cell_positions = self._color_cells[start:stop]
                for cell_position in cell_positions:
                    cell_id = int(cell_position)
                    rows = self._cell_rows[cell_id]
                    class_id = int(self._cells[cell_id].class_id)
                    source = (
                        self._working_residual
                        if initial_residual is None
                        else initial_residual
                    )
                    local_rhs = source[rows]
                    solved = self._factor_store.solve(class_id, local_rhs)
                    if (
                        not isinstance(solved, np.ndarray)
                        or solved.dtype != np.dtype(np.complex128)
                        or not solved.flags.c_contiguous
                        or not solved.flags.writeable
                        or solved.shape != rows.shape
                        or not np.all(np.isfinite(solved))
                    ):
                        raise ValueError("H2B factor solve returned invalid values")
                    solved /= self._multiplicity[rows]
                    self._correction[rows] += solved
                    if strategy != "additive":
                        self._color_delta[rows] = solved
                    del local_rhs, solved

                if strategy == "additive":
                    self._color_delta[:] = self._correction
                    self._color_delta[self._slave_rows] = 0.0
                else:
                    self._color_delta[self._slave_rows] = 0.0
                self._action(self._color_delta, self._action_output)
                if not np.all(np.isfinite(self._action_output)):
                    raise ValueError("H2B exact action returned nonfinite values")
                self._working_residual -= self._action_output
                self._last_action_count += 1

        del initial_residual
        self._total_action_count += self._last_action_count
        self._apply_count += 1
        self._last_strategy = strategy
        return self._correction.copy()

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        """Apply exactly one forward and one reverse fixed-unit sweep."""

        return self._apply_strategy(rhs, "symmetric")

    def apply_s0(self, rhs: np.ndarray, strategy: str) -> np.ndarray:
        """Apply one of the three fixed H2B-S0 combinations."""

        return self._apply_strategy(rhs, strategy)

    @property
    def audit(self) -> dict[str, Any]:
        color_digest = _array_digest(
            self._color_of_cell, self._color_offsets, self._color_cells
        )
        retained_components = {
            "color_of_cell_bytes": int(self._color_of_cell.nbytes),
            "color_offsets_bytes": int(self._color_offsets.nbytes),
            "color_cells_bytes": int(self._color_cells.nbytes),
            "multiplicity_bytes": int(self._multiplicity.nbytes),
            "working_residual_bytes": int(self._working_residual.nbytes),
            "correction_bytes": int(self._correction.nbytes),
            "color_delta_bytes": int(self._color_delta.nbytes),
            "action_output_bytes": int(self._action_output.nbytes),
            "slave_identity_rows_bytes": int(self._slave_rows.nbytes),
            "independent_rows_bytes": int(self._independent_rows.nbytes),
        }
        retained_work = int(sum(retained_components.values()))
        transient_components = {
            "returned_correction_copy_bytes": int(
                self._global_row_count * _COMPLEX128_BYTES
            ),
            "maximum_local_rhs_bytes": int(
                self._max_independent_count * _COMPLEX128_BYTES
            ),
            "maximum_local_solve_bytes": int(
                self._max_independent_count * _COMPLEX128_BYTES
            ),
        }
        transient_bound = int(sum(transient_components.values()))
        factor_plus_work = int(
            self._factor_payload_bytes + retained_work + transient_bound
        )
        covered_multiplicity = self._multiplicity[self._independent_rows]
        color_count = self._color_offsets.size - 1
        expected_action_count = {
            "additive": 1,
            "forward": color_count,
            "symmetric": 2 * color_count,
        }[self._last_strategy]
        return {
            "schema": _H2B_SCHEMA,
            "task037_extra_h2b": True,
            "global_row_count": self._global_row_count,
            "independent_row_count": int(self._independent_rows.size),
            "slave_identity_row_count": int(self._slave_rows.size),
            "color_count": int(self._color_offsets.size - 1),
            "color_digest": color_digest,
            "coloring_deterministic": True,
            "same_color_rows_disjoint": True,
            "multiplicity_min": int(np.min(covered_multiplicity)),
            "multiplicity_max": int(np.max(covered_multiplicity)),
            "partition_of_unity_closure_error": self._pou_closure_error,
            "factor_count": int(self._factor_store.audit["unique_factor_count"]),
            "factor_payload_bytes": self._factor_payload_bytes,
            "factor_payload_basis": self._factor_store.audit[
                "factor_plus_metadata_basis"
            ],
            "retained_work_components": retained_components,
            "retained_work_bytes": retained_work,
            "per_apply_transient_components": transient_components,
            "per_apply_transient_bound_bytes": transient_bound,
            "factor_plus_work_bytes": factor_plus_work,
            "factor_plus_work_limit_bytes": 500_000_000,
            "action_count": int(self._last_action_count),
            "expected_action_count": int(expected_action_count),
            "total_action_count": int(self._total_action_count),
            "apply_count": int(self._apply_count),
            "last_strategy": self._last_strategy,
            "identity": _fixed_identity(),
            "materialization_identity": {
                "global_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "cell_schur_matrix_materialized": False,
                "slab_matrix_materialized": False,
                "schur_materialized": False,
                "per_cell_factor": False,
                "per_cell_dense_c": False,
                "ksp_created": False,
                "dtn_used": False,
                "pde_solve_called": False,
            },
        }


def build_h2b_constrained_block_smoother(
    factor_store: Any,
    *,
    global_row_count: int,
    owned_slave_identity_rows: Sequence[int],
    action: Callable[[np.ndarray, np.ndarray], None],
    task037_extra_h2b: bool = False,
) -> H2BConstrainedBlockSmoother:
    """Build the fixed H2B smoother only with explicit task opt-in."""

    return H2BConstrainedBlockSmoother(
        factor_store,
        global_row_count=global_row_count,
        owned_slave_identity_rows=owned_slave_identity_rows,
        action=action,
        task037_extra_h2b=task037_extra_h2b,
    )
