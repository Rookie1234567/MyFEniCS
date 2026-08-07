from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from benchmarks import run_task033_full3d_watchdog as watchdog


def _common():
    return {
        "process_completed": True,
        "not_terminated_for_memory": True,
        "not_terminated_for_timeout": True,
        "live_authority_readable": True,
        "all_expected_mpi_ranks_observed": True,
        "exact_positive_rows": True,
        "exact_positive_assembled_nnz": True,
        "polarization_identity": True,
    }


def _e0_summary():
    return {
        "case_status": "diagnostic_assemble_only",
        "matrix_free_dtn_probe": True,
        "ordinary_default_changed": False,
        "matrix_diagnostics_assemble_only": True,
        "matrix_free_dtn_component_only": True,
        "global_A_materialized": False,
        "global_F_materialized": False,
        "ksp_iterations": 0,
        "official_result": False,
        "postprocess_skipped": True,
        "matrix_free_dtn_probe_audit": {
            "gate_pass": True,
            "n_aux": 80,
            "mode_identity": {
                "count": 80,
                "expected_count": 80,
                "primary_oracle_match": True,
            },
            "deterministic_seeds": [17037, 27037, 37037],
            "source_audits": [
                {"label": "seed_17037"},
                {"label": "seed_27037"},
                {"label": "seed_37037"},
                {"label": "physical_active_rhs"},
            ],
            "forward_action_relative_error_max": 0.0,
            "auxiliary_recovery_relative_error_max": 0.0,
            "physical_rhs_identity_relative_error": 0.0,
            "materialization": {
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
                "profiles_separate": True,
            },
        },
    }


def _m3a_fixture(tmp_path):
    active = tmp_path / "active.json"
    full = tmp_path / "full.json"
    active.write_text("active\n", encoding="utf-8")
    full.write_text("full\n", encoding="utf-8")

    def role(path: Path):
        return {
            "manifest": str(path),
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    summary = {
        "external_linear_solver_port": True,
        "external_solver_profile": "never_materialized_owner_local_overlap0125_partition",
        "global_A_materialized": False,
        "global_F_materialized": False,
        "external_reported_relative_residual": 1.0e-7,
        "external_condensed_true_residual": 2.0e-7,
        "external_full_augmented_true_residual": 3.0e-7,
        "linear_system_relative_residual": 4.0e-7,
        "case_status": "completed",
        "ksp_converged": True,
        "postprocess_skipped": False,
        "external_rta_gate_pass": True,
        "official_result": True,
        "stage4_energy_balance_pass": True,
        "A_volume_total": 0.1,
        "energy_closure_error_port_volume": 0.0,
        "R_total": 0.2,
        "T_total": 0.7,
        "A_balance": 0.1,
        "R_plus_T": 0.9,
        "task037_m3a_canonical_export": {
            "roles": {"active_trace": role(active), "full_fe": role(full)}
        },
    }
    audit = {
        "candidate": {
            "outer_ksp": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 90,
            "rtol": 1.0e-6,
            "atol": 0.0,
            "max_it": 3000,
            "num_slabs": 16,
            "overlap_fraction": 0.125,
            "interpolation": "partition",
            "absorption_shift": 0.1,
        },
        "final": {
            "reported_relative_residual": 1.0e-7,
            "condensed_true_residual": 2.0e-7,
            "full_augmented_true_residual": 3.0e-7,
        },
        "coarse": {"dimension": 75},
        "partition_audit": {"partition_weight_sum_error": 0.0},
        "smoother_diagnostics": {
            "assembly_order": "two_color",
            "local_ksp_type": "gmres",
            "local_ksp_iterations": 1,
            "smoother_ksp_type": "gmres",
            "smoother_iterations": 2,
            "factor_only_storage": True,
            "local_solver_types": ["ilu", "ilu"],
        },
        "no_global_factor_inventory": {
            "global_direct_factor_count": 0,
            "global_schur_matrix_materialized": False,
        },
    }
    return summary, audit


def test_e0_qualification_positive_and_probe_threshold_negative():
    positive = watchdog._task037_e0_qualification(
        solver_summary=_e0_summary(), events=[], common=_common(), no_swap=True
    )
    assert positive["pass"] is True

    negative_summary = _e0_summary()
    negative_summary["matrix_free_dtn_probe"] = False
    negative = watchdog._task037_e0_qualification(
        solver_summary=negative_summary, events=[], common=_common(), no_swap=True
    )
    assert negative["pass"] is False
    assert "matrix_free_dtn_probe" in negative["failures"]


def test_m3a_qualification_positive_and_residual_threshold_negative(tmp_path):
    summary, audit = _m3a_fixture(tmp_path)
    positive = watchdog._task037_m3a_qualification(
        solver_summary=summary, core_audit=audit, common=_common(), no_swap=True
    )
    assert positive["pass"] is True

    negative_summary = dict(summary)
    negative_summary["external_full_augmented_true_residual"] = 2.0e-6
    negative = watchdog._task037_m3a_qualification(
        solver_summary=negative_summary,
        core_audit=audit,
        common=_common(),
        no_swap=True,
    )
    assert negative["pass"] is False
    assert "core_final_residuals" in negative["failures"]


def _p6_args(tmp_path, mpi_size, flag):
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
        str(mpi_size),
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
        "1" * 40,
        flag,
    ]


def test_m0_parser_scope_and_worker_command_are_lane_specific(tmp_path):
    for mpi_size in (1, 2, 4):
        args = watchdog._parse_args(
            _p6_args(tmp_path, mpi_size, "--task037-e0-matrix-free-dtn-gate")
        )
        assert args.degree == 6
        assert args.h_nm == 10.0
        assert args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
        command = watchdog._worker_command(args, tmp_path)
        assert command.count("--task037-e0-matrix-free-dtn-gate") == 1
        assert "--task037-m3a-overlap0125-partition" not in command

    for mpi_size in (1, 2, 4, 8):
        args = watchdog._parse_args(
            _p6_args(tmp_path, mpi_size, "--task037-m3a-overlap0125-partition")
        )
        assert args.degree == 6
        assert args.h_nm == 10.0
        assert args.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
        command = watchdog._worker_command(args, tmp_path)
        assert command.count("--task037-m3a-overlap0125-partition") == 1
        assert "--task037-e0-matrix-free-dtn-gate" not in command

    with pytest.raises(SystemExit):
        watchdog._parse_args(_p6_args(tmp_path, 8, "--task037-e0-matrix-free-dtn-gate"))
