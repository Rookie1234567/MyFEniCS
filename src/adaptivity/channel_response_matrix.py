"""Pure postprocessing for significant-channel response directions.

The routines in this module deliberately operate on already-qualified JSON
payloads.  They do not import DOLFINx, PETSc, MPI, or any project solver.
Signed power errors and signed complex-amplitude errors are normalized by the
frozen per-channel Review-V1 tolerances before response directions are formed.
"""

from __future__ import annotations

from itertools import combinations
import math
from typing import Any, Mapping, Sequence

import numpy as np


ChannelKey = tuple[str, int, int, str]


def channel_key(payload: Mapping[str, Any]) -> ChannelKey:
    """Return the canonical significant-channel identity."""

    try:
        key = (
            str(payload["side"]),
            int(payload["m"]),
            int(payload["n"]),
            str(payload["polarization"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("incomplete significant-channel identity") from error
    if key[0] not in {"top", "bottom"}:
        raise ValueError(f"invalid channel side {key[0]!r}")
    if not key[3]:
        raise ValueError("empty channel polarization")
    return key


def channel_label(key: ChannelKey) -> str:
    """Return an unambiguous compact channel label."""

    prefix = "R" if key[0] == "top" else "T"
    return f"{prefix}({key[1]},{key[2]})_{key[3]}"


def _finite_float(value: Any, *, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _positive_float(value: Any, *, label: str) -> float:
    result = _finite_float(value, label=label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _complex_pair(value: Any, *, label: str) -> complex:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError(f"{label} must be a [real, imag] pair")
    return complex(
        _finite_float(value[0], label=f"{label}.real"),
        _finite_float(value[1], label=f"{label}.imag"),
    )


def reference_channel_contract(
    reference: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate and return the frozen ordered 12-channel contract."""

    if (
        reference.get("schema_version")
        != "task035b.significant-channel-reference.v1"
        or reference.get("status")
        != "significant_channel_reference_v1_frozen"
        or reference.get("pass") is not True
        or reference.get("mechanical_validation_pass") is not True
        or reference.get("ordinary_default_changed") is not False
    ):
        raise ValueError("significant-channel reference v1 is not qualified")
    channels = reference.get("channels")
    if not isinstance(channels, list) or len(channels) != 12:
        raise ValueError("reference must contain exactly 12 channels")

    result: list[dict[str, Any]] = []
    seen: set[ChannelKey] = set()
    for index, entry in enumerate(channels):
        if not isinstance(entry, Mapping):
            raise ValueError(f"reference channel {index} is not an object")
        identity = entry.get("channel")
        center = entry.get("reference_center")
        gate = entry.get("unchanged_v0_acceptance_gate")
        if not isinstance(identity, Mapping):
            raise ValueError(f"reference channel {index} lacks identity")
        if not isinstance(center, Mapping) or not isinstance(gate, Mapping):
            raise ValueError(f"reference channel {index} lacks center or Gate")
        key = channel_key(identity)
        if key in seen:
            raise ValueError(f"duplicate reference channel {channel_label(key)}")
        seen.add(key)
        expected_label = channel_label(key)
        if identity.get("label") != expected_label:
            raise ValueError(
                f"reference channel label mismatch for {expected_label}"
            )
        if gate.get("uses_numerical_convergence_band") is not False:
            raise ValueError(
                f"{expected_label} changes the unchanged-v0 Gate"
            )
        if gate.get("uses_h15_or_fixed_diagnostics") is not False:
            raise ValueError(f"{expected_label} lets diagnostics change Gate")
        result.append(
            {
                "key": key,
                "label": expected_label,
                "reference_power": _finite_float(
                    center.get("power"),
                    label=f"{expected_label}.reference_power",
                ),
                "reference_amplitude": _complex_pair(
                    center.get("complex_amplitude"),
                    label=f"{expected_label}.reference_amplitude",
                ),
                "power_tolerance": _positive_float(
                    gate.get("power_absolute_tolerance"),
                    label=f"{expected_label}.power_tolerance",
                ),
                "complex_amplitude_tolerance": _positive_float(
                    gate.get("complex_amplitude_absolute_tolerance"),
                    label=f"{expected_label}.amplitude_tolerance",
                ),
            }
        )
    return result


def normalized_error_vector(
    contract: Sequence[Mapping[str, Any]],
    comparison_channels: Sequence[Mapping[str, Any]],
    *,
    lane: str,
) -> dict[str, Any]:
    """Build signed normalized power and complex error vectors for one lane."""

    if not isinstance(comparison_channels, Sequence):
        raise ValueError(f"{lane} channels must be a sequence")
    by_key: dict[ChannelKey, Mapping[str, Any]] = {}
    for entry in comparison_channels:
        if not isinstance(entry, Mapping):
            raise ValueError(f"{lane} contains a non-object channel")
        key = channel_key(entry)
        if key in by_key:
            raise ValueError(f"{lane} duplicates {channel_label(key)}")
        by_key[key] = entry

    expected = {entry["key"] for entry in contract}
    available = set(by_key)
    missing = expected - available
    if missing:
        labels = ", ".join(sorted(channel_label(key) for key in missing))
        raise ValueError(f"{lane} lacks frozen channels: {labels}")

    power: list[float] = []
    amplitude: list[complex] = []
    channel_rows: list[dict[str, Any]] = []
    for reference_entry in contract:
        key = reference_entry["key"]
        label = reference_entry["label"]
        observed = by_key[key]
        if observed.get("analytic_identity_pass") is not True:
            raise ValueError(f"{lane} analytic identity fails for {label}")
        candidate_power = _finite_float(
            observed.get("candidate_power_ratio"),
            label=f"{lane}.{label}.candidate_power",
        )
        candidate_amplitude = _complex_pair(
            observed.get("candidate_outgoing_amplitude_at_boundary"),
            label=f"{lane}.{label}.candidate_amplitude",
        )
        power_error = (
            candidate_power - reference_entry["reference_power"]
        ) / reference_entry["power_tolerance"]
        amplitude_error = (
            candidate_amplitude - reference_entry["reference_amplitude"]
        ) / reference_entry["complex_amplitude_tolerance"]
        if not (
            math.isfinite(power_error)
            and math.isfinite(amplitude_error.real)
            and math.isfinite(amplitude_error.imag)
        ):
            raise ValueError(f"{lane} normalized error is nonfinite for {label}")
        power.append(float(power_error))
        amplitude.append(complex(amplitude_error))
        channel_rows.append(
            {
                "label": label,
                "key": list(key),
                "candidate_power": candidate_power,
                "candidate_amplitude": [
                    candidate_amplitude.real,
                    candidate_amplitude.imag,
                ],
                "normalized_power_error_signed": float(power_error),
                "normalized_complex_error_signed": [
                    amplitude_error.real,
                    amplitude_error.imag,
                ],
                "normalized_complex_error_magnitude": abs(amplitude_error),
                "power_pass_recomputed": abs(power_error) <= 1.0,
                "complex_amplitude_pass_recomputed": (
                    abs(amplitude_error) <= 1.0
                ),
            }
        )

    power_array = np.asarray(power, dtype=np.float64)
    amplitude_array = np.asarray(amplitude, dtype=np.complex128)
    _require_finite_array(power_array, label=f"{lane}.power")
    _require_finite_array(amplitude_array, label=f"{lane}.amplitude")
    return {
        "lane": lane,
        "power": power_array,
        "amplitude": amplitude_array,
        "channels": channel_rows,
    }


def _require_finite_array(array: np.ndarray, *, label: str) -> None:
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} contains nonfinite values")


def _norm(array: np.ndarray) -> float:
    value = float(np.linalg.norm(array))
    if not math.isfinite(value):
        raise ValueError("computed norm is nonfinite")
    return value


def _cosine(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    left_norm = _norm(left)
    right_norm = _norm(right)
    denominator = left_norm * right_norm
    if denominator == 0.0:
        return {"defined": False, "value": None}
    value = float(np.real(np.vdot(left, right)) / denominator)
    if not math.isfinite(value):
        raise ValueError("computed cosine is nonfinite")
    return {"defined": True, "value": max(-1.0, min(1.0, value))}


def _pearson(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    left_centered = left - np.mean(left)
    right_centered = right - np.mean(right)
    return _cosine(left_centered, right_centered)


def _complex_coherence(
    left: np.ndarray,
    right: np.ndarray,
) -> dict[str, Any]:
    denominator = _norm(left) * _norm(right)
    if denominator == 0.0:
        return {
            "defined": False,
            "real": None,
            "imag": None,
            "magnitude": None,
            "phase_radians": None,
        }
    value = complex(np.vdot(left, right) / denominator)
    if not (math.isfinite(value.real) and math.isfinite(value.imag)):
        raise ValueError("computed complex coherence is nonfinite")
    return {
        "defined": True,
        "real": value.real,
        "imag": value.imag,
        "magnitude": abs(value),
        "phase_radians": math.atan2(value.imag, value.real),
    }


def _pairwise_directionality(
    lane_order: Sequence[str],
    matrix: np.ndarray,
    *,
    complex_matrix: bool,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for left_index, right_index in combinations(range(len(lane_order)), 2):
        left = matrix[:, left_index]
        right = matrix[:, right_index]
        row = {
            "lane_a": lane_order[left_index],
            "lane_b": lane_order[right_index],
            "cosine": _cosine(left, right),
            "pearson_correlation": _pearson(left, right),
        }
        if complex_matrix:
            row["complex_hermitian_coherence"] = _complex_coherence(
                left,
                right,
            )
        result.append(row)
    return result


def _svd_payload(
    matrix: np.ndarray,
    lane_order: Sequence[str],
) -> dict[str, Any]:
    left, singular, right_h = np.linalg.svd(matrix, full_matrices=False)
    _require_finite_array(left, label="svd.left")
    _require_finite_array(singular, label="svd.singular")
    _require_finite_array(right_h, label="svd.right")
    squared = np.square(singular)
    total = float(np.sum(squared))
    energy = (
        [float(value / total) for value in squared]
        if total > 0.0
        else [0.0 for value in squared]
    )
    tolerance = (
        max(matrix.shape) * np.finfo(float).eps * float(singular[0])
        if singular.size and singular[0] > 0.0
        else 0.0
    )

    right_vectors: list[list[Any]] = []
    for vector in right_h:
        if np.iscomplexobj(vector):
            right_vectors.append(
                [[complex(value).real, complex(value).imag] for value in vector]
            )
        else:
            right_vectors.append([float(value) for value in vector])
    return {
        "matrix_shape": list(matrix.shape),
        "lane_order": list(lane_order),
        "singular_values": [float(value) for value in singular],
        "squared_energy_fractions": energy,
        "numerical_rank": int(np.count_nonzero(singular > tolerance)),
        "rank_tolerance": float(tolerance),
        "right_singular_vectors_by_lane": right_vectors,
        "left_singular_vector_shape": list(left.shape),
    }


def _pass_counts(
    power: np.ndarray,
    amplitude: np.ndarray,
) -> tuple[int, int]:
    return (
        int(np.count_nonzero(np.abs(power) <= 1.0)),
        int(np.count_nonzero(np.abs(amplitude) <= 1.0)),
    )


def _lane_classification(
    *,
    power_reduction: float,
    amplitude_reduction: float,
    seed_passes: tuple[int, int],
    lane_passes: tuple[int, int],
    response_relative_size: float,
) -> tuple[str, str]:
    no_count_regression = (
        lane_passes[0] >= seed_passes[0]
        and lane_passes[1] >= seed_passes[1]
    )
    if response_relative_size <= 1.0e-6:
        return (
            "not_worth_repeat",
            "response is numerically negligible relative to the seed error",
        )
    if (
        no_count_regression
        and abs(power_reduction) < 0.01
        and abs(amplitude_reduction) < 0.01
    ):
        return (
            "not_worth_repeat",
            "both normalized error changes remain below one percent and Gate "
            "counts are unchanged",
        )
    if (
        no_count_regression
        and power_reduction >= 0.05
        and amplitude_reduction >= 0.05
    ):
        return (
            "worth_followup",
            "both normalized error norms improve materially without Gate-count "
            "regression",
        )
    if (
        no_count_regression
        and max(power_reduction, amplitude_reduction) >= 0.05
        and min(power_reduction, amplitude_reduction) >= -0.01
    ):
        return (
            "worth_targeted_discriminator_only",
            "one response family improves materially and the other does not "
            "materially regress",
        )
    return (
        "not_supported_as_standalone_lane",
        "normalized errors or recomputed Gate counts regress",
    )


def response_matrix_evidence(
    *,
    contract: Sequence[Mapping[str, Any]],
    seed: Mapping[str, Any],
    lanes: Sequence[Mapping[str, Any]],
    compatible_pairs: set[frozenset[str]],
) -> dict[str, Any]:
    """Build response matrices, direction correlations, SVDs, and decisions."""

    if len(contract) != 12:
        raise ValueError("response matrix requires exactly 12 channels")
    lane_names = [str(lane["lane"]) for lane in lanes]
    if len(lane_names) != len(set(lane_names)):
        raise ValueError("response lane names must be unique")
    if not lane_names:
        raise ValueError("at least one response lane is required")

    seed_power = np.asarray(seed["power"], dtype=np.float64)
    seed_amplitude = np.asarray(seed["amplitude"], dtype=np.complex128)
    if seed_power.shape != (12,) or seed_amplitude.shape != (12,):
        raise ValueError("seed vectors must each have length 12")
    _require_finite_array(seed_power, label="seed.power")
    _require_finite_array(seed_amplitude, label="seed.amplitude")

    lane_power = np.column_stack(
        [np.asarray(lane["power"], dtype=np.float64) for lane in lanes]
    )
    lane_amplitude = np.column_stack(
        [np.asarray(lane["amplitude"], dtype=np.complex128) for lane in lanes]
    )
    if lane_power.shape != (12, len(lanes)):
        raise ValueError("power lane matrix has an invalid shape")
    if lane_amplitude.shape != (12, len(lanes)):
        raise ValueError("amplitude lane matrix has an invalid shape")
    _require_finite_array(lane_power, label="lane.power")
    _require_finite_array(lane_amplitude, label="lane.amplitude")

    power_response = lane_power - seed_power[:, None]
    amplitude_response = lane_amplitude - seed_amplitude[:, None]
    seed_power_norm = _norm(seed_power)
    seed_amplitude_norm = _norm(seed_amplitude)
    seed_combined_norm = math.hypot(seed_power_norm, seed_amplitude_norm)
    if seed_power_norm == 0.0 or seed_amplitude_norm == 0.0:
        raise ValueError("seed error norms must be positive")
    seed_passes = _pass_counts(seed_power, seed_amplitude)

    lane_metrics: list[dict[str, Any]] = []
    for index, lane_name in enumerate(lane_names):
        power = lane_power[:, index]
        amplitude = lane_amplitude[:, index]
        power_norm = _norm(power)
        amplitude_norm = _norm(amplitude)
        combined_norm = math.hypot(power_norm, amplitude_norm)
        passes = _pass_counts(power, amplitude)
        power_reduction = 1.0 - power_norm / seed_power_norm
        amplitude_reduction = 1.0 - amplitude_norm / seed_amplitude_norm
        response_relative_size = math.hypot(
            _norm(power_response[:, index]),
            _norm(amplitude_response[:, index]),
        ) / seed_combined_norm
        classification, reason = _lane_classification(
            power_reduction=power_reduction,
            amplitude_reduction=amplitude_reduction,
            seed_passes=seed_passes,
            lane_passes=passes,
            response_relative_size=response_relative_size,
        )
        lane_metrics.append(
            {
                "lane": lane_name,
                "normalized_power_l2": power_norm,
                "normalized_complex_amplitude_l2": amplitude_norm,
                "normalized_joint_l2": combined_norm,
                "power_relative_reduction_from_seed": power_reduction,
                "complex_amplitude_relative_reduction_from_seed": (
                    amplitude_reduction
                ),
                "joint_relative_reduction_from_seed": (
                    1.0 - combined_norm / seed_combined_norm
                ),
                "response_relative_size_to_seed_joint_error": (
                    response_relative_size
                ),
                "power_pass_count_recomputed": passes[0],
                "complex_amplitude_pass_count_recomputed": passes[1],
                "power_response_alignment_to_ideal_correction": _cosine(
                    power_response[:, index],
                    -seed_power,
                ),
                "complex_response_alignment_to_ideal_correction": _cosine(
                    amplitude_response[:, index],
                    -seed_amplitude,
                ),
                "classification": classification,
                "classification_reason": reason,
            }
        )

    pairwise_combinations: list[dict[str, Any]] = []
    metrics_by_name = {
        entry["lane"]: entry
        for entry in lane_metrics
    }
    for left_index, right_index in combinations(range(len(lane_names)), 2):
        left_name = lane_names[left_index]
        right_name = lane_names[right_index]
        compatible = frozenset({left_name, right_name}) in compatible_pairs
        row: dict[str, Any] = {
            "lane_a": left_name,
            "lane_b": right_name,
            "directly_composable": compatible,
            "semantics": (
                "unit-response linearized projection; not a solved candidate"
            ),
        }
        if not compatible:
            row.update(
                {
                    "classification": "not_directly_composable",
                    "reason": (
                        "the authorities are alternative topologies or one is "
                        "a mechanism-only control"
                    ),
                }
            )
            pairwise_combinations.append(row)
            continue
        predicted_power = (
            seed_power
            + power_response[:, left_index]
            + power_response[:, right_index]
        )
        predicted_amplitude = (
            seed_amplitude
            + amplitude_response[:, left_index]
            + amplitude_response[:, right_index]
        )
        predicted_power_norm = _norm(predicted_power)
        predicted_amplitude_norm = _norm(predicted_amplitude)
        predicted_joint_norm = math.hypot(
            predicted_power_norm,
            predicted_amplitude_norm,
        )
        predicted_passes = _pass_counts(
            predicted_power,
            predicted_amplitude,
        )
        best_single_joint = min(
            metrics_by_name[left_name]["normalized_joint_l2"],
            metrics_by_name[right_name]["normalized_joint_l2"],
        )
        best_single_power_pass = max(
            metrics_by_name[left_name]["power_pass_count_recomputed"],
            metrics_by_name[right_name]["power_pass_count_recomputed"],
        )
        best_single_amplitude_pass = max(
            metrics_by_name[left_name][
                "complex_amplitude_pass_count_recomputed"
            ],
            metrics_by_name[right_name][
                "complex_amplitude_pass_count_recomputed"
            ],
        )
        worth = (
            predicted_joint_norm <= 0.95 * best_single_joint
            and predicted_passes[0] >= best_single_power_pass
            and predicted_passes[1] >= best_single_amplitude_pass
        )
        row.update(
            {
                "predicted_normalized_power_l2": predicted_power_norm,
                "predicted_normalized_complex_amplitude_l2": (
                    predicted_amplitude_norm
                ),
                "predicted_normalized_joint_l2": predicted_joint_norm,
                "predicted_power_pass_count": predicted_passes[0],
                "predicted_complex_amplitude_pass_count": predicted_passes[1],
                "relative_joint_improvement_over_best_single": (
                    1.0 - predicted_joint_norm / best_single_joint
                    if best_single_joint > 0.0
                    else 0.0
                ),
                "classification": (
                    "worth_one_targeted_discriminator"
                    if worth
                    else "not_supported_by_linearized_response"
                ),
                "reason": (
                    "projected joint norm improves at least 5 percent without "
                    "recomputed Gate-count regression"
                    if worth
                    else "projection does not improve the best single lane by "
                    "5 percent with nonregressing Gate counts"
                ),
            }
        )
        pairwise_combinations.append(row)

    all_power = np.column_stack((seed_power, lane_power))
    all_amplitude = np.column_stack((seed_amplitude, lane_amplitude))
    full_lane_order = ["fixed_h15_seed", *lane_names]
    return {
        "normalization": {
            "power": (
                "(candidate power - frozen reference power) / unchanged-v0 "
                "per-channel power tolerance"
            ),
            "complex_amplitude": (
                "(candidate complex amplitude - frozen reference complex "
                "amplitude) / unchanged-v0 per-channel complex tolerance"
            ),
            "response": "lane normalized signed error minus fixed-h15 seed",
            "pass_recomputation": (
                "abs(power error)<=1 and abs(complex error)<=1"
            ),
        },
        "channel_order": [entry["label"] for entry in contract],
        "error_matrix": {
            "lane_order": full_lane_order,
            "power_signed_12_by_lane": all_power.tolist(),
            "complex_signed_12_by_lane": [
                [[complex(value).real, complex(value).imag] for value in row]
                for row in all_amplitude
            ],
        },
        "seed_relative_response_matrix": {
            "lane_order": lane_names,
            "power_signed_12_by_lane": power_response.tolist(),
            "complex_signed_12_by_lane": [
                [[complex(value).real, complex(value).imag] for value in row]
                for row in amplitude_response
            ],
        },
        "seed_metrics": {
            "normalized_power_l2": seed_power_norm,
            "normalized_complex_amplitude_l2": seed_amplitude_norm,
            "normalized_joint_l2": seed_combined_norm,
            "power_pass_count_recomputed": seed_passes[0],
            "complex_amplitude_pass_count_recomputed": seed_passes[1],
        },
        "lane_metrics": lane_metrics,
        "directionality": {
            "power_pairwise_response": _pairwise_directionality(
                lane_names,
                power_response,
                complex_matrix=False,
            ),
            "complex_amplitude_pairwise_response": _pairwise_directionality(
                lane_names,
                amplitude_response,
                complex_matrix=True,
            ),
            "power_response_svd": _svd_payload(
                power_response,
                lane_names,
            ),
            "complex_amplitude_response_svd": _svd_payload(
                amplitude_response,
                lane_names,
            ),
        },
        "linearized_pairwise_combinations": pairwise_combinations,
        "interpretation_guards": {
            "response_superposition_is_not_a_pde_result": True,
            "svd_is_diagnostic_not_a_reduced_physics_model": True,
            "correlation_does_not_prove_causality": True,
            "formal_12_power_and_12_complex_gate_unchanged": True,
        },
    }


def restricted_response_subspace(
    response: Mapping[str, Any],
    *,
    selected_channel_labels: Sequence[str],
) -> dict[str, Any]:
    """Recompute response SVDs on a named subset of frozen channels."""

    channel_order = response.get("channel_order")
    matrix = response.get("seed_relative_response_matrix")
    if not isinstance(channel_order, list) or len(channel_order) != 12:
        raise ValueError("response channel order is invalid")
    if not isinstance(matrix, Mapping):
        raise ValueError("seed-relative response matrix is absent")
    labels = list(selected_channel_labels)
    if not labels or len(labels) != len(set(labels)):
        raise ValueError("selected channel labels must be unique and nonempty")
    missing = set(labels) - set(channel_order)
    if missing:
        raise ValueError(f"selected channels are absent: {sorted(missing)}")
    indices = [channel_order.index(label) for label in labels]
    lane_order = matrix.get("lane_order")
    power = np.asarray(matrix.get("power_signed_12_by_lane"), dtype=float)
    complex_pairs = np.asarray(
        matrix.get("complex_signed_12_by_lane"),
        dtype=float,
    )
    if (
        not isinstance(lane_order, list)
        or power.shape != (12, len(lane_order))
        or complex_pairs.shape != (12, len(lane_order), 2)
    ):
        raise ValueError("seed-relative response matrix shape is invalid")
    amplitude = complex_pairs[:, :, 0] + 1j * complex_pairs[:, :, 1]
    power_selected = power[indices, :]
    amplitude_selected = amplitude[indices, :]
    _require_finite_array(power_selected, label="restricted.power")
    _require_finite_array(amplitude_selected, label="restricted.amplitude")

    power_svd = _svd_payload(power_selected, lane_order)
    amplitude_svd = _svd_payload(amplitude_selected, lane_order)

    def rank_for_energy(svd: Mapping[str, Any], threshold: float) -> int:
        cumulative = 0.0
        for rank, fraction in enumerate(
            svd["squared_energy_fractions"],
            start=1,
        ):
            cumulative += float(fraction)
            if cumulative >= threshold:
                return rank
        return len(svd["squared_energy_fractions"])

    return {
        "selected_channel_labels": labels,
        "selected_channel_count": len(labels),
        "lane_order": lane_order,
        "power_response_svd": power_svd,
        "complex_amplitude_response_svd": amplitude_svd,
        "effective_rank": {
            "power_at_95_percent_energy": rank_for_energy(power_svd, 0.95),
            "power_at_99_percent_energy": rank_for_energy(power_svd, 0.99),
            "complex_at_95_percent_energy": rank_for_energy(
                amplitude_svd,
                0.95,
            ),
            "complex_at_99_percent_energy": rank_for_energy(
                amplitude_svd,
                0.99,
            ),
        },
        "interpretation": (
            "rank is across measured lane responses restricted to the named "
            "channels; it does not imply a reduced PDE operator"
        ),
    }


def topology_resource_row(
    *,
    lane: str,
    record: Mapping[str, Any],
    result_field: str,
    seed_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Extract measured topology/matrix/factor/peak data fail-closed."""

    result = record.get(result_field)
    if not isinstance(result, Mapping):
        raise ValueError(f"{lane} lacks result field {result_field}")
    matrix = result.get("matrix_stats")
    factor = result.get("stage4_dtn_factor_inventory")
    authority = record.get("resource_authority")
    if not isinstance(matrix, Mapping):
        raise ValueError(f"{lane} lacks measured matrix statistics")
    if not isinstance(factor, Mapping) or factor.get("available") is not True:
        raise ValueError(f"{lane} lacks a measured factor inventory")
    factor_matrix = factor.get("matrix_stats")
    if not isinstance(factor_matrix, Mapping):
        raise ValueError(f"{lane} lacks factor matrix statistics")
    if not isinstance(authority, Mapping):
        raise ValueError(f"{lane} lacks process-tree resource authority")

    target = record.get("target_identity") or {}
    axis = result.get("mesh_cells_resolved")
    if axis is None:
        axis = target.get("actual_mesh_cells_resolved")
    if axis is not None:
        if (
            not isinstance(axis, Sequence)
            or isinstance(axis, (str, bytes))
            or len(axis) != 3
        ):
            raise ValueError(f"{lane} axis topology must contain three counts")
        axis = [int(value) for value in axis]
        if any(value <= 0 for value in axis):
            raise ValueError(f"{lane} axis topology must be positive")

    numeric = {
        "global_cells": _positive_float(
            result.get("num_mesh_cells"),
            label=f"{lane}.global_cells",
        ),
        "full3d_equivalent_dofs": _positive_float(
            result.get("num_nedelec_dofs"),
            label=f"{lane}.dofs",
        ),
        "active_rows": _positive_float(
            matrix.get("matrix_rows"),
            label=f"{lane}.rows",
        ),
        "matrix_nnz_used": _positive_float(
            matrix.get("matrix_nnz_used"),
            label=f"{lane}.matrix_nnz",
        ),
        "factor_nnz": _positive_float(
            factor_matrix.get("matrix_nnz_used"),
            label=f"{lane}.factor_nnz",
        ),
        "process_tree_peak_gib": _positive_float(
            authority.get("memory_authority_gib"),
            label=f"{lane}.peak_gib",
        ),
    }
    row: dict[str, Any] = {
        "lane": lane,
        "result_field": result_field,
        "space": (
            f"trace_p{int(result.get('nedelec_trace_degree_resolved'))}_"
            f"interior_p{int(result.get('nedelec_interior_degree_resolved'))}"
        ),
        "nominal_h_nm": _positive_float(
            result.get("h_nm"),
            label=f"{lane}.h_nm",
        ),
        "axis_cells": axis,
        "axis_cells_semantics": (
            "measured"
            if result.get("mesh_cells_resolved") is not None
            else (
                "recorded_in_target_identity"
                if axis is not None
                else "not_recorded_in_legacy_watchdog"
            )
        ),
        **{
            key: int(value)
            if key
            in {
                "global_cells",
                "full3d_equivalent_dofs",
                "active_rows",
                "matrix_nnz_used",
                "factor_nnz",
            }
            else value
            for key, value in numeric.items()
        },
        "average_matrix_row_width": (
            numeric["matrix_nnz_used"] / numeric["active_rows"]
        ),
        "factor_fill_ratio": (
            numeric["factor_nnz"] / numeric["matrix_nnz_used"]
        ),
        "peak_scope": (
            "two_solve_global_p_pair_plus_localization"
            if result_field == "enriched"
            else "single_fixed_trace_candidate_pipeline"
        ),
    }
    if seed_row is None:
        row["marginal_to_fixed_h15_seed"] = None
    else:
        marginal: dict[str, Any] = {}
        for key in (
            "global_cells",
            "full3d_equivalent_dofs",
            "active_rows",
            "matrix_nnz_used",
            "factor_nnz",
            "process_tree_peak_gib",
        ):
            delta = row[key] - seed_row[key]
            marginal[f"delta_{key}"] = delta
            marginal[f"relative_{key}"] = delta / seed_row[key]
        marginal["peak_directly_comparable"] = (
            row["peak_scope"] == seed_row["peak_scope"]
        )
        row["marginal_to_fixed_h15_seed"] = marginal
    return row
