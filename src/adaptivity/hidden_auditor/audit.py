"""Independent Task035e candidate-vs-hidden-reference audit."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .contracts import (
    FIXED_ORDER_KEYS,
    FIXED_PORTS,
    FORMAL_TOTAL_NAMES,
    FULL_SPECTRUM_GATE_SCHEMA,
    FULL_SPECTRUM_QUANTITIES,
    AuditGate,
    AuditItem,
    HiddenAuditContractError,
    HiddenAuditReport,
)
from .package_reader import CandidatePreflight


def _complex(value: Mapping[str, Any]) -> complex:
    return complex(float(value["real"]), float(value["imag"]))


def _json_complex(value: complex) -> dict[str, float]:
    return {"real": float(value.real), "imag": float(value.imag)}


def _stored_value(value: Mapping[str, Any]) -> float | complex:
    kind = value["kind"]
    if kind == "real":
        return float(value["value"])
    if kind == "complex":
        return _complex(value["value"])
    raise HiddenAuditContractError(f"unsupported stored value kind: {kind}")


def _json_value(value: float | complex) -> float | dict[str, float]:
    if isinstance(value, complex):
        return _json_complex(value)
    return float(value)


def _convergence_map(
    package: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = package["certification"]["convergence"]
    return {str(row["output_id"]): row for row in rows}


def _candidate_orders(
    preflight: CandidatePreflight,
) -> dict[tuple[str, int, int], Mapping[str, Any]]:
    return {
        (row["port"], int(row["m"]), int(row["n"])): row
        for row in preflight.outputs["orders"]
    }


def _reference_orders(
    package: Mapping[str, Any],
) -> dict[tuple[str, int, int], Mapping[str, Any]]:
    return {
        (row["port"], int(row["m"]), int(row["n"])): row
        for row in package["runs"][2]["diffraction_orders"]
    }


def _order_key(
    identity: tuple[str, int, int],
) -> tuple[int, int, int]:
    return FIXED_PORTS.index(identity[0]), -identity[1], identity[2]


def _order_identity_payload(
    identity: tuple[str, int, int],
) -> dict[str, int | str]:
    return {
        "port": identity[0],
        "m": identity[1],
        "n": identity[2],
    }


def _order_metadata_payload(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "kz": dict(row["kz"]),
        "admittance": dict(row["admittance"]),
        "normalization_identity": row["normalization_identity"],
    }


def _candidate_observations(
    preflight: CandidatePreflight,
) -> tuple[dict[str, float], dict[str, complex]]:
    scalars = {
        str(row["name"]): float(row["value"])
        for row in preflight.outputs["scalar_observations"]
    }
    complex_rows = {
        str(row["name"]): _complex(row["value"])
        for row in preflight.outputs["complex_observations"]
    }
    return scalars, complex_rows


def _reference_row(
    convergence: Mapping[str, Mapping[str, Any]],
    output_id: str,
    *,
    expected_kind: str,
) -> tuple[float | complex, float]:
    row = convergence.get(output_id)
    if row is None:
        raise HiddenAuditContractError(
            f"qualified reference lacks convergence row {output_id}"
        )
    if row["value_kind"] != expected_kind:
        raise HiddenAuditContractError(
            f"reference value kind differs for {output_id}"
        )
    center = _stored_value(row["reference_center"])
    uncertainty = float(row["reference_uncertainty"])
    if not math.isfinite(uncertainty) or uncertainty < 0.0:
        raise HiddenAuditContractError(
            f"reference uncertainty is invalid for {output_id}"
        )
    return center, uncertainty


def _power_items(
    preflight: CandidatePreflight,
    package: Mapping[str, Any],
    convergence: Mapping[str, Mapping[str, Any]],
) -> tuple[AuditItem, ...]:
    candidate = _candidate_orders(preflight)
    reference = _reference_orders(package)
    items = []
    for port, m, n in FIXED_ORDER_KEYS:
        identity = (port, m, n)
        candidate_row = candidate[identity]
        reference_row = reference[identity]
        output_id = f"order/{port}/m{m}/n{n}/total_power"
        reference_propagating = bool(reference_row["propagating"])
        candidate_propagating = bool(candidate_row["propagating"])
        if not reference_propagating:
            passed = (
                not candidate_propagating
                and reference_row["total_power"] is None
                and candidate_row["total_power"] is None
            )
            items.append(
                AuditItem(
                    category="order_power",
                    output_id=output_id,
                    reference_value=None,
                    candidate_value=candidate_row["total_power"],
                    actual_error=0.0 if passed else None,
                    tolerance=None,
                    reference_uncertainty=None,
                    applicable=False,
                    passed=passed,
                    reason=(
                        "matching_evanescent_identity"
                        if passed
                        else "propagation_identity_or_null_power_mismatch"
                    ),
                )
            )
            continue
        center_value, uncertainty = _reference_row(
            convergence,
            output_id,
            expected_kind="real",
        )
        center = float(center_value)
        candidate_power = candidate_row["total_power"]
        if candidate_power is None or not candidate_propagating:
            actual_error = None
            passed = False
        else:
            actual_error = abs(float(candidate_power) - center)
            passed = actual_error <= max(
                1.0e-9,
                5.0e-4 * abs(center),
                2.0 * uncertainty,
            )
        tolerance = max(
            1.0e-9,
            5.0e-4 * abs(center),
            2.0 * uncertainty,
        )
        items.append(
            AuditItem(
                category="order_power",
                output_id=output_id,
                reference_value=center,
                candidate_value=candidate_power,
                actual_error=actual_error,
                tolerance=tolerance,
                reference_uncertainty=uncertainty,
                applicable=True,
                passed=passed,
                reason=(
                    "within_hidden_power_tolerance"
                    if passed
                    else "hidden_power_tolerance_exceeded"
                ),
            )
        )
    return tuple(items)


def _amplitude_items(
    preflight: CandidatePreflight,
    package: Mapping[str, Any],
    convergence: Mapping[str, Mapping[str, Any]],
) -> tuple[AuditItem, ...]:
    candidate = _candidate_orders(preflight)
    reference = _reference_orders(package)
    items = []
    for port, m, n in FIXED_ORDER_KEYS:
        identity = (port, m, n)
        candidate_row = candidate[identity]
        reference_row = reference[identity]
        output_id = (
            f"order/{port}/m{m}/n{n}/co_polarized_amplitude"
        )
        center_value, uncertainty = _reference_row(
            convergence,
            output_id,
            expected_kind="complex",
        )
        center = complex(center_value)
        candidate_value = _complex(
            candidate_row["co_polarized_amplitude"]
        )
        actual_error = abs(candidate_value - center)
        tolerance = max(
            1.0e-6,
            1.0e-3 * abs(center),
            2.0 * uncertainty,
        )
        metadata_pass = (
            candidate_row["propagating"] == reference_row["propagating"]
        )
        passed = actual_error <= tolerance and metadata_pass
        items.append(
            AuditItem(
                category="order_amplitude",
                output_id=output_id,
                reference_value=_json_complex(center),
                candidate_value=_json_complex(candidate_value),
                actual_error=actual_error,
                tolerance=tolerance,
                reference_uncertainty=uncertainty,
                applicable=True,
                passed=passed,
                reason=(
                    "within_hidden_amplitude_tolerance"
                    if passed
                    else "hidden_amplitude_tolerance_or_metadata_failed"
                ),
            )
        )
    return tuple(items)


def _total_items(
    candidate_scalars: Mapping[str, float],
    convergence: Mapping[str, Mapping[str, Any]],
) -> tuple[AuditItem, ...]:
    items = []
    for name in FORMAL_TOTAL_NAMES:
        output_id = f"scalar/{name}"
        center_value, uncertainty = _reference_row(
            convergence,
            output_id,
            expected_kind="real",
        )
        center = float(center_value)
        candidate = candidate_scalars[name]
        actual_error = abs(candidate - center)
        tolerance = max(
            1.0e-6,
            2.0e-4 * abs(center),
            2.0 * uncertainty,
        )
        passed = actual_error <= tolerance
        items.append(
            AuditItem(
                category="total",
                output_id=output_id,
                reference_value=center,
                candidate_value=candidate,
                actual_error=actual_error,
                tolerance=tolerance,
                reference_uncertainty=uncertainty,
                applicable=True,
                passed=passed,
                reason=(
                    "within_hidden_total_tolerance"
                    if passed
                    else "hidden_total_tolerance_exceeded"
                ),
            )
        )
    return tuple(items)


def _field_items(
    candidate_scalars: Mapping[str, float],
    candidate_complex: Mapping[str, complex],
    convergence: Mapping[str, Mapping[str, Any]],
) -> tuple[AuditItem, ...]:
    items = []
    for category, base_tolerance in (
        ("interface_field", 0.01),
        ("volume_field", 0.015),
    ):
        rows = tuple(
            row
            for row in convergence.values()
            if row["category"] == category
            and (
                str(row["output_id"]).startswith("scalar/")
                or str(row["output_id"]).startswith("complex/")
            )
        )
        reference_values: list[complex] = []
        candidate_values: list[complex] = []
        uncertainties: list[float] = []
        missing = []
        for row in sorted(rows, key=lambda value: value["output_id"]):
            output_id = str(row["output_id"])
            center = complex(_stored_value(row["reference_center"]))
            if output_id.startswith("scalar/"):
                name = output_id.removeprefix("scalar/")
                if name not in candidate_scalars:
                    missing.append(output_id)
                    continue
                candidate_value = complex(candidate_scalars[name])
            else:
                name = output_id.removeprefix("complex/")
                if name not in candidate_complex:
                    missing.append(output_id)
                    continue
                candidate_value = candidate_complex[name]
            reference_values.append(center)
            candidate_values.append(candidate_value)
            uncertainties.append(float(row["reference_uncertainty"]))
        reference_norm = math.sqrt(
            sum(abs(value) ** 2 for value in reference_values)
        )
        error_norm = math.sqrt(
            sum(
                abs(candidate - reference) ** 2
                for candidate, reference in zip(
                    candidate_values,
                    reference_values,
                    strict=True,
                )
            )
        )
        uncertainty_norm = math.sqrt(
            sum(value * value for value in uncertainties)
        )
        if not rows or missing or reference_norm <= 0.0:
            relative_error = None
            relative_uncertainty = None
            tolerance = base_tolerance
            passed = False
            reason = (
                "missing_candidate_field_observations"
                if missing
                else "field_reference_norm_is_not_positive"
            )
        else:
            relative_error = error_norm / reference_norm
            relative_uncertainty = uncertainty_norm / reference_norm
            tolerance = max(
                base_tolerance,
                2.0 * relative_uncertainty,
            )
            passed = relative_error <= tolerance
            reason = (
                "within_hidden_field_relative_l2_tolerance"
                if passed
                else "hidden_field_relative_l2_tolerance_exceeded"
            )
        items.append(
            AuditItem(
                category="field",
                output_id=f"field/{category}/relative_l2",
                reference_value={
                    "l2_norm": reference_norm,
                    "observation_count": len(rows),
                },
                candidate_value={
                    "l2_error_norm": error_norm,
                    "missing_output_ids": missing,
                },
                actual_error=relative_error,
                tolerance=tolerance,
                reference_uncertainty=relative_uncertainty,
                applicable=True,
                passed=passed,
                reason=reason,
            )
        )
    return tuple(items)


def _full_propagating_spectrum_gate(
    preflight: CandidatePreflight,
    package: Mapping[str, Any],
    convergence: Mapping[str, Mapping[str, Any]],
) -> AuditGate:
    candidate_orders = _candidate_orders(preflight)
    reference_orders = _reference_orders(package)
    candidate_propagating = {
        identity: row
        for identity, row in candidate_orders.items()
        if row["propagating"] is True
    }
    reference_propagating = {
        identity: row
        for identity, row in reference_orders.items()
        if row["propagating"] is True
    }
    candidate_identities = tuple(
        sorted(candidate_propagating, key=_order_key)
    )
    reference_identities = tuple(
        sorted(reference_propagating, key=_order_key)
    )
    candidate_set = set(candidate_identities)
    reference_set = set(reference_identities)
    missing = tuple(sorted(reference_set - candidate_set, key=_order_key))
    unexpected = tuple(sorted(candidate_set - reference_set, key=_order_key))
    common = tuple(sorted(reference_set & candidate_set, key=_order_key))

    metadata_comparisons = []
    for identity in common:
        reference_metadata = _order_metadata_payload(
            reference_propagating[identity]
        )
        candidate_metadata = _order_metadata_payload(
            candidate_propagating[identity]
        )
        metadata_comparisons.append(
            {
                **_order_identity_payload(identity),
                "reference": reference_metadata,
                "candidate": candidate_metadata,
                "passed": candidate_metadata == reference_metadata,
            }
        )

    value_comparisons = []
    for identity in common:
        port, m, n = identity
        candidate_row = candidate_propagating[identity]
        for quantity in FULL_SPECTRUM_QUANTITIES:
            output_id = f"order/{port}/m{m}/n{n}/{quantity}"
            if quantity in {"total_power", "cross_polarized_power"}:
                center_value, uncertainty = _reference_row(
                    convergence,
                    output_id,
                    expected_kind="real",
                )
                center = float(center_value)
                candidate_value = float(candidate_row[quantity])
                actual_error = abs(candidate_value - center)
                tolerance = max(
                    1.0e-9,
                    5.0e-4 * abs(center),
                    2.0 * uncertainty,
                )
                reference_payload: Any = center
                candidate_payload: Any = candidate_value
            else:
                center_value, uncertainty = _reference_row(
                    convergence,
                    output_id,
                    expected_kind="complex",
                )
                center = complex(center_value)
                candidate_value = _complex(candidate_row[quantity])
                actual_error = abs(candidate_value - center)
                tolerance = max(
                    1.0e-6,
                    1.0e-3 * abs(center),
                    2.0 * uncertainty,
                )
                reference_payload = _json_complex(center)
                candidate_payload = _json_complex(candidate_value)
            value_comparisons.append(
                {
                    **_order_identity_payload(identity),
                    "quantity": quantity,
                    "reference_value": reference_payload,
                    "candidate_value": candidate_payload,
                    "actual_error": actual_error,
                    "tolerance": tolerance,
                    "reference_uncertainty": uncertainty,
                    "passed": actual_error <= tolerance,
                }
            )

    passed_value_count = sum(
        row["passed"] is True for row in value_comparisons
    )
    passed = all(
        (
            bool(reference_identities),
            not missing,
            not unexpected,
            all(row["passed"] is True for row in metadata_comparisons),
            passed_value_count == len(value_comparisons),
        )
    )
    actual = {
        "schema_version": FULL_SPECTRUM_GATE_SCHEMA,
        "status": "completed",
        "reference_orders": [
            _order_identity_payload(identity)
            for identity in reference_identities
        ],
        "candidate_orders": [
            _order_identity_payload(identity)
            for identity in candidate_identities
        ],
        "missing_candidate_orders": [
            _order_identity_payload(identity) for identity in missing
        ],
        "unexpected_candidate_orders": [
            _order_identity_payload(identity) for identity in unexpected
        ],
        "metadata_comparisons": metadata_comparisons,
        "value_comparisons": value_comparisons,
        "passed_value_count": passed_value_count,
        "total_value_count": len(value_comparisons),
    }
    return AuditGate(
        gate_id="full_propagating_spectrum_audit",
        actual=actual,
        limit={"required_status": "completed_and_passed"},
        passed=passed,
        reason=(
            "full_propagating_spectrum_completed_and_passed"
            if passed
            else "full_propagating_spectrum_failed_closed"
        ),
    )


def _hard_gates(
    preflight: CandidatePreflight,
    package: Mapping[str, Any],
    candidate_scalars: Mapping[str, float],
    convergence: Mapping[str, Mapping[str, Any]],
) -> tuple[AuditGate, ...]:
    residual = float(preflight.outputs["full_explicit_true_residual"])
    energy_error = abs(
        candidate_scalars["R_total"]
        + candidate_scalars["T_total"]
        + candidate_scalars["A_volume"]
        - 1.0
    )
    closure_error = abs(
        candidate_scalars["A_closure"]
        - candidate_scalars["A_volume"]
    )
    candidate_orders = _candidate_orders(preflight)
    reference_orders = _reference_orders(package)
    metadata_pass = True
    for identity in FIXED_ORDER_KEYS:
        candidate = candidate_orders[identity]
        reference = reference_orders[identity]
        metadata_pass = metadata_pass and all(
            (
                candidate["propagating"] == reference["propagating"],
                candidate["normalization_identity"]
                == reference["normalization_identity"],
                candidate["kz"] == reference["kz"],
                candidate["admittance"] == reference["admittance"],
            )
        )
    return (
        AuditGate(
            gate_id="full_explicit_true_residual",
            actual=residual,
            limit={"maximum": 1.0e-9},
            passed=residual <= 1.0e-9,
            reason="full_explicit_true_residual_must_not_exceed_1e-9",
        ),
        AuditGate(
            gate_id="energy_balance_R_plus_T_plus_Avolume",
            actual=energy_error,
            limit={"maximum_absolute_error": 1.0e-9},
            passed=energy_error <= 1.0e-9,
            reason="absolute_energy_balance_error_must_not_exceed_1e-9",
        ),
        AuditGate(
            gate_id="Aclosure_vs_Avolume",
            actual=closure_error,
            limit={"maximum_absolute_error": 1.0e-9},
            passed=closure_error <= 1.0e-9,
            reason="closure_volume_difference_must_not_exceed_1e-9",
        ),
        AuditGate(
            gate_id="Avolume_nonnegative",
            actual=candidate_scalars["A_volume"],
            limit={"minimum": 0.0},
            passed=candidate_scalars["A_volume"] >= 0.0,
            reason="volume_absorption_must_be_nonnegative",
        ),
        AuditGate(
            gate_id="fixed_order_physical_metadata",
            actual={"matching_order_count": 16 if metadata_pass else None},
            limit={"required_matching_order_count": 16},
            passed=metadata_pass,
            reason=(
                "propagation_kz_admittance_and_normalization_must_match"
            ),
        ),
        _full_propagating_spectrum_gate(
            preflight,
            package,
            convergence,
        ),
    )


def audit_candidate_against_reference(
    preflight: CandidatePreflight,
    package: Mapping[str, Any],
) -> HiddenAuditReport:
    """Recompute all final B3/G comparisons and make the result terminal."""

    convergence = _convergence_map(package)
    candidate_scalars, candidate_complex = _candidate_observations(preflight)
    items = (
        *_power_items(preflight, package, convergence),
        *_amplitude_items(preflight, package, convergence),
        *_total_items(candidate_scalars, convergence),
        *_field_items(candidate_scalars, candidate_complex, convergence),
    )
    gates = _hard_gates(
        preflight,
        package,
        candidate_scalars,
        convergence,
    )
    passed = all(item.passed for item in items) and all(
        gate.passed for gate in gates
    )
    report = HiddenAuditReport(
        status=(
            "REFERENCE_BLIND_HP_ACCURACY_PASS"
            if passed
            else "BLIND_STOP_FALSE_POSITIVE"
        ),
        passed=passed,
        terminal=True,
        candidate_frozen_payload_sha256=(
            preflight.receipt.frozen_payload_sha256
        ),
        candidate_output_sha256=preflight.receipt.output_sha256,
        reference_sealed_payload_sha256=(
            package["seal"]["sealed_payload_sha256"]
        ),
        reference_campaign_binding_sha256=(
            package["campaign_binding_sha256"]
        ),
        items=tuple(items),
        gates=gates,
    )
    counts = report.counts_payload()
    if (
        counts["fixed_order_inventory"] != 16
        or counts["power_total"] != 16
        or counts["amplitude_total"] != 16
    ):
        raise HiddenAuditContractError(
            "final audit did not produce the full 16/16 order inventory"
        )
    return report


__all__ = ["audit_candidate_against_reference"]
