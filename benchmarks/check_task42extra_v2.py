"""Independent compact V2 evidence from frozen raw records, without a solve."""

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "benchmarks/artifacts/task42extra"
RESULTS = ROOT / "results/task42extra"
CHECKS = ROOT / "tmp/task42extra/checks"
RECORDS = ROOT / "docs/task042extra_feinn_5nm/outcomes/records"
NEW = "FREE-FE-DUAL-GRAM-DIAG"
STAGES = ("v2_state_diagnostic", "v2_scaling_checks", NEW, "v2_compare_only")
V1_BASE_SECONDS = 26240.100355625153


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while block := f.read(2**20):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    path = RECORDS / name
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return path


def index(stage):
    path = ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")
    item = read(path)
    for key, entry in item["files"].items():
        raw = Path(entry["path"]).resolve()
        if not raw.is_relative_to(ARTIFACTS.resolve()) or sha(raw) != entry["sha256"]:
            raise ValueError(f"frozen artifact changed: {stage}/{key}")
    return item, path


def complex_array(value):
    if isinstance(value, dict) and set(value) == {"real", "imag"}:
        return [complex(value["real"], value["imag"])]
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(complex_array(v))
        return out
    raise ValueError("unexpected complex observable serialization")


def close(actual, expected, tolerance=2e-11):
    return math.isfinite(actual) and math.isfinite(expected) and abs(actual - expected) <= tolerance * max(1, abs(expected))


def channel_error(candidate, authority, key, recorded):
    a = np.asarray(complex_array(candidate[key]), dtype=np.complex128)
    b = np.asarray(complex_array(authority[key]), dtype=np.complex128)
    if a.shape != (40,) or b.shape != (40,):
        raise ValueError("complete ordered 40-channel inventory missing")
    absolute = float(np.linalg.norm(a - b))
    denominator = float(max(np.linalg.norm(b), 1e-12))
    relative = absolute / denominator
    if not all(close(value, recorded[name]) for name, value in (
        ("absolute", absolute), ("denominator", denominator), ("relative", relative)
    )):
        raise ValueError(f"recorded {key} error/denominator differs from raw complex vector")
    return dict(key=key, absolute=absolute, denominator=denominator, relative=relative)


def resource_record(directory):
    summary = read(directory / "run_summary.json")
    manifest = read(directory / "run_manifest.json")
    started = datetime.strptime(directory.name.rsplit("_", 1)[-1], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc).timestamp()
    full_wall = (directory / "run_summary.json").stat().st_mtime - started
    return dict(
        directory=str(directory),
        source_sha=manifest["source_sha"],
        input_sha256=manifest["input_sha256"],
        physical_model_sha256=manifest["physical_model_sha256"],
        material_sha256=manifest["material_table_sha256"],
        mesh_sha256=manifest.get("mesh_sha256"),
        mode_sha256=manifest.get("mode_sha256"),
        gram_sha256=manifest.get("gram_sha256"),
        cpu=manifest.get("cpu"),
        mpi=manifest["mpi_size"],
        math_threads=manifest["math_threads"],
        supervised_seconds=summary["elapsed_seconds"],
        launch_to_summary_seconds_derived=full_wall,
        peak_simultaneous_tree_RSS_bytes=summary["sampled_process_tree_rss_peak_bytes"],
        own_tree_swap_peak_bytes=summary["sampled_process_tree_swap_peak_bytes"],
        classification=summary["classification"],
        leader_exit_code=summary["leader_exit_code"],
        descendants_cleared=summary["descendants_cleared"],
        global_swap_diagnostic=summary.get("global_swap_activity"),
        launch_envelope=summary.get("launch_envelope"),
        run_summary_sha256=sha(directory / "run_summary.json"),
    )


