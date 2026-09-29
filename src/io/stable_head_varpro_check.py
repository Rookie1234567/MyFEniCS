"""Independent V11 gate derivation from raw numeric fields, never saved status."""

import math


def finite_le(value, bound):
    return (isinstance(value, (int, float)) and math.isfinite(value)
            and 0 <= value <= bound)


def manufactured_gate(row):
    stable = row["stable"]
    return (finite_le(stable["full_rhs_residual"]["relative"], 1e-8)
            and finite_le(stable["known_z_relative"], 1e-6)
            and finite_le(stable["homogeneous_recovery_pair"], 1e-10))


def corrected_manufactured_gate(row):
    return (finite_le(row["full_rhs_residual"]["relative"], 1e-8)
            and finite_le(row["known_z_relative"], 1e-6)
            and finite_le(row["homogeneous_recovery_pair"], 1e-10))


def stable_head_gate(point, rank_A):
    return (rank_A == 1560
            and all(finite_le(point[key], 1e-8) for key in (
                "network_vs_Pgamma_trace_relative", "Pgamma_vs_Zc_trace_relative",
                "actual_vs_thin_residual_fixed_physical_b",
                "actual_stationarity_UHr_fixed_physical_b")))


def same_discrete_gate(row):
    audit = row["audit"]
    fields = row["fields"]
    comparison = row["comparison"]
    equation = all(finite_le(audit[key], 1e-6) for key in (
        "schur_relative", "native_relative", "augmented_relative",
        "original_total_augmented_relative", "port_full_rhs_relative",
        "port_operation_relative", "independent_DOLFINx_total_native_relative"))
    equation &= finite_le(audit["recovery_relative"], 1e-10)
    equation &= audit["slave_storage_max"] == 0
    fields_good = all(finite_le(fields[key], 1e-4) for key in (
        "full_FE_L2_relative", "full_FE_scaled_curl_relative",
        "scattered_FE_L2_relative", "scattered_scaled_curl_relative",
        "selected_E_relative", "selected_H_relative"))
    channels = (len(row["ordered_complex_total_ports"]) == 40
                and len(row["ordered_complex_scattered_ports"]) == 40
                and finite_le(comparison["ordered_complex_ports_relative"], 1e-4))
    differences = comparison["power_absolute_differences"]
    power = (all(finite_le(differences[key], 1e-5) for key in
                 ("R_total", "T_total", "A_balance", "A_volume"))
             and finite_le(comparison["max_channel_power_difference"], 1e-6)
             and finite_le(comparison["energy_closure_absolute"], 1e-5))
    return bool(equation and fields_good and channels and power)


def check_v11(main, replay, verify):
    initial = main["manufactured"]
    raw = {name: manufactured_gate(initial[name]) for name in ("M1", "M2")}
    corrected = {"M1": raw["M1"], "M2": corrected_manufactured_gate(replay["M2_after"])}
    physical = replay["physical_baseline"]
    rank = main["stable_basis"]["solutions"]["physical"]["rank_A"]
    head = (main["stable_basis"]["P_rank"] == 1560
            and finite_le(main["stable_basis"]["P_reassembly"], 1e-10)
            and finite_le(main["stable_basis"]["Z_orthogonality"], 1e-10)
            and finite_le(main["stable_basis"]["H_condition"], 1e10)
            and stable_head_gate(physical, rank))
    actual_fe = {name: same_discrete_gate(row) for name, row in verify["rows"].items()}
    mismatches = []
    for name, passed in raw.items():
        if passed != initial[name]["stable_gate"]:
            mismatches.append(f"MAIN.{name}.stable_gate")
    if all(corrected.values()) != replay["S1_gate"]:
        mismatches.append("REPLAY.S1_gate")
    if head != replay["S2_gate"]:
        mismatches.append("REPLAY.S2_gate")
    for name, passed in actual_fe.items():
        if passed != (verify["rows"][name]["status"] == "SAME_DISCRETE_QUALIFIED"):
            mismatches.append("VERIFY." + name + ".status")
    return {
        "status": "PASS" if not mismatches else "RAW_STATUS_MISMATCH",
        "mismatches": mismatches,
        "initial_manufactured": raw,
        "corrected_manufactured": corrected,
        "corrected_stable_head_gate": head,
        "same_discrete": actual_fe,
        "hidden_updates": replay.get("accepted_updates", 0),
        "formal_solver_qualification": bool(head and all(corrected.values()) and all(actual_fe.values())),
        "saved_statuses_not_trusted": True,
    }
