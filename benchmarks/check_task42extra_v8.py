"""V8 frozen-record arithmetic and provenance checks; never run a solver."""

import csv
import json
import os
from pathlib import Path
import sys

import numpy as np

from benchmarks.check_task42extra_v2 import (
    ROOT,
    ARTIFACTS,
    RECORDS,
    RESULTS,
    CHECKS,
    read,
    write,
    sha,
    index,
    close,
    complex_array,
    channel_error,
    resource_record,
)
from benchmarks.check_task42extra_v7 import comparison_gate, reference_gate
from src.runners.feinn_campaign import STAGES, LIMITS, OLD_SECONDS, REVIEW_SHA

INIT = "11d8cd454281fab85cfc59f04cee6aa7b864157d9f98513830947a0223d64103"
LABEL = "0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7"
TRAIN = (
    "v8_plain_dual",
    "v8_phase_dual",
    "v8_plain_reference_fit",
    "v8_phase_reference_fit",
)
CHANNELS = {
    "ordered_total_channels": "ordered_complex_total_channels",
    "ordered_outgoing_channels": "ordered_complex_outgoing_channels",
    "ordered_boundary_outgoing_channels": "ordered_complex_boundary_outgoing_channels",
    "ordered_scattered_channels": "ordered_complex_scattered_channels",
}


def require(condition, name):
    if not condition:
        raise ValueError(name)


def vector(value):
    return np.asarray(complex_array(value), dtype=np.complex128)


def pair(raw, absolute, denominator):
    require(
        denominator > 0 and np.isfinite([absolute, denominator]).all(), "INVALID_PAIR"
    )
    for key, value in dict(
        absolute=absolute, denominator=denominator, relative=absolute / denominator
    ).items():
        require(
            abs(raw[key] - value)
            <= 2e-10 * max(abs(raw[key]), abs(value), np.finfo(float).tiny),
            "ERROR_PAIR_ARITHMETIC_" + key,
        )
    return dict(
        absolute=absolute, denominator=denominator, relative=absolute / denominator
    )


