"""Independent V9 frozen-record arithmetic, label and budget checker.

No optimizer, FE assembly, inverse/factor or reference solve is invoked here.
"""

import json
from pathlib import Path
import sys

import numpy as np

from benchmarks.check_task42extra_v2 import (
    ROOT,
    RESULTS,
    CHECKS,
    read,
    write,
    sha,
    close,
)
from benchmarks.check_task42extra_v7 import comparison_gate, reference_gate
from benchmarks.check_task42extra_v8 import (
    physical_gate,
    require,
    power_inventory,
    write_comparison,
)
from src.runners.feinn_gn_campaign import STAGES, LIMITS, OLD_SECONDS


def load(stage):
    path = ROOT / "benchmarks/artifacts/task42extra" / ("index_" + stage + ".json")
    item = read(path)
    base = (ROOT / "benchmarks/artifacts/task42extra").resolve()
    for name, entry in item["files"].items():
        raw = Path(entry["path"]).resolve()
        require(
            raw.is_relative_to(base) and sha(raw) == entry["sha256"],
            "FROZEN_FILE_HASH_" + stage + "/" + name,
        )
    return item


def renamed(value, pairs):
    def word(text):
        for a, b in pairs:
            text = text.replace(a, b)
        return text

    if isinstance(value, dict):
        return {word(k): renamed(v, pairs) for k, v in value.items()}
    if isinstance(value, list):
        return [renamed(v, pairs) for v in value]
    return word(value) if isinstance(value, str) else value


def gn_qualification(result):
    require(result["d_G"] > 0, "NONPOSITIVE_D_G")
    factor = result["Gram_factor"]
    require(factor["max_solve_true_relative"] <= 1e-11, "GRAM_ACCURACY")
    for name, row in result["routes"].items():
        require(row["coefficient_identity"]["relative"] <= 1e-10, "ANCHOR_C_CHANGED")
        require(row["input_frozen"], "PROBE_MUTATES_INPUT")
        require(
            len(row["direction_checks"]) == len(row["K_checks"]) == 3,
            "REAL_WITNESSES_MISSING",
        )
        for direction in row["direction_checks"]:
            defects = [x["relative"] for x in direction["difference"]]
            require(
                any(max(defects[j : j + 2]) <= 1e-5 for j in range(2)), "JVP_DIFFERENCE"
            )
            require(
                direction["real_adjoint"] <= 1e-10
                and direction["analytic_tangent"]["relative"] <= 1e-10,
                "REAL_ADJOINT_OR_TANGENT",
            )
        for witness in row["K_checks"]:
            require(
                witness["symmetry"] <= 1e-8
                and witness["positive_energy_pair"] <= 1e-8
                and witness["quadratic"] >= 0,
                "K_QUALIFICATION",
            )
        require(
            max(row[k]["relative"] for k in ("batch_c", "batch_JVP", "batch_VJP"))
            <= 1e-10
            and row["batch_loss_relative"] <= 1e-10,
            "BATCH_IDENTITY",
        )
    return dict(
        qualified=True, d_G=result["d_G"], Gram_factor=factor, routes=result["routes"]
    )


