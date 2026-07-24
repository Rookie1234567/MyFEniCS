"""Tests for the pure Task035b h10/p7 controlled-stop gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.task035b_p7_capability_resource_gate import (
    _base_trace_schur_nnz,
    _verified_source_identity,
    build_p7_capability_resource_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gate_record() -> dict[str, object]:
    sha = "a" * 40
    return build_p7_capability_resource_gate(
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
    )


def test_p7_gate_is_valid_controlled_stop_without_pde(
    gate_record: dict[str, object],
) -> None:
    assert gate_record["pass"] is True
    assert (
        gate_record["status"]
        == "p7_not_run_by_capability_or_resource_gate"
    )
    pde = gate_record["pde"]
    assert pde == {
        "status": "not_run",
        "heavy_case_started": False,
        "mesh_built": False,
        "form_compiled": False,
        "matrix_assembled": False,
        "factorization_started": False,
        "solver_failure": False,
    }
    qualification = gate_record["qualification"]
    assert qualification["evidence_valid"] is True
    assert qualification["candidate_capability_pass"] is False
    assert qualification["candidate_resource_pass"] is False
    assert qualification["p7_pde_authorized"] is False
    assert (
        gate_record["decision"]["ordinary_default_changed"] is False
    )


def test_p7_raw_basix_exists_but_qualified_floquet_stops(
    gate_record: dict[str, object],
) -> None:
    capability = gate_record["capability_gate"]
    raw = capability["raw_basix_layout"]
    assert raw["available"] is True
    assert raw["element_dimension"] == 1344
    assert raw["edge_dofs_per_entity"] == 7
    assert raw["face_dofs_per_entity"] == 84
    assert raw["cell_interior_dofs_per_entity"] == 756
    assert raw["local_trace_dimension"] == 588
    assert capability["candidate_capability_pass"] is False
    assert (
        capability["qualified_trace_layout_probe"]["rejected"] is True
    )
    assert (
        capability["fixed_target_floquet_dispatcher_probe"]["rejected"]
        is True
    )
    assert (
        capability["explicit_p7_floquet_mode_probe"]["rejected"] is True
    )


def test_h10_p7_row_and_nnz_projection_is_frozen(
    gate_record: dict[str, object],
) -> None:
    resources = gate_record["resource_gate"]
    rows = resources["row_projection"]
    assert rows == {
        "full3d_equivalent_dofs": 273581,
        "full_trace_rows_before_floquet": 83069,
        "floquet_slave_rows_projected": 12509,
        "periodic_independent_trace_rows": 70560,
        "dtn_auxiliary_rows": 80,
        "active_matrix_rows_with_dtn": 70640,
        "full3d_equivalent_dof_limit": 90000,
        "dof_limit_excess": 183581,
        "dof_to_limit_ratio": pytest.approx(3.039788888888889),
    }
    matrix = resources["matrix_projection"]
    assert matrix["base_trace_schur_nnz_exact_topology"] == 77905296
    assert matrix["dtn_port_nnz_correction_projected"] == 188432
    assert matrix["matrix_nnz_used_projected"] == 78093728
    assert (
        matrix["matrix_nnz_conservative_structural_upper"]
        == 78190736
    )
    assert matrix["maximum_base_row_width_exact"] == 1911
    assert matrix["peak_memory"] is None


def test_projection_reproduces_accepted_p4_p5_p6_anchors(
    gate_record: dict[str, object],
) -> None:
    calibration = gate_record["resource_gate"]["calibration"]
    assert [row["degree"] for row in calibration] == [4, 5, 6]
    assert [row["base_trace_schur_nnz_exact"] for row in calibration] == [
        8120448,
        20041200,
        41847840,
    ]
    assert [row["dtn_port_nnz_correction_measured"] for row in calibration] == [
        64016,
        99728,
        141200,
    ]
    assert [row["matrix_max_row_width_measured"] for row in calibration] == [
        612,
        965,
        1398,
    ]
    assert all(
        len(row["record_sha256"]) == 64 for row in calibration
    )
    assert all(all(row["checks"].values()) for row in calibration)


def test_periodic_trace_adjacency_is_degree_sensitive() -> None:
    assert _base_trace_schur_nnz((6, 3, 14), 4) == (8120448, 612)
    assert _base_trace_schur_nnz((6, 3, 14), 7) == (77905296, 1911)
    with pytest.raises(ValueError, match="too small"):
        _base_trace_schur_nnz((1, 1, 1), 7)


def test_cli_source_gate_fails_closed_on_wrong_sha() -> None:
    with pytest.raises(SystemExit, match="source gate failed"):
        _verified_source_identity(REPO_ROOT, "0" * 40)


def test_builder_rejects_unqualified_source_identity() -> None:
    record = build_p7_capability_resource_gate(
        REPO_ROOT,
        source={
            "commit_sha": "0" * 40,
            "verified_clean_sha": "1" * 40,
            "branch": "wrong",
            "checks": {},
        },
    )
    assert record["pass"] is False
    assert record["status"] == "p7_gate_evidence_invalid"
    assert (
        record["qualification"]["checks"][
            "clean_source_identity_hash_bound"
        ]
        is False
    )


def test_record_is_json_serializable(
    gate_record: dict[str, object],
) -> None:
    encoded = json.dumps(gate_record, ensure_ascii=False)
    assert "p7_not_run_by_capability_or_resource_gate" in encoded