def physical_gate(row, candidate, reference, *, supervised, natural_scale):
    """Use raw complex observables and norm/energy fields, not a saved pass flag."""
    comp, errors = row["comparisons"], row["comparisons"]["errors"]
    recomputed = {}
    for name, raw in errors.items():
        recomputed[name] = pair(raw, raw["absolute"], raw["denominator"])
    for kind in ("total", "scattered"):
        norms = reference[kind + "_L2_scaled_curl_norms"]
        for j, quantity in enumerate(("L2", "scaled_curl")):
            name = kind + "_" + quantity
            recomputed[name] = pair(
                errors[name],
                errors[name]["absolute"],
                max(norms[j], 1e-12 * natural_scale),
            )
        for quantity, field in (("E", "E"), ("H", "H_code")):
            name = "selected_" + kind + "_" + quantity
            a, b = (
                vector(x["selected_" + kind + "_" + field]).reshape(6, 3)
                for x in (candidate, reference)
            )
            for suffix, aa, bb in [
                ("", a, b),
                *[("_point_" + str(j), a[j], b[j]) for j in range(6)],
            ]:
                recomputed[name + suffix] = pair(
                    errors[name + suffix],
                    float(np.linalg.norm(aa - bb)),
                    max(float(np.linalg.norm(bb)), 1e-12),
                )
    for name, field in CHANNELS.items():
        checked = channel_error(candidate, reference, field, errors[name])
        recomputed[name] = pair(
            errors[name], checked["absolute"], checked["denominator"]
        )
    power, refpower = candidate["port"], reference["port"]
    volume = candidate["volume"]["A_volume_total"]
    refvolume = reference["volume"]["A_volume_total"]
    deltas = {
        key: abs(power[key] - refpower[key])
        for key in ("R_total", "T_total", "A_balance")
    }
    deltas["A_volume"] = abs(volume - refvolume)
    for key, value in deltas.items():
        require(
            close(value, comp["power_absolute_differences"][key]), "POWER_DELTA_CHANGED"
        )
    a, b = (np.asarray(x["ordered_per_channel_power"]) for x in (candidate, reference))
    require(a.shape == b.shape == (40,), "POWER_INVENTORY_INCOMPLETE")
    maxpower = float(np.max(abs(a - b)))
    energy = abs(power["R_total"] + power["T_total"] + volume - 1)
    absorption = abs(power["A_balance"] - volume)
    for key, value in dict(
        max_channel_power_absolute=maxpower,
        energy_closure_absolute=energy,
        absorption_balance_volume_absolute=absorption,
    ).items():
        require(close(comp[key], value), "POWER_CLOSURE_ARITHMETIC_CHANGED")
    audit = candidate["audit"]
    eqkeys = (
        "native_relative",
        "augmented_relative",
        "original_total_augmented_relative",
        "port_full_rhs_relative",
        "port_operation_relative",
        "independent_DOLFINx_total_native_relative",
    )
    equation = (
        all(audit[key] <= 1e-6 for key in eqkeys) and audit["slave_storage_max"] == 0
    )
    field = all(value["relative"] <= 1e-4 for value in recomputed.values())
    powerpass = (
        max(deltas.values()) <= 1e-5
        and max(energy, absorption) <= 1e-5
        and maxpower <= 1e-6
    )
    refaudit = reference["audit"]
    refpass = (
        max(
            refaudit[key]
            for key in (
                "native_relative",
                "augmented_relative",
                "independent_DOLFINx_total_native_relative",
            )
        )
        <= 1e-10
    )
    refpass &= abs(refpower["R_total"] + refpower["T_total"] + refvolume - 1) <= 1e-5
    refpass &= abs(refpower["A_balance"] - refvolume) <= 1e-5
    numeric = bool(equation and field and powerpass and refpass)
    require(
        numeric == comp["numerical_reconstruction_pass"], "SAVED_NUMERICAL_GATE_DIFFERS"
    )
    eg = row["G_field_error"]
    if "G_error_energy" in row:
        eg = float(np.sqrt(row["G_error_energy"] / row["G_reference_energy"]))
        require(close(eg, row["G_field_error"]), "G_FIELD_ERROR_CHANGED")
    identity = row["norm_identity"]
    physical = identity["L2_energy"] + identity["weighted_scaled_curl_energy"]
    require(close(physical, identity["physical_energy"]), "G_L2_CURL_SUM_CHANGED")
    expected = (
        errors["scattered_L2"]["absolute"] ** 2
        + (2 * np.pi) ** 2 * errors["scattered_scaled_curl"]["absolute"] ** 2
    )
    require(close(expected, physical), "G_L2_CURL_SCALING_CHANGED")
    normdefect = abs(identity["G_energy"] - physical) / max(
        identity["G_energy"], physical, 1e-30
    )
    require(
        close(normdefect, identity["relative"]) and normdefect <= 1e-10,
        "G_NORM_IDENTITY_FAILED",
    )
    if "reconstruction" in row:
        reconstruction = row["reconstruction"]
        nextq = reconstruction["next_quadrature_to_selected"]["relative"]
        require(
            reconstruction["parameters_to_saved_c"]["relative"] <= 1e-12,
            "REAL_NETWORK_RECONSTRUCTION_FAILED",
        )
        numerical = numeric and nextq <= 1e-8
        qualified = numerical and not supervised
        require(
            qualified
            == row["pde_only_solver_qualified"]
            == row["official_candidate_results"],
            "LABEL_POLICY_OR_SOLVER_GATE_CHANGED",
        )
        require(
            row["reference_used_for_training"]
            == row["features_reference_exposed"]
            == supervised,
            "REFERENCE_BOUNDARY_CHANGED",
        )
        require(
            row["pde_only_solve"] != supervised
            and row["production_initialization_allowed"] is False,
            "PRODUCTION_BOUNDARY_CHANGED",
        )
        threshold = max(
            eg,
            errors["scattered_L2"]["relative"],
            errors["scattered_scaled_curl"]["relative"],
        )
        category = (
            "QUADRATURE_DRIFT"
            if nextq > 1e-8
            else (
                "REPRESENTATION_WITNESS_POSITIVE"
                if threshold <= 1e-3
                else "PARTIAL_REPRESENTATION_WITNESS"
                if threshold <= 1e-2
                else "REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED"
            )
            if supervised
            else "PDE_ONLY_SAME_P3_DISCRETE_PASS"
            if qualified
            else "PDE_OPTIMIZATION_NEGATIVE"
        )
        require(category == row["category"], "SAVED_CATEGORY_DIFFERS")
    else:
        nextq, qualified, category = None, False, "ADAM500_SHARED_WORK_POINT"
    return dict(
        category=category,
        pde_only_solver_qualified=qualified,
        numerical_reconstruction_pass=numeric,
        equation_pass=equation,
        field_pass=field,
        power_pass=powerpass,
        reference_pass=refpass,
        G_field_error=eg,
        errors=recomputed,
        equation_audit=audit,
        power_absolute_differences=deltas,
        max_channel_power_absolute=maxpower,
        energy_closure_absolute=energy,
        absorption_balance_volume_absolute=absorption,
        norm_identity_relative=normdefect,
        next_quadrature_relative=nextq,
        failed_fields={k: v for k, v in recomputed.items() if v["relative"] > 1e-4},
        failed_equations={k: audit[k] for k in eqkeys if audit[k] > 1e-6},
        failed_power={k: v for k, v in deltas.items() if v > 1e-5},
    )


