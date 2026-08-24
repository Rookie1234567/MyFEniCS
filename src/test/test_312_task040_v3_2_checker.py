"""Synthetic raw-contract tests for the V3-2 independent checker."""

from __future__ import annotations

import json

import pytest

from benchmarks import check_task040_v3_full_span as checker
from benchmarks.task040_level_a import (
    TASK040_LEVEL_A_SOURCE_LABELS,
    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
    TASK040_V1_2_INPUT_SHA256,
    TASK040_V1_2_PHYSICAL_MODEL_SHA256,
    TASK040_V1_2_SELECTED_MANIFEST_SHA256,
    TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
    TASK040_V3_2_COUPLED_INTERFACE_FLAG,
    TASK040_V3_2_COUPLED_INTERFACE_METHOD,
    TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID,
    TASK040_V3_2_PRODUCER_SOURCE_SHA,
    TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
)

SOURCE_SHA = "c" * 40
RUN_SUMMARY_SHA = "r" * 64
TIMELINE_SHA = "t" * 64
PACKET_ROOT = "/home/Projects/MyFEniCS/results/task040_v3_1_augmented_packet"
LOWER_MODE_KEYS = "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
UPPER_MODE_KEYS = "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
UPPER_BETA = "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
LOWER_BETA = "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
NONZERO = tuple(TASK040_LEVEL_A_SOURCE_LABELS[1:])
STRICT = NONZERO[:3]


def _packet_audit() -> dict[str, object]:
    blocks = {
        "LL": {
            "shape": [296, 296],
            "dtype": "complex128",
            "rank": 296,
            "frobenius_norm": 1052857.3530587784,
            "sha256": "4be30638ca6ca7e6d6980ef45fa53250755d76961b336b60360f4b06a187dbe0",
        },
        "LU": {
            "shape": [296, 480],
            "dtype": "complex128",
            "rank": 296,
            "frobenius_norm": 36531.317719106126,
            "sha256": "1033fcc0d2d5ff2b0a3a018870f839b6e131d39a01de4d205fd3d496fc97db9e",
        },
        "UL": {
            "shape": [480, 296],
            "dtype": "complex128",
            "rank": 296,
            "frobenius_norm": 9728.7850526928,
            "sha256": "969e15b2d61f185bb276bab40904235343f118ef0a4d1aef2a6b05c61c048972",
        },
        "UU": {
            "shape": [480, 480],
            "dtype": "complex128",
            "rank": 480,
            "frobenius_norm": 6371.749206867203,
            "sha256": "3935fc7fbd064d333dfdc53fb738076a0273b9c2529274d648e11777369c6d09",
        },
    }
    return {
        "manifest_sha256": TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        "producer_source_sha": TASK040_V3_2_PRODUCER_SOURCE_SHA,
        "group_order": ["group0", "group1", "group2"],
        "span_sizes": [296, 776, 480],
        "ordering_identity": {
            "producer_source_sha": TASK040_V3_2_PRODUCER_SOURCE_SHA,
            "lower_mode_count": 296,
            "lower_mode_key_sha256": LOWER_MODE_KEYS,
            "upper_mode_count": 480,
            "upper_mode_key_sha256": UPPER_MODE_KEYS,
            "upper_beta_sha256": UPPER_BETA,
            "upper_branch_authority": "positive/forward",
            "upper_qep_calls": 0,
            "group1_span_size": 776,
            "group1_planes": ["lower", "upper"],
            "contract": "build_group_basis_columns: lower then upper",
        },
        "joint_diagnostics": {
            "shape": [776, 776],
            "dtype": "complex128",
            "rank": 776,
            "condition": checker.EXPECTED_JOINT_CONDITION,
            "content_sha256": TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
        },
        "joint_exact_blocks": blocks,
        "additional_middle_metadata": {
            "schema": "task040.v3.middle_group_schur_projection.v1",
            "semantic": "Y1^H [oracle.apply_group(1)] Z1",
            "shape": [776, 776],
            "dtype": "complex128",
            "finite": True,
            "apply_count": 776,
            "rank": 776,
            "condition": checker.EXPECTED_JOINT_CONDITION,
        },
        "additional_middle_diagnostics": {
            "shape": [776, 776],
            "dtype": "complex128",
            "rank": 776,
            "finite": True,
            "sha256": "m" * 64,
            "condition": checker.EXPECTED_JOINT_CONDITION,
        },
        "group1_gram_content_sha256": "a" * 64,
        "failure_decomposition": {
            "physical": {"count": 15},
            "modal_combination": {"count": 4},
            "complement": {"count": 4},
            "middle_lower_to_upper": {"count": 4},
            "middle_upper_to_lower": {"count": 4},
        },
        "checks": {
            "manifest_hash": True,
            "producer_source": True,
            "packet_authority": True,
            "group_order": True,
            "span_sizes": True,
            "group_gram_diagnostics": True,
            "joint_scalar_diagnostics": True,
            "middle_matrix": True,
            "joint_exact": True,
            "joint_exact_blocks": True,
            "ordering_identity": True,
            "report_decomposition": True,
            "local_middle_schur_evidence": True,
            "watchdog_hash": False,
            "run_summary_hash": False,
        },
        # Deliberately false: the independent checker must derive the result.
        "packet_sufficient": False,
    }


