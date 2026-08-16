from __future__ import annotations

import inspect

import numpy as np

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_m6b_w14_global_b0_inner_pc import (
    W14A_ACTION_SCHEMA,
    evaluate_w14a_action_gate,
)
from src.solvers.persistent_residual_one_vector import measure_rank_one_projection


def _evidence():
    inner_record = {
        "algorithm": "fgmres_right_b0_fixed20",
        "iterations": 20,
        "converged_reason": -3,
        "pc_apply_count_delta": 20,
        "operator_apply_count_delta": 20,
        "finite": True,
        "gate_pass": True,
        "true_residual": 1.0e-3,
        "rhs_sha256": "rhs",
    }
    return {
        "inner_audit": {
            "algorithm": {
                "solver": "fgmres",
                "restart": 20,
                "max_it": 20,
                "zero_start": True,
                "rtol": 0.0,
                "atol": 0.0,
                "pc_side": "right",
                "mpi_size": 1,
            },
            "rows": 2,
            "underlying_pc": {"apply_count": 40},
            "applications": [dict(inner_record), dict(inner_record)],
            "rhs_vec_owned": True,
            "rhs_vec_destroyed": False,
            "wrapper_owned_full_vector_count": 1,
            "wrapper_owned_full_vector_bytes": 32,
            "retained_full_vector_count": 1,
            "retained_full_vector_bytes": 32,
            "application_records_full_vector_count": 0,
            "application_records_full_vector_bytes": 0,
        },
        "z_identity": {
            "finite": True,
            "dtype": "complex128",
            "shape_equal": True,
            "sha256_equal": True,
            "relative_difference": 0.0,
        },
        "p_identity": {
            "finite": True,
            "dtype": "complex128",
            "shape_equal": True,
            "sha256_equal": True,
            "relative_difference": 0.0,
        },
        "measurement": {
            "schema": W14A_ACTION_SCHEMA,
            "finite": True,
            "rho": 0.8,
            "normal_closure": 1.0e-12,
            "projection_orthogonality": 1.0e-12,
            "repeat_exact": True,
            "repeat": {"repeat_exact": True, "passes": 2},
        },
        "p2_measurement": {
            "schema": W14A_ACTION_SCHEMA,
            "finite": True,
            "rho": 0.8,
            "normal_closure": 1.0e-12,
            "projection_orthogonality": 1.0e-12,
        },
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "global_matrix_materialized": False,
            "augmented_matrix_materialized": False,
            "condensation": False,
            "static_condensed_operator_used": False,
            "trace_slab_pc_used": False,
            "slab_factors": 0,
            "shifted_pc_used": False,
            "physical_ksp_used": False,
            "pde_used": False,
            "official_rta": False,
        },
        "predicted_live_set": runner._m6b_w14a_predicted_live_set(),
    }


def _checks(evidence):
    return evaluate_w14a_action_gate(
        inner_audit=evidence["inner_audit"],
        z_identity=evidence["z_identity"],
        p_identity=evidence["p_identity"],
        measurement=evidence["measurement"],
        p2_measurement=evidence["p2_measurement"],
        physical_action_count=2,
        architecture=evidence["architecture"],
        lifecycle_events=[
            "b0_constructed",
            "physical_constructed",
            "coexistence_ready",
            "physical_released",
            "b0_released",
        ],
        predicted_live_set=evidence["predicted_live_set"],
        source_ok=True,
        cache_ok=True,
    )


def test_w14a_gate_passes_fixed_scope_and_prediction():
    evidence = _evidence()
    checks = _checks(evidence)
    assert W14A_ACTION_SCHEMA == runner.M6B_W14A_SCHEMA
    assert all(checks.values())
    scope = runner._m6b_w14a_scope()
    assert scope["residual_role"] == "untouched_W7_cumulative400_full_explicit_residual"
    assert scope["w5_q_used_for_construction"] is False
    assert scope["simultaneous_b0_physical_residency"] is True
    prediction = runner._m6b_w14a_predicted_live_set()
    assert prediction["bytes"] == 1_281_057_286
    assert prediction["components"] == {
        "m5_calibrated_peak_bytes": 1_183_698_944,
        "m6a_work_bytes": 16_673_350,
        "six_full_space_vectors_bytes": 6 * 173_802 * 16,
        "fixed_runtime_reserve_bytes": 64_000_000,
    }
    assert prediction["gate"] is True


