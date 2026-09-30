"""Recompute bounded V3 decisions from immutable raw artifacts; never solve PDE."""

import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy import sparse

from benchmarks.check_task42extra_v2 import (
    ARTIFACTS,
    CHECKS,
    RECORDS,
    RESULTS,
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


STAGES = (
    "v3_error_geometry",
    "v3_fit_checks",
    "FEINN-REFERENCE-FIT-G",
    "v3_retained_snapshot",
    "v3_fit_reconstruct",
    "v3_fit_compare_only",
)
ROUTE = "FEINN-REFERENCE-FIT-G"


def all_runs(stage):
    stem = {
        "v3_error_geometry": "task42extra_v3_error_geometry_",
        "v3_fit_checks": "task42extra_v3_fit_checks_",
        ROUTE: "task42extra_v3_reference_fit_",
        "v3_retained_snapshot": "task42extra_v3_retained_snapshot_",
        "v3_fit_reconstruct": "task42extra_v3_fit_reconstruct_",
        "v3_fit_compare_only": "task42extra_v3_fit_compare_only_",
    }[stage]
    return sorted(RESULTS.glob(stem + "*"))


def _stage_index(stage):
    path = ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")
    return index(stage)[0] if path.exists() else None


def _finite_ratio(item):
    return all(
        math.isfinite(item[k]) for k in ("absolute", "denominator", "relative")
    ) and close(item["absolute"] / item["denominator"], item["relative"])


def _stage_resources(indices):
    interruption = read(RECORDS / "fit_interruption_v3.json")
    rows = {}
    for stage in STAGES:
        published = Path(indices[stage]["run_directory"]) if indices[stage] else None
        attempts = []
        for directory in all_runs(stage):
            if not (directory / "run_summary.json").exists():
                if (
                    stage == ROUTE
                    and directory.name == interruption["run_directory_name"]
                ):
                    manifest = directory / "run_manifest.json"
                    resources = directory / "supervision/resources.jsonl"
                    artifact = ARTIFACTS / directory.name
                    expected = {
                        manifest: interruption["manifest_sha256"],
                        resources: interruption["resources_jsonl_sha256"],
                        artifact / "history.jsonl": interruption[
                            "history_jsonl_sha256"
                        ],
                        artifact / "zero_checkpoint.npz": interruption[
                            "zero_checkpoint_sha256"
                        ],
                        artifact / "adam500_checkpoint.npz": interruption[
                            "adam500_checkpoint_sha256"
                        ],
                    }
                    if any(sha(path) != digest for path, digest in expected.items()):
                        raise ValueError("interrupted fit raw data changed")
                    peak_rss = peak_swap = 0
                    last = None
                    with resources.open() as stream:
                        for line in stream:
                            last = json.loads(line)
                            peak_rss = max(peak_rss, last["rss_bytes"])
                            peak_swap = max(peak_swap, last["swap_bytes"])
                    if (
                        last is None
                        or not close(
                            last["elapsed_seconds"],
                            interruption["last_supervisor_sample_elapsed_seconds"],
                        )
                        or peak_rss
                        != interruption["peak_sampled_simultaneous_tree_RSS_bytes"]
                        or peak_swap != interruption["peak_sampled_own_tree_swap_bytes"]
                    ):
                        raise ValueError("interrupted fit sampler accounting changed")
                    attempts.append(
                        dict(
                            directory=str(directory),
                            classification=interruption["classification"],
                            supervised_seconds=interruption[
                                "conservative_charged_seconds"
                            ],
                            sampled_lower_bound_seconds=last["elapsed_seconds"],
                            charged_upper_bound_to_first_confirmed_absence=True,
                            peak_simultaneous_tree_RSS_bytes=peak_rss,
                            own_tree_swap_peak_bytes=peak_swap,
                            supervisor_summary="NOT_RETAINED",
                            source_sha=read(manifest)["source_sha"],
                            manifest_sha256=sha(manifest),
                        )
                    )
                else:
                    attempts.append(
                        dict(directory=str(directory), status="INCOMPLETE_NO_SUMMARY")
                    )
                continue
            row = resource_record(directory)
            manifest = read(directory / "run_manifest.json")
            row["run_manifest_sha256"] = sha(directory / "run_manifest.json")
            row["resolved_config_sha256"] = sha(directory / "resolved_config.json")
            row["input_original_sha256"] = sha(directory / "input_original.dat")
            row["resource_baseline_sha256"] = (
                sha(directory / "resource_baseline.json")
                if (directory / "resource_baseline.json").exists()
                else None
            )
            row["moments_sha256"] = manifest.get("moments_sha256")
            row["reference_used_for_training"] = manifest.get(
                "reference_used_for_training"
            )
            row["pde_only_solve"] = manifest.get("pde_only_solve")
            row["production_initialization_allowed"] = manifest.get(
                "production_initialization_allowed"
            )
            row["published"] = directory == published
            if (directory / "worker_failure.json").exists():
                row["failure"] = read(directory / "worker_failure.json")
            attempts.append(row)
        rows[stage] = attempts
    return rows


def _auxiliary_resources():
    out = []
    for directory in sorted(CHECKS.glob("v3_*")):
        path = directory / "summary.json"
        if not path.exists():
            out.append(dict(directory=str(directory), status="INCOMPLETE_NO_SUMMARY"))
            continue
        item = read(path)
        out.append(
            dict(
                label=directory.name,
                directory=str(directory),
                classification=item["classification"],
                elapsed_seconds=item["elapsed_seconds"],
                peak_simultaneous_tree_RSS_bytes=item.get(
                    "sampled_process_tree_rss_peak_bytes"
                ),
                own_tree_swap_peak_bytes=item.get(
                    "sampled_process_tree_swap_peak_bytes"
                ),
                leader_exit_code=item.get("leader_exit_code"),
                descendants_cleared=item["descendants_cleared"],
                summary_sha256=sha(path),
            )
        )
    return out


def main():
    indices = {stage: _stage_index(stage) for stage in STAGES}
    interruption = read(RECORDS / "fit_interruption_v3.json")
    core, authority = index("e1_fe")[0], index("e3_reference")[0]
    design = read(RECORDS / "representation_design_v3.json")
    design_sha = sha(RECORDS / "representation_design_v3.json")
    if (
        core["files"]["native"]["sha256"] != design["native_sha256"]
        or core["files"]["gram"]["sha256"] != design["gram_sha256"]
        or authority["files"]["reference"]["sha256"] != design["reference_state_sha256"]
    ):
        raise ValueError("preregistered physical/reference data changed")
    run = _stage_resources(indices)
    checks = _auxiliary_resources()
    formal_seconds = sum(
        item.get("supervised_seconds", 0)
        for attempts in run.values()
        for item in attempts
    )
    auxiliary_seconds = sum(item.get("elapsed_seconds", 0) for item in checks)
    # Bound direct read-only verification, the current checker invocation,
    # and final branch publication. These have no self-inclusive supervisor
    # summary at this snapshot; overcharge a fixed allowance instead of zero.
    unsupervised_light_allowance = 120.0
    batch_seconds = formal_seconds + auxiliary_seconds + unsupervised_light_allowance
    resources = dict(
        schema="task42extra.resource-costs.v3",
        cutoff="after GitHub browser verification; supervised records present at this checker invocation plus conservative 120-second direct/final tail allowance",
        V1_V2_conservative_base_seconds=29225.912270474248,
        V2_post_final_checker_unledgered_seconds_conservative=2.027,
        original_16h_limit_seconds=57600,
        V3_limit_seconds=14400,
        V3_formal_seconds=formal_seconds,
        V3_auxiliary_seconds=auxiliary_seconds,
        V3_unsupervised_light_allowance_seconds_conservative=unsupervised_light_allowance,
        V3_batch_seconds=batch_seconds,
        original_total_conservative_seconds=29225.912270474248 + 2.027 + batch_seconds,
        V3_remaining_seconds=14400 - batch_seconds,
        original_16h_remaining_seconds=57600
        - 29225.912270474248
        - 2.027
        - batch_seconds,
        formal_stage_attempts=run,
        auxiliary_attempts=checks,
        stage_peak_RSS_bytes={
            stage: max(
                (x.get("peak_simultaneous_tree_RSS_bytes") or 0 for x in attempts),
                default=0,
            )
            for stage, attempts in run.items()
        },
        all_supervised_peak_RSS_bytes=max(
            [
                x.get("peak_simultaneous_tree_RSS_bytes") or 0
                for attempts in run.values()
                for x in attempts
            ]
            + [x.get("peak_simultaneous_tree_RSS_bytes") or 0 for x in checks]
            + [0]
        ),
        peak_scope="maximum sampled simultaneous own process-tree RSS, not summed phase peaks",
        own_swap_zero=all(
            x.get("own_tree_swap_peak_bytes") in (None, 0)
            for attempts in run.values()
            for x in attempts
        )
        and all(x.get("own_tree_swap_peak_bytes") in (None, 0) for x in checks),
        system_growth_reserve_bytes=384 * 2**30,
        shared_workstation=True,
        no_kernel_continuous_cgroup_limit_claim=True,
    )
    write("resource_costs_v3.json", resources)
    run_index = dict(
        schema="task42extra.run-index.v3",
        review_commit=design["review_commit"],
        pre_registration_sha256=design_sha,
        sources={
            stage: (
                indices[stage]["source_sha"]
                if indices[stage]
                else interruption["original_fit_source_sha"]
                if stage == ROUTE
                else "NOT_RUN"
            )
            for stage in STAGES
        },
        stages=[
            dict(
                stage=stage,
                index_sha256=sha(
                    ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")
                )
                if indices[stage]
                else None,
                result_status=indices[stage]["result"]["status"]
                if indices[stage]
                else interruption["classification"]
                if stage == ROUTE
                else "NOT_RUN",
                files=indices[stage]["files"] if indices[stage] else {},
                attempts=run[stage],
            )
            for stage in STAGES
        ],
        reused_native=core["files"]["native"],
        reused_Gram=core["files"]["gram"],
        reused_reference=authority["files"]["reference"],
        MUMPS_symbolic_numeric_solve_count_new=0,
        unique_fit_interruption=interruption,
    )
    write("run_index_v3.json", run_index)
    if indices["v3_error_geometry"]:
        geometry = indices["v3_error_geometry"]["result"]
        if set(geometry["states"]) != {
            "ZERO",
            "FREE-FE-DUAL",
            "FREE-FE-DUAL-GRAM-DIAG",
            "FEINN-DUAL",
        }:
            raise ValueError("P0 did not retain exactly the four permitted states")
        if (
            geometry["actions"]["A"] > 24
            or geometry["actions"]["AH"] > 24
            or geometry["Gram_factor"]["solve_count"] > 24
            or geometry["worker_wall_seconds"] > 1200
            or geometry["Gram_factor"]["max_solve_true_relative"] > 1e-11
        ):
            raise ValueError("P0 bounded-action or accurate Gram contract failed")
        if any(
            row.get("error_residual_operation_relative", 0) > 1e-10
            for row in geometry["states"].values()
        ):
            raise ValueError("P0 A(e)=r-r_ref failed")
        write(
            "error_residual_geometry_v3.json",
            dict(
                schema="task42extra.error-residual-geometry.v3",
                source=indices["v3_error_geometry"]["source_sha"],
                data_role="reference exposed offline diagnostic",
                **geometry,
            ),
        )
    if indices["v3_fit_checks"]:
        qualified = indices["v3_fit_checks"]["result"]
        if (
            qualified["status"] != "REFERENCE_FIT_CHECKS_PASS"
            or not qualified["transaction_exception_restored"]
            or max(qualified["batch"].values()) > 1e-10
            or not all(
                min(item["relative"] for item in row["observations"]) <= 1e-5
                for row in qualified["finite_differences"]
            )
        ):
            raise ValueError("P1 gradient/batch/transaction check failed")
        write(
            "reference_fit_checks_v3.json",
            dict(
                schema="task42extra.fit-checks.v3",
                source=indices["v3_fit_checks"]["source_sha"],
                **qualified,
            ),
        )
    exposure = dict(
        schema="task42extra.reference-exposure.v3",
        data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
        reference_used_for_training=True,
        pde_only_solve=False,
        production_initialization_allowed=False,
        V1_V2_blind_results_unchanged=True,
        reference_state=authority["files"]["reference"],
        fit_status=interruption["classification"]
        if not indices[ROUTE]
        else indices[ROUTE]["result"]["status"],
        retained_snapshot_status=indices["v3_retained_snapshot"]["result"]["status"]
        if indices["v3_retained_snapshot"]
        else "NOT_RUN",
        checkpoint=indices["v3_retained_snapshot"]["files"].get("checkpoint")
        if indices["v3_retained_snapshot"]
        else indices[ROUTE]["files"].get("checkpoint")
        if indices[ROUTE]
        else None,
        not_a_held_out_or_fresh_solution=True,
        not_authorized_as_Task042_or_0p7nm_initialization=True,
    )
    if indices[ROUTE]:
        fit = indices[ROUTE]["result"]
        if (
            fit["route"] != ROUTE
            or not fit["reference_used_for_training"]
            or fit["pde_only_solve"]
            or fit["production_initialization_allowed"]
        ):
            raise ValueError("fit result lost its reference-exposed boundary")
        checkpoint = indices[ROUTE]["files"]["checkpoint"]
        with np.load(checkpoint["path"], allow_pickle=False) as x:
            c = np.array(x["c"])
            p = np.array(x["parameters"])
            if (
                not bool(x["reference_used_for_training"])
                or bool(x["pde_only_solve"])
                or bool(x["production_initialization_allowed"])
            ):
                raise ValueError("checkpoint lost reference-exposure policy")
        if (
            c.shape != (31968,)
            or p.shape != (8966,)
            or array_hash(c) != fit["final_c_sha256"]
            or array_hash(p) != fit["final_parameters_sha256"]
        ):
            raise ValueError("fit frozen checkpoint parameters/full c disagree")
        if (
            fit["Gram_factor_created"]
            or fit["Gsolve_count"]
            or fit["native_action_counts"]["A"]
            or fit["native_action_counts"]["AH"]
        ):
            raise ValueError("fit used forbidden factor/solve/action path")
        if fit["counts"]["complete_closures"] > 4000 or fit["wall_seconds"] > 10800:
            raise ValueError("fit budget exceeded")
        exposure["final_parameters_sha256"] = fit["final_parameters_sha256"]
        exposure["final_c_sha256"] = fit["final_c_sha256"]
        exposure["initialization_sha256"] = fit["initialization_sha256"]
        exposure["parameter_only_nonresumable"] = not fit[
            "consistent_optimizer_resume_supported"
        ]
        exposure["per_25_closure_accepted_parameter_update_norm"] = "NOT_RETAINED"
        exposure["update_telemetry_limit"] = (
            "history parameter_update_norm was sampled inside the closure before "
            "Adam committed; L-BFGS values include line-search trial displacement, "
            "so neither is an accepted-update history"
        )
    elif indices["v3_retained_snapshot"]:
        retained = indices["v3_retained_snapshot"]["result"]
        checkpoint = indices["v3_retained_snapshot"]["files"]["checkpoint"]
        with np.load(checkpoint["path"], allow_pickle=False) as x:
            c = np.array(x["c"])
            p = np.array(x["parameters"])
            if (
                not bool(x["reference_used_for_training"])
                or bool(x["pde_only_solve"])
                or bool(x["production_initialization_allowed"])
                or int(x["closures"]) != 500
            ):
                raise ValueError("retained checkpoint lost Adam500 label boundary")
        if (
            retained["status"] != "INTERRUPTED_FIT_ADAM500_RETAINED_SNAPSHOT"
            or c.shape != (31968,)
            or p.shape != (8966,)
            or array_hash(c) != retained["retained_c_sha256"]
            or array_hash(p) != retained["retained_parameters_sha256"]
            or not retained["no_training_or_optimizer_step"]
        ):
            raise ValueError("retained snapshot provenance invalid")
        exposure.update(
            final_parameters="NOT_RETAINED",
            final_checkpoint="NOT_RETAINED",
            optimizer_state="NOT_RETAINED",
            retained_committed_closure=500,
            observed_complete_closures=interruption["observed_complete_closures"],
            last_logged_committed_audit_closure=interruption[
                "last_logged_committed_audit_closure"
            ],
            retained_parameters_sha256=retained["retained_parameters_sha256"],
            retained_c_sha256=retained["retained_c_sha256"],
            per_25_closure_accepted_parameter_update_norm="NOT_RETAINED",
            parameter_only_nonresumable=True,
        )
    write("reference_exposure_v3.json", exposure)
    comparison_row = None
    gate = dict(
        schema="task42extra.gate-decisions.v3",
        review_commit=design["review_commit"],
        source=indices["v3_fit_compare_only"]["source_sha"]
        if indices["v3_fit_compare_only"]
        else "NOT_RUN",
        representation_category="NOT_RUN",
        supervised_reconstruction="NOT_RUN",
        pde_only_solver_qualified=False,
        official_candidate_results=False,
        reference_used_for_training=True,
        strict_thresholds=design["strict_thresholds"],
        research_thresholds=design["representation_thresholds"],
    )
    if indices["v3_fit_compare_only"]:
        raw = indices["v3_fit_compare_only"]["result"]
        compare = raw["comparisons"][ROUTE]
        physics = raw["physics"]
        candidate = physics["records"][ROUTE]
        reference = physics["records"]["REFERENCE"]
        errors = compare["errors"]
        if not all(_finite_ratio(v) for v in errors.values()):
            raise ValueError("field error/denominator arithmetic failed")
        channels = {
            key: channel_error(candidate, reference, field, errors[key])
            for key, field in {
                "ordered_total_channels": "ordered_complex_total_channels",
                "ordered_outgoing_channels": "ordered_complex_outgoing_channels",
                "ordered_boundary_outgoing_channels": "ordered_complex_boundary_outgoing_channels",
                "ordered_scattered_channels": "ordered_complex_scattered_channels",
            }.items()
        }
        sample_fields = {
            "selected_total_E": "selected_total_E",
            "selected_total_H": "selected_total_H_code",
            "selected_scattered_E": "selected_scattered_E",
            "selected_scattered_H": "selected_scattered_H_code",
        }
        sample_checks = {}
        for key, raw_key in sample_fields.items():
            a = np.asarray(complex_array(candidate[raw_key]), dtype=np.complex128)
            b = np.asarray(complex_array(reference[raw_key]), dtype=np.complex128)
            if a.shape != (18,) or b.shape != (18,):
                raise ValueError("six complete selected complex vector samples missing")
            absolute = float(np.linalg.norm(a - b))
            denominator = float(max(np.linalg.norm(b), 1e-12))
            if (
                not close(absolute, errors[key]["absolute"])
                or not close(denominator, errors[key]["denominator"])
                or not close(absolute / denominator, errors[key]["relative"])
            ):
                raise ValueError(
                    "selected complex E/H field error differs from raw samples"
                )
            sample_checks[key] = dict(
                absolute=absolute,
                denominator=denominator,
                relative=absolute / denominator,
            )
        power = candidate["port"]
        ref_power = reference["port"]
        for item in (power, ref_power):
            if not close(item["R00_s"] + item["R00_p"], item["R00_total"]):
                raise ValueError("R00 polarization inventory does not sum")
        volume = candidate["volume"]["A_volume_total"]
        ref_volume = reference["volume"]["A_volume_total"]
        deltas = {
            key: abs(power[key] - ref_power[key])
            for key in ("R_total", "T_total", "A_balance")
        }
        deltas["A_volume"] = abs(volume - ref_volume)
        channel_power = np.array(candidate["ordered_per_channel_power"])
        ref_channel_power = np.array(reference["ordered_per_channel_power"])
        max_power = float(np.max(abs(channel_power - ref_channel_power)))
        energy = abs(power["R_total"] + power["T_total"] + volume - 1)
        absorption = abs(power["A_balance"] - volume)
        if (
            channel_power.shape != (40,)
            or not close(max_power, compare["max_channel_power_absolute"])
            or not close(energy, compare["energy_closure_absolute"])
            or not close(absorption, compare["absorption_balance_volume_absolute"])
        ):
            raise ValueError("power/channel/energy arithmetic failed")
        if any(
            not close(deltas[k], compare["power_absolute_differences"][k])
            for k in deltas
        ):
            raise ValueError("R/T/A/A_volume differences failed")
        with np.load(authority["files"]["reference"]["path"], allow_pickle=False) as x:
            cref = np.array(x["c"])
        fit_state = indices["v3_retained_snapshot"] or indices[ROUTE]
        if fit_state is None:
            raise ValueError("no retained parameters for independent comparison")
        with np.load(fit_state["files"]["checkpoint"]["path"], allow_pickle=False) as x:
            c = np.array(x["c"])
        reconstructed = indices["v3_fit_reconstruct"]
        if reconstructed is None:
            raise ValueError("frozen network reconstruction missing")
        with np.load(
            reconstructed["files"]["reconstructed"]["path"], allow_pickle=False
        ) as x:
            c_q15 = np.array(x["c_q15"])
            c_q30 = np.array(x["c_q30"])
        saved_relative = float(
            np.linalg.norm(c_q15 - c) / max(np.linalg.norm(c), 1e-12)
        )
        q30_relative = float(
            np.linalg.norm(c_q30 - c_q15) / max(np.linalg.norm(c_q15), 1e-12)
        )
        if (
            saved_relative > 1e-12
            or not close(q30_relative, raw["q30_to_q15_relative"])
            or not close(saved_relative, raw["parameters_to_saved_c_relative"])
        ):
            raise ValueError("frozen parameter/q15/q30 coefficient identity failed")
        G = sparse.load_npz(core["files"]["gram"]["path"])
        e = c - cref
        Eg = float(np.sqrt(np.vdot(e, G @ e).real / np.vdot(cref, G @ cref).real))
        recorded_Eg = fit_state["result"].get(
            "retained_E_G", fit_state["result"].get("final_E_G")
        )
        if not close(Eg, raw["G_field_error"]) or not close(Eg, recorded_Eg, 1e-8):
            raise ValueError("G error does not match frozen fit and FE compare")
        eL2 = errors["scattered_L2"]["relative"]
        curl = errors["scattered_scaled_curl"]["relative"]
        snapshot_category = (
            "QUADRATURE_DRIFT"
            if q30_relative > 1e-8
            else "REPRESENTATION_WITNESS_POSITIVE"
            if max(Eg, eL2, curl) <= 1e-3
            else "PARTIAL_REPRESENTATION_WITNESS"
            if max(Eg, eL2, curl) <= 1e-2
            else "REPRESENTATION_OR_FIT_OPTIMIZATION_UNRESOLVED"
        )
        category = (
            "INTERRUPTED_FIT_NO_FINAL_STATE"
            if indices["v3_retained_snapshot"]
            else snapshot_category
        )
        if (
            raw["category"] != category
            or raw["snapshot_threshold_category"] != snapshot_category
            or compare["qualified"]
            or candidate["official_candidate_results"]
            or raw["pde_only_solver_qualified"]
            or raw["official_candidate_results"]
            or not compare["reference_used_for_training"]
            or compare["pde_only_solve"]
            or compare["production_initialization_allowed"]
        ):
            raise ValueError("research category or diagnostic-only policy failed")
        equation = (
            all(
                candidate["audit"][key] <= 1e-6
                for key in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                    "port_full_rhs_relative",
                    "port_operation_relative",
                    "independent_DOLFINx_total_native_relative",
                )
            )
            and candidate["audit"]["slave_storage_max"] == 0
        )
        field = all(x["relative"] <= 1e-4 for x in errors.values())
        power_ok = (
            all(x <= 1e-5 for x in deltas.values())
            and max(energy, absorption) <= 1e-5
            and max_power <= 1e-6
        )
        supervised = bool(
            equation
            and field
            and power_ok
            and physics["reference_pass"]
            and snapshot_category != "QUADRATURE_DRIFT"
        )
        if supervised != (
            raw["supervised_reconstruction"]
            == "SUPERVISED_DISCRETE_RECONSTRUCTION_PASS"
        ):
            raise ValueError("supervised reconstruction category differs")
        gate.update(
            representation_category=category,
            retained_snapshot_threshold_category=snapshot_category,
            final_fit_parameters_retained=not bool(indices["v3_retained_snapshot"]),
            supervised_reconstruction=raw["supervised_reconstruction"],
            numerical_equation_pass=bool(equation),
            field_reconstruction_pass=bool(field),
            power_check_pass=bool(power_ok),
            reference_pass=physics["reference_pass"],
            G_field_error=Eg,
            scattered_E_L2_relative=eL2,
            scattered_scaled_curl_relative=curl,
            q30_to_q15_relative=raw["q30_to_q15_relative"],
            raw_comparison_index_sha256=sha(
                ARTIFACTS / "index_v3_fit_compare_only.json"
            ),
            independent_MUMPS_solve_count=raw["MUMPS_symbolic_numeric_solve_count"],
        )
        for name, region in raw["region_field_errors"].items():
            ids = np.asarray(region["cell_ids"], dtype=np.int32)
            if (
                name not in {"air", "substrate", "grating", "interface_near"}
                or ids.ndim != 1
                or len(ids) != region["cells"]
                or len(ids) == 0
                or not np.array_equal(ids, np.unique(ids))
                or np.min(ids) < 0
                or np.max(ids) >= 384
                or array_hash(ids) != region["cell_ids_sha256"]
            ):
                raise ValueError("region cell-set identity failed")
        comparison_row = dict(
            route=ROUTE,
            classification=category,
            reference_exposed=True,
            pde_only_solver_qualified=False,
            fit_closures_observed=interruption["observed_complete_closures"],
            fit_closures_retained=500
            if indices["v3_retained_snapshot"]
            else fit_state["result"]["counts"]["complete_closures"],
            fit_stop_reason=fit_state["result"]["stop_reason"],
            fit_loss=fit_state["result"].get(
                "retained_fit_loss", fit_state["result"].get("final_fit_loss")
            ),
            G_field_error=Eg,
            scattered_E_L2=eL2,
            scattered_scaled_curl=curl,
            total_E_L2=errors["total_L2"]["relative"],
            total_scaled_curl=errors["total_scaled_curl"]["relative"],
            selected_total_E=errors["selected_total_E"]["relative"],
            selected_total_H=errors["selected_total_H"]["relative"],
            native=candidate["audit"]["native_relative"],
            augmented=candidate["audit"]["augmented_relative"],
            port_operation=candidate["audit"]["port_operation_relative"],
            total_channel_relative=channels["ordered_total_channels"]["relative"],
            outgoing_channel_relative=channels["ordered_outgoing_channels"]["relative"],
            scattered_channel_relative=channels["ordered_scattered_channels"][
                "relative"
            ],
            R=power["R_total"],
            R00_s=power["R00_s"],
            R00_p=power["R00_p"],
            R00_total=power["R00_total"],
            T=power["T_total"],
            A_balance=power["A_balance"],
            A_volume=volume,
            energy_closure_abs=energy,
            max_channel_power_abs=max_power,
            q30_to_q15_relative=raw["q30_to_q15_relative"],
            supervised_reconstruction_pass=supervised,
        )
        gate["regions"] = raw["region_field_errors"]
        gate["channels"] = channels
        gate["ordered_complex_candidate"] = {
            field: candidate[field]
            for field in (
                "ordered_complex_total_channels",
                "ordered_complex_outgoing_channels",
                "ordered_complex_boundary_outgoing_channels",
                "ordered_complex_scattered_channels",
            )
        }
        gate["ordered_complex_reference"] = {
            field: reference[field]
            for field in (
                "ordered_complex_total_channels",
                "ordered_complex_outgoing_channels",
                "ordered_complex_boundary_outgoing_channels",
                "ordered_complex_scattered_channels",
            )
        }
        gate["selected_complex_E_H"] = sample_checks
        gate["selected_complex_candidate"] = {
            key: candidate[raw_key] for key, raw_key in sample_fields.items()
        }
        gate["selected_complex_reference"] = {
            key: reference[raw_key] for key, raw_key in sample_fields.items()
        }
        gate["power_differences"] = deltas
        gate["port_power_observables"] = {
            role: {
                key: item["port"][key]
                for key in (
                    "R00_s",
                    "R00_p",
                    "R00_total",
                    "R_total",
                    "T_total",
                    "A_balance",
                )
            }
            | {"A_volume": item["volume"]["A_volume_total"]}
            for role, item in (("candidate", candidate), ("reference", reference))
        }
        gate["ordered_per_channel_power"] = {
            "candidate": candidate["ordered_per_channel_power"],
            "reference": reference["ordered_per_channel_power"],
        }
    write("gate_decisions_v3.json", gate)
    path = RECORDS / "representation_comparison_v3.csv"
    if comparison_row is None:
        comparison_row = dict(
            route=ROUTE,
            classification="NOT_RUN",
            reference_exposed=True,
            pde_only_solver_qualified=False,
        )
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_row), lineterminator="\n")
        writer.writeheader()
        writer.writerow(comparison_row)
    print(
        json.dumps(
            dict(
                status=gate["representation_category"],
                batch_seconds=batch_seconds,
                formal_completed=sum(bool(indices[s]) for s in STAGES),
                strict_solver_pass=False,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