def training_gate(item, *, supervised):
    result = item["result"]
    require(
        result["initial_parameters_sha256"] == INIT,
        "NOT_IDENTICAL_FIXED_SEED_ZERO_START",
    )
    require(result["consistent_optimizer_state_saved"], "NO_MATCHED_OPTIMIZER_STATE")
    require(
        result["reference_used_for_training"]
        == result["features_reference_exposed"]
        == supervised,
        "TRAIN_LABEL_BOUNDARY_CHANGED",
    )
    require(
        result["pde_only_solve"] != supervised
        and not result["production_initialization_allowed"],
        "TRAIN_PDE_POLICY_CHANGED",
    )
    require(
        not result["Maxwell_factor_created"]
        and not result["global_Maxwell_matrix_created"],
        "MAXWELL_TRAINING_FALLBACK",
    )
    actual = set(result["actual_artifact_reads"])
    allowed = set(result["training_data_read_whitelist"])
    require(actual <= allowed, "READ_OUTSIDE_TRAINING_WHITELIST")
    if not supervised:
        require(
            result["label_identity"] is None
            and not any("reference_state" in x for x in actual),
            "C_READ_LABELS",
        )
        factor = result["Gram_factor"]
        require(
            factor["label"] == "RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR"
            and factor["max_solve_true_relative"] <= 1e-11,
            "GRAM_NOT_QUALIFIED_OR_UNCHARGED",
        )
        require(
            factor["rss_after_release_bytes"] < factor["rss_before_release_bytes"],
            "GRAM_RELEASE_NOT_PROVEN",
        )
    else:
        require(
            result["Gram_factor"] is None and result["Gsolve_count"] == 0,
            "D_USES_GSOLVE_OR_FACTOR",
        )
        require(
            result["native_action_counts"]["A"]
            == result["native_action_counts"]["AH"]
            == 0,
            "FIT_CLOSURE_USES_A_OR_AH",
        )
        require(
            result["label_identity"]["reference_state"]["sha256"] == LABEL,
            "D_LABEL_CHANGED",
        )
        interface = result["fit_interface"]
        require(
            max(x["relative"] for x in interface["batch"].values()) <= 1e-10,
            "FIT_BATCH_QUALIFICATION_FAILED",
        )
        require(len(interface["directions"]) == 3, "FIT_NONZERO_DIRECTIONS_MISSING")
        for direction in interface["directions"]:
            samples = direction["samples"]
            require(
                all(abs(x["analytic"]) > 1e-10 for x in samples),
                "FIT_ZERO_DIRECTIONAL_DERIVATIVE",
            )
            defects = [
                abs(x["analytic"] - x["observed"]) / abs(x["analytic"]) for x in samples
            ]
            require(
                any(
                    defects[j] <= 1e-5 and defects[j + 1] <= 1e-5
                    for j in range(len(defects) - 1)
                ),
                "FIT_DIRECTIONAL_GRADIENT_FAILED",
            )
    count = result["counts"]["complete_closures"]
    require(count <= (1500 if supervised else 4000), "CLOSURE_BUDGET_EXCEEDED")
    durable = result["final_checkpoint"]
    require(
        durable["sha256"] == item["files"]["durable_final"]["sha256"],
        "DURABLE_FINAL_HASH_CHANGED",
    )
    require(
        durable["metadata"]["committed_complete_closures"] <= count,
        "COMMITTED_AND_CHARGED_CONFUSED",
    )
    return {
        k: result[k]
        for k in (
            "route",
            "stop_reason",
            "failure",
            "counts",
            "final_audit",
            "initial_parameters_sha256",
            "final_c_sha256",
            "final_parameters_sha256",
            "buffers_sha256",
            "final_checkpoint",
            "consistent_optimizer_state_saved",
            "training_data_read_whitelist",
            "actual_artifact_reads",
            "label_identity",
            "fit_interface",
            "Gram_factor",
            "Gsolve_count",
            "G_matvec_count",
            "native_action_counts",
            "native_action_costs",
            "moment_counts",
            "moment_costs",
            "timers",
            "timer_scope",
            "wall_seconds",
            "launcher_charged_seconds",
            "reference_used_for_training",
            "features_reference_exposed",
            "pde_only_solve",
            "benchmark_previously_seen",
            "production_initialization_allowed",
        )
    }


def phase_gate(fe, ml):
    for key in ("independent_phase", "synthetic_nonunit_Floquet"):
        row = fe[key]
        require(
            max(
                row[x]
                for x in (
                    "independent_64_node_Legendre_relative",
                    "custom_DOLFINx_relative",
                    "mpc_full_storage_relative",
                )
            )
            <= 1e-10,
            "PHASE_INDEPENDENT_MOMENTS_FAILED",
        )
        require(
            set(row["families"]) == {"edge", "face", "interior"},
            "INCOMPLETE_FE_FAMILIES",
        )
        require(
            all(
                x["norm"] > 0 and x["relative"] <= 1e-10
                for x in row["families"].values()
            ),
            "PHASE_FAMILY_FAILED",
        )
    require(
        fe["synthetic_nonunit_Floquet"]["nonunit_distance"] > 0.1,
        "NO_NONUNIT_FLOQUET_WITNESS",
    )
    require(
        fe["full_independent_complex_FE"] == 31968
        and fe["volume_and_DtN_degree"] == 15,
        "M5_DISCRETE_CHANGED",
    )
    require(
        ml["initial_parameters_sha256"] == INIT and ml["initial_zero_scattered"],
        "INITIAL_ZERO_NOT_QUALIFIED",
    )
    require(ml["k_zero"]["relative"] <= 1e-10, "K_ZERO_REGRESSION_FAILED")
    for row in ml["gradients"].values():
        require(
            max(x["relative"] for x in row["batch"].values()) <= 1e-10,
            "BATCH_PAIR_FAILED",
        )
        require(
            len(row["directional_derivatives"]) == 3, "MISSING_NONZERO_REAL_DIRECTIONS"
        )
        for direction in row["directional_derivatives"]:
            samples = direction["samples"]
            require(
                all(abs(x["analytic"]) > 1e-10 for x in samples),
                "ZERO_DIRECTIONAL_DERIVATIVE",
            )
            defects = [
                abs(x["analytic"] - x["observed"]) / abs(x["analytic"]) for x in samples
            ]
            require(
                all(
                    close(x["relative"], d)
                    for x, d in zip(samples, defects, strict=True)
                ),
                "DIRECTIONAL_ARITHMETIC_CHANGED",
            )
            require(
                any(
                    defects[j] <= 1e-5 and defects[j + 1] <= 1e-5
                    for j in range(len(defects) - 1)
                ),
                "NONZERO_VJP_FAILED",
            )
    q = ml["network_quadrature_degree"]
    pairname = "q15_q30" if q == 15 else "q30_q60"
    require(
        q in (15, 30)
        and all(row[pairname]["relative"] <= 1e-8 for row in ml["quadrature"].values()),
        "SHARED_QUADRATURE_UNQUALIFIED",
    )
    return dict(qualified=True, selected_shared_network_quadrature=q, FE=fe, ML=ml)


