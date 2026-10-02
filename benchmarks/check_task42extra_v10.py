"""V10 compact frozen-record checker; no numerical solve or training."""

import csv
import json
from pathlib import Path
import shutil
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
    vector,
)
from benchmarks.check_task42extra_v9 import load
from src.runners.feinn_cached_gn_campaign import STAGES, LIMITS, OLD_SECONDS


def compact_write(name, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    require(len(data.encode()) <= 200 * 1024, "COMPACT_JSON_EXCEEDS_200_KIB:" + name)
    (RECORDS / name).write_text(data)


def distribution(values):
    if not values:
        return dict(count=0, minimum=None, median=None, maximum=None)
    a = np.asarray(values, dtype=float)
    require(np.isfinite(a).all(), "NONFINITE_DISTRIBUTION")
    return dict(
        count=len(a),
        minimum=float(a.min()),
        median=float(np.median(a)),
        maximum=float(a.max()),
        total=float(a.sum()),
    )


def derivative_gate(row, *, require_proposal=False):
    require(len(row["directions"]) == 3, "THREE_DIRECTIONS_NOT_RETAINED")
    passed = row["c"]["relative"] <= 1e-10
    for p in row["directions"]:
        passed &= max(p[k]["relative"] for k in ("JVP", "VJP")) <= 1e-10
        passed &= p["real_adjoint"] <= 1e-10
        passed &= set(p["families"]) == {"edge", "face", "interior"}
        passed &= all(r["relative"] <= 1e-10 for r in p["families"].values())
    passed &= max(row[k]["relative"] for k in ("K", "gradient")) <= 1e-9
    passed &= row["K_symmetry"] <= 1e-8 and row["K_energy_pair"] <= 1e-8
    passed &= all(x["relative"] <= 1e-10 for x in row["batch"].values())
    passed &= all(
        row[k]
        for k in (
            "cache_rejection_reuses",
            "cache_acceptance_invalidates",
            "buffer_invalidates",
            "mu_only_reuse",
            "recovery_rebuilt",
        )
    )
    passed &= row["recovery_JVP"]["relative"] <= 1e-10
    passed &= row["cache"]["resident_bytes"] <= 2 * 2**30
    p = row["proposal"]
    if require_proposal:
        require(
            p is not None
            and all(p[k] is not None for k in ("direction", "pred", "ared")),
            "REAL_C_COMPLETE_PROPOSAL_NOT_RETAINED",
        )
    if p is not None:
        passed &= all(
            p[k] is None or p[k]["relative"] <= 1e-8
            for k in ("direction", "pred", "ared")
        )
    require(bool(passed) == row["passed"], "DERIVATIVE_SAVED_GATE_DIFFERS")
    return bool(passed)


def benchmark_gates(checks, result):
    expected = {"plain_gn", "phase_gn", "plain_fit_gn", "phase_fit_gn"}
    require(
        set(checks) == set(result["states"]) == expected, "FOUR_FIXED_STATES_MISSING"
    )
    gates = {}
    for name, r in result["states"].items():
        samples = [x for x in result["samples"] if x["state"] == name]
        require(
            all(
                x["K_count"] == 16
                and x["seed"] == 4211001
                and x["cache_bytes"] <= 2 * 2**30
                for x in samples
            ),
            "PERFORMANCE_SAMPLE_IDENTITY_CHANGED",
        )
        for x in samples:
            parts = sum(
                x[k]
                for k in (
                    "build_seconds",
                    "gradient_seconds",
                    "K16_seconds",
                    "release_seconds",
                )
            )
            require(
                x["total_seconds"] > 0 and x["total_seconds"] >= parts - 1e-6,
                "PERFORMANCE_TIMER_SCOPE",
            )
        correct = derivative_gate(
            checks[name], require_proposal=not name.endswith("fit_gn")
        )
        if len(samples) != 8:
            require(
                not r["passed"] and r["status"] == "PERFORMANCE_BUDGET_FRONTIER",
                "INCOMPLETE_PERFORMANCE_PROMOTED",
            )
            gates[name] = dict(r, complete_samples=False, correctness_pass=correct)
            continue
        times = {}
        require(
            [(x["repeat"], x["implementation"]) for x in samples if not x["warmup"]]
            == [
                (0, "old_AD"),
                (0, "cached"),
                (1, "cached"),
                (1, "old_AD"),
                (2, "old_AD"),
                (2, "cached"),
            ],
            "PERFORMANCE_ORDER_CHANGED",
        )
        for kind in ("old_AD", "cached"):
            a = [
                x["total_seconds"]
                for x in samples
                if x["implementation"] == kind and not x["warmup"]
            ]
            require(len(a) == 3, "ALTERNATING_THREE_REPEATS_MISSING")
            times[kind] = float(np.median(a))
        speedup = times["old_AD"] / times["cached"]
        require(
            close(speedup, r["speedup_including_build_release"]),
            "MEDIAN_SPEEDUP_ARITHMETIC",
        )
        p = checks[name]["proposal"]
        proposal = p is None or p["new_seconds"] <= 1.10 * p["old_seconds"]
        passed = correct and speedup >= 1.30 and proposal
        require(passed == r["passed"], "PERFORMANCE_SAVED_GATE_DIFFERS")
        gates[name] = dict(
            r,
            median_recomputed=times,
            correctness_pass=checks[name]["passed"],
            proposal_cost_qualified=proposal,
        )
    return gates


def resource_costs():
    rows = []
    pending_formal = [
        str(p)
        for p in RESULTS.glob("task42extra_v10_*")
        if not (p / "run_summary.json").exists()
    ]
    require(
        not pending_formal, "ACTIVE_OR_MISSING_V10_RUN_SUMMARY:" + str(pending_formal)
    )
    for path in sorted(RESULTS.glob("task42extra_v10_*/run_summary.json")):
        r, m = read(path), read(path.parent / "run_manifest.json")
        resource = path.parent / "supervision/resources.jsonl"
        peak = swap = 0
        with resource.open() as stream:
            for line in stream:
                sample = json.loads(line)
                peak = max(peak, sample["rss_bytes"])
                swap = max(swap, sample["swap_bytes"])
        require(
            peak == r["sampled_process_tree_rss_peak_bytes"]
            and swap == r["sampled_process_tree_swap_peak_bytes"],
            "RESOURCE_SAMPLE_PEAK_ARITHMETIC",
        )
        baseline = read(path.parent / "resource_baseline.json")
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
        require(
            m["mpi_size"] == m["math_threads"] == 1 and m["cpu_only"],
            "MPI_THREAD_CPU_IDENTITY",
        )
        raw_hashes = {
            name: sha(path.parent / name)
            for name in (
                "run_manifest.json",
                "run_summary.json",
                "resource_baseline.json",
                "budget_at_launch.json",
                "input_original.dat",
                "resolved_config.json",
                "stages.jsonl",
                "supervision/resources.jsonl",
            )
        }
        gram_markers = {}
        for line in (path.parent / "stages.jsonl").read_text().splitlines():
            marker = json.loads(line)
            if marker.get("name") in (
                "riesz_symbolic",
                "riesz_numeric",
                "riesz_released",
            ):
                gram_markers[marker["name"]] = dict(
                    worker_elapsed_seconds=marker["seconds"], facts=marker["facts"]
                )
        gram_setup = gram_markers.get(
            "riesz_numeric", gram_markers.get("riesz_symbolic")
        )
        gram_record = dict(
            setup_observed=gram_setup,
            release_observed=gram_markers.get("riesz_released"),
            lifetime_status="NO_GRAM_FACTOR_IN_THIS_STAGE"
            if not gram_markers
            else "COMPLETE_RELEASE_RETAINED"
            if "riesz_released" in gram_markers
            else "LIFETIME_SOLVE_RELEASE_NOT_RETAINED",
            scope="nested observed stage facts; complete attempt wall already charges all setup/solve/interruption; do not add twice",
        )
        rows.append(
            dict(
                path=str(path),
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
                summary_sha256=sha(path),
                raw_hashes=raw_hashes,
                admission_memory=memory,
                selected_cpu=baseline["cpu"],
                Gram_auxiliary=gram_record,
                shared_workstation=True,
            )
        )
    for path in sorted(CHECKS.glob("v10_*/summary.json")):
        r = read(path)
        g = path.parent.name[4:5].upper()
        rows.append(
            dict(
                path=str(path),
                group=g if g in LIMITS else "E",
                seconds=r["elapsed_seconds"],
                peak_tree_RSS_bytes=r["sampled_process_tree_rss_peak_bytes"],
                own_swap_bytes=r["sampled_process_tree_swap_peak_bytes"],
                classification=r["classification"],
                descendants_cleared=r["descendants_cleared"],
                summary_sha256=sha(path),
            )
        )
    groups = {g: sum(x["seconds"] for x in rows if x["group"] == g) for g in LIMITS}
    tail = 120.0
    groups["E"] += tail
    used = sum(x["seconds"] for x in rows) + tail
    require(used <= 43200 and all(groups[g] <= LIMITS[g] for g in LIMITS), "V10_BUDGET")
    require(
        all(r["own_swap_bytes"] == 0 and r["descendants_cleared"] for r in rows),
        "SWAP_OR_CLEARANCE",
    )
    require(
        all(
            r["peak_tree_RSS_bytes"] < (2 if "/checks/" in r["path"] else 16) * 2**30
            for r in rows
        ),
        "TREE_RSS_BUDGET",
    )
    servers = []
    for p in sorted(
        (ROOT / "tmp/task42extra/durable").glob("v10_*/terminal_identity.json")
    ):
        x = read(p)["server"]
        s = dict(path=str(p), sha256=sha(p), pid=x["pid"], start_ticks=x["start_ticks"])
        for line in x["status"].splitlines():
            if line.startswith(("VmRSS:", "VmSwap:", "Threads:")):
                k, v = line.split(":", 1)
                s[k] = int(v.split()[0]) * (1 if k == "Threads" else 1024)
        servers.append(s)
    require(all(s.get("VmSwap", 0) == 0 for s in servers), "MANAGEMENT_SWAP")
    return dict(
        schema="task42extra.resource-costs.v10",
        old_seconds=OLD_SECONDS,
        new_seconds=used,
        cumulative_seconds=OLD_SECONDS + used,
        measured_stage_and_auxiliary_seconds=used - tail,
        direct_and_final_tail_allowance_seconds=tail,
        new_limit_seconds=43200,
        groups_seconds=groups,
        groups_limits_seconds=LIMITS,
        entries=rows,
        management_server_launch_samples=servers,
        old_interruption_and_replay_costs_preserved=True,
        old_lost_attempt_seconds_preserved=3284,
        historical_prefix_not_double_charged_to_project=True,
        memory_scope="sampled simultaneous numerical process tree RSS, not payload or sum of peaks",
        management_scope="separate own tmux launch snapshots, not continuous peak",
        no_continuous_kernel_cgroup_limit_claim=True,
    )


def journal(path):
    rows, incomplete = [], 0
    for line in Path(path).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            incomplete += 1
    return rows, incomplete


def recovery_journals(item):
    r = item["result"]
    previous, recovery = [], r.get("fault_recovery")
    while recovery:
        raw = recovery["history"]
        require(sha(raw["path"]) == raw["sha256"], "RECOVERY_HISTORY_BYTES_CHANGED")
        previous.append((raw, recovery["prior_source_sha"]))
        recovery = recovery["committed_metadata"].get("fault_recovery")
    sources = list(reversed(previous)) + [
        (item["files"]["history"], item["source_sha"])
    ]
    all_rows, scopes = [], []
    seen = set()
    for entry, source in sources:
        if entry["path"] in seen:
            continue
        seen.add(entry["path"])
        rows, incomplete = journal(entry["path"])
        run_id = Path(entry["path"]).parent.name
        all_rows.extend(
            dict(x, attempt_run_id=run_id, actual_source_sha=source) for x in rows
        )
        scopes.append(
            dict(
                entry,
                source_sha=source,
                run_id=run_id,
                parsed_rows=len(rows),
                incomplete_journal_lines=incomplete,
            )
        )
    return all_rows, scopes


def compact_audit(row):
    result = {k: v for k, v in row.items() if k != "checkpoint"}
    if "checkpoint" in row:
        p = row["checkpoint"]
        result["checkpoint"] = {k: p[k] for k in ("name", "sha256")}
    return result


def training(item):
    r = item["result"]
    meta = r["final_checkpoint"]["metadata"]
    require(
        r["new_Adam_updates"] == 0
        and r["old_optimizer_history_loaded"]
        and not r["scale_reestimated"],
        "GN_RECOVERY_RESET",
    )
    require(
        not r["Maxwell_factor_created"] and not r["global_Maxwell_matrix_created"],
        "MAXWELL_TRAINING_FALLBACK",
    )
    require(
        r["reference_used_for_training"]
        == r["features_reference_exposed"]
        == r["supervised"]
        and r["pde_only_solve"] != r["supervised"]
        and not r["production_initialization_allowed"],
        "LABEL_BOUNDARY",
    )
    require(r["benchmark_previously_seen"], "BENCHMARK_EXPOSURE_NOT_REPORTED")
    require(
        set(r["actual_artifact_reads"]).issubset(r["training_data_read_whitelist"]),
        "TRAINING_READ_WHITELIST",
    )
    if not r["supervised"]:
        require(
            not any(
                "reference_state" in x or "reference_fit" in x
                for x in r["actual_artifact_reads"]
            ),
            "C_REFERENCE_ARTIFACT_READ",
        )
    counts, inherited = r["counts"], r["inherited_counts"]
    require(
        all(
            r["cumulative_counts"][k] == inherited.get(k, 0) + v
            for k, v in counts.items()
        ),
        "COUNTS_NOT_INHERITED",
    )
    require(
        all(
            r["cumulative_JVP_VJP_counts"][k]
            == r["inherited_JVP_VJP_counts"].get(k, 0) + v
            for k, v in r["JVP_VJP_counts"].items()
        ),
        "DERIVATIVE_COUNTS_NOT_INHERITED",
    )
    require(
        r["cumulative_accepted_outer"]
        == r["new_accepted_outer"] + r["inherited_accepted_outer"],
        "ACCEPTED_NOT_INHERITED",
    )
    require(
        meta["mu"] == r["mu_final"]
        and meta["h0"] == r["h0"]
        and meta["accepted_outer"] == r["cumulative_accepted_outer"],
        "FINAL_STATE_META",
    )
    require(
        len(meta["PC_provenance"]) <= (1 if r["supervised"] else 2), "PC_LIFETIME_LIMIT"
    )
    require(
        meta["complete_c_sha256"] == r["final_c_sha256"]
        and meta["parameter_sha256"] == r["final_parameters_sha256"],
        "FROZEN_FINAL_HASH_META",
    )
    cap = meta["limits"]
    require(
        counts["K"] <= cap["K"]
        and sum(r["JVP_VJP_counts"].values()) <= cap["JVP_VJP"]
        and counts["trial_loss"] <= cap["trial"]
        and r["new_accepted_outer"] <= cap["accepted"],
        "ACTION_CAP",
    )
    if r["supervised"]:
        require(
            r["Gsolve_count"] == 0
            and r["native_action_counts"]["A"] == r["native_action_counts"]["AH"] == 0,
            "FIT_USES_PDE_ACTION",
        )
    else:
        if r.get("retained_resource_export"):
            require(
                r["Gram_factor"] is None and r["Gsolve_count"] is None,
                "UNRETAINED_GRAM_LIFETIME_PROMOTED",
            )
            require(
                r["failure"]["kind"] == "RESOURCE_WINDOW_UNAVAILABLE"
                and r["original_PT_unmodified"],
                "RESOURCE_EXPORT_NOT_IMMUTABLE_BOUNDARY",
            )
            require(
                not r["numerical_failure_claim"] and not r["normal_budget_stop_claim"],
                "RESOURCE_STOP_MISCLASSIFIED",
            )
        else:
            require(
                r["Gram_factor"]["max_solve_true_relative"] <= 1e-11, "GRAM_ACCURACY"
            )
        require(r["label_identity"] is None, "C_REFERENCE_LEAK")
    history = Path(item["files"]["history"]["path"])
    events, history_scopes = recovery_journals(item)
    current_events, _ = journal(history)
    trials = [x for x in events if x["kind"] in ("GN_TRIAL", "CAUCHY_TRIAL")]
    commits = [x for x in events if x["kind"] == "DURABLE_ACCEPTED"]
    require(len(commits) == r["new_accepted_outer"], "COMMIT_COUNT")
    current_commits = [x for x in current_events if x["kind"] == "DURABLE_ACCEPTED"]
    require(
        len(current_commits)
        == r.get("accepted_updates_this_attempt", r["new_accepted_outer"]),
        "CURRENT_ATTEMPT_COMMIT_COUNT",
    )
    require(
        r["new_accepted_outer"]
        == r.get("inherited_V10_accepted_outer", 0) + len(current_commits),
        "RETAINED_ACCEPTS_LOST_OR_RECOUNTED",
    )
    for x in trials:
        if x["accepted"]:
            require(
                x["g_dot_s"] < 0
                and x["pred"] > 0
                and x["ared"] > 0
                and x["eta"] >= 0.1,
                "INVALID_ACCEPTANCE",
            )
    for x in commits:
        require(x["accepted_update_norm"] > 0, "ZERO_UPDATE_TELEMETRY")
    keep = (
        "route",
        "supervised",
        "stop_reason",
        "failure",
        "counts",
        "JVP_VJP_counts",
        "inherited_counts",
        "inherited_JVP_VJP_counts",
        "cumulative_counts",
        "cumulative_JVP_VJP_counts",
        "new_accepted_outer",
        "inherited_accepted_outer",
        "cumulative_accepted_outer",
        "h0",
        "mu_final",
        "d_G",
        "d_ref",
        "Gram_factor",
        "Gsolve_count",
        "G_matvec_count",
        "JVP_VJP_costs",
        "nested_timers",
        "derivative_cache",
        "budget_frontier",
        "native_action_counts",
        "native_action_costs",
        "initial_audit",
        "final_audit",
        "final_c_sha256",
        "final_parameters_sha256",
        "launcher_charged_seconds",
        "inherited_prefix_seconds",
        "inherited_prior_attempt_seconds",
        "logical_path_seconds",
        "training_data_read_whitelist",
        "actual_artifact_reads",
    )
    value = {k: r[k] for k in keep}
    for k in ("initial_audit", "final_audit"):
        value[k] = compact_audit(r[k])
    value["accepted_updates_this_attempt"] = len(current_commits)
    value["inherited_V10_accepted_outer"] = r.get("inherited_V10_accepted_outer", 0)
    value["count_scope"] = (
        "all completed V10 work lower bounds across this route attempts; incomplete reservations separate"
    )
    value["cost_scope"] = r.get(
        "costs_scope",
        "current attempt only; all whole-attempt walls in resource ledger",
    )
    value["histories"] = history_scopes
    if r.get("fault_recovery"):
        recovery = r["fault_recovery"]
        value["fault_recovery"] = {
            k: recovery[k]
            for k in (
                "selection",
                "durable_final",
                "prior_source_sha",
                "prior_summary",
                "spent_counts_lower_bound",
                "spent_JVP_VJP_lower_bound",
                "incomplete_work_quota_reserve",
                "original_V9_logical_prefix_seconds",
                "unfinished_operations",
                "unknown_interrupted_suboperation_cost",
            )
        }
        require(
            all(
                counts[k] >= v for k, v in recovery["spent_counts_lower_bound"].items()
            ),
            "RECOVERY_SPENT_COUNTERS_RESET",
        )
    value["initialization_identity"] = r["initialization_identity"]
    if r.get("retained_resource_export"):
        for k in (
            "retained_resource_export",
            "numerical_failure_claim",
            "normal_budget_stop_claim",
            "original_PT_unmodified",
            "Gram_lifetime_record",
            "saved_boundary_logical_path_seconds",
            "parameter_origin_source_sha",
            "export_source_sha",
        ):
            value[k] = r[k]
        value["saved_boundary_counts"] = meta["counts"]
        value["saved_boundary_JVP_VJP_counts"] = meta["JVP_VJP_counts"]
    require(
        item["files"]["durable_final"]["sha256"] == r["final_checkpoint"]["sha256"],
        "DURABLE_FINAL_INDEX_MISMATCH",
    )
    value["final_checkpoint"] = dict(
        item["files"]["durable_final"], name=r["final_checkpoint"]["name"]
    )
    value["audit_intervals_seconds"] = [
        x.get("audit_interval_seconds")
        for x in r["audits"]
        if "audit_interval_seconds" in x
    ]
    value["PC_completed_total"] = len(meta["PC_provenance"])
    value["PC_provenance"] = meta["PC_provenance"]
    for pc in value["PC_provenance"]:
        require(
            pc["rank_requested"] == 32
            and 0 < pc["rank_retained"] <= 32
            and pc["K_actions"] == 64
            and pc["rcond"] == 1e-12,
            "PC_RANK_OR_CONSTRUCTION_CHANGED",
        )
        require(
            pc["source_accepted_outer"] <= r["cumulative_accepted_outer"],
            "PC_SOURCE_AFTER_STATE",
        )
        require(
            pc["projected_symmetry_relative"] <= 1e-8 and pc["orthogonality"] <= 1e-8,
            "PC_PROJECTED_QUALIFICATION",
        )
    value["history"] = dict(
        path=str(history),
        sha256=sha(history),
        full_K_trajectory="ignored artifact; not copied to Git JSON",
    )
    value["work_events"] = {
        k: dict(
            started=sum(
                x.get("operation") == k and x.get("phase") == "begin" for x in events
            ),
            ended=sum(
                x.get("operation") == k and x.get("phase") == "end" for x in events
            ),
        )
        for k in (
            "K",
            "CG",
            "CG_TRUE_RESIDUAL",
            "PC_BUILD",
            "PC_K_OMEGA",
            "PC_KU",
            "PC_EIGH",
            "TRUE_TRIAL",
            "COMMIT",
        )
    }
    for kind, counts_row in value["work_events"].items():
        require(
            counts_row["ended"] <= counts_row["started"],
            "WORK_EVENT_END_WITHOUT_BEGIN:" + kind,
        )
        end_rows = [
            x for x in events if x.get("operation") == kind and x.get("phase") == "end"
        ]
        counts_row["completed_nested_seconds"] = sum(x["seconds"] for x in end_rows)
        counts_row["unfinished_begins"] = counts_row["started"] - counts_row["ended"]
        counts_row["scope"] = (
            "nested measured duration; not added again to launcher wall"
        )
    value["PC_quota_consumed_after_rollback"] = sum(
        x["constructions"]
        for x in events
        if x["kind"] == "PC_COMPLETED_QUOTA_PRESERVED_AFTER_ROLLBACK"
    )
    value["accepted_state_boundaries"] = len(commits)
    value["new_K_after_last_accepted_boundary"] = counts["K"] - (
        commits[-1]["counts"]["K"] if commits else 0
    )
    require(
        value["new_K_after_last_accepted_boundary"] >= 0, "NEGATIVE_UNCOMMITTED_WORK"
    )
    value["inner_CG_summary"] = dict(
        completed=sum(
            x.get("operation") == "CG" and x.get("phase") == "end" for x in events
        ),
        iterations=distribution(
            [
                x["iterations"]
                for x in events
                if x.get("operation") == "CG" and x.get("phase") == "end"
            ]
        ),
        true_relative=distribution(
            [
                x["true_relative"]
                for x in events
                if x.get("operation") == "CG" and x.get("phase") == "end"
            ]
        ),
        early_budget_returns=sum(
            bool(x.get("budget_frontier_early"))
            for x in events
            if x.get("operation") == "CG" and x.get("phase") == "end"
        ),
        scope="CG end rows, including proposals interrupted after inner solve; not only accepted trials",
    )
    value["PC_deferred_by_budget"] = sum(
        x["kind"] == "PC_DEFERRED_BY_BUDGET" for x in events
    )
    return value, trials


def compare(item, supervised):
    r = item["result"]
    physics = r["physics"]
    modes = load("e1_fe")["result"]["identity"]["modes"]
    power_inventory(physics["records"], modes)
    gates = {
        name: physical_gate(
            row,
            physics["records"][name],
            physics["records"]["REFERENCE"],
            supervised=supervised,
            natural_scale=physics["reference_scattered_norms"][0],
        )
        for name, row in r["routes"].items()
    }
    name = "fit_comparison" if supervised else "pde_comparison"
    write_comparison(name, r, gates, modes, version=10)
    samples = []
    for route, row in r["routes"].items():
        record = physics["records"][route]
        ref = physics["records"]["REFERENCE"]
        for kind in ("total", "scattered"):
            for quantity, field in (("E", "E"), ("H", "H_code")):
                a, b = (
                    vector(x["selected_" + kind + "_" + field]).reshape(6, 3)
                    for x in (record, ref)
                )
                for point in range(6):
                    error = row["comparisons"]["errors"][
                        "selected_" + kind + "_" + quantity + "_point_" + str(point)
                    ]
                    for component in range(3):
                        samples.append(
                            dict(
                                route=route,
                                kind=kind,
                                quantity=quantity,
                                point=point,
                                component="xyz"[component],
                                point_nm=json.dumps(record["points_nm"][point]),
                                real=float(a[point, component].real),
                                imag=float(a[point, component].imag),
                                reference_real=float(b[point, component].real),
                                reference_imag=float(b[point, component].imag),
                                absolute_component_difference=float(
                                    abs(a[point, component] - b[point, component])
                                ),
                                point_vector_absolute=error["absolute"],
                                point_vector_denominator=error["denominator"],
                                point_vector_relative=error["relative"],
                            )
                        )
    if samples:
        with (RECORDS / (name + "_samples_v10.csv")).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(samples[0]))
            writer.writeheader()
            writer.writerows(samples)
    regions = []
    for route, row in r["routes"].items():
        for region, value in (
            {
                kind + ":" + key: value
                for kind in ("region_scattered", "region_total")
                for key, value in row.get(kind, {}).items()
            }
        ).items():
            regions.append(
                dict(
                    route=route,
                    region=region,
                    raw=json.dumps(value, ensure_ascii=False),
                )
            )
    with (RECORDS / (name + "_regions_v10.csv")).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["route", "region", "raw"])
        w.writeheader()
        w.writerows(regions)
    research = {}
    if not supervised:
        for name, gate in gates.items():
            if not name.startswith("V10-"):
                continue
            old_name = ("V9-PHASE" if "PHASE" in name else "V9-PLAIN") + "-DAMPED-GN"
            prior = gates[old_name]
            native_ratio = prior["equation_audit"]["native_relative"] / max(
                gate["equation_audit"]["native_relative"], 1e-30
            )
            aug_ratio = prior["equation_audit"]["augmented_relative"] / max(
                gate["equation_audit"]["augmented_relative"], 1e-30
            )
            small_field = (
                max(
                    gate["errors"][key]["relative"]
                    for key in ("scattered_L2", "scattered_scaled_curl")
                )
                <= 0.1
            )
            research[name] = dict(
                native_improvement_factor=native_ratio,
                augmented_improvement_factor=aug_ratio,
                scattered_L2_and_curl_le_01=small_field,
                passed=bool(min(native_ratio, aug_ratio) >= 10 and small_field),
                extra_time_used=True,
                same_cost_algorithm_superiority_claim=False,
            )
    return dict(
        routes=gates,
        research_signal=research,
        comparison_source=item["source_sha"],
        raw_result_path=item["files"]["result"]["path"],
        raw_result_sha256=item["files"]["result"]["sha256"],
        raw_scope="full complex channels/samples, fields, power, regions and denominators retained once in ignored compare artifact",
    )


