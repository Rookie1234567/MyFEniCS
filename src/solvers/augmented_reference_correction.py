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
NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15 = (
    "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
)

STRICT_REFERENCE_PASS = "STRICT_REFERENCE_PASS"
BOUNDED_INEXACT_REFERENCE_PC = "BOUNDED_INEXACT_REFERENCE_PC"
REFERENCE_PC_REJECTED = "REFERENCE_PC_REJECTED"
V15_REFERENCE_PC_PASS = "V15_REFERENCE_PC_PASS"
V15_REFERENCE_PC_REJECTED = "V15_REFERENCE_PC_REJECTED"

# Strict keeps the original combined local-equation gate; per-sector ratios
# remain recorded diagnostics here, while bounded-inexact gates each sector.
REFERENCE_PC_STRATEGIES = frozenset({
    STRICT_ONLY,
    STRICT_THEN_BOUNDED_INEXACT_V13,
    NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
})
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
V15_REFERENCE_PC_LIMITS = {
    "eliminated_fe": 1.0e-8,
    "complete_augmented_fe": 1.0e-8,
    "noncancelling_budget": 1.0e-8,
    "alpha_closure": 1.0e-9,
    "q_solve": 1.0e-8,
}
V15_FROZEN_SCALE_LIMITS = {
    "eliminated_fe": 1.0e-8,
    "complete_augmented_fe": 1.0e-8,
    "noncancelling_budget": 1.0e-8,
    "alpha_closure": 1.0e-9,
}
V15_DECOMPOSITION_CLOSURE_LIMIT = 1.0e-10
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
    if strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        return V15_REFERENCE_PC_LIMITS["q_solve"]
    raise ValueError(f"unknown Task40 reference-PC strategy: {strategy!r}")


def _finite_complex_vector(value: Any, name: str) -> np.ndarray:
    if not isinstance(value, np.ndarray) or value.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional NumPy vector")
    if value.dtype != np.dtype(np.complex128):
        raise ValueError(f"{name} must use complex128")
    if not np.isfinite(value).all():
        raise FloatingPointError(f"{name} contains nonfinite values")
    return value


def _zero_safe_relative(numerator: float, denominator: float) -> float:
    numerator = float(numerator)
    denominator = float(denominator)
    if not np.isfinite(numerator) or not np.isfinite(denominator):
        return float("inf")
    if denominator < 0.0:
        raise ValueError("relative-residual denominator cannot be negative")
    if denominator == 0.0:
        return 0.0 if numerator == 0.0 else float("inf")
    return numerator / denominator


def _registered_v15_profile_inventory(profile_identity: Any) -> dict[str, Any]:
    """Resolve q, twist, and mode counts from the registered periodic profile."""

    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    if not isinstance(profile_identity, str) or not profile_identity.startswith(
        ("task40extra_v15_", "task40extra_v16_", "task40extra_v17_", "task40extra_v18_")
    ):
        raise ValueError("V15 candidate must name a registered V15-V18 profile")
    profile = TASK40_P6_PERIODIC_PROFILES.get(profile_identity)
    if profile is None:
        raise ValueError(f"V15 candidate profile is not registered: {profile_identity!r}")
    sector_counts = tuple(int(value) for value in profile.sector_port_counts)
    if (
        int(profile.q_count) != len(profile.q_port_counts)
        or int(profile.replication_count) != len(sector_counts)
        or int(profile.mode_count) != sum(sector_counts)
    ):
        raise ValueError("registered V15 profile q/twist/mode inventory does not close")
    return {
        "identity": profile_identity,
        "q_count": int(profile.q_count),
        "twist_count": int(profile.replication_count),
        "mode_count": int(profile.mode_count),
        "sector_port_counts": sector_counts,
    }


def _q_rows_cover_expected(q_rows: Sequence[Any], expected_q_count: int) -> bool:
    return bool(
        len(q_rows) == expected_q_count
        and all(isinstance(row, Mapping) and type(row.get("q")) is int for row in q_rows)
        and {row["q"] for row in q_rows} == set(range(expected_q_count))
    )


