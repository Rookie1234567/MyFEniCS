"""V11 frozen-record arithmetic checker. Never solve, train, or load Torch."""

import csv
import json
from pathlib import Path
import sys

import numpy as np

from benchmarks.check_task42extra_v2 import (
    ROOT,
    RESULTS,
    CHECKS,
    RECORDS,
    read,
    sha,
    close,
)
from benchmarks.check_task42extra_v8 import (
    physical_gate,
    require,
    power_inventory,
    write_comparison,
)
from benchmarks.check_task42extra_v9 import load
from benchmarks.check_task42extra_v10 import compact_write, distribution
from src.runners.feinn_metric_campaign import STAGES, LIMITS, OLD_SECONDS, REVIEW_SHA

PILOTS = ("v11_phase_identity_metric", "v11_phase_block_metric")


def compact_metric_arrays(value):
    if isinstance(value, dict):
        return {
            k: compact_metric_arrays(v) for k, v in value.items() if k != "diagonal"
        }
    if isinstance(value, list):
        return [compact_metric_arrays(v) for v in value]
    return value


def check_scale(item):
    r = item["result"]
    e = r["estimate"]
    q = np.asarray(e["curvatures"], float)
    sizes = np.asarray(e["sizes"], int)
    require(
        q.shape == (8, 3) and np.isfinite(q).all() and (q >= 0).all(),
        "CURVATURE_PROBES",
    )
    require(sizes.tolist() == [192, 64, 4096, 64, 4096, 64, 384, 6], "GROUP_ORDER")
    h = q.mean(axis=1)
    bar = float(np.dot(h, sizes) / sizes.sum())
    require(bar > 0 and close(bar, e["weighted_mean"]), "WEIGHTED_CURVATURE")
    m = np.clip(h / bar, 1e-4, 1e4)
    require(np.allclose(m, e["values"], rtol=1e-12, atol=0), "FIXED_M_ARITHMETIC")
    span = float(h.max() / max(h.min(), 1e-4 * bar))
    require(close(span, e["curvature_span"]), "CURVATURE_SPAN")
    start = r["identity"]["original_audit"]["native_relative"]
    signal = span >= 10 and any(
        t["metric"] == "M"
        and t["valid"]
        and t["loss"] < r["original_loss"]
        and t["native_relative"] <= 1.01 * start
        for t in r["trials"]
    )
    require(signal == r["C_start_signal"], "A_SAVED_SIGNAL_DIFFERS")
    require(r["counts"]["K"] <= 32 and len(r["trials"]) <= 4, "A_WORK_CAPS")
    require(
        r["committed_updates"] == 0 and r["theta0_restored"] and r["cache_restored"],
        "A_STATE_RESTORE",
    )
    for t in r["trials"]:
        require(close(t["ared"], r["original_loss"] - t["loss"]), "A_REAL_DECREASE")
    return dict(r, checker_C_start_signal=bool(signal), checker_span=span)


def check_interface(item, attempts):
    r = item["result"]
    passed = r["actual_g_y"]["relative"] <= 1e-9
    require(len(r["directions"]) == 3, "B_THREE_DIRECTIONS")
    witnesses = []
    for row in r["directions"]:
        passed &= row["transformed_K_pair"]["relative"] <= 1e-9
        good = []
        for p in row["finite_difference"]:
            defect = abs(p["actual"] - p["expected"]) / max(
                abs(p["actual"]), abs(p["expected"]), 1e-30
            )
            require(close(defect, p["relative"]), "FD_ARITHMETIC")
            if defect <= 1e-5:
                good.append(p["epsilon"])
        passed &= len(good) >= 2
        witnesses.append(dict(direction=row["direction"], stable_steps=good))
    proposal = r["identity_short_proposal"]
    passed &= all(
        proposal[k]["relative"] <= 1e-10
        for k in ("step_pair", "pred_pair", "ared_pair")
    )
    passed &= r["theta0_restored"] and not r["reference_loaded"]
    require(bool(passed) == r["passed"], "B_SAVED_GATE_DIFFERS")
    total_k = sum(x["result"]["counts"]["K"] for x in attempts.values()) + 3
    require(
        total_k <= 96 and total_k == r["real_K_actions_including_independent_chains"],
        "B_REAL_K_CAP",
    )
    return dict(
        r,
        checker_passed=bool(passed),
        stable_witnesses=witnesses,
        total_new_real_K=total_k,
        failed_attempts=[
            dict(
                stage=s,
                source_sha=x["source_sha"],
                status=x["result"]["status"],
                result=x["files"]["result"],
            )
            for s, x in attempts.items()
            if not x["result"].get("passed")
        ],
    )


