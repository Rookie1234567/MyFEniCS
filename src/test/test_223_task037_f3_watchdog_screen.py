import json
from types import SimpleNamespace

import pytest

from benchmarks import run_task033_full3d_watchdog as watchdog


def _audit(screen_iterations=20):
    middle_iteration = 10 if screen_iterations == 20 else screen_iterations - 40
    return {
        "candidate": {
            "outer_ksp": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 90,
            "rtol": 1.0e-6,
            "atol": 0.0,
            "max_it": screen_iterations,
            "num_slabs": 16,
            "overlap_fraction": 0.25,
            "absorption_shift": 0.1,
        },
        "reported_history": [
            [0, 1.0],
            [middle_iteration, 0.5],
            [screen_iterations, 0.1],
        ],
        "condensed_true_samples": [
            [0, 1.0],
            [middle_iteration, 0.5],
            [screen_iterations, 0.1],
        ],
        "final": {
            "converged_reason": -3,
            "iterations": screen_iterations,
            "reported_relative_residual": 0.1,
            "condensed_true_residual": 0.1,
            "full_augmented_true_residual": 0.1,
        },
        "operator_apply_count": 1,
        "coarse": {"dimension": 75, "apply_count": 1},
        "smoother_diagnostics": {
            "one_level_apply_count": 1,
            "factor_only_storage": True,
            "local_solver_types": ["ilu"],
        },
        "partition_audit": {"coverage_pass": True},
        "no_global_factor_inventory": {
            "global_direct_factor_count": 0,
            "global_schur_matrix_materialized": False,
        },
    }


def _m4_audit(screen_iterations=20):
    audit = _audit(screen_iterations)
    audit.update(
        {
            "candidate": {
                "outer_ksp": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": screen_iterations,
                "p6_smoothing": "not_used",
                "p2_auxiliary_correction": True,
                "p2_absorption_shift": 0.1,
                "p2_diagonal_patch_omega": 0.6,
                "wave_coarse_post_smooth": False,
            },
            "solver_profile": "never_materialized_p2_auxiliary",
            "assembled_matrix_released_before_solve": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "smoother_diagnostics": {
                "p2_factor_count": 1,
                "p2_factor_solver_type": "mumps",
                "p2_matrix_materialized": True,
                "p2_unshifted_matrix_retained": False,
                "apply_count": 1,
            },
            "partition_audit": {
                "p6_slab_matrix_materialized": False,
                "p6_slab_matrix_count": 0,
                "p6_factor_count": 0,
            },
            "no_global_factor_inventory": {
                "full_p6_global_direct_factor_count": 0,
                "global_schur_matrix_materialized": False,
                "p2_distributed_mumps_factor_count": 1,
                "wave_coarse_dense_lu_count": 1,
            },
            "p2_auxiliary_audit": {"p2": {"active_rows": 1}},
        }
    )
    return audit


def _m4_factor_free_audit(
    screen_iterations=20, *, optimized_schwarz=False, local_krylov_steps=2
):
    audit = _audit(screen_iterations)
    patch = {
        "profile": "factor_free_local_slab_krylov",
        "num_slabs": 16,
        "partition_weighted_additive_schwarz": True,
        "local_krylov_steps": local_krylov_steps,
        "local_inner_preconditioner": "none",
        "outer_requires_fgmres": True,
        "partition_weight_sum_error": 0.0,
        "partition_weight_min": 0.5,
        "partition_weight_max": 1.0,
        "p6_slab_matrix_materialized": False,
        "p6_slab_matrix_count": 0,
        "p6_factor_count": 0,
        "p6_factor_nnz": 0,
        "global_A_materialized_by_pc": False,
        "apply_count": 2,
        "restricted_action_calls": local_krylov_steps * 16 * 2,
        "expected_action_calls": local_krylov_steps * 16 * 2,
    }
    audit.update(
        {
            "solver_profile": "never_materialized_p2_factor_free_slab_auxiliary",
            "assembled_matrix_released_before_solve": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "candidate": {
                "outer_ksp": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "max_it": screen_iterations,
                "num_slabs": 16,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "local_krylov_steps": local_krylov_steps,
                "local_inner_preconditioner": "none",
                "outer_requires_fgmres": True,
                "p2_auxiliary_correction": True,
                "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
                "fine_schur_action_kind": ("borrowed_p6_static_local_schur_action"),
                "wave_coarse_post_smooth": False,
            },
            "p2_auxiliary_audit": {
                "profile": "never_materialized_p2_factor_free_slab_auxiliary",
                "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
                "fine_schur_action_kind": "borrowed_p6_static_local_schur_action",
            },
            "smoother_diagnostics": {
                "profile": "never_materialized_p2_factor_free_slab_auxiliary",
                "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
                "global_p6_matrix_materialized": False,
                "global_p6_transfer_materialized": False,
                "p2_factor_count": 1,
                "p2_factor_solver_type": "mumps",
                "p2_matrix_materialized": True,
                "p2_unshifted_matrix_retained": False,
                "apply_count": 1,
                "factor_free_slab_patch": patch,
            },
            "partition_audit": {
                "p6_slab_matrix_materialized": False,
                "p6_slab_matrix_count": 0,
                "p6_factor_count": 0,
                "p6_factor_nnz": 0,
                "num_slabs": 16,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "local_krylov_steps": local_krylov_steps,
                "local_inner_preconditioner": "none",
                "outer_requires_fgmres": True,
                "global_A_materialized_by_pc": False,
                "partition_weight_sum_error": 0.0,
                "partition_weight_min": 0.5,
                "partition_weight_max": 1.0,
            },
            "no_global_factor_inventory": {
                "full_p6_global_direct_factor_count": 0,
                "global_schur_matrix_materialized": False,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "p6_factor_count": 0,
                "p6_factor_nnz": 0,
                "p6_slab_matrix_count": 0,
                "p2_distributed_mumps_factor_count": 1,
                "wave_coarse_dense_lu_count": 1,
            },
        }
    )
    if optimized_schwarz:
        patch.update(
            {
                "variant": "ras",
                "correction_partition": "one_hot_ras",
                "ras_core_sum_error": 0.0,
                "interface_row_count": 3,
                "interface_shift_mode": "shared_rows_only",
                "interface_shift_nonzero_rows": 3,
                "noninterface_shift_nonzero_rows": 0,
                "partition_weighted_additive_schwarz": False,
            }
        )
        audit["solver_profile"] = "never_materialized_p2_factor_free_slab_ras_auxiliary"
        audit["candidate"].update(
            {
                "variant": "ras",
                "correction_partition": "one_hot_ras",
                "interface_shift_mode": "shared_rows_only",
            }
        )
        audit["p2_auxiliary_audit"].update(
            {
                "profile": audit["solver_profile"],
            }
        )
        audit["smoother_diagnostics"].update(
            {
                "profile": audit["solver_profile"],
            }
        )
        audit["partition_audit"].update(
            {
                "variant": "ras",
                "correction_partition": "one_hot_ras",
                "ras_core_sum_error": 0.0,
                "interface_row_count": 3,
                "interface_shift_mode": "shared_rows_only",
                "interface_shift_nonzero_rows": 3,
                "noninterface_shift_nonzero_rows": 0,
            }
        )
    return audit


def _m3a_audit(screen_iterations=20):
    audit = _audit(screen_iterations)
    audit.update(
        {
            "solver_profile": "never_materialized_owner_local_overlap0125_partition",
            "assembled_matrix_released_before_solve": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "candidate": {
                **audit["candidate"],
                "overlap_fraction": 0.125,
                "interpolation": "partition",
            },
            "partition_audit": {
                "matrix_materialized": False,
                "coverage_pass": True,
                "num_slabs": 16,
                "overlap_fraction": 0.125,
                "interpolation": "partition",
                "partition_weight_sum_error": 0.0,
                "partition_weight_min": 0.5,
                "partition_weight_max": 1.0,
            },
            "smoother_diagnostics": {
                "one_level_apply_count": 1,
                "factor_only_storage": True,
                "local_solver_types": ["ilu"],
                "interpolation": "partition",
                "assembly_order": "two_color",
                "smoother_iterations": 2,
                "smoother_ksp_type": "gmres",
                "global_stored_factor_nnz": 100,
            },
        }
    )
    return audit


def _task037_g2_identity_audit(
    *,
    status="pass",
    missing_iterations=None,
    deterministic_gate=True,
    iter20_gate=True,
    overall_gate=True,
    deterministic_error=0.0,
    iter20_error=0.0,
):
    return {
        "primary_selection_basis": {"primary_slab": 14},
        "materialization": {
            "condensed_trace_matrix_materialized": False,
            "action_only_request": True,
            "blocks_F_present": False,
        },
        "collector": {
            "owner_active_row_count": 3,
            "owner_active_row_hash": "a" * 64,
        },
        "current_local_shift": {
            "count": 3,
            "owner_row_count": 3,
            "finite": True,
            "sha256": "b" * 64,
            "route": {"owner_local_row_count": 3},
        },
        "deterministic_vectors": {
            "count": 3,
            "gate_pass": deterministic_gate,
            "measurement": {
                "vector_count": 3,
                "finite": True,
                "deterministic": True,
                "max_relative_error": deterministic_error,
            },
        },
        "iter20_real_residual": {
            "iteration": 20,
            "gate_pass": iter20_gate,
            "owner_row_count": 3,
            "local_residual_norm2": 1.0,
            "finite": True,
            "sha256": "c" * 64,
            "route": {"owner_local_row_count": 3},
            "measurement": {
                "vector_count": 1,
                "finite": True,
                "deterministic": True,
                "max_relative_error": iter20_error,
            },
        },
        "missing_iterations": (
            [] if missing_iterations is None else missing_iterations
        ),
        "gate_pass": overall_gate,
        "status": status,
    }


