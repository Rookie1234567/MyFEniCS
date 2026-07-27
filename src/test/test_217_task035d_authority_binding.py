from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CASE_DIR = (
    ROOT
    / "benchmarks"
    / "cases"
    / "097_goal_oriented_exact_sequence_hp_adaptivity"
)
RECORDS = CASE_DIR / "records"
OUTER_CANDIDATE_ID = "h15_outer_top_periodic_p5fine_v1"
OUTER_MPI1 = RECORDS / "outer_top_periodic_p5fine_mpi1_v2.json"
DEFAULT_MPI1 = (
    RECORDS / "local_h_production_mpi1_v3_owner_gate_fix1.json"
)
SELECTIVE_MPI1 = RECORDS / "selective_p6_face_mpi1_v1.json"
COMPACT = RECORDS / "selective_face_selection_compact_v1.json"
PREFLIGHT = (
    RECORDS / "bounded_single_seed_top_air_hp_preflight_v1.json"
)


def _module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CASE_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failures(
    checker,
    path: Path,
    payload: dict,
    candidate_id: str,
) -> list[str]:
    return checker._validate_one(
        path,
        payload,
        candidate_id=candidate_id,
        spec=checker.CANDIDATE_SPECS[candidate_id],
    )


def test_component_checker_binds_plan_degree_and_p5_only_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = _module(
        "task035d_authority_binding_checker",
        "check_local_h_production_authority.py",
    )
    payload = json.loads(OUTER_MPI1.read_text(encoding="utf-8"))
    assert (
        _failures(
            checker,
            OUTER_MPI1,
            payload,
            OUTER_CANDIDATE_ID,
        )
        == []
    )

    degree_mutation = copy.deepcopy(payload)
    degree_mutation["stable_identity"][
        "geometry_canonical_entity_degree_sha256"
    ] = "0" * 64
    degree_mutation["reduction_audit"]["degree_plan"][
        "geometry_canonical_entity_degree_sha256"
    ] = "0" * 64
    assert "degree_identity" in _failures(
        checker,
        OUTER_MPI1,
        degree_mutation,
        OUTER_CANDIDATE_ID,
    )

    plan_path = ROOT / checker.CANDIDATE_SPECS[
        OUTER_CANDIDATE_ID
    ]["plan_relative"]
    mutated_plan = copy.deepcopy(payload["plan"]["payload"])
    mutated_plan["provenance"]["purpose"] = "self-consistent live drift"
    fake_live_sha = "1" * 64
    plan_mutation = copy.deepcopy(payload)
    plan_mutation["plan"]["file_sha256"] = fake_live_sha
    plan_mutation["plan"]["payload"] = mutated_plan
    real_strict_load = checker._strict_load
    real_sha256 = checker._sha256
    monkeypatch.setattr(
        checker,
        "_strict_load",
        lambda path: (
            mutated_plan
            if Path(path).resolve() == plan_path.resolve()
            else real_strict_load(path)
        ),
    )
    monkeypatch.setattr(
        checker,
        "_sha256",
        lambda path: (
            fake_live_sha
            if Path(path).resolve() == plan_path.resolve()
            else real_sha256(path)
        ),
    )
    assert "plan_source_identity" in _failures(
        checker,
        OUTER_MPI1,
        plan_mutation,
        OUTER_CANDIDATE_ID,
    )
    monkeypatch.undo()

    trace_mutation = copy.deepcopy(payload)
    trace_mutation["reduction_audit"]["physical_trace"][
        "selected_p6_face_count"
    ] = 1
    assert "p5_only_trace_scope" in _failures(
        checker,
        OUTER_MPI1,
        trace_mutation,
        OUTER_CANDIDATE_ID,
    )


def test_uniform_and_selective_face_historical_components_still_pass() -> None:
    checker = _module(
        "task035d_historical_authority_checker",
        "check_local_h_production_authority.py",
    )
    for path, candidate_id in (
        (DEFAULT_MPI1, checker.DEFAULT_CANDIDATE_ID),
        (SELECTIVE_MPI1, checker.SELECTIVE_FACE_CANDIDATE_ID),
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert _failures(checker, path, payload, candidate_id) == []


def test_compact_dwr_rejects_a_wholly_missing_x_band() -> None:
    analyzer = _module(
        "task035d_all_band_selection",
        "analyze_bounded_single_seed_top_air_hp_selection.py",
    )
    compact = json.loads(COMPACT.read_text(encoding="utf-8"))
    goals = copy.deepcopy(compact["goal_dwr"]["goals"])
    first = next(iter(goals.values()))
    omitted_band = analyzer._face_band(first["face_contributions"][0])
    first["face_contributions"] = [
        row
        for row in first["face_contributions"]
        if analyzer._face_band(row) != omitted_band
    ]
    with pytest.raises(ValueError, match="two y faces per x band"):
        analyzer._paired_contributions(goals)


def test_preflight_catalog_rejects_closure_drift_at_fixed_dimensions() -> None:
    analyzer = _module(
        "task035d_preflight_catalog_checker",
        "analyze_bounded_single_seed_top_air_hp_selection.py",
    )
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    assert analyzer._preflight_catalog_identity(preflight) is True
    mutation = copy.deepcopy(preflight)
    mutation["action_rows"]["left_grating_top"]["closure_counts"][
        "material"
    ] = 3
    mutation["action_rows"]["left_grating_top"]["closure_counts"][
        "balance"
    ] = 1
    assert analyzer._preflight_catalog_identity(mutation) is False
