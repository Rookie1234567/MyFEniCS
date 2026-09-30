"""Frozen p authority arithmetic and resource checker; no FE/Gram solve."""

import csv
import json
from pathlib import Path
import sys

import numpy as np

from benchmarks.check_task42extra_v2 import (
    ROOT,
    RECORDS,
    RESULTS,
    index,
    read,
    write,
    sha,
    close,
    complex_array,
)
from benchmarks.check_task42extra_v5 import resources
from src.solvers.feinn_native import load_native
from src.solvers.feinn_discretization_audit import POLICY, EXPECTED

STAGES = ("v7_p_transfer_checks", "v7_p4_reference", "v7_p3_p4_compare")
SOURCE = "76d863e43d2fc1b5bed8b1c835aa6f43bb2c93d2"
OLD_SECONDS = 45161.81665198447


def vector(value):
    return np.asarray(complex_array(value), dtype=np.complex128)


def require(condition, name):
    if not condition:
        raise ValueError(name)


def error_pair(raw, p3_norm, p4_norm, absolute):
    """Recompute the predeclared p4 denominator, including near-zero handling."""
    denominator = max(float(p4_norm), 1e-12 * raw["natural_scale"])
    values = dict(
        p3_norm=float(p3_norm),
        p4_norm=float(p4_norm),
        absolute=float(absolute),
        denominator=denominator,
        relative=float(absolute / denominator),
        natural_scale=raw["natural_scale"],
        near_zero=bool(p4_norm < 1e-12 * raw["natural_scale"]),
        difference="p3_minus_p4",
    )
    for key in ("p3_norm", "p4_norm", "absolute", "denominator", "relative"):
        require(
            abs(values[key] - raw[key])
            <= 2e-11 * max(abs(values[key]), abs(raw[key]), np.finfo(float).tiny),
            "COMPARISON_ARITHMETIC_" + key,
        )
    require(values["near_zero"] == raw["near_zero"], "NEAR_ZERO_POLICY_CHANGED")
    return values


def comparison_gate(result):
    """Recalculate from retained energies and raw complex samples/channels."""
    errors = {}
    for kind, pair in result["energy_pairs"].items():
        for j, name in enumerate(("L2", "scaled_curl")):
            energies = [float(pair[k][j]) for k in ("p3", "p4", "difference")]
            require(
                np.isfinite(energies).all() and min(energies) >= 0, "INVALID_RAW_ENERGY"
            )
            key = kind + "_" + name
            errors[key] = error_pair(result["errors"][key], *np.sqrt(energies))
    for kind, sample in result["samples"].items():
        for quantity in ("E", "H_code"):
            left = vector(sample["p3"][quantity]).reshape(6, 3)
            right = vector(sample["p4"][quantity]).reshape(6, 3)
            key = kind + "_selected_" + quantity
            errors[key] = error_pair(
                result["errors"][key],
                np.linalg.norm(left),
                np.linalg.norm(right),
                np.linalg.norm(left - right),
            )
            for j in range(6):
                name = key + "_point_" + str(j)
                errors[name] = error_pair(
                    result["errors"][name],
                    np.linalg.norm(left[j]),
                    np.linalg.norm(right[j]),
                    np.linalg.norm(left[j] - right[j]),
                )
    for kind, raw in result["channels"].items():
        left, right = vector(raw["p3"]), vector(raw["p4"])
        require(left.shape == right.shape == (40,), "INCOMPLETE_CHANNEL_INVENTORY")
        require(
            np.allclose(
                vector(raw["difference"]), left - right, rtol=1e-12, atol=1e-15
            ),
            "CHANNEL_DIFFERENCE_CHANGED",
        )
        errors["channels_" + kind] = error_pair(
            raw["error"],
            np.linalg.norm(left),
            np.linalg.norm(right),
            np.linalg.norm(left - right),
        )
    require(set(errors) == set(result["errors"]), "MISSING_MAIN_FIELD_CHECK")
    qchecks = {}
    for kind, raw in result["quadrature"].items():
        left, right, denominator = (
            np.asarray(raw[k]) for k in ("degree15", "degree30", "denominator_energy")
        )
        require(
            np.isfinite([left, right, denominator]).all()
            and min(*left, *right) >= 0
            and min(denominator) > 0,
            "INVALID_Q_ENERGY",
        )
        expected_denominator = np.maximum(
            result["energy_pairs"][kind]["p4"],
            1e-24 * result["errors"][kind + "_L2"]["natural_scale"] ** 2,
        )
        require(
            np.allclose(denominator, expected_denominator, rtol=1e-12, atol=0),
            "Q_DENOMINATOR_NOT_P4_ENERGY",
        )
        defect = abs(left - right) / denominator
        require(
            np.allclose(
                defect, raw["normalized_absolute_difference"], rtol=1e-12, atol=1e-16
            ),
            "Q_DIFFERENCE_CHANGED",
        )
        qchecks[kind] = defect.tolist()
    powers = result["powers"]
    p3, p4 = np.asarray(powers["p3"]), np.asarray(powers["p4"])
    require(p3.shape == p4.shape == (40,), "INCOMPLETE_POWER_INVENTORY")
    max_power = float(np.max(abs(p3 - p4)))
    require(close(max_power, powers["max_absolute"]), "POWER_ARITHMETIC_CHANGED")
    observables = {}
    for name, raw in result["observables"].items():
        absolute = abs(raw["p3"] - raw["p4"])
        require(close(absolute, raw["absolute"]), "OBSERVABLE_ARITHMETIC_CHANGED")
        observables[name] = absolute
    qpass = all(max(x) <= 1e-10 for x in qchecks.values())
    field_pass = all(x["relative"] <= 1e-3 for x in errors.values())
    power_pass = max_power <= 1e-4 and all(
        observables[k] <= 1e-4 for k in ("R_total", "T_total", "A_balance", "A_volume")
    )
    regional = {
        f"{name}/{kind}/{quantity}": row
        for name, region in result["regions"].items()
        for kind, fields in region["fields"].items()
        for quantity, row in fields.items()
    }
    for row in regional.values():
        error_pair(row, row["p3_norm"], row["p4_norm"], row["absolute"])
    region_pass = all(x["relative"] <= 1e-3 for x in regional.values())
    status = (
        "COMPARISON_QUADRATURE_UNRESOLVED"
        if not qpass
        else (
            "P3_P4_SMALL_CHANGE_LIMITED"
            if field_pass and power_pass
            else "P3_P4_SENSITIVITY_OBSERVED"
        )
    )
    require(status == result["status"], "RAW_COMPARISON_GATE_DIFFERS")
    return dict(
        status=status,
        comparison_qualified=qpass,
        small_change_signal=qpass and field_pass and power_pass,
        local_sensitivity_remains=field_pass and power_pass and not region_pass,
        field_pass=field_pass,
        power_pass=power_pass,
        region_pass=region_pass,
        errors=errors,
        quadrature_recomputed=qchecks,
        observables_absolute=observables,
        maximum_per_channel_power_difference=max_power,
        failed_main_fields={k: v for k, v in errors.items() if v["relative"] > 1e-3},
        failed_power_observables={k: v for k, v in observables.items() if v > 1e-4},
        failed_regions={k: v for k, v in regional.items() if v["relative"] > 1e-3},
    )