def _task037_g2_factor_audit(
    *, fullspace_retained_bytes=700, trace_retained_bytes=1000
):
    reduction = (
        trace_retained_bytes - fullspace_retained_bytes
    ) / trace_retained_bytes
    route_status = (
        "retained_payload_gate_pass_route_not_closed"
        if reduction >= 0.25
        else "close_fullspace_ilu_only_route"
    )
    matrix_audit = {
        "full_rows": 8,
        "interior_rows": 5,
        "trace_rows": 3,
        "trace_offset": 5,
        "matrix_nnz": 40,
        "matrix_csr_payload_bytes": 400,
        "matrix_fingerprint": "d" * 64,
        "matrix_assembly_seconds": 1.0,
    }
    fullspace = {
        "solver": "ilu",
        "factor_ordering": "rcm",
        "ilu_level": 0,
        "full_rows": 8,
        "interior_rows": 5,
        "trace_rows": 3,
        "matrix_nnz": 40,
        "matrix_csr_payload_bytes": 400,
        "matrix_fingerprint": "d" * 64,
        "factor_nnz": 30,
        "factor_csr_payload_bytes": fullspace_retained_bytes - 100,
        "work_vector_payload_bytes": 100,
        "retained_payload_lower_bound_bytes": fullspace_retained_bytes,
        "setup_seconds": 2.0,
        "apply_seconds": 0.1,
        "setup_matrix_lifetime": "released after factor extraction",
        "factor_lifetime": "owned by this oracle until destroy",
    }
    trace = {
        "rows": 3,
        "matrix_nnz": 20,
        "factor_nnz": 10,
        "factor_csr_payload_lower_bound_bytes": trace_retained_bytes - 100,
        "work_vector_payload_bytes": 100,
        "retained_payload_lower_bound_bytes": trace_retained_bytes,
        "factor_only_storage": True,
    }
    iter20 = {
        "trace_rhs": {
            "owner_row_count": 3,
            "norm2": 1.0,
            "finite": True,
            "sha256": "e" * 64,
            "trace_rhs_vs_extracted_relative_error": 0.0,
            "trace_rhs_exact": True,
        },
        "current_trace_ilu": {
            "input_norm": 1.0,
            "post_norm": 0.4,
            "rho": 0.4,
            "finite": True,
            "correction_norm2": 0.6,
            "correction_sha256": "f" * 64,
        },
        "fullspace_ilu": {
            "input_norm": 1.0,
            "post_norm": 0.3,
            "rho": 0.3,
            "finite": True,
            "correction_norm2": 0.7,
            "correction_sha256": "a" * 64,
            "deterministic": True,
            "correction_finite": True,
            "apply_count": 2,
            "apply_seconds": 0.1,
        },
        "contraction_comparison": {
            "full_minus_trace_rho": -0.1,
            "full_to_trace_rho_ratio": 0.75,
        },
    }
    return {
        "primary_slab": 14,
        "inventory_only": True,
        "used_in_outer_preconditioner": False,
        "global_A_materialized": False,
        "global_F_materialized": False,
        "official_result_unaffected": True,
        "matrix_audit": matrix_audit,
        "fullspace_factor_inventory": fullspace,
        "current_trace_factor_inventory": trace,
        "retained_payload_route": {
            "trace_retained_payload_lower_bound_bytes": trace_retained_bytes,
            "fullspace_retained_payload_lower_bound_bytes": fullspace_retained_bytes,
            "reduction_fraction": reduction,
            "gate_pass": reduction >= 0.25,
            "status": route_status,
        },
        "iter20": iter20,
        "iter20_gate_pass": True,
        "missing_iterations": [],
        "status": route_status,
    }


def _task037_g2_qualification_case(
    *,
    identity_audit=None,
    factor_audit=None,
    factor_enabled=False,
):
    args = SimpleNamespace(
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=True,
        task037_m3a_overlap0125_partition=True,
        task037_extra_g2_slab14_identity=True,
        task037_extra_g2_slab14_factor_inventory=factor_enabled,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        task037_canonical_vector_export=False,
        run_kind="full-solve",
        allow_swap=False,
        polarization_kind="s",
        mpi_size=1,
        task035d_case097_gate=False,
    )
    audit = _m3a_audit()
    identity_audit = (
        _task037_g2_identity_audit()
        if identity_audit is None
        else identity_audit
    )
    audit["task037_extra_g2_slab14_identity"] = identity_audit
    if factor_enabled:
        factor_audit = (
            _task037_g2_factor_audit()
            if factor_audit is None
            else factor_audit
        )
        identity_iter20 = identity_audit.get("iter20_real_residual")
        if (
            isinstance(identity_iter20, dict)
            and "factor_measurement" not in identity_iter20
        ):
            identity_iter20["factor_measurement"] = json.loads(
                json.dumps(factor_audit["iter20"])
            )
        audit["task037_extra_g2_slab14_factor_inventory"] = factor_audit
    summary = {
        "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": None},
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_no_global_factor": True,
        "ksp_converged_reason": -3,
        "linear_system_relative_residual": 0.1,
        "official_result": False,
        "postprocess_skipped": True,
        "external_solver_profile": audit["solver_profile"],
        "external_assembled_matrix_released_before_solve": False,
        "cell_static_condensation": {
            "action_only_setup": True,
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
    }
    factor_events = [
        {
            "stage": stage,
            "status": "end",
            "task037_g2_factor_inventory_lifecycle": True,
        }
        for stage in (
            "g2_fullspace_matrix_assembly_started",
            "g2_fullspace_matrix_assembly_ready",
            "g2_fullspace_factor_setup_started",
            "g2_fullspace_factor_setup_ready",
        )
    ]
    factor_stage_peaks = [
        {"stage": stage}
        for stage in (
            "g2_fullspace_matrix_assembly_started",
            "g2_fullspace_factor_setup_started",
        )
    ]
    return args, {
        "args": args,
        "solver_summary": summary,
        "events": factor_events if factor_enabled else [],
        "return_code": 0,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "no_swap": True,
        "observed_worker_rank_count": 1,
        "resource_summary": {
            "memory_authority_gib": 10.30,
            "stage_peaks": factor_stage_peaks if factor_enabled else [],
        },
        "task037_f3_core_audit": audit,
    }


