"""Small V25 volume-witness metric and persistence tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.task40_v25_complete_volume import (
    _atomic_save_array,
    _frozen_cell_class_coverage,
    _p6_action_owner_bound,
    _relative_error,
    _relative_error_between,
)


@pytest.fixture
def condensation_builder_audit() -> dict[str, int]:
    """The cell-class field names emitted by the actual condensation builder."""
    return {
        "owned_cell_count_global": 30_464,
        "raw_tensor_class_count_global_unique": 29,
        "raw_tensor_class_count_sum": 29,
        "raw_tensor_class_use_count_sum": 30_464,
        "oriented_schur_class_count_sum": 60,
        "retained_local_schur_class_count_sum": 60,
    }


def test_frozen_cell_coverage_reads_actual_builder_audit_keys(
    condensation_builder_audit: dict[str, int],
) -> None:
    coverage = _frozen_cell_class_coverage(condensation_builder_audit)
    assert coverage["status"] == "PASS"
    assert coverage["actual_counts"] == {
        "owned_cell_count_global": 30_464,
        "raw_tensor_class_count_global_unique": 29,
        "oriented_schur_class_count_sum": 60,
    }
    assert coverage["missing_fields"] == []


def test_frozen_cell_coverage_reports_a_missing_builder_field(
    condensation_builder_audit: dict[str, int],
) -> None:
    del condensation_builder_audit["raw_tensor_class_count_global_unique"]
    coverage = _frozen_cell_class_coverage(condensation_builder_audit)
    assert coverage["status"] == "FAILED"
    assert coverage["missing_fields"] == ["raw_tensor_class_count_global_unique"]


def test_frozen_cell_coverage_reports_wrong_observed_count(
    condensation_builder_audit: dict[str, int],
) -> None:
    condensation_builder_audit["oriented_schur_class_count_sum"] = 59
    coverage = _frozen_cell_class_coverage(condensation_builder_audit)
    assert coverage["status"] == "FAILED"
    assert coverage["mismatched_fields"]["oriented_schur_class_count_sum"] == {
        "expected": 60,
        "actual": 59,
    }


def test_native_residual_metric_uses_residual_over_native_rhs() -> None:
    rhs = np.asarray([3.0 + 0.0j, 4.0 + 0.0j])
    residual = np.asarray([3.0e-10 + 0.0j, 4.0e-10 + 0.0j])
    relative, residual_norm, rhs_norm = _relative_error(residual, rhs)
    assert relative == 1.0e-10
    assert residual_norm == 5.0e-10
    assert rhs_norm == 5.0


def test_chunked_forward_error_matches_direct_relative_norm() -> None:
    reference = np.asarray([1.0 + 1.0j, -2.0 + 0.5j, 0.25 - 0.75j])
    actual = reference + np.asarray([1.0e-9j, 0.0, -2.0e-9])
    direct = _relative_error(actual - reference, reference)
    chunked = _relative_error_between(actual, reference, chunk_entries=1)
    np.testing.assert_allclose(chunked, direct, rtol=1.0e-15, atol=0.0)


def test_raw_array_save_is_atomic_and_readback_verified(tmp_path) -> None:
    raw = np.asarray([1.0 + 2.0j, 3.5 - 0.25j], dtype=np.complex128)
    record = _atomic_save_array(tmp_path, "witness.npy", raw)
    assert record["readback_verified"] is True
    assert record["shape"] == [2]
    assert record["dtype"] == "complex128"
    np.testing.assert_array_equal(np.load(tmp_path / record["path"], allow_pickle=False), raw)


def test_p6_owner_bound_counts_cell_interior_and_trace_row_copies() -> None:
    bound = _p6_action_owner_bound(
        cell_count=30_464,
        local_dofs_per_cell=882,
        trace_rows_per_cell=432,
        maximum_masters_per_slave=1,
        index_bytes=4,
    )
    assert bound["per_cell_original_interior_and_trace_row_copies_bytes_upper"] == 107_476_992
    assert bound["additional_bytes_upper"] >= 107_476_992
