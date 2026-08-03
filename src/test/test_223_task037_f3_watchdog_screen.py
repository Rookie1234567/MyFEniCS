import json
from types import SimpleNamespace

import pytest

from benchmarks import run_task033_full3d_watchdog as watchdog


def _audit(screen_iterations=20):
    middle_iteration = 10 if screen_iterations == 20 else 60
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
    valid = []
    for screen_iterations in (20, 100):
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
    bad_iterations = valid.copy()
    bad_iterations[bad_iterations.index("--task037-f3-screen") + 1] = "200"
    missing_caps = valid.copy()
    for option in ("--warning-gib", "--terminate-gib", "--timeout-seconds"):
        index = missing_caps.index(option)
        del missing_caps[index : index + 2]
    for invalid in (
        bad_iterations,
        missing_caps,
        valid + ["--task037-f0-vector-observer"],
    ):
        with pytest.raises(SystemExit):
            watchdog._parse_args(invalid)


def test_worker_factory_writes_rank0_artifacts(tmp_path, monkeypatch):
    iterations_seen = []
    comm = SimpleNamespace(rank=0)
    petsc_comm = SimpleNamespace(tompi4py=lambda: comm)
    request = SimpleNamespace(
        A=SimpleNamespace(getComm=lambda: petsc_comm),
    )

    def fake_core(request, *, screen_iterations, residual_observer):
        iterations_seen.append(screen_iterations)
        for iteration in (0, 10, 20):
            residual_observer(iteration, 1.0 / (iteration + 1), 0.5)
        return object(), {"core": "audit"}

    def stage(*_args, **kwargs):
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
    args = SimpleNamespace(
        run_dir=tmp_path,
        task037_f0_vector_observer=False,
        task037_f1_direct_trace_oracle=None,
        task037_f1_direct_trace_sha256=None,
        task037_f3_screen=100,
        task035d_nested_p_dwr_phase=None,
        task035d_selective_face_dwr_phase=None,
    )
    assert watchdog._worker(args) == 0
    assert iterations_seen == [100]
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


def test_f3_qualification_uses_core_audit_gate():
    args = SimpleNamespace(
        task037_f3_screen=20,
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
    bad_trend = _audit(100)
    bad_trend["reported_history"][-1][1] = 0.5
    assert not watchdog._task037_f3_screen_gate(bad_trend, 100)["screen_100"]
    bad_residual = _audit(100)
    bad_residual["reported_history"][-1][1] = 0.31
    bad_residual["condensed_true_samples"][-1][1] = 0.31
    bad_residual["final"].update(
        reported_relative_residual=0.31,
        condensed_true_residual=0.31,
        full_augmented_true_residual=0.31,
    )
    assert not watchdog._task037_f3_screen_gate(bad_residual, 100)["screen_100"]
    bad = _audit()
    bad["reported_history"][1][1] = 11.0
    assert not watchdog._task037_f3_screen_gate(bad, 20)["finite_and_scale"]
    assert not watchdog._qualify(
        **qualify_kwargs,
        task037_f3_core_audit=bad,
    )["pass"]


def test_ordinary_full_solve_rules_remain_strict():
    args = SimpleNamespace(
        task037_f3_screen=None,
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
