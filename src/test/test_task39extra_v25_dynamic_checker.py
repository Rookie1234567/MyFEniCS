"""Small raw-field tests for the V25 dynamic accounting checker.

The literal call shape is copied from the historical V24 raw repair schema
(source ``2bb6770ad00b35881558c576e7296e250656e571``).  It is intentionally a
small tracked fixture, not a dependency on an ignored laptop result tree.
"""

from __future__ import annotations

from copy import deepcopy
import sys

from benchmarks.task39extra_v25_dynamic_checker import (
    BACKEND,
    BEST_FINITE_EXHAUSTION_PROFILE,
    H6_BACKEND,
    NATIVE_A4_IMPLEMENTATION,
    THREAD_CONTRACT,
    V29_A4_IMPLEMENTATION,
    V29_A4_ORACLE,
    V30_PROFILE,
    V31_PROFILE,
    V30_V31_COMPONENT_IDENTITY,
    _monitoring_facts,
    _raw_bal_h_facts,
    _raw_call_facts,
    _runtime_thread_facts,
    check_summary,
)


RAW_SCHEMA_SOURCE_SHA = "2bb6770ad00b35881558c576e7296e250656e571"


def _repair_record(
    rhs_norm: float,
    *,
    phase: str,
    index: int,
    factor_solve_call_delta: int,
    residual_norm: float,
) -> dict:
    denominator = max(rhs_norm, sys.float_info.min)
    return {
        "phase": phase,
        "index": index,
        "rhs_norm": rhs_norm,
        "residual_norm": residual_norm,
        "relative_residual": residual_norm / denominator,
        "factor_solve_call_delta": factor_solve_call_delta,
    }


def _call(
    *,
    rhs_norm: float = 1.0,
    extra_solve_count: int = 0,
    residual_norms: tuple[float, ...] | None = None,
) -> dict:
    nonzero = rhs_norm != 0.0
    actual = (1 if nonzero else 0) + extra_solve_count
    if residual_norms is None:
        residual_norms = (0.0,) * (1 + extra_solve_count)
    assert len(residual_norms) == 1 + extra_solve_count
    records = [
        _repair_record(
            rhs_norm,
            phase="raw",
            index=0,
            factor_solve_call_delta=1 if nonzero else 0,
            residual_norm=residual_norms[0],
        )
    ]
    records.extend(
        _repair_record(
            rhs_norm,
            phase="correction",
            index=index,
            factor_solve_call_delta=1,
            residual_norm=residual_norms[index],
        )
        for index in range(1, extra_solve_count + 1)
    )
    return {
        "inner": {
            "repair": {
                "logical_p4_apply_count": 1,
                "actual_mat_solve_count": actual,
                "native_A4_action_count": 1 + extra_solve_count,
                "rhs_norm": rhs_norm,
                "extra_solve_count": extra_solve_count,
                "records": records,
                "final_relative_residual": records[-1]["relative_residual"],
            },
            "p4_mat_solve_count": actual,
        }
    }


def _soft_call(residual_norms: tuple[float, ...]) -> dict:
    extra = len(residual_norms) - 1
    call = _call(extra_solve_count=extra, residual_norms=residual_norms)
    repair = call["inner"]["repair"]
    ratios = [record["relative_residual"] for record in repair["records"]]
    selected = min(range(len(ratios)), key=lambda index: (ratios[index], index))
    returned = ratios[selected]
    repair.update(
        a4_action_implementation=V29_A4_IMPLEMENTATION,
        a4_action_oracle=V29_A4_ORACLE,
        best_snapshot_peak_local_bytes=(
            3 * 201520 * 16 + 80 * 16
            if returned > 1.0e-10 else 0
        ),
        selected_evidence_copy_local_bytes=(
            4 * 201520 * 16 + 80 * 16
            if returned > 1.0e-10 else 0
        ),
        final_relative_residual=returned,
        selected_attempt=selected,
        returned_rho=returned,
        last_attempt_rho=ratios[-1],
        min_rho=min(ratios),
        status=(
            "COARSE_TARGET_UNMET_CONTINUE"
            if returned > 1.0e-10 else
            "REFINED_TARGET_MET" if extra else "NOT_NEEDED"
        ),
    )
    call["a4_action_implementation"] = V29_A4_IMPLEMENTATION
    call["a4_action_oracle"] = V29_A4_ORACLE
    call["native_A4_relative_residual"] = returned
    return call


