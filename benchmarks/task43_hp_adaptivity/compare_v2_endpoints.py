"""Pure, non-selecting comparison helpers for Task43 V2 endpoint diagnostics.

The V1 reader remains fixed to its 612-row R13 contract.  This module adds a
separate R13/R14 diagnostic comparison: common modes are keyed by physical
identity and the 224 R14-only modes are measured as a one-sided truncation
tail, never represented as zero-valued R13 coefficients.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

import numpy as np

from src.postprocessing.physical_field_comparison import (
    magnetic_field_from_electric_curl,
    weighted_vector_field_metrics,
)

ModeKey = tuple[str, int, int, str]

R13_MODE_KEYS = frozenset(
    (side, m, n, polarization)
    for side in ("top", "bottom")
    for m in range(-4, 5)
    for n in range(-8, 9)
    for polarization in ("s", "p")
)
R14_MODE_KEYS = frozenset(
    (side, m, n, polarization)
    for side in ("top", "bottom")
    for m in range(-5, 6)
    for n in range(-9, 10)
    for polarization in ("s", "p")
)
R14_TAIL_MODE_KEYS = R14_MODE_KEYS - R13_MODE_KEYS

# These are ten percent of the frozen final tolerances in comparison_contract_v1.
PERTURBATION_LIMITS = {
    "R_total": 1.0e-6,
    "T_total": 1.0e-6,
    "A_volume": 1.0e-6,
    "R00_s": 1.0e-7,
    "R00_p": 1.0e-7,
    "R00_total": 1.0e-6,
    "individual_channel_power_ratio": 1.0e-7,
    "boundary_amplitude_group_relative_with_incident_floor": 1.0e-5,
    "total_or_scattered_E_H_and_G_relative_with_incident_floor": 1.0e-5,
    "R14_tail_channel_power_ratio": 1.0e-7,
    "R14_tail_side_aggregate_power": 1.0e-6,
    "R14_tail_amplitude_group_relative_with_incident_floor": 1.0e-5,
}

_FIELD_ARRAYS = (
    "E_total_code",
    "curl_E_total_code",
    "H_total_A_per_m",
    "incident_background_E_code",
    "incident_background_H_A_per_m",
    "E_scattered_code",
    "H_scattered_A_per_m",
)
_POWER_NAMES = ("R_total", "T_total", "A_volume", "R00_s", "R00_p", "R00_total")
_PHYSICAL_CONFIGURATION_FIELDS = (
    "geometry_kind",
    "scattering_background",
    "electric_field_unit",
    "magnetic_field_unit",
    "lambda0",
    "period_x",
    "period_y",
    "physical_z_min",
    "physical_z_max",
    "domain_z_min",
    "domain_z_max",
    "air_height",
    "grating_bounds",
    "grating_width_x",
    "grating_width_y",
    "grating_height",
    "interface_z",
    "substrate_thickness",
    "incident_theta_deg",
    "incident_phi_deg",
    "incident_amplitude",
    "incident_e0_v_per_m",
    "polarization_kind",
    "polarization",
    "propagation_direction",
    "wavevector",
    "floquet_phase_x",
    "floquet_phase_y",
    "n_air",
    "mu_r",
    "n_substrate",
    "n_grating",
    "eps_air",
    "eps_substrate",
    "eps_grating",
    "eps_r",
    "grating_background_eps",
    "grating_index",
    "k0",
    "magnetic_field_scale_A_per_m",
    "use_floquet_xy",
    "use_pml",
    "pml_alpha",
    "pml_bottom_thickness",
    "pml_top_thickness",
    "stage4_boundary_model",
    "stage4_pml_outer_bc",
    "mesh_cell_type_resolved",
)


def task43_v2_physical_configuration_identity(
    resolved_config: Mapping[str, Any],
    *,
    axis_values_nm: Mapping[str, Any],
    candidate_plan_sha256: str,
    active_degree_plan_sha256: str,
) -> dict[str, Any]:
    """Hash physical coefficients separately from the candidate discretization."""

    missing = [
        name for name in _PHYSICAL_CONFIGURATION_FIELDS if name not in resolved_config
    ]
    if missing:
        raise ValueError(f"resolved physical config is missing fields: {missing}")
    axes: dict[str, list[float]] = {}
    for axis in ("x", "y", "z"):
        values = np.asarray(axis_values_nm[axis], dtype=np.float64)
        if values.ndim != 1 or values.size < 2 or not np.all(np.isfinite(values)):
            raise ValueError(
                f"actual {axis} axis must be finite with at least two entries"
            )
        if np.any(np.diff(values) <= 0.0):
            raise ValueError(f"actual {axis} axis must be strictly increasing")
        axes[axis] = values.tolist()
    for name, digest in (
        ("candidate_plan_sha256", candidate_plan_sha256),
        ("active_degree_plan_sha256", active_degree_plan_sha256),
    ):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"{name} must be a lowercase SHA256 identity")
    physical_payload = {
        "schema": "task43.v2.shared_physical_configuration.v1",
        "resolved_physics": {
            name: resolved_config[name] for name in _PHYSICAL_CONFIGURATION_FIELDS
        },
    }
    physical_sha256 = hashlib.sha256(
        json.dumps(
            physical_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    discretization_payload = {
        "schema": "task43.v2.discretization_identity.v1",
        "actual_axis_values_nm": axes,
        "candidate_plan_sha256": candidate_plan_sha256,
        "active_degree_plan_sha256": active_degree_plan_sha256,
    }
    discretization_sha256 = hashlib.sha256(
        json.dumps(
            discretization_payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": physical_payload["schema"],
        "sha256": physical_sha256,
        "payload": physical_payload,
        "discretization_identity": {
            "schema": discretization_payload["schema"],
            "sha256": discretization_sha256,
            "payload": discretization_payload,
        },
        "excluded_numerical_controls": [
            "volume/incident/port quadrature degrees",
            "DtN rectangle and derived outgoing mode inventory",
            "direct solver and preconditioner controls",
            "case name and output paths",
        ],
    }


def _mode_key(row: Mapping[str, Any]) -> ModeKey:
    for name in ("m", "n"):
        value = row[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"mode index {name} must be an integer JSON value")
    side = str(row["side"])
    polarization = str(row["polarization"])
    if side not in {"top", "bottom"} or polarization not in {"s", "p"}:
        raise ValueError("mode side/polarization must be top|bottom and s|p")
    return (
        side,
        row["m"],
        row["n"],
        polarization,
    )


def _complex_pair(value: Any, *, label: str) -> complex:
    pair = np.asarray(value, dtype=np.float64)
    if pair.shape != (2,) or not np.all(np.isfinite(pair)):
        raise ValueError(f"{label} must be a finite [real, imaginary] pair")
    return complex(float(pair[0]), float(pair[1]))


def _finite_float(value: Any, *, label: str) -> float:
    number = float(value)
    if not np.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _validated_rows(
    payload: Mapping[str, Any], *, label: str, expected: frozenset[ModeKey]
) -> dict[ModeKey, dict[str, Any]]:
    rows = payload.get("orders")
    if not isinstance(rows, list):
        raise TypeError(f"{label} mode payload must contain an orders list")
    if len(rows) != len(expected):
        raise ValueError(f"{label} mode count must be exactly {len(expected)}")
    indexed: dict[ModeKey, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError(f"{label} mode rows must be JSON objects")
        key = _mode_key(row)
        if key not in expected:
            raise ValueError(f"{label} contains out-of-contract mode {key}")
        if key in indexed:
            raise ValueError(f"{label} contains duplicate mode {key}")
        _complex_pair(
            row["outgoing_amplitude_at_boundary"], label=f"{label} {key} amplitude"
        )
        if not isinstance(row.get("power_carrying"), bool):
            raise TypeError(f"{label} {key} must declare power_carrying as a boolean")
        for field in ("power_ratio", "R", "T"):
            _finite_float(row[field], label=f"{label} {key} {field}")
        power_ratio = float(row["power_ratio"])
        reflected = float(row["R"])
        transmitted = float(row["T"])
        if power_ratio < 0.0 or reflected < 0.0 or transmitted < 0.0:
            raise ValueError(f"{label} {key} power values must be nonnegative")
        expected_reflected = (
            power_ratio if key[0] == "top" and row["power_carrying"] else 0.0
        )
        expected_transmitted = (
            power_ratio if key[0] == "bottom" and row["power_carrying"] else 0.0
        )
        if not np.isclose(reflected, expected_reflected, rtol=2.0e-10, atol=1.0e-14):
            raise ValueError(
                f"{label} {key} R does not match side/power-carrying semantics"
            )
        if not np.isclose(
            transmitted, expected_transmitted, rtol=2.0e-10, atol=1.0e-14
        ):
            raise ValueError(
                f"{label} {key} T does not match side/power-carrying semantics"
            )
        indexed[key] = row
    if set(indexed) != expected:
        missing = sorted(expected - set(indexed))
        raise ValueError(f"{label} mode inventory is incomplete; missing={missing[:4]}")
    payload_metrics = payload.get("metrics")
    if not isinstance(payload_metrics, Mapping):
        raise TypeError(f"{label} payload must declare aggregate modal metrics")
    derived = _power_aggregates(indexed, 0.0)
    for name in ("R_total", "T_total", "R00_s", "R00_p", "R00_total"):
        observed = _finite_float(payload_metrics[name], label=f"{label} metrics.{name}")
        if not np.isclose(observed, derived[name], rtol=2.0e-10, atol=1.0e-13):
            raise ValueError(f"{label} aggregate {name} differs from its raw mode rows")
    if int(payload_metrics.get("dtn_port_mode_count", -1)) != len(expected):
        raise ValueError(
            f"{label} declared mode count differs from its exact inventory"
        )
    return indexed


def _power_aggregates(
    rows: Mapping[ModeKey, Mapping[str, Any]], a_volume: float
) -> dict[str, float]:
    r_total = float(sum(float(row["R"]) for row in rows.values()))
    t_total = float(sum(float(row["T"]) for row in rows.values()))
    r00_s = float(
        sum(
            float(row["R"])
            for key, row in rows.items()
            if key[0] == "top" and key[1:3] == (0, 0) and key[3] == "s"
        )
    )
    r00_p = float(
        sum(
            float(row["R"])
            for key, row in rows.items()
            if key[0] == "top" and key[1:3] == (0, 0) and key[3] == "p"
        )
    )
    return {
        "R_total": r_total,
        "T_total": t_total,
        "A_volume": _finite_float(a_volume, label="A_volume"),
        "R00_s": r00_s,
        "R00_p": r00_p,
        "R00_total": r00_s + r00_p,
    }


def _key_digest(keys: set[ModeKey] | frozenset[ModeKey]) -> str:
    encoded = json.dumps(sorted(keys), separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _require_same_identity(reference: str, candidate: str, *, label: str) -> str:
    for value in (reference, candidate):
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"{label} identities must be lowercase SHA256 strings")
    if reference != candidate:
        raise ValueError(f"endpoints have different {label} identities")
    return reference


def compare_r13_modal_outputs(
    reference_payload: Mapping[str, Any],
    candidate_payload: Mapping[str, Any],
    *,
    reference_a_volume: float,
    candidate_a_volume: float,
    reference_physical_configuration_sha256: str,
    candidate_physical_configuration_sha256: str,
    reference_discretization_sha256: str,
    candidate_discretization_sha256: str,
) -> dict[str, Any]:
    """Compare two complete R13 outputs on the same physical problem and FE space."""

    physical_identity = _require_same_identity(
        reference_physical_configuration_sha256,
        candidate_physical_configuration_sha256,
        label="physical configuration",
    )
    discretization_identity = _require_same_identity(
        reference_discretization_sha256,
        candidate_discretization_sha256,
        label="discretization",
    )
    reference = _validated_rows(
        reference_payload, label="reference R13", expected=R13_MODE_KEYS
    )
    candidate = _validated_rows(
        candidate_payload, label="candidate R13", expected=R13_MODE_KEYS
    )
    reference_power = _power_aggregates(reference, reference_a_volume)
    candidate_power = _power_aggregates(candidate, candidate_a_volume)
    aggregate_differences = {
        name: abs(candidate_power[name] - reference_power[name])
        for name in _POWER_NAMES
    }
    aggregate_gates = {
        name: {
            "absolute_difference": difference,
            "limit": PERTURBATION_LIMITS[name],
            "pass": difference <= PERTURBATION_LIMITS[name],
        }
        for name, difference in aggregate_differences.items()
    }

    channel_rows: list[dict[str, Any]] = []
    amplitude_rows: list[dict[str, Any]] = []
    channel_differences: list[float] = []
    amplitude_groups: dict[str, dict[str, Any]] = {}
    for key in sorted(R13_MODE_KEYS):
        reference_row = reference[key]
        candidate_row = candidate[key]
        reference_amplitude = _complex_pair(
            reference_row["outgoing_amplitude_at_boundary"],
            label=f"reference R13 {key}",
        )
        candidate_amplitude = _complex_pair(
            candidate_row["outgoing_amplitude_at_boundary"],
            label=f"candidate R13 {key}",
        )
        power_difference = abs(
            float(candidate_row["power_ratio"]) - float(reference_row["power_ratio"])
        )
        amplitude_difference = candidate_amplitude - reference_amplitude
        channel_differences.append(power_difference)
        channel_rows.append(
            {
                "key": list(key),
                "reference_power_ratio": float(reference_row["power_ratio"]),
                "candidate_power_ratio": float(candidate_row["power_ratio"]),
                "absolute_difference": power_difference,
            }
        )
        amplitude_rows.append(
            {
                "key": list(key),
                "reference_boundary_amplitude": [
                    reference_amplitude.real,
                    reference_amplitude.imag,
                ],
                "candidate_boundary_amplitude": [
                    candidate_amplitude.real,
                    candidate_amplitude.imag,
                ],
                "difference": [amplitude_difference.real, amplitude_difference.imag],
                "absolute_difference": abs(amplitude_difference),
            }
        )
    max_index = int(np.argmax(channel_differences))
    channel_max = float(channel_differences[max_index])
    channel_gate = channel_max <= PERTURBATION_LIMITS["individual_channel_power_ratio"]
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            keys = [
                key
                for key in sorted(R13_MODE_KEYS)
                if key[0] == side and key[3] == polarization
            ]
            reference_values = np.asarray(
                [
                    _complex_pair(
                        reference[key]["outgoing_amplitude_at_boundary"],
                        label=f"reference R13 {key}",
                    )
                    for key in keys
                ],
                dtype=np.complex128,
            )
            candidate_values = np.asarray(
                [
                    _complex_pair(
                        candidate[key]["outgoing_amplitude_at_boundary"],
                        label=f"candidate R13 {key}",
                    )
                    for key in keys
                ],
                dtype=np.complex128,
            )
            reference_norm = float(np.linalg.norm(reference_values))
            difference_norm = float(np.linalg.norm(candidate_values - reference_values))
            relative = difference_norm / max(reference_norm, 1.0)
            limit = PERTURBATION_LIMITS[
                "boundary_amplitude_group_relative_with_incident_floor"
            ]
            amplitude_groups[f"{side}_{polarization}"] = {
                "mode_count": len(keys),
                "reference_l2": reference_norm,
                "absolute_difference_l2": difference_norm,
                "relative_with_unit_incident_modal_floor": relative,
                "limit": limit,
                "pass": relative <= limit,
            }

    passed = (
        all(gate["pass"] for gate in aggregate_gates.values())
        and channel_gate
        and all(group["pass"] for group in amplitude_groups.values())
    )
    return {
        "schema": "task43.v2_r13_same_space_modal_comparison.v1",
        "selection_eligible": False,
        "physical_configuration_identity_sha256": physical_identity,
        "discretization_identity_sha256": discretization_identity,
        "reference_inventory": {
            "mode_count": 612,
            "key_sha256": _key_digest(R13_MODE_KEYS),
        },
        "candidate_inventory": {
            "mode_count": 612,
            "key_sha256": _key_digest(R13_MODE_KEYS),
        },
        "aggregate_power": {
            "reference": reference_power,
            "candidate": candidate_power,
            "absolute_differences": aggregate_differences,
            "gates": aggregate_gates,
        },
        "per_channel_power_ratio": {
            "maximum_absolute_difference": channel_max,
            "maximum_key": channel_rows[max_index]["key"],
            "limit": PERTURBATION_LIMITS["individual_channel_power_ratio"],
            "pass": channel_gate,
            "all_rows": channel_rows,
        },
        "boundary_amplitude_groups": amplitude_groups,
        "boundary_amplitude_all_rows": amplitude_rows,
        "pass_10_percent_perturbation_gate": bool(passed),
        "threshold_basis": "0.1 times frozen Task43 final tolerances; exact R13 key matching",
    }


def compare_r13_r14_modal_outputs(
    r13_payload: Mapping[str, Any],
    r14_payload: Mapping[str, Any],
    *,
    r13_a_volume: float,
    r14_a_volume: float,
    r13_physical_configuration_sha256: str,
    r14_physical_configuration_sha256: str,
    r13_discretization_sha256: str,
    r14_discretization_sha256: str,
) -> dict[str, Any]:
    """Compare common R13 modes and measure the R14-only tail independently.

    The R13-only and R14-only mode sets are fixed by their finite rectangular
    inventories.  No missing mode is imputed as zero.  Power aggregates are
    recomputed from each mode row; ``A_volume`` is supplied from its independent
    volume-integral record.
    """

    physical_identity = _require_same_identity(
        r13_physical_configuration_sha256,
        r14_physical_configuration_sha256,
        label="physical configuration",
    )
    discretization_identity = _require_same_identity(
        r13_discretization_sha256,
        r14_discretization_sha256,
        label="discretization",
    )
    r13 = _validated_rows(r13_payload, label="R13", expected=R13_MODE_KEYS)
    r14 = _validated_rows(r14_payload, label="R14", expected=R14_MODE_KEYS)
    common = R13_MODE_KEYS & R14_MODE_KEYS
    tail = R14_MODE_KEYS - R13_MODE_KEYS
    if len(common) != 612 or len(tail) != 224:
        raise RuntimeError("frozen R13/R14 common and tail counts have changed")

    r13_power = _power_aggregates(r13, r13_a_volume)
    r14_power = _power_aggregates(r14, r14_a_volume)
    aggregate_differences = {
        name: abs(r14_power[name] - r13_power[name]) for name in _POWER_NAMES
    }

    common_power_rows: list[dict[str, Any]] = []
    common_amplitude_rows: list[dict[str, Any]] = []
    common_power_differences: list[float] = []
    for key in sorted(common):
        ref_row = r13[key]
        candidate_row = r14[key]
        ref_amplitude = _complex_pair(
            ref_row["outgoing_amplitude_at_boundary"], label=f"R13 {key}"
        )
        candidate_amplitude = _complex_pair(
            candidate_row["outgoing_amplitude_at_boundary"], label=f"R14 {key}"
        )
        power_difference = abs(
            float(candidate_row["power_ratio"]) - float(ref_row["power_ratio"])
        )
        amplitude_difference = candidate_amplitude - ref_amplitude
        common_power_differences.append(power_difference)
        common_power_rows.append(
            {
                "key": list(key),
                "R13_power_ratio": float(ref_row["power_ratio"]),
                "R14_power_ratio": float(candidate_row["power_ratio"]),
                "absolute_difference": power_difference,
            }
        )
        common_amplitude_rows.append(
            {
                "key": list(key),
                "R13_boundary_amplitude": [ref_amplitude.real, ref_amplitude.imag],
                "R14_boundary_amplitude": [
                    candidate_amplitude.real,
                    candidate_amplitude.imag,
                ],
                "difference": [amplitude_difference.real, amplitude_difference.imag],
                "absolute_difference": abs(amplitude_difference),
            }
        )

    common_power_max_index = int(np.argmax(common_power_differences))
    common_power_max = float(common_power_differences[common_power_max_index])
    common_power_max_key = common_power_rows[common_power_max_index]["key"]
    common_groups: dict[str, dict[str, float | int | bool]] = {}
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            group_keys = [
                key
                for key in sorted(common)
                if key[0] == side and key[3] == polarization
            ]
            ref_values = np.asarray(
                [
                    _complex_pair(
                        r13[key]["outgoing_amplitude_at_boundary"], label=f"R13 {key}"
                    )
                    for key in group_keys
                ],
                dtype=np.complex128,
            )
            candidate_values = np.asarray(
                [
                    _complex_pair(
                        r14[key]["outgoing_amplitude_at_boundary"], label=f"R14 {key}"
                    )
                    for key in group_keys
                ],
                dtype=np.complex128,
            )
            ref_norm = float(np.linalg.norm(ref_values))
            difference_norm = float(np.linalg.norm(candidate_values - ref_values))
            relative_floor = difference_norm / max(ref_norm, 1.0)
            common_groups[f"{side}_{polarization}"] = {
                "mode_count": len(group_keys),
                "R13_boundary_amplitude_l2": ref_norm,
                "difference_boundary_amplitude_l2": difference_norm,
                "relative_with_unit_incident_modal_floor": relative_floor,
                "within_10_percent_final_tolerance": relative_floor
                <= PERTURBATION_LIMITS[
                    "boundary_amplitude_group_relative_with_incident_floor"
                ],
            }

    tail_rows: list[dict[str, Any]] = []
    tail_power_max = 0.0
    tail_power_max_key: list[Any] | None = None
    tail_power_by_side = {"top": 0.0, "bottom": 0.0}
    tail_amplitude_groups: dict[str, dict[str, float | int | bool]] = {}
    for key in sorted(tail):
        row = r14[key]
        amplitude = _complex_pair(
            row["outgoing_amplitude_at_boundary"], label=f"R14 tail {key}"
        )
        power_ratio = float(row["power_ratio"])
        if power_ratio < 0.0:
            raise ValueError(f"R14 tail power ratio must be nonnegative: {key}")
        if power_ratio > tail_power_max:
            tail_power_max = power_ratio
            tail_power_max_key = list(key)
        tail_power_by_side[key[0]] += float(row["R"] if key[0] == "top" else row["T"])
        tail_rows.append(
            {
                "key": list(key),
                "R13_amplitude": None,
                "R13_power_ratio": None,
                "R14_boundary_amplitude": [amplitude.real, amplitude.imag],
                "R14_power_ratio": power_ratio,
                "R14_power_contribution": float(
                    row["R"] if key[0] == "top" else row["T"]
                ),
                "delta": None,
                "scope": "R14-only truncation-tail observation; no R13 coefficient exists",
            }
        )
    for side in ("top", "bottom"):
        for polarization in ("s", "p"):
            group_keys = [
                key for key in sorted(tail) if key[0] == side and key[3] == polarization
            ]
            amplitudes = np.asarray(
                [
                    _complex_pair(
                        r14[key]["outgoing_amplitude_at_boundary"],
                        label=f"R14 tail {key}",
                    )
                    for key in group_keys
                ],
                dtype=np.complex128,
            )
            norm = float(np.linalg.norm(amplitudes))
            relative_floor = norm / 1.0  # frozen unit-incident modal amplitude floor
            tail_amplitude_groups[f"{side}_{polarization}"] = {
                "mode_count": len(group_keys),
                "R14_tail_boundary_amplitude_l2": norm,
                "incident_amplitude_floor": 1.0,
                "relative_with_incident_floor": relative_floor,
                "within_10_percent_final_tolerance": relative_floor
                <= PERTURBATION_LIMITS[
                    "R14_tail_amplitude_group_relative_with_incident_floor"
                ],
            }

    joint_amplitude_groups: dict[str, dict[str, float | bool | str]] = {}
    for label, common_metrics in common_groups.items():
        tail_metrics = tail_amplitude_groups[label]
        common_difference = float(common_metrics["difference_boundary_amplitude_l2"])
        tail_norm = float(tail_metrics["R14_tail_boundary_amplitude_l2"])
        reference_norm = float(common_metrics["R13_boundary_amplitude_l2"])
        envelope = float(np.hypot(common_difference, tail_norm))
        relative = envelope / max(reference_norm, 1.0)
        limit = PERTURBATION_LIMITS[
            "boundary_amplitude_group_relative_with_incident_floor"
        ]
        joint_amplitude_groups[label] = {
            "common_612_difference_l2": common_difference,
            "R14_tail_224_l2": tail_norm,
            "extension_diagnostic_envelope_l2": envelope,
            "R13_common_reference_l2": reference_norm,
            "incident_amplitude_floor": 1.0,
            "relative_extension_diagnostic_envelope": relative,
            "limit": limit,
            "pass": relative <= limit,
            "meaning": "sqrt(common_delta_l2^2 + R14_tail_l2^2) / max(R13_common_l2, 1); diagnostic envelope, not an imputed R13 tail delta",
        }

    aggregate_gates = {
        name: {
            "absolute_difference": value,
            "limit": PERTURBATION_LIMITS[name],
            "pass": value <= PERTURBATION_LIMITS[name],
        }
        for name, value in aggregate_differences.items()
    }
    channel_gate = (
        common_power_max <= PERTURBATION_LIMITS["individual_channel_power_ratio"]
    )
    tail_channel_gate = (
        tail_power_max <= PERTURBATION_LIMITS["R14_tail_channel_power_ratio"]
    )
    tail_aggregate_gates = {
        side: {
            "R14_tail_aggregate_power": value,
            "limit": PERTURBATION_LIMITS["R14_tail_side_aggregate_power"],
            "pass": value <= PERTURBATION_LIMITS["R14_tail_side_aggregate_power"],
        }
        for side, value in tail_power_by_side.items()
    }
    all_gates = (
        all(item["pass"] for item in aggregate_gates.values())
        and channel_gate
        and all(
            item["within_10_percent_final_tolerance"] for item in common_groups.values()
        )
        and all(
            item["within_10_percent_final_tolerance"]
            for item in tail_amplitude_groups.values()
        )
        and all(item["pass"] for item in joint_amplitude_groups.values())
        and tail_channel_gate
        and all(item["pass"] for item in tail_aggregate_gates.values())
    )
    return {
        "schema": "task43.v2_r13_r14_modal_comparison.v1",
        "selection_eligible": False,
        "same_FE_space_different_port_operator": True,
        "physical_configuration_identity_sha256": physical_identity,
        "discretization_identity_sha256": discretization_identity,
        "reference_inventory": {
            "label": "R13",
            "mode_count": 612,
            "key_sha256": _key_digest(R13_MODE_KEYS),
        },
        "candidate_inventory": {
            "label": "R14",
            "mode_count": 836,
            "key_sha256": _key_digest(R14_MODE_KEYS),
        },
        "common_inventory": {
            "mode_count": len(common),
            "key_sha256": _key_digest(common),
        },
        "tail_inventory": {
            "mode_count": len(tail),
            "key_sha256": _key_digest(tail),
            "semantics": "R14-only tail; R13 coefficients and deltas are null, never zero-filled",
        },
        "aggregate_power": {
            "R13": r13_power,
            "R14": r14_power,
            "absolute_differences": aggregate_differences,
            "gates": aggregate_gates,
        },
        "common_612": {
            "per_channel_power_ratio": {
                "maximum_absolute_difference": common_power_max,
                "maximum_key": common_power_max_key,
                "l2_of_absolute_differences": float(
                    np.linalg.norm(common_power_differences)
                ),
                "limit": PERTURBATION_LIMITS["individual_channel_power_ratio"],
                "pass": channel_gate,
                "all_rows": common_power_rows,
            },
            "boundary_amplitude_groups": common_groups,
            "full_inventory_extension_diagnostic_groups": joint_amplitude_groups,
            "all_boundary_amplitude_rows": common_amplitude_rows,
        },
        "r14_tail_224": {
            "per_channel_power_ratio_maximum": {
                "value": tail_power_max,
                "key": tail_power_max_key,
                "limit": PERTURBATION_LIMITS["R14_tail_channel_power_ratio"],
                "pass": tail_channel_gate,
            },
            "aggregate_power_by_outgoing_side": tail_aggregate_gates,
            "boundary_amplitude_groups": tail_amplitude_groups,
            "all_rows": tail_rows,
        },
        "pass_10_percent_perturbation_gate": bool(all_gates),
        "threshold_basis": "0.1 times frozen Task43 final tolerances; R14-only tail uses incident amplitude floor and positive outgoing tail power",
    }


def _l2(values: np.ndarray, weights: np.ndarray) -> float:
    array = np.asarray(values, dtype=np.complex128)
    return float(np.sqrt(np.dot(weights, np.sum(np.abs(array) ** 2, axis=1))))


def compare_field_sample_bundles(
    reference: Mapping[str, np.ndarray],
    candidate: Mapping[str, np.ndarray],
    *,
    k0_per_nm: float,
    magnetic_field_scale_A_per_m: float,
    mu_r: complex,
    incident_e_norm_floor: float,
    incident_h_norm_floor: float,
    incident_g_norm_floor: float,
) -> dict[str, Any]:
    """Compare actual fields sampled at identical points and with fixed weights."""

    reference_cfg = reference.get("physical_configuration_identity_sha256")
    candidate_cfg = candidate.get("physical_configuration_identity_sha256")
    if (
        not isinstance(reference_cfg, str)
        or len(reference_cfg) != 64
        or any(char not in "0123456789abcdef" for char in reference_cfg)
        or candidate_cfg != reference_cfg
    ):
        raise ValueError(
            "field samples must carry the same lowercase SHA256 physical-configuration identity"
        )

    ref_points = np.asarray(reference["points_nm"], dtype=np.float64)
    candidate_points = np.asarray(candidate["points_nm"], dtype=np.float64)
    weights = np.asarray(reference["weights_nm3"], dtype=np.float64)
    candidate_weights = np.asarray(candidate["weights_nm3"], dtype=np.float64)
    if ref_points.ndim != 2 or ref_points.shape[1] != 3 or ref_points.shape[0] == 0:
        raise ValueError("field sample points must have nonempty shape (npoints, 3)")
    if not np.all(np.isfinite(ref_points)):
        raise ValueError("field sample points must be finite")
    if not np.array_equal(ref_points, candidate_points):
        raise ValueError("field samples must use identical physical points")
    if (
        weights.ndim != 1
        or weights.size != ref_points.shape[0]
        or not np.array_equal(weights, candidate_weights)
    ):
        raise ValueError(
            "field samples must use identical positive integration weights"
        )
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("field sample weights must be finite and positive")
    for name, value in (
        ("k0_per_nm", k0_per_nm),
        ("magnetic_field_scale_A_per_m", magnetic_field_scale_A_per_m),
        ("incident_e_norm_floor", incident_e_norm_floor),
        ("incident_h_norm_floor", incident_h_norm_floor),
        ("incident_g_norm_floor", incident_g_norm_floor),
    ):
        _finite_float(value, label=name)
    if (
        k0_per_nm <= 0.0
        or min(incident_e_norm_floor, incident_h_norm_floor, incident_g_norm_floor)
        <= 0.0
    ):
        raise ValueError("field comparison scales must be strictly positive")

    ref_arrays: dict[str, np.ndarray] = {}
    candidate_arrays: dict[str, np.ndarray] = {}
    for name in _FIELD_ARRAYS:
        ref_values = np.asarray(reference[name], dtype=np.complex128)
        candidate_values = np.asarray(candidate[name], dtype=np.complex128)
        if ref_values.shape != (weights.size, 3) or candidate_values.shape != (
            weights.size,
            3,
        ):
            raise ValueError(f"field array {name} must have exact shape (npoints, 3)")
        if not np.all(np.isfinite(ref_values)) or not np.all(
            np.isfinite(candidate_values)
        ):
            raise ValueError(f"field array {name} must be finite")
        ref_arrays[name] = ref_values
        candidate_arrays[name] = candidate_values

    expected_ref_h = magnetic_field_from_electric_curl(
        ref_arrays["curl_E_total_code"],
        magnetic_field_scale_A_per_m=float(magnetic_field_scale_A_per_m),
        k0_per_nm=float(k0_per_nm),
        mu_r=mu_r,
    )
    expected_candidate_h = magnetic_field_from_electric_curl(
        candidate_arrays["curl_E_total_code"],
        magnetic_field_scale_A_per_m=float(magnetic_field_scale_A_per_m),
        k0_per_nm=float(k0_per_nm),
        mu_r=mu_r,
    )
    for label, observed, expected in (
        ("reference", ref_arrays["H_total_A_per_m"], expected_ref_h),
        ("candidate", candidate_arrays["H_total_A_per_m"], expected_candidate_h),
    ):
        if not np.allclose(observed, expected, rtol=2.0e-12, atol=1.0e-14):
            raise ValueError(f"{label} H samples do not match its recovered curl(E)")
    for label, values in (("reference", ref_arrays), ("candidate", candidate_arrays)):
        expected_e_scattered = (
            values["E_total_code"] - values["incident_background_E_code"]
        )
        expected_h_scattered = (
            values["H_total_A_per_m"] - values["incident_background_H_A_per_m"]
        )
        if not np.allclose(
            values["E_scattered_code"],
            expected_e_scattered,
            rtol=2.0e-12,
            atol=1.0e-14,
        ):
            raise ValueError(f"{label} scattered E does not match saved background")
        if not np.allclose(
            values["H_scattered_A_per_m"],
            expected_h_scattered,
            rtol=2.0e-12,
            atol=1.0e-14,
        ):
            raise ValueError(f"{label} scattered H does not match saved background")

    for name in ("incident_background_E_code", "incident_background_H_A_per_m"):
        if not np.array_equal(ref_arrays[name], candidate_arrays[name]):
            raise ValueError(
                f"field samples must use the same incident background arrays for {name}"
            )

    arrays: dict[str, tuple[np.ndarray, np.ndarray, float]] = {
        "E_total_code": (
            ref_arrays["E_total_code"],
            candidate_arrays["E_total_code"],
            float(incident_e_norm_floor),
        ),
        "H_total_A_per_m": (
            ref_arrays["H_total_A_per_m"],
            candidate_arrays["H_total_A_per_m"],
            float(incident_h_norm_floor),
        ),
        "E_scattered_code": (
            ref_arrays["E_scattered_code"],
            candidate_arrays["E_scattered_code"],
            float(incident_e_norm_floor),
        ),
        "H_scattered_A_per_m": (
            ref_arrays["H_scattered_A_per_m"],
            candidate_arrays["H_scattered_A_per_m"],
            float(incident_h_norm_floor),
        ),
    }
    metrics: dict[str, Any] = {}
    for name, (ref_values, candidate_values, floor) in arrays.items():
        metrics[name] = weighted_vector_field_metrics(
            ref_values,
            candidate_values,
            weights,
            reference_norm_floor=floor,
        )
    ref_curl = ref_arrays["curl_E_total_code"] / float(k0_per_nm)
    candidate_curl = candidate_arrays["curl_E_total_code"] / float(k0_per_nm)
    ref_e = ref_arrays["E_total_code"]
    candidate_e = candidate_arrays["E_total_code"]
    ref_g_norm = float(np.sqrt(_l2(ref_e, weights) ** 2 + _l2(ref_curl, weights) ** 2))
    candidate_g_norm = float(
        np.sqrt(_l2(candidate_e, weights) ** 2 + _l2(candidate_curl, weights) ** 2)
    )
    difference_g_norm = float(
        np.sqrt(
            _l2(candidate_e - ref_e, weights) ** 2
            + _l2(candidate_curl - ref_curl, weights) ** 2
        )
    )
    metrics["G"] = {
        "reference_g_norm": ref_g_norm,
        "candidate_g_norm": candidate_g_norm,
        "difference_g_norm": difference_g_norm,
        "incident_g_norm_floor": float(incident_g_norm_floor),
        "relative_with_incident_floor": difference_g_norm
        / max(ref_g_norm, incident_g_norm_floor),
    }
    limit = PERTURBATION_LIMITS[
        "total_or_scattered_E_H_and_G_relative_with_incident_floor"
    ]
    component_values = {
        name: float(
            value["relative_with_incident_floor"]
            if name == "G"
            else value["relative_to_reference_or_floor"]
        )
        for name, value in metrics.items()
    }
    return {
        "schema": "task43.v2_same_point_field_comparison.v1",
        "same_points_and_weights": True,
        "same_physical_configuration_identity_sha256": reference_cfg,
        "same_incident_background_arrays": True,
        "sample_count": int(weights.size),
        "k0_per_nm": float(k0_per_nm),
        "metrics": metrics,
        "perturbation_limit": limit,
        "component_relative_values": component_values,
        "pass_10_percent_perturbation_gate": bool(
            all(value <= limit for value in component_values.values())
        ),
        "scope": "Stored or freshly sampled physical fields at the same actual points; no phase fit",
    }