def main():
    i = {name: index(name)[0] for name in STAGES}
    core = index("e1_fe")[0]
    old = index("FREE-FE-DUAL")[0]
    ref = index("e3_reference")[0]
    p4 = index("e4_p4")[0]
    if (p4["result"]["status"] != "DISCRETIZATION_NOT_QUALIFIED"
            or set(p4["files"]) != {"result"}):
        raise ValueError("V1 conditional p4 was not a not-run gate")
    if core["files"]["native"]["sha256"] != "2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215":
        raise ValueError("original physical packet differs")
    if i["v2_compare_only"]["result"]["reused_reference"]["sha256"] != ref["files"]["reference"]["sha256"]:
        raise ValueError("compare-only did not reuse V1 reference")
    if i["v2_compare_only"]["result"]["MUMPS_symbolic_numeric_solve_count"] != 0:
        raise ValueError("forbidden reference solve in V2")
    if i["v2_scaling_checks"]["result"]["status"] != "SCALING_CHECKS_PASS":
        raise ValueError("scaling tests did not qualify")
    scale_path = i["v2_state_diagnostic"]["files"]["scale"]["path"]
    with np.load(scale_path, allow_pickle=False) as s:
        a, D = np.array(s["a"]), np.array(s["D"])
    G = sparse.load_npz(core["files"]["gram"]["path"])
    if not (len(D) == G.shape[0] == 31968 and np.all(np.isfinite(D))
            and np.all(D > 0) and np.array_equal(a, G.diagonal().real)
            and np.array_equal(D, 1 / np.sqrt(a))):
        raise ValueError("D is not the exact constrained global Gram diagonal map")
    frozen = i[NEW]["files"]["checkpoint"]["path"]
    with np.load(frozen, allow_pickle=False) as f:
        p, c = np.array(f["parameters"]), np.array(f["c"])
    if p.shape != (63936,) or c.shape != (31968,) or not np.array_equal(c, D * (p[:31968] + 1j * p[31968:])):
        raise ValueError("frozen physical c is not D*y")
    v2 = i["v2_compare_only"]["result"]
    physics = v2["physics"]
    comparison = v2["comparisons"][NEW]
    candidate = physics["records"][NEW]
    authority = physics["records"]["REFERENCE"]
    error_map = comparison["errors"]
    for name, item in error_map.items():
        if not close(item["absolute"] / item["denominator"], item["relative"]):
            raise ValueError(f"field/channel ratio not reproducible: {name}")
    mapping = {
        "ordered_total_channels": "ordered_complex_total_channels",
        "ordered_outgoing_channels": "ordered_complex_outgoing_channels",
        "ordered_boundary_outgoing_channels": "ordered_complex_boundary_outgoing_channels",
        "ordered_scattered_channels": "ordered_complex_scattered_channels",
    }
    channels = {
        key: channel_error(candidate, authority, raw, error_map[key])
        for key, raw in mapping.items()
    }
    # Independently reconcile V1's short outgoing label and the CSV total-port key.
    old_physics = read(RECORDS / "blind_physics_v1.json")
    old_candidate = old_physics["physics"]["records"]["FREE-FE-DUAL"]
    old_authority = old_physics["physics"]["records"]["REFERENCE"]
    old_errors = old_physics["comparisons"]["FREE-FE-DUAL"]["errors"]
    old_channels = {
        key: channel_error(old_candidate, old_authority, raw, old_errors[key])
        for key, raw in mapping.items()
    }
    if not close(old_channels["ordered_outgoing_channels"]["relative"], 0.27517973615673735):
        raise ValueError("V1 short outgoing header did not map to raw outgoing vector")
    if not close(old_channels["ordered_total_channels"]["relative"], 0.5733490017448287):
        raise ValueError("V1 CSV total-port key did not map to raw total vector")
    power = candidate["port"]
    ref_power = authority["port"]
    volume = candidate["volume"]["A_volume_total"]
    ref_volume = authority["volume"]["A_volume_total"]
    deltas = {
        name: abs(power[name] - ref_power[name])
        for name in ("R_total", "T_total", "A_balance")
    }
    deltas["A_volume"] = abs(volume - ref_volume)
    if any(not close(value, comparison["power_absolute_differences"][name]) for name, value in deltas.items()):
        raise ValueError("total power differences differ from raw port/volume")
    per = np.array(candidate["ordered_per_channel_power"], dtype=float)
    per_ref = np.array(authority["ordered_per_channel_power"], dtype=float)
    if per.shape != (40,) or not close(float(np.max(abs(per - per_ref))), comparison["max_channel_power_absolute"]):
        raise ValueError("ordered per-channel power difference mismatches")
    energy = abs(power["R_total"] + power["T_total"] + volume - 1)
    absorption = abs(power["A_balance"] - volume)
    if not close(energy, comparison["energy_closure_absolute"]) or not close(absorption, comparison["absorption_balance_volume_absolute"]):
        raise ValueError("energy/absorption closure mismatches")
    audit = candidate["audit"]
    equations = all(math.isfinite(audit[k]) and audit[k] <= 1e-6 for k in (
        "native_relative", "augmented_relative", "original_total_augmented_relative",
        "independent_DOLFINx_total_native_relative", "port_full_rhs_relative",
        "port_operation_relative"
    )) and audit["slave_storage_max"] == 0
    fields = all(math.isfinite(x["relative"]) and x["relative"] <= 1e-4 for x in error_map.values())
    powers = all(x <= 1e-5 for x in deltas.values()) and max(energy, absorption) <= 1e-5 and float(np.max(abs(per - per_ref))) <= 1e-6
    reference_ok = physics["reference_pass"] and ref["result"]["physics"]["reference_pass"]
    run = {name: resource_record(Path(i[name]["run_directory"])) for name in STAGES}
    failures = []
    for directory in sorted(RESULTS.glob("task42extra_v2_compare_only_*")):
        if directory != Path(i["v2_compare_only"]["run_directory"]):
            item = resource_record(directory)
            if item["classification"] != "WORKER_FAILED":
                raise ValueError("unexpected duplicate compare-only stage")
            failure_file = directory / "worker_failure.json"
            item["failure"] = read(failure_file) if failure_file.exists() else "MPI_INIT_SOCKET_PERMISSION_DENIED_BEFORE_WORKER_RECORD"
            failures.append(item)
    resources = all(
        item["classification"] == "COMPLETED" and item["leader_exit_code"] == 0
        and item["descendants_cleared"] and item["peak_simultaneous_tree_RSS_bytes"] <= 16 * 2**30
        and item["own_tree_swap_peak_bytes"] == 0
        for item in run.values()
    )
    strict = bool(equations and fields and powers and reference_ok and resources)
    positive = bool(
        audit["native_relative"] <= 0.05969144472114
        and audit["augmented_relative"] <= 0.05969144472114
        and error_map["scattered_L2"]["relative"] <= 0.5
        and resources and i[NEW]["result"]["counts"]["closures"] <= 4000
    )
    if strict:
        status = "FREE_SCALED_DISCRETE_PASS"
    elif positive:
        status = "SCALING_DIAGNOSTIC_POSITIVE"
    elif audit["native_relative"] < old["result"]["final_audit"]["native_relative"] and error_map["scattered_L2"]["relative"] > 0.5:
        status = "RESIDUAL_ONLY_NOT_FIELD_PASS"
    else:
        status = "SCALING_DIAGNOSTIC_NEGATIVE"
    gate = dict(
        schema="task42extra.gate-decisions.v2",
        checker="independent raw JSON/complex vectors/Gram diagonal/checkpoint and resource arithmetic; no PDE solve",
        status=status,
        equation_pass=bool(equations), field_and_channel_pass=bool(fields), power_pass=bool(powers),
        V1_reference_pass=bool(reference_ok), resource_pass=bool(resources),
        strict_discrete_pass=strict, diagnostic_positive=positive,
        thresholds=dict(native_augmented_total=1e-6, field_channel=1e-4,
                        total_power=1e-5, per_channel_power=1e-6,
                        diagnostic_native_augmented=0.05969144472114,
                        diagnostic_scattered_E_L2=0.5),
        final_equation=audit, field_and_channel_errors=error_map,
        independently_recomputed_ordered_complex_channels=channels,
        power_absolute_differences=deltas,
        max_channel_power_absolute=float(np.max(abs(per - per_ref))),
        energy_closure_absolute=energy, absorption_balance_volume_absolute=absorption,
        V1_outgoing_header_audit=old_channels,
        p4_reference="not_run", p4_gate_source_sha=p4["source_sha"],
        MUMPS_symbolic_numeric_solve_count_v2=0,
        source_candidate=i[NEW]["source_sha"], source_compare=i["v2_compare_only"]["source_sha"],
    )
    write("gate_decisions_v2.json", gate)
    write("state_diagnostics_v2.json", dict(
        schema="task42extra.state-diagnostics.v2", source_sha=i["v2_state_diagnostic"]["source_sha"],
        scale_file=i["v2_state_diagnostic"]["files"]["scale"],
        result=i["v2_state_diagnostic"]["result"],
    ))
    write("scaling_checks_v2.json", dict(
        schema="task42extra.scaling-checks.v2", source_sha=i["v2_scaling_checks"]["source_sha"],
        result=i["v2_scaling_checks"]["result"],
    ))
    with (RECORDS / "route_comparison_v1.csv").open(newline="") as stream:
        old_row = next(row for row in csv.DictReader(stream) if row["route"] == "FREE-FE-DUAL")
    columns = ["route", "source_sha", "stop_reason", "closure_attempts", "committed_steps", "dual_loss", "native_relative", "augmented_relative", "original_total_augmented_relative", "scattered_E_L2_relative", "scattered_scaled_curl_relative", "total_E_L2_relative", "selected_total_E_relative", "selected_total_H_relative", "ordered_total_channels_relative", "ordered_outgoing_channels_relative", "ordered_scattered_channels_relative", "R_total", "T_total", "A_balance", "A_volume", "energy_closure_absolute", "max_channel_power_absolute", "qualified", "supervised_wall_seconds", "peak_tree_RSS_bytes", "own_swap_peak_bytes", "Gram_setup_seconds", "Gram_solve_seconds", "Gram_solve_count", "A_count", "AH_count", "original_equation_audit_count", "source_identity"]
    old_run = resource_record(Path(old["run_directory"]))
    old_row2 = dict(
        route="FREE-FE-DUAL", source_sha=old["source_sha"], stop_reason=old["result"]["stop_reason"],
        closure_attempts=old_row["closure_attempts"], committed_steps=old_row["committed_steps"],
        dual_loss=old_row["final_loss"], native_relative=old_row["native_relative"],
        augmented_relative=old_row["augmented_relative"], original_total_augmented_relative=old_row["original_total_augmented_relative"],
        scattered_E_L2_relative=old_row["scattered_E_L2_relative"], scattered_scaled_curl_relative=old_row["scattered_scaled_curl_relative"],
        total_E_L2_relative=old_row["total_E_L2_relative"], selected_total_E_relative=old_row["selected_total_E_relative"],
        selected_total_H_relative=old_row["selected_total_H_relative"], ordered_total_channels_relative=old_row["ordered_total_channels_relative"],
        ordered_outgoing_channels_relative=old_channels["ordered_outgoing_channels"]["relative"],
        ordered_scattered_channels_relative=old_channels["ordered_scattered_channels"]["relative"],
        R_total=old_row["R_total"], T_total=old_row["T_total"], A_balance=old_row["A_balance"], A_volume=old_row["A_volume"],
        energy_closure_absolute=old_row["energy_closure_absolute"], max_channel_power_absolute=old_physics["comparisons"]["FREE-FE-DUAL"]["max_channel_power_absolute"],
        qualified=False, supervised_wall_seconds=old_run["supervised_seconds"], peak_tree_RSS_bytes=old_run["peak_simultaneous_tree_RSS_bytes"],
        own_swap_peak_bytes=old_run["own_tree_swap_peak_bytes"], Gram_setup_seconds=old["result"]["Gram_factor"]["setup_seconds"],
        Gram_solve_seconds=old["result"]["Gram_factor"]["solve_seconds"], Gram_solve_count=old["result"]["Gram_factor"]["solve_count"],
        A_count=old["result"]["action_counts"]["A"], AH_count=old["result"]["action_counts"]["AH"],
        original_equation_audit_count=old["result"]["action_counts"]["audit"], source_identity="V1 measured reused",
    )
    trial = i[NEW]["result"]
    row2 = dict(
        route=NEW, source_sha=i[NEW]["source_sha"], stop_reason=trial["stop_reason"],
        closure_attempts=trial["counts"]["closures"], committed_steps=trial["counts"]["committed_outer_steps"],
        dual_loss=trial["final_loss"], native_relative=audit["native_relative"], augmented_relative=audit["augmented_relative"],
        original_total_augmented_relative=audit["original_total_augmented_relative"],
        scattered_E_L2_relative=error_map["scattered_L2"]["relative"],
        scattered_scaled_curl_relative=error_map["scattered_scaled_curl"]["relative"],
        total_E_L2_relative=error_map["total_L2"]["relative"],
        selected_total_E_relative=error_map["selected_total_E"]["relative"],
        selected_total_H_relative=error_map["selected_total_H"]["relative"],
        ordered_total_channels_relative=channels["ordered_total_channels"]["relative"],
        ordered_outgoing_channels_relative=channels["ordered_outgoing_channels"]["relative"],
        ordered_scattered_channels_relative=channels["ordered_scattered_channels"]["relative"],
        R_total=power["R_total"], T_total=power["T_total"], A_balance=power["A_balance"], A_volume=volume,
        energy_closure_absolute=energy, max_channel_power_absolute=float(np.max(abs(per-per_ref))), qualified=strict,
        supervised_wall_seconds=run[NEW]["supervised_seconds"], peak_tree_RSS_bytes=run[NEW]["peak_simultaneous_tree_RSS_bytes"],
        own_swap_peak_bytes=run[NEW]["own_tree_swap_peak_bytes"], Gram_setup_seconds=trial["Gram_factor"]["setup_seconds"],
        Gram_solve_seconds=trial["Gram_factor"]["solve_seconds"], Gram_solve_count=trial["Gram_factor"]["solve_count"],
        A_count=trial["action_counts"]["A"], AH_count=trial["action_counts"]["AH"],
        original_equation_audit_count=trial["action_counts"]["audit"], source_identity="V2 measured single candidate",
    )
    with (RECORDS / "scaled_route_comparison_v2.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows([old_row2, row2])
    records = []
    for stage in STAGES:
        item = i[stage]
        records.append(dict(stage=stage, source_sha=item["source_sha"], run_directory=item["run_directory"],
                            index_sha256=sha(ARTIFACTS / ("index_" + stage.lower().replace("-", "_") + ".json")),
                            files=item["files"], result_status=item["result"]["status"],
                            resource=run[stage]))
    write("run_index_v2.json", dict(
        schema="task42extra.run-index.v2", branch="task42extra_feinn_5nm",
        review_sha="0b61816c0189a2c05812044ab8e1d1513ef0407d",
        pre_registration_sha256=sha(RECORDS / "scaling_design_v2.json"),
        original_native_sha256=core["files"]["native"]["sha256"],
        original_gram_sha256=core["files"]["gram"]["sha256"],
        reused_V1_reference_sha256=ref["files"]["reference"]["sha256"],
        frozen_D_sha256=hashlib.sha256(np.ascontiguousarray(D).tobytes()).hexdigest(),
        stages=records, failed_compare_only_attempts=failures,
        reference_solve_repeated=False, candidate_repeated=False,
    ))
    light = []
    for directory in sorted(CHECKS.glob("v2_*")):
        path = directory / "summary.json"
        if path.exists():
            s = read(path)
            light.append(dict(label=directory.name, directory=str(directory),
                              supervised_seconds=s["elapsed_seconds"],
                              peak_tree_RSS_bytes=s["sampled_process_tree_rss_peak_bytes"],
                              own_swap_peak_bytes=s["sampled_process_tree_swap_peak_bytes"],
                              classification=s["classification"], leader_exit_code=s["leader_exit_code"],
                              summary_sha256=sha(path)))
    formal_seconds = sum(x["supervised_seconds"] for x in run.values()) + sum(x["supervised_seconds"] for x in failures)
    light_seconds = sum(x["supervised_seconds"] for x in light)
    V2 = formal_seconds + light_seconds
    max_peak = max([x["peak_simultaneous_tree_RSS_bytes"] for x in run.values()] +
                   [x["peak_simultaneous_tree_RSS_bytes"] for x in failures] +
                   [x["peak_tree_RSS_bytes"] for x in light])
    if V2 > 14400 or V1_BASE_SECONDS + V2 > 57600:
        raise ValueError("V2 supervised budget exceeded")
    write("resource_costs_v2.json", dict(
        schema="task42extra.resource-costs.v2", formal_stages=run,
        failed_compare_only_attempts=failures, light_checks=light,
        V2_formal_supervised_seconds=formal_seconds, V2_light_supervised_seconds=light_seconds,
        V2_total_supervised_seconds=V2, V2_cap_seconds=14400,
        conservative_V1_derived_base_seconds=V1_BASE_SECONDS,
        conservative_V1_plus_V2_seconds=V1_BASE_SECONDS + V2,
        original_16h_cap_seconds=57600,
        entire_V2_session_sampled_tree_RSS_peak_bytes=max_peak,
        own_swap_peak_bytes=max([x["own_tree_swap_peak_bytes"] for x in run.values()] +
                                [x["own_tree_swap_peak_bytes"] for x in failures] +
                                [x["own_swap_peak_bytes"] for x in light]),
        candidate_exclusive_costs_seconds=trial["costs_exclusive_seconds"],
        candidate_action_counts=trial["action_counts"],
        Gram_setup_each_process_seconds={name: i[name]["result"]["gram_factor" if name == "v2_state_diagnostic" else "Gram_factor"]["setup_seconds"] for name in ("v2_state_diagnostic", "v2_scaling_checks", NEW)},
        Gram_solve_each_process_seconds={name: i[name]["result"]["gram_factor" if name == "v2_state_diagnostic" else "Gram_factor"]["solve_seconds"] for name in ("v2_state_diagnostic", "v2_scaling_checks", NEW)},
        reused_original_G_assembly_new_seconds=0,
        V1_G_assembly_for_cold_start_attribution_seconds=core["result"]["gram"]["assembly_seconds"],
        scaled_candidate_from_zero_attributed_seconds=run[NEW]["supervised_seconds"] + core["result"]["gram"]["assembly_seconds"],
        attribution_is_not_added_to_actual_research_wall=True,
        global_swap_candidate_observation="25 host pswpin pages; unresolved attribution; own sampled VmSwap zero",
        memory_scope="simultaneous supervised process tree sampled at approximately 0.5 s; no cgroup continuous claim",
        host_kind="native Linux; historical WSL-global label is inherited only",
        evidence_snapshot_excludes_current_checker_supervision=True,
    ))
    print(json.dumps(dict(status=status, strict=strict, positive=positive,
                          V2_supervised_seconds=V2, candidate_native=audit["native_relative"],
                          scattered_E=error_map["scattered_L2"]["relative"],
                          failures=len(failures)), sort_keys=True))


if __name__ == "__main__":
    main()
