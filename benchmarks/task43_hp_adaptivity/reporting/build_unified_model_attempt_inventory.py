import hashlib
import json
from pathlib import Path

from benchmarks.task43_hp_adaptivity.reporting.watchdog_scope import (
    watchdog_resource_qualification,
)

r = Path(__file__).resolve().parents[3]
records = r / "docs/task43_hp_adaptivity/outcomes/records"
o = r / "docs/task43_hp_adaptivity/outcomes/records"
inputs = {}
scope_helper_path = Path(__file__).with_name("watchdog_scope.py")
inputs[str(scope_helper_path)] = hashlib.sha256(
    scope_helper_path.read_bytes()
).hexdigest()


def load(p):
    p = Path(p)
    p = p if p.is_absolute() else r / p
    inputs[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text())


def ref(p):
    return {
        "path": str(p.relative_to(r)) if p.is_relative_to(r) else str(p),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "bytes": p.stat().st_size,
    }


models = []
entries = [
    (
        "initial_current",
        r / "benchmarks/artifacts/task43/current_180/attempt1/run",
        "official_initial",
    ),
    (
        "initial_tightening",
        r / "benchmarks/artifacts/task43/current_180/tightening_attempt2/run",
        "same_initial_lineage_tightening_calibration",
    ),
]
for i in range(1, 10):
    s = load(records / f"round{i}_selection_transition{i}_v1.json")
    path = Path(s["selected_candidate"]["run_root"])
    path = path if path.is_absolute() else r / path
    entries.append((f"round{i}_p", path, "accepted_update"))
entries.append(
    (
        "round10_p",
        r / "benchmarks/artifacts/task43/round10_p_up_attempt1/run",
        "solver_qualified_but_rejected_G_noise",
    )
)
h = load(records / "h1_real_action_qualification_v1.json")
p = Path(h["evidence"]["PDE_record"]["path"])
p = p if p.is_absolute() else r / p
entries.append(
    (
        "h1_qualification_retry",
        p.parent,
        "same_h1_lineage_real_h_qualified_not_spatial_accuracy",
    )
)
s = load(records / "round1_selection_transition1_v1.json")
p = Path(s["h_candidate"]["plan"]["path"])
p = p if p.is_absolute() else r / p
entries.append(
    (
        "h1_original_interrupted",
        p.parent,
        "interrupted_unknown_sender_no_Task43_official_field",
    )
)
entries.append(
    (
        "round2_p_preflight_failed",
        r / "benchmarks/artifacts/task43/round2_p_up_attempt1/run",
        "full_active_preflight_failed_before_checkpoint_A6",
    )
)
entries.append(
    (
        "round5_p_performance_stop",
        r / "benchmarks/artifacts/task43/round5_p_up_attempt1/run",
        "root_performance_stop_no_numerical_or_resource_failure",
    )
)
assert len(entries) == 16
stages = [
    "stage4_dtn_base_matrix_assembly_seconds",
    "stage4_dtn_modal_vector_assembly_seconds",
    "stage4_dtn_modal_loop_seconds",
    "stage4_dtn_ksp_setup_seconds",
    "stage4_dtn_ksp_solve_seconds",
    "stage4_dtn_cell_static_condensation_recovery_seconds",
    "stage4_dtn_assembly_time_total_build_seconds",
    "stage4_dtn_assembly_time_preallocation_seconds",
    "stage4_variable_p_same_lu_residual_correction_seconds",
]


