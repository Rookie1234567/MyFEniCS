from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUMMARY = (
    ROOT
    / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
    "p4_h5_workstation_summary.json"
)


def test_tracked_phase_e_summary_is_hash_bound_and_preserves_boundaries() -> None:
    record = json.loads(SUMMARY.read_text(encoding="utf-8"))
    payload_sha256 = record.pop("payload_sha256")
    canonical = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == payload_sha256
    assert record["status"] == "p4_same_degree_closure_pass"
    assert record["aggregation_source"][
        "worktree_clean_including_nonignored_untracked"
    ]
    assert record["source_compatibility"]["multi_source_evidence"]
    assert all(record["source_compatibility"]["checks"].values())
    identity = record["identity"]
    assert not identity["thresholds_relaxed"]
    assert not identity["grid_convergence_proven"]
    assert not identity["continuum_reference"]
    assert not identity["heavy_artifacts_tracked"]


def test_phase_e_staged_gates_and_direct_solver_semantics_are_frozen() -> None:
    record = json.loads(SUMMARY.read_text(encoding="utf-8"))
    staged = record["staged_full3d"]
    assert staged["assembly_only"]["status"] == "assembly_calibration_pass"
    assert not staged["assembly_only"]["factorization_or_solve_seen"]
    assert (
        staged["factorization_only"]["status"]
        == "factorization_calibration_pass"
    )
    assert not staged["factorization_only"]["solve_executed"]
    full = staged["full_solve"]
    assert full["status"] == "full3d_reference_pass"
    assert full["true_relative_residual"] <= 1.0e-9
    assert full["no_swap"]
    assert full["ksp_setup_seconds"] > 100.0 * full["ksp_solve_seconds"]
    diagnosis = staged["setup_diagnosis"]
    assert diagnosis["ordinary_setup_classification"] == "normal"
    assert diagnosis["mesh_build_seconds"] < 2.0
    assert diagnosis["function_space_setup_seconds"] < 1.0
    assert diagnosis["floquet_total_seconds"] < 2.0
    assert diagnosis["variational_form_setup_seconds"] < 1.0
    assert diagnosis["augmented_copy_insert_finalize_seconds"] < 30.0


def test_phase_e_hybrid_closure_and_accuracy_gain_are_not_overclaimed() -> None:
    record = json.loads(SUMMARY.read_text(encoding="utf-8"))
    funnel = record["hybrid_funnel"]
    assert funnel["status"] == "qualified"
    assert funnel["selected_mode_count_per_direction"] == 160
    assert not funnel["M240_required"]
    assert all(row["no_swap"] for row in funnel["runs"])
    assert all(row["all_reported_gates_pass"] for row in funnel["runs"])
    closure = record["same_degree_closure"]
    assert closure["all_sixteen_measurement_gates_pass"]
    assert closure["reference_binding_verified"]
    assert closure["official_hybrid_values"]["true_relative_residual"] <= 1.0e-9
    accuracy = record[
        "accuracy_benefit_against_p3_h3_finer_discrete_reference"
    ]
    p4 = accuracy["p4_h5_metric_vector"]
    p3 = accuracy["p3_h5_metric_vector"]
    assert p4.keys() == p3.keys()
    assert all(p4[name] < p3[name] for name in p4)
    assert accuracy["p4_h5_better_than_p3_h5_on_all_twelve_components"]
    assert not accuracy["grid_convergence_proven"]
    assert not accuracy["continuum_reference"]