def _phase_row(
    label: str, phase: str, values: dict[str, float], max_it: int
) -> dict[str, object]:
    checkpoints = {
        "0": {
            "label": label,
            "phase": phase,
            "iteration": 0,
            "true_residual_relative": 1.0,
            "finite": True,
        }
    }
    for iteration, value in values.items():
        checkpoints[iteration] = {
            "label": label,
            "phase": phase,
            "iteration": int(iteration),
            "true_residual_relative": value,
            "finite": True,
        }
    history = [
        {"iteration": iteration, "relative_residual": 1.0 - 0.001 * iteration}
        for iteration in range(1, max_it + 1)
    ]
    final_value = values.get(str(max_it), 0.5)
    return {
        "label": label,
        "phase": phase,
        "restart": 32,
        "max_it": max_it,
        "zero_initial_guess": True,
        "zero_initial_guess_count": 1,
        "shared_ksp": True,
        "ksp_breakdown": False,
        "true_residual_matvec_count": {16: 4, 32: 2, 64: 2}[max_it],
        "reported_residual_history": history,
        "checkpoints": checkpoints,
        "ksp_reason": -3,
        "iterations": max_it,
        "final_iteration": max_it,
        "final_reason": -3,
        "elapsed_seconds": 0.01,
        "postsolve_true_residual_norm": final_value,
        "postsolve_true_residual_relative": final_value,
        "postsolve_true_residual_finite": True,
        "happy_breakdown": False,
        "early_stop": False,
        "missing_checkpoints": [],
        "right_pc_apply_count_delta": 1,
        "right_pc_apply_count_total": 1,
    }


def _screen(mode: str) -> dict[str, object]:
    phase1: dict[str, dict[str, object]] = {}
    if mode == "early":
        phase1_values = {
            label: {"4": 5.0e-4 if label in STRICT else 5.0e-3, "8": 0.2, "16": 0.2}
            for label in NONZERO
        }
    elif mode == "negative":
        phase1_values = {label: {"4": 0.95, "8": 0.8, "16": 0.4} for label in NONZERO}
    else:
        phase1_values = {label: {"4": 0.95, "8": 0.8, "16": 0.4} for label in NONZERO}
    for label in NONZERO:
        phase1[label] = _phase_row(label, "phase1", phase1_values[label], 16)

    phase2: dict[str, dict[str, object]] = {}
    phase3: dict[str, dict[str, object]] = {}
    if mode in {"negative", "phase2_pass", "phase3_pass", "history_tamper"}:
        for label in NONZERO:
            value = 0.5 if mode == "negative" else 5.0e-4 if label in STRICT else 5.0e-3
            phase2[label] = _phase_row(label, "phase2", {"32": value}, 32)
    if mode in {"phase3_pass", "history_tamper"}:
        for label in NONZERO:
            value = 5.0e-4 if label in STRICT else 5.0e-3
            phase2[label] = _phase_row(label, "phase2", {"32": 0.05}, 32)
            phase2[label]["reported_residual_history"] = [
                {"iteration": i, "relative_residual": 1.0 - 0.01 * (i - 16)}
                for i in range(1, 33)
            ]
            phase3[label] = _phase_row(label, "phase3", {"64": value}, 64)
            phase3[label]["reported_residual_history"] = [
                {"iteration": i, "relative_residual": 1.0 - 0.005 * i}
                for i in range(1, 65)
            ]
    if mode == "history_tamper":
        phase2[NONZERO[0]]["reported_residual_history"][20]["relative_residual"] = (
            float("nan")
        )

    boundaries = [
        {
            "boundary": "after_phase1",
            "rss_bytes": 1000,
            "swap_bytes": 0,
            "all_status_readable": True,
        }
    ]
    if phase2:
        boundaries.append(
            {
                "boundary": "after_phase2",
                "rss_bytes": 1000,
                "swap_bytes": 0,
                "all_status_readable": True,
            }
        )
    if phase3:
        boundaries.append(
            {
                "boundary": "after_phase3",
                "rss_bytes": 1000,
                "swap_bytes": 0,
                "all_status_readable": True,
            }
        )
    first = {"early": 4, "phase2_pass": 32, "phase3_pass": 64}.get(mode)
    return {
        "schema": "task040.v3_2.full_span_right_fgmres.v1",
        "labels": list(NONZERO),
        "phase1": phase1,
        "phase2": phase2,
        "phase3": phase3,
        "conditional_32_authorized": bool(phase2),
        "conditional_64_authorized": bool(phase3),
        "first_preferred_checkpoint": first,
        "ksp_setup_count": 1,
        "ksp_destroy_count": 1,
        "ksp_destroyed": True,
        "single_right_pc_setup": True,
        "zero_initial_guess_all_rhs": True,
        "resource_boundaries": boundaries,
    }


