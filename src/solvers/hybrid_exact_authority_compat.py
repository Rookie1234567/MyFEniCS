"""Small V4 compatibility audit for frozen exact-side authority outputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from petsc4py import PETSc


V4_EXACT_AUTHORITY_LABELS = (
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)
V4_EXACT_AUTHORITY_FAILURE = "EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F"
V4_EXACT_AUTHORITY_PASS = "EXACT_AUTHORITY_COMPATIBLE_WITH_CURRENT_BARE_F"

__all__ = (
    "V4_EXACT_AUTHORITY_FAILURE",
    "V4_EXACT_AUTHORITY_LABELS",
    "V4_EXACT_AUTHORITY_PASS",
    "audit_exact_authority_petsc",
)


def _operator_identity(
    operator: PETSc.Mat,
    name: str,
) -> dict[str, Any]:
    rows, columns = map(int, operator.getSize())
    identity = {
        "name": name,
        "semantic": "explicit bare components.F"
        if name == "bare_f"
        else "system.A = F - C H^-1 D action",
        "petsc_type": str(operator.getType()),
        "shape": [rows, columns],
        "global_size": [rows, columns],
        "local_size": list(map(int, operator.getLocalSize())),
        "ownership_range": list(map(int, operator.getOwnershipRange())),
        "block_size": int(operator.getBlockSize()),
        "matrix_free": str(operator.getType()).lower() in {"python", "shell"},
    }
    if name == "a_side":
        identity["action_identity"] = "system.A = F - C H^-1 D"
    return identity


def _apply_residual(
    operator: PETSc.Mat,
    exact: PETSc.Vec,
    rhs: PETSc.Vec,
) -> tuple[float, float, bool]:
    first = rhs.duplicate()
    repeat = rhs.duplicate()
    difference = rhs.duplicate()
    try:
        operator.mult(exact, first)
        operator.mult(exact, repeat)
        difference.waxpy(PETSc.ScalarType(-1.0), repeat, first)
        rhs_norm = float(rhs.norm())
        residual = first.duplicate()
        try:
            first.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            residual_relative = float(residual.norm()) / max(rhs_norm, 1.0e-30)
        finally:
            residual.destroy()
        repeat_relative = float(difference.norm()) / max(float(first.norm()), 1.0e-30)
        finite = bool(
            np.isfinite(rhs_norm)
            and np.isfinite(residual_relative)
            and np.isfinite(repeat_relative)
        )
        return residual_relative, repeat_relative, finite
    finally:
        difference.destroy()
        repeat.destroy()
        first.destroy()


def audit_exact_authority_petsc(
    bare_f: PETSc.Mat,
    side_operator: PETSc.Mat,
    rhs_vectors: Mapping[str, PETSc.Vec],
    exact_vectors: Mapping[str, PETSc.Vec],
    *,
    source_metadata: Mapping[str, Mapping[str, Any]],
    exact_output_identity_sha256: Mapping[str, str],
    identity: Mapping[str, Any],
    bare_matrix_hash: Callable[[PETSc.Mat], str],
    labels: Sequence[str] = V4_EXACT_AUTHORITY_LABELS,
) -> dict[str, Any]:
    """Compare frozen exact outputs against bare ``F`` and explanatory ``A``.

    ``side_operator`` is recorded as the historical explanatory
    ``A_side = F - C H^-1 D`` action.  It never substitutes for the bare-F
    residual Gate.  The helper intentionally owns no factors or interface
    data; all five vectors are borrowed and remain caller-owned.
    """

    labels = tuple(labels)
    if labels != V4_EXACT_AUTHORITY_LABELS:
        raise ValueError("V4 exact authority labels are not the frozen five labels")
    if set(rhs_vectors) != set(labels) or set(exact_vectors) != set(labels):
        raise ValueError("V4 exact authority vectors do not cover the frozen labels")
    if set(source_metadata) != set(labels):
        raise ValueError("V4 RHS probe metadata does not cover the frozen labels")
    if set(exact_output_identity_sha256) != set(labels):
        raise ValueError("V4 exact-output identities do not cover the frozen labels")

    bare_hash_before = str(bare_matrix_hash(bare_f))
    reports: list[dict[str, Any]] = []
    for label in labels:
        bare_relative, bare_repeat, bare_finite = _apply_residual(
            bare_f, exact_vectors[label], rhs_vectors[label]
        )
        side_relative, side_repeat, side_finite = _apply_residual(
            side_operator, exact_vectors[label], rhs_vectors[label]
        )
        reports.append(
            {
                "label": label,
                "source_probe_metadata": dict(source_metadata[label]),
                "exact_output_identity_sha256": str(
                    exact_output_identity_sha256[label]
                ),
                "bare_f": {
                    "residual_relative": bare_relative,
                    "repeat_relative": bare_repeat,
                    "finite": bare_finite,
                },
                "a_side_explanatory": {
                    "residual_relative": side_relative,
                    "repeat_relative": side_repeat,
                    "finite": side_finite,
                },
            }
        )
    bare_hash_after = str(bare_matrix_hash(bare_f))
    bare_pass = all(
        row["bare_f"]["finite"] is True and row["bare_f"]["residual_relative"] <= 1.0e-9
        for row in reports
    )
    all_finite = all(
        row["bare_f"]["finite"] is True and row["a_side_explanatory"]["finite"] is True
        for row in reports
    )
    repeat_pass = all(
        row["bare_f"]["repeat_relative"] <= 1.0e-12
        and row["a_side_explanatory"]["repeat_relative"] <= 1.0e-12
        for row in reports
    )
    bare_unchanged = bare_hash_before == bare_hash_after
    gate_pass = bool(bare_pass and all_finite and repeat_pass and bare_unchanged)
    return {
        "schema": "task040.v4.exact_authority_compatibility.v1",
        "labels": list(labels),
        "identity": dict(identity),
        "operator_identity": {
            "bare_f": _operator_identity(bare_f, "bare_f"),
            "a_side": _operator_identity(side_operator, "a_side"),
            "bare_f_hash_before": bare_hash_before,
            "bare_f_hash_after": bare_hash_after,
            "bare_f_unchanged": bare_hash_before == bare_hash_after,
        },
        "reports": reports,
        "exact_output_vectors_loaded": len(labels),
        "finite_pass": bool(all_finite),
        "bare_f_residual_pass": bool(bare_pass and all_finite),
        "repeat_pass": bool(repeat_pass),
        "bare_f_hash_unchanged_pass": bool(bare_unchanged),
        "factor_inventory": {
            "exact_output_vectors_loaded": len(labels),
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "cross_section_group_factor_count": 0,
            "reduced_dense_factor_count": 0,
            "factor_objects_created": 0,
        },
        "qep_calls": 0,
        "pde_solve": "not_run",
        "cleanup": {
            "factor_objects_created": 0,
            "interface_masses_built": False,
            "packet_built": False,
        },
        "classification": (
            V4_EXACT_AUTHORITY_PASS if gate_pass else V4_EXACT_AUTHORITY_FAILURE
        ),
        "gate_pass": gate_pass,
    }