def _set_v29_a4_identity(summary: dict) -> None:
    total = 0
    for boundary in summary["pc"]["boundary_records"]:
        for call in boundary["pc"]["inexact_balance"]["calls"]:
            repair = call["inner"]["repair"]
            identity = {
                "a4_action_implementation": V29_A4_IMPLEMENTATION,
                "a4_action_oracle": V29_A4_ORACLE,
            }
            call.update(identity)
            repair.update(identity)
            total += int(repair["native_A4_action_count"])
    summary["formal_release_timing"]["a4_verification"] = {
        "action_count": total,
        "implementation": V29_A4_IMPLEMENTATION,
        "oracle_identity": V29_A4_ORACLE,
        "selected_action_audit": {"apply_count": total},
        "selected_action_apply_count_start": 0,
        "selected_action_apply_count_end": total,
        "candidate_construction_facts": {
            "implementation_identity": V29_A4_IMPLEMENTATION,
            "oracle_identity": V29_A4_ORACLE,
            "degree": 4,
            "action_role": "full_A4_verification_candidate",
        },
        "soft_repair_workspace": {
            "enabled": True,
            "reserved_coarse_vector_upper_count": 24,
            "reserved_bytes": 24 * 201520 * 16,
            "best_snapshot_upper_bytes": 3 * 201520 * 16 + 80 * 16,
            "selected_evidence_copy_upper_bytes": 4 * 201520 * 16 + 80 * 16,
        },
    }


def _boundary(*, first_call: dict | None = None) -> dict:
    call = first_call if first_call is not None else _call()
    return {
        "completed": True,
        "pc": {
            "route": "BAL_H",
            "inexact_balance": {
                "calls": [deepcopy(call), _call()],
            },
        },
    }


def _live_candidate_a6() -> dict:
    component = lambda: {
        "apply_count": 2,
        "local_kernel": {
            "backend": BACKEND,
            "sum_factorized_opt_in": True,
        },
    }
    return {
        "apply_count": 2,
        "volume_action": {
            "components": {
                "curl_curl": component(),
                "complex_material_mass": component(),
            }
        },
    }


def _v25_fixture() -> tuple[dict, dict]:
    boundaries = [_boundary()]
    boundaries.extend(_boundary() for _ in range(3))
    # The first check call has one repair.  All remaining calls are ordinary
    # nonzero logical calls: logical=254, physical F4=255, MatSolve=255.
    boundaries.append(_boundary(first_call=_call(extra_solve_count=1)))
    boundaries.extend(_boundary() for _ in range(122))
    assert len(boundaries) == 127

    pair = {
        "passed": True,
        "variants": {
            name: {"pc_apply_delta": 1}
            for name in (
                "native_a6_native_h6",
                "candidate_a6_native_h6",
                "native_a6_candidate_h6",
                "candidate_a6_candidate_h6",
            )
        },
    }
    summary = {
        "status": "WORKER_CLAIMS_PASS",
        "release_after_final_residual": True,
        "final_explicit_relative_residual": 5.0e-7,
        "post_release_explicit_relative_residual": 5.0e-7,
        "solver": {
            "status": "TRUE_RESIDUAL_PASS",
            "final_true_residual": 5.0e-7,
            "pc_apply_count": 122,
            "retained_outer": {
                "actual_first_arnoldi": {
                    "passed": True,
                    "input_is_zero_start_retained_rhs": True,
                    "used_as_initial_guess": False,
                    "finite_output": True,
                    "size_ok": True,
                    "pair": pair,
                }
            },
        },
        "pc": {
            "apply_count": 127,
            "h6_apply_count": 127,
            "boundary_records": boundaries,
        },
        "x1_setup_checks": {
            "setup_pc_counts": {
                "bal_h": 1,
                "p4_call_records": [{"phase": "raw"}, {"phase": "raw"}],
            }
        },
        "formal_release_timing": {
            "p4": {
                "logical_p4_call_count": 254,
                "physical_f4_call_count": 255,
                "actual_mat_solve_count": 255,
            },
            "h6_apply_count": 127,
            "h6": {
                "apply_count": 127,
                "light_facts": {
                    "apply_action_backend": "packed_partial_assembly",
                    "sum_factorized_work_opt_in": True,
                    "power10_action_backend": "packed_partial_assembly",
                    "sum_factorized_power10_opt_in": True,
                },
            },
            "candidate_pc_internal_A6": {
                "construction_facts": {},
                "live_audit": _live_candidate_a6(),
            },
        },
        "native_aq_projection_check": {
            "passed": True,
            "probe_identity": {
                "owned_slave_zero": True,
                "input_unchanged_after_transfer": True,
            },
            "native_output_slave_zero": {"volume": True, "dtn": True},
            "volume": {"relative": 2.0e-15},
            "dtn": {"relative": 3.0e-15},
        },
    }
    config = {
        "solver": {
            "physical_operator_backend": BACKEND,
            "h6_backend_rule": H6_BACKEND,
            "thread_contract": THREAD_CONTRACT,
            "stage": "Q4_ORIGINAL",
            "coarse_degree": 4,
        }
    }
    return summary, config


