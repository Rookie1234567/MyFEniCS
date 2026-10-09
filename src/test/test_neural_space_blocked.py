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


def test_checker_dedicated_parent_with_existing_child(tmp_path):
    import subprocess
    import sys
    from time import monotonic
    from src.runners.saved_field_supervision import run_checker

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        summary = run_checker(
            [sys.executable, "-c", "print('SAVED_CHECKER_FIXTURE')"],
            tmp_path / "checker",
            monotonic() + 30,
            "fixture",
        )
        assert summary["classification"] == "COMPLETED"
        assert summary["descendants_cleared"] and child.poll() is None
        assert summary["rss_hard_limit_bytes"] == 2 * 2**30
    finally:
        child.terminate()
        child.wait()


def test_completed_verifier_binding_and_corruption(tmp_path, monkeypatch):
    import json
    import numpy as np
    import pytest
    from src.io.neural_wave_campaign import digest
    from src.runners import neural_space_verification as verify
    from src.io import neural_wave_backfit_store as store

    monkeypatch.setattr(verify, "ROOT", tmp_path)
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    model = tmp_path / "model.json"
    model.write_text("{}")
    state = tmp_path / "state.npz"
    c = np.zeros(31968, np.complex128)
    np.savez(state, c=c)
    boundary = dict(state=dict(path=str(state)), binding=dict(source_sha="physical"))
    monkeypatch.setattr(store, "check_boundary", lambda _: boundary)
    record = dict(model=dict(path="model.json", sha256=digest(model)))
    for path in ("raw.npz", "oracle.json", "design.json"):
        (tmp_path / path).write_text("fixture")
    np.savez(artifact / "route_rebuild.npz", c30=c, c60=c, saved=c)
    recon = dict(
        committed_boundary_sha256=digest(model), candidate_source_sha="physical"
    )
    frozen = dict(
        verification_complete=True,
        same_p3_reference_sha256="reference",
        reference_solve_count=0,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        reconstruction={"name_ORACLE": recon, "name_ORACLE_PRODUCER": recon},
        raw_complete_fields=dict(path="raw.npz", sha256=digest(tmp_path / "raw.npz")),
    )
    file = artifact / "verifier_result.json"
    file.write_text(json.dumps(frozen))
    args = (
        artifact,
        tmp_path / "oracle.json",
        tmp_path / "design.json",
        record,
        "name",
        "route",
        dict(reference=dict(sha256="reference")),
    )
    first = verify.freeze_blocked_verifier(*args)
    assert verify.freeze_blocked_verifier(*args) == first
    frozen["reconstruction"]["name_ORACLE"]["candidate_source_sha"] = "other"
    file.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="MODEL_REFERENCE_IDENTITY"):
        verify.freeze_blocked_verifier(*args)
    frozen["reconstruction"]["name_ORACLE"]["candidate_source_sha"] = "physical"
    frozen["same_p3_reference_sha256"] = "teacher_other_case"
    file.write_text(json.dumps(frozen))
    with pytest.raises(ValueError, match="MODEL_REFERENCE_IDENTITY"):
        verify.freeze_blocked_verifier(*args)
    frozen["same_p3_reference_sha256"] = "reference"
    file.write_text(json.dumps(frozen))
    (tmp_path / "raw.npz").write_text("corrupted")
    with pytest.raises(ValueError, match="RAW_FIELDS_HASH"):
        verify.freeze_blocked_verifier(*args)