def gn_training(item):
    r = item["result"]
    supervised = r["supervised"]
    count, jac = r["counts"], r["JVP_VJP_counts"]
    meta = r["final_checkpoint"]["metadata"]
    require(
        r["inherited_committed_Adam_updates"] == 500
        and r["new_Adam_updates"] == 0
        and not r["old_optimizer_history_loaded"],
        "ADAM_OR_OLD_OPTIMIZER_REPLAY",
    )
    require(
        r["reference_used_for_training"]
        == r["features_reference_exposed"]
        == supervised
        and r["pde_only_solve"] != supervised,
        "LABEL_LEAKAGE",
    )
    require(
        not r["production_initialization_allowed"]
        and not r["Maxwell_factor_created"]
        and not r["global_Maxwell_matrix_created"],
        "PRODUCTION_OR_MAXWELL_FALLBACK",
    )
    require(
        set(r["actual_artifact_reads"]).issubset(r["training_data_read_whitelist"]),
        "UNAUTHORIZED_TRAIN_READ",
    )
    require(
        meta["accepted_outer"] <= (60 if supervised else 120)
        and count["K"] <= (1000 if supervised else 4000),
        "OUTER_OR_K_BUDGET",
    )
    require(
        sum(jac.values()) <= (2500 if supervised else 8000)
        and count["trial_loss"] <= (256 if supervised else 512),
        "JVP_OR_TRIAL_BUDGET",
    )
    require(
        r["logical_path_seconds"] <= (3600 if supervised else 10800),
        "LOGICAL_PREFIX_TIME",
    )
    require(
        r["final_checkpoint"]["sha256"] == item["files"]["durable_final"]["sha256"],
        "FINAL_DURABLE_BINDING",
    )
    require(
        0 < r["h0"] and 1e-12 * r["h0"] <= r["mu_final"] <= 1e6 * r["h0"],
        "DAMPING_LIMIT",
    )
    if supervised:
        require(r["Gram_factor"] is None and r["Gsolve_count"] == 0, "FIT_USES_INVERSE")
        require(
            r["native_action_counts"]["A"] == r["native_action_counts"]["AH"] == 0,
            "FIT_CLOSURE_USES_MAXWELL_ACTION",
        )
    else:
        require(
            r["d_G"] > 0 and r["Gram_factor"]["max_solve_true_relative"] <= 1e-11,
            "PDE_GSOLVE",
        )
        require(
            not any(
                "reference_state" in x or "reference_fit" in x
                for x in r["actual_artifact_reads"]
            ),
            "PDE_LABEL_READ",
        )
    history = [
        json.loads(line)
        for line in Path(item["files"]["history"]["path"]).read_text().splitlines()
    ]
    for row in history:
        if row["kind"] in ("GN_TRIAL", "CAUCHY_TRIAL") and row.get("ared") is not None:
            require(close(row["eta"], row["ared"] / row["pred"]), "ETA_ARITHMETIC")
            require(
                row["accepted"] == (row["ared"] > 0 and row["eta"] >= 0.1),
                "ACCEPTANCE_POLICY",
            )
        if row["kind"] == "GN_TRIAL":
            require(0 <= row["damping_trial"] < 8, "DAMPING_TRIAL_COUNT")
            require(row["cg"]["iterations"] <= row["cg"]["max_iter"] <= 80, "CG_BUDGET")
        if row["kind"] == "PC_BUILD":
            require(
                row["rank_requested"] == 32
                and row["seed"] == 421902
                and row["rcond"] == 1e-12
                and row["K_actions"] <= 64,
                "PC_SCAN_OR_COST",
            )
    require(len(r["PC_builds"]) <= (1 if supervised else 2), "PC_REBUILD_BUDGET")
    return dict(
        source_sha=item["source_sha"],
        result=r,
        trial_and_accepted_history=history,
        retained_checkpoint_index=read(item["files"]["checkpoint_index"]["path"]),
    )


def research_signal(new, old):
    nr, oldr = new["equation_audit"], old["equation_audit"]
    field = all(
        new["errors"][k]["relative"] <= 0.1
        and new["errors"][k]["relative"] < old["errors"][k]["relative"]
        for k in ("scattered_L2", "scattered_scaled_curl")
    )
    residual = all(
        nr[k] <= oldr[k] / 10 for k in ("native_relative", "augmented_relative")
    )
    return dict(
        status="GN_RESEARCH_SIGNAL" if field and residual else "NO_GN_RESEARCH_SIGNAL",
        signal=field and residual,
        native_reduction=oldr["native_relative"] / nr["native_relative"],
        augmented_reduction=oldr["augmented_relative"] / nr["augmented_relative"],
        field_conditions_pass=field,
        residual_conditions_pass=residual,
    )