def test_parser_scope_and_worker_command(tmp_path):
    base = [
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
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
        "global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json",
        "--task035c-p6-preflight-sha256",
        "96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8",
        "--verified-clean-sha",
        "b" * 40,
    ]
    ordinary = watchdog._parse_args(base)
    assert ordinary.task037_f3_screen is None
    assert ordinary.task037_f3_full is False
    canonical_f0 = watchdog._parse_args(
        base
        + [
            "--task037-f0-vector-observer",
            "--task037-canonical-vector-export",
        ]
    )
    assert canonical_f0.task037_canonical_vector_export
    canonical_f0_command = watchdog._worker_command(canonical_f0, tmp_path)
    assert canonical_f0_command.count("--task037-canonical-vector-export") == 1
    valid = []
    for screen_iterations in (20, 100, 200):
        valid_args = base + [
            "--task037-f3-screen",
            str(screen_iterations),
            "--warning-gib",
            "10",
            "--terminate-gib",
            "14",
            "--timeout-seconds",
            "1800",
        ]
        args = watchdog._parse_args(valid_args)
        command = watchdog._worker_command(args, tmp_path)
        position = command.index("--task037-f3-screen")
        assert command.count("--task037-f3-screen") == 1
        assert command[position + 1] == str(screen_iterations)
        valid = valid_args
    full_args = base + [
        "--task037-f3-full",
        "--warning-gib",
        "10",
        "--terminate-gib",
        "14",
        "--timeout-seconds",
        "7200",
    ]
    full = watchdog._parse_args(full_args)
    assert full.task037_f3_full
    assert full.task037_m4_b2_long_full is False
    assert watchdog._task037_f3_iterations(full) == 3000
    full_command = watchdog._worker_command(full, tmp_path)
    assert full_command.count("--task037-f3-full") == 1
    assert "--task037-f3-screen" not in full_command
    m3_full_args = full_args + [
        "--task037-m2c-never-materialized",
        "--task037-m3a-overlap0125-partition",
    ]
    m3_full = watchdog._parse_args(m3_full_args)
    assert m3_full.task037_f3_full
    assert m3_full.task037_f3_screen is None
    m3_full_command = watchdog._worker_command(m3_full, tmp_path)
    assert m3_full_command.count("--task037-f3-full") == 1
    assert m3_full_command.count("--task037-m2c-never-materialized") == 1
    assert m3_full_command.count("--task037-m3a-overlap0125-partition") == 1
    m3_full_canonical = watchdog._parse_args(
        m3_full_args + ["--task037-canonical-vector-export"]
    )
    assert m3_full_canonical.task037_canonical_vector_export
    assert (
        watchdog._worker_command(m3_full_canonical, tmp_path).count(
            "--task037-canonical-vector-export"
        )
        == 1
    )
    for mpi_size in (1, 2, 4, 8):
        m3_full_mpi_args = list(m3_full_args)
        m3_full_mpi_args[m3_full_mpi_args.index("--mpi-size") + 1] = str(mpi_size)
        m3_full_mpi = watchdog._parse_args(
            m3_full_mpi_args + ["--task037-canonical-vector-export"]
        )
        assert m3_full_mpi.mpi_size == mpi_size
        m3_full_mpi_command = watchdog._worker_command(m3_full_mpi, tmp_path)
        assert m3_full_mpi_command.count("--task037-canonical-vector-export") == 1
        assert m3_full_mpi_command.count("--task037-m3a-overlap0125-partition") == 1
        assert m3_full_mpi_command[m3_full_mpi_command.index("-n") + 1] == str(mpi_size)
        assert m3_full_mpi_command[m3_full_mpi_command.index("--mpi-size") + 1] == str(
            mpi_size
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(m3_full_args + ["--task037-f5b-released-profile"])
    released_args = full_args + ["--task037-f5b-released-profile"]
    released = watchdog._parse_args(released_args)
    assert released.task037_f5b_released_profile
    released_command = watchdog._worker_command(released, tmp_path)
    assert released_command.count("--task037-f5b-released-profile") == 1
    canonical_f5b = watchdog._parse_args(
        released_args + ["--task037-canonical-vector-export"]
    )
    assert canonical_f5b.task037_canonical_vector_export
    canonical_f5b_command = watchdog._worker_command(canonical_f5b, tmp_path)
    assert canonical_f5b_command.count("--task037-canonical-vector-export") == 1
    m0_args = full_args + [
        "--task037-f5b-released-profile",
        "--task037-m0-lifecycle-audit",
    ]
    m0 = watchdog._parse_args(m0_args)
    assert m0.task037_m0_lifecycle_audit
    m0_command = watchdog._worker_command(m0, tmp_path)
    assert m0_command.count("--task037-m0-lifecycle-audit") == 1
    m2c_args = base + [
        "--task037-f3-screen",
        "20",
        "--warning-gib",
        "10",
        "--terminate-gib",
        "14",
        "--timeout-seconds",
        "1800",
        "--task037-m2c-never-materialized",
    ]
    m2c = watchdog._parse_args(m2c_args)
    assert m2c.task037_m2c_never_materialized
    m2c_command = watchdog._worker_command(m2c, tmp_path)
    assert m2c_command.count("--task037-m2c-never-materialized") == 1
    m4 = watchdog._parse_args(m2c_args + ["--task037-m4-p2-auxiliary"])
    assert m4.task037_m4_p2_auxiliary
    assert (
        watchdog._worker_command(m4, tmp_path).count("--task037-m4-p2-auxiliary") == 1
    )
    for screen_iterations in (20, 100, 200):
        m4_screen_args = list(m2c_args)
        m4_screen_args[m4_screen_args.index("20")] = str(screen_iterations)
        m4_screen = watchdog._parse_args(m4_screen_args + ["--task037-m4-p2-auxiliary"])
        m4_screen_command = watchdog._worker_command(m4_screen, tmp_path)
        assert m4_screen_command.count("--task037-m4-p2-auxiliary") == 1
        assert m4_screen_command[
            m4_screen_command.index("--task037-f3-screen") + 1
        ] == str(screen_iterations)
        m4_factor_free_screen = watchdog._parse_args(
            m4_screen_args
            + [
                "--task037-m4-p2-auxiliary",
                "--task037-m4-factor-free-slab",
            ]
        )
        m4_factor_free_command = watchdog._worker_command(
            m4_factor_free_screen, tmp_path
        )
        assert m4_factor_free_screen.task037_m4_factor_free_slab
        assert m4_factor_free_command.count("--task037-m4-p2-auxiliary") == 1
        assert m4_factor_free_command.count("--task037-m4-factor-free-slab") == 1
        assert m4_factor_free_command.count("--task037-m4-factor-free-local-steps") == 1
        assert (
            m4_factor_free_command[
                m4_factor_free_command.index("--task037-m4-factor-free-local-steps") + 1
            ]
            == "2"
        )
        m4_factor_free4 = watchdog._parse_args(
            m4_screen_args
            + [
                "--task037-m4-p2-auxiliary",
                "--task037-m4-factor-free-slab",
                "--task037-m4-factor-free-local-steps",
                "4",
            ]
        )
        m4_factor_free4_command = watchdog._worker_command(m4_factor_free4, tmp_path)
        assert m4_factor_free4.task037_m4_factor_free_local_steps == 4
        assert (
            m4_factor_free4_command.count("--task037-m4-factor-free-local-steps") == 1
        )
        assert (
            m4_factor_free4_command[
                m4_factor_free4_command.index("--task037-m4-factor-free-local-steps")
                + 1
            ]
            == "4"
        )
        m4_ras = watchdog._parse_args(
            m4_screen_args
            + [
                "--task037-m4-p2-auxiliary",
                "--task037-m4-factor-free-slab",
                "--task037-m4-factor-free-local-steps",
                "4",
                "--task037-m4-optimized-schwarz",
            ]
        )
        m4_ras_command = watchdog._worker_command(m4_ras, tmp_path)
        assert m4_ras.task037_m4_optimized_schwarz
        assert m4_ras_command.count("--task037-m4-optimized-schwarz") == 1
        assert m4_ras_command.count("--task037-m4-factor-free-slab") == 1
        assert (
            m4_ras_command[
                m4_ras_command.index("--task037-m4-factor-free-local-steps") + 1
            ]
            == "4"
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            base
            + [
                "--task037-f3-screen",
                "20",
                "--task037-m4-factor-free-slab",
            ]
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(m2c_args + ["--task037-m4-factor-free-local-steps", "4"])
    with pytest.raises(SystemExit):
        watchdog._parse_args(m2c_args + ["--task037-m4-optimized-schwarz"])
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            m2c_args
            + [
                "--task037-m4-p2-auxiliary",
                "--task037-m4-factor-free-slab",
                "--task037-m4-optimized-schwarz",
            ]
        )
    m4_factor_free_full_args = full_args + [
        "--task037-m2c-never-materialized",
        "--task037-m4-p2-auxiliary",
        "--task037-m4-factor-free-slab",
    ]
    with pytest.raises(SystemExit):
        watchdog._parse_args(m4_factor_free_full_args)
    for mpi_size in (1, 8):
        full_factor_free_mpi_args = list(m4_factor_free_full_args)
        full_factor_free_mpi_args[full_factor_free_mpi_args.index("--mpi-size") + 1] = (
            str(mpi_size)
        )
        full_factor_free = watchdog._parse_args(
            full_factor_free_mpi_args + ["--task037-canonical-vector-export"]
        )
        assert full_factor_free.task037_m4_factor_free_slab
        full_factor_free_command = watchdog._worker_command(full_factor_free, tmp_path)
        assert full_factor_free_command.count("--task037-m4-factor-free-slab") == 1
        assert full_factor_free_command[
            full_factor_free_command.index("-n") + 1
        ] == str(mpi_size)
    for mpi_size in (2, 4):
        full_factor_free_mpi_args = list(m4_factor_free_full_args)
        full_factor_free_mpi_args[full_factor_free_mpi_args.index("--mpi-size") + 1] = (
            str(mpi_size)
        )
        with pytest.raises(SystemExit):
            watchdog._parse_args(
                full_factor_free_mpi_args + ["--task037-canonical-vector-export"]
            )
    long_args = list(m4_factor_free_full_args)
    long_args[long_args.index("--mpi-size") + 1] = "1"
    long_args[long_args.index("--timeout-seconds") + 1] = "604800"
    long_args.extend(["--task037-m4-b2-long-full", "--task037-canonical-vector-export"])
    long = watchdog._parse_args(long_args)
    assert long.task037_m4_b2_long_full
    assert watchdog._task037_f3_iterations(long) == watchdog.LONG_MAX_IT
    long_command = watchdog._worker_command(long, tmp_path)
    assert long_command.count("--task037-m4-b2-long-full") == 1
    long_worker = watchdog._parse_args(long_command[long_command.index("--worker") :])
    assert long_worker.task037_m4_b2_long_full
    assert watchdog._task037_f3_iterations(long_worker) == watchdog.LONG_MAX_IT
    invalid_long_mpi = list(long_args)
    invalid_long_mpi[invalid_long_mpi.index("--mpi-size") + 1] = "8"
    with pytest.raises(SystemExit):
        watchdog._parse_args(invalid_long_mpi)
    invalid_long_canonical = [
        item for item in long_args if item != "--task037-canonical-vector-export"
    ]
    with pytest.raises(SystemExit):
        watchdog._parse_args(invalid_long_canonical)
    ras_full_base = m4_factor_free_full_args + [
        "--task037-m4-factor-free-local-steps",
        "4",
        "--task037-m4-optimized-schwarz",
    ]
    ras_full_mpi8 = watchdog._parse_args(
        ras_full_base + ["--task037-canonical-vector-export"]
    )
    assert ras_full_mpi8.task037_m4_optimized_schwarz
    ras_full_command = watchdog._worker_command(ras_full_mpi8, tmp_path)
    assert ras_full_command.count("--task037-m4-optimized-schwarz") == 1
    assert (
        ras_full_command[
            ras_full_command.index("--task037-m4-factor-free-local-steps") + 1
        ]
        == "4"
    )
    m3 = watchdog._parse_args(m2c_args + ["--task037-m3a-overlap0125-partition"])
    assert m3.task037_m3a_overlap0125_partition
    assert (
        watchdog._worker_command(m3, tmp_path).count(
            "--task037-m3a-overlap0125-partition"
        )
        == 1
    )
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            m2c_args
            + [
                "--task037-m3a-overlap0125-partition",
                "--task037-canonical-vector-export",
            ]
        )
    for mpi_size in (1, 2, 4, 8):
        m3_mpi_args = list(m2c_args)
        m3_mpi_args[m3_mpi_args.index("--mpi-size") + 1] = str(mpi_size)
        m3_mpi = watchdog._parse_args(
            m3_mpi_args + ["--task037-m3a-overlap0125-partition"]
        )
        assert m3_mpi.mpi_size == mpi_size
        m3_mpi_command = watchdog._worker_command(m3_mpi, tmp_path)
        assert m3_mpi_command.count("--task037-m3a-overlap0125-partition") == 1
        assert m3_mpi_command[m3_mpi_command.index("-n") + 1] == str(mpi_size)
        assert m3_mpi_command[m3_mpi_command.index("--mpi-size") + 1] == str(mpi_size)
    for mpi_size in (1, 2, 4):
        m2c_mpi_args = list(m2c_args)
        m2c_mpi_args[m2c_mpi_args.index("--mpi-size") + 1] = str(mpi_size)
        with pytest.raises(SystemExit):
            watchdog._parse_args(m2c_mpi_args)
    m2c_mpi4_args = list(m2c_args)
    m2c_mpi4_args[m2c_mpi4_args.index("--mpi-size") + 1] = "4"
    with pytest.raises(SystemExit):
        watchdog._parse_args(m2c_mpi4_args + ["--task037-m4-p2-auxiliary"])
    for screen_iterations in (20, 100, 200):
        m3_screen_args = list(m2c_args)
        m3_screen_args[m3_screen_args.index("20")] = str(screen_iterations)
        assert watchdog._parse_args(
            m3_screen_args + ["--task037-m3a-overlap0125-partition"]
        ).task037_m3a_overlap0125_partition
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            m2c_args
            + [
                "--task037-m3a-overlap0125-partition",
                "--task037-m4-p2-auxiliary",
            ]
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            base + ["--task037-f3-screen", "20", "--task037-m4-p2-auxiliary"]
        )
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            base + ["--task037-f3-screen", "20", "--task037-m3a-overlap0125-partition"]
        )
    bad_iterations = valid.copy()
    bad_iterations[bad_iterations.index("--task037-f3-screen") + 1] = "3000"
    missing_caps = valid.copy()
    for option in ("--warning-gib", "--terminate-gib", "--timeout-seconds"):
        index = missing_caps.index(option)
        del missing_caps[index : index + 2]
    for invalid in (
        bad_iterations,
        missing_caps,
        valid + ["--task037-f0-vector-observer"],
        base + ["--task037-canonical-vector-export"],
        valid + ["--task037-canonical-vector-export"],
        base + ["--task037-f5b-released-profile"],
        valid + ["--task037-f5b-released-profile"],
        full_args + ["--task037-f3-screen", "20"],
        full_args + ["--task037-m0-lifecycle-audit"],
        base + ["--task037-m2c-never-materialized"],
        full_args + ["--task037-m2c-never-materialized"],
        valid + ["--task037-m2c-never-materialized"],
    ):
        with pytest.raises(SystemExit):
            watchdog._parse_args(invalid)