def _versioned_fixture(profile: str = V30_PROFILE):
    summary, config = _v25_fixture()
    summary["pc"]["boundary_records"].extend(_boundary() for _ in range(4))
    for boundary in summary["pc"]["boundary_records"]:
        for index, _call_record in enumerate(boundary["pc"]["inexact_balance"]["calls"]):
            boundary["pc"]["inexact_balance"]["calls"][index] = _soft_call((0.0,))
    # Keep one extra MatSolve in the synthetic V30/V31 accounting closure.
    summary["pc"]["boundary_records"][4]["pc"]["inexact_balance"]["calls"][0] = _soft_call(
        (1.0, 1.0e-12)
    )
    summary["solver"]["pc_apply_count"] = 126
    summary["pc"]["apply_count"] = 131
    summary["pc"]["h6_apply_count"] = 131

    release = summary["formal_release_timing"]
    release["p4"].update(
        logical_p4_call_count=262,
        actual_mat_solve_count=263,
        physical_f4_call_count=263,
    )
    release["BAL_H"] = {"counts": {"C": 262, "A_structure": 262, "smoother": 131}}
    release["h6_apply_count"] = 131
    h6 = release["h6"]
    h6.update(apply_count=131, matrix_mult_count=282, power_matrix_mult_count=20)
    h6_facts = h6["light_facts"]
    h6_facts.update(
        power_matrix_mult_count=20,
        direct_selected_backend_used=True,
        apply_action_backend="packed_partial_assembly",
        power10_action_backend="packed_partial_assembly",
        sum_factorized_power10_opt_in=True,
    )

    identity = V30_V31_COMPONENT_IDENTITY
    q_identity = {
        "degree": identity["quadrature_degree"],
        "rule": identity["quadrature_rule"],
        "points_sha256": identity["points_sha256"],
        "weights_sha256": identity["weights_sha256"],
    }
    components = {}
    for component_name, qname in (("curl_curl", "curl"), ("complex_material_mass", "mass")):
        components[component_name] = {
            "backend": BACKEND,
            "component": qname,
            "sum_factorized_opt_in": True,
            "quadrature_degree": identity["quadrature_degree"],
            "quadrature_rule": identity["quadrature_rule"],
            "points": identity["points"],
            "points_sha256": identity["points_sha256"],
            "weights_sha256": identity["weights_sha256"],
            "natural_order_internal_opt_in": False,
            "continuous_projection_matmul_opt_in": False,
            "sum_factorized_audit": {
                "backend": BACKEND,
                "element_family": "N1E",
                "degree": 6,
                "element_dimension": 882,
                "element_variant": "legendre",
                "map_type": "covariantPiola",
                "polyset_type": "standard",
                "coefficient_matrix_shape": list(identity["coefficient_matrix_shape"]),
                "coefficient_matrix_sha256": identity["coefficient_matrix_sha256"],
                "quadrature_weights_sha256": identity["weights_sha256"],
                "quadrature_points": identity["points"],
                "quadrature_order": "actual_points_to_tensor_grid_checked",
                "quadrature_shape": list(identity["quadrature_shape"]),
                "projection_layout_v31_candidate": {
                    "natural_order_internal": False,
                    "continuous_projection_matmul": False,
                },
            },
        }
    fused = {
        "schema": "task039extra.fused-isotropic-split-kernel.v1",
        "cell_count": 990,
        "batch_size": 8,
        "apply_count": 2,
        "full_apply_count": 2,
        "component_apply_count": 0,
        "curl_component_apply_count": 0,
        "mass_component_apply_count": 0,
        "gather_count": 248,
        "coefficient_forward_count": 248,
        "coefficient_backward_count": 248,
        "scatter_count": 248,
        "curl_integral_count": 248,
        "mass_integral_count": 248,
        "component_quadrature_identities": {"curl": q_identity, "mass": q_identity},
        "distinct_integral_rules_preserved": True,
        "ordinary_default_changed": False,
    }
    live_candidate = release["candidate_pc_internal_A6"]["live_audit"]
    live_candidate["apply_count"] = 2
    live_candidate["volume_action"] = {
        "schema": "task039extra.fused-split-volume-action.v1",
        "apply_count": 2,
        "components": components,
        "fused_local_kernel": fused,
    }

    natural_v31 = profile == V31_PROFILE
    natural_points = (
        "b" * 64 if natural_v31 else identity["points_sha256"]
    )
    natural_weights = (
        "c" * 64 if natural_v31 else identity["weights_sha256"]
    )
    live_h6 = {
        "backend": BACKEND,
        "sum_factorized_opt_in": True,
        "quadrature_degree": identity["quadrature_degree"],
        "quadrature_rule": identity["quadrature_rule"],
        "points": identity["points"],
        "points_sha256": identity["points_sha256"],
        "weights_sha256": identity["weights_sha256"],
        "natural_order_internal_opt_in": natural_v31,
        "continuous_projection_matmul_opt_in": False,
        "sum_factorized_audit": {
            "backend": BACKEND,
            "degree": 6,
            "element_dimension": 882,
            "coefficient_matrix_shape": list(identity["coefficient_matrix_shape"]),
            "coefficient_matrix_sha256": identity["coefficient_matrix_sha256"],
            "quadrature_weights_sha256": identity["weights_sha256"],
            "quadrature_points": identity["points"],
            "quadrature_shape": list(identity["quadrature_shape"]),
            "points_sha256": identity["points_sha256"],
            "weights_sha256": identity["weights_sha256"],
            "quadrature_order": "actual_points_to_tensor_grid_checked",
            "points_sha256": identity["points_sha256"],
            "weights_sha256": identity["weights_sha256"],
            "internal_points_sha256": natural_points,
            "internal_weights_sha256": natural_weights,
            "internal_quadrature_order": (
                "natural_tensor_order_v31" if natural_v31 else "source_input_order"
            ),
            "natural_order_internal_opt_in": natural_v31,
            "continuous_projection_matmul_opt_in": False,
            "backward_projection_kernel": "einsum_z_y_x_legacy",
            "point_permutation_bijection_verified": True,
            "weights_permuted_with_points": natural_v31,
            "projection_workspace_bytes": 0,
        },
    }
    h6_facts["live_kernel_audit"] = live_h6
    _set_v29_a4_identity(summary)

    config["solver"].update(
        preconditioner=profile,
        physical_operator_backend=BACKEND,
        h6_backend_rule="direct_selected_backend_same_apply_and_power10",
        thread_contract="mpi1_omp1_blas1_v26",
        stage="Q4_ORIGINAL",
        coarse_degree=4,
    )
    sha = "a" * 64
    manifest = {
        "mpi_size": 1,
        "source_sha": "fixture-source-sha",
        "resolved_config_sha256": sha,
        "environment": {
            "qualified_activation": "1",
            "platform": "Linux fixture",
            "python_executable": "/fixture/.venv/bin/python",
        },
    }
    run_summary = {
        "status": "finished",
        "exit_status": 0,
        "swap_policy": "observe_only",
        "resource_authority": {
            "classification": "COMPLETED",
            "leader_exit_code": 0,
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "sampled_process_tree_rss_peak_bytes": 100,
            "sampled_process_tree_swap_peak_bytes": 0,
            "sampled_process_tree_pss_peak_bytes": None,
            "pss_status": "DISABLED_BY_PROFILE",
            "swap_policy": "observe_only",
            "process_tree_swap_gate_enforced": False,
            "source_state": {
                "source_sha": "fixture-source-sha",
                "tracked_and_nonignored_untracked_clean": True,
            },
        },
    }
    return summary, config, manifest, run_summary, sha


