"""V10 independent raw-field qualification and dispatch; no FE or solver."""

import math

import numpy as np

from benchmarks.neural_fe_gate_check import complex_values as complex_vector


def relative_difference(value, reference):
    absolute = float(np.linalg.norm(value - reference))
    scale = float(np.linalg.norm(reference))
    return absolute / scale if scale > 1e-12 else absolute


def original_equation(audit):
    fields = (
        "schur_relative",
        "native_relative",
        "augmented_relative",
        "original_total_augmented_relative",
        "port_full_rhs_relative",
        "port_operation_relative",
    )
    checks = {
        key: math.isfinite(audit[key]) and 0 <= audit[key] <= 1e-6 for key in fields
    }
    checks["recovery_relative"] = (
        math.isfinite(audit["recovery_relative"])
        and 0 <= audit["recovery_relative"] <= 1e-10
    )
    checks["slave_storage_zero"] = audit["slave_storage_max"] == 0
    checks["original_schur_identity"] = (
        0 <= audit["schur_original_identity_operation_relative"] <= 1e-10
    )
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "rho": max(
            audit[k]
            for k in ("schur_relative", "native_relative", "port_full_rhs_relative")
        ),
    }


def check_candidate(candidate, verification):
    name = verification["candidate"]
    physics = verification["physics"]
    row = physics["rows"][name]
    reference = physics["rows"]["REFERENCE"]
    equation = original_equation(row["audit"])
    field_keys = (
        "full_FE_L2_relative",
        "full_FE_scaled_curl_relative",
        "scattered_FE_L2_relative",
        "scattered_scaled_curl_relative",
        "selected_E_relative",
        "selected_H_relative",
    )
    errors = {key: row[key] for key in field_keys}
    for key, vector in (
        ("selected_E_relative", "selected_E"),
        ("selected_H_relative", "selected_H_code"),
    ):
        errors[key] = relative_difference(
            complex_vector(row[vector]), complex_vector(reference[vector])
        )
    fields = {
        key: math.isfinite(errors[key]) and 0 <= errors[key] <= 1e-4
        for key in field_keys
    }
    channel_checks = {}
    for key in ("ordered_complex_port_vector", "ordered_complex_scattered_port_vector"):
        value, ref = complex_vector(row[key]), complex_vector(reference[key])
        if value.shape != (40,) or ref.shape != (40,):
            raise ValueError("all forty original ordered channels required")
        difference = relative_difference(value, ref)
        channel_checks[key] = {
            "relative_or_near_zero_absolute": difference,
            "passed": math.isfinite(difference) and difference <= 1e-4,
        }
    powers = {
        key: abs(row["port"][key] - reference["port"][key])
        for key in ("R_total", "T_total", "A_balance")
    }
    powers["A_volume"] = abs(
        row["volume"]["A_volume_total"] - reference["volume"]["A_volume_total"]
    )
    values = np.asarray(row["ordered_per_channel_power"], dtype=float)
    refs = np.asarray(reference["ordered_per_channel_power"], dtype=float)
    if values.shape != (40,) or refs.shape != (40,):
        raise ValueError("complete per-channel power inventory required")
    power_error = float(np.max(np.abs(values - refs)))
    closure = abs(row["volume"]["energy_closure_error_port_volume"])
    volume_balance = abs(row["port"]["A_balance"] - row["volume"]["A_volume_total"])
    powers_pass = all(math.isfinite(x) and x <= 1e-5 for x in powers.values())
    powers_pass &= math.isfinite(power_error) and power_error <= 1e-6
    powers_pass &= math.isfinite(closure) and closure <= 1e-5 and volume_balance <= 1e-5
    reference_pass = original_equation(reference["audit"])["passed"]
    reference_pass &= (
        reference["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-10
    )
    independent_native_pass = (
        row["audit"]["independent_DOLFINx_total_native_relative"] <= 1e-6
    )
    same = equation["passed"] and reference_pass and independent_native_pass
    same &= (
        all(fields.values())
        and all(x["passed"] for x in channel_checks.values())
        and powers_pass
    )
    baseline = candidate["baseline_audit"]
    base_rho = original_equation(baseline)["rho"]
    scatter = row["scattered_FE_L2_relative"]
    curl = row["scattered_scaled_curl_relative"]
    strong = equation["rho"] <= 0.1 and scatter <= 0.25 and curl <= 0.25
    positive = (
        equation["rho"] <= 0.5 * base_rho
        and scatter <= 0.5
        and row["audit"]["native_relative"] <= baseline["native_relative"]
    )
    signal = (
        "P+" if strong else "P" if positive else "F" if scatter <= 0.25 else "NEGATIVE"
    )
    return {
        "candidate": name,
        "status": "SAME_DISCRETE_QUALIFIED" if same else "NOT_QUALIFIED",
        "original_equation": equation,
        "reference_pass": bool(reference_pass),
        "field_checks": fields,
        "original_field_errors": errors,
        "channel_checks": channel_checks,
        "power_differences": powers,
        "max_channel_power_difference": power_error,
        "energy_closure_absolute": closure,
        "A_balance_A_volume_absolute": volume_balance,
        "baseline_rho": base_rho,
        "progress_signal": signal,
        "E_admitted": signal in ("P", "P+") and not same,
        "P4_admitted": bool(same),
        "recorded_status_trusted": False,
        "diagnostic_RTA_only": not same,
        "selected_scattered_point_samples": "not separately recorded; full scattered E/H norms checked; no candidate qualifies",
    }
