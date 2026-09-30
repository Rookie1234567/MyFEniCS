"""Frozen readout arithmetic, label, and resource audit; no projection solve."""

import csv
import json
from pathlib import Path
import sys

import numpy as np
from scipy import sparse

from benchmarks.check_task42extra_v2 import (
    ROOT,
    RECORDS,
    RESULTS,
    CHECKS,
    index,
    read,
    write,
    sha,
    resource_record,
    close,
    channel_error,
    complex_array,
)
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.feinn_gqr import GramColumns, squared_norm

ROUTE = "FEINN-FROZEN-HIDDEN-READOUT-G"
STAGES = (
    "v5_readout_checks",
    ROUTE,
    "v5_readout_reconstruct",
    "v5_readout_compare_only",
)
POLICY = dict(
    reference_used_for_training=True,
    pde_only_solve=False,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
)
OLD_SECONDS = 44119.848638203344


def policy(item):
    if any(bool(item[k]) != v for k, v in POLICY.items()):
        raise ValueError("REFERENCE_EXPOSURE_POLICY_LOST")


def resources(indices, *, version=5, old_seconds=OLD_SECONDS, batch_limit=7200, main_limit=3600, main_route=ROUTE, new_factor_counts=(0, 0, 0)):
    stages = {}
    for stage, item in indices.items():
        directory = Path(item["run_directory"])
        row = resource_record(directory)
        summary = read(directory / "run_summary.json")
        row.update(
            launch_to_summary_monotonic=summary["launch_to_summary_seconds_monotonic"],
            launch_exit_remaining_seconds=summary["launch_exit_remaining_seconds"],
        )
        row["charged_seconds"] = max(
            row["launch_to_summary_monotonic"],
            row["launch_to_summary_seconds_derived"],
            row["supervised_seconds"],
        )
        row["raw_hashes"] = {
            name: sha(directory / name)
            for name in (
                "run_manifest.json",
                "run_summary.json",
                "resource_baseline.json",
                "budget_at_launch.json",
                "input_original.dat",
                "resolved_config.json",
                "supervision/resources.jsonl",
            )
        }
        peak_rss = peak_swap = 0
        for line in (
            (directory / "supervision/resources.jsonl").read_text().splitlines()
        ):
            value = json.loads(line)
            peak_rss = max(peak_rss, value["rss_bytes"])
            peak_swap = max(peak_swap, value["swap_bytes"])
        if (
            peak_rss != row["peak_simultaneous_tree_RSS_bytes"]
            or peak_swap != row["own_tree_swap_peak_bytes"]
        ):
            raise ValueError("RESOURCE_SUMMARY_NOT_REPRODUCED")
        stages[stage] = row
    auxiliary = []
    for directory in sorted(CHECKS.glob(f"v{version}_*")):
        p = directory / "summary.json"
        if not p.exists():
            auxiliary.append(
                dict(
                    directory=str(directory),
                    status="RUNNING_OR_NO_SUMMARY",
                    charged_seconds=0,
                )
            )
            continue
        value = read(p)
        auxiliary.append(
            dict(
                directory=str(directory),
                summary_sha256=sha(p),
                classification=value["classification"],
                leader_exit_code=value["leader_exit_code"],
                charged_seconds=value["elapsed_seconds"],
                peak_simultaneous_tree_RSS_bytes=value[
                    "sampled_process_tree_rss_peak_bytes"
                ],
                own_tree_swap_peak_bytes=value["sampled_process_tree_swap_peak_bytes"],
                descendants_cleared=value["descendants_cleared"],
            )
        )
    formal = sum(x["charged_seconds"] for x in stages.values())
    aux = sum(x["charged_seconds"] for x in auxiliary)
    batch = formal + aux + 120
    samples = []
    for path in sorted(
        (ROOT / "tmp/task42extra/durable").glob(f"v{version}_*/terminal_identity.json")
    ):
        identity = read(path)
        status = {}
        for line in identity["server"]["status"].splitlines():
            if line.startswith(("VmRSS:", "VmSwap:", "Threads:")):
                key, value = line.split(":", 1)
                status[key] = int(value.split()[0]) * (1 if key == "Threads" else 1024)
        samples.append(
            dict(
                proof=str(path),
                sha256=sha(path),
                pid=identity["server"]["pid"],
                start_ticks=identity["server"]["start_ticks"],
                **status,
            )
        )
    out = dict(
        schema=f"task42extra.resource-costs.v{version}",
        previous_conservative_seconds=old_seconds,
        old_lost_attempt_charged_seconds=3284,
        V5_formal_seconds=formal,
        V5_auxiliary_seconds=aux,
        direct_current_and_final_allowance_seconds_conservative=120,
        V5_batch_seconds=batch,
        V5_remaining_seconds=batch_limit - batch,
        original_total_conservative_seconds=old_seconds + batch,
        original_16h_remaining_seconds=57600 - old_seconds - batch,
        formal_stages=stages,
        auxiliary_attempts=auxiliary,
        numerical_peak_RSS_bytes=max(
            x["peak_simultaneous_tree_RSS_bytes"] for x in stages.values()
        ),
        all_supervised_peak_RSS_bytes=max(
            x.get("peak_simultaneous_tree_RSS_bytes", 0)
            for x in [*stages.values(), *auxiliary]
        ),
        own_sampled_swap_zero=all(
            x.get("own_tree_swap_peak_bytes", 0) == 0
            for x in [*stages.values(), *auxiliary]
        ),
        management_server_launch_samples=samples,
        management_scope="own tmux servers outside numeric tree; sparse observations, not continuous peak; wall included",
        main_numeric_cutoff_monotonic=indices[main_route]["result"][
            "numeric_cutoff_monotonic"
        ],
        reserve_120s_met=stages[main_route]["launch_exit_remaining_seconds"] >= 120,
        no_continuous_kernel_cgroup_limit_claim=True,
        shared_workstation=True,
        new_Gram_factor_Gsolve_Maxwell_factor_counts=list(new_factor_counts),
        historical_Gram_and_reference_costs_preserved=True,
        timer_scope="phase walls sum; nested G/QR/SVD/storage/supervisor timers are included and never added again",
        cutoff=f"all completed own V{version} summaries plus conservative direct/current/final 120s allowance",
    )
    if (
        batch > batch_limit
        or old_seconds + batch > 57600
        or stages[main_route]["charged_seconds"] > main_limit
    ):
        raise ValueError("READOUT_CUMULATIVE_BUDGET_FAILED")
    if version != 5:
        out = {k.replace("V5_", f"V{version}_"):v for k,v in out.items()}
    write(f"resource_costs_v{version}.json", out)
    return out


