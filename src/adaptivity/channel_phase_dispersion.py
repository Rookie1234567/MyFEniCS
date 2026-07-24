"""Pure diagnostics for diffraction-channel phase dispersion.

The helpers in this module do not solve a PDE and do not alter an acceptance
gate.  They decompose a complex-amplitude error into the radial and tangential
directions defined by a frozen reference amplitude, then fit the diagnostic
model

``arg(a_candidate / a_reference) ~= Re(k_z) * delta_z_eff``

independently on the top and bottom ports.  The fitted ``delta_z_eff`` is an
effective phase-delay diagnostic, not a geometric correction or a license to
shift a reference plane.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np


CHANNEL_IDENTITY_FIELDS = ("side", "m", "n", "polarization")
PORT_SIDES = ("bottom", "top")
DEFAULT_PHASE_BEARING_FRACTION = 0.8
MAXIMUM_UNAMBIGUOUS_PRINCIPAL_PHASE_RADIANS = math.pi / 2.0


def _finite_float(value: Any, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_float(value: Any, *, label: str) -> float:
    result = _finite_float(value, label=label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _nonnegative_float(value: Any, *, label: str) -> float:
    result = _finite_float(value, label=label)
    if result < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _complex_value(value: Any, *, label: str) -> complex:
    if isinstance(value, complex):
        result = value
    elif (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 2
    ):
        result = complex(
            _finite_float(value[0], label=f"{label}.real"),
            _finite_float(value[1], label=f"{label}.imag"),
        )
    else:
        raise ValueError(f"{label} must be complex or a [real, imag] pair")
    if not (math.isfinite(result.real) and math.isfinite(result.imag)):
        raise ValueError(f"{label} must be finite")
    return result


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def channel_identity(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    """Return one canonical diffraction-channel identity."""

    side = str(row.get("side"))
    if side not in PORT_SIDES:
        raise ValueError(f"unsupported channel side: {side}")
    polarization = str(row.get("polarization"))
    if polarization not in {"s", "p"}:
        raise ValueError(f"unsupported channel polarization: {polarization}")
    return (
        side,
        int(row.get("m")),
        int(row.get("n")),
        polarization,
    )


def radial_tangential_complex_error(
    reference_amplitude: complex,
    candidate_amplitude: complex,
) -> dict[str, Any]:
    """Decompose ``candidate-reference`` in the reference phase frame."""

    reference = _complex_value(
        reference_amplitude,
        label="reference_amplitude",
    )
    candidate = _complex_value(
        candidate_amplitude,
        label="candidate_amplitude",
    )
    reference_magnitude = abs(reference)
    if reference_magnitude == 0.0:
        raise ValueError("reference_amplitude must be nonzero")
    error = candidate - reference
    phase_frame_error = error * reference.conjugate() / reference_magnitude
    error_magnitude = abs(error)
    radial = float(phase_frame_error.real)
    tangential = float(phase_frame_error.imag)
    tangential_fraction = (
        0.0 if error_magnitude == 0.0 else abs(tangential) / error_magnitude
    )
    radial_fraction = (
        0.0 if error_magnitude == 0.0 else abs(radial) / error_magnitude
    )
    phase_error = float(np.angle(candidate / reference))
    return {
        "reference_amplitude": _complex_pair(reference),
        "candidate_amplitude": _complex_pair(candidate),
        "complex_error": _complex_pair(error),
        "complex_error_magnitude": float(error_magnitude),
        "radial_error": radial,
        "tangential_error": tangential,
        "radial_absolute_fraction": float(radial_fraction),
        "tangential_absolute_fraction": float(tangential_fraction),
        "radial_tangential_squared_fraction_closure": float(
            radial_fraction**2 + tangential_fraction**2
        ),
        "relative_magnitude_error": float(
            (abs(candidate) - reference_magnitude) / reference_magnitude
        ),
        "principal_phase_error_radians": phase_error,
        "principal_phase_error_degrees": math.degrees(phase_error),
    }


def _phase_fit(
    channel_rows: Sequence[Mapping[str, Any]],
    *,
    weight_policy: str,
) -> dict[str, Any]:
    if not channel_rows:
        raise ValueError("phase fit requires at least one channel")
    if weight_policy not in {"reference_power", "uniform"}:
        raise ValueError(f"unsupported phase-fit weight policy: {weight_policy}")

    labels = [str(row["label"]) for row in channel_rows]
    if len(labels) != len(set(labels)):
        raise ValueError("phase-fit channel labels must be unique")
    kz = np.asarray(
        [
            _finite_float(row["kz_real_per_nm"], label=f"{label}.kz_real")
            for label, row in zip(labels, channel_rows, strict=True)
        ],
        dtype=np.float64,
    )
    phases = np.asarray(
        [
            _finite_float(
                row["principal_phase_error_radians"],
                label=f"{label}.phase_error",
            )
            for label, row in zip(labels, channel_rows, strict=True)
        ],
        dtype=np.float64,
    )
    maximum_phase = float(np.max(np.abs(phases)))
    if maximum_phase >= MAXIMUM_UNAMBIGUOUS_PRINCIPAL_PHASE_RADIANS:
        raise ValueError(
            "principal phase exceeds the unambiguous linear-fit range"
        )
    if weight_policy == "reference_power":
        raw_weights = np.asarray(
            [
                _positive_float(
                    row["reference_power"],
                    label=f"{label}.reference_power",
                )
                for label, row in zip(labels, channel_rows, strict=True)
            ],
            dtype=np.float64,
        )
    else:
        raw_weights = np.ones(len(channel_rows), dtype=np.float64)
    weight_sum = float(np.sum(raw_weights))
    weights = raw_weights / weight_sum
    denominator = float(np.sum(weights * np.square(kz)))
    if denominator <= 0.0 or not math.isfinite(denominator):
        raise ValueError("phase-fit weighted kz denominator must be positive")
    numerator = float(np.sum(weights * kz * phases))
    delta_z_eff = numerator / denominator
    predicted = kz * delta_z_eff
    residual = phases - predicted
    weighted_residual_square = float(np.sum(weights * np.square(residual)))
    weighted_raw_square = float(np.sum(weights * np.square(phases)))
    residual_rms = math.sqrt(weighted_residual_square)
    raw_rms = math.sqrt(weighted_raw_square)
    residual_to_raw = (
        0.0
        if raw_rms == 0.0 and residual_rms == 0.0
        else None
        if raw_rms == 0.0
        else residual_rms / raw_rms
    )
    explained = (
        1.0
        if weighted_raw_square == 0.0 and weighted_residual_square == 0.0
        else None
        if weighted_raw_square == 0.0
        else 1.0 - weighted_residual_square / weighted_raw_square
    )
    return {
        "model": (
            "arg(a_candidate/a_reference) ~= "
            "Re(kz_per_nm) * delta_z_eff_nm"
        ),
        "fit_intercept_radians": 0.0,
        "weight_policy": weight_policy,
        "weight_sum_before_normalization": weight_sum,
        "delta_z_eff_nm": float(delta_z_eff),
        "weighted_kz_phase_numerator": numerator,
        "weighted_kz_squared_denominator": denominator,
        "weighted_raw_phase_rms_radians": raw_rms,
        "weighted_residual_rms_radians": residual_rms,
        "weighted_residual_to_raw_phase_rms": residual_to_raw,
        "through_origin_explained_square_fraction": explained,
        "maximum_absolute_principal_phase_radians": maximum_phase,
        "principal_phase_branch_qualified": True,
        "channels": [
            {
                "label": label,
                "kz_real_per_nm": float(kz_value),
                "principal_phase_error_radians": float(phase),
                "principal_phase_error_degrees": math.degrees(float(phase)),
                "raw_weight": float(raw_weight),
                "normalized_weight": float(weight),
                "fitted_phase_radians": float(prediction),
                "phase_fit_residual_radians": float(error),
            }
            for (
                label,
                kz_value,
                phase,
                raw_weight,
                weight,
                prediction,
                error,
            ) in zip(
                labels,
                kz,
                phases,
                raw_weights,
                weights,
                predicted,
                residual,
                strict=True,
            )
        ],
        "interpretation": (
            "effective phase-delay diagnostic only; not a physical "
            "reference-plane displacement"
        ),
    }


def _indexed_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    indexed: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for row in rows:
        identity = channel_identity(row)
        if identity in indexed:
            raise ValueError(f"{label} contains duplicate channel {identity}")
        indexed[identity] = row
    if not indexed:
        raise ValueError(f"{label} contains no channels")
    return indexed


def analyze_candidate_phase_dispersion(
    *,
    candidate_id: str,
    reference_channels: Sequence[Mapping[str, Any]],
    candidate_channels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Analyze one candidate against an unchanged frozen channel contract."""

    reference = _indexed_rows(reference_channels, label="reference")
    candidate = _indexed_rows(
        candidate_channels,
        label=f"candidate {candidate_id}",
    )
    if set(reference) != set(candidate):
        missing = sorted(set(reference) - set(candidate))
        extra = sorted(set(candidate) - set(reference))
        raise ValueError(
            f"{candidate_id} channel identity mismatch: "
            f"missing={missing}, extra={extra}"
        )

    channel_rows: list[dict[str, Any]] = []
    for identity, reference_row in reference.items():
        candidate_row = candidate[identity]
        label = str(reference_row["label"])
        reference_amplitude = _complex_value(
            reference_row["reference_amplitude"],
            label=f"{label}.reference_amplitude",
        )
        candidate_amplitude = _complex_value(
            candidate_row["candidate_amplitude"],
            label=f"{candidate_id}.{label}.candidate_amplitude",
        )
        reference_power = _positive_float(
            reference_row["reference_power"],
            label=f"{label}.reference_power",
        )
        candidate_power = _nonnegative_float(
            candidate_row["candidate_power"],
            label=f"{candidate_id}.{label}.candidate_power",
        )
        power_tolerance = _positive_float(
            reference_row["power_tolerance"],
            label=f"{label}.power_tolerance",
        )
        amplitude_tolerance = _positive_float(
            reference_row["amplitude_tolerance"],
            label=f"{label}.amplitude_tolerance",
        )
        decomposition = radial_tangential_complex_error(
            reference_amplitude,
            candidate_amplitude,
        )
        power_error = candidate_power - reference_power
        normalized_power_error = power_error / power_tolerance
        normalized_amplitude_error = (
            decomposition["complex_error_magnitude"] / amplitude_tolerance
        )
        power_pass = abs(normalized_power_error) <= 1.0
        amplitude_pass = normalized_amplitude_error <= 1.0
        kz = _complex_value(
            reference_row["kz"],
            label=f"{label}.kz",
        )
        row = {
            "label": label,
            "side": identity[0],
            "m": identity[1],
            "n": identity[2],
            "polarization": identity[3],
            "kz_per_nm": _complex_pair(kz),
            "kz_real_per_nm": float(kz.real),
            "reference_power": reference_power,
            "candidate_power": candidate_power,
            "power_error": float(power_error),
            "unchanged_power_tolerance": power_tolerance,
            "normalized_power_error": float(normalized_power_error),
            "power_pass": power_pass,
            "unchanged_complex_amplitude_tolerance": amplitude_tolerance,
            "normalized_complex_amplitude_error": float(
                normalized_amplitude_error
            ),
            "complex_amplitude_pass": amplitude_pass,
            "failed_any_unchanged_gate": not (power_pass and amplitude_pass),
            **decomposition,
        }
        channel_rows.append(row)

    channel_rows.sort(
        key=lambda row: (
            PORT_SIDES.index(str(row["side"])),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
        )
    )
    fits_by_side: dict[str, Any] = {}
    for side in PORT_SIDES:
        rows = [row for row in channel_rows if row["side"] == side]
        if not rows:
            raise ValueError(f"{candidate_id} has no {side} channels")
        fits_by_side[side] = {
            "reference_power_weighted": _phase_fit(
                rows,
                weight_policy="reference_power",
            ),
            "uniform_weighted": _phase_fit(
                rows,
                weight_policy="uniform",
            ),
        }
    failures = [
        row for row in channel_rows if row["failed_any_unchanged_gate"]
    ]
    return {
        "candidate_id": candidate_id,
        "channel_count": len(channel_rows),
        "power_pass_count_recomputed": sum(
            bool(row["power_pass"]) for row in channel_rows
        ),
        "complex_amplitude_pass_count_recomputed": sum(
            bool(row["complex_amplitude_pass"]) for row in channel_rows
        ),
        "all_power_gates_pass": all(
            bool(row["power_pass"]) for row in channel_rows
        ),
        "all_complex_amplitude_gates_pass": all(
            bool(row["complex_amplitude_pass"]) for row in channel_rows
        ),
        "phase_fit_by_side": fits_by_side,
        "channels": channel_rows,
        "failed_channels": failures,
        "diagnostic_only": True,
        "formal_gate_unchanged": True,
        "thresholds_relaxed": False,
    }


