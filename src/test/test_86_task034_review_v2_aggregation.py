from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from benchmarks.task034_review_v2_aggregation import (
    CASE092_RECORDS,
    CASE093_RELATIVE,
    COLUMNS,
    FIXTURE_RELATIVE,
    MPI_RELATIVE,
    build,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[2]
OUTCOMES = Path("docs/task034_workstation_wsl_adaptive_scalability/outcomes")


def _clean_root(tmp_path: Path) -> Path:
    root = tmp_path / "clean_checkout"
    required = [
        FIXTURE_RELATIVE,
        CASE093_RELATIVE,
        MPI_RELATIVE,
        *(CASE092_RECORDS / f"{stem}_{suffix}.json"
          for stem in ("p2_h1", "p3_h2", "p4_h3")
          for suffix in ("execution_outcome", "resource_gate")),
    ]
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    assert not (root / "benchmarks/artifacts").exists()
    return root


def test_all_model_results_schema_and_scope() -> None:
    result = build(ROOT)
    rows = result["rows"]
    assert result["row_count"] == 40
    assert all(list(row) == COLUMNS for row in rows)
    assert {row["polarization"] for row in rows} == {"s"}
    assert sum(
        row["data_identity"]
        == "measured_mpi_identity_with_selected_baseline_physics"
        for row in rows
    ) == 8
    assert sum(row["data_identity"] == "measured_mode_funnel" for row in rows) == 6
    assert result["identity"]["hermetic_no_artifact_reads"] is True
    assert result["identity"]["R00_p_semantics"] == (
        "cross-polarized p output under S incidence"
    )
    assert "matrix_nnz_used" in result["identity"]["factor_nnz_semantics"]


def test_clean_checkout_without_artifacts_is_byte_deterministic(tmp_path: Path) -> None:
    root = _clean_root(tmp_path)
    result = build(root)
    generated_json = tmp_path / "all_model_results.json"
    generated_csv = tmp_path / "all_model_results.csv"
    write_outputs(result, generated_json, generated_csv)
    assert generated_json.read_bytes() == (ROOT / OUTCOMES / generated_json.name).read_bytes()
    assert generated_csv.read_bytes() == (ROOT / OUTCOMES / generated_csv.name).read_bytes()


def test_compact_fixture_missing_field_fails_closed(tmp_path: Path) -> None:
    root = _clean_root(tmp_path)
    fixture_path = root / FIXTURE_RELATIVE
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["rows"][0].pop("factor_nnz")
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="schema mismatch"):
        build(root)


def test_controlled_resource_and_timeout_statuses_are_fail_closed() -> None:
    rows = {row["case_key"]: row for row in build(ROOT)["rows"]}
    for key in (
        "supplemental_p2_h1_full3d",
        "supplemental_p3_h2_full3d",
        "supplemental_p4_h3_full3d",
    ):
        row = rows[key]
        assert row["status"] == "not_run_by_conservative_resource_gate_after_assembly"
        assert row["assembly_seconds"] == row["total_seconds"]
        assert row["factor_nnz"] is None
        assert row["true_relative_residual"] is None
        assert "factorization_launched_false" in row["full3d_hybrid_closure_status"]
        assert "full_solve_launched_false" in row["full3d_hybrid_closure_status"]

    p4 = rows["supplemental_p4_h3_full3d"]
    assert p4["assembly_seconds"] == pytest.approx(3035.1390509350167)
    assert p4["peak_memory_gib"] == pytest.approx(80.53771209716797)

    timeout = rows["supplemental_p2_h1_hybrid_m160"]
    assert timeout["status"] == "timeout_during_field_recovery_no_official_solution"
    assert timeout["total_seconds"] == 7200.0
    assert timeout["peak_memory_gib"] == 95.87872314453125
    assert timeout["swap_bytes"] == 0
    assert timeout["R_total"] is None
    assert timeout["true_relative_residual"] is None


def test_s_incidence_contains_cross_polarized_zero_order_output() -> None:
    measured = [row for row in build(ROOT)["rows"] if row["R00_p"] is not None]
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
        hybrid["fe_dofs"] + hybrid["external_aux_dofs"] + hybrid["modal_unknowns"]
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
    assert all(
        not Path(row["evidence_path"]).is_absolute()
        for row in rows.values()
        if row["evidence_path"]
    )


def test_all_40_rows_have_authority_audit() -> None:
    path = ROOT / OUTCOMES / "all_model_authority_audit.json"
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["row_count"] == 40
    assert len(audit["rows"]) == 40
    assert audit["rows_with_drift"] == 1
    assert audit["field_drifts"] == 2
    assert {row["case_key"] for row in audit["rows"]} == {
        row["case_key"] for row in build(ROOT)["rows"]
    }


def test_adaptive_mesh_stays_out_of_production_selective_merge() -> None:
    path = ROOT / OUTCOMES / "selective_merge_manifest.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    matches = [row for row in rows if row["path"] == "src/geometry/task034_adaptive_mesh.py"]
    assert len(matches) == 1
    row = matches[0]
    assert row["merge_action"] == "research_only_do_not_merge_yet"
    assert row["dependency_group"] == "research_only_conforming_graded_mesh"
    assert "field-driven adaptivity not qualified" in row["fresh_pde_evidence"]
