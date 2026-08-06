from types import SimpleNamespace

import pytest

import benchmarks.run_task033_full3d_watchdog as watchdog


def _e0_args():
    return SimpleNamespace(
        task037_e0_matrix_free_dtn_gate=True,
        task037_m3a_overlap0125_partition=False,
        task037_m4_optimized_schwarz=False,
        task037_m4_factor_free_slab=False,
        task037_m4_p2_auxiliary=False,
        task037_m2c_never_materialized=False,
        mpi_size=1,
        polarization_kind="s",
    )


def _e0_summary(forward_error=1.0e-12):
    audit = {
        "gate_pass": True,
        "n_aux": 80,
        "deterministic_seeds": [17037, 27037, 37037],
        "mode_identity": {
            "count": 80,
            "expected_count": 80,
            "primary_oracle_match": True,
        },
        "source_audits": [
            {"label": "seed_17037"},
            {"label": "seed_27037"},
            {"label": "seed_37037"},
            {"label": "physical_active_rhs"},
        ],
        "forward_action_relative_error_max": forward_error,
        "auxiliary_recovery_relative_error_max": 1.0e-12,
        "physical_rhs_identity_relative_error": 1.0e-13,
        "materialization": {
            "profiles_separate": True,
            "primary": {
                "matrix_free_dtn": True,
                "explicit_c_matrix_count": 0,
                "explicit_d_matrix_count": 0,
            },
            "oracle": {
                "matrix_free_dtn": False,
                "explicit_c_matrix_count": 1,
                "explicit_d_matrix_count": 1,
            },
        },
    }
    return {
        "matrix_stats": {"matrix_rows": 10, "matrix_nnz_used": None},
        "polarization_kind": "s",
        "case_status": "diagnostic_assemble_only",
        "matrix_free_dtn_component_only": True,
        "matrix_free_dtn_probe": True,
        "matrix_free_dtn_probe_audit": audit,
        "ordinary_default_changed": False,
        "matrix_diagnostics_assemble_only": True,
        "postprocess_skipped": True,
        "official_result": False,
        "ksp_iterations": 0,
    }


def test_e0_qualify_checks_independent_capacity_audit():
    qualification = watchdog._qualify(
        args=_e0_args(),
        solver_summary=_e0_summary(),
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=1,
        resource_summary={},
    )
    assert qualification["pass"] is True

    negative = watchdog._qualify(
        args=_e0_args(),
        solver_summary=_e0_summary(forward_error=2.0e-11),
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=1,
        resource_summary={},
    )
    assert negative["pass"] is False
    assert "e0_forward_action_gate" in negative["failures"]


def _e0_cli(*extra):
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
        "2",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        "/tmp/task037-e0-preflight.json",
        "--task035c-p6-preflight-sha256",
        "0" * 64,
        "--verified-clean-sha",
        "0" * 40,
        "--task037-e0-matrix-free-dtn-gate",
        *extra,
    ]


def test_e0_parser_freezes_scope_and_parent_worker_forwards_flag(tmp_path):
    args = watchdog._parse_args(_e0_cli("--worker", "--run-dir", str(tmp_path)))
    assert args.task037_e0_matrix_free_dtn_gate is True
    command = watchdog._worker_command(args, tmp_path)
    assert "--task037-e0-matrix-free-dtn-gate" in command

    with pytest.raises(SystemExit):
        watchdog._parse_args(_e0_cli("--task037-m2c-never-materialized"))
