from __future__ import annotations

from pathlib import Path

from benchmarks.task034_review_v2_aggregation import COLUMNS, build


ROOT = Path(__file__).resolve().parents[2]


def test_all_model_results_schema_and_scope() -> None:
    result = build(ROOT)
    rows = result["rows"]
    assert result["row_count"] == 40
    assert all(list(row) == COLUMNS for row in rows)
    assert {row["polarization"] for row in rows} == {"s"}
    assert sum(row["data_identity"] == "measured_mpi_identity" for row in rows) == 8
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
