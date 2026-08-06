from __future__ import annotations

import numpy as np

from src.solvers.static_factor_reuse import (
    _canonical_global_row_ids_fingerprint,
    _exact_reuse_necessary_prefix,
)


def test_same_numeric_seqaij_needs_same_global_rows_and_order_for_prefix():
    # This is the existing shifted SeqAIJ fingerprint for identical numeric data.
    shifted_matrix_sha256 = "ab" * 32
    rows = np.asarray([10, 20], dtype=np.int32)
    same_rows = rows.copy()
    different_rows = np.asarray([10, 21], dtype=np.int32)
    reordered_rows = np.asarray([20, 10], dtype=np.int32)

    row_sha256 = _canonical_global_row_ids_fingerprint(rows)
    assert row_sha256 == _canonical_global_row_ids_fingerprint(same_rows)
    assert row_sha256 != _canonical_global_row_ids_fingerprint(different_rows)
    assert row_sha256 != _canonical_global_row_ids_fingerprint(reordered_rows)

    prefix = _exact_reuse_necessary_prefix(row_sha256, shifted_matrix_sha256)
    assert prefix == _exact_reuse_necessary_prefix(
        _canonical_global_row_ids_fingerprint(same_rows), shifted_matrix_sha256
    )
    assert prefix != _exact_reuse_necessary_prefix(
        _canonical_global_row_ids_fingerprint(different_rows),
        shifted_matrix_sha256,
    )
    assert prefix != _exact_reuse_necessary_prefix(
        _canonical_global_row_ids_fingerprint(reordered_rows),
        shifted_matrix_sha256,
    )