def reference_gate(result, independent):
    physics = result["physics"]
    ref = physics["records"]["REFERENCE"]
    audit = ref["audit"]
    keys = (
        "native_relative",
        "augmented_relative",
        "original_total_augmented_relative",
        "independent_DOLFINx_total_native_relative",
        "port_operation_relative",
        "port_full_rhs_relative",
    )
    closure = abs(
        ref["port"]["R_total"]
        + ref["port"]["T_total"]
        + ref["volume"]["A_volume_total"]
        - 1
    )
    gap = abs(ref["port"]["A_balance"] - ref["volume"]["A_volume_total"])
    direct = result["direct"]
    capacity = (
        direct["rss_after_symbolic_bytes"]
        + direct["estimated_factor_bytes"]
        + direct["conversion_and_workspace_reserve_bytes"]
        < 12 * 2**30
    )
    lifecycle = bool(
        direct["factor_released"]
        and direct["matrix_released"]
        and direct["minimal_recovery_packet_saved_before_factor_release"]
        and direct["rss_after_release_bytes"] < direct["rss_before_release_bytes"]
    )
    qualified = (
        max(audit[k] for k in keys) <= 1e-10
        and max(
            independent[k]
            for k in (
                "native_relative",
                "augmented_relative",
                "original_total_augmented_relative",
            )
        )
        <= 1e-10
        and audit["slave_storage_max"] <= 1e-10
        and result["MPC_recovery_relative"] <= 1e-10
        and direct["original_port_recovery_relative"] <= 1e-10
        and closure <= 1e-5
        and gap <= 1e-5
        and capacity
        and lifecycle
    )
    require(qualified == result["reference_qualified"], "RAW_REFERENCE_GATE_DIFFERS")
    return dict(
        qualified=qualified,
        original_audit=audit,
        independent_frozen_native_audit=independent,
        energy_closure=closure,
        absorption_gap=gap,
        capacity_pass=capacity,
        lifecycle_pass=lifecycle,
        MPC_recovery_relative=result["MPC_recovery_relative"],
    )


