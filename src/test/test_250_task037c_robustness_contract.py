from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from benchmarks import run_task037b_hybrid_iterative as iterative_runner
from benchmarks import run_task037b_hybrid_iterative_watchdog as watchdog
from benchmarks.task037c_robustness import (
    TASK37C_FORMAL_MPI,
    TASK37C_PHI_VALUES,
    TASK37C_TRACTION_MODELS,
    canonical_mode_key,
    choose_m_robust,
    classify_mpi_resource,
    direction_s_phase_audit,
    make_task37c_profile,
    mode_identity_audit,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d


def test_profile_and_angle_contract() -> None:
    profile = make_task37c_profile(-5.0, 160, 1)
    assert profile.incident_grazing_deg == 1.0
    assert profile.incident_phi_deg == -5.0
    assert profile.requested_modes == 160
    assert profile.candidate_modes == 320
    assert profile.mpi_size == 1
    for phi in TASK37C_PHI_VALUES:
        audit = direction_s_phase_audit(phi)
        assert audit["theta_deg"] == 89.0
        assert audit["pass"]
        assert audit["direction_unit"] and audit["s_unit"] and audit["orthogonal"]


@pytest.mark.parametrize(
    "args",
    [
        (1.0, 120, 8),
        (0.0, 80, 8),
        (5.0, 120, 2),
    ],
)
def test_invalid_profile_choices_fail_closed(args: tuple[float, int, int]) -> None:
    with pytest.raises(ValueError):
        make_task37c_profile(*args)


def test_dynamic_mode_identity_is_not_40_locked() -> None:
    modes = [
        {
            "side": "bottom",
            "m": index,
            "n": -index,
            "polarization": "s",
            "beta": 1.0 + 0.1j * index,
            "propagating": True,
            "rayleigh_warning": False,
        }
        for index in range(6)
    ]
    audit = mode_identity_audit(modes, expected_count=6)
    assert audit["count"] == 6
    assert audit["keys_unique"] and audit["beta_finite"] and audit["pass"]
    assert canonical_mode_key(modes[0]) == ("bottom", 0, 0, "s")


@pytest.mark.parametrize("phi, expected_count", [(-5.0, 42), (0.0, 40), (5.0, 42)])
def test_real_stage4_enumerator_drives_each_side_count(
    phi: float, expected_count: int
) -> None:
    cfg = target_stage4_config(degree=6, h_nm=10.0)
    cfg.incident_theta_deg = 89.0
    cfg.incident_phi_deg = phi
    cfg.polarization_kind = "s"
    modes = outgoing_port_modes_3d(cfg)
    for side in ("bottom", "top"):
        side_modes = [mode for mode in modes if mode.side == side]
        audit = mode_identity_audit(side_modes, expected_count=expected_count)
        assert audit["pass"]
        assert audit["count"] == expected_count
        if phi == -5.0:
            assert (side, -4, 2, "s") in audit["keys"]
        if phi == 5.0:
            assert (side, -4, -2, "s") in audit["keys"]


def test_m_selection_is_separate_from_comparison() -> None:
    m120 = [
        {
            "phi_deg": phi,
            "direct_pass": True,
            "m120_vs_m160_pass": True,
            "full3d_pass": True,
        }
        for phi in TASK37C_PHI_VALUES
    ]
    m160 = [
        {"phi_deg": phi, "direct_pass": True, "full3d_pass": True}
        for phi in TASK37C_PHI_VALUES
    ]
    assert choose_m_robust(m120, m160)["selected_m_robust"] == 120
    assert (
        choose_m_robust([{**row, "m120_vs_m160_pass": False} for row in m120], m160)[
            "selected_m_robust"
        ]
        == 160
    )
    assert (
        choose_m_robust([{**row, "direct_pass": False} for row in m120], m160)[
            "selected_m_robust"
        ]
        == 160
    )
    assert (
        choose_m_robust(
            m120,
            [{**row, "direct_pass": False} for row in m160],
        )["selected_m_robust"]
        == 120
    )
    assert (
        choose_m_robust(
            [{**row, "direct_pass": False} for row in m120],
            [{**row, "direct_pass": False} for row in m160],
        )["selected_m_robust"]
        is None
    )


def test_resource_classification_separates_numerics() -> None:
    mpi8 = classify_mpi_resource(
        mpi_size=8, numerical_pass=True, rss_mib=7000.0, swap_mib=0.0
    )
    mpi1 = classify_mpi_resource(
        mpi_size=1, numerical_pass=True, rss_mib=6144.0, swap_mib=0.0
    )
    assert (
        mpi8["numerical_pass"] and not mpi8["preferred_pass"] and not mpi8["hard_stop"]
    )
    assert mpi1["hard_stop"]
    assert (
        classify_mpi_resource(
            mpi_size=1, numerical_pass=False, rss_mib=1400.0, swap_mib=0.0
        )["numerical_pass"]
        is False
    )
    assert TASK37C_FORMAL_MPI == (1, 8)
    assert math.isfinite(mpi1["rss_mib"])


def test_task37c_cfg_and_side_identity_are_online_gate_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = make_task37c_profile(0.0, 120, 8)
    residuals = {
        key: 1.0e-12
        for key in (
            "reported_relative_residual",
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        )
    }

    def make_mode(side: str, *, beta: complex = 1.0 + 0.0j, m: int = 0):
        return SimpleNamespace(
            side=side,
            m=m,
            n=0,
            polarization="s",
            beta=beta,
            propagating=True,
            rayleigh_warning=False,
        )

    def make_record(
        bottom_modes: list[object],
        *,
        cfg_pass: bool,
    ) -> dict[str, object]:
        monkeypatch.setattr(
            iterative_runner,
            "_task37c_config_audit",
            lambda _setup, _profile: {"pass": cfg_pass},
        )
        result = SimpleNamespace(
            postsolve_audit={"pass": True, **residuals},
            iterations=10,
            converged_reason=1,
            history=[],
            history_evaluation_count=1,
            postsolve_evaluation_count=1,
        )
        linear = SimpleNamespace(
            result=result,
            linear_pass=True,
            inventory={},
            timings={},
            release={"pass": True},
        )
        recovery = SimpleNamespace(reports={}, timings={}, recovery_pass=True)
        physics = SimpleNamespace(
            port_power={},
            traction={},
            interface_continuity={},
            absorption={},
            external_orders=[],
            order_audit={},
            energy={},
            own_grid=None,
            canonical={},
            cleanup={},
            timings={},
            own_physics_pass=True,
            canonical_pass=True,
            physics_pass=True,
        )
        setup = SimpleNamespace(
            bottom=SimpleNamespace(external_modes=bottom_modes),
            top=SimpleNamespace(external_modes=[make_mode("top")]),
        )
        return iterative_runner.build_frozen_m10_online_record(
            case_label="task037c_test",
            source_before={},
            source_after={"clean": True, "matches_verified_clean_sha": True},
            authority_bindings={},
            lifecycle={"pass": True},
            linear=linear,
            recovery=recovery,
            physics=physics,
            final_release={"pass": True},
            profile=profile,
            setup=setup,
        )

    assert make_record([make_mode("bottom")], cfg_pass=True)["online_pass"] is True
    assert make_record([make_mode("bottom")], cfg_pass=False)["online_pass"] is False
    assert (
        make_record([make_mode("bottom"), make_mode("bottom")], cfg_pass=True)[
            "online_pass"
        ]
        is False
    )
    assert (
        make_record([make_mode("bottom", beta=math.inf + 0.0j)], cfg_pass=True)[
            "online_pass"
        ]
        is False
    )
    assert make_record([], cfg_pass=True)["online_pass"] is False


def _iterative_task37c_args(tmp_path, *, exact: bool = False) -> list[str]:
    args = [
        "--task037c-robustness-gate",
        "--case-label",
        "task037c_parser_test",
        "--run-dir",
        str(tmp_path / "run"),
        "--output",
        str(tmp_path / "online.json"),
        "--verified-clean-sha",
        "a" * 40,
        "--incident-phi-deg",
        "-5",
        "--requested-modes",
        "160",
        "--mpi-size",
        "8",
    ]
    if exact:
        args.extend(["--internal-traction-model", TASK37C_TRACTION_MODELS[1]])
    return args


def _watchdog_task37c_args(tmp_path, *, exact: bool = False) -> list[str]:
    args = [
        "--task037c-robustness-gate",
        "--case-label",
        "task037c_watchdog_parser_test",
        "--run-root",
        str(tmp_path / "root"),
        "--output",
        str(tmp_path / "watchdog.json"),
        "--verified-clean-sha",
        "a" * 40,
        "--incident-phi-deg",
        "-5",
        "--requested-modes",
        "160",
        "--mpi-size",
        "8",
    ]
    if exact:
        args.extend(["--internal-traction-model", TASK37C_TRACTION_MODELS[1]])
    return args


def _frozen_iterative_args(tmp_path) -> list[str]:
    return [
        "--frozen-m10",
        "--case-label",
        "frozen_parser_test",
        "--run-dir",
        str(tmp_path / "frozen-run"),
        "--output",
        str(tmp_path / "frozen.json"),
        "--verified-clean-sha",
        "a" * 40,
        "--h1-authority",
        str(tmp_path / "h1.json"),
        "--h1-authority-sha256",
        "b" * 64,
        "--full3d-reference",
        str(tmp_path / "full3d.json"),
        "--full3d-reference-sha256",
        "c" * 64,
        "--task035c-p6-preflight-authority",
        str(tmp_path / "p6.json"),
        "--task035c-p6-preflight-sha256",
        "d" * 64,
    ]


def _frozen_watchdog_args(tmp_path) -> list[str]:
    args = _frozen_iterative_args(tmp_path)
    run_root_index = args.index("--run-dir")
    args[run_root_index] = "--run-root"
    args[run_root_index + 1] = str(tmp_path / "frozen-root")
    return args


def test_task37c_exact_traction_model_propagates_to_worker_and_record(
    tmp_path,
) -> None:
    exact = TASK37C_TRACTION_MODELS[1]
    runner_args = iterative_runner.parse_args(
        _iterative_task37c_args(tmp_path, exact=True)
    )
    profile = iterative_runner.profile_from_args(runner_args)
    assert profile.internal_traction_model == exact
    assert iterative_runner.profile_record(profile)["internal_traction_model"] == exact

    watchdog_args = watchdog.parse_args(_watchdog_task37c_args(tmp_path, exact=True))
    command = watchdog.build_worker_command(
        watchdog_args,
        tmp_path / "payload",
        tmp_path / "online.json",
        tmp_path / "memory.json",
    )
    model_index = command.index("--internal-traction-model")
    assert command[model_index + 1] == exact
    assert watchdog_args.internal_traction_model == profile.internal_traction_model


def test_task37c_traction_model_defaults_and_frozen_rejection(tmp_path) -> None:
    assert (
        iterative_runner.profile_from_args(
            iterative_runner.parse_args(_iterative_task37c_args(tmp_path))
        ).internal_traction_model
        == TASK37C_TRACTION_MODELS[0]
    )
    assert (
        watchdog.parse_args(_watchdog_task37c_args(tmp_path)).internal_traction_model
        == TASK37C_TRACTION_MODELS[0]
    )
    with pytest.raises(SystemExit):
        iterative_runner.parse_args(
            _frozen_iterative_args(tmp_path)
            + ["--internal-traction-model", TASK37C_TRACTION_MODELS[1]]
        )
    with pytest.raises(SystemExit):
        watchdog.parse_args(
            _frozen_watchdog_args(tmp_path)
            + ["--internal-traction-model", TASK37C_TRACTION_MODELS[1]]
        )
    with pytest.raises(ValueError):
        make_task37c_profile(0.0, 120, 8, traction_model="not-a-model")


def test_exact_one_cell_work_dir_is_opt_in_and_run_scoped(tmp_path) -> None:
    exact_profile = make_task37c_profile(
        -5.0,
        120,
        8,
        traction_model=TASK37C_TRACTION_MODELS[1],
    )
    run_dir = tmp_path / "payload"
    assert iterative_runner._exact_one_cell_work_dir(exact_profile, run_dir) == (
        run_dir.resolve() / "exact_one_cell"
    )

    scalar_profile = make_task37c_profile(0.0, 120, 8)
    assert iterative_runner._exact_one_cell_work_dir(scalar_profile, run_dir) is None
    assert (
        iterative_runner._exact_one_cell_work_dir(
            iterative_runner.FROZEN_M10,
            run_dir,
        )
        is None
    )
