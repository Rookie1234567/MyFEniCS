import hashlib
import json

from benchmarks.check_task040_level_a import recompute_level_a_gate


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
