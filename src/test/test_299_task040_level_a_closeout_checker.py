import hashlib
import json

import numpy as np
import pytest

from benchmarks.check_task040_level_a import (
    V1_1_LABELS,
    recompute_level_a_gate,
    recompute_scalar_krylov_gate,
)


def _write_tiny_raw(root):
    worker = root / "worker"
    worker.mkdir(parents=True)
    labels = [
        "physical_side_rhs",
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    ]
    reports = [
        {
            "label": label,
            "finite": True,
            "source_norm": 0.0 if label == "physical_side_rhs" else 1.0,
            "output_norm": 0.0 if label == "physical_side_rhs" else 1.0,
            "true_residual_norm": 0.0 if label == "physical_side_rhs" else 0.5,
            "true_residual_relative": None if label == "physical_side_rhs" else 0.5,
            "repeat_error": 0.0,
        }
        for label in labels
    ]
    summary = {
        "source_sha": "a" * 40,
        "action": {
            "reports": reports,
            "action_identity": {
                "restriction_prolongation_pass": True,
                "global_numpy_copy": False,
                "subdomain_vectors_global_numpy_copy": False,
                "bare_operator_unchanged": True,
            },
            "factor_inventory": {
                "cross_section_factor_count_ready": 3,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
                "system_direct_factor_count_observed": 0,
                "system_global_A_materialized_observed": False,
                "oracle_only": True,
                "scalable_candidate": False,
            },
            "gate": {"linearity_relative_error": 0.0, "pass": False},
        },
        "interface_masses": [
            {
                "finite": True,
                "support_sets_exact_match": True,
                "bare_operator_unchanged": True,
            },
            {
                "finite": True,
                "support_sets_exact_match": True,
                "bare_operator_unchanged": True,
            },
        ],
        "cleanup": {"factor_owner": {"after": {"factor_count_after_cleanup": 0}}},
    }
    watchdog = {
        "return_code": 0,
        "termination_reason": "natural_exit",
        "run_summary_present": True,
        "all_status_readable": True,
        "peak_swap_bytes": 0,
        "peak_dedicated_cgroup_swap_bytes": 0,
    }
    worker_path = worker / "run_summary.json"
    worker_path.write_text(json.dumps(summary))
    watchdog["source_sha"] = summary["source_sha"]
    watchdog["run_summary_sha256"] = hashlib.sha256(
        worker_path.read_bytes()
    ).hexdigest()
    (root / "watchdog_summary.json").write_text(json.dumps(watchdog))
    (root / "process_tree_samples.jsonl").write_text(
        json.dumps(
            {
                "elapsed_seconds": 2.0,
                "resource_authority": {
                    "memory_authority_bytes": 2**30,
                    "process_tree": {"swap_bytes": 0},
                },
            }
        )
        + "\n"
    )
    for name in ("memory_stage_markers.raw.jsonl", "memory_stages.jsonl"):
        (root / name).write_text("{}\n")


def test_closeout_checker_recomputes_gate_after_worker_gate_tamper(tmp_path):
    _write_tiny_raw(tmp_path)
    first = recompute_level_a_gate(tmp_path)
    summary_path = tmp_path / "worker" / "run_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["status"] = "fake_failed_status"
    summary["action"]["gate"]["pass"] = True
    summary["action"]["gate"]["mandatory_rho_pass"] = False
    summary["action"]["gate"]["preferred_rho_pass"] = True
    summary["action"]["gate"]["worst_mandatory_rho"] = 0.0
    summary_path.write_text(json.dumps(summary))
    invalid_hash = recompute_level_a_gate(tmp_path)
    assert invalid_hash["checks"]["watchdog"] is False
    watchdog_path = tmp_path / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text())
    watchdog["run_summary_sha256"] = hashlib.sha256(
        summary_path.read_bytes()
    ).hexdigest()
    watchdog_path.write_text(json.dumps(watchdog))
    second = recompute_level_a_gate(tmp_path)
    assert first["gate_pass"] is True
    assert second["gate_pass"] is True
    assert second["rho_by_label"]["fixed_random_repeat_0"] == 0.5
    assert second["peak_rss_bytes"] == 2**30
    assert second["peak_rss_gib"] == 1.0
    assert second["factor_inventory"] == {
        "cross_section_ready": 3,
        "full_side": 0,
        "global_direct": 0,
        "nested_ksp": 0,
        "cleanup_after": 0,
    }


def _sync_watchdog_hash(root):
    worker_path = root / "worker" / "run_summary.json"
    watchdog_path = root / "watchdog_summary.json"
    watchdog = json.loads(watchdog_path.read_text())
    watchdog["run_summary_sha256"] = hashlib.sha256(
        worker_path.read_bytes()
    ).hexdigest()
    watchdog_path.write_text(json.dumps(watchdog))


