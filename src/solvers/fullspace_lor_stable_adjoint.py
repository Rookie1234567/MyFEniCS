"""Small pure-array stable-adjoint audit for the existing Route-A transfer.

The helper deliberately owns no mesh, PETSc, MPI, or solver objects.  It
compares the existing owner-routed adjoint with an independently applied local
``P.conj().T`` and records the summation facts needed by the V13 A0 audit.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np


A0_SCHEMA = "task038.full3d.interlevel-stable-adjoint.a0.v1"
A0_PAIRWISE_LIMIT = 1.0e-13
A0_COMPENSATED_LIMIT = 1.0e-12
A0_VECTOR_LIMIT = 1.0e-11
A0_ORDINARY_BOUND_FACTOR = 4.0
_EPS = np.finfo(np.float64).eps


def _complex_vector(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.dtype != np.dtype("complex128") or array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty complex128 vector")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    return np.ascontiguousarray(array, dtype=np.complex128)


def pairwise_sum(values: np.ndarray) -> complex:
    """Sum in a fixed left-to-right binary tree without changing the input."""

    work = np.asarray(values, dtype=np.complex128).reshape(-1).copy()
    if work.size == 0:
        raise ValueError("pairwise sum requires at least one term")
    while work.size > 1:
        count = work.size // 2
        reduced = work[: 2 * count : 2] + work[1 : 2 * count : 2]
        if work.size % 2:
            work = np.concatenate((reduced, work[-1:]))
        else:
            work = reduced
    return complex(work[0])


def compensated_sum(values: np.ndarray) -> complex:
    """Sum real and imaginary products with deterministic ``math.fsum``."""

    work = np.asarray(values, dtype=np.complex128).reshape(-1)
    if work.size == 0:
        raise ValueError("compensated sum requires at least one term")
    return complex(
        math.fsum(float(value.real) for value in work),
        math.fsum(float(value.imag) for value in work),
    )


def vdot_terms(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    left_values = _complex_vector(left, "left")
    right_values = _complex_vector(right, "right")
    if left_values.shape != right_values.shape:
        raise ValueError("vdot vectors must have the same shape")
    return np.ascontiguousarray(np.conjugate(left_values) * right_values)


def _scalar_relative(left: complex, right: complex) -> float:
    return float(
        abs(left - right)
        / max(abs(left), abs(right), np.finfo(float).tiny)
    )


def _owner_ids(value: Any, name: str) -> np.ndarray:
    ids = np.asarray(value)
    if ids.dtype != np.dtype("uint32") or ids.ndim != 1 or ids.size == 0:
        raise ValueError(f"{name} must be a non-empty uint32 owner-key vector")
    if ids.size > 1 and np.any(ids[1:] <= ids[:-1]):
        raise ValueError(f"{name} must be strictly increasing")
    return ids.copy()


def _side_facts(
    terms: np.ndarray,
    left: np.ndarray,
    right: np.ndarray,
    reduce_sum: Callable[[Any], Any] | None,
    reduce_count: Callable[[int], int] | None,
    reduce_real: Callable[[float], float] | None,
) -> dict[str, Any]:
    terms = np.asarray(terms, dtype=np.complex128).reshape(-1)
    if terms.size == 0 or not np.all(np.isfinite(terms)):
        raise ValueError("work terms must be finite and non-empty")
    left_values = _complex_vector(left, "ordinary left")
    right_values = _complex_vector(right, "ordinary right")
    if left_values.shape != right_values.shape:
        raise ValueError("ordinary dot vectors are not closed")
    ordinary_local = complex(np.vdot(left_values, right_values))
    pairwise_local = pairwise_sum(terms)
    compensated_local = compensated_sum(terms)
    ordinary = ordinary_local if reduce_sum is None else complex(reduce_sum(ordinary_local))
    pairwise = pairwise_local if reduce_sum is None else complex(reduce_sum(pairwise_local))
    compensated = (
        compensated_local
        if reduce_sum is None
        else complex(reduce_sum(compensated_local))
    )
    local_count = int(terms.size)
    count = local_count if reduce_count is None else int(reduce_count(local_count))
    local_abs_sum = float(math.fsum(float(abs(value)) for value in terms))
    abs_sum = local_abs_sum if reduce_real is None else float(reduce_real(local_abs_sum))
    denominator = 1.0 - count * _EPS
    gamma = float(count * _EPS / denominator) if denominator > 0.0 else math.inf
    return {
        "term_count": count,
        "term_count_local": local_count,
        "term_abs_sum": abs_sum,
        "term_abs_sum_local": local_abs_sum,
        "gamma_n": gamma,
        "forward_error_bound_abs": float(gamma * abs_sum),
        "ordinary_local": ordinary_local,
        "ordinary": ordinary,
        "pairwise_local": pairwise_local,
        "pairwise": pairwise,
        "compensated_local": compensated_local,
        "compensated": compensated,
    }


def _bound_facts(
    terms: np.ndarray,
    reduce_count: Callable[[int], int] | None,
    reduce_real: Callable[[float], float] | None,
) -> dict[str, Any]:
    terms = np.asarray(terms, dtype=np.complex128).reshape(-1)
    if terms.size == 0 or not np.all(np.isfinite(terms)):
        raise ValueError("ordinary work terms must be finite and non-empty")
    local_count = int(terms.size)
    count = local_count if reduce_count is None else int(reduce_count(local_count))
    local_abs_sum = float(math.fsum(float(abs(value)) for value in terms))
    abs_sum = local_abs_sum if reduce_real is None else float(reduce_real(local_abs_sum))
    denominator = 1.0 - count * _EPS
    gamma = float(count * _EPS / denominator) if denominator > 0.0 else math.inf
    return {
        "term_count": count,
        "term_count_local": local_count,
        "term_abs_sum": abs_sum,
        "term_abs_sum_local": local_abs_sum,
        "gamma_n": gamma,
        "forward_error_bound_abs": float(gamma * abs_sum),
    }


def audit_stable_adjoint(
    *,
    coarse_source: np.ndarray,
    fine_primal: np.ndarray,
    fine_dual: np.ndarray,
    implemented_adjoint: np.ndarray,
    explicit_adjoint: np.ndarray | None,
    lhs_owner: tuple[np.ndarray, np.ndarray, np.ndarray],
    rhs_owner: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    ordinary_lhs: tuple[np.ndarray, np.ndarray] | None = None,
    ordinary_rhs: tuple[np.ndarray, np.ndarray] | None = None,
    reduce_sum: Callable[[Any], Any] | None = None,
    reduce_count: Callable[[int], int] | None = None,
    reduce_real: Callable[[float], float] | None = None,
) -> dict[str, Any]:
    """Derive A0 facts from raw vectors and canonical owner-ordered packets."""

    source = _complex_vector(coarse_source, "coarse_source")
    primal = _complex_vector(fine_primal, "fine_primal")
    dual = _complex_vector(fine_dual, "fine_dual")
    implemented = _complex_vector(implemented_adjoint, "implemented_adjoint")
    explicit = None if explicit_adjoint is None else _complex_vector(
        explicit_adjoint, "explicit_adjoint"
    )
    if (explicit is not None and implemented.shape != explicit.shape) or (
        source.shape != implemented.shape
    ):
        raise ValueError("coarse adjoint vectors must have the same shape")
    lhs_ids, lhs_left, lhs_right = lhs_owner
    rhs_ids, rhs_source, rhs_implemented, rhs_explicit = rhs_owner
    lhs_ids = _owner_ids(lhs_ids, "lhs owner IDs")
    rhs_ids = _owner_ids(rhs_ids, "rhs owner IDs")
    lhs_left = _complex_vector(lhs_left, "lhs owner primal")
    lhs_right = _complex_vector(lhs_right, "lhs owner dual")
    rhs_source = _complex_vector(rhs_source, "rhs owner source")
    rhs_implemented = _complex_vector(rhs_implemented, "rhs owner implemented")
    rhs_explicit = _complex_vector(rhs_explicit, "rhs owner explicit")
    if lhs_ids.shape != lhs_left.shape or lhs_ids.shape != lhs_right.shape:
        raise ValueError("lhs owner packet shapes are not closed")
    if rhs_ids.shape != rhs_source.shape or rhs_ids.shape != rhs_implemented.shape:
        raise ValueError("rhs owner packet shapes are not closed")
    if rhs_ids.shape != rhs_explicit.shape:
        raise ValueError("explicit rhs owner packet shape is not closed")
    lhs_terms = vdot_terms(lhs_left, lhs_right)
    rhs_terms = vdot_terms(rhs_source, rhs_implemented)
    explicit_rhs_terms = vdot_terms(rhs_source, rhs_explicit)
    ordinary_lhs = (lhs_left, lhs_right) if ordinary_lhs is None else ordinary_lhs
    ordinary_rhs = (
        (rhs_source, rhs_implemented) if ordinary_rhs is None else ordinary_rhs
    )
    lhs_facts = _side_facts(
        lhs_terms, ordinary_lhs[0], ordinary_lhs[1],
        reduce_sum, reduce_count, reduce_real,
    )
    rhs_facts = _side_facts(
        rhs_terms, ordinary_rhs[0], ordinary_rhs[1],
        reduce_sum, reduce_count, reduce_real,
    )
    explicit_facts = _side_facts(
        explicit_rhs_terms, rhs_source, rhs_explicit,
        reduce_sum, reduce_count, reduce_real,
    )
    ordinary_lhs_terms = vdot_terms(ordinary_lhs[0], ordinary_lhs[1])
    ordinary_rhs_terms = vdot_terms(ordinary_rhs[0], ordinary_rhs[1])
    ordinary_lhs_bound = _bound_facts(
        ordinary_lhs_terms, reduce_count, reduce_real
    )
    ordinary_rhs_bound = _bound_facts(
        ordinary_rhs_terms, reduce_count, reduce_real
    )
    compensated_work_relative = _scalar_relative(
        lhs_facts["compensated"], rhs_facts["compensated"]
    )
    pairwise_vs_compensated_relative = max(
        _scalar_relative(lhs_facts["pairwise"], lhs_facts["compensated"]),
        _scalar_relative(rhs_facts["pairwise"], rhs_facts["compensated"]),
        _scalar_relative(
            explicit_facts["pairwise"], explicit_facts["compensated"]
        ),
    )
    ordinary_abs_defect = abs(
        lhs_facts["ordinary"] - rhs_facts["ordinary"]
    )
    bound = (
        ordinary_lhs_bound["forward_error_bound_abs"]
        + ordinary_rhs_bound["forward_error_bound_abs"]
    )
    vector_difference = rhs_implemented - rhs_explicit
    difference_sq_local = float(
        math.fsum(float(abs(value) ** 2) for value in vector_difference)
    )
    reference_sq_local = float(
        math.fsum(float(abs(value) ** 2) for value in rhs_explicit)
    )
    difference_sq = (
        difference_sq_local
        if reduce_real is None
        else float(reduce_real(difference_sq_local))
    )
    reference_sq = (
        reference_sq_local
        if reduce_real is None
        else float(reduce_real(reference_sq_local))
    )
    vector_relative = float(
        math.sqrt(max(difference_sq, 0.0))
        / max(math.sqrt(max(reference_sq, 0.0)), np.finfo(float).tiny)
    )
    facts: dict[str, Any] = {
        "schema": A0_SCHEMA,
        "ordinary_lhs": lhs_facts["ordinary"],
        "ordinary_rhs": rhs_facts["ordinary"],
        "pairwise_lhs": lhs_facts["pairwise"],
        "pairwise_rhs": rhs_facts["pairwise"],
        "compensated_lhs": lhs_facts["compensated"],
        "compensated_rhs": rhs_facts["compensated"],
        "explicit_compensated_rhs": explicit_facts["compensated"],
        "pairwise_vs_compensated_relative": pairwise_vs_compensated_relative,
        "compensated_work_relative": compensated_work_relative,
        "ordinary_abs_work_defect": float(ordinary_abs_defect),
        "forward_error_bound_abs": float(bound),
        "lhs_gamma_n": ordinary_lhs_bound["gamma_n"],
        "rhs_gamma_n": ordinary_rhs_bound["gamma_n"],
        "lhs_term_count": ordinary_lhs_bound["term_count"],
        "rhs_term_count": ordinary_rhs_bound["term_count"],
        "vector_adjoint_relative": float(vector_relative),
        "finite": bool(
            np.all(np.isfinite(rhs_implemented))
            and np.all(np.isfinite(rhs_explicit))
            and np.isfinite(ordinary_abs_defect)
            and np.isfinite(bound)
            and np.isfinite(vector_relative)
        ),
    }
    return facts


__all__ = [
    "A0_COMPENSATED_LIMIT",
    "A0_ORDINARY_BOUND_FACTOR",
    "A0_PAIRWISE_LIMIT",
    "A0_SCHEMA",
    "A0_VECTOR_LIMIT",
    "audit_stable_adjoint",
    "compensated_sum",
    "pairwise_sum",
    "vdot_terms",
]
