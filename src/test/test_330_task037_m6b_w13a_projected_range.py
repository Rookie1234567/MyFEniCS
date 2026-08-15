from __future__ import annotations

import inspect

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import H2BM6BProjectedRangePC
from src.solvers.hcurl_m6b_w13a_projected_range import (
    W13A_RESIDUAL_ORDER,
    run_w13a_projected_range_measurements,
)


_HASH = "a" * 64


def _measurement(rhs: np.ndarray, *, closure: float = 1.0e-14) -> dict[str, object]:
    return {
        "finite": True,
        "rho_local_only": 0.9,
        "rho_range_only": 0.8,
        "rho_projected": 0.7,
        "linear_action_closure": closure,
        "complement_optimality": closure,
        "alpha": [0.25, -0.5],
        "omega": [0.75, 0.125],
        "projection_denominator": [2.0, 0.0],
        "local_exact_shifted_action_count": 1,
        "action_counts": {
            "local_apply": 1,
            "physical_outer_action": 5,
            "range_apply": 3,
        },
        "rhs_sha256": _HASH,
        "final_correction_sha256": _HASH,
        "final_action_sha256": _HASH,
        "final_residual_sha256": _HASH,
    }


def test_w13a_core_has_one_gate_and_records_fixed_wall_and_action_contract() -> None:
    residuals = {
        "w5_iter200": np.array([1 + 2j, -2 + 0.5j], dtype=np.complex128),
        "w7_cumulative400": np.array([0.5 - 1j, 3 + 0.25j], dtype=np.complex128),
    }
    calls: list[str] = []

    def apply(rhs: np.ndarray):
        calls.append("apply")
        return rhs.copy(), _measurement(rhs)

    result = run_w13a_projected_range_measurements(
        residuals, apply, beta=1.0
    )

    assert result["residual_order"] == list(W13A_RESIDUAL_ORDER)
    assert set(result) == {
        "schema",
        "beta",
        "residual_order",
        "measurements",
        "action_counts",
        "gate",
        "elapsed_wall_seconds",
    }
    assert result["gate"]["pass"] is True
    assert all(result["gate"]["checks"].values())
    assert len(calls) == 4
    assert result["action_counts"] == {
        "local_apply": 4,
        "physical_outer_action": 20,
        "range_apply": 12,
        "local_exact_shifted_action_count": 4,
    }
    assert result["elapsed_wall_seconds"] >= 0.0
    for record in result["measurements"].values():
        assert record["repeat_exact"] is True
        assert record["local_exact_shifted_action_count"] == 1
        assert record["first_apply_wall_seconds"] >= 0.0
        assert record["repeat_apply_wall_seconds"] >= 0.0
        assert record["apply_wall_seconds"] >= 0.0


def test_w13a_core_closure_is_a_gate_and_fixed_beta_order_rejects_scans() -> None:
    residuals = {
        "w5_iter200": np.ones(2, dtype=np.complex128),
        "w7_cumulative400": np.ones(2, dtype=np.complex128),
    }

    def bad_apply(rhs: np.ndarray):
        return rhs.copy(), _measurement(rhs, closure=1.0e-8)

    failed = run_w13a_projected_range_measurements(
        residuals, bad_apply, beta=0.5
    )
    assert failed["gate"]["pass"] is False
    assert failed["gate"]["checks"]["action_closure"] is False
    with pytest.raises(ValueError, match="beta or residual order"):
        run_w13a_projected_range_measurements(residuals, bad_apply, beta=0.25)
    with pytest.raises(ValueError, match="beta or residual order"):
        run_w13a_projected_range_measurements(
            {"w7_cumulative400": residuals["w7_cumulative400"], "w5_iter200": residuals["w5_iter200"]},
            bad_apply,
            beta=0.5,
        )


def test_w13a_scope_prediction_and_parser_are_fixed_without_beta_argument() -> None:
    scope = runner._m6b_w13a_scope()
    prediction = runner._m6b_w13a_predicted_live_set()
    assert scope["betas"] == [1.0, 0.5]
    assert scope["parameter_scan"] is False
    assert scope["old_beta05_bare_pc"] == "frozen_failure_not_reopened"
    expected_prediction = (
        runner.M6B_W2R_BASE_PREDICTED_LIVE_SET_BYTES
        + 2 * runner.M6B_W2R_EXTERNAL_RESIDUAL_BYTES
        + runner.M6B_W2R_PROJECTED_INCREMENTAL_BYTES
    )
    assert expected_prediction == 1_726_081_915
    assert prediction["bytes"] == expected_prediction
    assert prediction["gate"] is True
    assert prediction["derived_not_measured"] is True
    diagnostic_source = inspect.getsource(runner._run_m6b_w13a_diagnostic)
    assert '"beta_wall_seconds"' in diagnostic_source
    assert diagnostic_source.count("_m6b_w13a_predicted_live_set()") == 1
    assert diagnostic_source.index("prediction =") < diagnostic_source.index(
        "w5 = _m6b_w7_s1_load_w5_authority"
    )
    assert '"first_apply_wall_seconds"' in inspect.getsource(
        run_w13a_projected_range_measurements
    )

    args = runner._parser().parse_args(
        [
            "m6b-w13a-diagnostic",
            "--run-dir",
            "/tmp/w13a-run",
            "--factor1-authority-dir",
            "/tmp/beta1",
            "--factor05-authority-dir",
            "/tmp/beta05",
            "--wave-authority-dir",
            "/tmp/wave",
            "--jit-cache-source",
            "/tmp/jit",
            "--w0-authority-file",
            "/tmp/w0.json",
            "--w5-compact",
            "/tmp/w5.json",
            "--w5-raw-dir",
            "/tmp/w5",
            "--w7-compact",
            "/tmp/w7.json",
            "--w7-raw-dir",
            "/tmp/w7",
            "--output",
            "/tmp/w13a.json",
            "--expected-source-sha",
            "a" * 40,
        ]
    )
    assert args.command == "m6b-w13a-diagnostic"
    assert not hasattr(args, "beta")


def test_w13a_keeps_projected_pc_default_behavior_and_no_heavy_dispatch() -> None:
    signature = inspect.signature(H2BM6BProjectedRangePC.__init__)
    assert signature.parameters["record_local_omega"].default is False
    core_source = inspect.getsource(run_w13a_projected_range_measurements)
    assert "dolfinx" not in core_source
    assert "PETSc" not in core_source
    assert "m6b-w13a-diagnostic" not in core_source