def _one_apply() -> dict[str, object]:
    reports = [
        {
            "label": label,
            "source_norm": 1.0,
            "output_norm": 1.0,
            "true_residual_norm": 0.001,
            "true_residual_relative": 0.001,
            "repeat_relative": 0.0,
            "first_coarse_residual_relative": 0.2,
            "second_coarse_residual_relative": 0.2,
            "coarse_residual_repeat_relative": 0.0,
            "finite": True,
            "first_coarse_residual_finite": True,
            "second_coarse_residual_finite": True,
            "coarse_residual_finite": True,
        }
        for label in NONZERO
    ]
    return {
        "schema": "task040.v3_2.full_side_one_apply.v1",
        "labels": list(NONZERO),
        "reports": reports,
        "physical_zero_report": {
            "label": TASK040_LEVEL_A_SOURCE_LABELS[0],
            "source_norm": 0.0,
            "output_norm": 0.0,
            "physical_zero": True,
            "finite": True,
        },
        "zero_output_norm": 0.0,
        "zero_map_pass": True,
        "physical_zero_pass": True,
        "source_reports_finite": True,
        "repeat_pass": True,
        "linearity_pass": True,
        "factor_inventory_pass": True,
        "coarse_residual_finite": True,
        "action_identity_pass": True,
        "linearity_relative": 0.0,
        "action_apply_count": 15,
    }


