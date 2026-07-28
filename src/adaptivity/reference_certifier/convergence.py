"""Three-point convergence analysis and fail-closed qualification."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TypeAlias

from .contracts import (
    ComplexValue,
    ReferenceCampaign,
    ReferenceRunResult,
    REQUIRED_TOTAL_SCALARS,
    fixed_order_inventory,
)


QUALIFIED = "qualified"
REFERENCE_CERTIFICATION_FAILED = "REFERENCE_CERTIFICATION_FAILED"
REFERENCE_CERTIFICATION_INCOMPLETE = "REFERENCE_CERTIFICATION_INCOMPLETE"

_NumericValue: TypeAlias = float | complex
_StoredValue: TypeAlias = float | ComplexValue


@dataclass(frozen=True, slots=True)
class CertificationPolicy:
    """Numerical limits used only by the evaluator-side certifier."""

    residual_limit: float = 1.0e-9
    energy_balance_limit: float = 1.0e-9
    closure_volume_limit: float = 1.0e-9
    minimum_h5_memory_headroom_fraction: float = 0.20
    fine_difference_ratio_limit: float = 0.90
    maximum_fit_condition_number: float = 1.0e8
    maximum_fit_relative_residual: float = 1.0e-8
    maximum_complex_ratio_imaginary_fraction: float = 1.0e-6
    maximum_fitted_q: float = 16.0
    formal_power_oscillation_floor: float = 1.0e-9
    formal_amplitude_oscillation_floor: float = 1.0e-6
    formal_total_oscillation_floor: float = 1.0e-6
    explained_oscillatory_output_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        positive_fields = (
            "residual_limit",
            "energy_balance_limit",
            "closure_volume_limit",
            "maximum_fit_condition_number",
            "maximum_fit_relative_residual",
            "maximum_complex_ratio_imaginary_fraction",
            "maximum_fitted_q",
            "formal_power_oscillation_floor",
            "formal_amplitude_oscillation_floor",
            "formal_total_oscillation_floor",
        )
        for field_name in positive_fields:
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be finite and positive")
            object.__setattr__(self, field_name, value)
        for field_name in (
            "minimum_h5_memory_headroom_fraction",
            "fine_difference_ratio_limit",
        ):
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"{field_name} must be in [0, 1]")
            object.__setattr__(self, field_name, value)
        if not isinstance(self.explained_oscillatory_output_ids, tuple):
            raise ValueError("explained_oscillatory_output_ids must be a tuple")
        if len(set(self.explained_oscillatory_output_ids)) != len(
            self.explained_oscillatory_output_ids
        ):
            raise ValueError("explained oscillatory output IDs must be unique")


@dataclass(frozen=True, slots=True)
class ThreePointConvergence:
    """Convergence evidence for one scalar or complex observable."""

    output_id: str
    category: str
    value_kind: str
    h10_value: _StoredValue
    h7p5_value: _StoredValue
    h5_value: _StoredValue
    d_10_7p5: float
    d_7p5_5: float
    difference_ratio_fine_over_coarse: float | None
    monotonic: bool
    sign_oscillation: bool
    fine_difference_significantly_smaller: bool
    fit_stable: bool
    fit_reason: str
    fitted_q: float | None
    fitted_q_positive: bool
    fit_condition_number: float | None
    fit_relative_residual: float | None
    reference_center: _StoredValue
    extrapolated_center: _StoredValue | None
    h5_to_extrapolated_center: float | None
    reference_uncertainty: float
    trend: str


@dataclass(frozen=True, slots=True)
class CertificationGateSummary:
    """All independently recomputed certification gates."""

    all_runs_completed: bool
    physical_identity_exact: bool
    fixed_order_inventory_exact: bool
    order_metadata_exact: bool
    required_total_inventory_complete: bool
    observable_inventory_exact: bool
    selected_interface_fields_present: bool
    selected_volume_fields_present: bool
    official_postprocessing_passed: bool
    residual_gate_passed: bool
    energy_gate_passed: bool
    zero_swap_passed: bool
    h5_memory_headroom_passed: bool
    no_unexplained_oscillation: bool
    selected_fields_stable: bool
    reference_uncertainty_quantified: bool

    @property
    def passed(self) -> bool:
        return all(
            (
                self.all_runs_completed,
                self.physical_identity_exact,
                self.fixed_order_inventory_exact,
                self.order_metadata_exact,
                self.required_total_inventory_complete,
                self.observable_inventory_exact,
                self.selected_interface_fields_present,
                self.selected_volume_fields_present,
                self.official_postprocessing_passed,
                self.residual_gate_passed,
                self.energy_gate_passed,
                self.zero_swap_passed,
                self.h5_memory_headroom_passed,
                self.no_unexplained_oscillation,
                self.selected_fields_stable,
                self.reference_uncertainty_quantified,
            )
        )


@dataclass(frozen=True, slots=True)
class ReferenceCertification:
    """Evaluator result retained by the hidden package writer."""

    campaign: ReferenceCampaign
    policy: CertificationPolicy
    status: str
    qualified: bool
    reasons: tuple[str, ...]
    gates: CertificationGateSummary
    convergence: tuple[ThreePointConvergence, ...]

    def __post_init__(self) -> None:
        allowed = {
            QUALIFIED,
            REFERENCE_CERTIFICATION_FAILED,
            REFERENCE_CERTIFICATION_INCOMPLETE,
        }
        if self.status not in allowed:
            raise ValueError(f"unsupported certification status: {self.status}")
        if self.qualified != (self.status == QUALIFIED):
            raise ValueError("qualified flag and status disagree")
        if self.qualified != self.gates.passed:
            raise ValueError("qualified flag and recomputed gates disagree")


@dataclass(frozen=True, slots=True)
class _Observable:
    output_id: str
    category: str
    value_kind: str
    value: _NumericValue


def _stored_value(value: _NumericValue) -> _StoredValue:
    if isinstance(value, complex):
        return ComplexValue.from_complex(value)
    return float(value)


def _order_prefix(port: str, m: int, n: int) -> str:
    return f"order/{port}/m{m}/n{n}"


def _run_observables(run: ReferenceRunResult) -> dict[str, _Observable]:
    rows: dict[str, _Observable] = {}

    def add(
        output_id: str,
        category: str,
        value_kind: str,
        value: _NumericValue,
    ) -> None:
        if output_id in rows:
            raise ValueError(f"duplicate observable ID: {output_id}")
        rows[output_id] = _Observable(
            output_id=output_id,
            category=category,
            value_kind=value_kind,
            value=value,
        )

    for observation in run.scalar_observations:
        add(
            f"scalar/{observation.name}",
            observation.category,
            "real",
            observation.value,
        )
    for observation in run.complex_observations:
        add(
            f"complex/{observation.name}",
            observation.category,
            "complex",
            observation.value.as_complex(),
        )
    for order in run.diffraction_orders:
        prefix = _order_prefix(order.port, order.m, order.n)
        fixed_order = order.identity in set(fixed_order_inventory())
        if order.propagating:
            assert order.total_power is not None
            assert order.cross_polarized_power is not None
            add(
                f"{prefix}/total_power",
                (
                    "formal_order_power"
                    if fixed_order
                    else "spectrum_diagnostic"
                ),
                "real",
                order.total_power,
            )
            add(
                f"{prefix}/cross_polarized_power",
                "order_diagnostic",
                "real",
                order.cross_polarized_power,
            )
        add(
            f"{prefix}/co_polarized_amplitude",
            (
                "formal_order_amplitude"
                if fixed_order
                else "spectrum_diagnostic"
            ),
            "complex",
            order.co_polarized_amplitude.as_complex(),
        )
        add(
            f"{prefix}/cross_polarized_amplitude",
            "order_diagnostic",
            "complex",
            order.cross_polarized_amplitude.as_complex(),
        )
        add(
            f"{prefix}/kz",
            "order_identity",
            "complex",
            order.kz.as_complex(),
        )
        add(
            f"{prefix}/admittance",
            "order_identity",
            "complex",
            order.admittance.as_complex(),
        )
    if run.gate.completed:
        assert run.gate.full_explicit_true_residual is not None
        assert run.gate.energy_balance_error is not None
        assert run.gate.closure_volume_error is not None
        add(
            "gate/full_explicit_true_residual",
            "gate",
            "real",
            run.gate.full_explicit_true_residual,
        )
        add(
            "gate/energy_balance_error",
            "gate",
            "real",
            run.gate.energy_balance_error,
        )
        add(
            "gate/closure_volume_error",
            "gate",
            "real",
            run.gate.closure_volume_error,
        )
    return rows


def _ratio_for_q(q: float) -> float:
    h10 = math.exp(q * math.log(10.0))
    h7p5 = math.exp(q * math.log(7.5))
    h5 = math.exp(q * math.log(5.0))
    return (h10 - h7p5) / (h7p5 - h5)


def _solve_positive_q(target_ratio: float, maximum_q: float) -> float | None:
    minimum_q = 1.0e-8
    lower_value = _ratio_for_q(minimum_q)
    upper_value = _ratio_for_q(maximum_q)
    numerical_margin = 256.0 * math.ulp(
        max(abs(lower_value), abs(upper_value), abs(target_ratio), 1.0)
    )
    if target_ratio < lower_value - numerical_margin:
        return None
    if target_ratio > upper_value + numerical_margin:
        return None
    if abs(target_ratio - lower_value) <= numerical_margin:
        return minimum_q
    lower = minimum_q
    upper = maximum_q
    for _ in range(100):
        midpoint = 0.5 * (lower + upper)
        if _ratio_for_q(midpoint) < target_ratio:
            lower = midpoint
        else:
            upper = midpoint
    return 0.5 * (lower + upper)


def _least_squares_fit(
    values: tuple[_NumericValue, _NumericValue, _NumericValue],
    q: float,
) -> tuple[complex, float, float]:
    x_values = tuple((h / 10.0) ** q for h in (10.0, 7.5, 5.0))
    sx = sum(x_values)
    sxx = sum(value * value for value in x_values)
    sy = sum(complex(value) for value in values)
    sxy = sum(
        x_value * complex(value)
        for x_value, value in zip(x_values, values, strict=True)
    )
    denominator = 3.0 * sxx - sx * sx
    if denominator <= 0.0:
        raise ArithmeticError("singular three-point extrapolation fit")
    center = (sxx * sy - sx * sxy) / denominator
    coefficient = (3.0 * sxy - sx * sy) / denominator
    residual = math.sqrt(
        sum(
            abs(complex(value) - (center + coefficient * x_value)) ** 2
            for x_value, value in zip(x_values, values, strict=True)
        )
    )
    trace = 3.0 + sxx
    discriminant = max(trace * trace - 4.0 * denominator, 0.0)
    lambda_max = 0.5 * (trace + math.sqrt(discriminant))
    lambda_min = 0.5 * (trace - math.sqrt(discriminant))
    condition_number = (
        math.inf if lambda_min <= 0.0 else math.sqrt(lambda_max / lambda_min)
    )
    return center, residual, condition_number


def analyze_three_point(
    *,
    output_id: str,
    category: str,
    h10_value: _NumericValue,
    h7p5_value: _NumericValue,
    h5_value: _NumericValue,
    policy: CertificationPolicy = CertificationPolicy(),
) -> ThreePointConvergence:
    """Analyze ``J(h)=J_star+C*h**q`` without assuming a stable fit."""

    values = (
        complex(h10_value),
        complex(h7p5_value),
        complex(h5_value),
    )
    value_kind = (
        "complex"
        if any(
            isinstance(value, complex)
            for value in (
                h10_value,
                h7p5_value,
                h5_value,
            )
        )
        else "real"
    )
    coarse_delta = values[0] - values[1]
    fine_delta = values[1] - values[2]
    d_coarse = abs(coarse_delta)
    d_fine = abs(fine_delta)
    value_scale = max(*(abs(value) for value in values), 1.0e-300)
    zero_tolerance = max(
        1.0e-300,
        64.0 * math.ulp(value_scale),
    )
    is_constant = d_coarse <= zero_tolerance and d_fine <= zero_tolerance
    if d_coarse > zero_tolerance:
        fine_over_coarse: float | None = d_fine / d_coarse
    elif d_fine <= zero_tolerance:
        fine_over_coarse = 0.0
    else:
        fine_over_coarse = None
    if d_coarse > zero_tolerance and d_fine > zero_tolerance:
        directional_product = (
            coarse_delta.real * fine_delta.real + coarse_delta.imag * fine_delta.imag
        )
        alignment = directional_product / (d_coarse * d_fine)
        sign_oscillation = alignment < 0.0
        monotonic = alignment >= 1.0 - 1.0e-8
    else:
        sign_oscillation = False
        monotonic = is_constant
    fine_smaller = d_fine <= policy.fine_difference_ratio_limit * max(
        d_coarse, zero_tolerance
    )

    fitted_q: float | None = None
    extrapolated_center: complex | None = None
    condition_number: float | None = None
    fit_relative_residual: float | None = None
    fit_stable = False
    fit_reason = "insufficient_nonzero_differences"

    if is_constant:
        fit_stable = True
        fit_reason = "constant_within_roundoff"
        extrapolated_center = values[2]
    elif d_coarse > zero_tolerance and d_fine > zero_tolerance:
        observed_ratio = coarse_delta / fine_delta
        ratio_scale = max(abs(observed_ratio.real), 1.0e-300)
        imaginary_fraction = abs(observed_ratio.imag) / ratio_scale
        if observed_ratio.real <= 0.0 or sign_oscillation:
            fit_reason = "oscillatory_or_nonpositive_difference_ratio"
        elif imaginary_fraction > policy.maximum_complex_ratio_imaginary_fraction:
            fit_reason = "complex_differences_not_collinear"
        else:
            fitted_q = _solve_positive_q(
                observed_ratio.real,
                policy.maximum_fitted_q,
            )
            if fitted_q is None:
                fit_reason = "no_positive_q_in_accepted_range"
            else:
                try:
                    (
                        extrapolated_center,
                        residual,
                        condition_number,
                    ) = _least_squares_fit(values, fitted_q)
                except ArithmeticError:
                    fit_reason = "singular_fit"
                    extrapolated_center = None
                else:
                    difference_scale = max(
                        d_coarse,
                        d_fine,
                        zero_tolerance,
                    )
                    fit_relative_residual = residual / difference_scale
                    if condition_number > policy.maximum_fit_condition_number:
                        fit_reason = "fit_condition_number_exceeded"
                    elif fit_relative_residual > policy.maximum_fit_relative_residual:
                        fit_reason = "fit_residual_exceeded"
                    else:
                        fit_stable = True
                        fit_reason = "stable_positive_q_fit"

    if fit_stable and extrapolated_center is not None:
        h5_to_center = abs(values[2] - extrapolated_center)
        uncertainty = max(d_fine, h5_to_center)
    else:
        extrapolated_center = None
        h5_to_center = None
        uncertainty = max(d_coarse, d_fine)

    if is_constant:
        trend = "constant"
    elif sign_oscillation:
        trend = "oscillatory"
    elif fit_stable:
        trend = "convergent_positive_q"
    elif fine_smaller:
        trend = "shrinking_difference_without_stable_fit"
    else:
        trend = "nonconvergent_or_indeterminate"

    def restore(value: complex) -> _StoredValue:
        if value_kind == "complex":
            return ComplexValue.from_complex(value)
        return float(value.real)

    return ThreePointConvergence(
        output_id=output_id,
        category=category,
        value_kind=value_kind,
        h10_value=restore(values[0]),
        h7p5_value=restore(values[1]),
        h5_value=restore(values[2]),
        d_10_7p5=float(d_coarse),
        d_7p5_5=float(d_fine),
        difference_ratio_fine_over_coarse=fine_over_coarse,
        monotonic=monotonic,
        sign_oscillation=sign_oscillation,
        fine_difference_significantly_smaller=fine_smaller,
        fit_stable=fit_stable,
        fit_reason=fit_reason,
        fitted_q=fitted_q,
        fitted_q_positive=(fitted_q is not None and fitted_q > 0.0),
        fit_condition_number=condition_number,
        fit_relative_residual=fit_relative_residual,
        reference_center=restore(values[2]),
        extrapolated_center=(
            restore(extrapolated_center) if extrapolated_center is not None else None
        ),
        h5_to_extrapolated_center=h5_to_center,
        reference_uncertainty=float(uncertainty),
        trend=trend,
    )


def _fixed_order_inventory_exact(run: ReferenceRunResult) -> bool:
    return set(fixed_order_inventory()).issubset(
        {row.identity for row in run.diffraction_orders}
    )


def _order_metadata_exact(campaign: ReferenceCampaign) -> bool:
    if not all(_fixed_order_inventory_exact(run) for run in campaign.runs):
        return False
    metadata_by_run = []
    for run in campaign.runs:
        metadata_by_run.append(
            {
                row.identity: (
                    row.propagating,
                    row.normalization_identity,
                    row.kz,
                    row.admittance,
                )
                for row in run.diffraction_orders
            }
        )
    return metadata_by_run[0] == metadata_by_run[1] == metadata_by_run[2]


def _field_block_stability(
    observable_maps: tuple[dict[str, _Observable], ...],
    *,
    category: str,
) -> bool:
    """Check selected fields by block relative-L2, not pointwise signs."""

    output_ids = tuple(
        sorted(
            output_id
            for output_id, row in observable_maps[0].items()
            if row.category == category
        )
    )
    if not output_ids:
        return False
    if any(
        tuple(
            sorted(
                output_id
                for output_id, row in rows.items()
                if row.category == category
            )
        )
        != output_ids
        for rows in observable_maps[1:]
    ):
        return False
    vectors = tuple(
        tuple(complex(rows[output_id].value) for output_id in output_ids)
        for rows in observable_maps
    )

    def norm(values: tuple[complex, ...]) -> float:
        return math.sqrt(sum(abs(value) ** 2 for value in values))

    coarse_difference = norm(
        tuple(
            left - right
            for left, right in zip(vectors[0], vectors[1], strict=True)
        )
    )
    fine_difference = norm(
        tuple(
            left - right
            for left, right in zip(vectors[1], vectors[2], strict=True)
        )
    )
    coarse_scale = max(norm(vectors[0]), norm(vectors[1]), 1.0e-300)
    fine_scale = max(norm(vectors[1]), norm(vectors[2]), 1.0e-300)
    coarse_relative = coarse_difference / coarse_scale
    fine_relative = fine_difference / fine_scale
    tolerance = 512.0 * math.ulp(max(coarse_relative, fine_relative, 1.0))
    return fine_relative <= coarse_relative + tolerance


def _formal_oscillation_is_material(
    row: ThreePointConvergence,
    policy: CertificationPolicy,
) -> bool:
    if not row.sign_oscillation:
        return False
    if row.category == "formal_order_power":
        floor = policy.formal_power_oscillation_floor
    elif row.category == "formal_order_amplitude":
        floor = policy.formal_amplitude_oscillation_floor
    elif row.category == "total":
        floor = policy.formal_total_oscillation_floor
    else:
        return False
    return max(row.d_10_7p5, row.d_7p5_5) > floor


def _field_categories_present(
    run: ReferenceRunResult,
) -> tuple[bool, bool]:
    categories = {
        *(row.category for row in run.scalar_observations),
        *(row.category for row in run.complex_observations),
    }
    return (
        "interface_field" in categories,
        "volume_field" in categories,
    )


def certify_reference_campaign(
    campaign: ReferenceCampaign,
    *,
    policy: CertificationPolicy = CertificationPolicy(),
) -> ReferenceCertification:
    """Recompute all Phase-A qualification gates and convergence evidence."""

    runs = campaign.runs
    completed = all(run.gate.completed for run in runs)
    identity_exact = runs[0].identity == runs[1].identity == runs[2].identity
    fixed_inventory = all(_fixed_order_inventory_exact(run) for run in runs)
    order_metadata = _order_metadata_exact(campaign)
    required_totals = all(
        REQUIRED_TOTAL_SCALARS.issubset({row.name for row in run.scalar_observations})
        for run in runs
    )
    interface_present = all(_field_categories_present(run)[0] for run in runs)
    volume_present = all(_field_categories_present(run)[1] for run in runs)
    official = all(
        run.gate.completed and run.gate.official_postprocessing_passed for run in runs
    )
    residual = all(
        run.gate.completed
        and run.gate.full_explicit_true_residual is not None
        and run.gate.full_explicit_true_residual <= policy.residual_limit
        for run in runs
    )
    energy = all(
        run.gate.completed
        and run.gate.energy_balance_error is not None
        and run.gate.closure_volume_error is not None
        and (run.gate.energy_balance_error <= policy.energy_balance_limit)
        and run.gate.closure_volume_error <= policy.closure_volume_limit
        for run in runs
    )
    zero_swap = all(run.gate.swap_peak_bytes == 0 for run in runs)
    h5_headroom = (
        campaign.h5.gate.completed
        and campaign.h5.gate.minimum_memory_headroom_fraction is not None
        and (
            campaign.h5.gate.minimum_memory_headroom_fraction
            >= policy.minimum_h5_memory_headroom_fraction
        )
    )

    observable_maps: tuple[dict[str, _Observable], ...]
    observable_maps = tuple(_run_observables(run) for run in runs)
    observable_inventory = (
        set(observable_maps[0]) == set(observable_maps[1]) == set(observable_maps[2])
    )
    if observable_inventory:
        for output_id in observable_maps[0]:
            metadata = {
                (
                    rows[output_id].category,
                    rows[output_id].value_kind,
                )
                for rows in observable_maps
            }
            if len(metadata) != 1:
                observable_inventory = False
                break

    convergence: tuple[ThreePointConvergence, ...] = ()
    if completed and observable_inventory:
        rows = []
        for output_id in sorted(observable_maps[0]):
            first = observable_maps[0][output_id]
            rows.append(
                analyze_three_point(
                    output_id=output_id,
                    category=first.category,
                    h10_value=observable_maps[0][output_id].value,
                    h7p5_value=observable_maps[1][output_id].value,
                    h5_value=observable_maps[2][output_id].value,
                    policy=policy,
                )
            )
        convergence = tuple(rows)

    explained = set(policy.explained_oscillatory_output_ids)
    unexplained_oscillation = tuple(
        row.output_id
        for row in convergence
        if (
            _formal_oscillation_is_material(row, policy)
            and row.output_id not in explained
        )
    )
    no_unexplained_oscillation = (
        completed and observable_inventory and not unexplained_oscillation
    )
    selected_fields_stable = (
        interface_present
        and volume_present
        and observable_inventory
        and _field_block_stability(
            observable_maps,
            category="interface_field",
        )
        and _field_block_stability(
            observable_maps,
            category="volume_field",
        )
    )
    uncertainty_quantified = bool(convergence) and all(
        math.isfinite(row.reference_uncertainty) and row.reference_uncertainty >= 0.0
        for row in convergence
    )

    gates = CertificationGateSummary(
        all_runs_completed=completed,
        physical_identity_exact=identity_exact,
        fixed_order_inventory_exact=fixed_inventory,
        order_metadata_exact=order_metadata,
        required_total_inventory_complete=required_totals,
        observable_inventory_exact=observable_inventory,
        selected_interface_fields_present=interface_present,
        selected_volume_fields_present=volume_present,
        official_postprocessing_passed=official,
        residual_gate_passed=residual,
        energy_gate_passed=energy,
        zero_swap_passed=zero_swap,
        h5_memory_headroom_passed=h5_headroom,
        no_unexplained_oscillation=no_unexplained_oscillation,
        selected_fields_stable=selected_fields_stable,
        reference_uncertainty_quantified=uncertainty_quantified,
    )

    reasons = []
    if not completed:
        for run in runs:
            if not run.gate.completed:
                label = str(run.h_nm).replace(".", "p")
                if run.gate.controlled_resource_stop:
                    reasons.append(f"h{label}_controlled_resource_stop")
                else:
                    reasons.append(f"h{label}_not_completed")
    for field_name in gates.__dataclass_fields__:
        if not getattr(gates, field_name):
            reasons.append(field_name)
    reasons.extend(
        f"unexplained_oscillation:{output_id}" for output_id in unexplained_oscillation
    )
    reasons = list(dict.fromkeys(reasons))

    if not completed:
        status = REFERENCE_CERTIFICATION_INCOMPLETE
    elif gates.passed:
        status = QUALIFIED
    else:
        status = REFERENCE_CERTIFICATION_FAILED
    return ReferenceCertification(
        campaign=campaign,
        policy=policy,
        status=status,
        qualified=(status == QUALIFIED),
        reasons=tuple(reasons),
        gates=gates,
        convergence=convergence,
    )


__all__ = [
    "CertificationGateSummary",
    "CertificationPolicy",
    "QUALIFIED",
    "REFERENCE_CERTIFICATION_FAILED",
    "REFERENCE_CERTIFICATION_INCOMPLETE",
    "ReferenceCertification",
    "ThreePointConvergence",
    "analyze_three_point",
    "certify_reference_campaign",
]
