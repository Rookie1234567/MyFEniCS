from __future__ import annotations

from benchmarks import run_task033_full3d_watchdog as watchdog
from src.solvers.dtn_port_3d import Stage4NeverMaterializedLinearSolverPort


def _m3a_args(tmp_path):
    return watchdog._parse_args(
        [
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
            str(tmp_path / "authority.json"),
            "--task035c-p6-preflight-sha256",
            "0" * 64,
            "--verified-clean-sha",
            "1" * 40,
            "--task037-m3a-overlap0125-partition",
            "--run-dir",
            str(tmp_path),
        ]
    )


def test_ordinary_defaults_leave_task037_lanes_disabled(tmp_path):
    args = watchdog._parse_args(
        [
            "--degree",
            "2",
            "--h-nm",
            "5",
            "--run-dir",
            str(tmp_path),
        ]
    )

    assert args.task037_e0_matrix_free_dtn_gate is False
    assert args.task037_m3a_overlap0125_partition is False
    contract = watchdog._worker_launch_contract(args)
    assert contract["task037_e0_matrix_free_dtn_gate"] is False
    assert contract["task037_m3a_overlap0125_partition"] is False


def test_m3a_worker_selects_action_port_and_canonical_retain_path(
    tmp_path, monkeypatch
):
    args = _m3a_args(tmp_path)
    captured = {}

    monkeypatch.setattr(watchdog, "_full3d_config", lambda _args: object())

    def fake_run(_cfg, _out_dir, **kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(
        "src.solvers.solve_maxwell_3d_stage_4b_block_grating.run_stage4b_block_grating_3d_case",
        fake_run,
    )

    assert watchdog._worker(args) == 0
    assert isinstance(
        captured["linear_solver_port"], Stage4NeverMaterializedLinearSolverPort
    )
    assert captured["solution_observer"] is not None
    assert captured["variable_p_live_observer"] is None
    assert captured["static_retain_local_schur_for_matrix_free"] is True
    assert captured["canonical_vector_export"] is True
    assert captured["matrix_free_dtn"] is False
    assert captured["matrix_free_dtn_probe"] is False
    assert watchdog.TASK037_M3A_MAX_ITERATIONS == 3000
