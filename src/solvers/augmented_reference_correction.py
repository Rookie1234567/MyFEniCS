"""Bounded one-step correction for complete augmented reference inverses.

The helper deliberately accepts a raw, non-recursive inverse. It updates the
finite-element and port-amplitude parts together and leaves physical
qualification to the caller's independent residual evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

import numpy as np


STRICT_ONLY = "STRICT_ONLY"
STRICT_THEN_BOUNDED_INEXACT_V13 = "STRICT_THEN_BOUNDED_INEXACT_V13"

STRICT_REFERENCE_PASS = "STRICT_REFERENCE_PASS"
BOUNDED_INEXACT_REFERENCE_PC = "BOUNDED_INEXACT_REFERENCE_PC"
REFERENCE_PC_REJECTED = "REFERENCE_PC_REJECTED"

# Strict keeps the original combined local-equation gate; per-sector ratios
# remain recorded diagnostics here, while bounded-inexact gates each sector.
REFERENCE_PC_STRATEGIES = frozenset({STRICT_ONLY, STRICT_THEN_BOUNDED_INEXACT_V13})
STRICT_REFERENCE_LIMITS = {
    "full_equation": 1.0e-10,
    "complete_augmented_fe_equation": 1.0e-10,
    "local_combined": 1.0e-10,
    "alpha_closure": 1.0e-11,
    "q_solve": 1.0e-10,
}
BOUNDED_INEXACT_LIMITS = {
    "full_equation": 1.0e-8,
    "complete_augmented_fe_equation": 1.0e-8,
    "local_sector_0": 1.0e-8,
    "local_sector_1": 1.0e-8,
    "local_combined": 1.0e-8,
    "alpha_closure": 1.0e-9,
    "q_solve": 1.0e-8,
}
MAX_EXTRA_MAT_SOLVES = 4
FACTOR_CALL_COUNTER_SOURCE = "factors.calls"


@dataclass(frozen=True)
class AugmentedCorrectionResult:
    """Updated complete FE/port state plus auditable correction facts."""

    finite_element: np.ndarray
    port_amplitudes: np.ndarray
    audit: Mapping[str, Any]


def q_solve_limit(strategy: str) -> float:
    """Return the permitted per-MatSolve true-residual ceiling."""

    if strategy == STRICT_ONLY:
        return STRICT_REFERENCE_LIMITS["q_solve"]
    if strategy == STRICT_THEN_BOUNDED_INEXACT_V13:
        return BOUNDED_INEXACT_LIMITS["q_solve"]
    raise ValueError(f"unknown Task40 reference-PC strategy: {strategy!r}")


def _checked_vector(value: Any, name: str, *, check_finite: bool = True) -> np.ndarray:
    """Validate metadata without silently allocating a cast or conversion."""

    if not isinstance(value, np.ndarray):
        raise TypeError(f"{name} must be a NumPy complex128 vector")
    if value.ndim != 1 or value.dtype != np.dtype(np.complex128):
        raise ValueError(f"{name} must be a one-dimensional complex128 vector")
    if check_finite and not np.isfinite(value).all():
        raise ValueError(f"{name} must contain only finite values")
    return value


def augmented_rhs_sha256(fe_residual: Any, port_residual: Any) -> str:
    """Hash the exact pair of correction right-hand sides, including shape."""

    fe = np.ascontiguousarray(_checked_vector(fe_residual, "FE residual"))
    port = np.ascontiguousarray(_checked_vector(port_residual, "port residual"))
    digest = sha256()
    for vector in (fe, port):
        digest.update(np.asarray(vector.shape, dtype=np.int64).tobytes())
        digest.update(vector.dtype.str.encode("ascii"))
        digest.update(vector.tobytes())
    return digest.hexdigest()


def augmented_port_state_offset(
    port_amplitudes: Any, recovered_port_amplitudes: Any
) -> np.ndarray:
    """Return the actual returned-alpha defect used in both augmented rows."""

    alpha = _checked_vector(port_amplitudes, "port-amplitude state")
    recovered = _checked_vector(
        recovered_port_amplitudes, "recovered port-amplitude state"
    )
    if alpha.shape != recovered.shape:
        raise ValueError("returned and recovered port-amplitude layouts differ")
    return np.subtract(alpha, recovered)


def stable_euclidean_norm(vector: np.ndarray) -> float:
    """Use complex BLAS xNRM2 scaling so tiny nonzero vectors stay nonzero."""

    from scipy.linalg.blas import dznrm2

    return float(dznrm2(vector))


def evaluate_complete_augmented_residual(
    *,
    physical_action_storage: Any,
    dual_coupling_storage: Any,
    finite_element_rhs: Any,
    port_amplitudes: Any,
    recovered_port_amplitudes: Any,
    port_state_offset: Any,
    port_rhs: Any,
    h: Any,
    original_fe_equation_scale: float,
    independent_rows: Any,
) -> dict[str, Any]:
    """Evaluate native FE and port residuals for one complete augmented state.

    The caller applies the native physical operator and dual port coupling with
    its domain objects. This solver-level function owns the common residual
    formula used by startup witnesses and every V13 reference-PC application.
    """

    physical = _checked_vector(physical_action_storage, "native physical action")
    coupling = _checked_vector(dual_coupling_storage, "native dual port coupling")
    fe_rhs = _checked_vector(finite_element_rhs, "finite-element right-hand side")
    alpha = _checked_vector(port_amplitudes, "port-amplitude state")
    recovered = _checked_vector(
        recovered_port_amplitudes, "recovered port-amplitude state"
    )
    offset = _checked_vector(port_state_offset, "returned-alpha state offset")
    rhs_port = _checked_vector(port_rhs, "port right-hand side")
    if not isinstance(h, np.ndarray) or h.ndim != 1 or h.dtype != np.dtype(np.float64):
        raise ValueError("original H_p normalization must be a float64 vector")
    if not isinstance(independent_rows, np.ndarray) or independent_rows.ndim != 1:
        raise ValueError("independent storage rows must be a one-dimensional array")
    if not np.issubdtype(independent_rows.dtype, np.integer):
        raise ValueError("independent storage rows must have an integer dtype")
    if physical.shape != coupling.shape:
        raise ValueError("native physical and dual-coupling storage layouts differ")
    if (
        fe_rhs.shape != independent_rows.shape
        or independent_rows.size == 0
        or int(independent_rows.min()) < 0
        or int(independent_rows.max()) >= physical.size
    ):
        raise ValueError("independent finite-element row layout is invalid")
    if any(
        vector.shape != h.shape
        for vector in (alpha, recovered, offset, rhs_port)
    ):
        raise ValueError("complete augmented port layouts differ")
    if not np.isfinite(h).all() or np.any(h <= 0.0):
        raise ValueError("original H_p normalization must be positive and finite")
    fe_equation_scale = float(original_fe_equation_scale)
    if not np.isfinite(fe_equation_scale) or fe_equation_scale < 0.0:
        raise ValueError("original FE equation scale must be finite and nonnegative")
    if not all(
        np.isfinite(vector).all()
        for vector in (physical, coupling, fe_rhs, alpha, recovered, offset, rhs_port)
    ):
        raise FloatingPointError("complete augmented native input contains nonfinite values")

    fe_action = physical[independent_rows] + coupling[independent_rows]
    fe_residual = fe_rhs - fe_action
    port_action = h * offset
    port_residual = rhs_port - port_action
    rhs_over_h = rhs_port / h
    alpha_expected = recovered + rhs_over_h
    closure_residual = alpha - alpha_expected

    fe_residual_norm = stable_euclidean_norm(fe_residual)
    port_residual_norm = stable_euclidean_norm(port_residual)
    augmented_residual_norm = float(np.hypot(fe_residual_norm, port_residual_norm))
    augmented_rhs_norm = float(
        np.hypot(stable_euclidean_norm(fe_rhs), stable_euclidean_norm(rhs_port))
    )
    stacked_relative_diagnostic = (
        augmented_residual_norm / augmented_rhs_norm
        if augmented_rhs_norm > 0.0
        else (0.0 if augmented_residual_norm == 0.0 else float("inf"))
    )
    complete_fe_equation_relative = (
        fe_residual_norm / fe_equation_scale
        if fe_equation_scale > 0.0
        else (0.0 if fe_residual_norm == 0.0 else float("inf"))
    )
    closure_residual_norm = stable_euclidean_norm(closure_residual)
    closure_scale = max(
        stable_euclidean_norm(alpha)
        + stable_euclidean_norm(recovered)
        + stable_euclidean_norm(rhs_over_h),
        np.finfo(float).tiny,
    )
    closure_relative = closure_residual_norm / closure_scale
    scalars = (
        fe_residual_norm, port_residual_norm, augmented_residual_norm,
        augmented_rhs_norm, stacked_relative_diagnostic,
        complete_fe_equation_relative, closure_residual_norm,
        closure_scale, closure_relative,
    )
    if not all(np.isfinite(value) for value in scalars) or not all(
        np.isfinite(vector).all()
        for vector in (fe_residual, port_residual, closure_residual)
    ):
        raise FloatingPointError("complete augmented reference residual is nonfinite")
    return {
        "finite_element_residual": fe_residual,
        "port_residual": port_residual,
        "finite_element_residual_norm": fe_residual_norm,
        "port_residual_norm": port_residual_norm,
        "augmented_residual_norm": augmented_residual_norm,
        "augmented_rhs_norm": augmented_rhs_norm,
        "complete_augmented_stacked_relative_diagnostic": stacked_relative_diagnostic,
        "original_fe_equation_scale": fe_equation_scale,
        "complete_augmented_fe_equation_relative": complete_fe_equation_relative,
        "alpha_closure_residual_norm": closure_residual_norm,
        "alpha_closure_scale": closure_scale,
        "alpha_closure_relative": closure_relative,
        "fe_row_formula": "physical_action(u) + B * (alpha - recover_auxiliary(u))",
        "port_row_formula": "g - h * (alpha - recover_auxiliary(u)); H_p uses original h",
    }


def _counter_facts(call_facts: Mapping[str, Any]) -> tuple[int | None, int | None, int | None]:
    """Read a real before/after factor-call counter; never infer it from rows."""

    before = call_facts.get("factor_calls_before")
    after = call_facts.get("factor_calls_after")
    if type(before) is not int or type(after) is not int:
        return None, None, None
    delta = after - before
    if before < 0 or after < before or delta > MAX_EXTRA_MAT_SOLVES:
        raise ValueError(
            "raw augmented inverse exceeded the four-extra-MatSolve counter limit"
        )
    return before, after, delta


def _q_phase_coverage(q_rows: Sequence[Any]) -> tuple[int, ...]:
    phases = set()
    for row in q_rows:
        if isinstance(row, Mapping):
            q = row.get("q")
            if type(q) is int:
                phases.add(q)
    return tuple(sorted(phases))


def apply_one_augmented_residual_correction(
    finite_element: Any,
    port_amplitudes: Any,
    fe_residual: Any,
    port_residual: Any,
    *,
    raw_inverse: Callable[[np.ndarray, np.ndarray], Any],
    allocation_gate: Callable[[str, Mapping[str, Any]], Any] | None = None,
    require_verified_solve_counter: bool = False,
) -> AugmentedCorrectionResult:
    """Apply one raw four-q inverse to both rows of an augmented error.

    ``raw_inverse`` must not perform another correction. The caller supplies
    residuals from an independent complete augmented action, not from the q
    matrices used by the inverse itself. When ``require_verified_solve_counter``
    is true, the raw call must return an actual ``factors.calls`` before/after
    snapshot and audit every q phase; q-record count alone is never treated as
    a solve counter.
    """

    state_fe_view = _checked_vector(
        finite_element, "finite-element state", check_finite=False
    )
    state_port_view = _checked_vector(
        port_amplitudes, "port-amplitude state", check_finite=False
    )
    rhs_fe_view = _checked_vector(fe_residual, "FE residual", check_finite=False)
    rhs_port_view = _checked_vector(port_residual, "port residual", check_finite=False)
    if state_fe_view.shape != rhs_fe_view.shape or state_port_view.shape != rhs_port_view.shape:
        raise ValueError("augmented correction state and residual shapes differ")
    if not callable(raw_inverse):
        raise TypeError("a raw non-recursive augmented inverse is required")

    input_array_bytes = int(
        state_fe_view.nbytes + state_port_view.nbytes
        + rhs_fe_view.nbytes + rhs_port_view.nbytes
    )
    copied_state_rhs_bytes = input_array_bytes
    delta_bytes = int(state_fe_view.nbytes + state_port_view.nbytes)
    updated_state_bytes = delta_bytes
    additional_payload_bytes = int(
        copied_state_rhs_bytes + delta_bytes + updated_state_bytes
    )
    simultaneous_live_array_bytes = int(input_array_bytes + additional_payload_bytes)
    if allocation_gate is not None:
        allocation_gate(
            "task40_v13_complete_augmented_residual_correction",
            {
                "additional_payload_bytes": additional_payload_bytes,
                "workspace_bytes": 0,
                "input_array_bytes": input_array_bytes,
                "copied_state_and_rhs_bytes": copied_state_rhs_bytes,
                "raw_correction_delta_bytes": delta_bytes,
                "updated_state_bytes": updated_state_bytes,
                "simultaneous_live_array_bytes": simultaneous_live_array_bytes,
                "simultaneous_live_array_groups": {
                    "caller_state_and_rhs": 2,
                    "owned_state_and_rhs_copies": 2,
                    "raw_correction_delta": 1,
                    "updated_state": 1,
                },
                "covers_explicit_copies_delta_and_updated_state": True,
                "finite_element_and_port_updated_together": True,
                "maximum_correction_calls": 1,
                "maximum_extra_mat_solves": MAX_EXTRA_MAT_SOLVES,
                "all_four_q_factors_reused": True,
            },
        )

    for vector, name in (
        (state_fe_view, "finite-element state"),
        (state_port_view, "port-amplitude state"),
        (rhs_fe_view, "FE residual"),
        (rhs_port_view, "port residual"),
    ):
        if not np.isfinite(vector).all():
            raise ValueError(f"{name} must contain only finite values")

    state_fe = state_fe_view.copy()
    state_port = state_port_view.copy()
    rhs_fe = rhs_fe_view.copy()
    rhs_port = rhs_port_view.copy()
    correction_hash = augmented_rhs_sha256(rhs_fe, rhs_port)
    exact_zero = np.count_nonzero(rhs_fe) == 0 and np.count_nonzero(rhs_port) == 0
    if exact_zero:
        return AugmentedCorrectionResult(
            finite_element=state_fe,
            port_amplitudes=state_port,
            audit={
                "attempted": False,
                "reason": "exact_zero_augmented_residual",
                "input_rhs_sha256": correction_hash,
                "extra_mat_solve_count": 0,
                "extra_mat_solve_count_status": "verified_no_call_exact_zero_rhs",
                "q_phase_coverage": [],
                "all_four_q_phases_covered": False,
                "solve_seconds": 0.0,
                "scratch_bytes_estimate": simultaneous_live_array_bytes,
                "additional_payload_bytes": additional_payload_bytes,
                "simultaneous_live_array_bytes": simultaneous_live_array_bytes,
                "maximum_corrections": 1,
            },
        )

    started = perf_counter()
    raw_result = raw_inverse(rhs_fe, rhs_port)
    solve_seconds = perf_counter() - started
    if not isinstance(raw_result, tuple) or len(raw_result) not in (2, 3):
        raise TypeError("raw augmented inverse must return (delta_fe, delta_port[, facts])")
    delta_fe = _checked_vector(raw_result[0], "FE correction")
    delta_port = _checked_vector(raw_result[1], "port correction")
    if delta_fe.shape != state_fe.shape or delta_port.shape != state_port.shape:
        raise ValueError("raw augmented correction has a mismatched state shape")

    call_facts: Mapping[str, Any] = (
        raw_result[2] if len(raw_result) == 3 and isinstance(raw_result[2], Mapping) else {}
    )
    factor_calls_before, factor_calls_after, solve_count = _counter_facts(call_facts)
    q_rows = list(call_facts.get("q_true_residuals", ()))
    q_coverage = _q_phase_coverage(q_rows)
    all_four_q_phases_covered = q_coverage == (0, 1, 2, 3)
    counter_source = call_facts.get("counter_source")
    if require_verified_solve_counter:
        if (
            solve_count is None
            or counter_source != FACTOR_CALL_COUNTER_SOURCE
            or solve_count != MAX_EXTRA_MAT_SOLVES
            or not all_four_q_phases_covered
        ):
            raise ValueError(
                "production augmented correction requires a verified four-call "
                "factors.calls delta and coverage of q=0,1,2,3"
            )

    updated_fe = state_fe + delta_fe
    updated_port = state_port + delta_port
    if not np.isfinite(updated_fe).all() or not np.isfinite(updated_port).all():
        raise FloatingPointError("complete augmented correction produced nonfinite values")

    if solve_count is None:
        counter_status = "unknown_no_factor_counter"
    elif counter_source != FACTOR_CALL_COUNTER_SOURCE:
        counter_status = "counter_source_not_verified_factors_calls"
    else:
        counter_status = "verified_from_factors_calls_delta"
    actual_live_array_bytes = int(
        input_array_bytes + copied_state_rhs_bytes + delta_fe.nbytes
        + delta_port.nbytes + updated_fe.nbytes + updated_port.nbytes
    )
    return AugmentedCorrectionResult(
        finite_element=updated_fe,
        port_amplitudes=updated_port,
        audit={
            "attempted": True,
            "input_rhs_sha256": correction_hash,
            "input_fe_residual_norm": stable_euclidean_norm(rhs_fe),
            "input_port_residual_norm": stable_euclidean_norm(rhs_port),
            "extra_mat_solve_count": solve_count,
            "extra_mat_solve_count_status": counter_status,
            "factor_calls_before": factor_calls_before,
            "factor_calls_after": factor_calls_after,
            "counter_source": counter_source,
            "q_true_residuals": q_rows,
            "q_phase_coverage": list(q_coverage),
            "all_four_q_phases_covered": all_four_q_phases_covered,
            "solve_seconds": float(solve_seconds),
            "scratch_bytes_estimate": simultaneous_live_array_bytes,
            "actual_explicit_live_array_bytes": actual_live_array_bytes,
            "additional_payload_bytes": additional_payload_bytes,
            "simultaneous_live_array_bytes": simultaneous_live_array_bytes,
            "maximum_corrections": 1,
            "nonrecursive_raw_inverse": True,
            "full_fe_and_port_updated_together": True,
        },
    )


def normalized_max_exceedance(
    metrics: Mapping[str, Any], limits: Mapping[str, float]
) -> float:
    """Return max(metric/limit), with no denominator floor or hidden tolerance."""

    ratios: list[float] = []
    for name, limit in limits.items():
        threshold = float(limit)
        value = float(metrics.get(name, np.inf))
        if not np.isfinite(value) or not np.isfinite(threshold) or threshold <= 0.0:
            return float("inf")
        ratios.append(value / threshold)
    return max(ratios, default=0.0)


def _candidate_metrics_with_frozen_scales(
    candidate: Mapping[str, Any], limits: Mapping[str, float]
) -> tuple[dict[str, Any], dict[str, float]]:
    metrics = candidate.get("metrics", {})
    frozen = candidate.get("frozen_scale_metrics", {})
    if not isinstance(metrics, Mapping) or not isinstance(frozen, Mapping):
        raise TypeError("candidate original and frozen-scale metrics must be mappings")
    combined_metrics = dict(metrics)
    combined_limits = dict(limits)
    for name, limit in limits.items():
        frozen_name = f"frozen_scale::{name}"
        combined_metrics[frozen_name] = frozen.get(name, np.inf)
        combined_limits[frozen_name] = float(limit)
    return combined_metrics, combined_limits


def select_reference_pc_candidate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    strict_limits: Mapping[str, float] = STRICT_REFERENCE_LIMITS,
    bounded_inexact_limits: Mapping[str, float] = BOUNDED_INEXACT_LIMITS,
) -> dict[str, Any]:
    """Select one whole state using original and frozen scales in both tiers."""

    if not candidates:
        raise ValueError("at least one complete augmented state is required")
    strict_facts = []
    bounded_facts = []
    for index, candidate in enumerate(candidates):
        structural = candidate.get("structural_gates", {})
        if not isinstance(structural, Mapping):
            raise TypeError("candidate structural gates must be mappings")
        structural_passed = bool(structural) and all(bool(value) for value in structural.values())
        strict_metrics, strict_all_limits = _candidate_metrics_with_frozen_scales(
            candidate, strict_limits
        )
        bounded_metrics, bounded_all_limits = _candidate_metrics_with_frozen_scales(
            candidate, bounded_inexact_limits
        )
        strict_exceedance = normalized_max_exceedance(
            strict_metrics, strict_all_limits
        )
        bounded_exceedance = normalized_max_exceedance(
            bounded_metrics, bounded_all_limits
        )
        strict_original = normalized_max_exceedance(
            candidate.get("metrics", {}), strict_limits
        )
        strict_frozen = normalized_max_exceedance(
            candidate.get("frozen_scale_metrics", {}), strict_limits
        )
        bounded_original = normalized_max_exceedance(
            candidate.get("metrics", {}), bounded_inexact_limits
        )
        bounded_frozen = normalized_max_exceedance(
            candidate.get("frozen_scale_metrics", {}), bounded_inexact_limits
        )
        fact = {
            "index": index,
            "strict_passed": structural_passed and strict_exceedance <= 1.0,
            "bounded_inexact_passed": structural_passed and bounded_exceedance <= 1.0,
            "structural_passed": structural_passed,
            "strict_max_normalized_exceedance": strict_exceedance,
            "strict_original_scale_max_normalized_exceedance": strict_original,
            "strict_frozen_scale_max_normalized_exceedance": strict_frozen,
            "bounded_inexact_max_normalized_exceedance": bounded_exceedance,
            "bounded_original_scale_max_normalized_exceedance": bounded_original,
            "bounded_frozen_scale_max_normalized_exceedance": bounded_frozen,
        }
        strict_facts.append(fact)
        bounded_facts.append(fact)

    strict_candidates = [row for row in strict_facts if row["strict_passed"]]
    if strict_candidates:
        selected = min(
            strict_candidates,
            key=lambda row: (
                row["strict_max_normalized_exceedance"], row["index"]
            ),
        )
        admission = STRICT_REFERENCE_PASS
    else:
        bounded = [row for row in bounded_facts if row["bounded_inexact_passed"]]
        if bounded:
            selected = min(
                bounded,
                key=lambda row: (
                    row["bounded_inexact_max_normalized_exceedance"],
                    row["index"],
                ),
            )
            admission = BOUNDED_INEXACT_REFERENCE_PC
        else:
            eligible = [row for row in strict_facts if row["structural_passed"]]
            pool = eligible or strict_facts
            selected = min(
                pool,
                key=lambda row: (
                    row["bounded_inexact_max_normalized_exceedance"],
                    row["index"],
                ),
            )
            admission = REFERENCE_PC_REJECTED

    return {
        "admission": admission,
        "admitted": admission != REFERENCE_PC_REJECTED,
        "strict_passed": admission == STRICT_REFERENCE_PASS,
        "selected_candidate_index": int(selected["index"]),
        "selected_max_normalized_exceedance": float(
            selected["strict_max_normalized_exceedance"]
            if admission == STRICT_REFERENCE_PASS
            else selected["bounded_inexact_max_normalized_exceedance"]
        ),
        "candidate_facts": strict_facts,
        "strict_limits": dict(strict_limits),
        "bounded_inexact_limits": dict(bounded_inexact_limits),
        "selection_rule": (
            "same complete state must satisfy original and frozen-scale limits; "
            "choose minimum maximum normalized exceedance with strict tier priority"
        ),
    }


def recheck_reference_pc_final_admission(
    last_facts: Mapping[str, Any],
    strategy: str,
    *,
    legacy_alpha_limit: float = 1.0e-10,
    legacy_q_limit: float = 1.0e-10,
) -> dict[str, Any]:
    """Independently recompute the parent worker's final reference-PC gate.

    V13 uses the selected whole-state candidate and the same original plus
    frozen scales recorded by the PC. The legacy path retains its existing
    1e-10 port-identity and q-solve thresholds.
    """

    alpha = float(last_facts.get("port_identity_relative", np.inf))
    q_relative = float(last_facts.get("maximum_q_true_residual_relative", np.inf))
    if strategy == STRICT_ONLY:
        alpha_limit = float(legacy_alpha_limit)
        q_limit = float(legacy_q_limit)
        passed = bool(
            last_facts.get("reference_pc_strategy", STRICT_ONLY) == STRICT_ONLY
            and np.isfinite(alpha)
            and alpha <= alpha_limit
            and np.isfinite(q_relative)
            and q_relative <= q_limit
        )
        return {
            "passed": passed,
            "strategy": strategy,
            "admission": STRICT_REFERENCE_PASS if passed else REFERENCE_PC_REJECTED,
            "port_identity_relative": alpha,
            "port_identity_limit": alpha_limit,
            "maximum_q_true_residual_relative": q_relative,
            "q_true_residual_limit": q_limit,
            "selection_recomputed_from_candidate_metrics": False,
        }

    if strategy != STRICT_THEN_BOUNDED_INEXACT_V13:
        return {
            "passed": False,
            "strategy": strategy,
            "admission": REFERENCE_PC_REJECTED,
            "reason": "unknown_reference_pc_strategy",
            "selection_recomputed_from_candidate_metrics": False,
        }

    subset_names = (
        "complete_augmented_fe_equation",
        "alpha_closure",
        "q_solve",
    )
    strict_limits = {name: float(STRICT_REFERENCE_LIMITS[name]) for name in subset_names}
    bounded_limits = {
        name: float(BOUNDED_INEXACT_LIMITS[name]) for name in subset_names
    }
    candidates = last_facts.get("candidate_metrics")
    recorded = last_facts.get("candidate_selection")
    failure_reason = None
    try:
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise TypeError("candidate_metrics is not a sequence")
        recomputed = select_reference_pc_candidate(
            candidates,
            strict_limits=strict_limits,
            bounded_inexact_limits=bounded_limits,
        )
        index = int(recomputed["selected_candidate_index"])
        selected = candidates[index]
        metrics = selected.get("metrics", {})
        selected_alpha = float(metrics.get("alpha_closure", np.inf))
        selected_q = float(metrics.get("q_solve", np.inf))
        admission = str(recomputed["admission"])
        alpha_limit = (
            strict_limits["alpha_closure"]
            if admission == STRICT_REFERENCE_PASS
            else bounded_limits["alpha_closure"]
        )
        q_limit = (
            strict_limits["q_solve"]
            if admission == STRICT_REFERENCE_PASS
            else bounded_limits["q_solve"]
        )
        q_rows = last_facts.get("q_true_residuals_selected", ())
        q_coverage = (
            isinstance(q_rows, Sequence)
            and len(q_rows) == 4
            and {
                int(row.get("q", -1))
                for row in q_rows
                if isinstance(row, Mapping)
            } == {0, 1, 2, 3}
            and all(isinstance(row, Mapping) for row in q_rows)
        )
        if not isinstance(recorded, Mapping):
            failure_reason = "recorded_candidate_selection_missing"
        elif (
            recorded.get("admission") != admission
            or recorded.get("selected_candidate_index") != index
        ):
            failure_reason = "recorded_candidate_selection_mismatch"
        elif last_facts.get("reference_pc_strategy") != strategy:
            failure_reason = "recorded_reference_pc_strategy_mismatch"
        elif not q_coverage or last_facts.get("all_four_q_used") is not True:
            failure_reason = "selected_q_phase_coverage_failed"
        elif not np.isfinite(alpha) or alpha != selected_alpha:
            failure_reason = "selected_alpha_metric_mismatch"
        elif not np.isfinite(q_relative) or q_relative != selected_q:
            failure_reason = "selected_q_metric_mismatch"
        elif not recomputed["admitted"]:
            failure_reason = "candidate_selection_rejected"
        return {
            "passed": failure_reason is None,
            "strategy": strategy,
            "admission": admission,
            "selected_candidate_index": index,
            "recorded_admission": (
                recorded.get("admission") if isinstance(recorded, Mapping) else None
            ),
            "recorded_selected_candidate_index": (
                recorded.get("selected_candidate_index")
                if isinstance(recorded, Mapping)
                else None
            ),
            "port_identity_relative": alpha,
            "selected_alpha_closure_relative": selected_alpha,
            "port_identity_limit": alpha_limit,
            "maximum_q_true_residual_relative": q_relative,
            "selected_q_solve_relative": selected_q,
            "q_true_residual_limit": q_limit,
            "all_four_q_phase_rows_covered": bool(q_coverage),
            "selection_recomputed_from_candidate_metrics": True,
            "candidate_selection": recomputed,
            "failure_reason": failure_reason,
        }
    except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
        return {
            "passed": False,
            "strategy": strategy,
            "admission": REFERENCE_PC_REJECTED,
            "reason": f"candidate_selection_recheck_error:{type(exc).__name__}:{exc}",
            "selection_recomputed_from_candidate_metrics": True,
        }


__all__ = [
    "AugmentedCorrectionResult",
    "BOUNDED_INEXACT_LIMITS",
    "BOUNDED_INEXACT_REFERENCE_PC",
    "FACTOR_CALL_COUNTER_SOURCE",
    "MAX_EXTRA_MAT_SOLVES",
    "REFERENCE_PC_REJECTED",
    "REFERENCE_PC_STRATEGIES",
    "STRICT_ONLY",
    "STRICT_REFERENCE_LIMITS",
    "STRICT_REFERENCE_PASS",
    "STRICT_THEN_BOUNDED_INEXACT_V13",
    "apply_one_augmented_residual_correction",
    "augmented_rhs_sha256",
    "normalized_max_exceedance",
    "q_solve_limit",
    "recheck_reference_pc_final_admission",
    "select_reference_pc_candidate",
    "stable_euclidean_norm",
]
