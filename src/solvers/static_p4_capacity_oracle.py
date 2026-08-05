"""Research-only dense p4 capacity oracle over a factor-free p6 action.

The oracle constructs only the local p4 projection needed by the F0
capacity experiment.  Its p6 operator is an owner-local action, so no p6
slab matrix or factor is retained.  A dense complex p4 factor is intentional
here: it is a bounded capacity measurement, not a production solver path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import scipy.linalg

from .static_trace_auxiliary import OwnerLocalTraceTransfer

__all__ = (
    "P4CapacityOracle",
    "build_p4_capacity_oracle",
    "local_transfer_matrix",
)


def local_transfer_matrix(
    transfer: OwnerLocalTraceTransfer,
    row_global_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Materialize one small owner-local transfer from its row stencils."""

    rows = np.asarray(row_global_ids, dtype=np.int64)
    positions = np.searchsorted(transfer.row_global_ids, rows)
    if np.any(positions >= transfer.row_global_ids.size) or np.any(
        transfer.row_global_ids[positions] != rows
    ):
        raise ValueError("requested transfer rows are not owner-local")
    columns = np.unique(
        np.concatenate(
            [
                transfer.column_ids[
                    transfer.row_offsets[position] : transfer.row_offsets[position + 1]
                ]
                for position in positions
            ]
        )
    )
    matrix = np.zeros((len(rows), len(columns)), dtype=np.complex128)
    for row, position in enumerate(positions):
        start = int(transfer.row_offsets[position])
        end = int(transfer.row_offsets[position + 1])
        source_columns = transfer.column_ids[start:end]
        matrix[row, np.searchsorted(columns, source_columns)] = transfer.values[
            start:end
        ]
    return columns, matrix


@dataclass
class P4CapacityOracle:
    """One-cell/slab F0 p4 projection and dense capacity factor."""

    slab: int
    p6_row_ids: np.ndarray
    p4_row_ids: np.ndarray
    p2_row_ids: np.ndarray
    p46: np.ndarray
    p24: np.ndarray
    a4: np.ndarray
    a2: np.ndarray
    combined_diagonal: np.ndarray
    fine_pc: Any = field(repr=False)
    _lu: tuple[np.ndarray, np.ndarray] = field(repr=False)
    audit: dict[str, Any]

    def solve_p4(self, values: np.ndarray) -> np.ndarray:
        """Solve the bounded dense p4 capacity factor."""

        return scipy.linalg.lu_solve(self._lu, np.asarray(values, dtype=np.complex128))

    def correction(self, values: np.ndarray) -> np.ndarray:
        """Return ``P46 A4^-1 P46^H v + D6^-1 v``."""

        rhs = np.asarray(values, dtype=np.complex128)
        return self.p46 @ self.solve_p4(self.p46.conj().T @ rhs) + (
            rhs / self.combined_diagonal
        )

    def action(self, values: np.ndarray) -> np.ndarray:
        """Apply the borrowed factor-free p6 action used to build A4."""

        return self.fine_pc.restricted_action(self.slab, values)

    def destroy(self) -> None:
        """Release the bounded dense capacity-oracle arrays."""

        self.p46 = np.empty((0, 0), dtype=np.complex128)
        self.p24 = np.empty((0, 0), dtype=np.complex128)
        self.a4 = np.empty((0, 0), dtype=np.complex128)
        self.a2 = np.empty((0, 0), dtype=np.complex128)
        self.combined_diagonal = np.empty(0, dtype=np.complex128)
        self._lu = (
            np.empty((0, 0), dtype=np.complex128),
            np.empty(0, dtype=np.int32),
        )


def build_p4_capacity_oracle(
    fine_pc: Any,
    slab: int,
    p46_transfer: OwnerLocalTraceTransfer,
    p24_transfer: OwnerLocalTraceTransfer,
    combined_diagonal: np.ndarray,
) -> P4CapacityOracle:
    """Build ``A4=P46ᴴA6P46`` and ``A2=P24ᴴA4P24`` for F0."""

    p6_row_ids = np.asarray(fine_pc.plan.owner_rows[slab], dtype=np.int64)
    p4_row_ids, p46 = local_transfer_matrix(p46_transfer, p6_row_ids)
    p2_row_ids, p24 = local_transfer_matrix(p24_transfer, p4_row_ids)
    diagonal = np.asarray(combined_diagonal, dtype=np.complex128)
    if diagonal.size != p6_row_ids.size:
        raise ValueError("combined p6 diagonal is not aligned with slab rows")
    a4 = np.empty((p46.shape[1], p46.shape[1]), dtype=np.complex128)
    for column in range(p46.shape[1]):
        p6_column = p46[:, column]
        a6_column = fine_pc.restricted_action(slab, p6_column)
        a4[:, column] = p46.conj().T @ a6_column
    a2 = p24.conj().T @ a4 @ p24
    lu, piv = scipy.linalg.lu_factor(a4)
    transfer_bytes = int(p46.nbytes + p24.nbytes)
    itemsize = np.dtype(np.complex128).itemsize
    p4_p2_workspace_bytes = int(p46.shape[1] * p24.shape[1] * itemsize)
    column_action_workspace_bytes = int((p46.shape[0] + p46.shape[1]) * itemsize)
    retained_payload_bytes = int(
        p46.nbytes
        + p24.nbytes
        + a4.nbytes
        + a2.nbytes
        + lu.nbytes
        + piv.nbytes
        + diagonal.nbytes
    )
    audit = {
        "research_only": True,
        "capacity_oracle": True,
        "slab": int(slab),
        "p6_slab_rows": int(p6_row_ids.size),
        "p4_trace_factor_rows": int(p4_row_ids.size),
        "p2_trace_factor_rows": int(p2_row_ids.size),
        "p4_matrix_shape": tuple(map(int, a4.shape)),
        "p4_matrix_nnz": int(np.count_nonzero(a4)),
        "p4_factor_nnz": int(np.count_nonzero(lu)),
        "p4_lu_payload_bytes": int(lu.nbytes + piv.nbytes),
        "p4_matrix_payload_bytes": int(a4.nbytes),
        "p46_transfer_nnz": int(np.count_nonzero(p46)),
        "p24_transfer_nnz": int(np.count_nonzero(p24)),
        "transfer_payload_bytes": transfer_bytes,
        "retained_oracle_payload_bytes": retained_payload_bytes,
        "construction_workspace_lower_bound_bytes": int(
            max(p4_p2_workspace_bytes, column_action_workspace_bytes)
        ),
        "p6_slab_matrix_materialized": False,
        "p6_slab_matrix_count": 0,
        "p6_slab_matrix_nnz": 0,
        "p6_factor_count": 0,
        "p6_factor_nnz": 0,
        "global_p6_matrix_materialized": False,
        "global_p6_factor_materialized": False,
        "operator_kind": "P46H_restricted_p6_action_P46",
        "correction_kind": "P46_A4_inverse_P46H_plus_D6_inverse",
    }
    return P4CapacityOracle(
        slab=int(slab),
        p6_row_ids=p6_row_ids,
        p4_row_ids=p4_row_ids,
        p2_row_ids=p2_row_ids,
        p46=p46,
        p24=p24,
        a4=a4,
        a2=a2,
        combined_diagonal=diagonal,
        fine_pc=fine_pc,
        _lu=(lu, piv),
        audit=audit,
    )
