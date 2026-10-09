from src.solvers.neural_space_blocked_checks import (
    fixture_cases,
    negative_cases,
    preservation_cases,
    real_panel_interruption_case,
)


def test_independent_whitened_complex_fixtures(tmp_path):
    rows = fixture_cases(tmp_path)
    assert len(rows) == 5
    assert rows[1]["retained_rank"] == 6
    assert not rows[1]["full_column_space_retained"]


def test_conjugate_transform_rank_and_identity_negatives(tmp_path):
    assert len(negative_cases(tmp_path)) == 5


def test_boundary_timeout_partial_atomic_and_empty(tmp_path):
    assert len(preservation_cases(tmp_path)) == 4


def test_actual_panel_interruption_and_resume(tmp_path):
    assert real_panel_interruption_case(tmp_path)["final_rank"] == 65


def test_v36_clock_is_independent_and_preserves_final_reserve():
    from src.runners.neural_wave_campaign import stage_deadline

    assert stage_deadline(
        dict(campaign_version=36, role="blocked_oracle"),
        dict(deadline_monotonic=12000),
        dict(deadline_monotonic=21600),
    ) == (12000, 1800)


def test_v36_stage_and_resource_roles():
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths
    from src.runners.block_wave_admission import pool, wait_limit

    spec = load_wave(ROOT / "input/task042extra_feinn_5nm/v36_learned_space_oracle.dat")
    assert spec["role"] == "blocked_oracle" and spec["campaign_version"] == 36
    assert profile_paths(spec)["root"].name == "v36"
    assert pool(profile_paths(spec)["root"]).parent.name == "v36"
    assert wait_limit(profile_paths(spec)["root"]) == 900


def test_oracle_writer_and_strict_policy(tmp_path):
    from src.solvers.neural_space_qualification import qualify

    # Reuse the small real writer/seal/reopen test; never an old expensive Gate.
    result = qualify(tmp_path, dict(source_sha="fixture", design_sha256="fixture"))
    assert result["actual_writer_seal_reopen"]