def compact_controls(record):
    controls = record.get("numerical_controls") or {}
    mesh = controls.get("mesh") or {}
    profile = controls.get("resolved_task43_profile_identity") or {}
    return {
        "geometry_profile": mesh.get("geometry_profile"),
        "axis_cell_counts_xyz": mesh.get("axis_cell_counts_xyz"),
        "global_cells": mesh.get("global_cells"),
        "nedelec_degree": controls.get("nedelec_degree"),
        "ordered_mode_count": controls.get("ordered_mode_count"),
        "ordered_mode_keys_sha256": controls.get("ordered_mode_keys_sha256"),
        "volume_quadrature_degree": controls.get("volume_quadrature_degree"),
        "volume_quadrature_rule": controls.get("volume_quadrature_rule"),
        "incident_and_port_quadrature_degree": controls.get(
            "incident_and_port_quadrature_degree"
        ),
        "sparse_cutoff_policy": controls.get("sparse_cutoff_policy"),
        "sparse_cutoff_relative_tolerance": controls.get(
            "sparse_cutoff_relative_tolerance"
        ),
        "port_amplitude_scale_policy": controls.get("port_amplitude_scale_policy"),
        "task43_profile_id": profile.get("profile_id"),
    }


def compact_solver_gates(record):
    solver = record.get("solver") or {}
    action = solver.get("independent_active_action") or {}
    gauge = action.get("full_solver_gauge_residual") or {}
    condensed = solver.get("condensed_residual") or {}
    return {
        "independent_A6": {
            k: gauge.get(k)
            for k in (
                "finite",
                "raw_l2_norm",
                "relative_to_independent_rhs",
                "task_gate_limit",
                "task_gate_pass",
                "small_direct_target_limit",
                "small_direct_target_pass",
            )
        },
        "condensed_relative_residual": condensed.get("linear_system_relative_residual"),
        "requested_direct_factor_backend": solver.get(
            "requested_direct_factor_backend"
        ),
        "actual_direct_factor_backend": solver.get("actual_direct_factor_backend"),
        "actual_live_direct_factor_backend": solver.get(
            "actual_live_direct_factor_backend"
        ),
    }


def compact_matrix(summary):
    augmented = summary.get("stage4_dtn_augmented_matrix_stats_after_finalize") or {}
    factor = summary.get("stage4_dtn_factor_inventory") or {}
    factor_stats = factor.get("matrix_stats") or {}
    corrected_factor_nnz = factor.get("factor_nnz_corrected")
    return {
        "augmented_rows": summary.get(
            "num_augmented_rows",
            summary.get("matrix_size", augmented.get("matrix_rows")),
        ),
        "operator_nnz_used": augmented.get("matrix_nnz_used"),
        "operator_nnz_allocated": augmented.get("matrix_nnz_allocated"),
        "factor_nnz": (
            corrected_factor_nnz
            if corrected_factor_nnz is not None
            else factor_stats.get("matrix_nnz_used")
        ),
        "factor_nnz_source": "factor matrix_stats.matrix_nnz_used; corrected value only if explicitly present",
        "factor_object_estimate_bytes": factor.get(
            "factor_memory_bytes", factor.get("factor_object_estimate_bytes")
        ),
    }


