"""Recompute Task42extra decisions from compact raw metrics, without a solve."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROUTES = ("FEINN-EUC", "FEINN-DUAL", "FREE-FE-DUAL")
EQUATION_KEYS = (
    "native_relative",
    "augmented_relative",
    "original_total_augmented_relative",
    "port_full_rhs_relative",
    "port_operation_relative",
)
ERROR_KEYS = (
    "total_L2",
    "total_scaled_curl",
    "scattered_L2",
    "scattered_scaled_curl",
    "selected_total_E",
    "selected_total_H",
    "selected_scattered_E",
    "selected_scattered_H",
    "ordered_total_channels",
    "ordered_scattered_channels",
    "ordered_outgoing_channels",
    "ordered_boundary_outgoing_channels",
) + tuple(
    f"{kind}_point_{point}"
    for kind in (
        "selected_total_E",
        "selected_total_H",
        "selected_scattered_E",
        "selected_scattered_H",
    )
    for point in range(6)
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(2**20):
            value.update(block)
    return value.hexdigest()


def below(value, limit):
    return (
        isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= limit
    )


def equations(audit, limit):
    keys = list(EQUATION_KEYS)
    if "independent_DOLFINx_total_native_relative" in audit:
        keys.append("independent_DOLFINx_total_native_relative")
    return bool(
        all(below(audit.get(key), limit) for key in keys)
        and audit.get("slave_storage_max") == 0
    )


def resources(record, cap=16 * 2**30):
    return bool(
        below(record.get("sampled_process_tree_rss_peak_bytes"), cap)
        and record.get("sampled_process_tree_swap_peak_bytes") == 0
        and record.get("descendants_cleared")
        and record.get("leader_exit_code") == 0
        and record.get("classification") == "COMPLETED"
    )


def complex_values(value):
    if isinstance(value, dict):
        return [complex(value["real"], value["imag"])]
    values = []
    for item in value:
        values.extend(complex_values(item))
    return values


def array_relative(left, right, natural=1):
    a, b = complex_values(left), complex_values(right)
    if len(a) != len(b):
        raise ValueError("complex observable shape mismatch")
    absolute = math.sqrt(sum(abs(x - y) ** 2 for x, y in zip(a, b, strict=True)))
    denominator = max(math.sqrt(sum(abs(x) ** 2 for x in b)), 1e-12 * natural)
    return absolute / denominator


def check(evidence, verify_raw=False):
    def read(name):
        return json.loads((evidence / name).read_text())

    inputs = read("interface_gates_v1.json")["stages"]
    cost = read("resource_costs_v1.json")
    summaries = cost["formal_summary_by_stage"]
    native = inputs["e1_fe"]["result"]["native"]
    moments = inputs["e1_fe"]["result"]["complete_moments"]
    gram = inputs["e1_fe"]["result"]["gram"]
    identity = inputs["e1_fe"]["result"]["identity"]
    grad = inputs["e1_grad"]["result"]
    smoke = inputs["e1_smoke"]["result"]
    interfaces = {
        "positive_manufactured": all(
            below(smoke.get(key), 1e-10)
            for key in ("residual_relative", "L2_relative", "coefficient_relative")
        ),
        "complete_moments": all(
            below(moments.get(key), 1e-10)
            for key in (
                "interpolation_relative",
                "independent_custom_relative",
                "shared_entity_relative",
                "mpc_expansion_relative",
            )
        )
        and moments.get("nonzero_slave_phase") is True
        and moments.get("orientation_classes", 0) >= 2
        and below(moments.get("basis_relative"), 1e-10)
        and all(
            below(value.get("relative"), 1e-10) and value.get("nonzero_norm", 0) > 0
            for value in moments["component_checks"].values()
        )
        and {key: value["count"] for key, value in moments["component_checks"].items()}
        == {"edge": 3744, "face": 14400, "interior": 13824},
        "full_uncondensed_model": identity.get("full_independent_rows") == 31968
        and identity.get("interior_rows") == 13824
        and identity.get("channels") == 40
        and identity.get("nonseparable_y_z_witness") is True
        and identity.get("interior_elimination") is False,
        "native_ports": len(native["samples"]) >= 3
        and all(
            below(sample.get(key), 1e-10)
            for sample in native["samples"]
            for key in (
                "original_native_relative",
                "adjoint_dot_relative",
                "augmented_native_relative",
                "original_port_operation_relative",
            )
        )
        and all(sample["arbitrary_interior_norm"] > 0 for sample in native["samples"])
        and below(native.get("nonzero_FE_and_port_load_relative"), 1e-10)
        and below(native.get("nonzero_port_load_operation_relative"), 1e-10),
        "Gram_variational": below(gram.get("hermitian_relative"), 1e-12)
        and gram.get("constrained_projection_count") == 1
        and gram.get("ell_nm") == 5
        and gram.get("material_independent") is True
        and gram.get("rows") == 31968
        and gram.get("label") == "RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR"
        and all(item["real"] > 0 for item in gram["nonzero_positive_forms"]),
        "Gram_solve": below(grad.get("Gram_max_solve_relative"), 1e-11)
        and grad["Gram_factor"]["numeric"]["positive_pivots"] == 31968,
        "quadrature": below(grad["quadrature_15_30"].get("relative"), 1e-8),
    }
    for name, record in grad["gradients"].items():
        interfaces[name + "_batch"] = all(
            below(value.get("relative"), 1e-10) for value in record["batch1_8"].values()
        )
        directions = record["directional_derivatives"]
        interfaces[name + "_gradient"] = len(directions) >= 3 and all(
            len(direction["samples"]) == 3
            and any(
                below(direction["samples"][j].get("relative_error"), 1e-5)
                and below(direction["samples"][j + 1].get("relative_error"), 1e-5)
                for j in (0, 1)
            )
            for direction in directions
        )
    for name in inputs:
        interfaces[name + "_resource"] = resources(summaries[name])
    interface_pass = all(interfaces.values())
    physics_path = evidence / "blind_physics_v1.json"
    physics = read(physics_path.name) if physics_path.exists() else None
    reference_pass = bool(
        physics
        and equations(physics["physics"]["records"]["REFERENCE"]["audit"], 1e-10)
        and resources(summaries["e3_reference"])
        and physics["reference"]["factor_released"]
        and physics["reference"]["matrix_released"]
        and physics["reference"]["rss_after_release_bytes"]
        < physics["reference"]["rss_before_release_bytes"]
    )
    reference_energy_pass = False
    if physics:
        reference_record = physics["physics"]["records"]["REFERENCE"]
        reference_energy_pass = below(
            abs(
                reference_record["port"]["R_total"]
                + reference_record["port"]["T_total"]
                + reference_record["volume"]["A_volume_total"]
                - 1
            ),
            1e-5,
        ) and below(
            abs(
                reference_record["port"]["A_balance"]
                - reference_record["volume"]["A_volume_total"]
            ),
            1e-5,
        )
        reference_pass = bool(reference_pass and reference_energy_pass)
    routes = {}
    initial_hashes = []
    for name in ROUTES:
        result = cost["route_results"].get(name)
        if result is None:
            routes[name] = dict(status="not_run_or_not_frozen", qualified=False)
            continue
        initial_hashes.append(result["initial_c_sha256"])
        gram_factor = result.get("Gram_factor")
        gram_pass = (
            name == "FEINN-EUC"
            and gram_factor is None
            or bool(
                gram_factor
                and gram_factor["label"] == "RESEARCH_ONLY_GLOBAL_RIESZ_FACTOR"
                and below(gram_factor.get("max_solve_true_relative"), 1e-11)
                and gram_factor["numeric"]["positive_pivots"] == 31968
            )
        )
        row = dict(
            numerical_equation_pass=equations(result["final_audit"], 1e-6),
            resource_pass=resources(summaries[name]),
            budget_pass=below(result["counts"]["closures"], 4000)
            and below(result["route_worker_wall_seconds"], 10800),
            Gram_solve_contract_pass=bool(gram_pass),
            from_zero_attributed_seconds=cost["from_zero_attribution"][name][
                "from_zero_attributed_seconds"
            ],
            target_solution_exclusion_pass=result["target_reference_loaded"] is False
            and result["global_Maxwell_factor_created"] is False
            and result["global_Maxwell_CSR_created"] is False,
            full_unknowns_pass=result["full_independent_complex_FE"] == 31968
            and result["full_internal_moments"] == 13824
            and result["full_ports"] == 40,
            source_sha=result["source_sha"],
            stop_reason=result["stop_reason"],
            closures=result["counts"]["closures"],
            status=result["status"],
            qualified=False,
        )
        if physics:
            comparison = physics["comparisons"][name]
            record = physics["physics"]["records"][name]
            authority = physics["physics"]["records"]["REFERENCE"]
            audit = record["audit"]
            # FE volume norm differences come from independent integration; ratio is re-derived.
            recomputed = {}
            for key, error in comparison["errors"].items():
                if error["denominator"] <= 0:
                    raise ValueError("nonpositive error denominator")
                recomputed[key] = error["absolute"] / error["denominator"]
            for key in (
                "selected_total_E",
                "selected_total_H",
                "selected_scattered_E",
                "selected_scattered_H",
            ):
                observable = key if not key.endswith("_H") else key + "_code"
                if observable not in record:
                    observable = key + "_code"
                recomputed[key] = array_relative(
                    record[observable], authority[observable]
                )
                for point in range(6):
                    recomputed[f"{key}_point_{point}"] = array_relative(
                        record[observable][point], authority[observable][point]
                    )
            for key, observable in (
                ("ordered_total_channels", "ordered_complex_total_channels"),
                ("ordered_scattered_channels", "ordered_complex_scattered_channels"),
                ("ordered_outgoing_channels", "ordered_complex_outgoing_channels"),
                (
                    "ordered_boundary_outgoing_channels",
                    "ordered_complex_boundary_outgoing_channels",
                ),
            ):
                recomputed[key] = array_relative(
                    record[observable], authority[observable]
                )
            for key, relative in recomputed.items():
                if abs(relative - comparison["errors"][key]["relative"]) > 1e-12 * max(
                    1, relative
                ):
                    raise ValueError("complex/norm error differs from raw record")
            power_differences = [
                abs(record["port"][key] - authority["port"][key])
                for key in ("R_total", "T_total", "A_balance")
            ]
            power_differences.append(
                abs(
                    record["volume"]["A_volume_total"]
                    - authority["volume"]["A_volume_total"]
                )
            )
            channel_power_difference = max(
                abs(a - b)
                for a, b in zip(
                    record["ordered_per_channel_power"],
                    authority["ordered_per_channel_power"],
                    strict=True,
                )
            )
            closure = abs(
                record["port"]["R_total"]
                + record["port"]["T_total"]
                + record["volume"]["A_volume_total"]
                - 1
            )
            absorption = abs(
                record["port"]["A_balance"] - record["volume"]["A_volume_total"]
            )
            row.update(
                numerical_equation_pass=equations(audit, 1e-6),
                field_pass=all(below(recomputed.get(key), 1e-4) for key in ERROR_KEYS),
                power_pass=all(below(value, 1e-5) for value in power_differences)
                and below(channel_power_difference, 1e-6),
                energy_pass=below(closure, 1e-5) and below(absorption, 1e-5),
            )
            mathematical = all(
                row[key]
                for key in (
                    "numerical_equation_pass",
                    "field_pass",
                    "power_pass",
                    "energy_pass",
                )
            )
            if (
                bool(mathematical and physics["physics"]["reference_pass"])
                != comparison["qualified"]
            ):
                raise ValueError("raw numerical Gate disagreement")
            row["qualified"] = bool(
                reference_pass
                and interface_pass
                and mathematical
                and all(
                    row[key]
                    for key in (
                        "resource_pass",
                        "budget_pass",
                        "Gram_solve_contract_pass",
                        "target_solution_exclusion_pass",
                        "full_unknowns_pass",
                    )
                )
            )
            row["status"] = (
                "FEINN_DISCRETE_PASS"
                if row["qualified"]
                else "FEINN_OPTIMIZATION_NEGATIVE"
            )
        row["reported_numeric_worker_status"] = result["status"]
        row["failure_kind"] = "none" if row["qualified"] else "accuracy_or_optimization"
        if result["stop_reason"] == "RIESZ_RESOURCE_BLOCKED":
            row.update(
                status="RIESZ_RESOURCE_BLOCKED", failure_kind="auxiliary_resource"
            )
        elif result["stop_reason"].startswith("NUMERICAL_OR_BACKEND_FAILED"):
            row.update(status="BLOCKED", failure_kind="numerical_or_backend")
        elif result["stop_reason"] == "NONFINITE":
            row.update(status="BLOCKED", failure_kind="nonfinite_numeric")
        elif not row["resource_pass"]:
            row.update(status="CONTROLLED_STOP", failure_kind="resource_or_supervision")
        elif row["numerical_equation_pass"] and not reference_pass:
            row.update(
                status="BLOCKED", failure_kind="independent_reference_not_qualified"
            )
        routes[name] = row
    p_record = read("p_check_v1.json")
    p4_status = (
        "BLOCKED"
        if p_record.get("status") == "not_run"
        else "DISCRETIZATION_NOT_QUALIFIED"
    )
    p4_qualified = False
    if p_record.get("p4_reference") == "measured":
        authority4 = p_record["reference"]
        p4_qualified = bool(
            any(row["qualified"] for row in routes.values())
            and resources(summaries["e4_p4"])
            and equations(authority4["original_full_equation_audit"], 1e-10)
            and below(authority4.get("original_augmented_relative"), 1e-10)
            and authority4.get("factor_released") is True
            and authority4.get("matrix_released") is True
            and authority4["rss_after_release_bytes"]
            < authority4["rss_before_release_bytes"]
            and p_record.get("errors")
            and all(
                below(value["absolute"] / value["denominator"], 1e-3)
                for value in p_record["errors"].values()
            )
        )
        p4_status = "P4_CHECK_PASS_LIMITED_DISCRETE" if p4_qualified else p4_status
    p4 = dict(
        record=p_record,
        independently_recomputed_status=p4_status,
        qualified=p4_qualified,
        target_PDE_started=False,
        reason_if_blocked="E4 has no frozen stage result; see E3/E4 formal workflow record"
        if p4_status == "BLOCKED"
        else None,
    )
    same_zero_start = (
        len(initial_hashes) == 3
        and len(set(initial_hashes)) == 1
        and all(
            result["initial_scattered_coefficients_zero"]
            for result in cost["route_results"].values()
        )
    )
    raw_verification = "not_requested; Gates recomputed from compact numeric fields"
    if verify_raw:
        for run in read("run_index_v1.json")["stages"]:
            if digest(run["index_path"]) != run["index_sha256"]:
                raise ValueError("stage index hash changed")
            for entry in run["files"].values():
                if digest(entry["path"]) != entry["sha256"]:
                    raise ValueError("large artifact hash changed")
            for name, expected in run["run_record_hashes"].items():
                if digest(Path(run["run_directory"]) / name) != expected:
                    raise ValueError("run provenance hash changed")
            run_directory = Path(run["run_directory"])
            manifest = json.loads((run_directory / "run_manifest.json").read_text())
            root = Path(read("run_index_v1.json")["root"])
            if (
                manifest["source_sha"] != run["source_sha"]
                or (run_directory / "source_sha.txt").read_text().strip()
                != run["source_sha"]
            ):
                raise ValueError("recorded runtime source differs from frozen source")
            if digest(run_directory / "input_original.dat") != manifest["input_sha256"]:
                raise ValueError("input identity differs from original input")
            if (
                digest(root / "input/materials/si_optical_constants_v1.json")
                != manifest["material_table_sha256"]
            ):
                raise ValueError("frozen material identity differs")
            if (
                digest(run_directory / "resource_baseline.json")
                != manifest["resource_baseline_sha256"]
            ):
                raise ValueError("resource baseline identity differs")
            for entry in manifest.get("qualified_environment_record", {}).values():
                if digest(entry["path"]) != entry["sha256"]:
                    raise ValueError("qualified task-local ABI record changed")
            for filename, expected in manifest.get(
                "numerical_module_sha256", {}
            ).items():
                blob = subprocess.check_output(
                    ["git", "show", f"{run['source_sha']}:{filename}"], cwd=root
                )
                if hashlib.sha256(blob).hexdigest() != expected:
                    raise ValueError(
                        "runtime module differs from its recorded Git source blob"
                    )
            original = json.loads(Path(run["files"]["result"]["path"]).read_text())
            original_index = json.loads(Path(run["index_path"]).read_text())
            if original != original_index["result"]:
                raise ValueError("raw result differs from frozen index")
            stage = run["stage"]
            if original_index["source_sha"] != run["source_sha"]:
                raise ValueError("run source SHA transcribed incorrectly")
            if stage in inputs:
                expected = json.loads(json.dumps(original))
                if stage == "e1_fe":
                    expected["identity"].pop("modes", None)
                if inputs[stage]["result"] != expected:
                    raise ValueError(
                        "compact interface numeric transcription differs from raw"
                    )
            elif stage in ROUTES:
                expected = json.loads(json.dumps(original))
                expected.pop("audits", None)
                compact = dict(cost["route_results"][stage])
                completed = compact.pop(
                    "completed_loss_gradient_closures_derived_from_history"
                )
                incomplete = compact.pop(
                    "incomplete_or_failed_closure_attempts_derived"
                )
                for key in ("raw_result_sha256", "source_sha"):
                    compact.pop(key)
                if compact != expected:
                    raise ValueError(
                        "compact route numeric transcription differs from raw"
                    )
                history = [
                    json.loads(line)
                    for line in Path(run["files"]["history"]["path"])
                    .read_text()
                    .splitlines()
                ]
                if (
                    completed != sum(row.get("kind") == "closure" for row in history)
                    or incomplete != original["counts"]["closures"] - completed
                ):
                    raise ValueError(
                        "closure counts differ from frozen complete-call history"
                    )
            elif stage == "e3_reference":
                compact = dict(physics)
                for key in ("raw_result_sha256", "source_sha", "ordered_mode_manifest"):
                    compact.pop(key)
                if compact != original:
                    raise ValueError(
                        "compact physics numeric transcription differs from raw"
                    )
            elif stage == "e4_p4" and read("p_check_v1.json") != original:
                raise ValueError("compact p-check transcription differs from raw")
            summary = json.loads(
                (Path(run["run_directory"]) / "run_summary.json").read_text()
            )
            if any(
                summary.get(key) != value
                for key, value in summaries[stage].items()
                if key
                not in (
                    "launch_through_summary_wall_seconds_derived",
                    "full_wall_boundary",
                )
            ):
                raise ValueError("compact resource transcription differs from raw")
        for item in (
            cost["all_formal_workflows_including_failures"] + cost["light_checks"]
        ):
            if digest(item["path"]) != item["sha256"]:
                raise ValueError("research ledger summary hash changed")
        derived_supervised = sum(
            item["elapsed_seconds"]
            for item in cost["all_formal_workflows_including_failures"]
            + cost["light_checks"]
        )
        derived_full = sum(
            item["launch_through_summary_wall_seconds_derived"]
            for item in cost["all_formal_workflows_including_failures"]
            + cost["light_checks"]
        )
        if (
            abs(derived_supervised - cost["actual_supervised_research_seconds"]) > 1e-6
            or abs(
                derived_full
                - cost["full_launch_through_summary_research_seconds_derived"]
            )
            > 1e-6
        ):
            raise ValueError("research ledger aggregation differs from stage costs")
        raw_verification = "all frozen artifacts/run records match; compact numeric transcription and research aggregation match raw"
    dual, euc, free = [
        routes[name] for name in ("FEINN-DUAL", "FEINN-EUC", "FREE-FE-DUAL")
    ]
    metric = "inconclusive_not_equal_accuracy"
    if dual["qualified"] and not euc["qualified"]:
        metric = "positive_pilot_only_DUAL_qualified"
    elif dual["qualified"] and euc["qualified"]:
        metric = "inconclusive_shared_workstation_performance"
    neural = (
        "inconclusive_shared_workstation_performance"
        if dual["qualified"] and free["qualified"]
        else "inconclusive_not_equal_accuracy"
    )
    return dict(
        schema="task42extra.independent-gates.v1",
        interfaces=interfaces,
        interface_all_pass=bool(interface_pass),
        same_zero_start=same_zero_start,
        independent_reference_pass=reference_pass,
        reference_energy_pass=reference_energy_pass,
        routes=routes,
        actual_supervised_research_seconds=cost["actual_supervised_research_seconds"],
        research_budget_pass=below(
            cost["full_launch_through_summary_research_seconds_derived"], 57600
        ),
        loss_metric_signal=metric,
        neural_increment=neural,
        p4=p4,
        raw_verification=raw_verification,
        target_5nm="not_run/not_qualified",
        target_0p7nm="not_run/not_qualified",
        no_merge=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-raw", action="store_true")
    arguments = parser.parse_args()
    result = check(arguments.evidence, arguments.verify_raw)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
