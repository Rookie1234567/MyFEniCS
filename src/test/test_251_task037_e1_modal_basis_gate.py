import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

import benchmarks.run_task033_full3d_watchdog as watchdog
from src.solvers.static_modal_coarse_gate import (
    OwnerLocalBasis,
    load_owner_local_basis_shard,
    qualify_e1_modal_basis_audit,
    save_owner_local_basis_shard,
)


def _e1_args():
    return SimpleNamespace(
        task037_e1_modal_basis_gate=True,
        task037_e0_matrix_free_dtn_gate=False,
        task037_f0_vector_observer=False,
        task037_canonical_vector_export=False,
        task037_f1_direct_trace_oracle=None,
        task037_f3_screen=None,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=False,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_optimized_schwarz=False,
        mpi_size=8,
        polarization_kind="s",
    )


def _e1_summary(**overrides):
    audit = {
        "research_only": True,
        "ordinary_default_changed": False,
        "implementation_gate_pass": True,
        "gate_pass": True,
        "n_aux": 80,
        "column_count": 240,
        "forward_column_count": 120,
        "backward_column_count": 120,
        "global_active_rows": 51192,
        "finite_nonzero_columns": True,
        "missing": 0,
        "extra": 0,
        "duplicate": 0,
        "max_repeat_error": 1.0e-13,
        "random_action_relative_error": 1.0e-13,
        "max_bottom_retained_residual": 1.0e-13,
        "max_top_retained_residual": 1.0e-13,
        "max_local_interface_mismatch": 1.0e-13,
        "max_stitch_interface_mismatch": 1.0e-13,
        "factors_released": True,
        "official_result": False,
        "ksp_iterations": 0,
        "column_audit_summary": {
            "first_pass_column_count": 240,
            "second_pass_column_count": 240,
            "all_columns_recreated": True,
        },
        "action_space": {
            "effective_rank": 200,
            "normal_equations_used": False,
        },
        "materialization": {
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
        "factor_inventory": {
            "bottom": {"setup_count": 1},
            "top": {"setup_count": 1},
        },
    }
    audit.update(overrides.pop("audit", {}))
    summary = {
        "matrix_stats": {
            "matrix_rows": 51192,
            "matrix_nnz_used": None,
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_solver_profile": "task037_e1_component_only",
        "official_result": False,
        "ksp_iterations": 0,
    }
    summary.update(overrides)
    return summary, audit


def test_research_only_shard_manifest_round_trip(tmp_path):
    values = np.asarray(
        [[1.0 + 2.0j, 0.0], [0.5 - 1.0j, 3.0 + 0.25j]],
        dtype=np.complex128,
    )
    with pytest.raises(ValueError, match="research-only"):
        OwnerLocalBasis.from_local_array(
            values,
            global_rows=2,
            comm=MPI.COMM_SELF,
            label="Z",
        )
    basis = OwnerLocalBasis.from_local_array(
        values,
        global_rows=2,
        comm=MPI.COMM_SELF,
        label="Z",
        research_opt_in=True,
    )
    try:
        manifest = save_owner_local_basis_shard(
            basis,
            tmp_path,
            source_sha="a" * 40,
            prefix="Z",
            research_opt_in=True,
        )
        assert manifest["owner_local"] is True
        assert manifest["replicated_global_basis"] is False
        shard = manifest["shards"][0]
        loaded = load_owner_local_basis_shard(
            shard["path"],
            expected_sha256=shard["sha256"],
        )
        np.testing.assert_array_equal(loaded["local_values"], values)
        assert loaded["source_sha"] == "a" * 40
        assert loaded["sha256"] == shard["sha256"]
    finally:
        basis.destroy()


def test_e1_checker_positive_and_failure_classifications():
    args = _e1_args()
    summary, audit = _e1_summary()
    positive = watchdog._qualify(
        args=args,
        solver_summary=summary,
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=8,
        resource_summary={},
        task037_e1_audit=audit,
    )
    assert positive["pass"] is True
    assert positive["e1_checker_classification"] == (
        "M120_GLOBAL_MODAL_BASIS_GATE_PASSED"
    )

    _, collapsed_audit = _e1_summary(
        audit={"action_space": {"effective_rank": 179, "normal_equations_used": False}}
    )
    collapsed = watchdog._qualify(
        args=args,
        solver_summary=summary,
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=8,
        resource_summary={},
        task037_e1_audit=collapsed_audit,
    )
    assert collapsed["pass"] is False
    assert collapsed["e1_checker_classification"] == (
        "M120_GLOBAL_ACTION_BASIS_COLLAPSED"
    )

    for overrides, expected_failure in (
        ({"action_space": {}}, "rank_gate"),
        ({"max_repeat_error": 2.0e-12}, "repeat_gate"),
        ({"random_action_relative_error": 2.0e-11}, "action_gate"),
        ({"max_top_retained_residual": 2.0e-10}, "interface_gate"),
    ):
        _, negative_audit = _e1_summary(audit=overrides)
        negative = watchdog._qualify(
            args=args,
            solver_summary=summary,
            events=[],
            return_code=0,
            terminated_for_memory=False,
            terminated_for_timeout=False,
            terminated_for_authority_unreadable=False,
            no_swap=True,
            observed_worker_rank_count=8,
            resource_summary={},
            task037_e1_audit=negative_audit,
        )
        assert negative["pass"] is False
        assert expected_failure in negative["e1_checker"]["failures"]
        assert negative["e1_checker_classification"] == (
            "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
        )

    _, missing_action_audit = _e1_summary(audit={"action_space": None})
    missing_action = qualify_e1_modal_basis_audit(
        missing_action_audit,
        solver_summary=summary,
        return_code=0,
        no_swap=True,
    )
    assert missing_action["classification"] == (
        "M120_GLOBAL_MODAL_BASIS_IMPLEMENTATION_FAILED"
    )


def _e1_cli(*extra, tmp_path):
    return [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        str(tmp_path / "authority.json"),
        "--task035c-p6-preflight-sha256",
        "0" * 64,
        "--verified-clean-sha",
        "0" * 40,
        "--task037-e1-modal-basis-gate",
        *extra,
    ]


def test_e1_parser_forwarding_and_source_wiring(tmp_path):
    args = watchdog._parse_args(
        _e1_cli("--worker", "--run-dir", str(tmp_path), tmp_path=tmp_path)
    )
    assert args.task037_e1_modal_basis_gate is True
    command = watchdog._worker_command(args, tmp_path)
    assert "--task037-e1-modal-basis-gate" in command
    assert "--task037-e0-matrix-free-dtn-gate" not in command

    with pytest.raises(SystemExit):
        watchdog._parse_args(
            _e1_cli("--task037-e0-matrix-free-dtn-gate", tmp_path=tmp_path)
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(_e1_cli("--task037-f3-full", tmp_path=tmp_path))

    source = inspect.getsource(watchdog._worker)
    assert "run_e1_modal_basis_gate" in source
    assert "Stage4NeverMaterializedLinearSolverPort(e1_callback)" in source
    assert "matrix_free_dtn=e0_gate or e1_gate" in source
    assert "matrix_free_dtn_probe=e0_gate" in source
    assert "static_retain_local_schur_for_matrix_free=(" in source
    assert "task037_e1_modal_basis_generation" in source