def test_w14a_resource_closeout_flags_have_fixed_pass_fail_semantics():
    assert runner._m6b_w14a_resource_closeout_flags(True) == {
        "formal_resource_closeout_unlocked": True,
        "formal_resource_closeout_pending": True,
        "formal_resource_closeout_locked": False,
    }
    assert runner._m6b_w14a_resource_closeout_flags(False) == {
        "formal_resource_closeout_unlocked": False,
        "formal_resource_closeout_pending": False,
        "formal_resource_closeout_locked": True,
    }


def test_w14a_gate_rejects_rho_and_inner_failures():
    evidence = _evidence()
    evidence["measurement"]["rho"] = 0.96
    checks = _checks(evidence)
    assert checks["measurement"] is False
    assert not all(checks.values())

    evidence = _evidence()
    evidence["inner_audit"]["applications"][1]["gate_pass"] = False
    evidence["inner_audit"]["applications"][1]["true_residual"] = 0.2
    checks = _checks(evidence)
    assert checks["inner_residual"] is False
    assert not all(checks.values())


def test_w14a_gate_missing_key_fails_closed_and_lifecycle_is_exact():
    evidence = _evidence()
    del evidence["architecture"]["trace_slab_pc_used"]
    checks = _checks(evidence)
    assert checks["architecture"] is False

    evidence = _evidence()
    checks = evaluate_w14a_action_gate(
        inner_audit=evidence["inner_audit"],
        z_identity=evidence["z_identity"],
        p_identity=evidence["p_identity"],
        measurement=evidence["measurement"],
        p2_measurement=evidence["p2_measurement"],
        physical_action_count=2,
        architecture=evidence["architecture"],
        lifecycle_events=["b0_constructed", "physical_constructed", "b0_released"],
        predicted_live_set=evidence["predicted_live_set"],
        source_ok=True,
        cache_ok=True,
    )
    assert checks["coexistence_lifecycle"] is False


def test_w14a_gate_rejects_negative_nonnegative_measurement_scalar():
    evidence = _evidence()
    evidence["measurement"]["normal_closure"] = -1.0e-12
    assert _checks(evidence)["measurement"] is False


def test_w14a_gate_requires_top_level_fixed_algorithm_and_rhs_bytes():
    evidence = _evidence()
    evidence["inner_audit"]["algorithm"]["max_it"] = 19
    assert _checks(evidence)["inner_algorithm"] is False

    evidence = _evidence()
    evidence["inner_audit"]["retained_full_vector_bytes"] = 0
    assert _checks(evidence)["inner_work_vector"] is False


def test_w14a_parser_and_shared_mode_contract_are_fixed():
    args = runner._parser().parse_args(
        [
            "m6b-w14a-action-diagnostic",
            "--run-dir",
            "run",
            "--w5-compact",
            "w5.json",
            "--w5-raw-dir",
            "w5",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7",
            "--m3y-manifest",
            "m3y.json",
            "--jit-cache-source",
            "physical-jit",
            "--b0-jit-cache-source",
            "b0-jit",
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.command == "m6b-w14a-action-diagnostic"
    source = inspect.getsource(runner._run_m6b_w11a_diagnostic)
    assert 'mode="w14a"' in inspect.getsource(runner._run_m6b_w14a_diagnostic)
    w14_branch = source[source.index("if is_w14a:", source.index("ensure_b0()")):source.index("elif is_w11b:")]
    assert "release_b0()" not in w14_branch
    assert "w14_physical_numpy" in source
    record_start = source.index("def record_b0_stage")
    record_end = source.index("def release_b0")
    assert "w14_pc_context.apply_count" in source[record_start:record_end]
    assert 'p2_measurement["schema"] = M6B_W14A_SCHEMA' in source
    authority_pos = source.index("authorities = _m6b_w11a_load_authorities")
    release_pos = source.index('del authorities["q"]', authority_pos)
    production_pos = source.index("m6a._production_objects", release_pos)
    assert authority_pos < release_pos < production_pos
    assert '"q_vector_retained": False' in source
    assert '"retained_authority_vector_roles": ["target"]' in source
    assert "_m6b_w14a_resource_closeout_flags(diagnostic_pass)" in source
    assert 'payload["resource_closeout_only"]' not in source


def test_w14a_second_projection_uses_existing_signature_and_records_schema():
    assert "schema" not in inspect.signature(measure_rank_one_projection).parameters
    residual = np.array([1.0 + 0.5j, -0.25 + 0.75j])
    direction = np.array([0.5 - 0.25j, 1.0 + 0.0j])
    measurement = measure_rank_one_projection(
        residual, direction, block_size=2
    )
    measurement["schema"] = W14A_ACTION_SCHEMA
    assert measurement["schema"] == W14A_ACTION_SCHEMA
    assert measurement["finite"] is True
