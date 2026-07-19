from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORD = (
    ROOT
    / "benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/"
    "wsl_extended_mpi_qualification.json"
)


def _load_hash_verified_record() -> dict:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    payload_sha256 = record.pop("payload_sha256")
    canonical = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == payload_sha256
    return record


def test_extended_mpi_record_is_hash_bound_to_clean_stable_source() -> None:
    record = _load_hash_verified_record()
    assert record["status"] == "environment_gate_pass"
    source = record["source"]
    assert (
        source["head_before_sha"]
        == source["head_after_sha"]
        == "8440bbaf42de9d633479d0ed65bdda544bd871ef"
    )
    assert source["clean_before"]
    assert source["clean_after"]
    assert source["stable_during_probe"]
    assert all(record["gate_checks"].values())


def test_extended_mpi_scope_preserves_formal_and_exploratory_boundary() -> None:
    record = _load_hash_verified_record()
    identity = record["identity"]
    assert identity["formal_mpi_sizes"] == [1, 2, 4, 8, 16]
    assert identity["exploratory_mpi_sizes"] == [32]
    assert identity["available_physical_core_count"] == 48
    assert identity["maximum_requested_mpi_size"] <= 48
    assert not identity["oversubscribed"]
    assert not identity["mpi32_replaces_mpi16"]
    assert not identity["mpi32_proves_pde_identity"]
    assert not identity["mpi32_speedup_claimed"]
    assert not identity["is_pde_run"]


def test_all_rank_identity_and_requested_solver_microfixtures_pass() -> None:
    record = _load_hash_verified_record()
    rows = {item["mpi_size"]: item for item in record["mpi_summary"]}
    assert set(rows) == {1, 2, 4, 8, 16, 32}
    for size, row in rows.items():
        assert row["pass"]
        assert row["rank_records_observed"] == size
        assert row["single_abi_signature"]
        assert row["rank_library_identity_pass"]
    assert rows[32]["scope"] == "exploratory"
    assert record["runtime"]["same_rank_library_identity_all_requested_sizes"]
    thresholds = record["microfixture_thresholds"]
    for size in (8, 16, 32):
        row = rows[size]
        assert row["distributed_solver_microfixture_required"]
        assert (
            row["mumps_solution_absolute_error_max"]
            <= thresholds["mumps_solution_absolute_error_max"]
        )
        assert (
            row["pep_expected_root_absolute_error"]
            <= thresholds["pep_expected_root_absolute_error_max"]
        )
        assert (
            row["pep_relative_error"]
            <= thresholds["pep_relative_error_max"]
        )
    assert not thresholds["thresholds_relaxed"]


def test_raw_evidence_is_hash_bound_but_not_tracked_as_heavy_output() -> None:
    record = _load_hash_verified_record()
    evidence = record["raw_evidence"]
    assert evidence["gitignored"]
    assert len(evidence["json_sha256"]) == 64
    assert len(evidence["markdown_sha256"]) == 64
    assert not record["identity"]["heavy_artifacts_tracked"]
    decision = record["decision"]
    assert decision["environment_gate_pass"]
    assert decision["mpi16_environment_qualified"]
    assert decision["mpi32_exploratory_environment_qualified"]
    assert not decision["heavy_pde_authorized_by_this_record_alone"]
    assert not decision["mpi_pde_numerical_identity_completed"]