def _phase_records(values, *, max_it, include_32):
    iterations = ("0", "4", "8", "16") + (("32",) if include_32 else ())
    records = {}
    for label in V1_1_LABELS:
        checkpoints = {
            iteration: {
                "finite": True,
                "true_residual_relative": 1.0
                if iteration == "0"
                else float(values[iteration]),
                "reported_relative_residual": 1.0
                if iteration == "0"
                else float(values[iteration]),
            }
            for iteration in iterations
        }
        records[label] = {
            "label": label,
            "pc_side": "right",
            "restart": 32,
            "max_it": max_it,
            "zero_initial_guess": True,
            "zero_initial_guess_count": 1,
            "ksp_breakdown": False,
            "shared_ksp": True,
            "checkpoints": checkpoints,
            "true_residual_matvec_count": len(iterations) - 1,
            "right_pc_apply_count": len(iterations) - 1,
        }
    return records


def _write_tiny_scalar_raw(
    root,
    *,
    phase1_values=None,
    phase2_values=None,
    resource_ok=True,
    complex_bhy=False,
):
    _write_tiny_raw(root)
    summary_path = root / "worker" / "run_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["schema"] = "task040.v1_1.scalar_krylov.v1"
    bhy_pair = [0.0, 0.5] if complex_bhy else [0.5, 0.0]
    true_residual_norm = 1.25**0.5 if complex_bhy else 0.5
    matrices = {
        "BHB": [[[1.0, 0.0] for _ in range(5)] for _ in range(5)],
        "BHY": [[list(bhy_pair) for _ in range(5)] for _ in range(5)],
        "YHY": [[[0.25, 0.0] for _ in range(5)] for _ in range(5)],
    }
    summary["action"]["scalar_contractions"] = {
        "labels": list(V1_1_LABELS),
        **matrices,
        "per_source": {
            label: {
                "source_norm": 1.0,
                "source_norm_squared": 1.0,
                "x_norm_squared": 0.25,
                "y_norm": 0.5,
                "y_norm_squared": 0.25,
                "true_residual_norm": true_residual_norm,
                "finite": True,
            }
            for label in V1_1_LABELS
        },
    }
    phase1_values = phase1_values or {"4": 0.02, "8": 0.01, "16": 0.0005}
    screen = {
        "schema": "task040.v1_1.right_fgmres_batch.v1",
        "labels": list(V1_1_LABELS),
        "phase1": _phase_records(phase1_values, max_it=16, include_32=False),
        "phase2": (
            _phase_records(phase2_values, max_it=32, include_32=True)
            if phase2_values is not None
            else {}
        ),
        "resource_at_phase_boundary": {
            "all_status_readable": True,
            "rss_bytes": 2**30 if resource_ok else 45 * 2**30,
            "swap_bytes": 0,
        },
        "ksp_setup_count": 1,
        "ksp_destroy_count": 1,
        "ksp_destroyed": True,
        "right_pc_apply_count": 35 if phase2_values is not None else 15,
        "single_right_pc_setup": True,
        "zero_initial_guess_all_rhs": True,
        "conditional_32_authorized": False,
        "status": "worker-derived-status-is-ignored",
    }
    summary["scalar_screen"] = screen
    summary_path.write_text(json.dumps(summary))
    _sync_watchdog_hash(root)