def own_pending_light(directory):
    """Defer only this checker's live supervisor; other missing summaries fail."""
    ancestors = set()
    pid = os.getpid()
    while pid > 0 and pid not in ancestors:
        ancestors.add(pid)
        status = Path(f"/proc/{pid}/status").read_text()
        pid = int(
            next(
                line.split()[1]
                for line in status.splitlines()
                if line.startswith("PPid:")
            )
        )
    path = directory / "supervision/resources.jsonl"
    with path.open() as stream:
        sample = json.loads(next(stream))
        for line in stream:
            if line.strip():
                sample = json.loads(line)
    require(sample["root_pid"] in ancestors, "INCOMPLETE_OTHER_LIGHT_TREE")
    require(
        sample["rss_bytes"] <= 2 * 2**30 and sample["swap_bytes"] == 0,
        "CURRENT_LIGHT_RESOURCE_FAILED",
    )
    return dict(
        directory=str(directory),
        status="OWN_CURRENT_LIGHT_SUMMARY_PENDING",
        root_pid=sample["root_pid"],
        current_sample_RSS_bytes=sample["rss_bytes"],
        current_sample_swap_bytes=sample["swap_bytes"],
        accounting="covered by conservative current/final allowance; next closed refresh charges actual wall",
    )


def resource_costs(indices):
    formal, groups, auxiliary = {}, dict.fromkeys(LIMITS, 0.0), []
    own_pending = []
    for directory in sorted(RESULTS.glob("task42extra_v8_*")):
        if not (directory / "run_summary.json").exists():
            raise ValueError("ACTIVE_OR_MISSING_V8_RUN_SUMMARY: " + directory.name)
        manifest, summary = (
            read(directory / name) for name in ("run_manifest.json", "run_summary.json")
        )
        stage = manifest["stage"]
        baseline = read(directory / "resource_baseline.json")
        memory = baseline["memory"]
        require(
            memory["neighbor_growth_allowance_bytes"] >= 384 * 2**30,
            "NEIGHBOR_GROWTH_RESERVE_MISSING",
        )
        require(
            memory["system_reserve_bytes"]
            >= max(128 * 2**30, memory["effective_total_bytes"] / 10),
            "SYSTEM_RESERVE_MISSING",
        )
        require(
            memory["effective_available_bytes"]
            >= memory["reserve_bytes"] + memory["launch_cap_bytes"]
            and baseline["disk_free_bytes"] >= 50 * 2**30,
            "ADMISSION_CAPACITY_NOT_MET",
        )
        row = resource_record(directory)
        charged = max(
            summary["launch_to_summary_seconds_monotonic"],
            row["launch_to_summary_seconds_derived"],
            row["supervised_seconds"],
        )
        row.update(
            charged_seconds=charged,
            launch_exit_remaining_seconds=summary["launch_exit_remaining_seconds"],
            index_published=stage in indices,
        )
        row["admission_memory"] = memory
        row["shared_workstation_identity"] = baseline["performance_identity"]
        peak = swap = 0
        with (directory / "supervision/resources.jsonl").open() as stream:
            for line in stream:
                sample = json.loads(line)
                peak, swap = (
                    max(peak, sample["rss_bytes"]),
                    max(swap, sample["swap_bytes"]),
                )
        require(
            peak == row["peak_simultaneous_tree_RSS_bytes"]
            and swap == row["own_tree_swap_peak_bytes"],
            "RESOURCE_PEAK_NOT_REPRODUCED",
        )
        require(
            swap == 0 and peak <= 16 * 2**30 and row["descendants_cleared"],
            "NUMERIC_RESOURCE_OR_CLEAR_FAILED",
        )
        require(
            manifest["mpi_size"] == manifest["math_threads"] == 1,
            "THREAD_OR_MPI_BUDGET_CHANGED",
        )
        require(charged <= STAGES[stage][1], "FORMAL_STAGE_WALL_EXCEEDED")
        groups[STAGES[stage][2]] += charged
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
        formal[directory.name] = row
    for directory in sorted(CHECKS.glob("v8_*")):
        if not (directory / "summary.json").exists():
            own_pending.append(own_pending_light(directory))
            continue
        value = read(directory / "summary.json")
        group = directory.name[3:4].upper()
        group = group if group in LIMITS else "E"
        row = dict(
            directory=str(directory),
            summary_sha256=sha(directory / "summary.json"),
            classification=value["classification"],
            leader_exit_code=value["leader_exit_code"],
            charged_seconds=value["elapsed_seconds"],
            peak_simultaneous_tree_RSS_bytes=value[
                "sampled_process_tree_rss_peak_bytes"
            ],
            own_tree_swap_peak_bytes=value["sampled_process_tree_swap_peak_bytes"],
            descendants_cleared=value["descendants_cleared"],
            group=group,
        )
        require(
            row["own_tree_swap_peak_bytes"] == 0
            and row["peak_simultaneous_tree_RSS_bytes"] <= 2 * 2**30
            and row["descendants_cleared"],
            "LIGHT_RESOURCE_OR_CLEAR_FAILED",
        )
        groups[group] += row["charged_seconds"]
        auxiliary.append(row)
    formal_seconds = sum(x["charged_seconds"] for x in formal.values())
    auxiliary_seconds = sum(x["charged_seconds"] for x in auxiliary)
    total = formal_seconds + auxiliary_seconds + 120
    groups["E"] += 120
    require(
        total <= 43200 and all(groups[k] <= LIMITS[k] for k in groups),
        "V8_CAMPAIGN_BUDGET_EXCEEDED",
    )
    servers = []
    for path in sorted(
        (ROOT / "tmp/task42extra/durable").glob("v8_*/terminal_identity.json")
    ):
        value = read(path)["server"]
        server = dict(
            proof=str(path),
            sha256=sha(path),
            pid=value["pid"],
            start_ticks=value["start_ticks"],
        )
        for line in value["status"].splitlines():
            if line.startswith(("VmRSS:", "VmSwap:", "Threads:")):
                key, val = line.split(":", 1)
                server[key] = int(val.split()[0]) * (1 if key == "Threads" else 1024)
        servers.append(server)
    out = dict(
        schema="task42extra.resource-costs.v8",
        previous_conservative_seconds=OLD_SECONDS,
        old_lost_attempt_charged_seconds=3284,
        V8_formal_seconds=formal_seconds,
        V8_auxiliary_seconds=auxiliary_seconds,
        direct_current_and_final_allowance_seconds_conservative=120,
        V8_batch_seconds=total,
        V8_remaining_seconds=43200 - total,
        original_total_conservative_seconds=OLD_SECONDS + total,
        original_16h_applies_to_V8=False,
        group_seconds=groups,
        group_limits_seconds=LIMITS,
        formal_stages=formal,
        auxiliary_attempts=auxiliary,
        own_current_light_summary_pending=own_pending,
        numerical_peak_RSS_bytes=max(
            x["peak_simultaneous_tree_RSS_bytes"] for x in formal.values()
        ),
        all_supervised_peak_RSS_bytes=max(
            x["peak_simultaneous_tree_RSS_bytes"]
            for x in [*formal.values(), *auxiliary]
        ),
        own_sampled_swap_zero=True,
        no_continuous_kernel_cgroup_limit_claim=True,
        shared_workstation=True,
        management_server_launch_samples=servers,
        management_scope="own tmux servers outside numeric tree; launch snapshots, not continuous peak; wall included",
        timer_scope="disjoint stage walls; nested closure/G/IO timers included, never added again",
        historical_Gram_and_reference_costs_preserved=True,
        old_interruption_and_replay_costs_preserved=True,
    )
    write("resource_costs_v8.json", out)
    return out


