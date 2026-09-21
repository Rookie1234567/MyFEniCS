"""Minimal V25 input and worker-dispatch contracts."""

from pathlib import Path

from src.io import load_and_resolve
from src.io.physical_intermediate_profile import (
    COARSE_DEGREE_SPEED_PROFILE,
    profile_facts,
)
from src.io.run_specification import thaw
from src.runners import task038_full3d_iterative as dispatch


ROOT = Path(__file__).resolve().parents[2]


def test_v25_inputs_bind_direct_coarse_degree_to_each_stage():
    expected = {
        "v25_q4_speed_h7p5.dat": ("Q4_ORIGINAL", 4),
        "v25_q3_speed_h7p5.dat": ("Q3_ORIGINAL", 3),
        "v25_q2_speed_h7p5.dat": ("Q2_ORIGINAL", 2),
    }
    facts = profile_facts(COARSE_DEGREE_SPEED_PROFILE)
    for name, (stage, degree) in expected.items():
        specification = load_and_resolve(ROOT / "input/task39extra" / name)
        assert specification.solver["preconditioner"] == COARSE_DEGREE_SPEED_PROFILE
        assert specification.solver["stage"] == stage
        assert specification.solver["coarse_degree"] == degree
        assert specification.solver["physical_operator_backend"] == (
            "isotropic_sum_factorized_n1e_v26"
        )
        assert specification.solver["h6_backend_rule"] == (
            "isotropic_sum_factorized_n1e_v26_apply_and_power10"
        )
        assert specification.solver["thread_contract"] == "mpi1_omp1_blas1_v25"
        assert specification.as_jsonable()["derived"]["physical_intermediate_profile"] == thaw(facts)


def test_v24_resolved_identity_does_not_gain_v25_backend_fields():
    specification = load_and_resolve(
        ROOT / "input/task39extra/v24_laptop_speed_original_h7p5.dat"
    )
    assert all(
        key not in specification.solver
        for key in (
            "physical_operator_backend",
            "h6_backend_rule",
            "thread_contract",
        )
    )


def test_v25_worker_dispatch_keeps_explicit_stage_degree(monkeypatch, tmp_path):
    specification = load_and_resolve(
        ROOT / "input/task39extra/v25_q3_speed_h7p5.dat"
    )
    captured = {}

    def fake_runner(payload, run_directory, **kwargs):
        captured.update(kwargs)
        captured["payload"] = payload
        captured["run_directory"] = run_directory
        return {"passed": False, "errors": ["dispatch probe"]}

    from src.runners import physical_dual_cell_condensed_lowmem_v20 as lowmem

    monkeypatch.setattr(lowmem, "_run_physical_dual_cell_condensed_lowmem", fake_runner)
    result = dispatch.run_full3d_iterative(
        specification.as_jsonable(), tmp_path, source_sha="s" * 40
    )
    assert result["errors"] == ["dispatch probe"]
    assert captured["coarse_degree"] == 3
    assert captured["allowed_stages"] == (
        "Q4_ORIGINAL",
        "Q3_ORIGINAL",
        "Q2_ORIGINAL",
    )
    assert captured["evidence_prefix"] == "v25q3"
    assert captured["profile_identity"] == COARSE_DEGREE_SPEED_PROFILE


def test_v25_public_launcher_accepts_observe_only_policy(capsys):
    from scripts.run_case import main as run_case_main

    assert run_case_main(
        [
            str(ROOT / "input/task39extra/v25_q4_speed_h7p5.dat"),
            "--validate-only",
            "--v14-time-policy",
            "observe_only",
        ]
    ) == 0
    capsys.readouterr()