def build_phase_dispersion_analysis(
    *,
    reference_channels: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Sequence[Mapping[str, Any]]],
    priority_candidate_id: str,
    phase_bearing_fraction: float = DEFAULT_PHASE_BEARING_FRACTION,
) -> dict[str, Any]:
    """Analyze all candidates and derive a fail-closed research priority."""

    threshold = _finite_float(
        phase_bearing_fraction,
        label="phase_bearing_fraction",
    )
    if not 0.0 < threshold <= 1.0:
        raise ValueError("phase_bearing_fraction must lie in (0, 1]")
    if priority_candidate_id not in candidates:
        raise ValueError("priority candidate is absent")
    analyses = {
        candidate_id: analyze_candidate_phase_dispersion(
            candidate_id=candidate_id,
            reference_channels=reference_channels,
            candidate_channels=rows,
        )
        for candidate_id, rows in candidates.items()
    }
    priority = analyses[priority_candidate_id]
    remaining_failures = priority["failed_channels"]
    phase_bearing = [
        row
        for row in remaining_failures
        if row["tangential_absolute_fraction"] >= threshold
    ]
    priority_supported = bool(
        len(remaining_failures) >= 2
        and len(phase_bearing) == len(remaining_failures)
    )
    return {
        "schema_version": "task035b.channel-phase-dispersion-analysis.v1",
        "candidate_order": list(candidates),
        "candidates": analyses,
        "research_priority": {
            "status": (
                "prioritize_phase_bearing_periodic_trace_orbit_diagnostic"
                if priority_supported
                else "insufficient_uniform_phase_bearing_failure_signal"
            ),
            "supported": priority_supported,
            "priority_candidate_id": priority_candidate_id,
            "phase_bearing_fraction_threshold": threshold,
            "remaining_failed_channel_count": len(remaining_failures),
            "phase_bearing_failed_channel_count": len(phase_bearing),
            "remaining_failed_channel_labels": [
                row["label"] for row in remaining_failures
            ],
            "phase_bearing_failed_channel_labels": [
                row["label"] for row in phase_bearing
            ],
            "next_diagnostic_target": (
                "phase-bearing periodic p6 trace orbits under physical "
                "Riesz/DWR and exact-sequence closure"
            ),
            "does_not_select_trace_modes": True,
            "does_not_authorize_candidate_matrix": True,
            "does_not_authorize_gate_relaxation": True,
        },
        "interpretation_guards": {
            "delta_z_eff_is_not_a_geometry_or_port_plane_correction": True,
            "phase_fit_does_not_prove_causality": True,
            "radial_tangential_split_does_not_replace_dwr": True,
            "formal_12_power_gate_unchanged": True,
            "formal_12_complex_amplitude_gate_unchanged": True,
            "thresholds_relaxed": False,
            "diagnostic_only": True,
        },
    }