def common_work_points(left, right):
    """Latest persisted audit before a common wall cap; no best-state selection."""

    def retained(result):
        return [row for row in result["audits"] if "checkpoint" in row]

    lrows, rrows = retained(left), retained(right)

    def compact(row):
        metadata = row["checkpoint"]["metadata"]
        return dict(
            complete_closures=row["complete_closures"],
            committed_complete_closures=row["committed_complete_closures"],
            boundary_elapsed_seconds=metadata["elapsed_charged_seconds"],
            checkpoint_sha256=row["checkpoint"]["sha256"],
            native_relative=row["native_relative"],
            augmented_relative=row["augmented_relative"],
            loss=row["loss"],
            G_field_error=row.get("E_G"),
            field_physics_at_this_wall_point="NOT_RUN",
            used_for_initialization=False,
        )

    lm = {
        row["complete_closures"]: row
        for row in lrows
        if row["committed_complete_closures"] == row["complete_closures"]
    }
    rm = {
        row["complete_closures"]: row
        for row in rrows
        if row["committed_complete_closures"] == row["complete_closures"]
    }
    common = {
        str(n): dict(plain=compact(lm[n]), phase=compact(rm[n]))
        for n in sorted(lm.keys() & rm.keys())
    }
    cap = min(left["launcher_charged_seconds"], right["launcher_charged_seconds"])
    selected = {}
    for name, rows in (("plain", lrows), ("phase", rrows)):
        eligible = [
            row
            for row in rows
            if row["checkpoint"]["metadata"]["elapsed_charged_seconds"] <= cap
        ]
        row = max(
            eligible,
            key=lambda x: x["checkpoint"]["metadata"]["elapsed_charged_seconds"],
        )
        selected[name] = dict(
            compact(row),
            lag_from_common_cap_seconds=cap
            - row["checkpoint"]["metadata"]["elapsed_charged_seconds"],
        )
    return dict(
        exact_common_committed_closure_points=common,
        common_wall_cap_seconds=cap,
        common_wall_latest_persisted_audits=selected,
        policy="latest persisted audit at/before common cap; discrete checkpoint lag explicitly reported; full field metrics available separately at Adam500 and frozen final",
        final_charged_vs_committed={
            "plain": [
                left["counts"]["complete_closures"],
                left["final_audit"]["committed_complete_closures"],
            ],
            "phase": [
                right["counts"]["complete_closures"],
                right["final_audit"]["committed_complete_closures"],
            ],
        },
    )