def test_worker_factory_writes_rank0_artifacts(tmp_path, monkeypatch):
    iterations_seen = []
    progress_events = []
    comm = SimpleNamespace(rank=0, gather=lambda payload, root=0: [payload])
    petsc_comm = SimpleNamespace(tompi4py=lambda: comm)

    def owner_release():
        return None

    request = SimpleNamespace(
        A=SimpleNamespace(getComm=lambda: petsc_comm),
        release_assembled_matrix=owner_release,
    )

    def fake_core(request, **kwargs):
        iterations_seen.append(kwargs["screen_iterations"])
        request.profile = kwargs["solver_profile"]
        request.release = kwargs["release_assembled_matrix"]
        residual_observer = kwargs["residual_observer"]
        for iteration in (0, 10, 20):
            residual_observer(iteration, 1.0 / (iteration + 1), 0.5)
        lifecycle_observer = kwargs["lifecycle_observer"]
        for event in ("blocks_extracted", "solver_owned_objects_released"):
            lifecycle_observer(event, {"rank_local_event": True})
        return object(), {"core": "audit"}

    def stage(*_args, **kwargs):
        assert kwargs["static_retain_local_schur_for_matrix_free"] is True
        assert kwargs["canonical_vector_export"] is True
        kwargs["linear_solver_port"](request)

    monkeypatch.setattr(watchdog, "_full3d_config", lambda _args: object())
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_assembled_static_condensed_fgmres",
        fake_core,
    )
    monkeypatch.setattr(
        "src.solvers.solve_maxwell_3d_stage_4b_block_grating."
        "run_stage4b_block_grating_3d_case",
        stage,
    )
    monkeypatch.setattr(
        watchdog,
        "_write_progress_event",
        lambda *args, **kwargs: progress_events.append(kwargs),
    )
    args = SimpleNamespace(
        run_dir=tmp_path,
        task037_f0_vector_observer=False,
        task037_f1_direct_trace_oracle=None,
        task037_f1_direct_trace_sha256=None,
        task037_f3_screen=None,
        task037_f3_full=True,
        task037_f5b_released_profile=True,
        task037_m2c_never_materialized=False,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_factor_free_local_steps=2,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        task037_canonical_vector_export=True,
        task037_m0_lifecycle_audit=True,
        task035d_nested_p_dwr_phase=None,
        task035d_selective_face_dwr_phase=None,
    )
    assert watchdog._worker(args) == 0
    assert iterations_seen == [3000]
    assert request.profile == (
        "assembled_setup_then_static_local_schur_matrix_free_solve"
    )
    assert request.release is owner_release
    history = (tmp_path / "task037_f3_residual_history.jsonl").read_text()
    lines = [json.loads(line) for line in history.splitlines()]
    assert len(lines) == 3
    assert all(
        set(line)
        == {"iteration", "reported_relative_residual", "condensed_true_residual"}
        for line in lines
    )
    assert json.loads((tmp_path / "task037_f3_core_audit.json").read_text()) == {
        "core": "audit",
        "task037_m4_b2_long_full": False,
    }
    assert [item["extra"]["m0_event"] for item in progress_events] == [
        "blocks_extracted",
        "solver_owned_objects_released",
    ]
    assert all(
        item["extra"]["task037_m0_rank_ledgers_by_rank"] == [{"rank_local_event": True}]
        for item in progress_events
    )


def test_worker_wraps_never_materialized_port(tmp_path, monkeypatch):
    from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort

    class Comm:
        rank = 0
        size = 1

        def tompi4py(self):
            return self

    operator = SimpleNamespace(getComm=lambda: Comm())
    request = SimpleNamespace(operator=operator)
    captured = {}
    selected_profiles = []
    selected_iterations = []

    def fake_action_core(request, **kwargs):
        selected_profiles.append("m2c")
        captured["request"] = request
        captured["kwargs"] = kwargs
        return object(), {"solver_profile": "never_materialized_owner_local"}

    def fake_p2_action_core(request, **kwargs):
        selected_profiles.append("m4")
        captured["request"] = request
        captured["kwargs"] = kwargs
        return object(), {"solver_profile": "never_materialized_p2_auxiliary"}

    def fake_factor_free_action_core(request, **kwargs):
        selected_profiles.append("m4-factor-free")
        captured["request"] = request
        captured["kwargs"] = kwargs
        for iteration in (0, 10, 20):
            kwargs["residual_observer"](iteration, 1.0 / (iteration + 1), 0.5)
        if kwargs["screen_iterations"] > 3000:
            kwargs["residual_observer"](100, 0.01, 0.5)
        return object(), {
            "solver_profile": "never_materialized_p2_factor_free_slab_auxiliary"
        }

    def fake_ras_action_core(request, **kwargs):
        selected_profiles.append("m4-ras")
        captured["request"] = request
        captured["kwargs"] = kwargs
        return object(), {
            "solver_profile": "never_materialized_p2_factor_free_slab_ras_auxiliary"
        }

    def fake_m3a_action_core(request, **kwargs):
        selected_profiles.append("m3a")
        selected_iterations.append(kwargs["screen_iterations"])
        captured["request"] = request
        captured["kwargs"] = kwargs
        return object(), {
            "solver_profile": "never_materialized_owner_local_overlap0125_partition"
        }

    def stage(*_args, **kwargs):
        captured["retain"] = kwargs["static_retain_local_schur_for_matrix_free"]
        captured["port"] = kwargs["linear_solver_port"]
        kwargs["linear_solver_port"](request)

    monkeypatch.setattr(watchdog, "_full3d_config", lambda _args: object())
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative.solve_never_materialized_static_condensed_fgmres",
        fake_action_core,
    )
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative.solve_never_materialized_p2_auxiliary_fgmres",
        fake_p2_action_core,
    )
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres",
        fake_factor_free_action_core,
    )
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres",
        fake_ras_action_core,
    )
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_overlap0125_partition_fgmres",
        fake_m3a_action_core,
    )
    monkeypatch.setattr(
        "src.solvers.solve_maxwell_3d_stage_4b_block_grating.run_stage4b_block_grating_3d_case",
        stage,
    )
    common_args = dict(
        run_dir=tmp_path,
        task037_f0_vector_observer=False,
        task037_f1_direct_trace_oracle=None,
        task037_f1_direct_trace_sha256=None,
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=True,
        task037_canonical_vector_export=False,
        task037_m0_lifecycle_audit=False,
        task037_m4_b2_long_full=False,
        task035d_nested_p_dwr_phase=None,
        task035d_selective_face_dwr_phase=None,
    )
    for m3a, m4, factor_free, optimized in (
        (False, False, False, False),
        (False, True, False, False),
        (False, True, True, False),
        (False, True, True, True),
        (True, False, False, False),
    ):
        args = SimpleNamespace(
            **common_args,
            task037_m3a_overlap0125_partition=m3a,
            task037_m4_p2_auxiliary=m4,
            task037_m4_factor_free_slab=factor_free,
            task037_m4_factor_free_local_steps=(4 if optimized else 2),
            task037_m4_optimized_schwarz=optimized,
        )
        assert watchdog._worker(args) == 0
    assert captured["retain"] is True
    assert isinstance(captured["port"], Stage4NeverMaterializedLinearSolverPort)
    assert captured["request"] is request
    assert captured["kwargs"]["screen_iterations"] == 20
    full_args = SimpleNamespace(
        **{
            **common_args,
            "task037_f3_screen": None,
            "task037_f3_full": True,
            "task037_m3a_overlap0125_partition": True,
            "task037_m4_p2_auxiliary": False,
            "task037_m4_factor_free_slab": False,
            "task037_m4_factor_free_local_steps": 2,
            "task037_m4_optimized_schwarz": False,
        }
    )
    assert watchdog._worker(full_args) == 0
    assert captured["kwargs"]["screen_iterations"] == 3000
    assert selected_profiles == [
        "m2c",
        "m4",
        "m4-factor-free",
        "m4-ras",
        "m3a",
        "m3a",
    ]
    assert selected_iterations == [20, 3000]
    long_args = SimpleNamespace(
        **{
            **common_args,
            "task037_f3_screen": None,
            "task037_f3_full": True,
            "task037_m3a_overlap0125_partition": False,
            "task037_m4_p2_auxiliary": True,
            "task037_m4_factor_free_slab": True,
            "task037_m4_factor_free_local_steps": 2,
            "task037_m4_b2_long_full": True,
            "task037_m4_optimized_schwarz": False,
            "task037_canonical_vector_export": True,
        }
    )
    assert watchdog._worker(long_args) == 0
    assert captured["kwargs"]["screen_iterations"] == watchdog.LONG_MAX_IT
    history = (tmp_path / "task037_f3_residual_history.jsonl").read_text()
    assert [json.loads(line)["iteration"] for line in history.splitlines()[-4:]] == [
        0,
        10,
        20,
        100,
    ]