def compare_gate(item, *, supervised):
    r = item["result"]
    physics = r["physics"]
    reference = physics["records"]["REFERENCE"]
    checked = {}
    natural = physics["reference_scattered_norms"][0]
    for name, row in r["routes"].items():
        checked[name] = physical_gate(
            row,
            physics["records"][name],
            reference,
            supervised=supervised,
            natural_scale=natural,
        )
        if "COMMON-WALL" in name:
            checked[name]["category"] = "RETAINED_COMMON_WALL_DIAGNOSTIC"
            checked[name]["selection"] = row["shared_work_point"]
    signals = {}
    if not supervised:
        for name, row in r["routes"].items():
            if name.endswith("-DAMPED-GN"):
                a, b = name + "-COMMON-WALL", name + "-V8-COMMON-WALL"
                if a not in checked or b not in checked:
                    signals[name] = dict(status="NOT_RETAINED", signal=False)
                    continue
                new, old = checked[a], checked[b]
                signals[name] = dict(
                    **research_signal(new, old),
                    same_wall_new=r["routes"][a]["shared_work_point"],
                    same_wall_V8=r["routes"][b]["shared_work_point"],
                    labels_do_not_select_checkpoint=True,
                )
    return dict(
        routes=checked,
        research_signals=signals,
        raw_index_source=item["source_sha"],
        raw_frozen_compare_result=r,
        raw_scope="compact complex samples/channels, energies, powers, regions and denominators; no full FE arrays",
    )