def test_counts_are_recomputed_from_raw_calls_and_four_diagnostics() -> None:
    summary, config = _v25_fixture()
    result = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is True
    assert result["partial"] is True
    assert "passed" not in result
    counts = result["recomputed"]["bal_h_and_p4"]
    assert counts["setup_bal_h"] == 1
    assert counts["check_bal_h"] == 4
    assert counts["iteration_bal_h"] == 122
    assert counts["logical_units"] == 254
    assert counts["physical_f4_calls"] == 255
    assert counts["actual_mat_solve"] == 255
    assert counts["extra_repairs"] == 1


def test_v27_workingset_backend_contract_is_accepted_without_changing_v25_defaults():
    summary, config = _v25_fixture()
    config["solver"].update(
        preconditioner="physical_p6_trace_workingset_efficiency_v27",
        h6_backend_rule="direct_selected_backend_same_apply_and_power10",
        thread_contract="mpi1_omp1_blas1_v26",
    )
    result = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is True
    assert result["recomputed"]["backend"]["checks"]["h6_backend_rule"] is True
    assert result["recomputed"]["backend"]["checks"]["thread_contract"] is True


def test_v28_fused_backend_selects_a6_fusion_and_nonshared_a6_h6_kernels():
    summary, config = _v25_fixture()
    config["solver"].update(
        preconditioner="physical_p6_trace_fused_kernel_v28",
        h6_backend_rule="direct_selected_backend_same_apply_and_power10",
        thread_contract="mpi1_omp1_blas1_v26",
    )
    release = summary["formal_release_timing"]
    candidate = release["candidate_pc_internal_A6"]["live_audit"]
    volume = candidate["volume_action"]
    volume["apply_count"] = 2
    volume.update(
        schema="task039extra.fused-split-volume-action.v1",
        fused_local_kernel={
            "cell_count": 990,
            "batch_size": 8,
            "apply_count": 2,
            "full_apply_count": 2,
            "component_apply_count": 0,
            "curl_component_apply_count": 0,
            "mass_component_apply_count": 0,
            "gather_count": 248,
            "coefficient_forward_count": 248,
            "coefficient_backward_count": 248,
            "scatter_count": 248,
            "curl_integral_count": 248,
            "mass_integral_count": 248,
            "tensor_contractions": {
                name: {
                    "forward_tensor_contraction_count": 100,
                    "backward_tensor_contraction_count": 100,
                    "timing_cumulative_seconds": {
                        "reference_forward": 1.0,
                        "reference_backward": 1.0,
                    },
                }
                for name in ("curl", "mass")
            },
        },
    )
    for component in volume["components"].values():
        kernel = component.pop("local_kernel")
        component.clear()
        component.update(kernel)
        component["shared_contractions_opt_in"] = False
    release["h6"]["light_facts"].update(
        direct_selected_backend_used=True,
        power_matrix_mult_count=20,
        power_matrix_mult_seconds=0.5,
        apply_action_backend="packed_partial_assembly",
        power10_action_backend="packed_partial_assembly",
        sum_factorized_power10_opt_in=True,
        live_kernel_audit={
            "shared_contractions_opt_in": False,
            "sum_factorized_audit": {
                "forward_tensor_contraction_count": 100,
                "backward_tensor_contraction_count": 100,
            },
            "timing_cumulative_seconds": {
                "reference_forward": 1.0,
                "reference_backward": 1.0,
            },
        },
        # The checker must bind power10 to this live direct-selected backend,
        # not this construction-time snapshot.
        power10_kernel={"shared_contractions_opt_in": True},
    )

    result = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is True
    checks = result["recomputed"]["backend"]["checks"]
    assert checks["fused_volume_schema"] is True
    assert checks["fused_curl_and_mass_integrated"] is True
    assert checks["candidate_a6_shared_contractions_disabled"] is True
    assert checks["candidate_a6_contraction_audit_present"] is True
    assert checks["h6_apply_shared_contractions_disabled"] is True
    assert checks["h6_power10_uses_same_live_nonshared_backend"] is True

    misconfigured = deepcopy(summary)
    misconfigured["formal_release_timing"]["h6"]["light_facts"][
        "live_kernel_audit"
    ]["shared_contractions_opt_in"] = True
    rejected = check_summary(
        misconfigured, resolved_config=config, stage="Q4_ORIGINAL"
    )
    assert rejected["dynamic_passed"] is False
    assert rejected["recomputed"]["backend"]["checks"][
        "h6_apply_shared_contractions_disabled"
    ] is False


