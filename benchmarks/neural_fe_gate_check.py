"""Recompute pilot Gates from saved original audits and complex observables.

This checker never imports FE runtimes or implements a solver. Full field
integrals are the independently measured FE scalars; selected E/H and all
port differences are recomputed from saved complex vectors.
"""

import numpy as np


def complex_values(value):
    def convert(item):
        if isinstance(item, dict):
            return complex(item["real"], item["imag"])
        if isinstance(item, list):
            return [convert(x) for x in item]
        return item

    result = np.asarray(convert(value), dtype=np.complex128)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite saved complex observable")
    return result


def relative_difference(left, right):
    error, scale = np.linalg.norm(left - right), np.linalg.norm(right)
    return float(error / scale) if scale > 1e-12 else float(error)


def equation_gate(audit, limit=1e-6):
    keys = (
        "schur_relative",
        "augmented_relative",
        "native_relative",
        "original_total_augmented_relative",
        "port_full_rhs_relative",
        "port_operation_relative",
        "independent_DOLFINx_total_native_relative",
    )
    return bool(
        all(np.isfinite(audit[k]) and 0 <= audit[k] <= limit for k in keys)
        and np.isfinite(audit["port_absolute"])
        and audit["port_absolute"] >= 0
        and 0 <= audit["recovery_relative"] <= 1e-10
        and audit["slave_storage_max"] == 0
    )


def check_report(report):
    rows = report["physics"]["rows"]
    ref = rows["REFERENCE"]
    reference_pass = equation_gate(ref["audit"], 1e-10)
    checks = {}
    for name, row in rows.items():
        if name == "REFERENCE":
            continue
        computed = {
            "selected_E_relative": relative_difference(
                complex_values(row["selected_E"]), complex_values(ref["selected_E"])
            ),
            "selected_H_relative": relative_difference(
                complex_values(row["selected_H_code"]),
                complex_values(ref["selected_H_code"]),
            ),
            "ordered_complex_ports_relative": relative_difference(
                complex_values(row["ordered_complex_port_vector"]),
                complex_values(ref["ordered_complex_port_vector"]),
            ),
            "max_channel_power_difference": float(
                np.max(
                    np.abs(
                        np.asarray(row["ordered_per_channel_power"])
                        - np.asarray(ref["ordered_per_channel_power"])
                    )
                )
            ),
            "energy_closure_absolute": abs(
                row["port"]["R_total"]
                + row["port"]["T_total"]
                + row["volume"]["A_volume_total"]
                - 1
            ),
        }
        power_diff = {
            k: abs(row["port"][k] - ref["port"][k])
            for k in ("R_total", "T_total", "A_balance")
        }
        power_diff["A_volume"] = abs(
            row["volume"]["A_volume_total"] - ref["volume"]["A_volume_total"]
        )
        field_pass = all(
            0 <= row[k] <= 1e-4
            for k in ("full_FE_L2_relative", "full_FE_scaled_curl_relative")
        )
        field_pass &= all(
            computed[k] <= 1e-4
            for k in (
                "selected_E_relative",
                "selected_H_relative",
                "ordered_complex_ports_relative",
            )
        )
        power_pass = (
            all(v <= 1e-5 for v in power_diff.values())
            and computed["max_channel_power_difference"] <= 1e-6
            and computed["energy_closure_absolute"] <= 1e-5
        )
        equation_pass = equation_gate(row["audit"])
        original = report["comparisons"][name]
        differences_agree = all(
            np.isclose(value, original[key], rtol=1e-12, atol=1e-14)
            for key, value in computed.items()
        )
        if not differences_agree:
            raise ValueError(
                "saved comparison disagrees with complex-vector recomputation"
            )
        checks[name] = dict(
            equation_pass=equation_pass,
            field_pass=bool(field_pass),
            power_pass=bool(power_pass),
            reference_accuracy_pass=reference_pass,
            status="SAME_DISCRETE_QUALIFIED"
            if reference_pass and equation_pass and field_pass and power_pass
            else "NOT_QUALIFIED",
            computed=computed,
            power_absolute_differences=power_diff,
            full_FE_norms="independent DOLFINx integral measurement, no FE replay",
            saved_status_trusted=False,
        )
    return dict(
        reference_accuracy_pass=reference_pass,
        routes=checks,
        near_zero_absolute_threshold=1e-12,
        reference_feedback=False,
    )


def check_finite_differences(record):
    maxima = []
    stable = []
    for direction in record["finite_difference"]:
        errors = [
            abs(sample["finite_difference"] - direction["analytic"])
            / max(abs(direction["analytic"]), 1e-12)
            for sample in direction["samples"]
        ]
        maxima.extend(errors)
        stable.append(
            any(
                errors[i] <= 1e-5 and errors[i + 1] <= 1e-5
                for i in range(len(errors) - 1)
            )
        )
    return dict(
        pass_all_directions=all(stable),
        maximum_recomputed_relative_error=max(maxima),
        physical_operator=record["physical_operator"],
        synthetic_operator=False,
        target_solution_loaded=record["target_solution_loaded"],
    )
