from __future__ import annotations

import copy

import numpy as np

from benchmarks import run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import M6BScreenCheckpointWriter

from src.solvers.hcurl_m6b_w14_global_b0_inner_pc import (
    W14B_CHECKPOINTS,
    W14B_PREDICTED_LIVE_SET_BYTES,
    W14B_PREDICTED_LIVE_SET_LIMIT_BYTES,
    W14B_RHO1_ANCHOR,
    evaluate_w14b_fixed4_gate,
    run_w14b_fixed4_cycle,
)


def _inner_audit() -> dict[str, object]:
    record = {
        "algorithm": "fgmres_right_b0_fixed20",
        "iterations": 20,
        "converged_reason": -3,
        "pc_apply_count_delta": 20,
        "finite": True,
        "gate_pass": True,
        "true_residual": 1.0e-3,
    }
    return {
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
        "applications": [copy.deepcopy(record) for _ in range(4)],
        "underlying_pc": {"apply_count": 80},
    }


def _evidence() -> dict[str, object]:
    inner = _inner_audit()
    return {
        "outer_audit": {
            "algorithm": "right_flexible_gmres",
            "max_steps": 4,
            "iterations": 4,
            "checkpoint_iterations": [1, 2, 4],
            "checkpoint_count": 3,
            "checkpoint_set_complete": True,
            "observer_count": 3,
            "action_count": 7,
            "pc_count": 4,
            "initial_action_count": 0,
            "orthogonalization_passes": 2,
            "basis_in_memory": False,
            "mmap": False,
            "scratch_bytes": 25_027_488,
            "scratch_mmap": False,
            "scratch_basis_in_memory": False,
            "bounded_full_vector_bytes": 32 * 1024 * 1024,
            "bounded_full_vector_gate": True,
        },
        "inner_audit": inner,
        "samples": {
            "1": {
                "iteration": 1,
                "true_relative_residual": W14B_RHO1_ANCHOR,
                "finite": True,
            },
            "2": {
                "iteration": 2,
                "true_relative_residual": 0.8,
                "finite": True,
            },
            "4": {
                "iteration": 4,
                "true_relative_residual": 0.7,
                "finite": True,
            },
        },
        "action_audit": {
            "outer": {
                "apply_count": 0,
            },
            "physical": {
                "apply_count": 0,
            },
            "dtn": {
                "apply_count": 0,
            },
            "bridge": {
                "forward_apply_count": 0,
            },
            "b0_instances": [
                {
                    "total_pc_apply_count": 80,
                    "inner_pc": {"underlying_pc": {"apply_count": 80}},
                }
            ],
            "physical_instances": [
                {
                    "total_physical_action_count": 7,
                    "physical": {
                        "apply_count": 7,
                        "global_matrix_materialized": False,
                        "global_constraint_matrix_materialized": False,
                        "global_condensed_schur_materialized": False,
                        "cell_schur_matrix_materialized": False,
                        "slab_matrix_materialized": False,
                        "retained_dense_cell_tensor_count": 0,
                        "dense_cell_tensor_materialized_per_apply": False,
                        "factor_count": 0,
                        "ksp_created": False,
                        "cell_schur_matrix_nnz": 0,
                        "slab_matrix_nnz": 0,
                        "explicit_C_materialized_count": 0,
                        "explicit_D_materialized_count": 0,
                        "ordinary_default_changed": False,
                    },
                    "outer": {
                        "apply_count": 7,
                        "matrix_type": "python_action_only",
                        "global_matrix": False,
                        "augmented_matrix": False,
                        "static_condensation": False,
                        "trace_slab": False,
                        "explicit_C_materialized_count": 0,
                        "explicit_D_materialized_count": 0,
                    },
                    "dtn": {
                        "apply_count": 7,
                        "mode_count": 80,
                        "fine_space": "uncondensed_fullspace",
                        "condensation": False,
                        "static_condensed_operator_used": False,
                        "trace_slab_pc_used": False,
                        "global_matrix_materialized": False,
                        "augmented_matrix_materialized": False,
                        "explicit_C_materialized_count": 0,
                        "explicit_D_materialized_count": 0,
                        "fe_sized_allgather": False,
                        "modal_allreduce_count_per_apply": 1,
                        "modal_allreduce_count_per_hermitian_apply": 1,
                    },
                    "bridge": {
                        "forward_apply_count": 7,
                        "vector_create_count": 2,
                        "fixed_work_vectors": 2,
                        "per_apply_vec_creation": 0,
                    },
                }
            ],
            "authority_vector_retention": {
                "q_vector_retained": False,
                "retained_authority_vector_roles": ["target"],
            },
            "lifecycle_events": [
                "b0_constructed",
                "physical_constructed",
                "coexistence_ready",
                "physical_released",
                "b0_released",
            ],
            "coexistence": {
                "b0_live": True,
                "physical_live": True,
                "release_between_operations": False,
            },
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
        "predicted_live_set": {
            "bytes": W14B_PREDICTED_LIVE_SET_BYTES,
            "limit_bytes": W14B_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "gate": True,
            "derived_not_measured": True,
            "scratch_bytes": 25_027_488,
        },
    }


def _gate(evidence: dict[str, object]) -> dict[str, object]:
    return evaluate_w14b_fixed4_gate(
        outer_audit=evidence["outer_audit"],
        inner_audit=evidence["inner_audit"],
        samples=evidence["samples"],
        action_audit=evidence["action_audit"],
        architecture=evidence["architecture"],
        predicted_live_set=evidence["predicted_live_set"],
        w14a_authority_ok=True,
        source_ok=True,
        cache_ok=True,
    )


def test_w14b_fixed4_helper_keeps_fixed_disk_cycle_and_counts(tmp_path):
    diagonal = np.asarray(
        [1.0 + 0.1j, 1.5 - 0.2j, 2.0 + 0.3j, 2.5 - 0.1j, 3.0 + 0.2j, 3.5 - 0.4j],
        dtype=np.complex128,
    )
    rhs = np.asarray(
        [1.0 - 0.5j, -0.25 + 0.75j, 0.5 + 0.25j, 0.2j, -0.8 + 0.1j, 0.4 - 0.3j],
        dtype=np.complex128,
    )
    seen: list[int] = []
    result = run_w14b_fixed4_cycle(
        rhs,
        action=lambda values: diagonal * values,
        pc=lambda values: values,
        scratch_dir=tmp_path / "scratch",
        observer=lambda event: seen.append(event["iteration"]),
    )
    audit = result.audit
    assert result.solution.dtype == np.dtype(np.complex128)
    assert result.iterations == 4
    expected_residual = rhs - diagonal * result.solution
    expected_relative = np.linalg.norm(expected_residual) / np.linalg.norm(rhs)
    assert result.final_relative_residual == expected_relative
    assert tuple(seen) == W14B_CHECKPOINTS
    assert audit["checkpoint_iterations"] == [1, 2, 4]
    assert audit["checkpoint_count"] == 3
    assert audit["observer_count"] == 3
    assert audit["action_count"] == 7
    assert audit["pc_count"] == 4
    assert audit["initial_action_count"] == 0
    assert audit["orthogonalization_passes"] == 2
    assert audit["basis_in_memory"] is False
    assert audit["mmap"] is False


def test_w14b_gate_passes_anchor_rho4_and_counts():
    evidence = _evidence()
    result = _gate(evidence)
    assert result["pass"] is True
    assert all(result["checks"].values())
    assert result["rho"] == {"1": W14B_RHO1_ANCHOR, "2": 0.8, "4": 0.7}
    assert evidence["outer_audit"]["action_count"] == 7
    assert evidence["inner_audit"]["underlying_pc"]["apply_count"] == 80


def test_w14b_gate_rejects_anchor_or_rho4_failure():
    evidence = _evidence()
    evidence["samples"]["1"]["true_relative_residual"] += 2.0e-12
    result = _gate(evidence)
    assert result["checks"]["rho1_anchor"] is False
    assert result["pass"] is False

    evidence = _evidence()
    evidence["samples"]["4"]["true_relative_residual"] = 0.75 + 1.0e-12
    result = _gate(evidence)
    assert result["checks"]["rho4"] is False
    assert result["pass"] is False


def test_w14b_gate_missing_key_and_architecture_tamper_fail_closed():
    evidence = _evidence()
    del evidence["samples"]["2"]
    result = _gate(evidence)
    assert result["pass"] is False
    assert result["checks"]["checkpoints"] is False

    evidence = _evidence()
    evidence["architecture"]["trace_slab_pc_used"] = True
    result = _gate(evidence)
    assert result["pass"] is False
    assert result["checks"]["architecture"] is False


def test_w14b_gate_rejects_count_and_scratch_tamper():
    evidence = _evidence()
    evidence["action_audit"]["physical_instances"][0]["outer"]["apply_count"] = 6
    result = _gate(evidence)
    assert result["pass"] is False
    assert result["checks"]["action_audit"] is False

    evidence = _evidence()
    evidence["outer_audit"]["scratch_bytes"] -= 1
    result = _gate(evidence)
    assert result["pass"] is False
    assert result["checks"]["outer"] is False


def test_w14b_writer_default_and_fixed4_iterations(tmp_path):
    values = np.asarray([1.0 + 0.5j, -2.0 + 0.25j], dtype=np.complex128)
    default_writer = M6BScreenCheckpointWriter(tmp_path / "default")
    assert default_writer._allowed_iterations == (20, 100, 150, 200)
    default_record = default_writer.write_numpy_checkpoint(
        20,
        solution=values,
        outer_action=values,
        residual=values,
        rhs=values,
    )
    assert default_record["iteration"] == 20

    fixed_writer = M6BScreenCheckpointWriter(
        tmp_path / "fixed4", allowed_iterations=(1, 2, 4)
    )
    assert fixed_writer._allowed_iterations == (1, 2, 4)
    fixed_record = fixed_writer.write_numpy_checkpoint(
        1,
        solution=values,
        outer_action=values,
        residual=values,
        rhs=values,
    )
    assert fixed_record["iteration"] == 1
    with np.testing.assert_raises(ValueError):
        fixed_writer.write_numpy_checkpoint(
            20,
            solution=values,
            outer_action=values,
            residual=values,
            rhs=values,
        )


def test_w14b_w14a_compact_authority_and_tamper(monkeypatch):
    authority = runner._m6b_w14b_w14a_compact_authority(
        runner.ROOT / runner.M6B_W14B_W14A_COMPACT_RELATIVE_PATH
    )
    assert authority["formal_pass"] is True
    assert authority["anchor_rho"] == W14B_RHO1_ANCHOR
    assert authority["inner_pc_apply_count"] == 40
    assert authority["physical_action_count"] == 2

    monkeypatch.setattr(
        runner, "M6B_W14B_W14A_COMPACT_FILE_SHA256", "0" * 64
    )
    with np.testing.assert_raises(ValueError):
        runner._m6b_w14b_w14a_compact_authority(
            runner.ROOT / runner.M6B_W14B_W14A_COMPACT_RELATIVE_PATH
        )


def test_w14b_scope_prediction_and_fixed_markers():
    assert runner.M6B_W14B_EVENTS == (
        "authority_validated",
        "w14a_unlocked",
        "mesh_ready",
        "space_ready",
        "floquet_mpc_ready",
        "cache_ready",
        "b0_ready",
        "inner_pc_ready",
        "physical_action_ready",
        "coexistence_ready",
        "outer_checkpoint_1_ready",
        "outer_checkpoint_2_ready",
        "outer_checkpoint_4_ready",
        "measurement_ready",
        "summary_ready",
    )
    scope = runner._m6b_w14b_scope()
    prediction = runner._m6b_w14b_predicted_live_set()
    assert scope["equation"] == "A_physical delta = r_W7_cumulative400"
    assert scope["w5_q_used_for_construction"] is False
    assert prediction["bytes"] == 1_348_166_150
    assert prediction["components"]["w14a_predicted_live_set_bytes"] + prediction[
        "components"
    ]["existing_disk_core_increment_bytes"] == prediction["bytes"]
    assert prediction["components"]["scratch_bytes_not_rss"] == 25_027_488


def test_w14b_parser_and_main_dispatch(monkeypatch):
    captured = {}

    def fake_worker(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return 17

    monkeypatch.setattr(runner, "_run_m6b_w14b_diagnostic", fake_worker)
    args = [
        "m6b-w14b-correction-diagnostic",
        "--run-dir", "run",
        "--w5-compact", "w5.json",
        "--w5-raw-dir", "w5raw",
        "--w7-compact", "w7.json",
        "--w7-raw-dir", "w7raw",
        "--m3y-manifest", "m3y.json",
        "--jit-cache-source", "jit",
        "--b0-jit-cache-source", "b0jit",
        "--w14a-compact", "w14a.json",
        "--expected-source-sha", "a" * 40,
    ]
    assert runner.main(args) == 17
    assert captured["args"][-2].name == "w14a.json"
    assert captured["args"][-1] == "a" * 40
    parsed = runner._parser().parse_args(args)
    assert parsed.w14a_compact == "w14a.json"


def test_w14b_finalization_flattens_gate_checks_only():
    report = {
        "pass": True,
        "checks": {"outer": True, "rho4": True},
        "problems": [],
        "rho": {"1": W14B_RHO1_ANCHOR, "4": 0.7},
    }
    checks = runner._m6b_w14b_merge_gate_checks(
        report, execution_ok=True, lifecycle_ok=True
    )
    assert checks == {
        "outer": True,
        "rho4": True,
        "execution": True,
        "lifecycle": True,
    }
    assert "pass" not in checks
    assert "problems" not in checks
    assert "rho" not in checks
    assert all(checks.values())

    failed = runner._m6b_w14b_merge_gate_checks(
        {**report, "checks": {"outer": False, "rho4": True}},
        execution_ok=True,
        lifecycle_ok=True,
    )
    assert failed["outer"] is False
    assert failed["rho4"] is True
    assert failed["execution"] is True
    assert failed["lifecycle"] is True

    malformed = runner._m6b_w14b_merge_gate_checks(
        {"pass": True}, execution_ok=True, lifecycle_ok=True
    )
    assert malformed == {
        "gate_report": False,
        "execution": True,
        "lifecycle": True,
    }