def resource_costs(indices):
    if STAGES[1] not in indices:
        directory = next(RESULTS.glob("task42extra_v7_p4_reference_*"))
        request = read(directory / "budget_stop_request.json")
        handles = dict(indices)
        handles[STAGES[1]] = dict(
            run_directory=str(directory),
            result=dict(numeric_cutoff_monotonic=request["numeric_cutoff_monotonic"]),
            record_kind="RESOURCE_ONLY_NO_NUMERICAL_INDEX",
        )
        out = resources(
            handles,
            version=7,
            old_seconds=OLD_SECONDS,
            batch_limit=7200,
            main_limit=3600,
            main_route=STAGES[1],
            new_factor_counts=(0, 0, 0),
        )
        u0 = out["formal_stages"][STAGES[0]]["charged_seconds"] + sum(
            x["charged_seconds"]
            for x in out["auxiliary_attempts"]
            if Path(x["directory"]).name.startswith("v7_u0_")
        )
        out.update(
            U0_charged_seconds=u0,
            U0_limit_seconds=1200,
            U2_status="NOT_RUN_P4_REFERENCE_NOT_QUALIFIED",
            p4_status="P4_REFERENCE_TIME_BLOCKED",
            MUMPS_symbolic_started="NOT_RETAINED_NO_START_MARKER",
            MUMPS_symbolic_completed=0,
            MUMPS_numeric_started=0,
            MUMPS_solve_started=0,
            new_completed_Gram_factor_Gsolve_Maxwell_factor_counts=[0, 0, 0],
            raw_p4_manifest_operator_hash_is_unfinalized=True,
            authoritative_p4_native_sha256=indices[STAGES[0]]["files"]["native"][
                "sha256"
            ],
            reference_assembly_completion_timer="NOT_RETAINED",
            timer_scope="formal stage walls sum; interrupted native assembly included in whole launcher wall; no missing component timer replay",
        )
        require(u0 <= 1200, "U0_BUDGET_FAILED")
        write("resource_costs_v7.json", out)
        return out
    out = resources(
        indices,
        version=7,
        old_seconds=OLD_SECONDS,
        batch_limit=7200,
        main_limit=3600,
        main_route="v7_p4_reference",
        new_factor_counts=(0, 0, 1),
    )
    u0 = out["formal_stages"][STAGES[0]]["charged_seconds"] + sum(
        x["charged_seconds"]
        for x in out["auxiliary_attempts"]
        if Path(x["directory"]).name.startswith("v7_u0_")
    )
    out.update(
        U0_charged_seconds=u0,
        U0_limit_seconds=1200,
        U2_limit_seconds=1200,
        new_MUMPS_symbolic_numeric_solve_counts=[1, 1, 1],
        new_Gram_matrix_count=0,
        direct_current_and_final_allowance_meaning="all small direct inspections, syntax/docs handling and final Git/records costs reserved conservatively; supervised tests/browser also charged separately",
        timer_scope="formal stage walls sum; symbolic/numeric/release/physics are nested and not added again",
    )
    require(
        u0 <= 1200 and out["formal_stages"][STAGES[2]]["charged_seconds"] <= 1200,
        "AUTHORITY_STAGE_BUDGET_FAILED",
    )
    write("resource_costs_v7.json", out)
    return out