def power_inventory(records, modes):
    require(len(modes) == 40, "PHYSICAL_POWER_KEYS_INCOMPLETE")
    for record in records.values():
        values = np.asarray(record["ordered_per_channel_power"])
        require(
            values.shape == (40,) and np.isfinite(values).all(),
            "POWER_INVENTORY_INVALID",
        )
        port = record["port"]
        for side, key in (("top", "R_total"), ("bottom", "T_total")):
            total = sum(
                v for v, m in zip(values, modes, strict=True) if m["side"] == side
            )
            require(close(total, port[key]), "POWER_SIDE_SUM_DIFFERS")
        require(
            close(1 - port["R_total"] - port["T_total"], port["A_balance"]),
            "BALANCE_ABSORPTION_DIFFERS",
        )
        zero = {}
        for pol in ("s", "p"):
            zero[pol] = sum(
                v
                for v, m in zip(values, modes, strict=True)
                if m["side"] == "top"
                and m["m"] == m["n"] == 0
                and m["polarization"] == pol
            )
            require(
                close(zero[pol], port["R00_" + pol]),
                "ZERO_ORDER_POLARIZATION_SUM_DIFFERS",
            )
        require(
            close(sum(zero.values()), port["R00_total"]), "ZERO_ORDER_TOTAL_DIFFERS"
        )


