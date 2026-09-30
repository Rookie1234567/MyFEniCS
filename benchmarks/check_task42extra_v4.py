"""Read frozen V4 artifacts and recompute decisions; no optimizer or PDE solve."""

import csv
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy import sparse

from benchmarks.check_task42extra_v2 import (
    ARTIFACTS,
    CHECKS,
    RECORDS,
    RESULTS,
    ROOT,
    channel_error,
    close,
    complex_array,
    index,
    read,
    resource_record,
    sha,
    write,
)
from src.solvers.neural_fe_action_packet import array_hash

ROUTE = "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"
STAGES = ("v4_boundary_checks", ROUTE, "v4_fit_reconstruct", "v4_fit_compare_only")
POLICY = dict(
    reference_used_for_training=True,
    pde_only_solve=False,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
)
OLD_SECONDS = 33070.52670758043


def policy(item):
    if any(bool(item[k]) != v for k, v in POLICY.items()):
        raise ValueError("reference-exposed policy lost")


def equal_state(a, b):
    """Exact CPU checkpoint identity, including nested optimizer state."""
    import torch

    if isinstance(a, torch.Tensor):
        return isinstance(b, torch.Tensor) and torch.equal(a, b)
    if isinstance(a, np.ndarray):
        return isinstance(b, np.ndarray) and np.array_equal(a, b)
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal_state(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return (
            type(a) is type(b)
            and len(a) == len(b)
            and all(equal_state(x, y) for x, y in zip(a, b, strict=True))
        )
    return a == b


def checkpoint_records(fit, saved_p, saved_c):
    from src.solvers.optimization_checkpoint import load_checkpoint

    entry = fit["files"]["checkpoint_index"]
    raw = read(entry["path"])
    directory = Path(entry["path"]).parent / "durable_checkpoints"
    pointer = read(directory / "current.json")
    if pointer["current"] != raw["current"] or not pointer["previous"]:
        raise ValueError("checkpoint pointer does not identify two full generations")
    rows = []
    for record in raw["checkpoints"]:
        path = directory / record["name"]
        if record["retained"] != path.exists():
            raise ValueError("retained checkpoint inventory differs")
        row = {
            k: record[k]
            for k in ("generation", "name", "sha256", "bytes", "pinned", "retained")
        }
        meta = record["metadata"]
        row.update(
            state_kind=meta["state_kind"],
            counts=meta["counts"],
            committed_complete_fit_closures=meta["committed_complete_fit_closures"],
            logical_path_closures=meta["logical_path_closures"],
            accepted_update_norm=meta.get("accepted_update_norm"),
            complete_c_sha256=meta.get("complete_c_sha256"),
        )
        if path.exists():
            state = load_checkpoint(path, record["sha256"])
            if (
                state["metadata"] != meta
                or state["parameter_order"] != record["parameter_order"]
            ):
                raise ValueError("checkpoint payload and metadata disagree")
            policy(meta)
            params = np.concatenate(
                [
                    state["model"][x["name"]].numpy().ravel()
                    for x in state["parameter_order"]
                ]
            )
            if params.shape != (8966,) or state["optimizer_class"] != "LBFGS":
                raise ValueError("checkpoint network or optimizer changed")
            groups = state["optimizer"]["param_groups"]
            expected = read(RECORDS / "replay_design_v4.json")["optimizer"]
            if len(groups) != 1 or any(groups[0][k] != v for k, v in expected.items()):
                raise ValueError("L-BFGS hyperparameters changed")
            row["parameters_sha256"] = array_hash(params)
            row["buffers_sha256"] = {
                k: array_hash(state["model"][k].numpy())
                for k in ("center", "half_width")
            }
            if row["buffers_sha256"] != meta["buffers_sha256"]:
                raise ValueError("saved buffers changed")
            if (
                "complete_c" in state
                and array_hash(state["complete_c"]) != meta["complete_c_sha256"]
            ):
                raise ValueError("saved complete FE coefficient hash changed")
            history = state["optimizer"]["state"]
            if record["generation"] == 0 and history:
                raise ValueError("boundary L-BFGS was not fresh")
            if history:
                h = next(iter(history.values()))
                if len(h.get("old_dirs", [])) > 20 or len(h.get("old_stps", [])) > 20:
                    raise ValueError("unbounded L-BFGS history")
                row["optimizer_inner_iterations"] = h.get("n_iter")
                row["optimizer_func_evals"] = h.get("func_evals")
        rows.append(row)
    final = load_checkpoint(
        directory / raw["current"]["name"], raw["current"]["sha256"]
    )
    previous = load_checkpoint(
        directory / pointer["previous"]["name"], pointer["previous"]["sha256"]
    )
    actual_p = np.concatenate(
        [final["model"][x["name"]].numpy().ravel() for x in final["parameter_order"]]
    )
    if not np.array_equal(actual_p, saved_p) or not np.array_equal(
        final["complete_c"], saved_c
    ):
        raise ValueError("durable final and frozen NPZ differ")
    if not all(
        equal_state(final[k], previous[k])
        for k in (
            "model",
            "optimizer",
            "gradients",
            "torch_rng",
            "numpy_rng",
            "python_rng",
        )
    ):
        raise ValueError("budget rollback did not match last complete boundary")
    if len(rows) != fit["result"]["counts"]["committed_outer_steps"] + 2:
        raise ValueError("every complete outer step was not published")
    out = dict(
        schema="task42extra.checkpoint-index.v4",
        raw_index=entry,
        pointer_sha256=sha(directory / "current.json"),
        final=raw["current"],
        previous=pointer["previous"],
        checkpoints=rows,
        parameter_order=final["parameter_order"],
        final_optimizer_matches_last_complete_boundary=True,
        original_Adam500_parameter_only=True,
        old817_parameters_optimizer="NOT_RETAINED",
        optimizer_state_saved=True,
        resumability_qualified_by_small_problem_tests=True,
        automatic_resume_authorized=False,
        **POLICY,
    )
    write("checkpoint_index_v4.json", out)
    return out


def resource_costs(indices):
    stages = {}
    for stage, item in indices.items():
        directory = Path(item["run_directory"])
        row = resource_record(directory)
        row.update(
            run_manifest_sha256=sha(directory / "run_manifest.json"),
            resource_baseline_sha256=sha(directory / "resource_baseline.json"),
            resource_jsonl_sha256=sha(directory / "supervision/resources.jsonl"),
            input_original_sha256=sha(directory / "input_original.dat"),
            resolved_config_sha256=sha(directory / "resolved_config.json"),
        )
        row["charged_seconds"] = max(
            row["supervised_seconds"], row["launch_to_summary_seconds_derived"]
        )
        peak_rss = peak_swap = 0
        with (directory / "supervision/resources.jsonl").open() as stream:
            for line in stream:
                sample = json.loads(line)
                peak_rss = max(peak_rss, sample["rss_bytes"])
                peak_swap = max(peak_swap, sample["swap_bytes"])
        if (peak_rss != row["peak_simultaneous_tree_RSS_bytes"]
            or peak_swap != row["own_tree_swap_peak_bytes"]):
            raise ValueError("tree RSS/swap summary differs from raw samples")
        if not row["descendants_cleared"] or row["own_tree_swap_peak_bytes"] != 0:
            raise ValueError("formal tree cleanup or swap contract failed")
        stages[stage] = row
    checks = []
    for directory in sorted(CHECKS.glob("v4_*")):
        path = directory / "summary.json"
        # The current invocation has no summary until it returns. Its cost is
        # covered by the explicit conservative direct/final tail allowance.
        if not path.exists():
            checks.append(
                dict(
                    directory=str(directory),
                    status="RUNNING_OR_NO_SUMMARY",
                    charged_seconds=0,
                )
            )
            continue
        r = read(path)
        checks.append(
            dict(
                directory=str(directory),
                summary_sha256=sha(path),
                classification=r["classification"],
                leader_exit_code=r["leader_exit_code"],
                elapsed_seconds=r["elapsed_seconds"],
                charged_seconds=r["elapsed_seconds"],
                peak_simultaneous_tree_RSS_bytes=r[
                    "sampled_process_tree_rss_peak_bytes"
                ],
                own_tree_swap_peak_bytes=r["sampled_process_tree_swap_peak_bytes"],
                descendants_cleared=r["descendants_cleared"],
            )
        )
    formal = sum(x["charged_seconds"] for x in stages.values())
    auxiliary = sum(x["charged_seconds"] for x in checks)
    batch = formal + auxiliary + 120
    supervisor_wall = stages[ROUTE]["supervised_seconds"]
    management = (
        ROOT / "tmp/task42extra/durable/v4_formal_replay/management_samples.jsonl"
    )
    samples = [json.loads(line) for line in management.read_text().splitlines()]
    out = dict(
        schema="task42extra.resource-costs.v4",
        cutoff="all available summaries plus conservative 120s direct/current-check/final allowance",
        previous_conservative_seconds=OLD_SECONDS,
        old_lost_attempt_charged_seconds=3284,
        V4_formal_seconds=formal,
        V4_auxiliary_seconds=auxiliary,
        direct_and_final_allowance_seconds_conservative=120,
        V4_batch_seconds=batch,
        V4_remaining_seconds=14400 - batch,
        original_total_conservative_seconds=OLD_SECONDS + batch,
        original_16h_remaining_seconds=57600 - OLD_SECONDS - batch,
        formal_stages=stages,
        auxiliary_attempts=checks,
        all_supervised_peak_RSS_bytes=max(
            x.get("peak_simultaneous_tree_RSS_bytes", 0)
            for x in [*stages.values(), *checks]
        ),
        own_sampled_swap_zero=all(
            x.get("own_tree_swap_peak_bytes", 0) == 0
            for x in [*stages.values(), *checks]
        ),
        management_server_samples=samples,
        management_samples_sha256=sha(management),
        management_scope="tmux server outside numerical tree; sparse samples only, not a continuous peak",
        reserve_120s_met_for_actual_run=False,
        actual_supervisor_remaining_after_exit_seconds=10800 - supervisor_wall,
        budget_clock_issue="C1 route clock began after worker imports; internal stop already completed before planned external request; no signal was sent",
        subsequent_fix="c8a057a46645542aaa17a38b78e64c6add80cb68: launcher monotonic origin and 150s cutoff; targeted clock tests only, NO_SECOND_FORMAL_REPLAY",
        no_kernel_continuous_cgroup_limit_claim=True,
        shared_workstation=True,
        timer_scope="phase wall totals; G/VJP/checkpoint/nested supervisor timers included, never added again",
    )
    if batch > 14400 or OLD_SECONDS + batch > 57600 or supervisor_wall > 10800:
        raise ValueError("authorized cumulative wall budget exceeded")
    write("resource_costs_v4.json", out)
    return out


def main():
    indices = {stage: index(stage)[0] for stage in STAGES}
    core, ref_index = index("e1_fe")[0], index("e3_reference")[0]
    fit = indices[ROUTE]
    result = fit["result"]
    design = read(RECORDS / "replay_design_v4.json")
    for key, entry in (
        ("native_sha256", core["files"]["native"]),
        ("gram_sha256", core["files"]["gram"]),
        ("reference_state_sha256", ref_index["files"]["reference"]),
    ):
        if entry["sha256"] != design[key]:
            raise ValueError("frozen review identity changed")
    boundary = indices["v4_boundary_checks"]["result"]
    if (
        boundary["status"] != "ADAM500_BOUNDARY_REPLAY_QUALIFIED"
        or boundary["real_M5_complete_loss_gradient_evaluations"] > 12
        or not boundary["fresh_LBFGS_state_empty"]
        or max(boundary["pairing"].values()) > 1e-10
    ):
        raise ValueError("Adam500 boundary was not qualified")
    starts = sorted(RESULTS.glob("task42extra_v4_reference_fit_boundary_replay_*"))
    if (
        len(starts) != 1
        or result["failure"] is not None
        or not result["no_Adam_updates"]
    ):
        raise ValueError("unique authorized replay contract failed")
    if (
        result["new_complete_fit_closures"] > 3500
        or result["counts"]["native_audits"] > 40
        or result["logical_path_closures"] != 500 + result["new_complete_fit_closures"]
        or result["Gsolve_count"]
        or result["Gram_factor_created"]
        or result["native_action_counts"]["A"]
        or result["native_action_counts"]["AH"]
    ):
        raise ValueError("fit closure work/algorithm contract failed")
    with np.load(fit["files"]["checkpoint"]["path"], allow_pickle=False) as x:
        policy(x)
        c, p = np.array(x["c"]), np.array(x["parameters"])
    saved = checkpoint_records(fit, p, c)
    for stage, entry in indices.items():
        policy(entry["result"])
        policy(read(Path(entry["run_directory"]) / "run_manifest.json"))
    raw = indices["v4_fit_compare_only"]["result"]
    if (
        raw["MUMPS_symbolic_numeric_solve_count"]
        or raw["reference_recomputed"]
        or raw["global_Maxwell_factor_created"]
    ):
        raise ValueError("compare-only performed a new solve")
    physics = raw["physics"]
    compare = raw["comparisons"][ROUTE]
    candidate, reference = physics["records"][ROUTE], physics["records"]["REFERENCE"]
    policy(compare)
    policy(candidate)
    errors = compare["errors"]
    if any(
        not all(math.isfinite(v[k]) for k in ("absolute", "denominator", "relative"))
        or v["denominator"] <= 0
        or not close(v["absolute"] / v["denominator"], v["relative"])
        for v in errors.values()
    ):
        raise ValueError("field denominator arithmetic failed")
    channel_fields = {
        "ordered_total_channels": "ordered_complex_total_channels",
        "ordered_outgoing_channels": "ordered_complex_outgoing_channels",
        "ordered_boundary_outgoing_channels": "ordered_complex_boundary_outgoing_channels",
        "ordered_scattered_channels": "ordered_complex_scattered_channels",
    }
    channels = {
        k: channel_error(candidate, reference, field, errors[k])
        for k, field in channel_fields.items()
    }
    sample_fields = {
        "selected_total_E": "selected_total_E",
        "selected_total_H": "selected_total_H_code",
        "selected_scattered_E": "selected_scattered_E",
        "selected_scattered_H": "selected_scattered_H_code",
    }
    for key, field in sample_fields.items():
        a, b = (
            np.asarray(complex_array(item[field])).reshape(6, 3)
            for item in (candidate, reference)
        )
        for suffix, aa, bb in [("", a, b)] + [
            (f"_point_{i}", a[i], b[i]) for i in range(6)
        ]:
            absolute = float(np.linalg.norm(aa - bb))
            denominator = max(float(np.linalg.norm(bb)), 1e-12)
            row = errors[key + suffix]
            if not all(
                close(v, row[k])
                for k, v in (
                    ("absolute", absolute),
                    ("denominator", denominator),
                    ("relative", absolute / denominator),
                )
            ):
                raise ValueError("selected E/H complex vector arithmetic failed")
    with np.load(ref_index["files"]["reference"]["path"], allow_pickle=False) as x:
        cref = np.array(x["c"])
    rec = indices["v4_fit_reconstruct"]
    with np.load(rec["files"]["reconstructed"]["path"], allow_pickle=False) as x:
        policy(x)
        q15, q30 = np.array(x["c_q15"]), np.array(x["c_q30"])
    pairing = float(np.linalg.norm(q15 - c) / max(np.linalg.norm(c), 1e-12))
    quadrature = float(np.linalg.norm(q30 - q15) / max(np.linalg.norm(q15), 1e-12))
    G = sparse.load_npz(core["files"]["gram"]["path"])
    e = c - cref
    numerator = float(np.vdot(e, G @ e).real)
    denominator = float(np.vdot(cref, G @ cref).real)
    Eg = float(np.sqrt(numerator / denominator))
    if (
        pairing > 1e-12
        or not close(quadrature, raw["q30_to_q15_relative"])
        or not close(Eg, raw["G_field_error"])
        or not close(Eg, result["final_audit"]["E_G"])
    ):
        raise ValueError("saved field/G/q15/q30 identity failed")
    power, ref_power = candidate["port"], reference["port"]
    volume, ref_volume = (
        item["volume"]["A_volume_total"] for item in (candidate, reference)
    )
    deltas = {
        k: abs(power[k] - ref_power[k]) for k in ("R_total", "T_total", "A_balance")
    }
    deltas["A_volume"] = abs(volume - ref_volume)
    per_channel = np.asarray(candidate["ordered_per_channel_power"])
    per_channel_ref = np.asarray(reference["ordered_per_channel_power"])
    if per_channel.shape != (40,) or per_channel_ref.shape != (40,):
        raise ValueError("complete channel power inventory missing")
    channel_power = float(np.max(abs(per_channel - per_channel_ref)))
    energy = abs(power["R_total"] + power["T_total"] + volume - 1)
    absorption = abs(power["A_balance"] - volume)
    if (
        not close(energy, compare["energy_closure_absolute"])
        or not close(absorption, compare["absorption_balance_volume_absolute"])
        or not close(channel_power, compare["max_channel_power_absolute"])
        or any(
            not close(v, compare["power_absolute_differences"][k])
            for k, v in deltas.items()
        )
    ):
        raise ValueError("power and energy arithmetic failed")
    for item in (power, ref_power):
        if not close(item["R00_s"] + item["R00_p"], item["R00_total"]):
            raise ValueError("R00 polarization sum failed")
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
    power_ok = (
        max(deltas.values()) <= 1e-5
        and max(energy, absorption) <= 1e-5
        and channel_power <= 1e-6
    )
    eL2, curl = (
        errors["scattered_L2"]["relative"],
        errors["scattered_scaled_curl"]["relative"],
    )
    category = (
        "QUADRATURE_DRIFT"
        if quadrature > 1e-8
        else "REPRESENTATION_WITNESS_POSITIVE"
        if max(Eg, eL2, curl) <= 1e-3
        else "PARTIAL_REPRESENTATION_WITNESS"
        if max(Eg, eL2, curl) <= 1e-2
        else "REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED"
    )
    if (
        raw["category"] != category
        or compare["qualified"]
        or (equation and field and power_ok) != compare["numerical_reconstruction_pass"]
    ):
        raise ValueError("raw decisions disagree with recomputation")
    for name, region in raw["region_field_errors"].items():
        ids = np.asarray(region["cell_ids"], dtype=np.int32)
        if (
            name not in {"air", "substrate", "grating", "interface_near"}
            or ids.ndim != 1
            or len(ids) != region["cells"]
            or not np.array_equal(ids, np.unique(ids))
            or ids.min() < 0
            or ids.max() >= 384
            or array_hash(ids) != region["cell_ids_sha256"]
        ):
            raise ValueError("original region identity failed")
        for k in ("scattered_L2", "scattered_scaled_curl"):
            x = region[k]
            if not close(x["absolute"] / x["reference_denominator"], x["relative"]):
                raise ValueError("region error arithmetic failed")
    gate = dict(
        schema="task42extra.gate-decisions.v4",
        category=category,
        source=indices["v4_fit_compare_only"]["source_sha"],
        R0_boundary_qualified=True,
        unique_formal_replay_starts=len(starts),
        final_state_retained=True,
        G_field_error=dict(numerator=numerator, denominator=denominator, relative=Eg),
        parameter_to_saved_c_relative=pairing,
        q30_to_q15_relative=quadrature,
        representation_positive=category == "REPRESENTATION_WITNESS_POSITIVE",
        representation_partial=category == "PARTIAL_REPRESENTATION_WITNESS",
        numerical_equation_pass=bool(equation),
        field_reconstruction_pass=bool(field),
        power_check_pass=bool(power_ok),
        reference_pass=physics["reference_pass"],
        reserve_120s_met_for_actual_run=False,
        neural_increment="NOT_DEMONSTRATED_REFERENCE_EXPOSED_DIAGNOSTIC",
        audit=audit,
        errors=errors,
        channels=channels,
        region_field_errors=raw["region_field_errors"],
        energy_closure_absolute=energy,
        absorption_balance_volume_absolute=absorption,
        max_channel_power_absolute=channel_power,
        power_differences=deltas,
        powers={
            role: {
                k: item["port"][k]
                for k in (
                    "R_total",
                    "T_total",
                    "A_balance",
                    "R00_s",
                    "R00_p",
                    "R00_total",
                )
            }
            | {"A_volume": item["volume"]["A_volume_total"]}
            for role, item in (("candidate", candidate), ("reference", reference))
        },
        ordered_complex={
            role: {field: item[field] for field in channel_fields.values()}
            for role, item in (("candidate", candidate), ("reference", reference))
        },
        selected_complex={
            role: {field: item[field] for field in sample_fields.values()}
            for role, item in (("candidate", candidate), ("reference", reference))
        },
        ordered_per_channel_power=dict(
            candidate=per_channel.tolist(), reference=per_channel_ref.tolist()
        ),
        thresholds=dict(
            equation=1e-6,
            field_channels=1e-4,
            powers_energy=1e-5,
            channel_power=1e-6,
            mpc=1e-10,
            representation_positive=1e-3,
            representation_partial=1e-2,
        ),
        **POLICY,
    )
    write("gate_decisions_v4.json", gate)
    old = read(RECORDS / "gate_decisions_v3.json")
    old_row = next(
        csv.DictReader((RECORDS / "representation_comparison_v3.csv").open())
    )
    row = dict(
        route=ROUTE,
        classification=category,
        inherited_Adam_updates=500,
        new_complete_fit_closures=result["new_complete_fit_closures"],
        logical_path_closures=result["logical_path_closures"],
        committed_new_closures=result["committed_complete_fit_closures"],
        stop_reason=result["stop_reason"],
        G_field_error=Eg,
        scattered_E_L2=eL2,
        scattered_scaled_curl=curl,
        total_E_L2=errors["total_L2"]["relative"],
        total_scaled_curl=errors["total_scaled_curl"]["relative"],
        selected_total_E=errors["selected_total_E"]["relative"],
        selected_total_H=errors["selected_total_H"]["relative"],
        native=audit["native_relative"],
        augmented=audit["augmented_relative"],
        total_channel_relative=channels["ordered_total_channels"]["relative"],
        outgoing_channel_relative=channels["ordered_outgoing_channels"]["relative"],
        scattered_channel_relative=channels["ordered_scattered_channels"]["relative"],
        R=power["R_total"],
        T=power["T_total"],
        A_balance=power["A_balance"],
        A_volume=volume,
        energy_closure_abs=energy,
        max_channel_power_abs=channel_power,
        q30_to_q15_relative=quadrature,
        **POLICY,
    )
    old_same = {k: old_row.get(k, "") for k in row}
    old_same.update(
        route="V3_RETAINED_ADAM500",
        classification="INTERRUPTED_FIT_NO_FINAL_STATE",
        G_field_error=old["G_field_error"],
        inherited_Adam_updates=500,
        new_complete_fit_closures=0,
        logical_path_closures=500,
        committed_new_closures=0,
        stop_reason="OLD_ATTEMPT_INTERRUPTED_NOT_A_FINAL_FIT_STATE",
        **POLICY,
    )
    with (RECORDS / "representation_comparison_v4.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row), lineterminator="\n")
        writer.writeheader()
        writer.writerows((old_same, row))
    run_index = dict(
        schema="task42extra.run-index.v4",
        review_commit=design["review_commit"],
        pre_registration_sha256=sha(RECORDS / "replay_design_v4.json"),
        stages=[
            dict(
                stage=stage,
                source_sha=item["source_sha"],
                run_directory=item["run_directory"],
                files=item["files"],
                index_sha256=sha(
                    ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")
                ),
            )
            for stage, item in indices.items()
        ],
        reused_native=core["files"]["native"],
        reused_Gram=core["files"]["gram"],
        reused_reference=ref_index["files"]["reference"],
        old_observed_complete_fit_closures_lower_bound=825,
        old817_parameters_optimizer="NOT_RETAINED",
        old_lost_attempt_seconds_retained=3284,
        observed_old_plus_new_complete_fit_closures_lower_bound=825
        + result["new_complete_fit_closures"],
        new_Gsolve_count=0,
        new_Gram_factor_count=0,
        new_Maxwell_factor_count=0,
        new_MUMPS_symbolic_numeric_solve_count=0,
        checkpoint_seconds_nested=result["checkpoint_seconds"],
        G_matvec_seconds_nested=result["G_matvec_seconds"],
        G_matvec_count=result["G_matvec_count"],
        moment_costs_nested=result["moment_costs"],
        **POLICY,
    )
    write("run_index_v4.json", run_index)
    with (RECORDS / "durable_audits_v4.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            (
                "checkpoint",
                "sha256",
                "new_evaluated",
                "committed_new",
                "logical_evaluated",
                "E_G",
                "native",
            )
        )
        for a in result["audits"]:
            writer.writerow(
                (
                    a["checkpoint"]["name"],
                    a["checkpoint"]["sha256"],
                    a["new_complete_fit_closures"],
                    a["committed_complete_fit_closures"],
                    a["logical_path_closures"],
                    a["E_G"],
                    a["native_relative"],
                )
            )
    xml = ROOT / "tmp/task42extra/v4_post_fit_targeted.xml"
    suite = ET.parse(xml).getroot()[0]
    write(
        "post_fit_checks_v4.json",
        dict(
            schema="task42extra.post-fit-checks.v4",
            source="c8a057a46645542aaa17a38b78e64c6add80cb68",
            pytest=dict(suite.attrib),
            xml_sha256=sha(xml),
            budget_fix_only_targeted_not_formal=True,
            boundary=boundary,
            final_checkpoint_sha256=saved["final"]["sha256"],
            **POLICY,
        ),
    )
    resources = resource_costs(indices)
    print(
        json.dumps(
            dict(
                category=category,
                new_complete_closures=result["new_complete_fit_closures"],
                E_G=Eg,
                native=audit["native_relative"],
                batch_seconds=resources["V4_batch_seconds"],
                all_peak_RSS=resources["all_supervised_peak_RSS_bytes"],
                official_candidate_results=False,
            )
        )
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--resources-only"]:
        costs = resource_costs({stage: index(stage)[0] for stage in STAGES})
        print(json.dumps({key: costs[key] for key in (
            "V4_batch_seconds", "original_total_conservative_seconds", "all_supervised_peak_RSS_bytes"
        )}))
    elif len(sys.argv) == 1:
        main()
    else:
        raise SystemExit("usage: check_task42extra_v4.py [--resources-only]")
