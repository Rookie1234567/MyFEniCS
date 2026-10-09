"""Small stage gates for the Task40 V20 single-q numeric resource pilot."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

import numpy as np


V20_SELECTED_Q = 0
V20_PHYSICAL_RHS_LIMIT = 1.0e-8


def _array_sha256(value: np.ndarray) -> str:
    array = np.asarray(value)
    if not array.flags.c_contiguous:
        array = np.ascontiguousarray(array)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def require_v20_symbolic_admission(
    factors: Any, q_matrices: Mapping[int, Any], *, q_count: int
) -> dict[str, Any]:
    """Reject any numeric attempt until every registered q is symbolic-ready."""

    audit = factors.audit
    required_q = set(range(int(q_count)))
    numeric_attempts = int(audit.get("numeric_factor_build_attempt_count", -1))
    if (
        audit.get("all_q_symbolic_covered") is not True
        or set(q_matrices) != required_q
        or numeric_attempts != 0
        or bool(factors.factors)
        or bool(factors.matrices)
    ):
        raise RuntimeError(
            "V20 one-q numeric admission requires all-q CSR and symbolic coverage "
            "with zero numeric attempts and an empty one-q slot"
        )
    return {
        "all_q_symbolic_covered": True,
        "symbolic_q_coverage": sorted(required_q),
        "numeric_factor_build_attempt_count_before_selected_q": numeric_attempts,
        "one_q_factor_slot_empty_before_selected_q": True,
    }


def validate_v20_one_q_numeric_audit(
    audit: Mapping[str, Any], *, selected_q: int = V20_SELECTED_Q
) -> list[int]:
    numeric_qs = sorted({int(row["q"]) for row in audit.get("factor_tests", ())})
    attempts = int(audit.get("numeric_factor_build_attempt_count", -1))
    if (
        audit.get("all_q_symbolic_covered") is not True
        or numeric_qs != [int(selected_q)]
        or attempts != 1
    ):
        raise RuntimeError(
            "V20 one-q numeric stage must build exactly the selected q factor "
            "after complete all-q symbolic coverage"
        )
    return numeric_qs


def run_v20_one_q_physical_rhs(
    inverse: Any,
    factors: Any,
    full_physical_rhs: Any,
    *,
    physical_rhs_facts: Mapping[str, Any],
    q_count: int,
    selected_q: int = V20_SELECTED_Q,
    residual_limit: float = V20_PHYSICAL_RHS_LIMIT,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Factor one declared q and solve its production-folded physical RHS values."""

    q_matrices = factors.csr_matrices
    admission = require_v20_symbolic_admission(
        factors, q_matrices, q_count=q_count
    )
    if type(selected_q) is not int or selected_q != V20_SELECTED_Q:
        raise ValueError("V20 resource pilot is predeclared for q0 only")

    from src.solvers.augmented_reference_correction import stable_euclidean_norm

    raw_arrays: dict[str, np.ndarray] = {}
    sector_rows = []
    port_rhs = np.zeros(inverse.mode_count, dtype=np.complex128)
    for modal in inverse.iter_q_modal_rhs(
        full_physical_rhs, port_rhs=port_rhs, q_index=selected_q
    ):
        q = int(modal["q"])
        if q != selected_q:
            raise RuntimeError("V20 q-specific RHS iterator yielded an undeclared q")
        rhs = np.asarray(modal["rhs"], dtype=np.complex128)
        solution = factors.solve(
            q, rhs, category="startup_rhs_mat_solve_count"
        )
        residual = np.asarray(q_matrices[q] @ solution - rhs, dtype=np.complex128)
        rhs_norm = stable_euclidean_norm(rhs)
        residual_norm = stable_euclidean_norm(residual)
        relative = (
            residual_norm / rhs_norm
            if rhs_norm > 0.0
            else (0.0 if residual_norm == 0.0 else float("inf"))
        )
        if not np.isfinite(relative) or relative > residual_limit:
            raise FloatingPointError(
                f"V20 q={q} physical startup RHS residual failed: "
                f"{relative} > {residual_limit}"
            )
        sector = int(modal["sector_index"])
        prefix = f"q{q}_sector{sector}"
        raw_arrays[f"{prefix}_physical_rhs"] = rhs.copy()
        raw_arrays[f"{prefix}_solution"] = np.asarray(solution, dtype=np.complex128).copy()
        raw_arrays[f"{prefix}_true_residual"] = residual.copy()
        sector_rows.append(
            {
                "q": q,
                "sector_index": sector,
                "twist_index": int(modal["twist_index"]),
                "branch": int(modal["branch"]),
                "mode_indices": [int(value) for value in modal["mode_indices"]],
                "local_fe_rhs_norm": float(modal["fe_rhs_norm"]),
                "local_port_rhs_norm": float(modal["port_rhs_norm"]),
                "modal_rhs_rows": int(rhs.size),
                "modal_rhs_sha256": _array_sha256(rhs),
                "solution_sha256": _array_sha256(solution),
                "true_residual_sha256": _array_sha256(residual),
                "rhs_norm": rhs_norm,
                "true_residual_norm": residual_norm,
                "true_residual_relative": float(relative),
                "true_residual_limit": float(residual_limit),
                "passed": True,
            }
        )
        del modal, rhs, solution, residual

    if not sector_rows:
        raise RuntimeError("V20 selected q0 has no folded physical RHS in the registered sectors")
    numeric_qs = validate_v20_one_q_numeric_audit(
        factors.audit, selected_q=selected_q
    )
    facts = {
        "schema": "task40extra.review_v20_one_q_physical_startup_rhs.v1",
        "selected_q": selected_q,
        "selected_q_numeric_coverage": numeric_qs,
        "all_q_symbolic_covered": admission["all_q_symbolic_covered"],
        "symbolic_admission": admission,
        "numeric_factor_build_attempt_count": int(
            factors.audit["numeric_factor_build_attempt_count"]
        ),
        "factor_probe_mat_solve_count": int(
            factors.audit.get("factor_probe_mat_solve_count", 0)
        ),
        "startup_rhs_mat_solve_count": int(
            factors.audit.get("rhs_mat_solve_count_by_category", {}).get(
                "startup_rhs_mat_solve_count", 0
            )
        ),
        "physical_rhs_facts": dict(physical_rhs_facts),
        "physical_rhs_kind": "production dtn-port modal Maxwell RHS",
        "physical_rhs_storage_sha256": _array_sha256(
            np.asarray(full_physical_rhs, dtype=np.complex128)
        ),
        "production_fold_and_reduce": (
            "CompleteTwoCellInverse.iter_q_modal_rhs: fold_dual, sector action.reduce_rhs, "
            "then selected q-map adjoint"
        ),
        "sector_solve_count": len(sector_rows),
        "sector_solves": sector_rows,
        "not_a_factor_probe": True,
        "fresh_factor_probe_limit_is_separate": 1.0e-10,
        "actual_physical_rhs_limit": float(residual_limit),
        "passed": all(row["passed"] for row in sector_rows),
    }
    return facts, raw_arrays


def v20_factor_cleanup_facts(factors: Any) -> dict[str, Any]:
    audit = getattr(factors, "audit", {})
    live_factors = len(getattr(factors, "factors", {}))
    live_matrices = len(getattr(factors, "matrices", {}))
    destroyed = getattr(factors, "destroyed", None) is True
    audit_factor_count = audit.get("factors_live_count_current")
    audit_matrix_count = audit.get("matrices_live_count_current")
    passed = bool(
        destroyed
        and live_factors == 0
        and live_matrices == 0
        and audit_factor_count == 0
        and audit_matrix_count == 0
    )
    return {
        "factor_backend_destroyed": destroyed,
        "live_factor_count_after_cleanup": live_factors,
        "live_petsc_matrix_count_after_cleanup": live_matrices,
        "audit_factor_count_after_cleanup": audit_factor_count,
        "audit_matrix_count_after_cleanup": audit_matrix_count,
        "passed": passed,
    }


__all__ = [
    "V20_PHYSICAL_RHS_LIMIT",
    "V20_SELECTED_Q",
    "require_v20_symbolic_admission",
    "run_v20_one_q_physical_rhs",
    "validate_v20_one_q_numeric_audit",
    "v20_factor_cleanup_facts",
]
