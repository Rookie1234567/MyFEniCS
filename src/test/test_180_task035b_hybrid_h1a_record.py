from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORD = (
    ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "hybrid_static_condensation_h1a_mpi8_v1.json"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_h1a_record_preserves_controlled_negative_semantics() -> None:
    record = _record()
    gates = record["gates"]
    continuation = record["continuation"]

    assert record["status"] == (
        "h1a_controlled_negative_hybrid_same_discretization_gate_failed"
    )
    assert record["classification"] == "controlled_negative"
    assert record["pass"] is False
    assert record["ordinary_default_changed"] is False
    assert gates["static_full3d_equivalence_pass"] is True
    assert gates["static_hybrid_equivalence_pass"] is True
    assert gates["static_hybrid_m120_to_m160_converged"] is True
    assert gates["static_full3d_vs_static_hybrid_m160_pass"] is False
    assert gates["h1a_all_pass"] is False
    assert gates["h1b_launch_authorized"] is False
    assert continuation["H1_B"] == "not_run_by_review_prerequisite"
    assert continuation["H1_C"] == "not_run_after_h1a_numerical_gate"
    assert continuation["H1_D"] == "not_run_after_h1a_numerical_gate"


def test_h1a_pairwise_equivalence_and_failure_counts_recompute() -> None:
    record = _record()
    comparisons = record["comparisons"]

    for key in (
        "standard_full3d_vs_static_full3d",
        "standard_hybrid_m120_vs_static_hybrid_m120",
        "standard_hybrid_m160_vs_static_hybrid_m160",
        "static_hybrid_m120_vs_static_hybrid_m160",
    ):
        comparison = comparisons[key]
        assert comparison["power_pass_count"] == 12
        assert comparison["amplitude_pass_count"] == 12
        assert comparison["pass"] is True

    channels = record["static_full3d_vs_static_hybrid_m160_channels"]
    assert len(channels) == 12
    assert len({row["channel"] for row in channels}) == 12
    assert sum(row["power_relative_1e-3_pass"] for row in channels) == 3
    assert sum(row["amplitude_relative_1e-3_pass"] for row in channels) == 2
    assert sum(row["power_abs_pass"] for row in channels) == 2
    assert sum(row["amplitude_abs_pass"] for row in channels) == 2

    failure = comparisons["static_full3d_vs_static_hybrid_m160"]
    assert failure["primary_relative_power_pass_count"] == 3
    assert failure["primary_relative_amplitude_pass_count"] == 2
    assert failure["secondary_absolute_power_pass_count"] == 2
    assert failure["secondary_absolute_amplitude_pass_count"] == 2
    assert failure["pass"] is False


def test_h1a_failed_channels_keep_actual_values_and_limits() -> None:
    channels = _record()["static_full3d_vs_static_hybrid_m160_channels"]
    relative_power_failures = {
        row["channel"]
        for row in channels
        if not row["power_relative_1e-3_pass"]
    }
    relative_amplitude_failures = {
        row["channel"]
        for row in channels
        if not row["amplitude_relative_1e-3_pass"]
    }

    assert relative_power_failures == {
        "T(-5,0)_s",
        "T(-4,0)_s",
        "T(-2,0)_s",
        "T(-1,0)_s",
        "R(-7,0)_s",
        "R(-5,0)_s",
        "R(-4,0)_s",
        "R(-2,0)_s",
        "R(-1,0)_s",
    }
    assert relative_amplitude_failures == relative_power_failures | {
        "T(-7,0)_s"
    }
    for row in channels:
        assert row["power_abs_diff"] >= 0.0
        assert row["power_abs_tolerance"] > 0.0
        assert row["amplitude_abs_diff"] >= 0.0
        assert row["amplitude_abs_tolerance"] > 0.0
        assert len(row["static_full_amplitude"]) == 2
        assert len(row["static_hybrid_m160_amplitude"]) == 2


def test_h1a_resource_result_does_not_overclaim_rows_as_memory_success() -> None:
    record = _record()
    deltas = record["resource_deltas"]["hybrid_m160_standard_to_static_percent"]

    assert deltas["total_rows"] < -20.0
    assert deltas["local_matrix_nnz_pair"] < -20.0
    assert -10.0 < deltas["factor_nnz_pair"] < 0.0
    assert deltas["factor_fill"] > 0.0
    assert deltas["peak_process_tree_rss"] > 0.0
    assert deltas["total_seconds"] > 0.0
    assert record["interpretation"]["resource_signal"].startswith(
        "mixed_negative"
    )


def test_h1a_authority_hashes_and_source_identity_are_explicit() -> None:
    record = _record()
    source = record["source"]
    authorities = record["raw_authorities"]

    assert SHA_RE.fullmatch(source["numerical_commit_sha"])
    assert SHA_RE.fullmatch(source["master_base_sha"])
    assert source["mpi_size"] == 8
    assert source["petsc_scalar_type"] == "complex128"
    assert source["petsc_int_type"] == "int32"
    assert len(authorities) == 8
    assert all(SHA256_RE.fullmatch(item["sha256"]) for item in authorities)
