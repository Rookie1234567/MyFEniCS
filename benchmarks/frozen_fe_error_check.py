"""Independent compact/raw checks; no FE imports, factor, action or new solve."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def relative_difference(left, right):
    scale = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)))
    absolute = float(np.linalg.norm(left - right))
    return absolute / scale if scale > 1e-12 else absolute


def square_sum_check(left, right):
    """Operation scale is the terms before cancellation, never their small sum."""
    cross = np.vdot(left, right)
    terms = np.linalg.norm(left) ** 2 + np.linalg.norm(right) ** 2
    squared = terms + 2 * cross.real
    absolute = float(abs(squared - np.linalg.norm(left + right) ** 2))
    scale = float(terms + 2 * abs(cross))
    return dict(
        absolute=absolute,
        operation_scale=scale,
        operation_relative=absolute / scale if scale > 1e-12 else absolute,
    )


def check_report(report, raw):
    checks = {}
    square_details = {}
    audits = report["audits"]
    for name, audit in audits.items():
        checks[name + ".r=b-Sz"] = relative_difference(
            raw[name + ".r"], raw["b"] - raw[name + ".Sz"]
        )
        for key, field, denominator in (
            ("schur", "r", "schur_rhs_norm"),
            ("native", "native", "native_rhs_norm"),
            ("total_augmented", "total_residual", "total_rhs_norm"),
        ):
            norm = float(np.linalg.norm(raw[name + "." + field]))
            checks[name + "." + key + "_absolute_recomputed"] = relative_difference(
                np.array([norm]), np.array([audit[key + "_absolute"]])
            )
            checks[name + "." + key + "_relative_recomputed"] = relative_difference(
                np.array([norm / audit[denominator]]),
                np.array([audit[key + "_relative"]]),
            )
        augmented = np.r_[raw[name + ".rfe"], raw[name + ".rp"]]
        port_norm = float(np.linalg.norm(raw[name + ".rp"]))
        for key, actual in (
            (
                "augmented_relative",
                np.linalg.norm(augmented) / audit["augmented_rhs_norm"],
            ),
            (
                "port_operation_relative",
                port_norm / audit["port_operation_scale"]
                if audit["port_operation_scale"] > 1e-12
                else port_norm,
            ),
            (
                "recovery_relative",
                np.linalg.norm(raw[name + ".rfe"][raw["idofs"]])
                / audit["augmented_rhs_norm"],
            ),
        ):
            checks[name + "." + key + "_recomputed"] = relative_difference(
                np.array([actual]), np.array([audit[key]])
            )
        injected = np.zeros_like(raw[name + ".rfe"])
        injected[raw["masters"]] = raw[name + ".r"][: report["trace_rows"]]
        checks[name + ".Schur_body"] = relative_difference(injected, raw[name + ".rfe"])
        checks[name + ".Schur_port"] = relative_difference(
            raw[name + ".r"][report["trace_rows"] :], raw[name + ".rp"]
        )
    if "REF7" in audits:
        ref = audits["REF7"]
        reference_pass = all(
            ref[key] <= 1e-10
            for key in (
                "schur_relative",
                "native_relative",
                "augmented_relative",
                "total_augmented_relative",
                "port_operation_relative",
                "recovery_relative",
            )
        )
    else:
        reference_pass = False
    for name in report.get("errors", {}):
        key = name + ".error."
        checks[name + ".e=zref-z"] = relative_difference(
            raw[key + "e"], raw["REF7.z"] - raw[name + ".z"]
        )
        checks[name + ".Se=r-rref"] = relative_difference(
            raw[key + "Se"], raw[name + ".r"] - raw["REF7.r"]
        )
        checks[name + ".homogeneous_recovery"] = relative_difference(
            raw[key + "homogeneous"], raw["REF7.field"] - raw[name + ".field"]
        )
        checks[name + ".F(e)-F(0)"] = relative_difference(
            raw[key + "default_error"] - raw["Z0.field"], raw[key + "delta"]
        )
        a, c, d, h = (raw[key + part] for part in ("a", "c", "d", "h"))
        aug = np.r_[a + c, -d + h]
        target = np.r_[
            raw[name + ".rfe"] - raw["REF7.rfe"], raw[name + ".rp"] - raw["REF7.rp"]
        ]
        checks[name + ".original_augmented"] = relative_difference(aug, target)
        checks[name + ".native"] = relative_difference(
            a + raw[key + "native_port"], raw[name + ".native"] - raw["REF7.native"]
        )
        checks[name + ".Hp_is_original"] = relative_difference(
            h, raw["Hp"] @ raw[key + "e"][report["trace_rows"] :]
        )
        for category, left, right in (
            ("body", a, c),
            ("port", -d, h),
            ("native", a, raw[key + "native_port"]),
        ):
            row = report["errors"][name][category]
            cross = np.vdot(left, right)
            checks[name + "." + category + ".cross"] = relative_difference(
                np.array([cross.real, cross.imag]),
                np.array([row["cross_real"], row["cross_imag"]]),
            )
            square_key = name + "." + category + ".squares"
            square_details[square_key] = square_sum_check(left, right)
            checks[square_key] = square_details[square_key]["operation_relative"]
    field = report.get("fields")
    if field:
        for row in field["fields"]:
            name = row["state"]
            if name == "REF7":
                continue
            regions = [r for r in field["regions"] if r["state"] == name]
            for quantity in ("L2", "curl_scaled"):
                values = sum(r["error_" + quantity + "_squared"] for r in regions)
                checks[name + ".regions." + quantity] = relative_difference(
                    np.array([values]),
                    np.array([row["error_" + quantity + "_squared"]]),
                )
            expanded = (
                row["trace_field_L2_squared"]
                + row["internal_field_L2_squared"]
                + 2 * row["trace_internal_cross_real"]
            )
            checks[name + ".field_cross"] = relative_difference(
                np.array([expanded]), np.array([row["error_L2_squared"]])
            )
            checks[name + ".field_L2_coefficient_independent"] = relative_difference(
                np.array([np.linalg.norm(raw[name + ".field"])]),
                np.array([row["coefficient_l2"]]),
            )
            for value in field["consistency"][name].values():
                if isinstance(value, dict):
                    checks[name + ".FE_consistency." + str(len(checks))] = value[
                        "operation_relative"
                    ]
            checks[name + ".FE_homogeneous"] = field["consistency"][name][
                "homogeneous_field_relative"
            ]
        for name, value in field["mpc_checks"].items():
            checks[name + ".actual_MPC"] = value["operation_relative"]
        if field["region_counts"] != dict(
            air_excluding_notch=192, notch_air=8, substrate=48, Si_block=136
        ):
            checks["region_inventory"] = 1.0
    finite = all(np.isfinite(value) for value in checks.values())
    identities_pass = finite and all(value <= 1e-10 for value in checks.values())
    calls = report["action_counts"]
    bounded = calls["S"] + calls["SH"] <= 128 and all(
        calls[k] <= 128 for k in ("recover", "uncondensed", "Hp_audit")
    )
    complete = (
        len(audits) == 6
        and reference_pass
        and len(report.get("errors", {})) == 5
        and field is not None
    )
    return dict(
        status="FIXED_ERROR_DIAGNOSTIC_COMPLETE"
        if complete and identities_pass and bounded
        else "PARTIAL"
        if identities_pass and bounded
        else "DIAGNOSTIC_SELF_CHECK_FAILED",
        independent_checks=checks,
        square_identity_absolute_and_operation_scales=square_details,
        max_operation_scaled_defect=max(checks.values(), default=0),
        identities_pass=identities_pass,
        reference_original_equations_pass=reference_pass,
        action_budget_pass=bounded,
        usable_states=len(audits),
        solver_pass=False,
        new_solve=False,
        reference_role="offline fixed-error diagnostic only",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    with Path(report["raw_vectors"]["path"]).open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual_hash != report["raw_vectors"]["sha256"]:
        raise ValueError("frozen diagnostic raw NPZ hash differs")
    with np.load(report["raw_vectors"]["path"], allow_pickle=False) as raw:
        record = check_report(report, raw)
    args.output.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                k: record[k]
                for k in (
                    "status",
                    "usable_states",
                    "max_operation_scaled_defect",
                    "solver_pass",
                )
            }
        )
    )
    return 0 if record["identities_pass"] and record["action_budget_pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