def test_scalar_checker_recomputes_complex_contractions_and_earliest_checkpoint(
    tmp_path,
):
    _write_tiny_scalar_raw(
        tmp_path,
        phase1_values={"4": 0.02, "8": 0.01, "16": 0.0005},
        phase2_values={"0": 1.0, "4": 0.002, "8": 0.001, "16": 0.0006, "32": 0.0004},
    )
    result = recompute_scalar_krylov_gate(tmp_path)
    assert result["classification"] == "SCALAR_TRANSMISSION_KRYLOV_PASS"
    assert result["gate_pass"] is True
    assert result["derived"]["early_passing_checkpoint"] == "phase1:16"
    derived = result["derived"]["by_label"][V1_1_LABELS[0]]
    assert derived["alpha_star"] == [2.0, 0.0]
    assert derived["alpha_magnitude"] == 2.0
    assert derived["alpha_phase_radians"] == 0.0
    assert derived["original_rho"] == 0.5
    assert result["derived"]["B_vs_Y_normalized_cross_correlation"][0][0] == [
        1.0,
        0.0,
    ]
    assert result["derived"]["B_vs_Y_normalized_cross_correlation_abs"][0][0] == 1.0

    summary_path = tmp_path / "worker" / "run_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["status"] = "tampered-status"
    summary["action"]["gate"]["pass"] = False
    summary["action"]["gate"]["mandatory_rho_pass"] = False
    summary["scalar_screen"]["conditional_32_authorized"] = False
    summary["scalar_screen"]["status"] = "tampered-derived-status"
    for record in summary["scalar_screen"]["phase1"].values():
        record["pass"] = False
    summary_path.write_text(json.dumps(summary))
    _sync_watchdog_hash(tmp_path)
    tampered = recompute_scalar_krylov_gate(tmp_path)
    assert tampered["classification"] == "SCALAR_TRANSMISSION_KRYLOV_PASS"
    assert tampered["gate_pass"] is True

    _write_tiny_scalar_raw(
        tmp_path / "complex",
        phase1_values={"4": 0.0005, "8": 0.0005, "16": 0.0005},
        complex_bhy=True,
    )
    complex_result = recompute_scalar_krylov_gate(tmp_path / "complex")
    complex_derived = complex_result["derived"]["by_label"][V1_1_LABELS[0]]
    assert complex_result["classification"] == "SCALAR_TRANSMISSION_KRYLOV_PASS"
    assert complex_result["derived"]["early_passing_checkpoint"] == "phase1:4"
    assert complex_result["derived"]["conditional_32_authorized"] is False
    assert complex_derived["alpha_star"] == [0.0, -2.0]
    assert complex_derived["alpha_phase_radians"] == pytest.approx(-np.pi / 2)
    assert complex_derived["original_rho"] == pytest.approx(1.25**0.5)
    assert complex_result["derived"]["B_vs_Y_normalized_cross_correlation"][0][0] == [
        0.0,
        1.0,
    ]


def test_scalar_checker_classifies_directional_and_capacity_cases(tmp_path):
    _write_tiny_scalar_raw(
        tmp_path / "directional",
        phase1_values={"4": 0.02, "8": 0.02, "16": 0.02},
    )
    directional = recompute_scalar_krylov_gate(tmp_path / "directional")
    assert directional["classification"] == "SCALAR_TRANSMISSION_DIRECTIONAL_FAIL"
    assert directional["gate_pass"] is False

    high_residual = tmp_path / "high_residual"
    _write_tiny_scalar_raw(
        high_residual,
        phase1_values={"4": 2.0, "8": 1.8, "16": 1.0},
    )
    high_residual_result = recompute_scalar_krylov_gate(high_residual)
    assert high_residual_result["derived"]["all_five_r16_ge_0p9"] is True
    assert high_residual_result["derived"]["conditional_32_authorized"] is False
    assert high_residual_result["checks"]["conditional_32_contract"] is True
    assert (
        high_residual_result["classification"] == "SCALAR_TRANSMISSION_DIRECTIONAL_FAIL"
    )

    _write_tiny_scalar_raw(
        tmp_path / "capacity",
        phase1_values={"4": 0.02, "8": 0.02, "16": 0.01},
        phase2_values={"0": 1.0, "4": 0.02, "8": 0.02, "16": 0.01, "32": 0.02},
    )
    capacity = recompute_scalar_krylov_gate(tmp_path / "capacity")
    assert capacity["classification"] == "SCALAR_TRANSMISSION_KRYLOV_CAPACITY_FAIL"
    assert capacity["gate_pass"] is False


def test_scalar_checker_rejects_nonfinite_and_inconsistent_raw_contractions(tmp_path):
    _write_tiny_scalar_raw(
        tmp_path,
        phase1_values={"4": 0.02, "8": 0.01, "16": 0.0005},
    )
    summary_path = tmp_path / "worker" / "run_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["action"]["scalar_contractions"]["BHB"][0][0] = [float("nan"), 0.0]
    summary_path.write_text(json.dumps(summary))
    _sync_watchdog_hash(tmp_path)
    invalid = recompute_scalar_krylov_gate(tmp_path)
    assert invalid["checks"]["contraction_finite"] is False
    assert invalid["classification"] == "IMPLEMENTATION_OR_RESOURCE_FAILURE"

    _write_tiny_scalar_raw(
        tmp_path / "negative",
        phase1_values={"4": 0.02, "8": 0.01, "16": 0.0005},
    )
    negative_summary_path = tmp_path / "negative" / "worker" / "run_summary.json"
    negative = json.loads(negative_summary_path.read_text())
    negative["action"]["scalar_contractions"]["per_source"][V1_1_LABELS[0]][
        "x_norm_squared"
    ] = -1.0
    negative_summary_path.write_text(json.dumps(negative))
    _sync_watchdog_hash(tmp_path / "negative")
    negative_result = recompute_scalar_krylov_gate(tmp_path / "negative")
    assert negative_result["checks"]["norm_storage_consistency"] is False
