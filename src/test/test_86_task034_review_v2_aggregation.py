from __future__ import annotations

import csv
from pathlib import Path

import pytest

from benchmarks.task034_review_v2_aggregation import COLUMNS, build


ROOT = Path(__file__).resolve().parents[2]


def test_all_model_results_schema_and_scope() -> None:
    result = build(ROOT)
    rows = result["rows"]
    assert result["row_count"] == 40
    assert all(list(row) == COLUMNS for row in rows)
    assert {row["polarization"] for row in rows} == {"s"}
    assert (
        sum(
            row["data_identity"]
            == "measured_mpi_identity_with_selected_baseline_physics"
            for row in rows
        ) == 8
    )
    assert sum(row["data_identity"] == "measured_mode_funnel" for row in rows) == 6
    assert result["identity"]["R00_p_semantics"] == (
        "cross-polarized p output under S incidence"
    )


def test_controlled_resource_and_timeout_statuses_are_fail_closed() -> None:
    rows = {row["case_key"]: row for row in build(ROOT)["rows"]}
    for key in (
        "supplemental_p2_h1_full3d",
        "supplemental_p3_h2_full3d",
        "supplemental_p4_h3_full3d",
    ):
        row = rows[key]
        assert row["status"] == "not_run_by_conservative_resource_gate_after_assembly"
        assert row["factor_nnz"] is None
        assert row["true_relative_residual"] is None
        assert "factorization_launched_false" in row[
            "full3d_hybrid_closure_status"
        ]
        assert "full_solve_launched_false" in row[
            "full3d_hybrid_closure_status"
        ]

    timeout = rows["supplemental_p2_h1_hybrid_m160"]
    assert timeout["status"] == "timeout_during_field_recovery_no_official_solution"
    assert timeout["total_seconds"] == 7200.0
    assert timeout["peak_memory_gib"] == 95.87872314453125
    assert timeout["swap_bytes"] == 0
    assert timeout["R_total"] is None
    assert timeout["true_relative_residual"] is None


def test_s_incidence_contains_cross_polarized_zero_order_output() -> None:
    rows = build(ROOT)["rows"]
    measured = [row for row in rows if row["R00_p"] is not None]
    assert measured
    assert all(row["polarization"] == "s" for row in measured)
    assert all(row["R00_total"] == row["R00_s"] + row["R00_p"] for row in measured)


def test_review_v2_authoritative_schema_bindings() -> None:
    rows = {row["case_key"]: row for row in build(ROOT)["rows"]}
    full = rows["case093_p3_h3_full3d"]
    hybrid = rows["case093_p3_h3_hybrid"]

    assert hybrid["total_seconds"] == pytest.approx(661.4100284820015)
    assert full["total_seconds"] == pytest.approx(1726.3617402129894)
    assert hybrid["total_seconds"] != full["total_seconds"]
    assert full["factor_nnz"] == 1_307_605_045
    assert hybrid["factor_nnz"] is None
    assert hybrid["external_aux_dofs"] == 80
    assert hybrid["total_rows"] == (
        hybrid["fe_dofs"]
        + hybrid["external_aux_dofs"]
        + hybrid["modal_unknowns"]
    )

    p3_funnel = sorted(
        (row["M_per_direction"], row["MPI"], row["total_seconds"])
        for row in rows.values()
        if row["case_key"].startswith("m_funnel_p3_h3")
    )
    assert p3_funnel == [
        (80, 8, pytest.approx(529.5561790400097)),
        (120, 8, pytest.approx(567.5734034569905)),
        (160, 8, pytest.approx(661.4100284820015)),
    ]

    repo_evidence = [
        row["evidence_path"]
        for row in rows.values()
        if row["evidence_path"]
        and not row["evidence_path"].startswith("external_absolute:")
    ]
    assert repo_evidence
    assert all(not Path(path).is_absolute() for path in repo_evidence)


def test_adaptive_mesh_stays_out_of_production_selective_merge() -> None:
    path = (
        ROOT
        / "docs/task034_workstation_wsl_adaptive_scalability/outcomes"
        / "selective_merge_manifest.csv"
    )
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    matches = [
        row
        for row in rows
        if row["path"] == "src/geometry/task034_adaptive_mesh.py"
    ]
    assert len(matches) == 1
    row = matches[0]
    assert row["merge_action"] == "research_only_do_not_merge_yet"
    assert row["dependency_group"] == "research_only_conforming_graded_mesh"
    assert "field-driven adaptivity not qualified" in row["fresh_pde_evidence"]
