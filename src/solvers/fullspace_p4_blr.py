"""Review V16's opt-in global p4 BLR factor and augmented residual checks.

This module contains only the reusable numerical pieces.  A caller assembles
the already-qualified ``[V, B; -D, H]`` PETSc matrix and owns the stage
resource ledger; no p6 setup or ordinary solver default is changed here.
"""

from __future__ import annotations

from typing import Any

import numpy as np

P4_BLR_PROFILE = "physical_p4_blr_bal_h_v16"
P4_BLR_THRESHOLD = 1.0e-5


def _carrier_entries(carrier: Any) -> tuple[Any, ...]:
    entries = tuple(getattr(carrier, "entries", ()))
    if not entries:
        raise ValueError("p4 BLR residual identity requires non-empty DtN carrier entries")
    return entries


def native_a4_residual_from_augmented(
    top_residual: Any,
    port_residual: Any,
    carrier: Any,
    *,
    volume_rows: int | None = None,
) -> np.ndarray:
    """Recover ``g-A4*c`` from the non-Hermitian augmented residual.

    For ``mathcal A4=[[V,B],[-D,H]]``, the port residual is
    ``e_port = D*c-H*alpha``.  Consequently the native residual is
    ``e_top-B*H^{-1}*e_port``.  The implementation uses the stored carrier
    signs and values directly; it never substitutes ``B.conj().T`` for ``D``.
    """

    top = np.ascontiguousarray(np.asarray(top_residual, dtype=np.complex128))
    port = np.ascontiguousarray(np.asarray(port_residual, dtype=np.complex128)).reshape(-1)
    if top.ndim != 1:
        raise ValueError("augmented top residual must be one-dimensional")
    entries = _carrier_entries(carrier)
    if port.shape != (len(entries),):
        raise ValueError("augmented port residual has the wrong number of entries")
    if volume_rows is not None and top.size != int(volume_rows):
        raise ValueError("augmented top residual has the wrong p4 storage size")
    if not np.all(np.isfinite(top)) or not np.all(np.isfinite(port)):
        raise ValueError("augmented residual contains non-finite values")
    result = top.copy()
    for index, entry in enumerate(entries):
        rows = np.asarray(entry.coupling_rows, dtype=np.int64).reshape(-1)
        values = np.asarray(entry.coupling_values, dtype=np.complex128).reshape(-1)
        if rows.shape != values.shape:
            raise ValueError("p4 DtN coupling rows/values have different shapes")
        if np.any(rows < 0) or np.any(rows >= result.size):
            raise ValueError("p4 DtN coupling row is outside the volume residual")
        diagonal = complex(entry.normalization_h)
        if not np.isfinite(diagonal.real) or not np.isfinite(diagonal.imag) or diagonal == 0:
            raise ValueError("p4 DtN normalization is not finite and nonzero")
        # This is B*H^{-1}*e_port.  No conjugation is intentional: the
        # augmented system is non-Hermitian when the DtN carrier is complex.
        result[rows] -= values * (port[index] / diagonal)
    return result


def augmented_residual_identity(
    native_residual: Any,
    top_residual: Any,
    port_residual: Any,
    carrier: Any,
    *,
    rhs_norm: float,
    native_action_norm: float,
) -> dict[str, Any]:
    """Compare independent native/augmented residuals on the operator scale.

    ``rhs_norm`` and ``native_action_norm`` are the norms of the actual
    ``g`` and ``A4*c`` used for the native residual.  They are required so a
    rounding-level identity difference is not divided by an already tiny
    residual.  The residual-only ratio remains a diagnostic, never the gate.
    """

    rhs_norm = float(rhs_norm)
    native_action_norm = float(native_action_norm)
    if (
        not np.isfinite(rhs_norm)
        or not np.isfinite(native_action_norm)
        or rhs_norm < 0.0
        or native_action_norm < 0.0
    ):
        raise ValueError("identity scale norms must be finite and non-negative")

    expected = native_a4_residual_from_augmented(top_residual, port_residual, carrier)
    actual = np.ascontiguousarray(np.asarray(native_residual, dtype=np.complex128)).reshape(-1)
    if actual.shape != expected.shape:
        raise ValueError("native and augmented residual shapes differ")
    difference = actual - expected
    # This is an operator-identity check, not the native solve gate.  Scaling
    # by the residual itself would make a correct zero RHS look ill-conditioned
    # and would hide cancellation.  The top term plus the explicitly formed
    # port correction is a conservative operation scale; the residual-relative
    # value is retained only as a diagnostic.
    top_array = np.ascontiguousarray(
        np.asarray(top_residual, dtype=np.complex128)
    ).reshape(-1)
    correction = top_array - expected
    operation_scale = max(
        rhs_norm + native_action_norm,
        float(np.linalg.norm(top_array)) + float(np.linalg.norm(correction)),
        np.finfo(float).tiny,
    )
    absolute_difference = float(np.linalg.norm(difference))
    relative = absolute_difference / operation_scale if operation_scale else 0.0
    residual_relative = absolute_difference / max(
        float(np.linalg.norm(actual)), np.finfo(float).tiny
    )
    return {
        "schema": "task039extra.v16.p4-augmented-residual-identity.v1",
        "relative": relative,
        "residual_relative_diagnostic": residual_relative,
        "absolute_difference": absolute_difference,
        "operation_scale": operation_scale,
        "limit": 1.0e-10,
        "passed": bool(np.isfinite(relative) and relative <= 1.0e-10),
        "formula": "g-A4*c = e_top - B*H^{-1}*e_port",
        "port_sign": "augmented lower-left=-D; e_port=D*c-H*alpha",
        "uses_conjugate_transpose_for_D": False,
        "native_residual_norm": float(np.linalg.norm(actual)),
        "derived_residual_norm": float(np.linalg.norm(expected)),
        "rhs_norm": rhs_norm,
        "native_action_norm": native_action_norm,
    }


__all__ = [
    "P4_BLR_PROFILE",
    "P4_BLR_THRESHOLD",
    "augmented_residual_identity",
    "native_a4_residual_from_augmented",
]