def test_f3_qualification_uses_core_audit_gate():
    args = SimpleNamespace(
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=False,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        task037_canonical_vector_export=False,
        run_kind="full-solve",
        allow_swap=False,
        polarization_kind="s",
        mpi_size=8,
        task035d_case097_gate=False,
    )
    summary = {
        "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": 1},
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_no_global_factor": True,
        "ksp_converged_reason": -3,
        "linear_system_relative_residual": 0.1,
        "official_result": False,
        "postprocess_skipped": True,
    }
    audit = _audit()
    qualify_kwargs = {
        "args": args,
        "solver_summary": summary,
        "events": [],
        "return_code": 0,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "no_swap": True,
        "observed_worker_rank_count": 8,
    }
    result = watchdog._qualify(
        **qualify_kwargs,
        task037_f3_core_audit=audit,
    )
    assert result["pass"]
    args100 = SimpleNamespace(**{**vars(args), "task037_f3_screen": 100})
    audit100 = _audit(100)
    audit100["reported_history"][-1][1] = 1.0e-7
    audit100["condensed_true_samples"][-1][1] = 1.0e-7
    audit100["final"].update(
        converged_reason=1,
        reported_relative_residual=1.0e-7,
        condensed_true_residual=1.0e-7,
        full_augmented_true_residual=1.0e-7,
    )
    summary100 = {
        **summary,
        "ksp_converged_reason": 1,
        "linear_system_relative_residual": 1.0e-7,
        "official_result": True,
        "postprocess_skipped": False,
    }
    assert watchdog._qualify(
        **{**qualify_kwargs, "args": args100, "solver_summary": summary100},
        task037_f3_core_audit=audit100,
    )["pass"]
    good200 = _audit(200)
    good200["reported_history"][-1][1] = 0.01
    good200["condensed_true_samples"][-1][1] = 0.01
    good200["final"].update(
        reported_relative_residual=0.01,
        condensed_true_residual=0.01,
        full_augmented_true_residual=0.01,
    )
    args200 = SimpleNamespace(**{**vars(args), "task037_f3_screen": 200})
    summary200 = {**summary, "elapsed_seconds": 300.0}
    assert watchdog._task037_f3_screen_gate(good200, 200, 300.0)["screen_200"]
    good200["final"]["condensed_true_residual"] = 0.051
    assert watchdog._task037_f3_screen_gate(good200, 200, 300.0)["screen_200"]
    good200["final"]["condensed_true_residual"] = 0.01
    assert watchdog._qualify(
        **{**qualify_kwargs, "args": args200, "solver_summary": summary200},
        task037_f3_core_audit=good200,
    )["pass"]
    assert not watchdog._task037_f3_screen_gate(good200, 200, 5000.0)["screen_200"]
    bad_full = _audit(200)
    bad_full["final"]["full_augmented_true_residual"] = 0.051
    assert not watchdog._task037_f3_screen_gate(bad_full, 200, 300.0)["screen_200"]
    slow = _audit(200)
    slow["reported_history"][1][1] = 0.05
    slow["reported_history"][-1][1] = 0.049
    slow["condensed_true_samples"][1][1] = 0.05
    slow["condensed_true_samples"][2][1] = 0.049
    slow["final"].update(
        reported_relative_residual=0.049,
        condensed_true_residual=0.049,
        full_augmented_true_residual=0.049,
    )
    assert not watchdog._task037_f3_screen_gate(slow, 200, 300.0)["screen_200"]
    full = _audit(3000)
    full["reported_history"][-1][1] = 1.0e-7
    full["condensed_true_samples"][-1][1] = 1.0e-7
    full["final"].update(
        converged_reason=1,
        reported_relative_residual=1.0e-7,
        condensed_true_residual=1.0e-7,
        full_augmented_true_residual=1.0e-7,
    )
    full["solver_profile"] = "assembled_setup_then_static_local_schur_matrix_free_solve"
    full["assembled_matrix_released_before_solve"] = True
    args_full = SimpleNamespace(**vars(args))
    args_full.task037_f3_screen = None
    args_full.task037_f3_full = True
    args_full.task037_f5b_released_profile = True
    summary_full = {
        **summary,
        "ksp_converged_reason": 1,
        "linear_system_relative_residual": 1.0e-7,
        "official_result": True,
        "postprocess_skipped": False,
        "external_rta_gate_pass": True,
        "external_reported_relative_residual": 1.0e-7,
        "external_condensed_true_residual": 1.0e-7,
        "external_full_augmented_true_residual": 1.0e-7,
    }
    summary_full["external_solver_profile"] = full["solver_profile"]
    summary_full["external_assembled_matrix_released_before_solve"] = True
    assert watchdog._qualify(
        **{**qualify_kwargs, "args": args_full, "solver_summary": summary_full},
        task037_f3_core_audit=full,
    )["pass"]
    summary_full["external_assembled_matrix_released_before_solve"] = False
    assert not watchdog._qualify(
        **{**qualify_kwargs, "args": args_full, "solver_summary": summary_full},
        task037_f3_core_audit=full,
    )["pass"]
    bad_trend = _audit(100)
    bad_trend["reported_history"][-1][1] = 0.5
    assert not watchdog._task037_f3_screen_gate(bad_trend, 100, None)["screen_100"]
    bad_residual = _audit(100)
    bad_residual["reported_history"][-1][1] = 0.31
    bad_residual["condensed_true_samples"][-1][1] = 0.31
    bad_residual["final"].update(
        reported_relative_residual=0.31,
        condensed_true_residual=0.31,
        full_augmented_true_residual=0.31,
    )
    assert not watchdog._task037_f3_screen_gate(bad_residual, 100, None)["screen_100"]
    bad = _audit()
    bad["reported_history"][1][1] = 11.0
    assert not watchdog._task037_f3_screen_gate(bad, 20, None)["finite_and_scale"]
    assert not watchdog._qualify(
        **qualify_kwargs,
        task037_f3_core_audit=bad,
    )["pass"]


def test_m2c_qualification_requires_action_profile_and_memory_gate():
    args = SimpleNamespace(
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=True,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        task037_canonical_vector_export=False,
        run_kind="full-solve",
        allow_swap=False,
        polarization_kind="s",
        mpi_size=8,
        task035d_case097_gate=False,
    )
    audit = _audit()
    audit.update(
        {
            "solver_profile": "never_materialized_owner_local",
            "assembled_matrix_released_before_solve": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
        }
    )
    audit["partition_audit"]["matrix_materialized"] = False
    audit["smoother_diagnostics"].update(
        {
            "assembly_order": "two_color",
            "smoother_iterations": 2,
            "smoother_ksp_type": "gmres",
        }
    )
    summary = {
        "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": None},
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_no_global_factor": True,
        "ksp_converged_reason": -3,
        "linear_system_relative_residual": 0.1,
        "official_result": False,
        "postprocess_skipped": True,
        "external_solver_profile": "never_materialized_owner_local",
        "external_assembled_matrix_released_before_solve": False,
        "cell_static_condensation": {
            "action_only_setup": True,
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
    }
    kwargs = {
        "args": args,
        "solver_summary": summary,
        "events": [],
        "return_code": 0,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "no_swap": True,
        "observed_worker_rank_count": 8,
        "resource_summary": {"memory_authority_gib": 10.30},
        "task037_f3_core_audit": audit,
    }
    assert "m3a_screen_decline" not in watchdog._task037_f3_screen_gate(audit, 20, None)
    assert watchdog._qualify(**kwargs)["pass"]
    kwargs["solver_summary"]["cell_static_condensation"]["action_only_setup"] = False
    assert not watchdog._qualify(**kwargs)["pass"]
    kwargs["solver_summary"]["cell_static_condensation"]["action_only_setup"] = True
    kwargs["resource_summary"] = {"memory_authority_gib": 10.31}
    assert not watchdog._qualify(**kwargs)["pass"]


