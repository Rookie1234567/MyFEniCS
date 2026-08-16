from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path

import numpy as np
import pytest

from src.solvers.hcurl_m6b_w16_global_shifted_inner_pc import (
    W16A_AUXILIARY_BETA,
    W16A_AUXILIARY_OPERATOR,
    W16A_AUXILIARY_PC,
    W16A_CHECKPOINTS,
    W16A_INNER_SCHEMA,
    W16A_INNER_TRUE_RESIDUAL_LIMIT,
    W16A_MAX_STEPS,
    W16A_PREDICTED_LIVE_SET_BYTES,
    W16A_PREDICTED_LIVE_SET_LIMIT_BYTES,
    W16A_RELATIVE_IDENTITY_LIMIT,
    W16A_RHO_LIMIT,
    W16A_SCHEMA,
    W16A_SCRATCH_PER_RUN_BYTES,
    W16A_SCRATCH_TWO_RUN_TOTAL_BYTES,
    W16A_SCRATCH_IS_DISK_NOT_RSS,
    W16A_VECTOR_BYTES,
    W16A_WATCHDOG_LIMIT_BYTES,
    evaluate_w16a_global_shifted_gate,
    run_w16a_fixed20,
)


def _synthetic_summary() -> dict:
    vector_bytes = W16A_VECTOR_BYTES
    record = {
        "schema": W16A_INNER_SCHEMA,
        "algorithm": "fgmres_right_shifted_beta1_fixed20",
        "iterations": 20,
        "checkpoint_iteration": 20,
        "action_count": 21,
        "pc_apply_count_delta": 20,
        "observer_count": 1,
        "initial_action_count": 0,
        "finite": True,
        "true_residual": 1.0e-3,
        "solution_sha256": "z-hash",
        "rhs_sha256": "rhs-hash",
    }
    return {
        "schema": W16A_SCHEMA,
        "status": "producer_status_is_not_trusted",
        "pass": False,
        "fixed_identity": {
            "operator": W16A_AUXILIARY_OPERATOR,
            "beta": W16A_AUXILIARY_BETA,
            "right_pc": W16A_AUXILIARY_PC,
            "auxiliary_dtn_used": False,
            "projected_range_used": False,
            "b0_used": False,
            "m3y_used": False,
            "range_store_used": False,
        },
        "inner_audits": [{
            "algorithm": "right_flexible_gmres",
            "rows": 173_802,
            "dtype": "complex128",
            "max_steps": 20,
            "iterations": 20,
            "checkpoint_iterations": [20],
            "checkpoint_count": 1,
            "observer_count": 1,
            "action_count": 21,
            "pc_count": 20,
            "initial_action_count": 0,
            "orthogonalization_passes": 2,
            "mmap": False,
            "basis_in_memory": False,
            "scratch_bytes": W16A_SCRATCH_PER_RUN_BYTES,
            "scratch_mmap": False,
            "scratch_basis_in_memory": False,
            "checkpoint_set_complete": True,
            "bounded_full_vector_gate": True,
            "scratch_paths": {
                "v_basis": f"/tmp/w16a-run-{run_index}/v_basis.bin",
                "z_basis": f"/tmp/w16a-run-{run_index}/z_basis.bin",
            },
            "v_basis": {
                "capacity": 21,
                "written_count": 21,
                "write_count": 21,
                "allocated_bytes": 21 * vector_bytes,
                "mmap": False,
            },
            "z_basis": {
                "capacity": 20,
                "written_count": 20,
                "write_count": 20,
                "allocated_bytes": 20 * vector_bytes,
                "mmap": False,
            },
        } for run_index in (1, 2)],
        "inner_records": [
            dict(deepcopy(record), run_index=run_index)
            for run_index in (1, 2)
        ],
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
        "measurements": [
            {
                "schema": W16A_SCHEMA,
                "finite": True,
                "repeat_exact": True,
                "rho": 0.82,
                "normal_closure": 1.0e-12,
                "projection_orthogonality": 1.0e-12,
            },
            {
                "schema": W16A_SCHEMA,
                "finite": True,
                "repeat_exact": True,
                "rho": 0.82,
                "normal_closure": 1.0e-12,
                "projection_orthogonality": 1.0e-12,
            },
        ],
        "action_audit": {
            "global_shifted_action_count": 42,
            "local_pc_apply_count": 40,
            "local_exact_shifted_volume_action_count": 40,
            "shifted_action_total_count": 82,
            "physical_action_count": 2,
            "physical_dtn_action_count": 2,
        },
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "physical_operator": "beta0_volume_plus_matrix_free_dtn80",
            "auxiliary_dtn_used": False,
            "global_matrix_materialized": False,
            "augmented_matrix_materialized": False,
            "condensation": False,
            "static_condensation": False,
            "trace_slab": False,
            "slab_factors": 0,
            "physical_ksp_used": False,
            "pde_used": False,
            "official_rta": False,
        },
        "lifecycle": {
            "events": [
                "auxiliary_constructed",
                "inner_apply_1",
                "inner_apply_2",
                "auxiliary_released",
                "physical_constructed",
                "physical_apply_1",
                "physical_apply_2",
                "physical_released",
            ],
            "auxiliary_physical_overlap": False,
            "release_between_inner_runs": False,
        },
        "prediction": {
            "bytes": W16A_PREDICTED_LIVE_SET_BYTES,
            "limit_bytes": W16A_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "watchdog_limit_bytes": W16A_WATCHDOG_LIMIT_BYTES,
            "derived_not_measured": True,
            "per_run_scratch_bytes": W16A_SCRATCH_PER_RUN_BYTES,
            "two_run_scratch_bytes": W16A_SCRATCH_TWO_RUN_TOTAL_BYTES,
            "scratch_is_disk_not_rss": W16A_SCRATCH_IS_DISK_NOT_RSS,
            "swap_bytes": 0,
        },
    }