def resource_costs():
    rows = []
    for path in sorted(RESULTS.glob("task42extra_v9_*/run_summary.json")):
        r = read(path)
        manifest = read(path.parent / "run_manifest.json")
        stage = manifest["stage"]
        rows.append(
            dict(
                path=str(path),
                group=STAGES[stage][2],
                stage=stage,
                source_sha=manifest["source_sha"],
                input_sha256=manifest["input_sha256"],
                seconds=max(
                    r["elapsed_seconds"],
                    r.get("launch_to_summary_seconds_monotonic", 0),
                ),
                peak_tree_RSS_bytes=r["sampled_process_tree_rss_peak_bytes"],
                own_swap_bytes=r["sampled_process_tree_swap_peak_bytes"],
                classification=r["classification"],
                descendants_cleared=r["descendants_cleared"],
                summary_sha256=sha(path),
                launch_envelope=r.get("launch_envelope"),
                tmux_management_scope="outside numerical tree; separate durable overhead record",
            )
        )
    for path in sorted(CHECKS.glob("v9_*/summary.json")):
        r = read(path)
        group = path.parent.name[3:4].upper()
        rows.append(
            dict(
                path=str(path),
                group=group if group in LIMITS else "E",
                seconds=r["elapsed_seconds"],
                peak_tree_RSS_bytes=r["sampled_process_tree_rss_peak_bytes"],
                own_swap_bytes=r["sampled_process_tree_swap_peak_bytes"],
                classification=r["classification"],
                descendants_cleared=r["descendants_cleared"],
                summary_sha256=sha(path),
            )
        )
    totals = {
        group: sum(x["seconds"] for x in rows if x["group"] == group)
        for group in LIMITS
    }
    # Conservative bound for direct short metadata/commit audits and final tail;
    # not an extra measured run and not added to nested factor/closure timers.
    tail = 120.0
    totals["E"] += tail
    raw_used = sum(x["seconds"] for x in rows)
    used = raw_used + tail
    require(
        used <= 43200 and all(totals[g] <= LIMITS[g] for g in LIMITS),
        "CAMPAIGN_TIME_BUDGET",
    )
    require(
        all(x["own_swap_bytes"] == 0 and x["descendants_cleared"] for x in rows),
        "OWN_SWAP_OR_CLEARANCE",
    )
    require(
        all(
            x["peak_tree_RSS_bytes"] < (2 if "/checks/" in x["path"] else 16) * 2**30
            for x in rows
        ),
        "TREE_MEMORY_BUDGET",
    )
    servers = []
    for path in sorted(
        (ROOT / "tmp/task42extra/durable").glob("v9_*/terminal_identity.json")
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
    require(
        all(x.get("VmSwap", 0) == 0 for x in servers), "TMUX_MANAGEMENT_SWAP_AT_LAUNCH"
    )
    return dict(
        schema="task42extra.resource-costs.v9",
        old_seconds=OLD_SECONDS,
        new_seconds=used,
        cumulative_seconds=OLD_SECONDS + used,
        new_limit_seconds=43200,
        measured_stage_and_auxiliary_seconds=raw_used,
        direct_and_final_tail_allowance_seconds=tail,
        groups_seconds=totals,
        groups_limits_seconds=LIMITS,
        entries=rows,
        old_failed_and_replayed_costs_preserved=True,
        historical_prefix_not_double_charged_to_project=True,
        old_lost_attempt_seconds_preserved=3284,
        management_server_launch_samples=servers,
        management_scope="own tmux server outside numeric tree; launch snapshots, not continuous peak; whole stage wall charged",
        no_continuous_kernel_cgroup_limit_claim=True,
        memory_scope="sampled simultaneous numerical process tree RSS, not payload or sum of peaks",
    )


def main():
    if "--resources-only" in sys.argv:
        value = resource_costs()
        write("resource_costs_v9.json", value)
        print(
            json.dumps(
                dict(
                    status="V9_RESOURCE_LEDGER_UPDATED",
                    new_seconds=value["new_seconds"],
                    cumulative_seconds=value["cumulative_seconds"],
                )
            )
        )
        return
    checks = gn_qualification(load("v9_gn_checks")["result"])
    a = load("v9_p5_reference")["result"]
    from src.solvers.feinn_native import load_native

    packet = load_native(load("v9_p5_checks")["files"]["native"]["path"])
    with np.load(
        load("v9_p5_reference")["files"]["reference"]["path"], allow_pickle=False
    ) as state:
        independent = packet.audit(np.array(state["c_scattered"]))
    del packet
    p5 = reference_gate(a, independent)
    require(
        a["independent_Basix_total_relative"] <= 1e-10
        and a["degree"] == 5
        and sum(a["independent_families"].values()) == 146400,
        "P5_INDEPENDENT_IDENTITY",
    )
    ladder_raw = load("v9_p_ladder_compare")["result"]
    ladder = comparison_gate(
        renamed(
            ladder_raw,
            [("p4", "@LEFT@"), ("p5", "p4"), ("@LEFT@", "p3"), ("P4_P5", "P3_P4")],
        )
    )
    ladder = renamed(ladder, [("p4", "p5"), ("p3", "p4"), ("P3_P4", "P4_P5")])
    training = {
        name: gn_training(load(name)) for name in ("v9_plain_gn", "v9_phase_gn")
    }
    pde = compare_gate(load("v9_gn_compare"), supervised=False)
    modes = load("e1_fe")["result"]["identity"]["modes"]
    power_inventory(load("v9_gn_compare")["result"]["physics"]["records"], modes)
    write_comparison(
        "pde_gn", load("v9_gn_compare")["result"], pde["routes"], modes, version=9
    )
    fit = None
    if load("v9_gn_compare")["result"]["conditional_D_required"]:
        training.update(
            {
                name: gn_training(load(name))
                for name in ("v9_plain_fit_gn", "v9_phase_fit_gn")
            }
        )
        fit = compare_gate(load("v9_fit_gn_compare"), supervised=True)
        power_inventory(
            load("v9_fit_gn_compare")["result"]["physics"]["records"], modes
        )
        write_comparison(
            "fit_gn",
            load("v9_fit_gn_compare")["result"],
            fit["routes"],
            modes,
            version=9,
        )
    write(
        "inner_solver_history_v9.json",
        dict(schema="task42extra.GN-inner-history.v9", routes=training),
    )
    write("pde_comparison_v9.json", pde)
    if fit is not None:
        write("fit_comparison_v9.json", fit)
    write(
        "gate_decisions_v9.json",
        dict(
            schema="task42extra.raw-gates.v9",
            gn_interface=checks,
            p5_reference=p5,
            p4_p5=ladder,
            PDE=pde,
            FIT=fit,
        ),
    )
    write("resource_costs_v9.json", resource_costs())
    run_index = {}
    for stage in STAGES:
        path = ROOT / "benchmarks/artifacts/task42extra" / ("index_" + stage + ".json")
        if path.exists():
            run_index[stage] = dict(
                path=str(path),
                sha256=sha(path),
                source_sha=read(path)["source_sha"],
                run_directory=read(path)["run_directory"],
                files=read(path)["files"],
            )
    write(
        "run_index_v9.json", dict(schema="task42extra.run-index.v9", stages=run_index)
    )
    print(
        json.dumps(
            dict(
                status="RAW_V9_CHECKS_COMPLETE",
                p5_qualified=p5["qualified"],
                p4_p5=ladder["status"],
                PDE_routes={k: v["category"] for k, v in pde["routes"].items()},
                FIT_ran=fit is not None,
            )
        )
    )


if __name__ == "__main__":
    main()
