"""Research-only exact one-cell traction coupling contracts.

This module contains the small, explicit data boundary between the exact
one-cell endpoint Schur oracle and a Hybrid local interface.  It does not
change ordinary scalar-CG traction behavior and never constructs a dense
endpoint square.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
from petsc4py import PETSc


EXACT_ONE_CELL_TRACTION_MODEL = "full3d_one_cell_exact_schur"
EXACT_ROW_IDENTITY_TOLERANCE = 1.0e-10


def _columns(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 2:
        raise ValueError(f"{name} must be a rank-2 complex array.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite.")
    return array


def congruent_trace_identity(
    exact_columns: Any,
    local_columns: Any,
    *,
    side: str,
    tolerance: float = EXACT_ROW_IDENTITY_TOLERANCE,
) -> dict[str, Any]:
    """Compare exact one-cell and local-interface primal columns.

    The arrays must use the same ordered active trace rows.  A shape mismatch
    is a structural error, while the returned relative discrepancy is the
    numerical identity evidence used by the explicit Task37c lane.
    """

    if side not in {"bottom", "top"}:
        raise ValueError("Trace identity side must be bottom or top.")
    exact = _columns(exact_columns, f"{side} exact columns")
    local = _columns(local_columns, f"{side} local columns")
    if exact.shape != local.shape:
        raise ValueError(
            f"{side} exact/local trace shapes differ: {exact.shape} != {local.shape}."
        )
    scale = max(float(np.linalg.norm(exact)), float(np.linalg.norm(local)), 1.0e-30)
    relative = float(np.linalg.norm(exact - local) / scale)
    return {
        "side": side,
        "rows": int(exact.shape[0]),
        "columns": int(exact.shape[1]),
        "relative_l2": relative,
        "tolerance": float(tolerance),
        "finite": True,
        "pass": bool(relative <= float(tolerance)),
    }


def require_congruent_trace_identity(
    exact_columns: Any,
    local_columns: Any,
    *,
    side: str,
    tolerance: float = EXACT_ROW_IDENTITY_TOLERANCE,
) -> dict[str, Any]:
    """Return identity evidence or fail closed before dual embedding."""

    audit = congruent_trace_identity(
        exact_columns,
        local_columns,
        side=side,
        tolerance=tolerance,
    )
    if audit["pass"] is not True:
        raise RuntimeError(
            f"{side} exact/local primal trace identity failed: "
            f"relative_l2={audit['relative_l2']:.6e}, "
            f"limit={audit['tolerance']:.6e}."
        )
    return audit


def split_exact_local_amplitude_blocks(
    forward_flux: Any,
    backward_flux: Any,
    *,
    left_rows: int,
    right_rows: int,
    forward_factors: Any,
    backward_factors: Any,
) -> dict[str, np.ndarray]:
    """Split exact outward flux into bottom/top local-amplitude blocks."""

    forward = _columns(forward_flux, "forward flux")
    backward = _columns(backward_flux, "backward flux")
    if forward.shape != backward.shape:
        raise ValueError("Forward/backward exact flux shapes differ.")
    expected_rows = int(left_rows) + int(right_rows)
    if forward.shape[0] != expected_rows:
        raise ValueError("Exact flux rows do not match the two endpoint row counts.")
    lam = np.asarray(forward_factors, dtype=np.complex128)
    mu = np.asarray(backward_factors, dtype=np.complex128)
    expected = (forward.shape[1],)
    if lam.shape != expected or mu.shape != expected:
        raise ValueError("Exact propagation factors need one entry per column.")
    if (
        not np.all(np.isfinite(lam))
        or not np.all(np.isfinite(mu))
        or np.any(np.abs(lam) <= 1.0e-14)
        or np.any(np.abs(mu) <= 1.0e-14)
    ):
        raise ValueError("Exact propagation factors must be finite and nonzero.")
    split = int(left_rows)
    return {
        "bottom_forward": forward[:split].copy(),
        "top_forward": (forward[split:] / lam[None, :]).copy(),
        "bottom_backward": (backward[:split] / mu[None, :]).copy(),
        "top_backward": backward[split:].copy(),
    }


def embed_exact_trace_columns_dense_reference(
    local_rows: Any,
    columns: Any,
    *,
    local_fe_rows: int,
) -> np.ndarray:
    """Pure dense reference embedding; production uses owned PETSc insertion."""

    rows = np.asarray(local_rows, dtype=PETSc.IntType)
    values = _columns(columns, "exact trace columns")
    if rows.ndim != 1 or len(np.unique(rows)) != len(rows):
        raise ValueError("Local interface rows must be a unique one-dimensional list.")
    if len(rows) != values.shape[0]:
        raise ValueError("Local interface row count and exact column rows differ.")
    if np.any(rows < 0) or np.any(rows >= int(local_fe_rows)):
        raise ValueError("Exact interface rows lie outside the local FE layout.")
    result = np.zeros((int(local_fe_rows), values.shape[1]), dtype=np.complex128)
    result[rows, :] = values
    return result


@dataclass(frozen=True)
class ExactOneCellCoupling:
    """Four exact blocks plus the auditable row/lifecycle contract."""

    blocks: Mapping[str, np.ndarray]
    bottom_rows: np.ndarray
    top_rows: np.ndarray
    row_identity: Mapping[str, Mapping[str, Any]]
    action_audit: Mapping[str, int]
    dense_endpoint_square_formed: bool = False
    exact_reduced_trace_columns: bool = True
    zero_eliminated_interior_support: bool = True
    transient_released: bool = True

    def __post_init__(self) -> None:
        required = {
            "bottom_forward",
            "top_forward",
            "bottom_backward",
            "top_backward",
        }
        if set(self.blocks) != required:
            raise ValueError(
                "Exact coupling must contain exactly four directional blocks."
            )
        blocks = dict(self.blocks)
        object.__setattr__(self, "blocks", blocks)
        bottom_rows = np.asarray(self.bottom_rows, dtype=PETSc.IntType)
        top_rows = np.asarray(self.top_rows, dtype=PETSc.IntType)
        object.__setattr__(self, "bottom_rows", bottom_rows)
        object.__setattr__(self, "top_rows", top_rows)
        for name, values in blocks.items():
            array = _columns(values, name)
            expected_rows = bottom_rows if name.startswith("bottom") else top_rows
            if array.shape[0] != len(expected_rows):
                raise ValueError(f"{name} does not match its ordered interface rows.")
            blocks[name] = array
        identity = {side: dict(values) for side, values in self.row_identity.items()}
        for side in ("bottom", "top"):
            if side not in identity:
                raise ValueError(f"Exact coupling is missing {side} row identity.")
            for trace_kind in ("positive", "raw_negative"):
                if identity[side].get(trace_kind, {}).get("pass") is not True:
                    raise ValueError(
                        f"{side} {trace_kind} row identity must pass before embedding."
                    )
        object.__setattr__(self, "row_identity", identity)
        action = dict(self.action_audit)
        required_action = {"port_rows", "interior_rows", "interior_matrix_nnz"}
        if set(action) != required_action:
            raise ValueError("Exact coupling action audit has the wrong fields.")
        if any(int(value) < 0 for value in action.values()):
            raise ValueError("Exact coupling action audit cannot be negative.")
        object.__setattr__(self, "action_audit", action)
        if self.dense_endpoint_square_formed:
            raise ValueError(
                "Exact one-cell coupling may not form a dense endpoint square."
            )
        if self.transient_released is not True:
            raise ValueError("Exact one-cell transient owners must be released.")

    @property
    def mode_count(self) -> int:
        return int(self.blocks["bottom_forward"].shape[1])

    def audit(self) -> dict[str, Any]:
        return {
            "model": EXACT_ONE_CELL_TRACTION_MODEL,
            "block_shapes": {
                name: list(values.shape) for name, values in self.blocks.items()
            },
            "bottom_rows": int(len(self.bottom_rows)),
            "top_rows": int(len(self.top_rows)),
            **self.action_audit,
            "dense_endpoint_square_formed": False,
            "exact_reduced_trace_columns": bool(self.exact_reduced_trace_columns),
            "zero_eliminated_interior_support": bool(
                self.zero_eliminated_interior_support
            ),
            "row_identity": dict(self.row_identity),
            "transient_released": bool(self.transient_released),
        }


def exact_model_record(enabled: bool) -> dict[str, Any]:
    """Return explicit model identity without changing ordinary defaults."""

    return {
        "requested": bool(enabled),
        "model": EXACT_ONE_CELL_TRACTION_MODEL if enabled else "ordinary_default",
        "research_only": bool(enabled),
        "production_qualified": False if enabled else None,
    }


__all__ = [
    "EXACT_ONE_CELL_TRACTION_MODEL",
    "EXACT_ROW_IDENTITY_TOLERANCE",
    "ExactOneCellCoupling",
    "congruent_trace_identity",
    "embed_exact_trace_columns_dense_reference",
    "exact_model_record",
    "require_congruent_trace_identity",
    "split_exact_local_amplitude_blocks",
]