def comparison_csv(result):
    rows = []
    for name, row in result["errors"].items():
        rows.append(
            dict(
                section="field_vector",
                quantity=name,
                key="complete vector",
                p3_real=row["p3_norm"],
                p4_real=row["p4_norm"],
                absolute=row["absolute"],
                denominator=row["denominator"],
                relative=row["relative"],
                limit=1e-3,
                passed=row["relative"] <= 1e-3,
            )
        )
    for name, row in result["observables"].items():
        rows.append(
            dict(
                section="observable",
                quantity=name,
                key="incident power normalized",
                p3_real=row["p3"],
                p4_real=row["p4"],
                absolute=row["absolute"],
                denominator=1,
                limit=1e-4,
                passed=row["absolute"] <= 1e-4,
            )
        )
    keys = result["powers"]["keys"]
    for name, row in result["channels"].items():
        left, right = vector(row["p3"]), vector(row["p4"])
        for j, key in enumerate(keys):
            absolute = float(abs(left[j] - right[j]))
            denominator = max(float(abs(right[j])), 1e-12)
            rows.append(
                dict(
                    section="complex_channel",
                    quantity=name,
                    key=f"{key['side']}/{key['m']}/{key['n']}/{key['polarization']}",
                    p3_real=left[j].real,
                    p3_imag=left[j].imag,
                    p4_real=right[j].real,
                    p4_imag=right[j].imag,
                    absolute=absolute,
                    denominator=denominator,
                    relative=absolute / denominator,
                    vector_denominator=row["error"]["denominator"],
                    vector_relative=row["error"]["relative"],
                    limit="vector 1e-3",
                    passed=row["error"]["relative"] <= 1e-3,
                )
            )
    for j, key in enumerate(keys):
        left, right = result["powers"]["p3"][j], result["powers"]["p4"][j]
        rows.append(
            dict(
                section="channel_power",
                quantity="incident power normalized",
                key=f"{key['side']}/{key['m']}/{key['n']}/{key['polarization']}",
                p3_real=left,
                p4_real=right,
                absolute=abs(left - right),
                denominator=1,
                limit=1e-4,
                passed=abs(left - right) <= 1e-4,
            )
        )
    for kind, sample in result["samples"].items():
        for quantity in ("E", "H_code"):
            left = vector(sample["p3"][quantity]).reshape(6, 3)
            right = vector(sample["p4"][quantity]).reshape(6, 3)
            for j in range(6):
                error = result["errors"][
                    kind + "_selected_" + quantity + "_point_" + str(j)
                ]
                for component in range(3):
                    rows.append(
                        dict(
                            section="six_point_complex",
                            quantity=kind + "/" + quantity,
                            key=f"point{j}/component{component}/cell{result['cells'][j]}",
                            p3_real=left[j, component].real,
                            p3_imag=left[j, component].imag,
                            p4_real=right[j, component].real,
                            p4_imag=right[j, component].imag,
                            absolute=abs(left[j, component] - right[j, component]),
                            denominator=error["denominator"],
                            vector_denominator=error["denominator"],
                            vector_relative=error["relative"],
                            limit="point-vector 1e-3",
                            passed=error["relative"] <= 1e-3,
                        )
                    )
    for name, region in result["regions"].items():
        for kind, fields in region["fields"].items():
            for quantity, row in fields.items():
                rows.append(
                    dict(
                        section="region",
                        quantity=kind + "/" + quantity,
                        key=name,
                        p3_real=row["p3_norm"],
                        p4_real=row["p4_norm"],
                        absolute=row["absolute"],
                        denominator=row["denominator"],
                        relative=row["relative"],
                        limit=1e-3,
                        passed=row["relative"] <= 1e-3,
                    )
                )
    with (RECORDS / "p3_p4_comparison_v7.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "section",
                "quantity",
                "key",
                "p3_real",
                "p3_imag",
                "p4_real",
                "p4_imag",
                "absolute",
                "denominator",
                "relative",
                "vector_denominator",
                "vector_relative",
                "limit",
                "passed",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def partial_main(indices):
    """Qualify retained U0, classify the known budget stop, never invent c4."""
    checks = indices[STAGES[0]]["result"]
    core, _ = index("e1_fe")
    oldref, _ = index("e3_reference")
    legacy, legacy_path = index("e4_p4")
    require(
        legacy["result"]["status"] == "DISCRETIZATION_NOT_QUALIFIED"
        and set(legacy["files"]) == {"result"},
        "OLD_E4_CHANGED",
    )
    require(
        core["files"]["native"]["sha256"] == EXPECTED["native"]
        and oldref["files"]["reference"]["sha256"] == EXPECTED["reference"],
        "FROZEN_P3_CHANGED",
    )
    require(
        len(list(RESULTS.glob("task42extra_v7_p4_reference_*"))) == 1,
        "UNIQUE_P4_START_FAILED",
    )
    directory = next(RESULTS.glob("task42extra_v7_p4_reference_*"))
    summary = read(directory / "run_summary.json")
    request = read(directory / "budget_stop_request.json")
    manifest = read(directory / "run_manifest.json")
    require(
        summary["classification"] == "USER_CONTROLLED_STOP"
        and summary["leader_exit_code"] == -15
        and summary["descendants_cleared"],
        "EXPECTED_MANAGED_BUDGET_STOP_NOT_REPRODUCED",
    )
    require(
        request["reason"] == "REVIEW_V6_V7_NUMERIC_CUTOFF_SAVE_RESERVE"
        and request["stage_elapsed_seconds"] >= 3450
        and summary["launch_exit_remaining_seconds"] >= 120,
        "SAVE_RESERVE_NOT_MET",
    )
    require(
        manifest["source_sha"] == SOURCE
        and request["source_sha"] == SOURCE
        and indices[STAGES[0]]["source_sha"] == SOURCE,
        "SOURCE_BINDING_FAILED",
    )
    for value in (manifest, checks):
        require(
            all(value[k] == v for k, v in POLICY.items()), "AUTHORITY_POLICY_CHANGED"
        )
    require(
        manifest["gram_sha256"] is None
        and manifest["mpi_size"] == 1
        and manifest["math_threads"] == 1,
        "AUTHORITY_ENV_CHANGED",
    )
    events = [
        json.loads(line)
        for line in (directory / "stages.jsonl").read_text().splitlines()
    ]
    require(
        [x["name"] for x in events]
        == ["physical_model", "reference_pre_assembly_capacity"],
        "UNEXPECTED_RETAINED_REFERENCE_PHASE",
    )
    native = indices[STAGES[0]]["files"]["native"]
    require(
        manifest["frozen_dependencies_before_worker_launch"][STAGES[0]]["files"][
            "native"
        ]["sha256"]
        == native["sha256"],
        "INTERRUPTED_P4_INPUT_BINDING_FAILED",
    )
    require(
        not any(
            (ROOT / "benchmarks/artifacts/task42extra").glob(
                "task42extra_v7_p4_reference_*/p4_reference_state.npz"
            )
        ),
        "UNEXPECTED_REFERENCE_PACKET_EXISTS",
    )
    transfer_pass = all(
        max(
            checks[key][field]
            for field in (
                "common_point_E_relative",
                "common_point_curl_relative",
                "MPC_embedding_relative",
            )
        )
        <= 1e-10
        for key in ("small_transfer", "M5_transfer")
    )
    action_pass = all(
        max(
            row[k]
            for k in (
                "original_native_relative",
                "adjoint_dot_relative",
                "augmented_native_relative",
                "original_port_operation_relative",
            )
        )
        <= 1e-10
        for row in checks["action"]["samples"]
    )
    action_pass &= (
        max(
            checks["action"][k]
            for k in (
                "nonzero_FE_and_port_load_relative",
                "nonzero_port_load_operation_relative",
            )
        )
        <= 1e-10
    )
    require(transfer_pass and action_pass, "U0_RAW_PAIR_FAILED")
    identity = {k: v for k, v in checks["identity"].items() if k != "modes"}
    binding = dict(
        authoritative_p4_native=native,
        raw_interrupted_manifest_physical_model_sha256=manifest[
            "physical_model_sha256"
        ],
        raw_manifest_hash_valid_for_p4=False,
        reason="C1 launch initially used p3 dependency hash; p4 post-result update was never reached. Raw record preserved, actual p4 input independently bound by U0 dependency and degree4 physical-model event.",
        future_fix="pre-worker p4 identity binding; no formal restart",
    )
    write(
        "p_transfer_checks_v7.json",
        dict(
            schema="task42extra.p-transfer.v7",
            source_sha=SOURCE,
            transfer_pass=transfer_pass,
            action_pass=action_pass,
            small_transfer=checks["small_transfer"],
            M5_transfer=checks["M5_transfer"],
            action=checks["action"],
            independent_families=checks["independent_families"],
            identity=identity,
            array_capacity=checks["array_capacity"],
            physics_equivalence_fields=checks["physics_equivalence_fields"],
            counts=checks["counts"],
            old_e4_not_run_index_sha256=sha(legacy_path),
            **POLICY,
        ),
    )
    stop = dict(
        status="P4_REFERENCE_TIME_BLOCKED",
        reference_qualified=False,
        stop_request=request,
        supervision_classification=summary["classification"],
        worker_exit_code=summary["leader_exit_code"],
        descendants_cleared=summary["descendants_cleared"],
        launch_to_summary_seconds=summary["launch_to_summary_seconds_monotonic"],
        exit_remaining_seconds=summary["launch_exit_remaining_seconds"],
        last_retained_stage=events[-1]["name"],
        preassembly_capacity=events[-1]["facts"],
        p4_physical_model_event={
            k: v for k, v in events[0]["facts"].items() if k != "modes"
        },
        p4_input_binding=binding,
        CSR_complete="NOT_RETAINED",
        symbolic_capacity="NOT_RUN_NO_COMPLETION_RECORD",
        symbolic_started="NOT_RETAINED_NO_START_MARKER",
        symbolic_completed=0,
        numeric_started=0,
        solve_started=0,
        c_scattered="NOT_RETAINED_NO_SOLVE",
        alpha_scattered="NOT_RETAINED_NO_SOLVE",
        alpha_total="NOT_RETAINED_NO_SOLVE",
        native_residual="NOT_RUN",
        augmented_residual="NOT_RUN",
        total_residual="NOT_RUN",
        E_H_curl_R_T_A_A_volume="NOT_RUN",
        OOM_evidence=False,
        precision_failure_evidence=False,
        new_Gram_matrix_count=0,
        new_Gram_factor_count=0,
        new_Gsolve_count=0,
        new_completed_Maxwell_factor_count=0,
        NN_training_count=0,
        **POLICY,
    )
    write(
        "p4_reference_v7.json",
        dict(schema="task42extra.p4-reference.v7", source_sha=SOURCE, **stop),
    )
    write(
        "gate_decisions_v7.json",
        dict(
            schema="task42extra.raw-gates.v7",
            source_sha=SOURCE,
            U0_pass=transfer_pass and action_pass,
            p4_reference=stop,
            p3_p4=dict(
                status="NOT_RUN_P4_REFERENCE_NOT_QUALIFIED",
                small_change_signal=None,
                comparison_qualified=False,
            ),
            old_e4_not_run_preserved=True,
            old_neural_failure_conclusions_unchanged=True,
            official_neural_candidate_results=False,
            **POLICY,
        ),
    )
    original = oldref["result"]["physics"]["records"]["REFERENCE"]
    with (RECORDS / "p3_p4_comparison_v7.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "quantity",
                "p3_original",
                "p4",
                "absolute_difference",
                "denominator",
                "relative_difference",
                "status",
                "reason",
            ],
        )
        writer.writeheader()
        for name in (
            "R_total",
            "T_total",
            "A_balance",
            "R00_s",
            "R00_p",
            "R00_total",
            "A_volume",
        ):
            value = (
                original["volume"]["A_volume_total"]
                if name == "A_volume"
                else original["port"][name]
            )
            writer.writerow(
                dict(
                    quantity=name,
                    p3_original=value,
                    p4="NOT_RUN",
                    absolute_difference="NOT_RUN",
                    denominator="NOT_RUN",
                    relative_difference="NOT_RUN",
                    status="NOT_RUN_P4_REFERENCE_NOT_QUALIFIED",
                    reason="p4 unique run stopped at numeric cutoff before retained reference; no comparison started",
                )
            )
        for name in (
            "total_L2",
            "scattered_L2",
            "total_scaled_curl",
            "scattered_scaled_curl",
            "six_point_complex_E_H",
            "four_classes_40_complex_channels",
            "per_channel_power",
            "air_substrate_grating_interface_regions",
        ):
            writer.writerow(
                dict(
                    quantity=name,
                    p3_original="V1_RETAINED",
                    p4="NOT_RUN",
                    absolute_difference="NOT_RUN",
                    denominator="NOT_RUN",
                    relative_difference="NOT_RUN",
                    status="NOT_RUN_P4_REFERENCE_NOT_QUALIFIED",
                    reason="no qualified p4; no different-length coefficient subtraction",
                )
            )
    run_records = {
        STAGES[0]: dict(
            index_sha256=sha(
                ROOT
                / "benchmarks/artifacts/task42extra/index_v7_p_transfer_checks.json"
            ),
            source_sha=SOURCE,
            run_directory=indices[STAGES[0]]["run_directory"],
            files=indices[STAGES[0]]["files"],
            status=checks["status"],
        ),
        STAGES[1]: dict(
            index=None,
            source_sha=SOURCE,
            run_directory=str(directory),
            status="P4_REFERENCE_TIME_BLOCKED",
            request_sha256=sha(directory / "budget_stop_request.json"),
            raw_manifest_sha256=sha(directory / "run_manifest.json"),
            run_summary_sha256=sha(directory / "run_summary.json"),
            stages_sha256=sha(directory / "stages.jsonl"),
            p4_input=native,
            reference=None,
        ),
        STAGES[2]: dict(
            status="NOT_RUN_P4_REFERENCE_NOT_QUALIFIED", index=None, run_directory=None
        ),
    }
    write(
        "run_index_v7.json",
        dict(
            schema="task42extra.run-index.v7",
            source_sha=SOURCE,
            review_release="ecabef960cdf1ac194ef293ff83c65b14e8b7ba3",
            reviewed_baseline="fa83e9cb751ecd213e04ce79804cda4643fc3232",
            original_base="fbac3d8777fcfd897d93b898cb9f460f79ddd6ff",
            runs=run_records,
            old_reference=oldref["files"]["reference"],
            old_native=core["files"]["native"],
            old_e4_index_sha256=sha(legacy_path),
            **POLICY,
        ),
    )
    resource_costs(indices)
    print(
        json.dumps(
            dict(
                U0_pass=True,
                p4_reference="P4_REFERENCE_TIME_BLOCKED",
                U2="NOT_RUN",
                source_sha=SOURCE,
            )
        )
    )