def metric_compact(record):
    d = np.asarray(record["diagonal"], float)
    starts = np.cumsum([0, 192, 64, 4096, 64, 4096, 64, 384])
    return {
        **{k: v for k, v in record.items() if k != "diagonal"},
        "group_values": d[starts].tolist(),
        "size": len(d),
    }


def pilot_record(item):
    r = item["result"]
    require(
        r["common_theta0_sha256"]
        == "d79d1363c45aad4b215289a4bebd39be6430e1ca9fcb095e4224d493af857599",
        "C_COMMON_ANCHOR",
    )
    require(
        close(r["common_mu0"], 8.319921758282803)
        and close(r["common_h0"], 506073208.19371504),
        "C_COMMON_GN",
    )
    require(
        r["inherited_accepted_outer"] == 75
        and r["new_Adam_updates"] == 0
        and r["consistent_optimizer_state_saved"],
        "C_PREFIX_OR_STATE",
    )
    require(not r["PC_allowed"] and not r["PC_builds"], "C_PC_FORBIDDEN")
    require(
        not r["reference_used_for_training"]
        and not r["features_reference_exposed"]
        and r["pde_only_solve"],
        "C_LABEL_BOUNDARY",
    )
    require(
        not r["production_initialization_allowed"] and r["benchmark_previously_seen"],
        "C_PRODUCTION_BOUNDARY",
    )
    require(
        all(
            not any(
                b in p
                for b in (
                    "reference_state",
                    "reference_fit",
                    "Phi",
                    "projection.npz",
                    "p4_reference",
                    "p5_reference",
                )
            )
            for p in r["actual_artifact_reads"]
        ),
        "C_TRAINING_READS",
    )
    count, jac = r["counts"], r["JVP_VJP_counts"]
    require(
        r["new_accepted_outer"] <= 30
        and count["K"] <= 1200
        and sum(jac.values()) <= 2500
        and count["trial_loss"] <= 128,
        "C_WORK_CAPS",
    )
    require(
        r["d_G"] > 0 and r["Gram_factor"]["max_solve_true_relative"] <= 1e-11,
        "C_G_SOLVE",
    )
    history = Path(item["files"]["history"]["path"])
    trials, events, cgs = [], {}, []
    with history.open() as stream:
        for line in stream:
            row = json.loads(line)
            kind = row.get("kind", "UNKNOWN")
            events[kind] = events.get(kind, 0) + 1
            if kind not in ("GN_TRIAL", "CAUCHY_TRIAL"):
                continue
            cg = row.get("cg", {})
            if cg:
                require(cg["max_iter"] <= 40 and cg["iterations"] <= 40, "CG_ITER_CAP")
                require(
                    cg["converged"]
                    == (
                        cg["finite"] and cg["original_parameter_true_relative"] <= 0.01
                    ),
                    "ORIGINAL_CG_GATE",
                )
                cgs.append(cg)
            require(
                not row["accepted"]
                or (row["ared"] > 0 and row["eta"] >= 0.1 and row["pred"] > 0),
                "ACCEPTANCE_ARITHMETIC",
            )
            if row.get("pred") is not None and row["pred"] > 0:
                require(close(row["eta"], row["ared"] / row["pred"]), "ETA_ARITHMETIC")
            trials.append(
                {
                    k: row.get(k)
                    for k in (
                        "accepted",
                        "mu",
                        "loss",
                        "pred",
                        "ared",
                        "eta",
                        "elapsed_charged_seconds",
                    )
                }
                | {
                    "cg_iterations": cg.get("iterations"),
                    "cg_original_relative": cg.get("original_parameter_true_relative"),
                    "cg_transformed_relative": cg.get("transformed_true_relative"),
                    "cg_converged": cg.get("converged"),
                }
            )
    fields = (
        "route",
        "stop_reason",
        "failure",
        "counts",
        "JVP_VJP_counts",
        "native_action_counts",
        "Gsolve_count",
        "initial_audit",
        "final_audit",
        "inherited_accepted_outer",
        "new_accepted_outer",
        "cumulative_accepted_outer",
        "inherited_counts",
        "inherited_JVP_VJP_counts",
        "cumulative_counts",
        "cumulative_JVP_VJP_counts",
        "mu_final",
        "h0",
        "d_G",
        "inherited_prefix_seconds",
        "logical_path_seconds",
        "launcher_charged_seconds",
        "final_c_sha256",
        "final_parameters_sha256",
        "buffers_sha256",
        "Gram_factor",
        "derivative_cache",
        "nested_timers",
        "JVP_VJP_costs",
        "native_action_costs",
        "fixed_time_boundaries",
        "fault_recovery",
    )
    compact = {k: r.get(k) for k in fields}
    compact.update(
        source_sha=item["source_sha"],
        files=item["files"],
        parameter_metric=metric_compact(r["parameter_metric"]),
        history_event_counts=events,
        trial_count=len(trials),
        rejected=sum(not t["accepted"] for t in trials),
        CG_iterations=distribution([c["iterations"] for c in cgs]),
        CG_original_true_relative=distribution(
            [c["original_parameter_true_relative"] for c in cgs]
        ),
        inner_converged=sum(c["converged"] for c in cgs),
        inner_inexact=sum(not c["converged"] for c in cgs),
        PC_constructions=0,
        history_sha256=sha(history),
        full_K_history="ignored; hash bound; not copied into Git",
        final_PT=item["files"]["durable_final"],
        final_NPZ=item["files"]["checkpoint"],
    )
    # Actual accepted updates and eight-group telemetry only, no inner trajectories.
    compact["accepted_updates"] = [
        {
            k: x.get(k)
            for k in (
                "accepted_outer",
                "committed_elapsed_seconds",
                "group_update_norms",
                "group_update_RMS",
                "mu_over_h0",
            )
        }
        for x in r["accepted_history"]
    ]
    return compact_metric_arrays(compact), trials