def _fixture(
    mode: str = "early",
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    packet = _packet_audit()
    raw = {
        "packet_dependent": True,
        "packet_manifest_sha256": TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        "producer_source_sha": TASK040_V3_2_PRODUCER_SOURCE_SHA,
        "basis_global_replicated": False,
        "fe_numeric_allgather": False,
        "forbidden_routes": [
            "exact_interface_oracle",
            "exact_output_vector_load",
            "full_side_factor",
            "global_hybrid_outer_ksp",
            "qep",
            "pde_solve",
            "recovery",
            "top",
            "full_hybrid",
            "response_packet",
        ],
        "group1_remap": {
            "audit": {"max_relative_error": 0.0},
            "collective_max_relative_error": 0.0,
        },
        "z_reconstruction": {
            "qep_calls": 0,
            "lower_mode_key_sha256": LOWER_MODE_KEYS,
            "lower_beta_sha256": LOWER_BETA,
            "upper_mode_key_sha256": UPPER_MODE_KEYS,
            "upper_beta_sha256": UPPER_BETA,
            "gram_relative_error": 0.0,
            "gram_block_relative_errors": {
                "LL": 0.0,
                "LU": 0.0,
                "UL": 0.0,
                "UU": 0.0,
            },
            "packet_gram_sha256": "a" * 64,
            "recomputed_gram_sha256": "b" * 64,
            "y_authority": "packet_dual_from_VG",
            "z_authority": "fresh_lower_fourier_upper_selected_right_transfer",
            "right_transfer": {
                "schema": "task040.v3.packet_dual_right_transfer.v1",
                "y_authority": "packet_dual_from_VG",
                "z_authority": "fresh_lower_fourier_upper_selected_right_transfer",
                "cross_gram": {
                    "sha256": "b" * 64,
                    "blocks": {
                        "LL": {
                            "shape": [296, 296],
                            "rank": 296,
                            "condition": 2.0,
                            "norm": 1.0,
                            "sha256": "c" * 64,
                            "relative_to_packet": 0.0,
                        },
                        "LU": {
                            "shape": [296, 480],
                            "rank": 0,
                            "condition": None,
                            "norm": 0.0,
                            "sha256": "d" * 64,
                            "relative_to_packet": 0.0,
                        },
                        "UL": {
                            "shape": [480, 296],
                            "rank": 0,
                            "condition": None,
                            "norm": 0.0,
                            "sha256": "e" * 64,
                            "relative_to_packet": 0.0,
                        },
                        "UU": {
                            "shape": [480, 480],
                            "rank": 480,
                            "condition": 2.0,
                            "norm": 1.0,
                            "sha256": "f" * 64,
                            "relative_to_packet": 0.0,
                        },
                    },
                    "offdiagonal_norm": {"LU": 0.0, "UL": 0.0},
                },
                "right_transfer": {
                    "blocks": {
                        "LL": {
                            "rank": 296,
                            "condition": 2.0,
                            "residual_relative": 0.0,
                            "transfer_condition": 2.0,
                        },
                        "UU": {
                            "rank": 480,
                            "condition": 2.0,
                            "residual_relative": 0.0,
                            "transfer_condition": 2.0,
                        },
                    },
                    "offdiagonal_norm": {"LU": 0.0, "UL": 0.0},
                },
                "post_gram_sha256": "b" * 64,
                "post_gram_relative_error": 0.0,
                "post_block_relative_errors": {
                    "LL": 0.0,
                    "LU": 0.0,
                    "UL": 0.0,
                    "UU": 0.0,
                },
            },
        },
        "joint": {
            "shape": [776, 776],
            "rank": 776,
            "condition": checker.EXPECTED_JOINT_CONDITION,
            "content_sha256": TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
            "blocks": {
                name: {
                    "shape": value["shape"],
                    "dtype": value["dtype"],
                    "rank": value["rank"],
                    "norm": value["frobenius_norm"],
                    "sha256": value["sha256"],
                }
                for name, value in packet["joint_exact_blocks"].items()
            },
        },
        "bare_f_identity": {"before": "f" * 64, "after": "f" * 64, "unchanged": True},
        "one_apply": _one_apply(),
        "factor_inventory": {
            "cross_section_group_factor_count": 3,
            "reduced_dense_factor_count": 1,
            "exact_interface_schur_oracle_object_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
        "lifecycle": {
            "factor_count_ready": 3,
            "reduced_dense_factor_count_ready": 1,
            "exact_interface_schur_oracle_object_count": 0,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "factor_count_after_cleanup": 0,
            "reduced_dense_factor_count_after_cleanup": 0,
            "projected_inverse_count_after_cleanup": 0,
            "action_destroyed": True,
            "factor_destroyed": True,
        },
        "fgmres_screen": _screen(mode),
    }
    run = {
        "schema": "task040.v3_2.coupled_interface.v1",
        "method": TASK040_V3_2_COUPLED_INTERFACE_METHOD,
        "profile": TASK040_V3_2_COUPLED_INTERFACE_PROFILE_ID,
        "source_sha": SOURCE_SHA,
        "input_sha256": TASK040_V1_2_INPUT_SHA256,
        "physical_model_sha256": TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        "selected_manifest_sha256": TASK040_V1_2_SELECTED_MANIFEST_SHA256,
        "exact_spool_catalog_sha256": TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        "packet_manifest_sha256": TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        "packet_producer_source_sha": TASK040_V3_2_PRODUCER_SOURCE_SHA,
        "true_joint_content_sha256": TASK040_V3_2_TRUE_JOINT_CONTENT_SHA256,
        "rhs_vectors_loaded": 6,
        "exact_output_vectors_loaded": 0,
        "qep_calls": 0,
        "pde_solve": "not_run",
        "coupled_interface_raw": raw,
    }
    watchdog = {
        "method": TASK040_V3_2_COUPLED_INTERFACE_METHOD,
        "source_sha": SOURCE_SHA,
        "hard_stop_bytes": 45 * 2**30,
        "termination_reason": "natural_exit",
        "return_code": 0,
        "run_summary_present": True,
        "run_summary_sha256": RUN_SUMMARY_SHA,
        "sample_count": 2,
        "authoritative_sample_count": 2,
        "terminal_teardown_excluded_count": 0,
        "all_status_readable": True,
        "swap_authority_readable": True,
        "peak_rss_bytes": 1000,
        "peak_swap_bytes": 0,
        "peak_dedicated_cgroup_swap_bytes": 0,
        "artifact_hashes": {"process_tree_samples.jsonl": TIMELINE_SHA},
        "command": [
            "mpiexec",
            "-n",
            "8",
            "-m",
            "benchmarks.task040_level_a",
            "--source-sha",
            SOURCE_SHA,
            TASK040_V3_2_COUPLED_INTERFACE_FLAG,
            "--interface-packet-root",
            PACKET_ROOT,
        ],
    }
    rows = [
        {
            "authoritative_sample": True,
            "terminal_teardown_excluded": False,
            "rss_bytes": 800 + index * 200,
            "swap_bytes": 0,
            "resource_authority": {
                "process_tree": {"all_status_readable": True, "pids": [100 + index]},
                "job_cgroup": {
                    "dedicated_job_cgroup": True,
                    "swap_current_bytes": 0,
                },
            },
        }
        for index in range(2)
    ]
    return run, watchdog, rows


def _check(mode: str = "early") -> dict[str, object]:
    run, watchdog, rows = _fixture(mode)
    return checker.recompute_v3_full_span(
        run,
        watchdog,
        _packet_audit(),
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
        expected_packet_root=PACKET_ROOT,
    )


def test_v3_checker_binds_packet_to_its_producer_watchdog(tmp_path) -> None:
    packet_root = tmp_path / "producer" / "worker" / "interface_packet"
    packet_root.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="producer watchdog summary"):
        checker._producer_watchdog_summary_path(packet_root)
    watchdog = packet_root.parent.parent / "watchdog_summary.json"
    watchdog.write_text("{}", encoding="utf-8")
    assert checker._producer_watchdog_summary_path(packet_root) == watchdog.resolve()


def test_v3_checker_positive_is_independent_and_json_serializable() -> None:
    result = _check()
    assert result["classification"] == "COUPLED_INTERFACE_FULL_SPAN_PASS"
    assert result["gate_pass"] is True
    assert result["screen"]["first_preferred_checkpoint"] == 4
    assert all(result["checks"].values())
    positive_run, _, _ = _fixture()
    positive_z = positive_run["coupled_interface_raw"]["z_reconstruction"]
    assert positive_z["packet_gram_sha256"] != positive_z["recomputed_gram_sha256"]
    assert json.loads(json.dumps(result))["gate_pass"] is True

    run, watchdog, rows = _fixture()
    run["status"] = "fake_failure"
    run["classification"] = "fake_pass"
    run["coupled_interface_raw"]["gate_pass"] = True
    result = checker.recompute_v3_full_span(
        run,
        watchdog,
        _packet_audit(),
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
    )
    assert result["classification"] == "COUPLED_INTERFACE_FULL_SPAN_PASS"


def test_v3_checker_reports_evidence_valid_numerical_negative() -> None:
    result = _check("negative")
    assert result["evidence_valid"] is True
    assert result["screen"]["contract_pass"] is True
    assert result["numerical_pass"] is False
    assert result["classification"] == "COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL"
    assert result["gate_pass"] is False


def test_v3_checker_derives_conditional32_and64() -> None:
    phase2 = _check("phase2_pass")
    assert phase2["screen"]["first_preferred_checkpoint"] == 32
    assert phase2["screen"]["conditional_64_authorized"] is False
    phase3 = _check("phase3_pass")
    assert phase3["screen"]["conditional_32_authorized"] is True
    assert phase3["screen"]["conditional_64_authorized"] is True
    assert phase3["screen"]["first_preferred_checkpoint"] == 64

    run, watchdog, rows = _fixture("history_tamper")
    result = checker.recompute_v3_full_span(
        run,
        watchdog,
        _packet_audit(),
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
    )
    assert result["classification"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize("tamper", ("manifest", "cross_hash"))
def test_v3_checker_packet_tamper_is_incomplete(tamper: str) -> None:
    packet = _packet_audit()
    manifest_sha = TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256
    if tamper == "manifest":
        packet["manifest_sha256"] = "0" * 64
    else:
        packet["joint_exact_blocks"]["LU"]["sha256"] = "bad"
    run, watchdog, rows = _fixture()
    result = checker.recompute_v3_full_span(
        run,
        watchdog,
        packet,
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=manifest_sha,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
    )
    assert result["classification"] == "COUPLED_PACKET_INFORMATION_INCOMPLETE"
    assert result["gate_pass"] is False


@pytest.mark.parametrize("field", ("factor_count_ready", "factor_count_after_cleanup"))
def test_v3_checker_factor_lifecycle_tamper_is_implementation(field: str) -> None:
    run, watchdog, rows = _fixture()
    value = 4 if field == "factor_count_ready" else 1
    run["coupled_interface_raw"]["lifecycle"][field] = value
    result = checker.recompute_v3_full_span(
        run,
        watchdog,
        _packet_audit(),
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
    )
    assert result["classification"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize(
    "tamper",
    (
        "one_apply_labels",
        "action_count",
        "factor_inventory",
        "joint_block",
        "phase1_trend",
        "watchdog_peak",
        "y_authority",
        "gram_block_error",
        "packet_gram_hash",
        "right_transfer_post",
        "right_transfer_cross",
    ),
)
def test_v3_checker_implementation_contract_tamper(tamper: str) -> None:
    mode = "negative" if tamper == "phase1_trend" else "early"
    run, watchdog, rows = _fixture(mode)
    raw = run["coupled_interface_raw"]
    if tamper == "one_apply_labels":
        raw["one_apply"]["labels"][0] = "tampered"
    elif tamper == "action_count":
        raw["one_apply"]["action_apply_count"] = 14
    elif tamper == "factor_inventory":
        raw["factor_inventory"]["full_side_exact_factor_count"] = 1
    elif tamper == "joint_block":
        raw["joint"]["blocks"]["LU"]["sha256"] = "bad"
    elif tamper == "phase1_trend":
        raw["fgmres_screen"]["phase1"][NONZERO[0]]["checkpoints"]["16"][
            "true_residual_relative"
        ] = 0.9
    elif tamper == "y_authority":
        raw["z_reconstruction"]["y_authority"] = (
            "current_lower_upper_left_basis_trace_mass_dual"
        )
    elif tamper == "gram_block_error":
        raw["z_reconstruction"]["gram_block_relative_errors"]["LU"] = 1.0e-9
    elif tamper == "packet_gram_hash":
        raw["z_reconstruction"]["packet_gram_sha256"] = "x" * 64
    elif tamper == "right_transfer_post":
        raw["z_reconstruction"]["right_transfer"]["post_block_relative_errors"][
            "LL"
        ] = 1.0e-9
    elif tamper == "right_transfer_cross":
        raw["z_reconstruction"]["right_transfer"]["cross_gram"]["offdiagonal_norm"][
            "LU"
        ] = 1.0e-9
    else:
        watchdog["peak_rss_bytes"] = 999
    result = checker.recompute_v3_full_span(
        run,
        watchdog,
        _packet_audit(),
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
        expected_packet_root=PACKET_ROOT,
    )
    assert result["classification"] == "IMPLEMENTATION_FAILURE"


@pytest.mark.parametrize("tamper", ("rss", "swap", "hash", "count", "source"))
def test_v3_checker_resource_and_identity_tamper(tamper: str) -> None:
    run, watchdog, rows = _fixture()
    if tamper == "rss":
        rows[1]["rss_bytes"] = 45 * 2**30
        watchdog["peak_rss_bytes"] = 45 * 2**30
    elif tamper == "swap":
        rows[0]["swap_bytes"] = 1
        rows[0]["resource_authority"]["process_tree"]["swap_bytes"] = 1
        watchdog["peak_swap_bytes"] = 1
    elif tamper == "hash":
        watchdog["artifact_hashes"]["process_tree_samples.jsonl"] = "wrong"
    elif tamper == "count":
        watchdog["sample_count"] = 1
    else:
        run["source_sha"] = "d" * 40
    result = checker.recompute_v3_full_span(
        run,
        watchdog,
        _packet_audit(),
        rows,
        expected_source_sha=SOURCE_SHA,
        manifest_sha256=TASK040_V3_2_AUGMENTED_PACKET_MANIFEST_SHA256,
        run_summary_sha256=RUN_SUMMARY_SHA,
        timeline_sha256=TIMELINE_SHA,
    )
    if tamper in {"source", "hash", "count"}:
        assert result["classification"] == "IMPLEMENTATION_FAILURE"
    else:
        assert result["classification"] == "COUPLED_INTERFACE_FULL_SPAN_RESOURCE_FAIL"