def test_versioned_v30_and_v31_fixture_closes_live_counts_with_limited_threads():
    for profile in (V30_PROFILE, V31_PROFILE):
        summary, config, manifest, run_summary, sha = _versioned_fixture(profile)
        result = check_summary(
            summary,
            resolved_config=config,
            stage="Q4_ORIGINAL",
            run_manifest=manifest,
            run_summary=run_summary,
            resolved_config_sha256=sha,
        )
        assert result["dynamic_passed"] is True
        assert result["status"] == "DYNAMIC_PASS_EVIDENCE_LIMITED"
        backend = result["recomputed"]["backend"]
        assert backend["call_scope"]["logical_C"] == 262
        assert backend["call_scope"]["H6_apply"] == 131
        assert backend["call_scope"]["B6_matrix_mult_including_power10"] == 282
        assert backend["raw_pc_scope"] == {
            "setup_BAL_H": 1,
            "check_BAL_H": 4,
            "outer_iteration_BAL_H": 126,
            "cumulative_PC_apply": 131,
            "raw_boundary_records": 131,
            "logical_C": 262,
        }
        if profile == V31_PROFILE:
            assert backend["projection_layout"]["passed"] is True
            assert backend["projection_layout"]["checks"]["live_h6_flags_match_config"] is True
            assert backend["projection_layout"]["checks"]["a6_unchanged_for_h6_scope"] is True