def test_m4_qualification_uses_final_p2_smoother_and_resource_gate():
    args = SimpleNamespace(
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=True,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=True,
        task037_m4_factor_free_slab=False,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        task037_canonical_vector_export=False,
        run_kind="full-solve",
        allow_swap=False,
        polarization_kind="s",
        mpi_size=8,
        task035d_case097_gate=False,
    )
    audit = _m4_audit()
    summary = {
        "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": None},
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_no_global_factor": True,
        "ksp_converged_reason": -3,
        "linear_system_relative_residual": 0.1,
        "official_result": False,
        "postprocess_skipped": True,
        "external_solver_profile": "never_materialized_p2_auxiliary",
        "external_assembled_matrix_released_before_solve": False,
        "cell_static_condensation": {
            "action_only_setup": True,
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
    }
    kwargs = {
        "args": args,
        "solver_summary": summary,
        "events": [],
        "return_code": 0,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "no_swap": True,
        "observed_worker_rank_count": 8,
        "resource_summary": {"memory_authority_gib": 7.60},
        "task037_f3_core_audit": audit,
    }
    screen = watchdog._task037_f3_screen_gate(audit, 20, None)
    assert screen["candidate"]
    assert screen["apply_counts"]
    assert screen["partition_and_ilu"]
    assert watchdog._qualify(**kwargs)["pass"]

    bad_factor = _m4_audit()
    bad_factor["no_global_factor_inventory"]["full_p6_global_direct_factor_count"] = 1
    assert not watchdog._qualify(**{**kwargs, "task037_f3_core_audit": bad_factor})[
        "pass"
    ]

    assert not watchdog._qualify(
        **{**kwargs, "resource_summary": {"memory_authority_gib": 7.61}}
    )["pass"]
    bad_scale = _m4_audit()
    bad_scale["reported_history"][1][1] = 11.0
    assert (
        watchdog._task037_f3_screen_gate(bad_scale, 20, None)["finite_and_scale"]
        is False
    )

    factor_free_args = SimpleNamespace(
        **{
            **vars(args),
            "task037_m4_factor_free_slab": True,
            "task037_m4_factor_free_local_steps": 2,
        }
    )
    factor_free_audit = _m4_factor_free_audit()
    factor_free_summary = {
        **summary,
        "external_solver_profile": factor_free_audit["solver_profile"],
    }
    factor_free_kwargs = {
        **kwargs,
        "args": factor_free_args,
        "solver_summary": factor_free_summary,
        "task037_f3_core_audit": factor_free_audit,
        "resource_summary": {"memory_authority_gib": 10.30},
    }
    factor_free_screen = watchdog._task037_f3_screen_gate(
        factor_free_audit, 20, None, expected_factor_free_steps=2
    )
    assert factor_free_screen["candidate"]
    assert factor_free_screen["partition_and_ilu"]
    assert factor_free_screen["m4_factor_free_screen_decline"]
    assert watchdog._qualify(**factor_free_kwargs)["pass"]

    bad_factor_free = _m4_factor_free_audit()
    bad_factor_free["partition_audit"]["p6_factor_nnz"] = 1
    assert not watchdog._qualify(
        **{**factor_free_kwargs, "task037_f3_core_audit": bad_factor_free}
    )["pass"]
    bad_factor_free_kind = _m4_factor_free_audit()
    bad_factor_free_kind["p2_auxiliary_audit"]["fine_schur_action_kind"] = (
        "wrong-action-kind"
    )
    assert not watchdog._task037_f3_screen_gate(
        bad_factor_free_kind, 20, None, expected_factor_free_steps=2
    )["no_global_factor"]

    factor_free_full_args = SimpleNamespace(
        **{
            **vars(factor_free_args),
            "task037_f3_screen": None,
            "task037_f3_full": True,
            "task037_canonical_vector_export": True,
        }
    )
    factor_free_full_audit = _m4_factor_free_audit(3000)
    factor_free_full_audit["reported_history"][-1][1] = 1.0e-7
    factor_free_full_audit["condensed_true_samples"][-1][1] = 1.0e-7
    factor_free_full_audit["final"].update(
        converged_reason=1,
        reported_relative_residual=1.0e-7,
        condensed_true_residual=1.0e-7,
        full_augmented_true_residual=1.0e-7,
    )
    factor_free_full_summary = {
        **factor_free_summary,
        "ksp_converged_reason": 1,
        "linear_system_relative_residual": 1.0e-7,
        "official_result": True,
        "postprocess_skipped": False,
        "external_rta_gate_pass": True,
    }
    assert watchdog._qualify(
        **{
            **factor_free_kwargs,
            "args": factor_free_full_args,
            "solver_summary": factor_free_full_summary,
            "task037_f3_core_audit": factor_free_full_audit,
        }
    )["pass"]
    assert (
        watchdog._task037_m4_factor_free_status(factor_free_args, {"pass": True})
        == "task037_m4_p2_factor_free_slab_steps2_20_screen_pass"
    )
    assert (
        watchdog._task037_m4_factor_free_status(factor_free_args, {"pass": False})
        == "task037_m4_p2_factor_free_slab_steps2_20_screen_not_pass"
    )
    assert (
        watchdog._task037_m4_factor_free_status(factor_free_full_args, {"pass": True})
        == "task037_m4_p2_factor_free_slab_steps2_full_pass"
    )
    assert (
        watchdog._task037_m4_factor_free_status(factor_free_full_args, {"pass": False})
        == "task037_m4_p2_factor_free_slab_steps2_full_not_pass"
    )
    assert watchdog._task037_m4_factor_free_status(args, {"pass": True}) is None

    ras_args = SimpleNamespace(
        **{
            **vars(factor_free_args),
            "task037_m4_factor_free_local_steps": 4,
            "task037_m4_optimized_schwarz": True,
        }
    )
    ras_audit = _m4_factor_free_audit(optimized_schwarz=True, local_krylov_steps=4)
    ras_summary = {
        **summary,
        "external_solver_profile": ras_audit["solver_profile"],
    }
    ras_kwargs = {
        **factor_free_kwargs,
        "args": ras_args,
        "solver_summary": ras_summary,
        "task037_f3_core_audit": ras_audit,
    }
    ras_screen = watchdog._task037_f3_screen_gate(
        ras_audit,
        20,
        None,
        expected_factor_free_steps=4,
        expected_factor_free_variant="ras",
    )
    assert ras_screen["candidate"]
    assert ras_screen["partition_and_ilu"]
    assert watchdog._qualify(**ras_kwargs)["pass"]
    ordinary_artifact = _m4_factor_free_audit(local_krylov_steps=4)
    ordinary_artifact["p2_auxiliary_audit"]["profile"] = (
        "never_materialized_p2_factor_free_slab_auxiliary"
    )
    assert not watchdog._qualify(
        **{**ras_kwargs, "task037_f3_core_audit": ordinary_artifact}
    )["pass"]
    wrong_variant = _m4_factor_free_audit(optimized_schwarz=True, local_krylov_steps=4)
    wrong_variant["partition_audit"]["variant"] = "partition"
    assert not watchdog._qualify(
        **{**ras_kwargs, "task037_f3_core_audit": wrong_variant}
    )["pass"]
    assert (
        watchdog._task037_m4_optimized_schwarz_status(ras_args, {"pass": True})
        == "task037_m4_p2_factor_free_slab_ras_steps4_20_screen_pass"
    )
    assert (
        watchdog._task037_m4_optimized_schwarz_status(ras_args, {"pass": False})
        == "task037_m4_p2_factor_free_slab_ras_steps4_20_screen_not_pass"
    )
    ras_full_args = SimpleNamespace(
        **{
            **vars(ras_args),
            "task037_f3_screen": None,
            "task037_f3_full": True,
            "task037_canonical_vector_export": True,
        }
    )
    assert (
        watchdog._task037_m4_optimized_schwarz_status(ras_full_args, {"pass": True})
        == "task037_m4_p2_factor_free_slab_ras_steps4_full_pass"
    )
    assert (
        watchdog._task037_m4_optimized_schwarz_status(ras_full_args, {"pass": False})
        == "task037_m4_p2_factor_free_slab_ras_steps4_full_not_pass"
    )


def test_m3a_partition_profile_and_memory_gates():
    args = SimpleNamespace(
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=True,
        task037_m3a_overlap0125_partition=True,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        task037_canonical_vector_export=False,
        run_kind="full-solve",
        allow_swap=False,
        polarization_kind="s",
        mpi_size=8,
        task035d_case097_gate=False,
    )
    audit = _m3a_audit()
    summary = {
        "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": None},
        "polarization_kind": "s",
        "external_linear_solver_port": True,
        "external_no_global_factor": True,
        "ksp_converged_reason": -3,
        "linear_system_relative_residual": 0.1,
        "official_result": False,
        "postprocess_skipped": True,
        "external_solver_profile": audit["solver_profile"],
        "external_assembled_matrix_released_before_solve": False,
        "cell_static_condensation": {
            "action_only_setup": True,
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
    }
    kwargs = {
        "args": args,
        "solver_summary": summary,
        "events": [],
        "return_code": 0,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "terminated_for_authority_unreadable": False,
        "no_swap": True,
        "observed_worker_rank_count": 8,
        "resource_summary": {"memory_authority_gib": 10.30},
        "task037_f3_core_audit": audit,
    }
    screen = watchdog._task037_f3_screen_gate(audit, 20, None)
    assert screen["candidate"]
    assert screen["partition_and_ilu"]
    assert screen["m3a_screen_decline"]
    assert watchdog._qualify(**kwargs)["pass"]

    bad_decline = _m3a_audit()
    bad_decline["reported_history"][1][1] = 1.1
    bad_decline_screen = watchdog._task037_f3_screen_gate(bad_decline, 20, None)
    assert not bad_decline_screen["m3a_screen_decline"]
    assert not watchdog._qualify(**{**kwargs, "task037_f3_core_audit": bad_decline})[
        "pass"
    ]

    bad_condensed_decline = _m3a_audit()
    bad_condensed_decline["condensed_true_samples"][1][1] = 1.1
    assert not watchdog._task037_f3_screen_gate(bad_condensed_decline, 20, None)[
        "m3a_screen_decline"
    ]

    bad_factor = _m3a_audit()
    bad_factor["smoother_diagnostics"]["global_stored_factor_nnz"] = 103336560
    assert not watchdog._qualify(**{**kwargs, "task037_f3_core_audit": bad_factor})[
        "pass"
    ]
    assert not watchdog._qualify(
        **{**kwargs, "resource_summary": {"memory_authority_gib": 10.31}}
    )["pass"]

    full_args = SimpleNamespace(
        **{
            **vars(args),
            "task037_f3_screen": None,
            "task037_f3_full": True,
        }
    )
    full_audit = _m3a_audit(3000)
    full_audit["reported_history"][-1][1] = 1.0e-7
    full_audit["condensed_true_samples"][-1][1] = 1.0e-7
    full_audit["final"].update(
        converged_reason=1,
        reported_relative_residual=1.0e-7,
        condensed_true_residual=1.0e-7,
        full_augmented_true_residual=1.0e-7,
    )
    full_summary = {
        **summary,
        "ksp_converged_reason": 1,
        "linear_system_relative_residual": 1.0e-7,
        "official_result": True,
        "postprocess_skipped": False,
        "external_rta_gate_pass": True,
        "external_solver_profile": full_audit["solver_profile"],
        "external_assembled_matrix_released_before_solve": False,
    }
    full_kwargs = {
        **kwargs,
        "args": full_args,
        "solver_summary": full_summary,
        "task037_f3_core_audit": full_audit,
    }
    assert watchdog._qualify(**full_kwargs)["pass"]
    assert watchdog._task037_m3a_status(full_args, {"pass": True}) == (
        "task037_m3a_overlap0125_partition_full_pass"
    )
    assert watchdog._task037_m3a_status(full_args, {"pass": False}) == (
        "task037_m3a_overlap0125_partition_full_not_pass"
    )
    full_summary["external_rta_gate_pass"] = False
    assert not watchdog._qualify(**full_kwargs)["pass"]


def test_task037_extra_g2_identity_qualification_positive():
    args, kwargs = _task037_g2_qualification_case()
    qualification = watchdog._qualify(**kwargs)

    assert qualification["pass"]
    assert qualification["checks"]["task037_g2_identity_present"]
    assert watchdog._task037_extra_g2_status(args, qualification) == (
        "task037_extra_g2_slab14_identity_pass"
    )


