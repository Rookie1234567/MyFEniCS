"""Opt-in constrained local expansion for the Task037 H2A-R2 slice.

This module owns only the local algebra needed to represent one constrained
cell block.  A cell retains a CSR-like expansion and its actual independent
global rows; it does not retain a dense expansion matrix.  Dense ``C`` and
``C^H B C`` arrays are materialized only for the representative setup/test
operation.  No global matrix, Schur complement, or factor cache is built here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

import numpy as np

__all__ = (
    "H2AR2CellExpansion",
    "build_h2a_r2_cell_expansion",
    "build_h2a_r2_transformed_block",
)

R2_NONZERO_TOLERANCE = 1.0e-14


def _phase_for_kind(
    kind: str,
    *,
    phase_x: complex,
    phase_y: complex,
    phase_corner: complex | None,
) -> complex:
    if kind == "x":
        return complex(phase_x)
    if kind == "y":
        return complex(phase_y)
    if kind == "corner":
        return (
            complex(phase_corner)
            if phase_corner is not None
            else complex(phase_x) * complex(phase_y)
        )
    raise ValueError(f"Unsupported Floquet phase kind {kind!r}")


def _complex_pair(value: complex) -> tuple[float, float]:
    value = complex(value)
    if not np.isfinite(value.real) or not np.isfinite(value.imag):
        raise ValueError("R2 expansion coefficients must be finite")
    return float(value.real), float(value.imag)


def _pattern_payload(
    *,
    nloc: int,
    independent_count: int,
    offsets: np.ndarray,
    column_indices: np.ndarray,
    coefficients: np.ndarray,
) -> tuple[Any, ...]:
    return (
        "task037-extra-r2-expansion-v1",
        ("nloc", int(nloc)),
        ("canonical_independent_count", int(independent_count)),
        ("row_offsets", tuple(int(value) for value in offsets)),
        ("canonical_column_indices", tuple(int(value) for value in column_indices)),
        (
            "complex_coefficients",
            tuple(_complex_pair(value) for value in coefficients),
        ),
    )


def _pattern_sha256(payload: tuple[Any, ...]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class H2AR2CellExpansion:
    """Retained sparse ``C_c`` metadata for one cell.

    ``column_indices`` are canonical first-appearance column ordinals.  The
    corresponding absolute rows are kept only in ``independent_global_rows``
    for later vector gather/scatter and are excluded from the pattern identity.
    """

    offsets: np.ndarray
    column_indices: np.ndarray
    coefficients: np.ndarray
    independent_global_rows: np.ndarray
    pattern_identity: tuple[Any, ...]
    pattern_sha256: str

    def __post_init__(self) -> None:
        offsets = np.asarray(self.offsets, dtype=np.int32)
        columns = np.asarray(self.column_indices, dtype=np.int32)
        coefficients = np.asarray(self.coefficients, dtype=np.complex128)
        global_rows = np.asarray(self.independent_global_rows, dtype=np.int64)
        if offsets.ndim != 1 or offsets.size == 0 or int(offsets[0]) != 0:
            raise ValueError("R2 expansion offsets must start at zero")
        if int(offsets[-1]) != columns.size or columns.size != coefficients.size:
            raise ValueError("R2 expansion CSR arrays have inconsistent sizes")
        if np.any(np.diff(offsets) < 0) or np.any(columns < 0):
            raise ValueError("R2 expansion CSR indices must be nonnegative")
        if np.any(columns >= global_rows.size) and columns.size:
            raise ValueError("R2 expansion column ordinal is out of range")
        if np.unique(global_rows).size != global_rows.size:
            raise ValueError("R2 independent global rows must be unique")
        if not np.all(np.isfinite(coefficients)):
            raise ValueError("R2 expansion coefficients must be finite")
        identity = tuple(self.pattern_identity)
        actual_identity = _pattern_payload(
            nloc=offsets.size - 1,
            independent_count=global_rows.size,
            offsets=offsets,
            column_indices=columns,
            coefficients=coefficients,
        )
        if identity != actual_identity:
            raise ValueError("R2 expansion pattern identity does not match CSR arrays")
        if _pattern_sha256(actual_identity) != str(self.pattern_sha256):
            raise ValueError("R2 expansion pattern hash mismatch")
        offsets.setflags(write=False)
        columns.setflags(write=False)
        coefficients.setflags(write=False)
        global_rows.setflags(write=False)
        object.__setattr__(self, "offsets", offsets)
        object.__setattr__(self, "column_indices", columns)
        object.__setattr__(self, "coefficients", coefficients)
        object.__setattr__(self, "independent_global_rows", global_rows)
        object.__setattr__(self, "pattern_identity", identity)

    @property
    def nloc(self) -> int:
        return int(self.offsets.size - 1)

    @property
    def independent_count(self) -> int:
        return int(self.independent_global_rows.size)

    @property
    def nnz(self) -> int:
        return int(self.coefficients.size)

    def materialize_dense(self) -> np.ndarray:
        """Create a temporary dense ``C_c`` for one representative operation."""

        dense = np.zeros(
            (self.nloc, self.independent_count),
            dtype=np.complex128,
        )
        for row in range(self.nloc):
            start, stop = int(self.offsets[row]), int(self.offsets[row + 1])
            dense[row, self.column_indices[start:stop]] = self.coefficients[
                start:stop
            ]
        return dense


def build_h2a_r2_cell_expansion(
    blocks: Iterable[Any],
    cell_local_dofs: Sequence[int],
    index_map: Any,
    *,
    index_map_bs: int,
    phase_x: complex,
    phase_y: complex,
    phase_corner: complex | None = None,
) -> H2AR2CellExpansion:
    """Build one sparse constrained expansion from real Floquet block data.

    Local rows are mapped to absolute global rows only for gather/scatter.  A
    slave row uses exactly one ``kind`` phase multiplied by its row of the
    phase-independent coefficient transform.  Blocks not fully touching this
    cell are ignored, which permits passing the full topology block iterable.
    """

    if int(index_map_bs) != 1:
        raise ValueError("R2 Nedelec expansion requires index_map_bs == 1")
    local_rows = tuple(int(value) for value in cell_local_dofs)
    if not local_rows or len(set(local_rows)) != len(local_rows):
        raise ValueError("R2 cell local DoF rows must be unique and nonempty")
    local_array = np.asarray(local_rows, dtype=np.int32)
    global_array = np.asarray(index_map.local_to_global(local_array), dtype=np.int64)
    if global_array.shape != local_array.shape:
        raise ValueError("R2 local_to_global returned an unexpected shape")
    ordinal_by_local = {value: ordinal for ordinal, value in enumerate(local_rows)}

    slave_rows: dict[int, tuple[int, Any, complex]] = {}
    cell_row_set = set(local_rows)
    for block in blocks:
        block_local = tuple(int(value) for value in block.slave_local_dofs)
        if not block_local or not all(value in cell_row_set for value in block_local):
            continue
        transform = np.asarray(block.coefficient_transform, dtype=np.complex128)
        masters = tuple(int(value) for value in block.master_global_dofs)
        if transform.shape != (len(block_local), len(masters)):
            raise ValueError("R2 Floquet transform shape does not match block")
        phase = _phase_for_kind(
            str(block.kind),
            phase_x=phase_x,
            phase_y=phase_y,
            phase_corner=phase_corner,
        )
        for row_index, local_row in enumerate(block_local):
            if local_row in slave_rows:
                raise ValueError(f"R2 local slave row {local_row} is duplicated")
            ordinal = ordinal_by_local[local_row]
            if int(block.slave_global_dofs[row_index]) != int(global_array[ordinal]):
                raise ValueError("R2 slave local/global row mapping disagrees")
            slave_rows[local_row] = (row_index, block, phase)

    global_to_column: dict[int, int] = {}
    independent_rows: list[int] = []
    offsets = [0]
    columns: list[int] = []
    values: list[complex] = []
    for ordinal, local_row in enumerate(local_rows):
        row_terms: dict[int, complex] = {}
        slave = slave_rows.get(local_row)
        if slave is None:
            terms = ((int(global_array[ordinal]), 1.0 + 0.0j),)
        else:
            row_index, block, phase = slave
            terms = tuple(
                (
                    int(master),
                    complex(phase * transform_value),
                )
                for master, transform_value in zip(
                    block.master_global_dofs,
                    np.asarray(block.coefficient_transform, dtype=np.complex128)[
                        row_index, :
                    ],
                    strict=True,
                )
                if abs(complex(phase * transform_value)) > R2_NONZERO_TOLERANCE
            )
            if not terms:
                raise RuntimeError("An R2 Floquet constraint row has no masters")
        for global_row, coefficient in terms:
            column = global_to_column.get(global_row)
            if column is None:
                column = len(independent_rows)
                global_to_column[global_row] = column
                independent_rows.append(global_row)
            row_terms[column] = row_terms.get(column, 0.0 + 0.0j) + coefficient
        active_row_terms = tuple(
            (column, coefficient)
            for column, coefficient in row_terms.items()
            if coefficient != 0.0 + 0.0j
        )
        if not active_row_terms:
            raise RuntimeError("An R2 aggregated constraint row has no masters")
        for column, coefficient in active_row_terms:
            columns.append(column)
            values.append(coefficient)
        offsets.append(len(columns))

    offsets_array = np.asarray(offsets, dtype=np.int32)
    columns_array = np.asarray(columns, dtype=np.int32)
    values_array = np.asarray(values, dtype=np.complex128)
    identity = _pattern_payload(
        nloc=len(local_rows),
        independent_count=len(independent_rows),
        offsets=offsets_array,
        column_indices=columns_array,
        coefficients=values_array,
    )
    return H2AR2CellExpansion(
        offsets=offsets_array,
        column_indices=columns_array,
        coefficients=values_array,
        independent_global_rows=np.asarray(independent_rows, dtype=np.int64),
        pattern_identity=identity,
        pattern_sha256=_pattern_sha256(identity),
    )


def build_h2a_r2_transformed_block(
    local_block: np.ndarray,
    expansion: H2AR2CellExpansion,
) -> np.ndarray:
    """Materialize temporary ``C_c^H B_c C_c`` for one representative block."""

    block = np.asarray(local_block, dtype=np.complex128)
    if block.shape != (expansion.nloc, expansion.nloc):
        raise ValueError("R2 local block shape does not match cell expansion")
    if not np.all(np.isfinite(block)):
        raise ValueError("R2 local block must be finite")
    dense_expansion = expansion.materialize_dense()
    transformed = dense_expansion.conj().T @ block @ dense_expansion
    if not np.all(np.isfinite(transformed)):
        raise ValueError("R2 transformed local block is not finite")
    return np.asarray(transformed, dtype=np.complex128)
