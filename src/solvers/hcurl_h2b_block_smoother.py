"""Opt-in constrained block smoother for the Task037 H2B slice.

The R2 factor store already contains factors in the reduced independent/master
coordinates of each constrained cell.  This module only supplies the fixed
full-space sweep around those factors: deterministic coloring, multiplicity
weights, identity-row handling, and one exact action after each color
aggregate.  It never materializes a cell expansion or a global matrix.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from typing import Any

import numpy as np


__all__ = (
    "H2BConstrainedBlockSmoother",
    "build_h2b_constrained_block_smoother",
    "H2BP0Factor",
    "select_h2b_p0_class",
    "discover_h2b_p0_touching_cells",
    "group_h2b_p0_touching_cells_by_class",
    "stream_h2b_p0_patch",
    "factorize_h2b_p0_patch",
    "measure_h2b_p0_patch_direction",
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


_H2B_P0_SCHEMA = "task037.extra.h2b.p0.restricted-patch.v1"
_H2B_P0_NONZERO_HEX = frozenset("0123456789abcdef")


def _p0_require_opt_in(task037_extra_h2b: bool) -> None:
    if not bool(task037_extra_h2b):
        raise ValueError("H2B-P0 requires explicit task037_extra_h2b opt-in")


def _p0_sha256_is_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and set(value) <= _H2B_P0_NONZERO_HEX
    )


def _p0_numeric_sha(array: np.ndarray) -> str:
    values = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(values).cast("B")).hexdigest()


def select_h2b_p0_class(
    class_inventory: Sequence[Mapping[str, Any]],
    *,
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    """Select the unique largest R0 class with no local Floquet pattern."""

    _p0_require_opt_in(task037_extra_h2b)
    candidates: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    for item in class_inventory:
        if not isinstance(item, Mapping):
            raise ValueError("H2B-P0 class inventory entry is not a mapping")
        required = (
            "class_id",
            "cell_count",
            "constraint_pattern_entry_count",
            "constraint_pattern_kinds",
            "class_key_sha256",
            "constraint_pattern_sha256",
        )
        if any(key not in item for key in required):
            raise ValueError("H2B-P0 class inventory is missing a required field")
        class_id = item["class_id"]
        cell_count = item["cell_count"]
        entry_count = item["constraint_pattern_entry_count"]
        if (
            type(class_id) is not int
            or type(cell_count) is not int
            or type(entry_count) is not int
            or class_id < 0
            or cell_count <= 0
            or entry_count < 0
            or class_id in seen_ids
        ):
            raise ValueError("H2B-P0 class inventory integer field is invalid")
        seen_ids.add(class_id)
        if not _p0_sha256_is_valid(item["class_key_sha256"]):
            raise ValueError("H2B-P0 class key SHA is invalid")
        if not _p0_sha256_is_valid(item["constraint_pattern_sha256"]):
            raise ValueError("H2B-P0 constraint pattern SHA is invalid")
        kinds = item["constraint_pattern_kinds"]
        if not isinstance(kinds, (list, tuple)) or not all(
            isinstance(kind, str) for kind in kinds
        ):
            raise ValueError("H2B-P0 constraint pattern kinds are invalid")
        if entry_count == 0 and len(kinds) == 0:
            candidates.append(item)
    if not candidates:
        raise ValueError("H2B-P0 has no unconstrained interior class")
    largest = max(int(item["cell_count"]) for item in candidates)
    largest_items = [
        item for item in candidates if int(item["cell_count"]) == largest
    ]
    if len(largest_items) != 1:
        raise ValueError("H2B-P0 largest unconstrained class is not unique")
    selected = largest_items[0]
    return {
        "class_id": int(selected["class_id"]),
        "cell_count": int(selected["cell_count"]),
        "class_key_sha256": str(selected["class_key_sha256"]),
        "constraint_pattern_sha256": str(selected["constraint_pattern_sha256"]),
        "constraint_pattern_entry_count": 0,
        "constraint_pattern_kinds": [],
        "selection_rule": "unique_max_cell_count_with_empty_floquet_pattern",
    }


def _p0_rows_from_reference(reference: Any) -> np.ndarray:
    if isinstance(reference, Mapping):
        if "independent_global_rows" not in reference:
            raise ValueError("H2B-P0 cell reference lacks independent rows")
        value = reference["independent_global_rows"]
    else:
        if not hasattr(reference, "independent_global_rows"):
            raise ValueError("H2B-P0 cell reference lacks independent rows")
        value = reference.independent_global_rows
    rows = np.asarray(value, dtype=np.int64)
    if rows.ndim != 1 or rows.size == 0 or np.unique(rows).size != rows.size:
        raise ValueError("H2B-P0 cell reference rows are invalid")
    return rows


def _p0_patch_rows(value: object) -> np.ndarray:
    rows = np.asarray(value, dtype=np.int64)
    if rows.ndim != 1 or rows.size == 0 or np.unique(rows).size != rows.size:
        raise ValueError("H2B-P0 patch rows must be unique and nonempty")
    return np.ascontiguousarray(rows, dtype=np.int64)


def discover_h2b_p0_touching_cells(
    cell_references: Sequence[Any],
    patch_rows: object,
    *,
    task037_extra_h2b: bool = False,
) -> tuple[int, ...]:
    """Find cells whose expanded master support touches every patch row."""

    _p0_require_opt_in(task037_extra_h2b)
    rows = _p0_patch_rows(patch_rows)
    patch_set = {int(value) for value in rows}
    touching: list[int] = []
    covered: set[int] = set()
    for ordinal, reference in enumerate(cell_references):
        expanded_rows = _p0_rows_from_reference(reference)
        overlap = patch_set.intersection(int(value) for value in expanded_rows)
        if overlap:
            touching.append(int(ordinal))
            covered.update(overlap)
    if covered != patch_set:
        missing = sorted(patch_set - covered)
        raise ValueError(f"H2B-P0 patch rows are not covered: {missing[:4]}")
    return tuple(touching)


def group_h2b_p0_touching_cells_by_class(
    cell_references: Sequence[Any],
    touching_cell_ordinals: Sequence[int],
    *,
    task037_extra_h2b: bool = False,
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """Group touching cells by exact class in first-seen order.

    The returned cell ordinals are sorted within each class.  This is only an
    ordering helper for one-class-at-a-time P0 tensor streaming; it does not
    retain tensors or introduce a cache.
    """

    _p0_require_opt_in(task037_extra_h2b)
    groups: dict[int, list[int]] = {}
    order: list[int] = []
    seen_cells: set[int] = set()
    for value in touching_cell_ordinals:
        ordinal = int(value)
        if ordinal in seen_cells or ordinal < 0 or ordinal >= len(cell_references):
            raise ValueError("H2B-P0 touching cell ordinals are invalid")
        seen_cells.add(ordinal)
        reference = cell_references[ordinal]
        if isinstance(reference, Mapping):
            class_id = reference.get("class_id")
        else:
            class_id = getattr(reference, "class_id", None)
        if type(class_id) is not int or class_id < 0:
            raise ValueError("H2B-P0 cell reference class id is invalid")
        if class_id not in groups:
            groups[class_id] = []
            order.append(class_id)
        groups[class_id].append(ordinal)
    return tuple((class_id, tuple(sorted(groups[class_id]))) for class_id in order)


def _p0_add_restricted_cell(
    patch_matrix: np.ndarray,
    patch_index: Mapping[int, int],
    local_block: np.ndarray,
    expansion: Any,
) -> None:
    block = np.asarray(local_block)
    if block.dtype != np.dtype(np.complex128) or not block.flags.c_contiguous:
        raise ValueError("H2B-P0 local tensor must be C-contiguous complex128")
    if block.ndim != 2 or block.shape[0] != block.shape[1]:
        raise ValueError("H2B-P0 local tensor must be square")
    offsets = np.asarray(expansion.offsets)
    columns = np.asarray(expansion.column_indices)
    coefficients = np.asarray(expansion.coefficients)
    global_rows = np.asarray(expansion.independent_global_rows, dtype=np.int64)
    nloc = int(offsets.size - 1)
    if (
        offsets.ndim != 1
        or columns.ndim != 1
        or coefficients.ndim != 1
        or block.shape != (nloc, nloc)
        or columns.size != coefficients.size
        or int(offsets[-1]) != columns.size
        or global_rows.ndim != 1
        or np.unique(global_rows).size != global_rows.size
        or np.any(columns < 0)
        or np.any(columns >= global_rows.size)
        or not np.all(np.isfinite(coefficients))
    ):
        raise ValueError("H2B-P0 cell expansion is invalid")
    column_to_patch = np.full(global_rows.size, -1, dtype=np.int32)
    for column, global_row in enumerate(global_rows):
        position = patch_index.get(int(global_row))
        if position is not None:
            column_to_patch[column] = int(position)
    work = np.zeros((nloc, patch_matrix.shape[0]), dtype=np.complex128)
    for local_column in range(nloc):
        start, stop = int(offsets[local_column]), int(offsets[local_column + 1])
        for position in range(start, stop):
            patch_column = int(column_to_patch[int(columns[position])])
            if patch_column >= 0:
                work[:, patch_column] += block[:, local_column] * coefficients[position]
    for local_row in range(nloc):
        start, stop = int(offsets[local_row]), int(offsets[local_row + 1])
        for position in range(start, stop):
            patch_row = int(column_to_patch[int(columns[position])])
            if patch_row >= 0:
                patch_matrix[patch_row, :] += (
                    np.conjugate(coefficients[position]) * work[local_row, :]
                )


def stream_h2b_p0_patch(
    cell_references: Sequence[Any],
    patch_rows: object,
    oriented_cell_stream: Iterable[tuple[int, np.ndarray, Any]],
    *,
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    """Stream oriented cell tensors into one row-complete patch matrix.

    ``oriented_cell_stream`` is consumed once.  It yields a canonical cell
    ordinal, one borrowed oriented tensor, and its sparse R2 expansion; no
    per-cell tensor or dense expansion is retained by this function.
    """

    _p0_require_opt_in(task037_extra_h2b)
    rows = _p0_patch_rows(patch_rows)
    touching = discover_h2b_p0_touching_cells(
        cell_references, rows, task037_extra_h2b=True
    )
    patch_index = {int(row): index for index, row in enumerate(rows)}
    matrix = np.zeros((rows.size, rows.size), dtype=np.complex128)
    required = set(touching)
    seen: set[int] = set()
    for cell_ordinal, local_block, expansion in oriented_cell_stream:
        ordinal = int(cell_ordinal)
        if ordinal not in required:
            continue
        if ordinal in seen or ordinal < 0 or ordinal >= len(cell_references):
            raise ValueError("H2B-P0 cell stream has a duplicate or invalid cell")
        reference_rows = _p0_rows_from_reference(cell_references[ordinal])
        expansion_rows = np.asarray(expansion.independent_global_rows, dtype=np.int64)
        if not np.array_equal(reference_rows, expansion_rows):
            raise ValueError("H2B-P0 expansion rows differ from cell reference")
        _p0_add_restricted_cell(matrix, patch_index, local_block, expansion)
        seen.add(ordinal)
    if seen != required:
        raise ValueError("H2B-P0 tensor stream omitted a touching cell")
    return {
        "schema": _H2B_P0_SCHEMA,
        "patch_rows": tuple(int(row) for row in rows),
        "patch_row_count": int(rows.size),
        "touching_cell_ordinals": tuple(touching),
        "touching_cell_count": len(touching),
        "matrix": matrix,
        "matrix_sha256": _p0_numeric_sha(matrix),
        "matrix_shape": tuple(int(value) for value in matrix.shape),
        "matrix_dtype": str(matrix.dtype),
        "matrix_nbytes": int(matrix.nbytes),
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "per_cell_factor": False,
        "slab_factor": False,
        "schur_materialized": False,
    }


def _p0_rhs(size: int, phase: float) -> np.ndarray:
    values = np.asarray(
        [1.0 + phase * index + 1j * (0.23 - 0.011 * index) for index in range(size)],
        dtype=np.complex128,
    )
    return values / np.linalg.norm(values)


def _p0_lu_reconstruction(lu: np.ndarray, pivots: np.ndarray) -> np.ndarray:
    lower = np.tril(lu, -1) + np.eye(lu.shape[0], dtype=np.complex128)
    upper = np.triu(lu)
    reconstructed = lower @ upper
    pivot_values = np.asarray(pivots, dtype=np.int64)
    for row in range(pivot_values.size - 1, -1, -1):
        pivot = int(pivot_values[row])
        if row != int(pivot):
            reconstructed[[row, int(pivot)], :] = reconstructed[
                [int(pivot), row], :
            ]
    return reconstructed


@dataclass(frozen=True)
class H2BP0Factor:
    """One retained LU for the single P0 row-complete patch."""

    values: np.ndarray
    pivots: np.ndarray
    matrix_sha256: str
    factor_values_sha256: str
    pivot_sha256: str
    factorization_residual: float
    solve_residual: float
    finite: bool
    deterministic: bool
    pivot_growth: float
    reciprocal_condition_estimate: float
    condition_estimate: float
    solve_gains: tuple[float, float]

    def __post_init__(self) -> None:
        values = np.asarray(self.values, dtype=np.complex128)
        pivots = np.asarray(self.pivots)
        if values.ndim != 2 or values.shape[0] != values.shape[1]:
            raise ValueError("H2B-P0 LU values must be square")
        if pivots.ndim != 1 or pivots.size != values.shape[0]:
            raise ValueError("H2B-P0 pivots have the wrong shape")
        values = np.array(values, dtype=np.complex128, copy=True, order="C")
        pivots = np.array(pivots, dtype=np.int32, copy=True, order="C")
        values.setflags(write=False)
        pivots.setflags(write=False)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "pivots", pivots)
        reciprocal = float(self.reciprocal_condition_estimate)
        condition = float(self.condition_estimate)
        if (
            not np.isfinite(reciprocal)
            or not 0.0 < reciprocal <= 1.0 + 1.0e-12
            or not np.isfinite(condition)
            or condition < 1.0 - 1.0e-12
        ):
            raise ValueError("H2B-P0 condition estimates are invalid")

    @property
    def factor_bytes(self) -> int:
        return int(self.values.nbytes + self.pivots.nbytes)

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        from scipy.linalg import lu_solve

        values = np.asarray(rhs)
        if (
            values.dtype != np.dtype(np.complex128)
            or not values.flags.c_contiguous
            or values.ndim != 1
            or values.size != self.values.shape[0]
            or not np.all(np.isfinite(values))
        ):
            raise ValueError("H2B-P0 solve RHS must be C-contiguous complex128")
        result = lu_solve((self.values, self.pivots), values)
        result = np.ascontiguousarray(result, dtype=np.complex128)
        if not np.all(np.isfinite(result)):
            raise ValueError("H2B-P0 solve returned nonfinite values")
        return result


def factorize_h2b_p0_patch(
    matrix: np.ndarray,
    *,
    task037_extra_h2b: bool = False,
) -> H2BP0Factor:
    """Factor one finite row-complete patch and audit repeated LU exactly."""

    _p0_require_opt_in(task037_extra_h2b)
    from scipy.linalg import lapack, lu_factor, lu_solve

    original = np.asarray(matrix)
    if (
        original.dtype != np.dtype(np.complex128)
        or not original.flags.c_contiguous
        or original.ndim != 2
        or original.shape[0] != original.shape[1]
        or original.shape[0] == 0
        or not np.all(np.isfinite(original))
    ):
        raise ValueError("H2B-P0 patch matrix must be finite C-contiguous complex128")
    matrix_sha = _p0_numeric_sha(original)
    first_values, first_pivots = lu_factor(
        np.array(original, copy=True, order="C"),
        overwrite_a=True,
        check_finite=False,
    )
    second_values, second_pivots = lu_factor(
        np.array(original, copy=True, order="C"),
        overwrite_a=True,
        check_finite=False,
    )
    deterministic = bool(
        np.array_equal(first_values, second_values)
        and np.array_equal(first_pivots, second_pivots)
    )
    del second_values, second_pivots
    if not deterministic:
        raise ValueError("H2B-P0 repeated LU factorization is not deterministic")
    first_values = np.ascontiguousarray(first_values, dtype=np.complex128)
    first_pivots = np.ascontiguousarray(first_pivots, dtype=np.int32)
    if (
        not np.all(np.isfinite(first_values))
        or not np.all(np.abs(np.diag(first_values)) > 0.0)
    ):
        raise ValueError("H2B-P0 patch LU is nonfinite or singular")
    reconstructed = _p0_lu_reconstruction(first_values, first_pivots)
    factorization_residual = float(
        np.linalg.norm(reconstructed - original)
        / max(float(np.linalg.norm(original)), np.finfo(float).tiny)
    )
    upper = np.triu(first_values)
    pivot_growth = float(
        np.max(np.abs(upper))
        / max(float(np.max(np.abs(original))), np.finfo(float).tiny)
    )
    gecon = lapack.get_lapack_funcs(("gecon",), (first_values,))[0]
    reciprocal_condition_estimate, info = gecon(
        first_values, float(np.linalg.norm(original, 1))
    )
    reciprocal_condition_estimate = float(reciprocal_condition_estimate)
    if (
        int(info) != 0
        or not np.isfinite(reciprocal_condition_estimate)
        or reciprocal_condition_estimate <= 0.0
        or reciprocal_condition_estimate > 1.0 + 1.0e-12
    ):
        raise ValueError("H2B-P0 LAPACK condition estimate failed")
    condition_estimate = 1.0 / reciprocal_condition_estimate
    if not np.isfinite(condition_estimate):
        raise ValueError("H2B-P0 condition estimate is nonfinite")
    rhs_a = _p0_rhs(original.shape[0], 0.017)
    rhs_b = _p0_rhs(original.shape[0], 0.023)
    solutions = tuple(
        np.ascontiguousarray(
            lu_solve((first_values, first_pivots), rhs), dtype=np.complex128
        )
        for rhs in (rhs_a, rhs_b)
    )
    if not all(np.all(np.isfinite(solution)) for solution in solutions):
        raise ValueError("H2B-P0 LU solve returned nonfinite values")
    solve_residual = max(
        float(
            np.linalg.norm(original @ solution - rhs)
            / max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        )
        for rhs, solution in zip((rhs_a, rhs_b), solutions, strict=True)
    )
    gains = tuple(
        float(np.linalg.norm(solution) / np.linalg.norm(rhs))
        for rhs, solution in zip((rhs_a, rhs_b), solutions, strict=True)
    )
    return H2BP0Factor(
        values=first_values,
        pivots=first_pivots,
        matrix_sha256=matrix_sha,
        factor_values_sha256=_p0_numeric_sha(first_values),
        pivot_sha256=_p0_numeric_sha(first_pivots),
        factorization_residual=factorization_residual,
        solve_residual=solve_residual,
        finite=True,
        deterministic=deterministic,
        pivot_growth=pivot_growth,
        reciprocal_condition_estimate=reciprocal_condition_estimate,
        condition_estimate=condition_estimate,
        solve_gains=gains,
    )


def measure_h2b_p0_patch_direction(
    rhs: np.ndarray,
    patch_matrix: np.ndarray,
    factor: H2BP0Factor,
    patch_rows: object,
    exact_action: Callable[[np.ndarray, np.ndarray], None],
    *,
    closure_matrix: np.ndarray | None = None,
    task037_extra_h2b: bool = False,
) -> dict[str, Any]:
    """Measure the official patch-row oracle and full-space spill diagnostic."""

    _p0_require_opt_in(task037_extra_h2b)
    values = np.asarray(rhs)
    rows = _p0_patch_rows(patch_rows)
    matrix = np.asarray(patch_matrix)
    closure_operator = (
        matrix if closure_matrix is None else np.asarray(closure_matrix)
    )
    if (
        values.dtype != np.dtype(np.complex128)
        or not values.flags.c_contiguous
        or values.ndim != 1
        or not np.all(np.isfinite(values))
        or matrix.dtype != np.dtype(np.complex128)
        or not matrix.flags.c_contiguous
        or matrix.shape != (rows.size, rows.size)
        or closure_operator.dtype != np.dtype(np.complex128)
        or not closure_operator.flags.c_contiguous
        or closure_operator.shape != (rows.size, rows.size)
        or factor.values.shape != matrix.shape
    ):
        raise ValueError("H2B-P0 patch oracle inputs are invalid")
    patch_rhs = np.ascontiguousarray(values[rows], dtype=np.complex128)
    rhs_norm = float(np.linalg.norm(patch_rhs))
    if not np.isfinite(rhs_norm) or rhs_norm <= np.finfo(float).tiny:
        raise ValueError("H2B-P0 patch RHS is zero or nonfinite")
    solution = factor.solve(patch_rhs)
    correction = np.zeros_like(values)
    correction[rows] = solution
    action_output = np.empty_like(values)
    exact_action(correction, action_output)
    if (
        action_output.dtype != np.dtype(np.complex128)
        or not action_output.flags.c_contiguous
        or not np.all(np.isfinite(action_output))
    ):
        raise ValueError("H2B-P0 exact action returned invalid values")
    patch_output = np.ascontiguousarray(action_output[rows], dtype=np.complex128)
    expected_patch_output = np.ascontiguousarray(
        closure_operator @ solution, dtype=np.complex128
    )
    solved_patch_output = np.ascontiguousarray(matrix @ solution, dtype=np.complex128)
    q_norm = float(np.linalg.norm(patch_output))
    if not np.isfinite(q_norm) or q_norm <= np.finfo(float).tiny:
        raise ValueError("H2B-P0 patch action is zero or nonfinite")
    patch_norm = float(np.linalg.norm(expected_patch_output))
    closure = float(
        np.linalg.norm(patch_output - expected_patch_output)
        / max(q_norm, np.finfo(float).tiny)
    )
    inner = np.vdot(patch_output, patch_rhs)
    omega = complex(inner / np.vdot(patch_output, patch_output))
    residual = patch_rhs - omega * patch_output
    rho_star = float(np.linalg.norm(residual) / rhs_norm)
    rho_unit = float(np.linalg.norm(patch_rhs - patch_output) / rhs_norm)
    eta = float(abs(inner) / max(q_norm * rhs_norm, np.finfo(float).tiny))
    operator_mismatch = float(
        np.linalg.norm(solved_patch_output - expected_patch_output)
        / max(patch_norm, np.finfo(float).tiny)
    )
    full_rhs_norm = float(np.linalg.norm(values))
    full_inner = np.vdot(action_output, values)
    full_omega = complex(full_inner / np.vdot(action_output, action_output))
    full_residual = values - full_omega * action_output
    full_rho_star = float(np.linalg.norm(full_residual) / full_rhs_norm)
    full_rho_unit = float(np.linalg.norm(values - action_output) / full_rhs_norm)
    full_eta = float(
        abs(full_inner)
        / max(float(np.linalg.norm(action_output)) * full_rhs_norm, np.finfo(float).tiny)
    )
    outside = np.ones(values.size, dtype=bool)
    outside[rows] = False
    off_patch_spill_norm = float(np.linalg.norm(action_output[outside]))
    return {
        "schema": _H2B_P0_SCHEMA,
        "patch_row_count": int(rows.size),
        "rhs_sha256": _p0_numeric_sha(patch_rhs),
        "correction_sha256": _p0_numeric_sha(correction),
        "action_sha256": _p0_numeric_sha(action_output),
        "r_norm": rhs_norm,
        "q_norm": q_norm,
        "rho_unit": rho_unit,
        "rho_star": rho_star,
        "eta": eta,
        "omega_real": float(omega.real),
        "omega_imag": float(omega.imag),
        "omega_abs": float(abs(omega)),
        "correction_norm": float(np.linalg.norm(solution)),
        "correction_amplification": float(np.linalg.norm(solution) / rhs_norm),
        "exact_action_relative_error": closure,
        "element_operator_mismatch_relative": operator_mismatch,
        "off_patch_spill_norm": off_patch_spill_norm,
        "off_patch_spill_ratio": float(
            off_patch_spill_norm / max(q_norm, np.finfo(float).tiny)
        ),
        "full_space_rho_star": full_rho_star,
        "full_space_rho_unit": full_rho_unit,
        "full_space_eta": full_eta,
        "full_space_rho_scope": "diagnostic_only",
        "external_slave_mask": False,
        "rho_scope": "patch_rows_only",
    }