def test_task037_extra_g2_factor_status_has_priority():
    args, kwargs = _task037_g2_qualification_case(factor_enabled=True)
    qualification = watchdog._qualify(**kwargs)

    assert watchdog._task037_extra_g2_status(args, qualification) == (
        "task037_extra_g2_slab14_factor_inventory_pass"
    )
    failed = {**qualification, "pass": False}
    assert watchdog._task037_extra_g2_status(args, failed) == (
        "task037_extra_g2_slab14_factor_inventory_not_pass"
    )


def test_task037_extra_g2_factor_static_inventory_positive_and_route_negative():
    args, kwargs = _task037_g2_qualification_case(factor_enabled=True)
    qualification = watchdog._qualify(**kwargs)

    assert qualification["pass"]
    assert qualification["checks"]["task037_g2_factor_route_gate_raw"]
    assert watchdog._task037_extra_g2_status(args, qualification) == (
        "task037_extra_g2_slab14_factor_inventory_pass"
    )

    negative_audit = _task037_g2_factor_audit(fullspace_retained_bytes=800)
    negative_args, negative_kwargs = _task037_g2_qualification_case(
        factor_audit=negative_audit,
        factor_enabled=True,
    )
    negative = watchdog._qualify(**negative_kwargs)

    assert negative["pass"]
    assert negative["checks"]["task037_g2_factor_route_gate_raw"]
    assert negative_audit["retained_payload_route"]["gate_pass"] is False
    assert negative["checks"]["task037_g2_factor_route_status_raw"]
    assert watchdog._task037_extra_g2_status(negative_args, negative) == (
        "task037_extra_g2_slab14_factor_inventory_pass"
    )

    signed_negative_audit = _task037_g2_factor_audit(
        fullspace_retained_bytes=648750388,
        trace_retained_bytes=122023588,
    )
    signed_negative_args, signed_negative_kwargs = _task037_g2_qualification_case(
        factor_audit=signed_negative_audit,
        factor_enabled=True,
    )
    signed_negative = watchdog._qualify(**signed_negative_kwargs)

    assert signed_negative["pass"]
    assert signed_negative_audit["retained_payload_route"]["reduction_fraction"] == (
        pytest.approx(-4.316598197391147)
    )
    assert signed_negative_audit["retained_payload_route"]["gate_pass"] is False
    assert signed_negative_audit["retained_payload_route"]["status"] == (
        "close_fullspace_ilu_only_route"
    )
    assert watchdog._task037_extra_g2_status(
        signed_negative_args, signed_negative
    ) == "task037_extra_g2_slab14_factor_inventory_pass"


def test_task037_extra_g2_factor_static_inventory_tamper_not_pass():
    factor_audit = _task037_g2_factor_audit()
    factor_audit["matrix_audit"]["matrix_fingerprint"] = "e" * 64
    _, kwargs = _task037_g2_qualification_case(
        factor_audit=factor_audit,
        factor_enabled=True,
    )
    qualification = watchdog._qualify(**kwargs)

    assert not qualification["pass"]
    assert not qualification["checks"][
        "task037_g2_factor_matrix_inventory_consistent"
    ]

    timing_audit = _task037_g2_factor_audit()
    timing_audit["fullspace_factor_inventory"]["setup_seconds"] = -1.0
    _, timing_kwargs = _task037_g2_qualification_case(
        factor_audit=timing_audit,
        factor_enabled=True,
    )
    timing_qualification = watchdog._qualify(**timing_kwargs)
    assert not timing_qualification["pass"]
    assert not timing_qualification["checks"]["task037_g2_factor_timings"]


def test_task037_extra_g2_factor_non_mapping_subblock_not_pass():
    factor_audit = _task037_g2_factor_audit()
    factor_audit["current_trace_factor_inventory"] = []
    _, kwargs = _task037_g2_qualification_case(
        factor_audit=factor_audit,
        factor_enabled=True,
    )
    qualification = watchdog._qualify(**kwargs)

    assert not qualification["pass"]
    assert not qualification["checks"]["task037_g2_factor_inventory_mappings"]


@pytest.mark.parametrize(
    "tamper",
    (
        "trace_rhs_exact",
        "trace_rhs_relative_error",
        "rho_arithmetic",
        "apply_count",
        "correction_hash",
        "top_status",
        "missing_iterations",
        "identity_copy",
        "lifecycle_event",
        "stage_peak",
    ),
)
def test_task037_extra_g2_factor_iter20_and_lifecycle_tamper_not_pass(tamper):
    _, kwargs = _task037_g2_qualification_case(factor_enabled=True)
    factor_audit = kwargs["task037_f3_core_audit"][
        "task037_extra_g2_slab14_factor_inventory"
    ]
    if tamper == "trace_rhs_exact":
        factor_audit["iter20"]["trace_rhs"]["trace_rhs_exact"] = False
    elif tamper == "trace_rhs_relative_error":
        factor_audit["iter20"]["trace_rhs"][
            "trace_rhs_vs_extracted_relative_error"
        ] = 1.0e-9
    elif tamper == "rho_arithmetic":
        factor_audit["iter20"]["current_trace_ilu"]["rho"] = 0.5
    elif tamper == "apply_count":
        factor_audit["iter20"]["fullspace_ilu"]["apply_count"] = 1
    elif tamper == "correction_hash":
        factor_audit["iter20"]["fullspace_ilu"]["correction_sha256"] = "bad"
    elif tamper == "top_status":
        factor_audit["status"] = "close_fullspace_ilu_only_route"
    elif tamper == "missing_iterations":
        factor_audit["missing_iterations"] = [20]
    elif tamper == "identity_copy":
        kwargs["task037_f3_core_audit"]["task037_extra_g2_slab14_identity"][
            "iter20_real_residual"
        ]["factor_measurement"]["trace_rhs"]["norm2"] = 2.0
    elif tamper == "lifecycle_event":
        kwargs["events"] = kwargs["events"][:-1]
    elif tamper == "stage_peak":
        kwargs["resource_summary"]["stage_peaks"] = []

    qualification = watchdog._qualify(**kwargs)
    assert not qualification["pass"], tamper


def test_task037_extra_g2_identity_qualification_missing_iter20_not_pass():
    identity_audit = _task037_g2_identity_audit(
        status="missing_iter20",
        missing_iterations=[20],
        iter20_gate=False,
        overall_gate=False,
        iter20_error=1.0e-9,
    )
    args, kwargs = _task037_g2_qualification_case(
        identity_audit=identity_audit,
    )
    qualification = watchdog._qualify(**kwargs)

    assert not qualification["pass"]
    assert "task037_g2_no_missing_iterations" in qualification["failures"]
    assert "task037_g2_iter20_gate_pass" in qualification["failures"]
    assert "task037_g2_iter20_raw_measurement" in qualification["failures"]
    assert watchdog._task037_extra_g2_status(args, qualification) == (
        "task037_extra_g2_slab14_identity_not_pass"
    )


def test_ordinary_full_solve_rules_remain_strict():
    args = SimpleNamespace(
        task037_f3_screen=None,
        task037_f3_full=False,
        task037_m2c_never_materialized=False,
        task037_m3a_overlap0125_partition=False,
        task037_m4_p2_auxiliary=False,
        task037_m4_factor_free_slab=False,
        task037_m4_b2_long_full=False,
        task037_m4_optimized_schwarz=False,
        run_kind="full-solve",
        allow_swap=False,
        polarization_kind="s",
        mpi_size=8,
        task035d_case097_gate=False,
    )
    result = watchdog._qualify(
        args=args,
        solver_summary={
            "matrix_stats": {"matrix_rows": 1, "matrix_nnz_used": 1},
            "polarization_kind": "s",
        },
        events=[],
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        terminated_for_authority_unreadable=False,
        no_swap=True,
        observed_worker_rank_count=8,
    )
    assert not result["pass"]


def test_task037_extra_g0_snapshot_observer_filters_requested_iterations(tmp_path):
    calls = []
    records = {}
    comm = SimpleNamespace(rank=0)

    def fake_writer(directory, residual, **kwargs):
        calls.append(
            {
                "directory": directory,
                "residual": residual,
                **kwargs,
            }
        )
        iteration = int(kwargs["iteration"])
        return {
            "manifest_filename": f"manifest_{iteration}.json",
            "manifest_sha256": f"hash-{iteration}",
        }

    observer = watchdog._task037_extra_g0_snapshot_observer(
        tmp_path,
        "a" * 40,
        comm,
        records,
        writer=fake_writer,
    )
    borrowed_residual = object()
    for iteration in (0, 10, 20):
        observer(iteration, borrowed_residual, 0.5, 0.25)

    assert [call["iteration"] for call in calls] == [0, 20]
    assert all(call["residual"] is borrowed_residual for call in calls)
    assert all(call["source_sha"] == "a" * 40 for call in calls)
    assert set(records) == {"0", "20"}
    assert records["0"]["sha256"] == "hash-0"
    assert records["20"]["sha256"] == "hash-20"


def test_task037_extra_g0_flag_reaches_only_m3a_wrapper(tmp_path, monkeypatch):
    class Comm:
        rank = 0

        def tompi4py(self):
            return self

    request = SimpleNamespace(operator=SimpleNamespace(getComm=lambda: Comm()))
    captured = []
    ordinary_captured = []

    def fake_m3a_core(_request, **kwargs):
        captured.append(kwargs)
        return object(), {
            "solver_profile": "never_materialized_owner_local_overlap0125_partition"
        }

    def fake_ordinary_core(_request, **kwargs):
        ordinary_captured.append(kwargs)
        return object(), {"solver_profile": "never_materialized_owner_local"}

    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_overlap0125_partition_fgmres",
        fake_m3a_core,
    )
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_static_condensed_fgmres",
        fake_ordinary_core,
    )

    for enabled in (True, False):
        solve = watchdog._task037_f3_assembled_fgmres_port(
            tmp_path,
            20,
            never_materialized=True,
            overlap0125_partition=True,
            task037_extra_g0_diagnostics=enabled,
            verified_clean_sha="b" * 40,
        )
        solve(request)

    assert [kwargs["task037_extra_g0_diagnostics"] for kwargs in captured] == [
        True,
        False,
    ]
    assert captured[0]["residual_snapshot_observer"] is not None
    assert captured[1]["residual_snapshot_observer"] is None

    ordinary_solve = watchdog._task037_f3_assembled_fgmres_port(
        tmp_path,
        20,
        never_materialized=True,
        verified_clean_sha="b" * 40,
    )
    ordinary_solve(request)
    assert "task037_extra_g0_diagnostics" not in ordinary_captured[0]
    assert "residual_snapshot_observer" not in ordinary_captured[0]