def main():
    ledger = resource_costs()
    compact_write("resource_costs_v10.json", ledger)
    if "--resources-only" in sys.argv:
        print(json.dumps({k: ledger[k] for k in ("new_seconds", "cumulative_seconds")}))
        return
    a = load("v10_state_and_work_audit")
    for source, target in (
        ("state_identity", "state_identity_v10.json"),
        ("inner_summary", "inner_summary_v10.json"),
    ):
        compact_write(target, read(a["files"][source]["path"]))
    shutil.copyfile(
        a["files"]["outer_history"]["path"], RECORDS / "v9_outer_summary_v10.csv"
    )
    ch = load("v10_derivative_checks_tangent_repair")["result"]
    b = load("v10_derivative_benchmark")
    with Path(b["files"]["benchmark"]["path"]).open() as stream:
        csv_samples = list(csv.DictReader(stream))
    require(len(csv_samples) == len(b["result"]["samples"]), "BENCHMARK_CSV_ROW_COUNT")
    for saved, raw in zip(csv_samples, b["result"]["samples"]):
        require(
            saved["state"] == raw["state"]
            and saved["implementation"] == raw["implementation"]
            and saved["warmup"] == str(raw["warmup"]),
            "BENCHMARK_CSV_LAYOUT",
        )
        require(
            all(
                close(float(saved[k]), raw[k])
                for k in (
                    "repeat",
                    "K_count",
                    "seed",
                    "build_seconds",
                    "gradient_seconds",
                    "K16_seconds",
                    "release_seconds",
                    "total_seconds",
                    "cache_bytes",
                )
            ),
            "BENCHMARK_CSV_NUMERIC_FIELDS",
        )
    acceleration = benchmark_gates(ch["states"], b["result"])
    prior = {}
    for stage in ("v10_derivative_checks", "v10_derivative_checks_repair"):
        item = load(stage)
        prior[stage] = dict(
            source_sha=item["source_sha"],
            states=item["result"]["states"],
            Gram_factor=item["result"]["Gram_factor"],
            raw_checks=item["files"]["checks"],
        )
    compact_write(
        "cache_checks_v10.json",
        dict(
            states=ch["states"],
            Gram_factor=ch["Gram_factor"],
            gates=acceleration,
            prior_failed_qualification=prior,
        ),
    )
    shutil.copyfile(
        b["files"]["benchmark"]["path"], RECORDS / "derivative_benchmark_v10.csv"
    )
    trains, outer = {}, []
    indices = {
        stage: load(stage)
        for stage in STAGES
        if (
            ROOT / "benchmarks/artifacts/task42extra" / ("index_" + stage + ".json")
        ).exists()
    }
    for stage, item in indices.items():
        if stage in (
            "v10_plain_cached_gn",
            "v10_phase_cached_gn",
            "v10_plain_cached_fit_gn",
            "v10_phase_cached_fit_gn",
            "v10_phase_resource_freeze",
        ):
            trains[stage], rows = training(item)
            for x in rows:
                cg = x.get("cg") or {}
                outer.append(
                    dict(
                        stage=stage,
                        attempt_run_id=x["attempt_run_id"],
                        source_sha=x["actual_source_sha"],
                        kind=x["kind"],
                        accepted=x["accepted"],
                        mu=x["mu"],
                        pred=x["pred"],
                        ared=x.get("ared"),
                        eta=x.get("eta"),
                        cg_iterations=cg.get("iterations"),
                        cg_true_relative=cg.get("true_relative"),
                        PC_source_outer=x.get("PC_source_outer"),
                        elapsed_seconds=x["elapsed_charged_seconds"],
                    )
                )
    compact_write("training_v10.json", dict(routes=trains))
    original_inner = read(a["files"]["inner_summary"]["path"])
    compact_write(
        "inner_summary_v10.json",
        dict(
            original_V9=original_inner,
            current_V10={
                stage: {
                    key: row[key]
                    for key in (
                        "route",
                        "new_accepted_outer",
                        "cumulative_accepted_outer",
                        "counts",
                        "JVP_VJP_counts",
                        "PC_completed_total",
                        "PC_provenance",
                        "PC_deferred_by_budget",
                        "PC_quota_consumed_after_rollback",
                        "new_K_after_last_accepted_boundary",
                        "inner_CG_summary",
                        "work_events",
                        "histories",
                        "count_scope",
                        "cost_scope",
                    )
                }
                for stage, row in trains.items()
            },
            full_K_trajectory="ignored hash-bound originals only; no replay to fill missing history",
        ),
    )
    with (RECORDS / "accepted_steps_v10.csv").open("w", newline="") as f:
        fields = (
            list(outer[0]) if outer else ["stage", "accepted", "pred", "ared", "eta"]
        )
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(outer)
    comparisons = {}
    for stage, supervised in (("v10_gn_compare", False), ("v10_fit_compare", True)):
        if stage in indices:
            comparisons["D" if supervised else "C"] = compare(
                indices[stage], supervised
            )
    compact_write("comparison_v10.json", comparisons)
    runindex = {
        s: dict(
            source_sha=x["source_sha"],
            run_directory=x["run_directory"],
            files=x["files"],
            status=x["result"]["status"],
        )
        for s, x in indices.items()
    }
    attempts = [
        dict(
            stage=r["stage"],
            path=r["path"],
            source_sha=r["source_sha"],
            input_sha256=r["input_sha256"],
            classification=r["classification"],
            seconds=r["seconds"],
            descendants_cleared=r["descendants_cleared"],
            raw_hashes=r["raw_hashes"],
        )
        for r in ledger["entries"]
        if "stage" in r
    ]
    compact_write(
        "run_index_v10.json",
        dict(
            stages=runindex,
            attempts=attempts,
            review_commit="47317bb648d5e2237657f8b6c75c239ab5bf55c5",
        ),
    )
    compact_write(
        "gate_decisions_v10.json",
        dict(
            acceleration=acceleration,
            C=comparisons.get("C", {}).get("routes", {}),
            C_research_signal=comparisons.get("C", {}).get("research_signal", {}),
            D=comparisons.get("D", {}).get("routes", {}),
            production_merge=False,
        ),
    )
    print(
        json.dumps(
            dict(
                status="V10_COMPACT_RECORD_ARITHMETIC_COMPLETE",
                stages=len(indices),
                new_seconds=ledger["new_seconds"],
            )
        )
    )


if __name__ == "__main__":
    main()