for name, run, classification in entries:
    paths = [
        run / "task43_round1_candidate_record.json",
        run / "task43_initial180_current_record.json",
    ]
    record_path = next((p for p in paths if p.exists()), None)
    record = load(record_path) if record_path else None
    summary_path = run / "solve/run_summary.json"
    summary = load(summary_path) if summary_path.exists() else {}
    wdpaths = list(run.parent.glob("watchdog*/summary.json"))
    assert len(wdpaths) <= 1, (name, wdpaths)
    wd = load(wdpaths[0]) if wdpaths else None
    resource_qualification = watchdog_resource_qualification(
        name, wd is not None, run, r
    )
    partial_resource_observation = None
    if wd is None:
        r8_audit_path = records / "round8_independent_audit_v1.json"
        r8_audit = load(r8_audit_path)
        r8_pde_resources = r8_audit["resources"]["PDE"]
        partial_identity = r8_pde_resources["partial_audit"]
        partial_path = r / partial_identity["path"]
        assert (
            hashlib.sha256(partial_path.read_bytes()).hexdigest()
            == partial_identity["sha256"]
        )
        assert name == "round8_p"
        assert (
            r8_audit["source_identity"]["HEAD_at_solve_and_comparison"]
            == (record["source_identity"]["git_head"])
        )
        assert r8_audit["source_identity"]["clean_source_bytes_equal_git_HEAD"]
        assert r8_pde_resources["original_summary_json_present"] is False
        assert r8_pde_resources["observed_elapsed_lower_bound_seconds"] is not None
        assert (
            r8_pde_resources[
                "observed_sample_window_tree_RSS_peak_bytes_not_lifecycle_peak"
            ]
            is not None
        )
        assert partial_path.resolve().is_relative_to(
            (r / "benchmarks/artifacts/task43/round8_p_up_attempt1").resolve()
        )
        partial_resource_observation = {
            "audit_record": ref(r8_audit_path),
            "partial_terminal_executor_audit": ref(partial_path),
            "observed_elapsed_lower_bound_seconds": r8_pde_resources[
                "observed_elapsed_lower_bound_seconds"
            ],
            "observed_sample_count": r8_pde_resources["observed_sample_count"],
            "observed_window_tree_RSS_peak_bytes_not_lifecycle_peak": r8_pde_resources[
                "observed_sample_window_tree_RSS_peak_bytes_not_lifecycle_peak"
            ],
            "sample_window_task_VmSwap_peak_bytes": r8_pde_resources[
                "sample_window_task_VmSwap_peak_bytes"
            ],
            "outer_tool_session_exit_code": r8_pde_resources[
                "outer_tool_session_exit_code"
            ],
            "signal_sender": r8_pde_resources["signal_sender"],
            "status": r8_pde_resources["status"],
            "scope": "partial window only; no complete whole wall, lifetime peak, original exit, or original watchdog cleanup claim",
        }
    row = {
        "model_attempt": name,
        "run_root": str(run.relative_to(r)),
        "classification": classification,
        "record": ref(record_path) if record_path else None,
        "official_result": record.get("solver", {}).get("official_result")
        if record
        else False,
        "independent_FE_identity": record.get("recovered_solution_storage")
        if record
        else None,
        "model_identity_summary": compact_controls(record) if record else None,
        "solver_numeric_gates": compact_solver_gates(record) if record else None,
        "source_identity": record.get("source_identity") if record else None,
        "environment_ABI": record.get("environment") if record else None,
        "solver_summary": ref(summary_path) if summary_path.exists() else None,
        "matrix_statistics": compact_matrix(summary),
        "stage_seconds": {k: summary.get(k) for k in stages},
        "watchdog": {
            "identity": ref(wdpaths[0]),
            "classification": wd["classification"],
            "wall_seconds": wd["elapsed_seconds"],
            "simultaneous_tree_RSS_peak_bytes": wd.get(
                "sampled_process_tree_rss_peak_bytes",
                wd.get("process_tree_rss_peak_bytes"),
            ),
            "leader_exit_code": wd.get("leader_exit_code"),
            "descendants_cleared": wd.get("descendants_cleared"),
        }
        if wd
        else None,
        "resource_qualification": resource_qualification,
        "partial_resource_observation": partial_resource_observation,
        "timing_scope": "Base includes new-process space; modal loop contains vector assembly; build/preallocation nested. Per-record wall ends before JSON/exit. Whole wall only watchdog. Missing values=null/not measured, never zero.",
    }
    if record:
        agg = record["power"]["aggregate"]
        row["scalar_power_vector"] = {
            k: agg.get(k) for k in ["R_total", "T_total", "R00_s", "R00_p", "R00_total"]
        }
        row["scalar_power_vector"]["A_volume"] = record["power"]["A_volume_total"]
        storage = record["recovered_solution_storage"]
        row["independent_FE"] = storage.get("independent_active_fe_dofs")
        if row["independent_FE"] is None:
            trace_rows = storage.get("active_trace_rows")
            interior_rows = storage.get("active_cell_interior_rows")
            if trace_rows is not None and interior_rows is not None:
                row["independent_FE"] = trace_rows + interior_rows
        row["source_record_is_not_claim_of_clean_HEAD_only"] = (
            "Exact source file map and snapshot evidence retained; early dirty source map and omitted-list supplement boundaries remain in original records."
        )
    events_path = run.parent / "watchdog/worker.log"
    if events_path.exists():
        row["stage_log_identity"] = ref(events_path)
    if wd is None:
        row["scope"] = (
            "R8 only sampled window; no whole-run peak/swap/exit/cleanup or full cost claim."
        )
    if not record:
        progress = run / "solve/progress_3d.jsonl"
        row["official_power_unavailable"] = True
        row["progress_diagnostic_identity"] = (
            ref(progress) if progress.exists() else None
        )
        row["failed_or_stopped_reason_scope"] = classification
    models.append(row)