def resources(tail_allowance=120.0):
    rows = []
    require(
        not [
            p
            for p in RESULTS.glob("task42extra_v11_*")
            if not (p / "run_summary.json").exists()
        ],
        "ACTIVE_OR_MISSING_V11_SUMMARY",
    )
    for p in sorted(RESULTS.glob("task42extra_v11_*/run_summary.json")):
        r, m = read(p), read(p.parent / "run_manifest.json")
        peak = swap = 0
        for line in (p.parent / "supervision/resources.jsonl").read_text().splitlines():
            x = json.loads(line)
            peak = max(peak, x["rss_bytes"])
            swap = max(swap, x["swap_bytes"])
        require(
            peak == r["sampled_process_tree_rss_peak_bytes"]
            and swap == r["sampled_process_tree_swap_peak_bytes"],
            "TREE_RESOURCE_RECOUNT",
        )
        b = read(p.parent / "resource_baseline.json")
        memory = b["memory"]
        require(
            memory["neighbor_growth_allowance_bytes"] >= 384 * 2**30
            and memory["system_reserve_bytes"]
            >= max(128 * 2**30, memory["effective_total_bytes"] * 0.1),
            "RESERVES",
        )
        require(
            memory["effective_available_bytes"]
            >= memory["reserve_bytes"] + memory["launch_cap_bytes"]
            and b["disk_free_bytes"] >= 50 * 2**30,
            "ADMISSION_MEMORY_DISK",
        )
        require(
            m["mpi_size"] == m["math_threads"] == 1 and m["cpu_only"], "CPU_MPI_THREADS"
        )
        keys = (
            "input_original.dat",
            "resolved_config.json",
            "run_manifest.json",
            "run_summary.json",
            "resource_baseline.json",
            "budget_at_launch.json",
            "stages.jsonl",
            "supervision/resources.jsonl",
            "pressure_stable_window.json",
        )
        raw = {k: sha(p.parent / k) for k in keys if (p.parent / k).exists()}
        stable = read(p.parent / "pressure_stable_window.json")
        require(stable["passed"] and stable["observed_seconds"] >= 60, "STABLE_WINDOW")
        stages = [
            json.loads(line)
            for line in (p.parent / "stages.jsonl").read_text().splitlines()
        ]
        factor = [
            s
            for s in stages
            if s.get("name") in ("riesz_symbolic", "riesz_numeric", "riesz_released")
        ]
        rows.append(
            dict(
                path=str(p),
                stage=m["stage"],
                group=STAGES[m["stage"]][2],
                source_sha=m["source_sha"],
                input_sha256=m["input_sha256"],
                seconds=max(
                    r["elapsed_seconds"],
                    r.get("launch_to_summary_seconds_monotonic", 0),
                ),
                peak_tree_RSS_bytes=peak,
                own_swap_bytes=swap,
                classification=r["classification"],
                descendants_cleared=r["descendants_cleared"],
                termination_reason=r.get("termination_reason"),
                raw_hashes=raw,
                admission_memory=memory,
                selected_cpu=b["cpu"],
                pressure_stability={
                    k: stable[k]
                    for k in (
                        "passed",
                        "required_seconds",
                        "observed_seconds",
                        "thresholds",
                        "watchdog_bad_samples_to_stop",
                    )
                },
                Gram_markers=factor,
                shared_workstation=True,
            )
        )
    for p in sorted(CHECKS.glob("v11_*/summary.json")):
        r = read(p)
        g = p.parent.name[4:5].upper()
        rows.append(
            dict(
                path=str(p),
                group=g if g in LIMITS else "E",
                seconds=r["elapsed_seconds"],
                peak_tree_RSS_bytes=r.get("sampled_process_tree_rss_peak_bytes"),
                own_swap_bytes=r.get("sampled_process_tree_swap_peak_bytes"),
                classification=r["classification"],
                descendants_cleared=r["descendants_cleared"],
                summary_sha256=sha(p),
                scope=r.get("scope"),
            )
        )
    groups = {g: sum(x["seconds"] for x in rows if x["group"] == g) for g in LIMITS}
    groups["E"] += tail_allowance
    used = sum(groups.values())
    require(used <= 21600 and all(groups[g] <= LIMITS[g] for g in LIMITS), "V11_BUDGET")
    require(
        all(
            x["own_swap_bytes"] in (None, 0) and x["descendants_cleared"] for x in rows
        ),
        "OWN_SWAP_OR_CLEARANCE",
    )
    require(
        all(
            x["peak_tree_RSS_bytes"] is None
            or x["peak_tree_RSS_bytes"] < (2 if "/checks/" in x["path"] else 16) * 2**30
            for x in rows
        ),
        "TREE_RSS_CAP",
    )
    management = []
    for p in sorted(
        (ROOT / "tmp/task42extra/durable").glob("v11_*/terminal_identity.json")
    ):
        x = read(p)["server"]
        row = dict(
            path=str(p), sha256=sha(p), pid=x["pid"], start_ticks=x["start_ticks"]
        )
        for line in x["status"].splitlines():
            if line.startswith(("VmRSS:", "VmSwap:", "Threads:")):
                k, v = line.split(":", 1)
                row[k] = int(v.split()[0]) * (1 if k == "Threads" else 1024)
        management.append(row)
    require(all(x.get("VmSwap", 0) == 0 for x in management), "MANAGEMENT_SWAP")
    return dict(
        schema="task42extra.resource-costs.v11",
        old_seconds=OLD_SECONDS,
        new_seconds=used,
        cumulative_seconds=OLD_SECONDS + used,
        new_limit_seconds=21600,
        groups_seconds=groups,
        groups_limits_seconds=LIMITS,
        entries=rows,
        final_tail_allowance_seconds=tail_allowance,
        management_server_launch_samples=management,
        memory_scope="sampled simultaneous supervised numerical process-tree peak; manager launch samples separate; not a continuous kernel cgroup guarantee",
        old_interruption_and_replay_costs_preserved=True,
        old_lost_attempt_seconds_preserved=3284,
        historical_prefix_not_double_charged_to_project=True,
        system_pressure_recoveries_used=0,
    )


