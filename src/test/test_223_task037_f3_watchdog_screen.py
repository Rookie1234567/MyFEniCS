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
    full_command = watchdog._worker_command(full, tmp_path)
    assert full_command.count("--task037-f3-full") == 1
    assert "--task037-f3-screen" not in full_command
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
    with pytest.raises(SystemExit):
        watchdog._parse_args(
            base + ["--task037-f3-screen", "20", "--task037-m4-p2-auxiliary"]
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
        task037_m4_p2_auxiliary=False,
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
        "core": "audit"
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
        task035d_nested_p_dwr_phase=None,
        task035d_selective_face_dwr_phase=None,
    )
    for m4 in (False, True):
        args = SimpleNamespace(
            **common_args,
            task037_m4_p2_auxiliary=m4,
        )
        assert watchdog._worker(args) == 0
    assert captured["retain"] is True
    assert isinstance(captured["port"], Stage4NeverMaterializedLinearSolverPort)
    assert captured["request"] is request
    assert captured["kwargs"]["screen_iterations"] == 20
    assert selected_profiles == ["m2c", "m4"]


def test_f3_qualification_uses_core_audit_gate():
    args = SimpleNamespace(
        task037_f3_screen=20,
        task037_f3_full=False,
        task037_f5b_released_profile=False,
        task037_m2c_never_materialized=False,
        task037_m4_p2_auxiliary=False,
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
        task037_m4_p2_auxiliary=False,
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
        task037_m4_p2_auxiliary=True,
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


def test_ordinary_full_solve_rules_remain_strict():
    args = SimpleNamespace(
        task037_f3_screen=None,
        task037_f3_full=False,
        task037_m2c_never_materialized=False,
        task037_m4_p2_auxiliary=False,
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