def test_w16a_fixed20_wrapper_uses_disk_basis_and_fixed_counts(tmp_path):
    rows = 24
    diagonal = np.asarray(
        [1.2 + 0.07 * index + 0.03j * (index + 1) for index in range(rows)],
        dtype=np.complex128,
    )
    rhs = np.asarray(
        [1.0 + 0.1 * index + 1j * (0.3 - 0.02 * index) for index in range(rows)],
        dtype=np.complex128,
    )

    def action(values):
        return np.asarray(diagonal * values, dtype=np.complex128)

    def pc(values):
        return np.asarray((0.71 - 0.08j) * values, dtype=np.complex128)

    observed = [[], []]
    results = [
        run_w16a_fixed20(
            action,
            pc,
            rhs,
            tmp_path / f"cycle-{run_index}",
            observer=lambda event, events=events: events.append(event["iteration"]),
        )
        for run_index, events in ((1, observed[0]), (2, observed[1]))
    ]

    for result in results:
        assert result.iterations == W16A_MAX_STEPS == 20
        assert result.audit["checkpoint_iterations"] == list(W16A_CHECKPOINTS)
        assert result.audit["action_count"] == 21
        assert result.audit["pc_count"] == 20
        assert result.audit["observer_count"] == 1
        assert result.audit["initial_action_count"] == 0
        assert result.audit["orthogonalization_passes"] == 2
        assert result.audit["mmap"] is False
        assert result.audit["basis_in_memory"] is False
        assert result.audit["checkpoint_set_complete"] is True
        assert Path(result.audit["v_basis"]["path"]).stat().st_size == 21 * rhs.nbytes
        assert Path(result.audit["z_basis"]["path"]).stat().st_size == 20 * rhs.nbytes
        assert result.audit["scratch_bytes"] == 41 * rhs.nbytes
        assert result.solution.dtype == np.dtype(np.complex128)
        assert np.all(np.isfinite(result.solution))
        assert "solution" not in result.audit

    assert observed == [[20], [20]]
    assert np.array_equal(results[0].solution, results[1].solution)
    assert results[0].audit["scratch_paths"] != results[1].audit["scratch_paths"]
    assert results[0].audit["v_basis"]["path"] != results[1].audit["v_basis"]["path"]
    assert results[0].audit["z_basis"]["path"] != results[1].audit["z_basis"]["path"]

    def physical(values):
        return np.asarray(diagonal * values, dtype=np.complex128)

    assert np.array_equal(physical(results[0].solution), physical(results[1].solution))

    signature = inspect.signature(run_w16a_fixed20)
    assert "max_steps" not in signature.parameters
    assert "checkpoints" not in signature.parameters
    assert "initial_solution" not in signature.parameters


