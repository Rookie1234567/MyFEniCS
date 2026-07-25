"""Contract tests for the Task035b bounded memory/factor ledger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.solvers.condensed_iterative_profiles import (
    PHYSICS_AWARE_PROFILE,
    condensed_iterative_profile_contract,
)


ROOT = Path(__file__).resolve().parents[2]
RECORDS = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
)
LEDGER = RECORDS / "h15_memory_floor_factor_inventory_ledger_v2.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_ledger_is_hash_bound_and_does_not_claim_a_pde_rerun() -> None:
    ledger = _json(LEDGER)

    assert ledger["pass"] is True
    assert ledger["heavy_pde_rerun"] is False
    assert ledger["candidate_promotion"] is False
    assert ledger["ordinary_default_changed"] is False
    assert "does not mean" in ledger["record_semantics"]

    for authority in ledger["source"]["authority_records"]:
        path = ROOT / authority["path"]
        assert path.is_file()
        assert _sha256(path) == authority["sha256"]

    typed = ledger["source"]["typed_physics_aware_profile"]
    for field in ("profile_source", "runner_source"):
        source = typed[field]
        path = ROOT / source["path"]
        assert path.is_file()
        assert _sha256(path) == source["sha256"]


def test_direct_rank_ledger_recomputes_the_measured_not_theoretical_floor() -> None:
    ledger = _json(LEDGER)
    direct = _json(RECORDS / "h15_direct_mpi1_2_4_8_resource_floor_v1.json")
    audit = _json(
        RECORDS / "h15_solve_thread_memory_semantics_audit_v1.json"
    )
    rows = ledger["direct_rank_study"]["rows"]

    assert [row["mpi_size"] for row in rows] == [1, 2, 4, 8]
    assert [row["process_tree_peak_gib"] for row in rows] == [
        row["max_process_tree_rss_gib"] for row in direct["measurements"]
    ]
    assert [row["worker_rank_pss_peak_gib"] for row in rows] == [
        row["max_worker_rank_pss_sum_gib"] for row in direct["measurements"]
    ]
    assert [row["worker_rank_uss_peak_gib"] for row in rows] == [
        row["max_worker_rank_uss_sum_gib"] for row in direct["measurements"]
    ]
    assert [row["factor_peak_stage"] for row in rows] == [
        row["factor_peak"]["stage"] for row in audit["measurements"]
    ]
    assert [row["timeline_sha256"] for row in rows] == [
        row["timeline"]["sha256"]
        for row in audit["authority"]["evidence_sources"]
    ]
    assert [row["worker_result_sha256"] for row in rows] == [
        row["worker_result"]["sha256"]
        for row in audit["authority"]["evidence_sources"]
    ]
    assert [row["native_numpy_build_rank_sum_bytes"] for row in rows] == [
        row["native_numpy_ledger_rank_sum_bytes"]
        for row in audit["measurements"]
    ]
    assert [row["recovery_native_after_rank_sum_bytes"] for row in rows] == [
        row["recovery_lifecycle_after_rank_sum_bytes"]
        for row in audit["measurements"]
    ]
    assert all(row["process_tree_swap_mb"] == 0.0 for row in rows)
    assert all(row["full_explicit_true_residual"] <= 1.0e-9 for row in rows)

    interpretation = ledger["direct_rank_study"]["interpretation"]
    assert interpretation["historical_5p8_to_6p4_gib_is_a_memory_floor"] is False
    assert interpretation["best_observed_direct_rank_point"] == "MPI1"
    assert interpretation["best_observed_direct_process_tree_peak_gib"] == min(
        row["process_tree_peak_gib"] for row in rows
    )
    assert interpretation["best_observed_direct_point_is_a_theoretical_floor"] is False
    assert interpretation["best_observed_direct_point_is_a_software_stack_floor"] is False
    assert interpretation["best_observed_direct_point_is_a_factor_free_floor"] is False


def test_factor_free_controls_preserve_accuracy_failure_and_factor_scope() -> None:
    ledger = _json(LEDGER)
    authority = _json(RECORDS / "h15_factor_free_iterative_mpi8_v1.json")
    profiles = ledger["measured_assembled_iterative_controls"]["profiles"]

    assert [row["profile"] for row in profiles] == [
        row["profile"] for row in authority["profiles"]
    ]
    assert [row["process_tree_peak_gib"] for row in profiles] == [
        row["max_process_tree_rss_gib"] for row in authority["profiles"]
    ]
    assert all(row["global_fine_sparse_factor_nnz"] == 0 for row in profiles)
    assert all(row["mumps_symbolic_or_numeric_created"] is False for row in profiles)
    assert all(row["iterations"] == 200 for row in profiles)
    assert all(row["accuracy_pass"] is False for row in profiles)
    assert all(row["official_result"] is False for row in profiles)
    assert all(row["full_recovered_true_residual"] > 0.8 for row in profiles)
    assert (
        ledger["measured_assembled_iterative_controls"]["interpretation"][
            "factor_free_accuracy_qualified_memory_floor_measured"
        ]
        is False
    )
    assert min(row["process_tree_peak_gib"] for row in profiles) > ledger[
        "direct_rank_study"
    ]["interpretation"]["best_observed_direct_process_tree_peak_gib"]


def test_typed_profile_discloses_dense_coarse_factor_and_not_run_fields() -> None:
    ledger = _json(LEDGER)
    typed = ledger["typed_physics_aware_profile_v2"]
    contract = condensed_iterative_profile_contract(PHYSICS_AWARE_PROFILE)

    assert typed["profile"] == PHYSICS_AWARE_PROFILE
    assert typed["configured_programmatically"] is True
    assert typed["raw_petsc_options_accepted"] is False
    assert typed["assembled_reduced_operator"] is True
    assert typed["matrix_free"] is False
    assert typed["fine_operator_factor_free_by_contract"] is True
    assert typed["strictly_factorless_preconditioner"] is False
    assert typed["retained_factor"] == "small replicated dense Galerkin coarse LU"
    assert typed["derived_coarse_dense_matrix_payload_bytes"] == 80 * 80 * 16
    assert typed["coarse_dense_lu_and_workspace_bytes"] is None
    assert typed["formal_process_tree_peak_gib"] is None
    assert typed["formal_full_recovered_true_residual"] is None
    assert typed["formal_screen_status"] == "not_run"
    assert contract["configured_programmatically"] is True
    assert contract["raw_petsc_options_accepted"] is False
    assert contract["assembled_reduced_operator"] is True
    assert contract["matrix_free"] is False
    assert contract["ordinary_default_changed"] is False


def test_component_coverage_and_non_additivity_fail_closed() -> None:
    ledger = _json(LEDGER)
    coverage = {
        row["component"]: row for row in ledger["component_coverage_ledger"]
    }
    expected = {
        "runtime_floor",
        "mesh_and_function_space",
        "local_tensors_aii_schur_and_recovery_caches",
        "petsc_matrix_and_vectors",
        "mumps_symbolic_numeric_workspace_and_factor",
        "recovery_and_postprocess",
        "allocator_retention",
        "cgroup",
    }
    assert set(coverage) == expected
    assert coverage["runtime_floor"]["measurement_status"] == "not_isolated"
    assert coverage["petsc_matrix_and_vectors"]["measurement_status"] == (
        "derived_matrix_proxy_only"
    )
    assert coverage["cgroup"]["measurement_status"] == "diagnostic_non_authority"
    assert "not dedicated" in coverage["cgroup"]["limitation"]
    assert len(ledger["open_measurement_gaps"]) >= 10

    rules = ledger["non_additivity_rules"]
    assert all(value == "forbidden" for key, value in rules.items() if key != "reason")
    checks = ledger["qualification"]["checks"]
    assert all(checks.values())
    decision = ledger["decision"]
    assert decision["historical_5p8_to_6p4_gib_is_a_floor"] is False
    assert decision["mpi1_1p295_gib_is_a_floor"] is False
    assert decision["current_accuracy_qualified_factor_free_memory_floor"] is None
    assert decision["matrix_free_status"] == "not_run"