def evaluate_v15_non_cancelling_budget(
    *,
    effective_rhs: Any,
    global_eliminated_action: Any,
    original_fe_rhs: Any,
    port_elimination_action: Any,
    complete_augmented_fe_residual: Any,
    modal_alpha_defect_action: Any,
    sectors: Sequence[Mapping[str, Any]],
    retain_lifted_errors: bool = False,
) -> dict[str, Any]:
    """Independently evaluate V15 native residual decomposition and budget.

    Each sector entry supplies its actual folded effective RHS, its local
    native action on E_s u, and the native L_s dual-lift callable. The helper
    performs the lifts before measuring local errors so no unitary-map or
    sector-denominator assumption is hidden in the budget.
    """

    b_eff = _finite_complex_vector(effective_rhs, "effective FE RHS")
    a_global = _finite_complex_vector(
        global_eliminated_action, "global eliminated native action"
    )
    f_rhs = _finite_complex_vector(original_fe_rhs, "original FE RHS")
    port_effect = _finite_complex_vector(
        port_elimination_action, "B H^-1 g action"
    )
    r_fe = _finite_complex_vector(
        complete_augmented_fe_residual, "complete augmented FE residual"
    )
    b_delta = _finite_complex_vector(
        modal_alpha_defect_action, "B delta-alpha action"
    )
    if any(
        vector.shape != b_eff.shape
        for vector in (a_global, f_rhs, port_effect, r_fe, b_delta)
    ):
        raise ValueError("V15 global vectors have inconsistent independent-row layouts")
    if not sectors:
        raise ValueError("V15 residual decomposition requires every sector")

    sum_lifted_rhs = np.zeros_like(b_eff)
    sum_lifted_actions = np.zeros_like(b_eff)
    sum_lifted_errors = np.zeros_like(b_eff)
    lifted_rhs_norms: list[float] = []
    lifted_action_norms: list[float] = []
    lifted_error_norms: list[float] = []
    lifted_errors: list[np.ndarray] = []
    local_errors: list[np.ndarray] = []
    lifted_effective_rhs: list[np.ndarray] = []
    lifted_native_actions: list[np.ndarray] = []
    for index, sector in enumerate(sectors):
        if not isinstance(sector, Mapping):
            raise TypeError("V15 sector decomposition entries must be mappings")
        b_s = _finite_complex_vector(sector.get("rhs"), f"sector {index} effective RHS")
        a_s = _finite_complex_vector(sector.get("action"), f"sector {index} native action")
        lift = sector.get("lift_dual")
        if b_s.shape != a_s.shape or not callable(lift):
            raise ValueError(f"V15 sector {index} has invalid RHS/action/lift")
        e_s = b_s - a_s
        lifted_b = _finite_complex_vector(
            lift(b_s), f"sector {index} lifted effective RHS"
        )
        lifted_a = _finite_complex_vector(
            lift(a_s), f"sector {index} lifted native action"
        )
        lifted_e = _finite_complex_vector(
            lift(e_s), f"sector {index} lifted residual"
        )
        if any(vector.shape != b_eff.shape for vector in (lifted_b, lifted_a, lifted_e)):
            raise ValueError(f"V15 sector {index} lift has an invalid global layout")
        sum_lifted_rhs += lifted_b
        sum_lifted_actions += lifted_a
        sum_lifted_errors += lifted_e
        lifted_rhs_norms.append(stable_euclidean_norm(lifted_b))
        lifted_action_norms.append(stable_euclidean_norm(lifted_a))
        lifted_error_norms.append(stable_euclidean_norm(lifted_e))
        if retain_lifted_errors:
            lifted_errors.append(lifted_e.copy())
            local_errors.append(e_s.copy())
            lifted_effective_rhs.append(lifted_b.copy())
            lifted_native_actions.append(lifted_a.copy())
        del lifted_b, lifted_a, lifted_e, e_s
    d_b = b_eff - sum_lifted_rhs
    d_a = sum_lifted_actions - a_global
    r_elim_direct = b_eff - a_global
    r_elim_decomposed = d_b + sum_lifted_errors + d_a
    r_fe_decomposed = r_elim_decomposed - b_delta
    decomposition_error = r_elim_direct - r_elim_decomposed
    augmented_error = r_fe - r_fe_decomposed
    effective_rhs_identity_error = b_eff - (f_rhs - port_effect)

    original_scale = stable_euclidean_norm(f_rhs) + stable_euclidean_norm(port_effect)
    budget_terms = {
        "d_b": stable_euclidean_norm(d_b),
        "lifted_sector_errors": lifted_error_norms,
        "d_A": stable_euclidean_norm(d_a),
        "B_delta_alpha": stable_euclidean_norm(b_delta),
    }
    budget_numerator = float(
        budget_terms["d_b"]
        + sum(lifted_error_norms)
        + budget_terms["d_A"]
        + budget_terms["B_delta_alpha"]
    )
    budget_relative = _zero_safe_relative(budget_numerator, original_scale)
    eliminated_relative = _zero_safe_relative(
        stable_euclidean_norm(r_elim_direct), original_scale
    )
    complete_fe_relative = _zero_safe_relative(
        stable_euclidean_norm(r_fe), original_scale
    )
    closure_scale = float(
        stable_euclidean_norm(b_eff)
        + stable_euclidean_norm(a_global)
        + sum(lifted_rhs_norms)
        + sum(lifted_action_norms)
        + stable_euclidean_norm(r_fe)
        + stable_euclidean_norm(b_delta)
        + stable_euclidean_norm(f_rhs)
        + stable_euclidean_norm(port_effect)
    )
    closure_numerator = max(
        stable_euclidean_norm(decomposition_error),
        stable_euclidean_norm(augmented_error),
        stable_euclidean_norm(effective_rhs_identity_error),
    )
    closure_relative = _zero_safe_relative(closure_numerator, closure_scale)
    scalars = (
        original_scale, budget_numerator, budget_relative, eliminated_relative,
        complete_fe_relative, closure_scale, closure_numerator, closure_relative,
    )
    if not all(np.isfinite(value) for value in scalars):
        if original_scale == 0.0 and budget_numerator > 0.0:
            budget_relative = float("inf")
        elif original_scale == 0.0 and budget_numerator == 0.0:
            budget_relative = 0.0
        else:
            raise FloatingPointError("V15 native residual decomposition is nonfinite")
    return {
        "effective_rhs_scale": original_scale,
        "budget_numerator": budget_numerator,
        "budget_terms": budget_terms,
        "noncancelling_budget_relative": budget_relative,
        "eliminated_fe_residual_norm": stable_euclidean_norm(r_elim_direct),
        "eliminated_fe_relative": eliminated_relative,
        "complete_augmented_fe_residual_norm": stable_euclidean_norm(r_fe),
        "complete_augmented_fe_relative": complete_fe_relative,
        "decomposition_closure_scale": closure_scale,
        "decomposition_closure_norm": closure_numerator,
        "decomposition_closure_relative": closure_relative,
        "effective_rhs_identity_error_norm": stable_euclidean_norm(
            effective_rhs_identity_error
        ),
        "d_b": d_b,
        "d_A": d_a,
        "sum_lifted_effective_rhs": sum_lifted_rhs,
        "sum_lifted_native_actions": sum_lifted_actions,
        "modal_alpha_defect_action": b_delta,
        "lifted_sector_errors": lifted_errors if retain_lifted_errors else None,
        "local_sector_errors": local_errors if retain_lifted_errors else None,
        "lifted_sector_effective_rhs": (
            lifted_effective_rhs if retain_lifted_errors else None
        ),
        "lifted_sector_native_actions": (
            lifted_native_actions if retain_lifted_errors else None
        ),
        "eliminated_fe_residual_direct": r_elim_direct,
        "eliminated_fe_residual_decomposed": r_elim_decomposed,
        "complete_fe_residual_decomposed": r_fe_decomposed,
    }