def main():
    indices = {
        stage: index(stage)[0]
        for stage in STAGES
        if (
            ROOT / "benchmarks/artifacts/task42extra" / ("index_" + stage + ".json")
        ).exists()
    }
    if "--resources-only" in sys.argv:
        resource_costs(indices)
        return
    if STAGES[1] not in indices:
        partial_main(indices)
        return
    require(
        len(list(RESULTS.glob("task42extra_v7_p4_reference_*"))) == 1,
        "UNIQUE_P4_START_FAILED",
    )
    for item in indices.values():
        manifest = read(Path(item["run_directory"]) / "run_manifest.json")
        require(
            item["source_sha"] == manifest["source_sha"] == SOURCE,
            "ACTUAL_SOURCE_DIFFERS",
        )
        for data in (item["result"], manifest):
            require(
                all(data[k] == v for k, v in POLICY.items()), "AUDIT_POLICY_CHANGED"
            )
        require(
            manifest["gram_sha256"] is None
            and manifest["mpi_size"] == 1
            and manifest["math_threads"] == 1,
            "AUTHORITY_ENVIRONMENT_CHANGED",
        )
    checks, ref, comparison = (indices[s]["result"] for s in STAGES)
    core, _ = index("e1_fe")
    oldref, _ = index("e3_reference")
    oldp4, oldpath = index("e4_p4")
    require(
        core["files"]["native"]["sha256"] == EXPECTED["native"]
        and oldref["files"]["reference"]["sha256"] == EXPECTED["reference"],
        "FROZEN_P3_CHANGED",
    )
    require(
        oldp4["result"]["status"] == "DISCRETIZATION_NOT_QUALIFIED"
        and set(oldp4["files"]) == {"result"},
        "OLD_P4_NOT_RUN_REWRITTEN",
    )
    transfer_pass = all(
        max(
            checks[key][field]
            for field in (
                "common_point_E_relative",
                "common_point_curl_relative",
                "MPC_embedding_relative",
            )
        )
        <= 1e-10
        for key in ("small_transfer", "M5_transfer")
    )
    action_pass = all(
        max(
            sample[k]
            for k in (
                "original_native_relative",
                "adjoint_dot_relative",
                "augmented_native_relative",
                "original_port_operation_relative",
            )
        )
        <= 1e-10
        for sample in checks["action"]["samples"]
    )
    require(transfer_pass and action_pass, "U0_RAW_PAIR_FAILED")
    require(
        checks["independent_families"] == dict(edge=4992, face=28800, interior=41472),
        "MEASURED_P4_FAMILIES_DIFFERS",
    )
    packet = load_native(indices[STAGES[0]]["files"]["native"]["path"])
    with np.load(
        indices[STAGES[1]]["files"]["reference"]["path"], allow_pickle=False
    ) as x:
        c = np.array(x["c_scattered"])
        alpha = np.array(x["alpha_scattered"])
        total = np.array(x["alpha_total"])
        require(str(x["source_sha"]) == SOURCE, "PACKET_SOURCE_DIFFERS")
        require(
            c.shape == (75264,) and c.dtype == np.complex128, "P4_FROZEN_STATE_SHAPE"
        )
        require(
            np.linalg.norm(alpha - packet.alpha(c)) / np.linalg.norm(alpha) <= 1e-10
            and np.linalg.norm(total - alpha - packet.a["background_alpha"])
            / np.linalg.norm(total)
            <= 1e-10,
            "P4_PORT_SCHEMA_DIFFERS",
        )
    audit = packet.audit(c)
    rg = reference_gate(ref, audit)
    cg = comparison_gate(comparison)
    require(rg["qualified"], "P4_REFERENCE_FAILED")
    original_physics = oldref["result"]["physics"]["records"]["REFERENCE"]
    new_physics = ref["physics"]["records"]["REFERENCE"]
    ordering = comparison["channel_alignment_p4_indices"]
    require(sorted(ordering) == list(range(40)), "CHANNEL_ALIGNMENT_NOT_BIJECTIVE")
    for label, physics in (("p3", original_physics), ("p4", new_physics)):
        for kind in ("total", "scattered"):
            norms = np.sqrt(comparison["energy_pairs"][kind][label])
            require(
                np.allclose(
                    norms,
                    physics[kind + "_L2_scaled_curl_norms"],
                    rtol=1e-10,
                    atol=1e-13,
                ),
                "COMMON_SPACE_REFERENCE_NORMS_CHANGED",
            )
            for quantity, oldname in (("E", "E"), ("H_code", "H_code")):
                require(
                    np.allclose(
                        vector(comparison["samples"][kind][label][quantity]),
                        vector(physics["selected_" + kind + "_" + oldname]),
                        rtol=1e-10,
                        atol=1e-13,
                    ),
                    "SIX_POINT_REFERENCE_FIELDS_CHANGED",
                )
        for kind in ("total", "outgoing", "boundary_outgoing", "scattered"):
            expected = vector(physics["ordered_complex_" + kind + "_channels"])
            if label == "p4":
                expected = expected[ordering]
            require(
                np.array_equal(vector(comparison["channels"][kind][label]), expected),
                "CHANNEL_REFERENCE_FIELDS_CHANGED",
            )
        expected = np.asarray(physics["ordered_per_channel_power"])
        if label == "p4":
            expected = expected[ordering]
        require(
            np.array_equal(comparison["powers"][label], expected),
            "POWER_REFERENCE_FIELDS_CHANGED",
        )
        keys = comparison["powers"]["keys"]
        for side, name in (("top", "R_total"), ("bottom", "T_total")):
            value = sum(
                power
                for key, power in zip(keys, comparison["powers"][label], strict=True)
                if key["side"] == side
            )
            require(close(value, physics["port"][name]), "POWER_SUM_REFERENCE_DIFFERS")
    require(
        comparison["MUMPS_symbolic_numeric_solve_count"] == [0, 0, 0]
        and ref["MUMPS_symbolic_numeric_solve_count"] == [1, 1, 1],
        "FACTOR_COUNT_CHANGED",
    )
    identity = checks["identity"]
    minimal_identity = {
        k: identity[k]
        for k in (
            "mesh_coordinates_sha256",
            "geometry_cell_dofs_sha256",
            "cell_tags_sha256",
            "centers_sha256",
            "mode_manifest_sha256",
            "cells",
            "channels",
            "degree",
            "native_rows",
            "slaves",
            "full_independent_rows",
            "interior_rows",
            "dtn_quadrature_degree",
            "actual_material_cell_counts",
            "actual_notch_cells",
            "nonseparable_y_z_witness",
            "local_tensor_classes",
            "local_tensor_payload_bytes",
            "packet_payload_bytes",
            "packet_array_hashes",
        )
    }
    write(
        "p_transfer_checks_v7.json",
        dict(
            schema="task42extra.p-transfer.v7",
            source_sha=SOURCE,
            transfer_pass=transfer_pass,
            action_pass=action_pass,
            small_transfer=checks["small_transfer"],
            M5_transfer=checks["M5_transfer"],
            action=checks["action"],
            independent_families=checks["independent_families"],
            identity=minimal_identity,
            array_capacity=checks["array_capacity"],
            physics_equivalence_fields=checks["physics_equivalence_fields"],
            old_e4_not_run_index_sha256=sha(oldpath),
            **POLICY,
        ),
    )
    physics = ref["physics"]["records"]["REFERENCE"]
    write(
        "p4_reference_v7.json",
        dict(
            schema="task42extra.p4-reference.v7",
            source_sha=SOURCE,
            gate=rg,
            direct=ref["direct"],
            MUMPS_symbolic_numeric_solve_count=ref[
                "MUMPS_symbolic_numeric_solve_count"
            ],
            new_Gram_matrix_count=0,
            new_Gram_factor_count=0,
            independent_checker_packet_counts=packet.counts,
            physics={
                k: physics[k]
                for k in (
                    "port",
                    "volume",
                    "ordered_complex_total_channels",
                    "ordered_complex_outgoing_channels",
                    "ordered_complex_boundary_outgoing_channels",
                    "ordered_complex_scattered_channels",
                    "ordered_per_channel_power",
                )
            },
            identity=minimal_identity,
            p4_native_sha256=ref["p4_native_sha256"],
            p4_reference_sha256=ref["p4_reference_sha256"],
            field_schema={
                k: ref[k]
                for k in (
                    "c_scattered_meaning",
                    "alpha_scattered_meaning",
                    "alpha_total_meaning",
                )
            },
            **POLICY,
        ),
    )
    compact_comparison = {
        k: v
        for k, v in comparison.items()
        if k not in ("physics_equivalence_fields", "regions", "powers")
    }
    compact_comparison["regions"] = {
        name: {k: v for k, v in value.items() if k != "cell_ids"}
        for name, value in comparison["regions"].items()
    }
    compact_comparison["powers"] = {
        k: v for k, v in comparison["powers"].items() if k != "keys"
    }
    compact_comparison["channel_physical_keys"] = [
        dict(
            side=x["side"],
            m=x["m"],
            n=x["n"],
            polarization=x["polarization"],
            reference_plane_nm=8.75 if x["side"] == "top" else -1.25,
            propagating=x["propagating"],
        )
        for x in comparison["powers"]["keys"]
    ]
    write(
        "gate_decisions_v7.json",
        dict(
            schema="task42extra.raw-gates.v7",
            source_sha=SOURCE,
            U0_pass=transfer_pass and action_pass,
            p4_reference=rg,
            p3_p4=cg,
            full_comparison=compact_comparison,
            old_e4_not_run_preserved=True,
            old_neural_failure_conclusions_unchanged=True,
            official_neural_candidate_results=False,
            **POLICY,
        ),
    )
    comparison_csv(comparison)
    runs = {
        stage: dict(
            index_path=str(
                Path(ROOT / "benchmarks/artifacts/task42extra")
                / ("index_" + stage + ".json")
            ),
            index_sha256=sha(
                Path(ROOT / "benchmarks/artifacts/task42extra")
                / ("index_" + stage + ".json")
            ),
            source_sha=item["source_sha"],
            run_directory=item["run_directory"],
            files=item["files"],
            status=item["result"]["status"],
        )
        for stage, item in indices.items()
    }
    write(
        "run_index_v7.json",
        dict(
            schema="task42extra.run-index.v7",
            source_sha=SOURCE,
            review_release="ecabef960cdf1ac194ef293ff83c65b14e8b7ba3",
            reviewed_baseline="fa83e9cb751ecd213e04ce79804cda4643fc3232",
            original_base="fbac3d8777fcfd897d93b898cb9f460f79ddd6ff",
            runs=runs,
            old_reference=oldref["files"]["reference"],
            old_native=core["files"]["native"],
            old_e4_index_sha256=sha(oldpath),
            **POLICY,
        ),
    )
    resource_costs(indices)
    print(
        json.dumps(
            dict(
                U0_pass=True,
                p4_reference_qualified=rg["qualified"],
                comparison=cg["status"],
                source_sha=SOURCE,
            )
        )
    )


if __name__ == "__main__":
    main()
