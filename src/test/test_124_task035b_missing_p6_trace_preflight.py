"""Tests for the pure Task035b missing-p6-trace preflight generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.task035b_missing_p6_trace_preflight import (
    SOURCE_FILES,
    _environment_identity,
    _verified_source_identity,
    _write_record_exclusive,
    build_missing_p6_trace_preflight_record,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def preflight_record() -> dict[str, object]:
    environment = _environment_identity(REPO_ROOT)
    sha = "a" * 40
    return build_missing_p6_trace_preflight_record(
        REPO_ROOT,
        source={
            "commit_sha": sha,
            "verified_clean_sha": sha,
            "branch": (
                "codex/20260723-task35b-"
                "high-order-local-hp-resource-envelope"
            ),
            "tracked_source_dirty": False,
            "stable_and_clean_before": True,
            "checks": {"fixture_source_identity": True},
        },
        environment=environment,
    )


def test_preflight_freezes_complete_132_mode_audit(
    preflight_record: dict[str, object],
) -> None:
    assert preflight_record["pass"] is True
    assert (
        preflight_record["status"]
        == "missing_p6_trace_complement_preflight_pass"
    )
    inventory = preflight_record["missing_trace_mode_inventory"]
    assert inventory == {
        "reference_cell_missing_trace_modes": 132,
        "missing_edge_modes": 12,
        "missing_face_modes": 120,
        "missing_cell_interior_modes": 0,
        "edge_count": 12,
        "face_count": 6,
        "missing_modes_per_edge": [1] * 12,
        "missing_modes_per_face": [20] * 6,
    }
    audit = preflight_record["complement_audit"]
    assert audit["pass"] is True
    assert audit["retained_local_dimension"] == 750
    assert audit["enriched_local_dimension"] == 882
    assert audit["missing_local_trace_dimension"] == 132
    assert audit["direct_sum_rank"] == 882
    assert len(audit["retained_to_enriched_sha256"]) == 64
    assert len(audit["missing_to_enriched_sha256"]) == 64
    assert all(audit["checks"].values())


def test_preflight_is_explicitly_not_pde_not_candidate_not_dwr(
    preflight_record: dict[str, object],
) -> None:
    assert preflight_record["pde"] == {
        "status": "not_run",
        "heavy_case_started": False,
        "mesh_built": False,
        "form_compiled": False,
        "global_matrix_assembled": False,
        "factorization_started": False,
        "solver_started": False,
        "solver_failure": False,
    }
    semantics = preflight_record["diagnostic_semantics"]
    assert semantics["candidate_matrix_constructed"] is False
    assert (
        semantics["inactive_p6_rows_retained_in_candidate_matrix"]
        is False
    )
    assert semantics["actual_missing_trace_residual_computed"] is False
    assert (
        semantics["actual_missing_trace_adjoint_residual_computed"]
        is False
    )
    assert semantics["actual_dwr_indicator"] is False
    assert semantics["lane_b_formal_selection_authorized"] is False
    assert preflight_record["qualification"]["pass"] is True
    assert all(
        preflight_record["qualification"]["checks"].values()
    )


def test_environment_and_source_file_hashes_are_preserved(
    preflight_record: dict[str, object],
) -> None:
    environment = preflight_record["environment"]
    assert environment["pass"] is True
    assert all(environment["checks"].values())
    assert environment["petsc_scalar_type"] == "complex128"
    assert environment["petsc_int_type"] == "int32"
    assert environment["mpi_world_size"] == 1
    hashes = preflight_record["source_file_sha256"]
    assert set(hashes) == set(SOURCE_FILES)
    assert all(len(value) == 64 for value in hashes.values())


def test_record_is_json_serializable(
    preflight_record: dict[str, object],
) -> None:
    encoded = json.dumps(preflight_record, ensure_ascii=False)
    assert "missing_p6_trace_complement_preflight_pass" in encoded
    assert '"status": "not_run"' in encoded


def test_exclusive_writer_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "record.json"
    _write_record_exclusive(output, {"pass": True})
    with pytest.raises(FileExistsError):
        _write_record_exclusive(output, {"pass": False})
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "pass": True
    }


def test_cli_source_gate_fails_closed_on_wrong_sha() -> None:
    with pytest.raises(SystemExit, match="source gate failed"):
        _verified_source_identity(REPO_ROOT, "0" * 40)


def test_builder_rejects_unqualified_source_identity() -> None:
    record = build_missing_p6_trace_preflight_record(
        REPO_ROOT,
        source={
            "commit_sha": "0" * 40,
            "verified_clean_sha": "1" * 40,
            "branch": "wrong",
            "checks": {},
        },
        environment=_environment_identity(REPO_ROOT),
    )
    assert record["pass"] is False
    assert (
        record["status"]
        == "missing_p6_trace_complement_preflight_fail"
    )
    assert (
        record["qualification"]["checks"][
            "clean_source_identity_hash_bound"
        ]
        is False
    )