def write_comparison(name, result, gates, modes):
    physics = result["physics"]
    ref = physics["records"]["REFERENCE"]
    columns = [
        "route",
        "category",
        "G_field_error",
        "native_relative",
        "augmented_relative",
        "original_total_augmented_relative",
        "total_L2_relative",
        "total_scaled_curl_relative",
        "scattered_L2_relative",
        "scattered_scaled_curl_relative",
        "selected_total_E_relative",
        "selected_total_H_relative",
        "ordered_total_channels_relative",
        "ordered_outgoing_channels_relative",
        "ordered_boundary_outgoing_channels_relative",
        "ordered_scattered_channels_relative",
        "R_total",
        "T_total",
        "A_balance",
        "A_volume",
        "R00_s",
        "R00_p",
        "R00_total",
        "energy_closure_absolute",
        "max_channel_power_absolute",
        "pde_only_solver_qualified",
    ]
    with (RECORDS / (name + "_v8.csv")).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for route, gate in gates.items():
            row = dict(
                route=route,
                category=gate["category"],
                G_field_error=gate["G_field_error"],
                pde_only_solver_qualified=gate["pde_only_solver_qualified"],
            )
            row.update(
                {
                    k: gate["equation_audit"][k]
                    for k in (
                        "native_relative",
                        "augmented_relative",
                        "original_total_augmented_relative",
                    )
                }
            )
            row.update(
                {
                    k + "_relative": v["relative"]
                    for k, v in gate["errors"].items()
                    if k + "_relative" in columns
                }
            )
            record = physics["records"][route]
            row.update(
                {
                    k: record["port"][k]
                    for k in (
                        "R_total",
                        "T_total",
                        "A_balance",
                        "R00_s",
                        "R00_p",
                        "R00_total",
                    )
                }
            )
            row.update(
                A_volume=record["volume"]["A_volume_total"],
                energy_closure_absolute=gate["energy_closure_absolute"],
                max_channel_power_absolute=gate["max_channel_power_absolute"],
            )
            writer.writerow(row)
    with (RECORDS / (name + "_channels_v8.csv")).open("w", newline="") as stream:
        fields = [
            "route",
            "kind",
            "side",
            "m",
            "n",
            "polarization",
            "reference_plane_nm",
            "real",
            "imag",
            "reference_real",
            "reference_imag",
            "absolute_difference",
            "vector_denominator",
            "vector_relative",
            "power",
            "reference_power",
            "power_absolute_difference",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for route, gate in gates.items():
            record = physics["records"][route]
            for key, field in CHANNELS.items():
                for j, (a, b, mode) in enumerate(
                    zip(vector(record[field]), vector(ref[field]), modes, strict=True)
                ):
                    writer.writerow(
                        dict(
                            route=route,
                            kind=key,
                            side=mode["side"],
                            m=mode["m"],
                            n=mode["n"],
                            polarization=mode["polarization"],
                            reference_plane_nm=8.75 if mode["side"] == "top" else -1.25,
                            real=a.real,
                            imag=a.imag,
                            reference_real=b.real,
                            reference_imag=b.imag,
                            absolute_difference=abs(a - b),
                            vector_denominator=gate["errors"][key]["denominator"],
                            vector_relative=gate["errors"][key]["relative"],
                            power=record["ordered_per_channel_power"][j],
                            reference_power=ref["ordered_per_channel_power"][j],
                            power_absolute_difference=abs(
                                record["ordered_per_channel_power"][j]
                                - ref["ordered_per_channel_power"][j]
                            ),
                        )
                    )


def main():
    resource_only = "--resources-only" in sys.argv
    indices = {
        name: (
            read(ARTIFACTS / ("index_" + name + ".json"))
            if resource_only
            else index(name)[0]
        )
        for name in STAGES
        if (ARTIFACTS / ("index_" + name + ".json")).exists()
    }
    if "--resources-only" in sys.argv:
        resource_costs(indices)
        return
    require(
        all(
            name in indices
            for name in (
                "v8_authority_assembly_checks",
                "v8_p4_reference_recovery",
                "v8_p3_p4_compare",
                "v8_phase_moment_checks",
                "v8_phase_checks",
                "v8_plain_dual",
                "v8_phase_dual",
                "v8_pde_compare",
            )
        ),
        "MISSING_REQUIRED_V8_INDEX",
    )
    for name, item in indices.items():
        manifest = read(Path(item["run_directory"]) / "run_manifest.json")
        require(
            manifest["source_sha"] == item["source_sha"], "RUN_SOURCE_IDENTITY_CHANGED"
        )
    core, oldref, oldp4 = (
        index(name)[0] for name in ("e1_fe", "e3_reference", "e4_p4")
    )
    require(oldref["files"]["reference"]["sha256"] == LABEL, "P3_REFERENCE_CHANGED")
    require(
        oldp4["result"]["status"] == "DISCRETIZATION_NOT_QUALIFIED",
        "OLD_P4_NOT_RUN_OVERWRITTEN",
    )
    assembly = indices["v8_authority_assembly_checks"]["result"]
    for key in ("eight_cell_p4", "independent_p4", "independent_p3"):
        require(
            len(assembly[key]["samples"]) >= 3, "MISSING_INDEPENDENT_NONZERO_SAMPLES"
        )
        require(
            all(
                max(x[k] for k in ("volume", "augmented", "adjoint")) <= 1e-10
                and x["interior_norm"] > 0
                for x in assembly[key]["samples"]
            ),
            "AUTHORITY_INDEPENDENCE_FAILED",
        )
    require(
        max(assembly["p3_saved_reference_augmented"], assembly["p3_independent_total"])
        <= 1e-10,
        "P3_REFERENCE_ACTION_FAILED",
    )
    p4 = indices["v8_p4_reference_recovery"]["result"]
    rg = reference_gate(p4, p4["physics"]["records"]["REFERENCE"]["audit"])
    rg["stored_packet_audit_used_by_checker"] = rg.pop(
        "independent_frozen_native_audit"
    )
    rg["checker_scope"] = (
        "raw-record arithmetic; final full-field independence is the separately retained Basix integral and DOLFINx linear-form audit, not a new solve or factor"
    )
    rg["independent_Basix_total_relative"] = p4["independent_Basix_total_relative"]
    require(
        p4["independent_Basix_total_relative"] <= 1e-10
        and p4["MUMPS_symbolic_numeric_solve_count"] == [1, 1, 1],
        "P4_INDEPENDENCE_OR_UNIQUE_SOLVE_FAILED",
    )
    cg = comparison_gate(indices["v8_p3_p4_compare"]["result"])
    write(
        "authority_v8.json",
        dict(
            schema="task42extra.authority.v8",
            assembly=assembly,
            profile=indices["v8_authority_profile"]["result"],
            reference=p4,
            reference_gate=rg,
            comparison=indices["v8_p3_p4_compare"]["result"],
            comparison_gate=cg,
            old_e4_not_run_preserved=True,
        ),
    )
    pg = phase_gate(
        indices["v8_phase_moment_checks"]["result"],
        indices["v8_phase_checks"]["result"],
    )
    write("phase_checks_v8.json", dict(schema="task42extra.phase-checks.v8", **pg))
    training = {
        name: training_gate(indices[name], supervised="reference_fit" in name)
        for name in TRAIN
        if name in indices
    }
    write(
        "training_v8.json",
        dict(
            schema="task42extra.training.v8",
            routes=training,
            d_G_runtime_scalar="NOT_RETAINED; exact formula/source/f/G hashes bound; no new factor to reconstruct metadata",
        ),
    )
    work = {
        "C": common_work_points(
            indices["v8_plain_dual"]["result"], indices["v8_phase_dual"]["result"]
        )
    }
    if "v8_phase_reference_fit" in indices:
        work["D"] = common_work_points(
            indices["v8_plain_reference_fit"]["result"],
            indices["v8_phase_reference_fit"]["result"],
        )
    write(
        "common_work_comparison_v8.json",
        dict(schema="task42extra.common-work.v8", **work),
    )
    gates = {}
    for name, supervised in (
        ("v8_pde_compare", False),
        ("v8_representation_compare", True),
    ):
        if name not in indices:
            continue
        result = indices[name]["result"]
        require(
            result["MUMPS_symbolic_numeric_solve_count"] == [0, 0, 0]
            and result["Gsolve_count"] == 0
            and not result["Gram_factor_created"]
            and not result["Maxwell_factor_created"]
            and not result["reference_recomputed"],
            "COMPARE_ONLY_USED_FACTOR_OR_SOLVE",
        )
        reference = result["physics"]["records"]["REFERENCE"]
        power_inventory(
            result["physics"]["records"], core["result"]["identity"]["modes"]
        )
        rows = {
            route: physical_gate(
                row,
                result["physics"]["records"][route],
                reference,
                supervised=supervised,
                natural_scale=result["physics"]["natural_E_scale"],
            )
            for route, row in result["routes"].items()
        }
        gates[name] = rows
        kind = "representation_comparison" if supervised else "PDE_comparison"
        write(
            kind + "_v8.json",
            dict(
                schema="task42extra." + kind + ".v8",
                source_sha=indices[name]["source_sha"],
                independent_gates=rows,
                raw=result,
                reference_never_resolved=True,
            ),
        )
        write_comparison(kind, result, rows, core["result"]["identity"]["modes"])
    conditional = not gates["v8_pde_compare"]["V8-PHASE-DUAL"][
        "pde_only_solver_qualified"
    ]
    require(
        not conditional
        or all(
            name in indices
            for name in (
                "v8_plain_reference_fit",
                "v8_phase_reference_fit",
                "v8_representation_compare",
            )
        ),
        "D_REQUIRED_BUT_NOT_COMPLETED",
    )
    pdegates = gates["v8_pde_compare"]

    def signal(plain, phase):
        pa, qa = plain["equation_audit"], phase["equation_audit"]
        native_ratio = pa["native_relative"] / max(
            qa["native_relative"], np.finfo(float).tiny
        )
        augmented_ratio = pa["augmented_relative"] / max(
            qa["augmented_relative"], np.finfo(float).tiny
        )
        field = (
            phase["errors"]["scattered_L2"]["relative"]
            < plain["errors"]["scattered_L2"]["relative"]
        )
        bothres = native_ratio > 1 and augmented_ratio > 1
        strong = (
            min(native_ratio, augmented_ratio) >= 10
            and max(
                phase["errors"][k]["relative"]
                for k in ("scattered_L2", "scattered_scaled_curl")
            )
            <= 0.1
        )
        return dict(
            native_improvement_ratio=native_ratio,
            augmented_improvement_ratio=augmented_ratio,
            joint_residual_and_scattered_field_improvement=bothres and field,
            registered_PHASE_RESEARCH_SIGNAL=strong,
        )

    signals = dict(
        Adam500=signal(
            pdegates["V8-PLAIN-DUAL-ADAM500"], pdegates["V8-PHASE-DUAL-ADAM500"]
        ),
        final=signal(pdegates["V8-PLAIN-DUAL"], pdegates["V8-PHASE-DUAL"]),
    )
    write(
        "gate_decisions_v8.json",
        dict(
            schema="task42extra.raw-gates.v8",
            authority_reference=rg,
            authority_p_comparison=cg,
            phase_interface=pg["qualified"],
            conditional_D_required=conditional,
            routes=gates,
            phase_scientific_signals=signals,
            production_initialization_allowed=False,
            target_5nm="NOT_RUN",
            target_0p7nm="NOT_RUN",
            old_negative_evidence_preserved=True,
        ),
    )
    runs = {
        name: dict(
            index_sha256=sha(ARTIFACTS / ("index_" + name + ".json")),
            source_sha=item["source_sha"],
            run_directory=item["run_directory"],
            files=item["files"],
            status=item["result"]["status"],
        )
        for name, item in indices.items()
    }
    write(
        "run_index_v8.json",
        dict(
            schema="task42extra.run-index.v8",
            review_release=REVIEW_SHA,
            reviewed_baseline="64e945b386e4c2608450c78a7d9dec9328c691da",
            original_base="fbac3d8777fcfd897d93b898cb9f460f79ddd6ff",
            runs=runs,
            reused_reference=oldref["files"]["reference"],
            reused_native=core["files"]["native"],
            reused_Gram=core["files"]["gram"],
            reused_moments=core["files"]["moments_q15"],
        ),
    )
    cost = resource_costs(indices)
    print(
        json.dumps(
            dict(
                status="V8_RAW_RECORDS_CHECKED",
                p4=rg["qualified"],
                p_sensitivity=cg["status"],
                conditional_D=conditional,
                batch_seconds=cost["V8_batch_seconds"],
            )
        )
    )


if __name__ == "__main__":
    main()
