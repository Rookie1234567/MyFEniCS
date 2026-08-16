from __future__ import annotations

import copy
import json
from pathlib import Path

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_m6b_w14_global_b0_inner_pc import (
    W14A_ACTION_SCHEMA,
    W15A_RHO1_AUTHORITY,
    W15A_CUMULATIVE_RHO_LIMIT,
    W15A_RHO_LIMIT,
    evaluate_w15a_restart1_gate,
)


def _evidence(local_rho: float = 0.8) -> dict[str, object]:
    record = {
        "algorithm": "fgmres_right_b0_fixed20",
        "iterations": 20,
        "converged_reason": -3,
        "pc_apply_count_delta": 20,
        "operator_apply_count_delta": 3,
        "finite": True,
        "gate_pass": True,
        "true_residual": 1.0e-3,
        "rhs_sha256": "rhs",
    }
    measurement = {
        "schema": W14A_ACTION_SCHEMA,
        "finite": True,
        "rho": local_rho,
        "normal_closure": 0.0,
        "projection_orthogonality": 0.0,
        "repeat_exact": True,
        "repeat": {
            "repeat_exact": True,
            "passes": 2,
        },
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
            "applications": [copy.deepcopy(record), copy.deepcopy(record)],
            "underlying_pc": {"apply_count": 40},
            "rows": 4,
            "rhs_vec_owned": True,
            "rhs_vec_destroyed": False,
            "retained_full_vector_count": 1,
            "retained_full_vector_bytes": 64,
            "wrapper_owned_full_vector_count": 1,
            "wrapper_owned_full_vector_bytes": 64,
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
        "measurement": measurement,
        "p2_measurement": {
            **measurement,
            "repeat": {},
        },
        "cumulative_rho": W15A_RHO1_AUTHORITY * local_rho,
        "physical_action_count": 2,
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
        "lifecycle_events": [
            "b0_constructed",
            "physical_constructed",
            "coexistence_ready",
            "physical_released",
            "b0_released",
        ],
        "predicted_live_set": runner._m6b_w15a_predicted_live_set(),
    }


def _evaluate(evidence: dict[str, object], *, authority: bool = True):
    return evaluate_w15a_restart1_gate(
        **evidence,
        checkpoint_authority_ok=authority,
        source_ok=True,
        cache_ok=True,
    )


def test_w15a_fixed_rank1_gate_passes_with_derived_cumulative_rho():
    report = _evaluate(_evidence())
    assert report["pass"] is True
    assert report["checks"]["checkpoint_authority"] is True
    assert report["checks"]["local_rho"] is True
    assert report["checks"]["cumulative_rho"] is True
    assert _evidence()["cumulative_rho"] <= W15A_CUMULATIVE_RHO_LIMIT


def test_w15a_local_or_cumulative_rho_gate_fails_closed():
    local_fail = _evaluate(_evidence(local_rho=W15A_RHO_LIMIT + 0.01))
    assert local_fail["pass"] is False
    assert local_fail["checks"]["local_rho"] is False

    cumulative_fail = _evidence(local_rho=0.8)
    cumulative_fail["cumulative_rho"] = W15A_CUMULATIVE_RHO_LIMIT + 0.01
    report = _evaluate(cumulative_fail)
    assert report["pass"] is False
    assert report["checks"]["cumulative_rho"] is False


def test_w15a_missing_checkpoint_authority_fails_closed():
    report = _evaluate(_evidence(), authority=False)
    assert report["pass"] is False
    assert report["checks"]["checkpoint_authority"] is False


def test_frozen_w14b_remains_numeric_fail():
    compact = (
        runner.ROOT / runner.M6B_W15A_W14B_COMPACT_RELATIVE_PATH
    )
    record = json.loads(Path(compact).read_text(encoding="utf-8"))
    assert record["classification"] == "W14B_FIXED4_CORRECTION_FAIL"
    assert record["checks"]["worker_action_gate"] is False
    assert record["formal_pass"] is False
    assert record["pde_pass"] is False


def test_w15a_scope_prediction_and_fixed_cli_contract():
    scope = runner._m6b_w15a_scope()
    prediction = runner._m6b_w15a_predicted_live_set()
    assert runner.M6B_W15A_EVENTS == (
        "authority_validated",
        "w14b_checkpoint1_validated",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "b0_ready",
        "inner_pc_ready",
        "physical_action_ready",
        "coexistence_ready",
        "inner_apply_1_ready",
        "inner_apply_2_ready",
        "physical_apply_1_ready",
        "physical_apply_2_ready",
        "measurement_ready",
        "summary_ready",
    )
    assert scope["residual_role"] == "frozen_W14B_fixed4_checkpoint1_residual"
    assert scope["w5_q_used_for_construction"] is False
    assert scope["parameter_scan"] is False
    assert prediction["bytes"] == 1_281_057_286
    assert prediction["derived_not_measured"] is True
    parsed = runner._parser().parse_args(
        [
            "m6b-w15a-restarted-rank1-diagnostic",
            "--run-dir", "run",
            "--w5-compact", "w5.json",
            "--w5-raw-dir", "w5",
            "--w7-compact", "w7.json",
            "--w7-raw-dir", "w7",
            "--m3y-manifest", "m3y.json",
            "--jit-cache-source", "physical-jit",
            "--b0-jit-cache-source", "b0-jit",
            "--w14b-compact", "w14b.json",
            "--w14b-raw-dir", "w14b-raw",
            "--expected-source-sha", "b31512756937eb9f4a7bfd97c2999eedbb479827",
        ]
    )
    assert parsed.command == "m6b-w15a-restarted-rank1-diagnostic"
    assert parsed.w14b_compact == "w14b.json"
    assert parsed.w14b_raw_dir == "w14b-raw"