def select_v15_reference_pc_candidate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    profile_identity: str | None = None,
) -> dict[str, Any]:
    """Admit one whole V15 state only when every original/frozen gate passes."""

    if not candidates:
        raise ValueError("at least one complete V15 FE/alpha state is required")
    facts: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        metrics = candidate.get("metrics", {})
        frozen = candidate.get("frozen_scale_metrics", {})
        structural = candidate.get("structural_gates", {})
        if not isinstance(metrics, Mapping) or not isinstance(frozen, Mapping):
            raise TypeError("V15 candidate metrics must be mappings")
        if not isinstance(structural, Mapping):
            raise TypeError("V15 candidate structural gates must be a mapping")
        raw_recheck = recompute_v15_candidate_facts(
            candidate, profile_identity=profile_identity
        )
        original_exceedance = normalized_max_exceedance(
            raw_recheck["metrics"], V15_REFERENCE_PC_LIMITS
        )
        frozen_exceedance = normalized_max_exceedance(
            raw_recheck["frozen_scale_metrics"], V15_FROZEN_SCALE_LIMITS
        )
        structural_passed = bool(structural) and all(bool(v) for v in structural.values())
        structural_passed = (
            structural_passed
            and raw_recheck["raw_facts_consistent"]
            and raw_recheck["q_rows_consistent"]
            and raw_recheck["sector_mode_mapping_valid"]
        )
        closure_passed = (
            raw_recheck["decomposition_closure_relative"]
            <= V15_DECOMPOSITION_CLOSURE_LIMIT
        )
        q_coverage = raw_recheck["q_phase_coverage"]
        passed = (
            structural_passed
            and closure_passed
            and q_coverage
            and original_exceedance <= 1.0
            and frozen_exceedance <= 1.0
        )
        facts.append({
            "index": index,
            "state_label": candidate.get("state_label"),
            "passed": passed,
            "structural_passed": structural_passed,
            "raw_facts_consistent": raw_recheck["raw_facts_consistent"],
            "decomposition_closure_passed": closure_passed,
            "q_phase_coverage": q_coverage,
            "original_scale_max_normalized_exceedance": original_exceedance,
            "frozen_scale_max_normalized_exceedance": frozen_exceedance,
            "state_sha256": raw_recheck["state_sha256"],
        })

    passed_indices = [row["index"] for row in facts if row["passed"]]
    if passed_indices:
        selected_index = int(passed_indices[0])
        admission = V15_REFERENCE_PC_PASS
    else:
        eligible = [row for row in facts if row["structural_passed"]]
        pool = eligible or facts
        selected = min(
            pool,
            key=lambda row: max(
                row["original_scale_max_normalized_exceedance"],
                row["frozen_scale_max_normalized_exceedance"],
            ),
        )
        selected_index = int(selected["index"])
        admission = V15_REFERENCE_PC_REJECTED
    return {
        "admission": admission,
        "admitted": admission == V15_REFERENCE_PC_PASS,
        "selected_candidate_index": selected_index,
        "candidate_facts": facts,
        "original_scale_limits": dict(V15_REFERENCE_PC_LIMITS),
        "frozen_scale_limits": dict(V15_FROZEN_SCALE_LIMITS),
        "decomposition_closure_limit": V15_DECOMPOSITION_CLOSURE_LIMIT,
        "selection_rule": (
            "initial whole state is used immediately when every V15 original, "
            "frozen, and structural gate passes; otherwise only one whole corrected state may qualify"
        ),
    }


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