def main():
    indices = {stage: index(stage)[0] for stage in STAGES}
    if "--resources-only" in sys.argv:
        resources(indices)
        return
    fit = indices[ROUTE]
    result = fit["result"]
    core = index("e1_fe")[0]
    ref_index = index("e3_reference")[0]
    old = index("FEINN-REFERENCE-FIT-G-ADAM500-REPLAY")[0]
    if len(list(RESULTS.glob("task42extra_v5_frozen_hidden_readout_*"))) != 1:
        raise ValueError("UNIQUE_READOUT_START_FAILED")
    for item in indices.values():
        policy(item["result"])
        policy(read(Path(item["run_directory"]) / "run_manifest.json"))
    if (
        result["optimizer_steps"]
        or result["optimizer_state_saved"]
        or not result["no_Gsolve"]
        or not result["no_Gram_factor"]
    ):
        raise ValueError("READOUT_ALGORITHM_SCOPE_FAILED")
    with np.load(
        indices["v5_readout_checks"]["files"]["columns"]["path"], allow_pickle=False
    ) as x:
        Phi, a0, c0 = np.array(x["Phi"]), np.array(x["a0"]), np.array(x["c0"])
    with np.load(fit["files"]["projection_arrays"]["path"], allow_pickle=False) as x:
        arrays = {k: np.array(x[k]) for k in x.files}
    with np.load(fit["files"]["checkpoint"]["path"], allow_pickle=False) as x:
        policy(x)
        c, p, a1 = np.array(x["c"]), np.array(x["parameters"]), np.array(x["a1"])
    with np.load(ref_index["files"]["reference"]["path"], allow_pickle=False) as x:
        cref = np.array(x["c"])
    G = sparse.load_npz(core["files"]["gram"]["path"])
    # FE compare-only performs exactly two CSR G-vector products. Reconstruction
    # has no G product. Reserve these two before independent projection checking.
    prior_columns = result["G_action_columns_S0_and_main"] + 2
    action = GramColumns(G, limit=2500 - prior_columns)
    GPhi = action(Phi, "independent_column_scaling")
    scales = np.sqrt(np.einsum("ij,ij->j", Phi.conj(), GPhi).real)
    if (
        not np.array_equal(scales == 0, arrays["scales"] == 0)
        or np.max(
            abs(scales[scales > 0] - arrays["scales"][scales > 0]) / scales[scales > 0]
        )
        > 1e-12
    ):
        raise ValueError("READOUT_SCALES_NOT_REPRODUCED")
    del GPhi
    perm = arrays["permutation"]
    Q, Qeff, R = arrays["Q"], arrays["Q_eff"], arrays["R"]
    GQeff = action(Qeff, "independent_effective_space")
    orth = float(np.linalg.norm(Qeff.conj().T @ GQeff - np.eye(Qeff.shape[1])))
    U = np.zeros_like(Phi)
    nz = scales > 0
    U[:, nz] = Phi[:, nz] / scales[nz]
    qr_error = U[:, perm] - Q @ R
    Gqr = action(qr_error, "independent_QR_reconstruction")
    qr_relative = float(
        np.sqrt(np.einsum("ij,ij->", qr_error.conj(), Gqr).real / Phi.shape[1])
    )
    del qr_error, Gqr
    d = cref - c0
    Gd = action(d, "independent_anchor_error")
    dref = squared_norm(cref, action(cref, "independent_reference"))
    beta = Qeff.conj().T @ Gd
    ideal_delta = Qeff @ beta
    residual = cref - c
    Gres = action(residual, "independent_actual_network_residual")
    optimal = float(np.linalg.norm(Qeff.conj().T @ Gres) / np.sqrt(dref))
    E0sq = squared_norm(d, Gd) / dref
    E1sq = squared_norm(residual, Gres) / dref
    removed = (
        squared_norm(ideal_delta, action(ideal_delta, "independent_correction")) / dref
    )
    pythagorean = abs(E0sq - E1sq - removed)
    delta = arrays["delta_a"]
    columns = c0 + Phi @ delta
    ideal = c0 + ideal_delta
    pairings = {}
    for name, other in (("columns", columns), ("ideal_projection", ideal)):
        error = c - other
        pairings[name] = dict(
            euclidean_relative=float(np.linalg.norm(error) / np.linalg.norm(other)),
            G_relative=float(
                np.sqrt(
                    squared_norm(error, action(error, "independent_writeback")) / dref
                )
            ),
        )
    if not np.array_equal(a0 + delta, a1) or array_hash(Phi) != result["Phi_sha256"]:
        raise ValueError("READOUT_WEIGHTS_OR_PHI_IDENTITY_FAILED")
    singular = arrays["singular_values"]
    keep = singular > singular[0] * 1e-12
    svd_reconstruction = float(
        np.linalg.norm(R - (arrays["left"] * singular) @ arrays["vh"])
        / np.linalg.norm(R)
    )
    if svd_reconstruction > 1e-12 or Qeff.shape[1] != sum(keep):
        raise ValueError("SMALL_R_SVD_IDENTITY_FAILED")
    stable = (
        orth <= 1e-9
        and qr_relative <= 1e-9
        and optimal <= 1e-9
        and E1sq <= E0sq + 1e-10
        and pythagorean <= 1e-8
        and all(
            x["euclidean_relative"] <= 1e-10 and x["G_relative"] <= 1e-9
            for x in pairings.values()
        )
    )
    if not stable or result["status"] != "FROZEN_HIDDEN_READOUT_COMPLETE":
        raise ValueError("READOUT_STABILITY_NOT_REPRODUCED")
    # Only task-created hash-bound checkpoint deserialization, ML environment.
    from src.solvers.optimization_checkpoint import load_checkpoint

    previous = load_checkpoint(
        old["files"]["durable_final"]["path"], old["files"]["durable_final"]["sha256"]
    )
    model = load_checkpoint(
        fit["files"]["parameter_only_model"]["path"],
        fit["files"]["parameter_only_model"]["sha256"],
    )
    policy(model["metadata"])
    if "optimizer" in model or model["metadata"]["optimizer_state_saved"]:
        raise ValueError("OLD_LBFGS_HISTORY_MIXED_WITH_READOUT")
    for name, value in model["model"].items():
        if not name.startswith("envelopes.6.") and not np.array_equal(
            value.numpy(), previous["model"][name].numpy()
        ):
            raise ValueError("READOUT_HIDDEN_OR_BUFFER_CHANGED")
    params = np.concatenate(
        [model["model"][x["name"]].numpy().ravel() for x in model["parameter_order"]]
    )
    if not np.array_equal(p, params):
        raise ValueError("NPZ_PT_PARAMETER_ORDER_MISMATCH")
    metrics = dict(
        G_orthogonality_F=orth,
        QR_G_F_relative=qr_relative,
        actual_network_optimality=optimal,
        E0_squared=E0sq,
        E1_squared=E1sq,
        correction_relative_energy=removed,
        gamma=removed / E0sq,
        pythagorean_defect=pythagorean,
        writeback=pairings,
        SVD_reconstruction_relative=svd_reconstruction,
        independent_G_columns=action.count,
        total_pipeline_G_columns=action.count + prior_columns,
        independent_G_columns_by_role=action.by_role,
        all_normalized_original_column_residual_correlations=[
            dict(real=z.real, imag=z.imag) for z in (U.conj().T @ Gres / np.sqrt(dref))
        ],
    )
    projection = dict(
        schema="task42extra.readout-projection.v5",
        source_sha=fit["source_sha"],
        raw=fit["files"]["projection"],
        Phi=indices["v5_readout_checks"]["files"]["columns"],
        computed_by_checker=metrics,
        main_projection=result["projection"],
        G_action_columns_main=result["G_action_columns_main"],
        hidden_buffers_exactly_unchanged=True,
        no_optimizer_state_for_new_parameters=True,
        **POLICY,
    )
    write("readout_projection_v5.json", projection)
    physical = indices["v5_readout_compare_only"]["result"]
    candidate = physical["physics"]["records"][ROUTE]
    reference = physical["physics"]["records"]["REFERENCE"]
    comparison = physical["comparisons"][ROUTE]
    policy(candidate)
    policy(comparison)
    if (
        physical["MUMPS_symbolic_numeric_solve_count"]
        or physical["reference_recomputed"]
        or physical["global_Maxwell_factor_created"]
    ):
        raise ValueError("COMPARE_ONLY_CREATED_A_REFERENCE_SOLVE")
    errors = comparison["errors"]
    for error in errors.values():
        if error["denominator"] <= 0 or not close(
            error["absolute"] / error["denominator"], error["relative"]
        ):
            raise ValueError("FIELD_DENOMINATOR_ARITHMETIC_FAILED")
    fields = {
        "ordered_total_channels": "ordered_complex_total_channels",
        "ordered_outgoing_channels": "ordered_complex_outgoing_channels",
        "ordered_boundary_outgoing_channels": "ordered_complex_boundary_outgoing_channels",
        "ordered_scattered_channels": "ordered_complex_scattered_channels",
    }
    channels = {
        k: channel_error(candidate, reference, v, errors[k]) for k, v in fields.items()
    }
    for key, field in dict(
        selected_total_E="selected_total_E",
        selected_total_H="selected_total_H_code",
        selected_scattered_E="selected_scattered_E",
        selected_scattered_H="selected_scattered_H_code",
    ).items():
        aa, bb = (
            np.asarray(complex_array(x[field])).reshape(6, 3)
            for x in (candidate, reference)
        )
        for suffix, a, b in [("", aa, bb)] + [
            (f"_point_{j}", aa[j], bb[j]) for j in range(6)
        ]:
            absolute = float(np.linalg.norm(a - b))
            denominator = max(float(np.linalg.norm(b)), 1e-12)
            if not close(absolute / denominator, errors[key + suffix]["relative"]):
                raise ValueError("SELECTED_COMPLEX_FIELD_ARITHMETIC_FAILED")
    power, refpower = candidate["port"], reference["port"]
    volume, refvolume = (x["volume"]["A_volume_total"] for x in (candidate, reference))
    deltas = {
        k: abs(power[k] - refpower[k]) for k in ("R_total", "T_total", "A_balance")
    }
    deltas["A_volume"] = abs(volume - refvolume)
    channelpower = float(
        np.max(
            abs(
                np.asarray(candidate["ordered_per_channel_power"])
                - np.asarray(reference["ordered_per_channel_power"])
            )
        )
    )
    energy = abs(power["R_total"] + power["T_total"] + volume - 1)
    absorption = abs(power["A_balance"] - volume)
    if not close(energy, comparison["energy_closure_absolute"]) or not close(
        channelpower, comparison["max_channel_power_absolute"]
    ):
        raise ValueError("POWER_ENERGY_ARITHMETIC_FAILED")
    audit = candidate["audit"]
    equation = (
        all(
            audit[k] <= 1e-6
            for k in (
                "native_relative",
                "augmented_relative",
                "original_total_augmented_relative",
                "port_full_rhs_relative",
                "port_operation_relative",
                "independent_DOLFINx_total_native_relative",
            )
        )
        and audit["slave_storage_max"] == 0
    )
    field = all(x["relative"] <= 1e-4 for x in errors.values())
    power_pass = (
        max(deltas.values()) <= 1e-5
        and max(energy, absorption) <= 1e-5
        and channelpower <= 1e-6
    )
    Eg = np.sqrt(E1sq)
    if not close(Eg, physical["G_field_error"]):
        raise ValueError("INDEPENDENT_FE_G_ERROR_DIFFERS")
    rec = indices["v5_readout_reconstruct"]["result"]
    quadrature = rec["q30_to_q15_relative"]
    category = (
        "QUADRATURE_DRIFT"
        if quadrature > 1e-8
        else "REPRESENTATION_WITNESS_POSITIVE"
        if max(
            Eg,
            errors["scattered_L2"]["relative"],
            errors["scattered_scaled_curl"]["relative"],
        )
        <= 1e-3
        else "PARTIAL_REPRESENTATION_WITNESS"
        if max(
            Eg,
            errors["scattered_L2"]["relative"],
            errors["scattered_scaled_curl"]["relative"],
        )
        <= 1e-2
        else "REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED"
    )
    if (
        category != physical["category"]
        or comparison["qualified"]
        or comparison["numerical_reconstruction_pass"]
        != (equation and field and power_pass)
    ):
        raise ValueError("SUPERVISED_DIAGNOSTIC_DECISION_DIFFERS")
    old_gate = read(RECORDS / "gate_decisions_v4.json")
    for name, region in physical["region_field_errors"].items():
        if (
            region["cell_ids_sha256"]
            != old_gate["region_field_errors"][name]["cell_ids_sha256"]
        ):
            raise ValueError("V4_REGION_SET_CHANGED")
    gate = dict(
        schema="task42extra.gate-decisions.v5",
        category=category,
        projection_stability_pass=stable,
        G_field_error=dict(relative=float(Eg), denominator=dref, numerator=E1sq * dref),
        q30_to_q15_relative=quadrature,
        parameter_to_saved_c_relative=rec["parameter_to_saved_c_relative"],
        numerical_equation_pass=bool(equation),
        field_reconstruction_pass=bool(field),
        power_check_pass=bool(power_pass),
        audit=audit,
        errors=errors,
        channels=channels,
        region_field_errors=physical["region_field_errors"],
        energy_closure_absolute=energy,
        absorption_balance_volume_absolute=absorption,
        max_channel_power_absolute=channelpower,
        power_differences=deltas,
        raw_physics=physical["physics"],
        representation_positive=category == "REPRESENTATION_WITNESS_POSITIVE",
        representation_partial=category == "PARTIAL_REPRESENTATION_WITNESS",
        neural_increment="NOT_DEMONSTRATED_REFERENCE_EXPOSED_DIAGNOSTIC",
        total_G_action_columns=metrics["total_pipeline_G_columns"],
        unique_main_starts=1,
        **POLICY,
    )
    write("gate_decisions_v5.json", gate)
    checks = read(RECORDS / "readout_checks_v5.json")
    checks.update(
        real_M5_status="FROZEN_READOUT_CHECKS_PASS",
        actual_source_sha=indices["v5_readout_checks"]["source_sha"],
        raw_index=str(index("v5_readout_checks")[1]),
        raw_index_sha256=sha(index("v5_readout_checks")[1]),
        real_result=indices["v5_readout_checks"]["result"],
    )
    write("readout_checks_v5.json", checks)
    rows = []
    for name, g in (("V4_COMMITTED_FINAL", old_gate), (ROUTE, gate)):
        raw_candidate = (
            candidate
            if name == ROUTE
            else index("v4_fit_compare_only")[0]["result"]["physics"]["records"][
                "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"
            ]
        )
        rows.append(
            dict(
                route=name,
                category=g["category"],
                G_field_error=g["G_field_error"]["relative"],
                scattered_E_L2=g["errors"]["scattered_L2"]["relative"],
                scattered_scaled_curl=g["errors"]["scattered_scaled_curl"]["relative"],
                total_E_L2=g["errors"]["total_L2"]["relative"],
                total_scaled_curl=g["errors"]["total_scaled_curl"]["relative"],
                native=g["audit"]["native_relative"],
                augmented=g["audit"]["augmented_relative"],
                R=raw_candidate["port"]["R_total"],
                T=raw_candidate["port"]["T_total"],
                A_balance=raw_candidate["port"]["A_balance"],
                A_volume=raw_candidate["volume"]["A_volume_total"],
                energy_closure_abs=g["energy_closure_absolute"],
                max_channel_power_abs=g["max_channel_power_absolute"],
                **POLICY,
            )
        )
    with (RECORDS / "readout_comparison_v5.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write(
        "run_index_v5.json",
        dict(
            schema="task42extra.run-index.v5",
            stages={
                k: dict(
                    source_sha=v["source_sha"],
                    run_directory=v["run_directory"],
                    files=v["files"],
                    index_sha256=sha(index(k)[1]),
                )
                for k, v in indices.items()
            },
            main_start_count=1,
            source_is_documentation_HEAD=False,
            **POLICY,
        ),
    )
    resource = resources(indices)
    print(
        json.dumps(
            dict(
                status="INDEPENDENT_V5_AUDIT_COMPLETE",
                category=category,
                E_G=float(Eg),
                gamma=metrics["gamma"],
                G_columns=metrics["total_pipeline_G_columns"],
                batch_seconds=resource["V5_batch_seconds"],
            )
        )
    )


if __name__ == "__main__":
    main()