def test_versioned_negative_fixtures_reject_backend_threads_integral_identity_and_missing_fields():
    summary, config, manifest, run_summary, sha = _versioned_fixture(V31_PROFILE)
    config["solver"]["physical_operator_backend"] = "wrong_backend"
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["checks"]["physical_operator_backend"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V30_PROFILE)
    manifest["environment"]["OPENBLAS_NUM_THREADS"] = "8"
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["checks"]["runtime_thread_environment_matches_one"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V30_PROFILE)
    components = summary["formal_release_timing"]["candidate_pc_internal_A6"]["live_audit"]["volume_action"]["components"]
    components["curl_curl"]["points_sha256"] = "0" * 64
    summary["formal_release_timing"]["candidate_pc_internal_A6"]["live_audit"]["volume_action"]["fused_local_kernel"]["component_quadrature_identities"]["curl"]["points_sha256"] = "0" * 64
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["candidate_component_checks"]["curl_curl"]["quadrature_identity"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V31_PROFILE)
    components = summary["formal_release_timing"]["candidate_pc_internal_A6"]["live_audit"]["volume_action"]["components"]
    audit = components["curl_curl"]["sum_factorized_audit"]
    audit.pop("coefficient_matrix_sha256")
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["checks"]["candidate_a6_quadrature_identity"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V31_PROFILE)
    h6_audit = summary["formal_release_timing"]["h6"]["light_facts"]["live_kernel_audit"]["sum_factorized_audit"]
    h6_audit["natural_order_internal_opt_in"] = False
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["projection_layout"]["checks"]["live_h6_flags_match_config"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V31_PROFILE)
    components = summary["formal_release_timing"]["candidate_pc_internal_A6"]["live_audit"]["volume_action"]["components"]
    component_audit = components["curl_curl"]["sum_factorized_audit"]
    component_audit["projection_layout_v31_candidate"]["natural_order_internal"] = True
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["projection_layout"]["checks"]["a6_unchanged_for_h6_scope"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V31_PROFILE)
    summary["formal_release_timing"]["candidate_pc_internal_A6"]["live_audit"]["volume_action"]["components"]["curl_curl"] = None
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False


def test_versioned_pcscope_and_disabled_pss_contract_reject_scope_drift():
    summary, config, manifest, run_summary, sha = _versioned_fixture(V30_PROFILE)
    summary["formal_release_timing"]["h6"]["matrix_mult_count"] -= 2
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["backend"]["checks"]["actual_B6_and_power10_scopes_close"] is False

    summary, config, manifest, run_summary, sha = _versioned_fixture(V30_PROFILE)
    run_summary["resource_authority"]["pss_status"] = "MEASURED"
    run_summary["resource_authority"]["sampled_process_tree_pss_peak_bytes"] = 100
    result = check_summary(
        summary,
        resolved_config=config,
        stage="Q4_ORIGINAL",
        run_manifest=manifest,
        run_summary=run_summary,
        resolved_config_sha256=sha,
    )
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["monitoring"]["checks"]["pss_status_explicit_and_disabled_by_profile"] is False


def test_v31_best_state_continue_checks_selected_attempt_and_two_refinements():
    for selected, residuals in ((0, (0.3, 0.4, 0.5)), (1, (0.4, 0.3, 0.5))):
        summary, config, manifest, run_summary, sha = _versioned_fixture(V31_PROFILE)
        call = _soft_call(residuals)
        summary["pc"]["boundary_records"][4]["pc"]["inexact_balance"]["calls"][0] = call
        summary["formal_release_timing"]["p4"].update(
            actual_mat_solve_count=264,
            physical_f4_call_count=264,
        )
        _set_v29_a4_identity(summary)
        result = check_summary(
            summary,
            resolved_config=config,
            stage="Q4_ORIGINAL",
            run_manifest=manifest,
            run_summary=run_summary,
            resolved_config_sha256=sha,
        )
        raw = result["recomputed"]["bal_h_and_p4"]
        assert raw["passed"] is True
        assert raw["coarse_unmet_continued_count"] == 1
        assert raw["actual_mat_solve"] == 264
        assert raw["rows"][8]["selected_attempt"] == selected

        broken = deepcopy(summary)
        broken_call = broken["pc"]["boundary_records"][4]["pc"]["inexact_balance"]["calls"][0]
        if selected == 0:
            broken_call["inner"]["repair"]["selected_attempt"] = 1
        else:
            broken_call["inner"]["repair"].pop("selected_attempt")
        rejected = check_summary(
            broken,
            resolved_config=config,
            stage="Q4_ORIGINAL",
            run_manifest=manifest,
            run_summary=run_summary,
            resolved_config_sha256=sha,
        )
        assert rejected["recomputed"]["bal_h_and_p4"]["passed"] is False