def main():
    scale = load("v11_parameter_scale_diagnostic")
    check_scale(scale)
    compact_write(
        "parameter_scale_v11.json",
        dict(
            source_sha=scale["source_sha"],
            files=scale["files"],
            result=check_scale(scale),
        ),
    )
    attempts = {
        s: load(s)
        for s in (
            "v11_parameter_metric_checks",
            "v11_parameter_metric_checks_repair",
            "v11_parameter_metric_checks_stability",
        )
    }
    checks = check_interface(
        attempts["v11_parameter_metric_checks_stability"], attempts
    )
    compact_write(
        "metric_checks_v11.json",
        dict(
            source_sha=attempts["v11_parameter_metric_checks_stability"]["source_sha"],
            result=checks,
            attempts={
                s: dict(
                    source_sha=x["source_sha"],
                    files=x["files"],
                    counts=x["result"]["counts"],
                    status=x["result"]["status"],
                )
                for s, x in attempts.items()
            },
        ),
    )
    indices = {
        s: load(s)
        for s in STAGES
        if (ROOT / "benchmarks/artifacts/task42extra" / f"index_{s}.json").exists()
    }
    pilots = {}
    trials = []
    for s in PILOTS:
        if s not in indices:
            continue
        record, rows = pilot_record(indices[s])
        pilots[s] = record
        trials.extend(
            dict(route=record["route"], trial_index=j, **r)
            for j, r in enumerate(rows, 1)
        )
    with (RECORDS / "metric_trials_v11.csv").open("w", newline="") as stream:
        keys = list(trials[0]) if trials else ["route", "trial_index", "accepted"]
        w = csv.DictWriter(stream, fieldnames=keys)
        w.writeheader()
        w.writerows(trials)
    comparison = indices.get("v11_metric_compare")
    gates = {}
    signal = False
    performance = "NOT_RUN"
    if comparison:
        r = comparison["result"]
        require(
            not r["reference_recomputed"]
            and r["reference_loaded_only_after_candidates_frozen"]
            and not r["D_authorized_in_this_batch"],
            "E_REFERENCE_POLICY",
        )
        records = r["physics"]["records"]
        ref = records["REFERENCE"]
        native = load("e1_fe")
        modes = native["result"]["identity"]["modes"]
        power_inventory(records, modes)
        gates = {
            name: physical_gate(
                row, records[name], ref, supervised=False, natural_scale=np.sqrt(750.0)
            )
            for name, row in r["routes"].items()
        }
        write_comparison("metric_comparison", r, gates, modes, version=11)
        fields = {
            name: dict(
                source_sha=row["source_sha"],
                frozen_checkpoint=row["frozen_checkpoint"],
                reference_G_norm=r["reference_G_norm_identity"],
                errors=gates[name]["errors"],
                region_scattered=row["region_scattered"],
                region_total=row["region_total"],
                reconstruction=row["reconstruction"],
                total_norms=records[name]["total_L2_scaled_curl_norms"],
                scattered_norms=records[name]["scattered_L2_scaled_curl_norms"],
            )
            for name, row in r["routes"].items()
        }
        compact_write(
            "metric_field_diagnostics_v11.json",
            dict(
                reference_identity=r["reference_identity"],
                reference_norms={k: v for k, v in ref.items() if "norm" in k},
                routes=fields,
            ),
        )
        a = r["routes"]["V11-PHASE-IDENTITY-METRIC-CONTROL"]
        b = r["routes"]["V11-PHASE-BLOCK-METRIC"]
        baseline = scale["result"]["identity"]["original_audit"]
        signal = all(
            b["comparisons"]["equation_audit"][k] <= 0.1 * baseline[k]
            and b["comparisons"]["equation_audit"][k]
            <= 0.5 * a["comparisons"]["equation_audit"][k]
            for k in ("native_relative", "augmented_relative")
        )
        signal &= all(
            b["comparisons"]["errors"][k]["relative"] <= 0.1
            and b["comparisons"]["errors"][k]["relative"]
            < a["comparisons"]["errors"][k]["relative"]
            for k in ("scattered_L2", "scattered_scaled_curl")
        )
        performance = "SHARED_WORKSTATION_NO_PRESSURE_STOPS_RECORDED"
    cost = resources(float(sys.argv[1]) if len(sys.argv) > 1 else 120.0)
    compact_write("resource_costs_v11.json", cost)
    compact_write(
        "run_index_v11.json",
        dict(
            schema="task42extra.run-index.v11",
            authority_release=REVIEW_SHA,
            actual_sources={s: x["source_sha"] for s, x in indices.items()},
            indices={
                s: dict(
                    path=str(
                        ROOT / "benchmarks/artifacts/task42extra" / f"index_{s}.json"
                    ),
                    sha256=sha(
                        ROOT / "benchmarks/artifacts/task42extra" / f"index_{s}.json"
                    ),
                    files=x["files"],
                )
                for s, x in indices.items()
            },
            pilots=pilots,
            source_vs_later_document_HEAD_separate=True,
        ),
    )
    compact_write(
        "gate_decisions_v11.json",
        dict(
            schema="task42extra.gates.v11",
            A_signal=scale["result"]["C_start_signal"],
            B_interface_pass=checks["checker_passed"],
            pilots_completed=list(pilots),
            physical=gates,
            research_signal=bool(signal),
            research_category="BLOCK_METRIC_RESEARCH_SIGNAL"
            if signal
            else "NO_USEFUL_METRIC_GAIN"
            if comparison
            else "NOT_RUN",
            cost_performance_scope=performance,
            production_initialization_allowed=False,
            merge_approved=False,
            derivative_cache_qualification_reused_not_convergence=True,
            D_training_authorized=False,
            p5_existing_authority_reused_no_new_solve=True,
            h_and_ports_not_qualified=True,
        ),
    )
    print(
        json.dumps(
            dict(
                status="V11_COMPACT_CHECKER_COMPLETE",
                research_signal=bool(signal),
                new_seconds=cost["new_seconds"],
                groups=cost["groups_seconds"],
                physical_routes=len(gates),
            )
        )
    )


if __name__ == "__main__":
    main()