# Imported references/controls are historical fields, not additional new fullsolver attempts.
external = []
inv = load(records / "existing_validation_fields_v1.json")
for label in ["Y6_1", "Y6_2", "Y5_1", "Y3", "Y3_2"]:
    entry = next(x for x in inv["cases"] if x["label"] == label)
    root = (
        r / "benchmarks/artifacts/task43/reference_imports/attempt2"
        if label.startswith("Y6")
        else r
        / "benchmarks/artifacts/task43/post_selection_restore_attempt1/restores/attempt1"
    ) / label
    rest = load(root / "restore_identity_record.json")
    cfg = rest["resolved_identity"]
    shape = cfg["storage_shape"][0]
    fe = shape - cfg["floquet_slave_count"]
    orders = load(root / "numerical_output/dtn_port_diffraction_orders_3d.json")
    power = entry["power"].copy()
    for pol in ["s", "p"]:
        power["R00_" + pol] = sum(
            float(row["R"])
            for row in orders["orders"]
            if row["side"] == "top"
            and row["m"] == row["n"] == 0
            and row["polarization"] == pol
        )
    power["R00_total"] = power["R00_s"] + power["R00_p"]
    summary = root / "p6_condensed_direct_summary.json"
    old = load(summary)
    external.append(
        {
            "label": label,
            "role": entry["role"],
            "historical_source_SHA": entry["source_sha"],
            "storage_rows": shape,
            "actual_restored_Floquet_slaves": cfg["floquet_slave_count"],
            "independent_FE_from_restoration": fe,
            "independent_FE_scope": "Previously/now restored native space minus actual slaves; same formula as actual Floquet identity, not new solve",
            "scalar_power_vector": power,
            "historical_solver_summary": ref(summary),
            "historical_recorded_matrix_and_timing": {
                k: v
                for k, v in old.items()
                if any(
                    word in k
                    for word in [
                        "nnz",
                        "rows",
                        "dof",
                        "time",
                        "seconds",
                        "memory",
                        "matrix_stats",
                    ]
                )
            },
            "restore_record": ref(root / "restore_identity_record.json"),
            "restore_wall_seconds": rest["timing_seconds"],
            "fresh_Task43_PDE_wall_and_peak": None,
            "scope": "Imported historical source/runtime only, no cold/source-matched cost comparison, reference own q/R/continuum qualification missing",
        }
    )
data = {
    "schema": "task43.unified-model-attempt-inventory.v2",
    "status": "V2_REBUILT_WITH_EXACT_R8_RESOURCE_EXCEPTION",
    "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "new_fullsolver_attempt_count": 16,
    "scientific_lineages": 12,
    "accepted_updates": 9,
    "new_fullsolver_attempts": models,
    "imported_fields_not_new_solver_attempts": external,
    "input_sha256": inputs,
    "scope": "All16 formal fullsolver attempts including failed/stopped/retry; existing small numerical-sanity fixtures separately indexed in g1/h100/direct-backend component records. Absent fields null, not inferred PASS. Raw summary identities bind rows/NNZ/timings/source/ABI.",
    "incomplete_resource_historical_R8_explicit": True,
}
(o / "unified_model_attempt_inventory_v2.json").write_text(
    json.dumps(data, indent=2, allow_nan=False) + "\n"
)
print(
    "models",
    len(models),
    "imported",
    len(external),
    "bytes",
    (o / "unified_model_attempt_inventory_v2.json").stat().st_size,
)