def augmented_state_sha256(finite_element: Any, port_amplitudes: Any) -> str:
    """Hash one complete FE/alpha candidate state with its exact layout."""

    fe = np.ascontiguousarray(_checked_vector(finite_element, "finite-element state"))
    port = np.ascontiguousarray(_checked_vector(port_amplitudes, "port-amplitude state"))
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
    closure_raw_scale = (
        stable_euclidean_norm(alpha)
        + stable_euclidean_norm(recovered)
        + stable_euclidean_norm(rhs_over_h)
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
        "alpha_closure_residual": closure_residual,
        "alpha_closure_scale": closure_scale,
        "alpha_closure_raw_scale": closure_raw_scale,
        "alpha_closure_relative": closure_relative,
        "fe_row_formula": "physical_action(u) + B * (alpha - recover_auxiliary(u))",
        "port_row_formula": "g - h * (alpha - recover_auxiliary(u)); H_p uses original h",
    }


def _counter_facts(
    call_facts: Mapping[str, Any], maximum_extra_mat_solves: int
) -> tuple[int | None, int | None, int | None]:
    """Read a real before/after factor-call counter; never infer it from rows."""

    before = call_facts.get("factor_calls_before")
    after = call_facts.get("factor_calls_after")
    if type(before) is not int or type(after) is not int:
        return None, None, None
    delta = after - before
    if before < 0 or after < before or delta > maximum_extra_mat_solves:
        raise ValueError(
            f"raw augmented inverse exceeded the {maximum_extra_mat_solves}-extra-MatSolve counter limit"
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
    expected_q_count: int = MAX_EXTRA_MAT_SOLVES,
    factor_capabilities: Mapping[str, Any] | None = None,
) -> AugmentedCorrectionResult:
    """Apply one raw profile-sized inverse to both rows of an augmented error.

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
    if type(expected_q_count) is not int or expected_q_count <= 0:
        raise ValueError("expected_q_count must be a positive integer")
    lifecycle_facts = dict(factor_capabilities) if factor_capabilities is not None else None
    if lifecycle_facts is not None:
        expected_qs = set(range(expected_q_count))
        input_qs = lifecycle_facts.get("input_q_coverage")
        max_live_factors = lifecycle_facts.get("max_live_factors")
        max_live_matrices = lifecycle_facts.get("max_live_matrices")
        if (
            lifecycle_facts.get("factor_lifecycle_strategy") != "ONE_Q_REFACTOR_V19"
            or lifecycle_facts.get("all_q_source_csr_covered") is not True
            or not isinstance(input_qs, Sequence)
            or isinstance(input_qs, (str, bytes))
            or any(type(q) is not int for q in input_qs)
            or set(input_qs) != expected_qs
            or lifecycle_facts.get("all_q_solve_coverage") is not True
            or lifecycle_facts.get("all_q_fresh_factor_probe_covered") is not True
            or lifecycle_facts.get("all_q_factors_simultaneously_resident") is not False
            or lifecycle_facts.get("all_q_factors_reused") is not False
            or type(max_live_factors) is not int
            or not 1 <= max_live_factors <= 1
            or type(max_live_matrices) is not int
            or not 1 <= max_live_matrices <= 1
        ):
            raise ValueError(
                "V19 augmented correction requires verified all-q input/probe/solve "
                "coverage and max-live factor/matrix <= 1"
            )
    all_q_factors_reused = (
        True if lifecycle_facts is None
        else lifecycle_facts.get("all_q_factors_reused") is True
    )
    all_four_q_factors_reused = expected_q_count == 4 and all_q_factors_reused

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
                "maximum_extra_mat_solves": expected_q_count,
                "all_q_factors_reused": all_q_factors_reused,
                "all_four_q_factors_reused": all_four_q_factors_reused,
                "factor_lifecycle_capabilities": lifecycle_facts,
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
                "expected_q_count": expected_q_count,
                "all_q_phases_covered": False,
                "all_four_q_phases_covered": False,
                "solve_seconds": 0.0,
                "scratch_bytes_estimate": simultaneous_live_array_bytes,
                "additional_payload_bytes": additional_payload_bytes,
                "simultaneous_live_array_bytes": simultaneous_live_array_bytes,
                "maximum_corrections": 1,
                "factor_lifecycle_capabilities": lifecycle_facts,
                "all_q_factors_reused": all_q_factors_reused,
                "all_four_q_factors_reused": all_four_q_factors_reused,
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
    factor_calls_before, factor_calls_after, solve_count = _counter_facts(
        call_facts, expected_q_count
    )
    q_rows = list(call_facts.get("q_true_residuals", ()))
    q_coverage = _q_phase_coverage(q_rows)
    all_q_phases_covered = _q_rows_cover_expected(q_rows, expected_q_count)
    all_four_q_phases_covered = expected_q_count == 4 and all_q_phases_covered
    counter_source = call_facts.get("counter_source")
    if require_verified_solve_counter:
        if (
            solve_count is None
            or counter_source != FACTOR_CALL_COUNTER_SOURCE
            or solve_count != expected_q_count
            or not all_q_phases_covered
        ):
            raise ValueError(
                "production augmented correction requires a verified "
                f"{expected_q_count}-call factors.calls delta and coverage of "
                f"q=0..{expected_q_count - 1}"
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
            "expected_q_count": expected_q_count,
            "all_q_phases_covered": all_q_phases_covered,
            "all_four_q_phases_covered": all_four_q_phases_covered,
            "solve_seconds": float(solve_seconds),
            "scratch_bytes_estimate": simultaneous_live_array_bytes,
            "actual_explicit_live_array_bytes": actual_live_array_bytes,
            "additional_payload_bytes": additional_payload_bytes,
            "simultaneous_live_array_bytes": simultaneous_live_array_bytes,
            "maximum_corrections": 1,
            "nonrecursive_raw_inverse": True,
            "full_fe_and_port_updated_together": True,
            "factor_lifecycle_capabilities": lifecycle_facts,
            "all_q_factors_reused": all_q_factors_reused,
            "all_four_q_factors_reused": all_four_q_factors_reused,
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


def recompute_v15_candidate_facts(
    candidate: Mapping[str, Any], *, profile_identity: str | None = None
) -> dict[str, Any]:
    """Rebuild V15 admission metrics from saved raw norms and actual q rows."""

    raw = candidate.get("raw_facts", {})
    if not isinstance(raw, Mapping):
        raise TypeError("V15 candidate raw_facts must be a mapping")
    scale = float(raw.get("effective_rhs_scale", np.nan))
    eliminated_norm = float(raw.get("eliminated_fe_residual_norm", np.nan))
    complete_norm = float(raw.get("complete_augmented_fe_residual_norm", np.nan))
    budget_terms = raw.get("budget_term_norms", {})
    if not isinstance(budget_terms, Mapping):
        raise TypeError("V15 candidate budget_term_norms must be a mapping")
    raw_profile_identity = raw.get("profile_identity")
    if raw_profile_identity is not None and profile_identity is not None and raw_profile_identity != profile_identity:
        raise ValueError("V15 candidate raw profile identity differs from its registered outer profile")
    trusted_profile_identity = raw_profile_identity or profile_identity
    inventory = _registered_v15_profile_inventory(trusted_profile_identity)
    if inventory["q_count"] == 8 and raw_profile_identity != inventory["identity"]:
        raise ValueError("V18 Ny8 candidate raw facts must explicitly record their profile identity")
    sector_terms = budget_terms.get("lifted_sector_errors")
    if not isinstance(sector_terms, Sequence) or isinstance(sector_terms, (str, bytes)):
        raise TypeError("V15 candidate lifted-sector budget terms must be a sequence")
    if len(sector_terms) != inventory["twist_count"]:
        raise ValueError("V15 candidate budget does not cover every registered twist sector")
    budget_numerator = float(
        float(budget_terms.get("d_b", np.nan))
        + sum(float(value) for value in sector_terms)
        + float(budget_terms.get("d_A", np.nan))
        + float(budget_terms.get("B_delta_alpha", np.nan))
    )
    alpha_norm = float(raw.get("alpha_closure_residual_norm", np.nan))
    alpha_scale = float(raw.get("alpha_closure_original_scale", np.nan))
    alpha_frozen_scale = float(raw.get("alpha_closure_frozen_scale", np.nan))
    q_rows = raw.get("q_true_residuals")
    if not isinstance(q_rows, Sequence) or isinstance(q_rows, (str, bytes)):
        raise TypeError("V15 candidate q_true_residuals must be a sequence")
    q_coverage = _q_rows_cover_expected(q_rows, inventory["q_count"])
    q_relatives: list[float] = []
    q_rows_consistent = bool(q_coverage)
    for row in q_rows:
        if not isinstance(row, Mapping):
            q_rows_consistent = False
            continue
        rhs_norm = float(row.get("rhs_norm", np.nan))
        residual_norm = float(row.get("true_residual_norm", np.nan))
        recomputed_q_relative = _zero_safe_relative(residual_norm, rhs_norm)
        recorded_q_relative = float(row.get("true_residual_relative", np.nan))
        q_rows_consistent = q_rows_consistent and bool(
            np.isfinite(rhs_norm)
            and np.isfinite(residual_norm)
            and rhs_norm >= 0.0
            and residual_norm >= 0.0
            and recorded_q_relative == recomputed_q_relative
        )
        q_relatives.append(recomputed_q_relative)
    q_max = max(
        q_relatives,
        default=float("inf"),
    )
    retained_mode_count = int(raw.get("retained_mode_count", -1))
    sector_facts = raw.get("native_sector_facts")
    mode_ids: list[int] = []
    sector_by_twist: dict[int, Mapping[str, Any]] = {}
    sector_mapping_valid = bool(
        isinstance(sector_facts, Sequence)
        and not isinstance(sector_facts, (str, bytes))
        and len(sector_facts) == inventory["twist_count"]
        and all(isinstance(row, Mapping) for row in sector_facts)
    )
    if sector_mapping_valid:
        for sector in sector_facts:
            twist = sector.get("twist_index")
            if type(twist) is not int or twist in sector_by_twist:
                sector_mapping_valid = False
                break
            sector_by_twist[twist] = sector
        sector_mapping_valid = sector_mapping_valid and set(sector_by_twist) == set(
            range(inventory["twist_count"])
        )
    if sector_mapping_valid:
        for twist, expected_mode_count in enumerate(inventory["sector_port_counts"]):
            ids = sector_by_twist[twist].get("mode_indices")
            if (
                not isinstance(ids, Sequence)
                or isinstance(ids, (str, bytes))
                or any(type(value) is not int for value in ids)
                or len(ids) != expected_mode_count
            ):
                sector_mapping_valid = False
                break
            mode_ids.extend(ids)
    sector_mapping_valid = bool(
        sector_mapping_valid
        and retained_mode_count == inventory["mode_count"]
        and len(mode_ids) == inventory["mode_count"]
        and len(set(mode_ids)) == inventory["mode_count"]
        and sorted(mode_ids) == list(range(inventory["mode_count"]))
    )
    closure_norm = float(raw.get("decomposition_closure_norm", np.nan))
    closure_scale = float(raw.get("decomposition_closure_scale", np.nan))
    recomputed_metrics = {
        "eliminated_fe": _zero_safe_relative(eliminated_norm, scale),
        "complete_augmented_fe": _zero_safe_relative(complete_norm, scale),
        "noncancelling_budget": _zero_safe_relative(budget_numerator, scale),
        "alpha_closure": _zero_safe_relative(alpha_norm, alpha_scale),
        "q_solve": q_max,
    }
    recomputed_frozen = {
        "eliminated_fe": recomputed_metrics["eliminated_fe"],
        "complete_augmented_fe": recomputed_metrics["complete_augmented_fe"],
        "noncancelling_budget": recomputed_metrics["noncancelling_budget"],
        "alpha_closure": _zero_safe_relative(alpha_norm, alpha_frozen_scale),
    }
    recorded_metrics = candidate.get("metrics", {})
    recorded_frozen = candidate.get("frozen_scale_metrics", {})
    metrics_match = isinstance(recorded_metrics, Mapping) and all(
        name in recorded_metrics
        and float(recorded_metrics[name]) == value
        for name, value in recomputed_metrics.items()
    )
    frozen_match = isinstance(recorded_frozen, Mapping) and all(
        name in recorded_frozen
        and float(recorded_frozen[name]) == value
        for name, value in recomputed_frozen.items()
    )
    state_sha = str(raw.get("state_sha256", ""))
    state_hash_valid = len(state_sha) == 64 and all(
        character in "0123456789abcdef" for character in state_sha
    )
    state_hash_valid = state_hash_valid and candidate.get("state_sha256") == state_sha
    closure_relative = _zero_safe_relative(closure_norm, closure_scale)
    all_finite = all(
        np.isfinite(value)
        for value in (
            scale, eliminated_norm, complete_norm, budget_numerator, alpha_norm,
            alpha_scale, alpha_frozen_scale, q_max, closure_norm, closure_scale,
            closure_relative,
        )
    )
    return {
        "metrics": recomputed_metrics,
        "frozen_scale_metrics": recomputed_frozen,
        "budget_numerator": budget_numerator,
        "q_phase_coverage": q_coverage,
        "expected_q_count": inventory["q_count"],
        "expected_twist_count": inventory["twist_count"],
        "q_rows_consistent": q_rows_consistent,
        "sector_mode_mapping_valid": sector_mapping_valid,
        "decomposition_closure_relative": closure_relative,
        "state_sha256": state_sha,
        "raw_facts_consistent": bool(
            metrics_match and frozen_match and state_hash_valid and all_finite
        ),
    }


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

    if strategy == NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        alpha_limit = float(V15_REFERENCE_PC_LIMITS["alpha_closure"])
        q_limit = float(V15_REFERENCE_PC_LIMITS["q_solve"])
        candidates = last_facts.get("candidate_metrics")
        recorded = last_facts.get("candidate_selection")
        q_rows = last_facts.get("q_true_residuals_selected", ())
        failure_reason = None
        try:
            if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
                raise TypeError("candidate_metrics is not a sequence")
            profile_identity = last_facts.get("profile_identity")
            if profile_identity is None and candidates:
                first_raw = candidates[0].get("raw_facts", {})
                if isinstance(first_raw, Mapping):
                    profile_identity = first_raw.get("profile_identity")
            recomputed = select_v15_reference_pc_candidate(
                candidates, profile_identity=profile_identity
            )
            selected_index = int(recomputed["selected_candidate_index"])
            selected = candidates[selected_index]
            metrics = selected.get("metrics", {})
            selected_raw = selected.get("raw_facts", {})
            raw_recheck = recompute_v15_candidate_facts(
                selected, profile_identity=profile_identity
            )
            q_coverage = (
                isinstance(q_rows, Sequence)
                and not isinstance(q_rows, (str, bytes))
                and _q_rows_cover_expected(q_rows, raw_recheck["expected_q_count"])
            )
            q_rows_pass = bool(q_coverage) and all(
                np.isfinite(float(row.get("true_residual_relative", np.inf)))
                and float(row.get("true_residual_relative", np.inf))
                <= V15_REFERENCE_PC_LIMITS["q_solve"]
                for row in q_rows
            )
            selected_closure = float(
                last_facts.get("selected_decomposition_closure_relative", np.inf)
            )
            reported_metrics = last_facts.get("selected_v15_metrics", {})
            reported_raw = last_facts.get("selected_v15_raw_facts", {})
            selected_state_sha = str(
                last_facts.get("selected_state_sha256", "")
            )
            selected_q_max = max(
                (
                    float(row.get("true_residual_relative", np.inf))
                    for row in q_rows
                    if isinstance(row, Mapping)
                ),
                default=float("inf"),
            )
            if not isinstance(recorded, Mapping):
                failure_reason = "recorded_candidate_selection_missing"
            elif (
                recorded.get("admission") != recomputed["admission"]
                or recorded.get("selected_candidate_index") != selected_index
            ):
                failure_reason = "recorded_candidate_selection_mismatch"
            elif last_facts.get("reference_pc_strategy") != strategy:
                failure_reason = "recorded_reference_pc_strategy_mismatch"
            elif not recomputed["admitted"]:
                failure_reason = "candidate_selection_rejected"
            elif not q_coverage or last_facts.get("all_q_used") is not True:
                failure_reason = "selected_q_phase_coverage_failed"
            elif list(q_rows) != list(selected_raw.get("q_true_residuals", ())):
                failure_reason = "selected_q_rows_mismatch"
            elif not q_rows_pass or not np.isfinite(q_relative) or q_relative > V15_REFERENCE_PC_LIMITS["q_solve"]:
                failure_reason = "selected_q_solve_contract_failed"
            elif (
                not np.isfinite(selected_q_max)
                or selected_q_max != q_relative
                or selected_q_max != float(metrics.get("q_solve", np.inf))
            ):
                failure_reason = "selected_q_metric_mismatch"
            elif (
                float(last_facts.get("port_identity_relative", np.inf))
                != float(metrics.get("alpha_closure", np.inf))
            ):
                failure_reason = "selected_alpha_metric_mismatch"
            elif not np.isfinite(selected_closure) or selected_closure > V15_DECOMPOSITION_CLOSURE_LIMIT:
                failure_reason = "selected_native_decomposition_closure_failed"
            elif selected_closure != raw_recheck["decomposition_closure_relative"]:
                failure_reason = "selected_decomposition_closure_mismatch"
            elif (
                not isinstance(selected_raw, Mapping)
                or not isinstance(reported_raw, Mapping)
                or dict(reported_raw) != dict(selected_raw)
            ):
                failure_reason = "selected_raw_facts_mismatch"
            elif (
                not selected_state_sha
                or selected_state_sha != raw_recheck["state_sha256"]
            ):
                failure_reason = "selected_state_hash_mismatch"
            elif not isinstance(reported_metrics, Mapping) or any(
                not np.isfinite(float(metrics.get(name, np.inf)))
                or float(reported_metrics.get(name, np.inf)) != float(metrics.get(name, np.inf))
                for name in V15_REFERENCE_PC_LIMITS
            ):
                failure_reason = "selected_v15_metric_mismatch"
            return {
                "passed": failure_reason is None,
                "strategy": strategy,
                "admission": recomputed["admission"],
                "selected_candidate_index": selected_index,
                "recorded_admission": recorded.get("admission") if isinstance(recorded, Mapping) else None,
                "recorded_selected_candidate_index": recorded.get("selected_candidate_index") if isinstance(recorded, Mapping) else None,
                "port_identity_relative": alpha,
                "port_identity_limit": alpha_limit,
                "maximum_q_true_residual_relative": q_relative,
                "q_true_residual_limit": q_limit,
                "profile_identity": profile_identity,
                "all_q_phase_rows_covered": bool(q_coverage),
                "all_four_q_phase_rows_covered": (
                    bool(q_coverage) and raw_recheck["expected_q_count"] == 4
                ),
                "selected_decomposition_closure_relative": selected_closure,
                "decomposition_closure_limit": V15_DECOMPOSITION_CLOSURE_LIMIT,
                "selected_state_sha256": selected_state_sha,
                "selection_recomputed_from_candidate_metrics": True,
                "candidate_selection": recomputed,
                "failure_reason": failure_reason,
            }
        except (TypeError, ValueError, KeyError, IndexError, OverflowError) as exc:
            return {
                "passed": False,
                "strategy": strategy,
                "admission": V15_REFERENCE_PC_REJECTED,
                "port_identity_relative": alpha,
                "port_identity_limit": alpha_limit,
                "maximum_q_true_residual_relative": q_relative,
                "q_true_residual_limit": q_limit,
                "reason": f"candidate_selection_recheck_error:{type(exc).__name__}:{exc}",
                "selection_recomputed_from_candidate_metrics": True,
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
    "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15",
    "REFERENCE_PC_REJECTED",
    "REFERENCE_PC_STRATEGIES",
    "STRICT_ONLY",
    "STRICT_REFERENCE_LIMITS",
    "STRICT_REFERENCE_PASS",
    "STRICT_THEN_BOUNDED_INEXACT_V13",
    "V15_DECOMPOSITION_CLOSURE_LIMIT",
    "V15_FROZEN_SCALE_LIMITS",
    "V15_REFERENCE_PC_LIMITS",
    "V15_REFERENCE_PC_PASS",
    "V15_REFERENCE_PC_REJECTED",
    "evaluate_v15_non_cancelling_budget",
    "apply_one_augmented_residual_correction",
    "augmented_rhs_sha256",
    "augmented_state_sha256",
    "normalized_max_exceedance",
    "q_solve_limit",
    "recheck_reference_pc_final_admission",
    "recompute_v15_candidate_facts",
    "select_reference_pc_candidate",
    "select_v15_reference_pc_candidate",
    "stable_euclidean_norm",
]