def test_task037_extra_g2_flag_reaches_only_m3a_wrapper(tmp_path, monkeypatch):
    class Comm:
        rank = 0

        def tompi4py(self):
            return self

    request = SimpleNamespace(operator=SimpleNamespace(getComm=lambda: Comm()))
    captured = []
    ordinary_captured = []

    def fake_m3a_core(_request, **kwargs):
        captured.append(kwargs)
        return object(), {
            "solver_profile": "never_materialized_owner_local_overlap0125_partition"
        }

    def fake_ordinary_core(_request, **kwargs):
        ordinary_captured.append(kwargs)
        return object(), {"solver_profile": "never_materialized_owner_local"}

    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_overlap0125_partition_fgmres",
        fake_m3a_core,
    )
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_static_condensed_fgmres",
        fake_ordinary_core,
    )

    for enabled in (True, False):
        solve = watchdog._task037_f3_assembled_fgmres_port(
            tmp_path,
            20,
            never_materialized=True,
            overlap0125_partition=True,
            task037_extra_g2_slab14_identity=enabled,
            task037_extra_g2_slab14_factor_inventory=enabled,
            verified_clean_sha="b" * 40,
        )
        solve(request)

    assert [kwargs["task037_extra_g2_slab14_identity"] for kwargs in captured] == [
        True,
        False,
    ]
    assert [
        kwargs["task037_extra_g2_slab14_factor_inventory"] for kwargs in captured
    ] == [True, False]
    ordinary_solve = watchdog._task037_f3_assembled_fgmres_port(
        tmp_path,
        20,
        never_materialized=True,
        verified_clean_sha="b" * 40,
    )
    ordinary_solve(request)
    assert "task037_extra_g2_slab14_identity" not in ordinary_captured[0]
    assert "task037_extra_g2_slab14_factor_inventory" not in ordinary_captured[0]


def test_task037_extra_g2_factor_lifecycle_uses_raw_progress_stages(
    tmp_path, monkeypatch
):
    class Comm:
        rank = 0

        def tompi4py(self):
            return self

        def gather(self, payload, root=0):
            assert root == 0
            return [payload]

    request = SimpleNamespace(operator=SimpleNamespace(getComm=lambda: Comm()))
    progress_events = []

    def write_progress(_run_dir, _comm, **kwargs):
        progress_events.append(kwargs)

    def fake_m3a_core(_request, **kwargs):
        observer = kwargs["lifecycle_observer"]
        assert observer is not None
        for event in (
            "g2_fullspace_matrix_assembly_started",
            "g2_fullspace_matrix_assembly_ready",
            "g2_fullspace_factor_setup_started",
            "g2_fullspace_factor_setup_ready",
        ):
            observer(event, {"event": event})
        return object(), {
            "solver_profile": "never_materialized_owner_local_overlap0125_partition"
        }

    monkeypatch.setattr(watchdog, "_write_progress_event", write_progress)
    monkeypatch.setattr(
        "src.solvers.static_condensed_iterative."
        "solve_never_materialized_overlap0125_partition_fgmres",
        fake_m3a_core,
    )
    solve = watchdog._task037_f3_assembled_fgmres_port(
        tmp_path,
        20,
        never_materialized=True,
        overlap0125_partition=True,
        lifecycle_enabled=True,
        task037_extra_g2_slab14_identity=True,
        task037_extra_g2_slab14_factor_inventory=True,
        verified_clean_sha="b" * 40,
    )
    solve(request)

    assert [item["stage"] for item in progress_events] == [
        "g2_fullspace_matrix_assembly_started",
        "g2_fullspace_matrix_assembly_ready",
        "g2_fullspace_factor_setup_started",
        "g2_fullspace_factor_setup_ready",
    ]
    assert all(
        item["extra"]["task037_g2_factor_inventory_lifecycle"] is True
        for item in progress_events
    )
    assert all(
        "task037_m0_lifecycle" not in item["extra"]
        and "m0_event" not in item["extra"]
        and "task037_m0_rank_ledgers_by_rank" not in item["extra"]
        for item in progress_events
    )

    progress_events.clear()
    ordinary_solve = watchdog._task037_f3_assembled_fgmres_port(
        tmp_path,
        20,
        never_materialized=True,
        overlap0125_partition=True,
        lifecycle_enabled=True,
        task037_extra_g2_slab14_identity=True,
        task037_extra_g2_slab14_factor_inventory=False,
        verified_clean_sha="b" * 40,
    )
    ordinary_solve(request)
    assert progress_events[0]["stage"] == "m0_g2_fullspace_matrix_assembly_started"
    assert progress_events[0]["extra"]["task037_m0_lifecycle"] is True
    assert progress_events[0]["extra"]["m0_event"] == (
        "g2_fullspace_matrix_assembly_started"
    )
    assert progress_events[0]["extra"]["task037_m0_rank_ledgers_by_rank"] == [
        {"event": "g2_fullspace_matrix_assembly_started"}
    ]


def test_task037_extra_g2_parser_is_exact_screen20_mpi1_scope(tmp_path):
    authority = (
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
        "global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json"
    )
    base = [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "1",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        authority,
        "--task035c-p6-preflight-sha256",
        "96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8",
        "--verified-clean-sha",
        "c" * 40,
        "--run-dir",
        str(tmp_path),
        "--task037-f3-screen",
        "20",
        "--warning-gib",
        "10",
        "--terminate-gib",
        "14",
        "--timeout-seconds",
        "1800",
        "--task037-m2c-never-materialized",
        "--task037-m3a-overlap0125-partition",
        "--task037-extra-g2-slab14-identity",
    ]
    args = watchdog._parse_args(base)
    assert args.task037_extra_g2_slab14_identity is True
    command = watchdog._worker_command(args, tmp_path)
    assert command.count("--task037-extra-g2-slab14-identity") == 1
    worker_args = watchdog._parse_args(command[command.index("--worker") :])
    assert worker_args.task037_extra_g2_slab14_identity is True
    contract = watchdog._worker_launch_contract(args)
    assert contract["task037_extra_g2_slab14_identity"] is True
    assert contract["task037_extra_g2_slab14_factor_inventory"] is False
    assert contract["verified_clean_sha"] == "c" * 40

    factor_args = watchdog._parse_args(
        base + ["--task037-extra-g2-slab14-factor-inventory"]
    )
    assert factor_args.task037_extra_g2_slab14_identity is True
    assert factor_args.task037_extra_g2_slab14_factor_inventory is True
    factor_command = watchdog._worker_command(factor_args, tmp_path)
    assert factor_command.count("--task037-extra-g2-slab14-identity") == 1
    assert factor_command.count("--task037-extra-g2-slab14-factor-inventory") == 1
    factor_worker_args = watchdog._parse_args(
        factor_command[factor_command.index("--worker") :]
    )
    assert factor_worker_args.task037_extra_g2_slab14_identity is True
    assert factor_worker_args.task037_extra_g2_slab14_factor_inventory is True
    factor_contract = watchdog._worker_launch_contract(factor_args)
    assert factor_contract["task037_extra_g2_slab14_factor_inventory"] is True

    factor_only = [
        item
        for item in base
        if item != "--task037-extra-g2-slab14-identity"
    ] + ["--task037-extra-g2-slab14-factor-inventory"]
    with pytest.raises(SystemExit):
        watchdog._parse_args(factor_only)

    for invalid in (
        base[: base.index("--mpi-size") + 1]
        + ["2"]
        + base[base.index("--mpi-size") + 2 :],
        base[: base.index("--task037-f3-screen") + 1]
        + ["100"]
        + base[base.index("--task037-f3-screen") + 2 :],
        [item for item in base if item != "--task037-m3a-overlap0125-partition"],
        base + ["--task037-extra-g0-diagnostics"],
    ):
        with pytest.raises(SystemExit):
            watchdog._parse_args(invalid)


def test_task037_extra_g0_parser_is_exact_screen20_mpi1_scope(tmp_path):
    authority = (
        "benchmarks/cases/095_high_order_local_hp_resource_envelope/records/"
        "global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json"
    )
    base = [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "1",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        authority,
        "--task035c-p6-preflight-sha256",
        "96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8",
        "--verified-clean-sha",
        "c" * 40,
        "--run-dir",
        str(tmp_path),
        "--task037-f3-screen",
        "20",
        "--warning-gib",
        "10",
        "--terminate-gib",
        "14",
        "--timeout-seconds",
        "1800",
        "--task037-m2c-never-materialized",
        "--task037-m3a-overlap0125-partition",
        "--task037-extra-g0-diagnostics",
    ]
    args = watchdog._parse_args(base)
    assert args.task037_extra_g0_diagnostics is True
    command = watchdog._worker_command(args, tmp_path)
    assert command.count("--task037-extra-g0-diagnostics") == 1
    assert command.count("--verified-clean-sha") == 1
    assert command[command.index("--verified-clean-sha") + 1] == "c" * 40
    worker_args = watchdog._parse_args(command[command.index("--worker") :])
    assert worker_args.worker is True
    assert worker_args.task037_extra_g0_diagnostics is True
    contract = watchdog._worker_launch_contract(args)
    assert contract["task037_extra_g0_diagnostics"] is True
    assert contract["verified_clean_sha"] == "c" * 40

    for invalid in (
        base[: base.index("--mpi-size") + 1]
        + ["2"]
        + base[base.index("--mpi-size") + 2 :],
        base[: base.index("--task037-f3-screen") + 1]
        + ["100"]
        + base[base.index("--task037-f3-screen") + 2 :],
        base + ["--poll-interval", "0.1"],
        [item for item in base if item != "--task037-m3a-overlap0125-partition"],
    ):
        with pytest.raises(SystemExit):
            watchdog._parse_args(invalid)