def test_w16a_prediction_and_disk_scratch_contract_are_exact():
    assert W16A_VECTOR_BYTES == 173_802 * 16
    assert W16A_SCRATCH_PER_RUN_BYTES == (21 + 20) * W16A_VECTOR_BYTES
    assert W16A_SCRATCH_TWO_RUN_TOTAL_BYTES == 2 * W16A_SCRATCH_PER_RUN_BYTES
    assert W16A_SCRATCH_IS_DISK_NOT_RSS is True
    assert W16A_PREDICTED_LIVE_SET_BYTES <= W16A_PREDICTED_LIVE_SET_LIMIT_BYTES
    assert W16A_PREDICTED_LIVE_SET_BYTES == 1_739_986_075


def test_w16a_evaluator_recomputes_complete_fixed_gate():
    summary = _synthetic_summary()
    report = evaluate_w16a_global_shifted_gate(summary)
    assert report["pass"] is True
    assert all(report["checks"].values())
    assert report["problems"] == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("fixed_identity", "auxiliary_dtn_used"), True),
        (("fixed_identity", "beta"), 0.5),
        (("fixed_identity", "projected_range_used"), True),
        (("action_audit", "global_shifted_action_count"), 41),
        (("inner_records", 0, "true_residual"), W16A_INNER_TRUE_RESIDUAL_LIMIT * 2),
        (("measurements", 0, "rho"), W16A_RHO_LIMIT + 0.01),
        (("z_identity", "relative_difference"), W16A_RELATIVE_IDENTITY_LIMIT * 2),
    ],
)
def test_w16a_evaluator_rejects_wrong_identity_or_numeric_gate(path, value):
    summary = _synthetic_summary()
    target = summary
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    report = evaluate_w16a_global_shifted_gate(summary)
    assert report["pass"] is False
    assert report["problems"]


def test_w16a_evaluator_missing_key_fails_closed():
    summary = _synthetic_summary()
    del summary["inner_audits"][0]["v_basis"]
    report = evaluate_w16a_global_shifted_gate(summary)
    assert report["pass"] is False
    assert report["checks"]["inner_audits"] is False

    summary = _synthetic_summary()
    del summary["inner_audits"][1]
    report = evaluate_w16a_global_shifted_gate(summary)
    assert report["pass"] is False
    assert report["checks"]["inner_audits"] is False

    summary = _synthetic_summary()
    summary["inner_audits"][1]["action_count"] = 20
    report = evaluate_w16a_global_shifted_gate(summary)
    assert report["pass"] is False
    assert report["checks"]["inner_audits"] is False


@pytest.mark.parametrize("tamper", ["second_run_index", "duplicate_scratch_path"])
def test_w16a_evaluator_rejects_non_independent_second_run(tamper):
    summary = _synthetic_summary()
    if tamper == "second_run_index":
        summary["inner_records"][1]["run_index"] = 1
    else:
        summary["inner_audits"][1]["scratch_paths"]["v_basis"] = (
            summary["inner_audits"][0]["scratch_paths"]["v_basis"]
        )
    report = evaluate_w16a_global_shifted_gate(summary)
    assert report["pass"] is False
    assert report["checks"]["inner_records"] is False or report["checks"]["inner_audits"] is False