def test_runtime_thread_and_monitoring_evidence_boundaries_are_explicit():
    assert _runtime_thread_facts({})["status"].startswith("EVIDENCE_LIMITED")
    assert _runtime_thread_facts(
        {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    )["status"] == "measured"
    assert _runtime_thread_facts({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "8"})["passed"] is False

    _summary, _config, manifest, run_summary, _sha = _versioned_fixture(V30_PROFILE)
    monitoring = _monitoring_facts(manifest, run_summary)
    assert monitoring["passed"] is True
    assert monitoring["thread_runtime_evidence"].startswith("EVIDENCE_LIMITED")
    run_summary["resource_authority"]["pss_status"] = "MEASURED"
    run_summary["resource_authority"]["sampled_process_tree_pss_peak_bytes"] = 1
    assert _monitoring_facts(manifest, run_summary)["passed"] is False


def test_v25_checker_defaults_remain_the_historical_contract():
    assert H6_BACKEND == "isotropic_sum_factorized_n1e_v26_apply_and_power10"
    assert THREAD_CONTRACT == "mpi1_omp1_blas1_v25"


def test_worker_status_cannot_hide_a_bad_raw_repair_count() -> None:
    summary, config = _v25_fixture()
    broken = deepcopy(summary)
    broken["status"] = "TRUE_RESIDUAL_PASS"
    broken["pc"]["boundary_records"][2]["pc"]["inexact_balance"]["calls"][0][
        "inner"
    ]["repair"]["actual_mat_solve_count"] += 1
    result = check_summary(broken, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is False
    assert "raw_bal_h_and_p4" in result["gate_failures"]


def test_call_reader_covers_tiny_nonzero_zero_rhs_and_two_repairs() -> None:
    nonzero, failures = _raw_call_facts(
        _call(
            rhs_norm=1.0e-320,
            residual_norms=(0.0,),
        ),
        "tiny_nonzero",
    )
    assert not failures
    assert nonzero["logical_units"] == 1
    assert nonzero["actual_mat_solve"] == 1

    zero, failures = _raw_call_facts(_call(rhs_norm=0.0), "zero")
    assert not failures
    assert zero["logical_units"] == 1
    assert zero["nonzero_logical_units"] == 0
    assert zero["actual_mat_solve"] == 0

    repaired, failures = _raw_call_facts(
        _call(
            extra_solve_count=2,
            residual_norms=(2.8870661155266027e-10, 2.0e-10, 9.827559370577298e-13),
        ),
        "two_repairs",
    )
    assert not failures
    assert repaired["physical_f4_calls"] == 3
    assert repaired["actual_mat_solve"] == 3
    assert repaired["extra_repairs"] == 2


def test_final_repair_residual_over_limit_rejects_worker_pass_status() -> None:
    summary, config = _v25_fixture()
    bad = deepcopy(summary)
    bad["status"] = "TRUE_RESIDUAL_PASS"
    repair = bad["pc"]["boundary_records"][4]["pc"]["inexact_balance"]["calls"][0][
        "inner"
    ]["repair"]
    repair["records"][-1].update(
        {"residual_norm": 2.0e-10, "relative_residual": 2.0e-10}
    )
    repair["final_relative_residual"] = 2.0e-10
    result = check_summary(bad, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is False
    assert "raw_bal_h_and_p4" in result["gate_failures"]


def test_extra_setup_is_counted_once_and_not_from_x1_copy() -> None:
    summary, config = _v25_fixture()
    summary["pc"]["boundary_records"].insert(0, deepcopy(summary["pc"]["boundary_records"][0]))
    summary["pc"]["apply_count"] = 128
    summary["pc"]["h6_apply_count"] = 128
    setup = summary["x1_setup_checks"]["setup_pc_counts"]
    setup["bal_h"] = 2
    setup["p4_call_records"].extend(deepcopy(setup["p4_call_records"]))
    summary["formal_release_timing"]["p4"].update(
        {
            "logical_p4_call_count": 256,
            "physical_f4_call_count": 257,
            "actual_mat_solve_count": 257,
        }
    )
    summary["formal_release_timing"]["h6_apply_count"] = 128
    summary["formal_release_timing"]["h6"]["apply_count"] = 128
    result = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is True
    counts = result["recomputed"]["bal_h_and_p4"]
    assert counts["setup_bal_h"] == 2
    assert counts["logical_units"] == 256
    assert counts["actual_mat_solve"] == 257


def test_release_is_required_even_when_post_residual_is_present() -> None:
    summary, config = _v25_fixture()
    summary.pop("release_after_final_residual")
    result = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is False
    assert result["recomputed"]["residual"]["checks"]["release_after_final_residual"] is False


def test_missing_native_aq_is_not_reported_as_pass() -> None:
    summary, config = _v25_fixture()
    summary.pop("native_aq_projection_check")
    result = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert result["dynamic_passed"] is False
    assert "native_aq" in result["gate_failures"]


def test_soft_checker_recomputes_best_finite_selection_and_tie_order():
    call = _soft_call((0.4, 0.4, 0.5))
    facts, failures = _raw_call_facts(
        call, "soft_tie", allow_soft_return=True
    )
    assert not failures
    assert facts["selected_attempt"] == 0
    assert facts["final_recomputed_relative"] == 0.4
    assert facts["last_attempt_recomputed_relative"] == 0.5
    assert facts["coarse_target_met"] is False

    broken = deepcopy(call)
    broken["inner"]["repair"]["selected_attempt"] = 1
    _facts, failures = _raw_call_facts(
        broken, "soft_tie", allow_soft_return=True
    )
    assert "soft_tie.selected_attempt_not_argmin_tie_earliest" in failures


def test_only_v29_resolved_profile_allows_soft_return_status():
    summary, config = _v25_fixture()
    for boundary in summary["pc"]["boundary_records"]:
        calls = boundary["pc"]["inexact_balance"]["calls"]
        boundary["pc"]["inexact_balance"]["calls"] = [
            _soft_call((0.0,)) for _ in calls
        ]
    call = _soft_call((0.5, 0.4, 0.5))
    summary["pc"]["boundary_records"][4]["pc"]["inexact_balance"]["calls"][0] = call
    summary["formal_release_timing"]["p4"].update(
        actual_mat_solve_count=256,
        physical_f4_call_count=256,
    )
    _set_v29_a4_identity(summary)

    config["solver"]["preconditioner"] = BEST_FINITE_EXHAUSTION_PROFILE
    allowed = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    bal_h = allowed["recomputed"]["bal_h_and_p4"]
    assert bal_h["passed"] is True
    assert bal_h["coarse_target_met_all"] is False
    assert bal_h["coarse_unmet_continued_count"] == 1
    assert bal_h["returned_rho_distribution"]["max"] == 0.4

    config["solver"]["preconditioner"] = "physical_p6_trace_fused_kernel_v28"
    strict = check_summary(summary, resolved_config=config, stage="Q4_ORIGINAL")
    assert strict["recomputed"]["bal_h_and_p4"]["passed"] is False
    assert "raw_bal_h_and_p4" in strict["gate_failures"]

    fallback = deepcopy(summary)
    for boundary in fallback["pc"]["boundary_records"]:
        for call in boundary["pc"]["inexact_balance"]["calls"]:
            repair = call["inner"]["repair"]
            call["a4_action_implementation"] = NATIVE_A4_IMPLEMENTATION
            call["a4_action_oracle"] = NATIVE_A4_IMPLEMENTATION
            repair["a4_action_implementation"] = NATIVE_A4_IMPLEMENTATION
            repair["a4_action_oracle"] = NATIVE_A4_IMPLEMENTATION
    verification = fallback["formal_release_timing"]["a4_verification"]
    verification.update(
        implementation=NATIVE_A4_IMPLEMENTATION,
        oracle_identity=NATIVE_A4_IMPLEMENTATION,
        selected_action_audit={"apply_count": 263},
        selected_action_apply_count_start=7,
        selected_action_apply_count_end=263,
        candidate_construction_facts={},
    )
    fallback["formal_release_timing"]["native_A4"] = {
        "operator_action": {"apply_count": 263}
    }
    config["solver"]["preconditioner"] = BEST_FINITE_EXHAUSTION_PROFILE
    # The fallback's existing native action history begins at 7. The selected
    # interval still contains exactly the 256 recomputed repair checks.
    fallback_result = check_summary(
        fallback, resolved_config=config, stage="Q4_ORIGINAL"
    )
    assert fallback_result["recomputed"]["bal_h_and_p4"]["passed"] is True
