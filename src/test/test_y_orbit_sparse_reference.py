"""Small contract tests only; genuine FE qualification is the admitted pilot."""
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from src.solvers.y_orbit_sparse_reference import (
    AugmentedYCoordinates, SparseAllQFactor, _product_bound, csr_audit, integer_admission,
)


def test_int32_nnz_offset_overflow_rejected_without_large_allocation():
    limit = np.iinfo(np.int32).max
    result = integer_admission((31, 47), limit, index_dtype=np.int32)
    assert result["indptr_bits"] == 32
    with pytest.raises(OverflowError, match="indptr"):
        integer_admission((31, 47), int(limit) + 1, index_dtype=np.int32)
    with pytest.raises(OverflowError, match="indices"):
        integer_admission((int(limit) + 1, 47), 0, index_dtype=np.int32)
    assert integer_admission((int(limit) + 1, 47), int(limit) + 1, index_dtype=np.int64)["indices_bits"] == 64


def test_real_CSR_width_and_qualified_ABI_width_are_distinct():
    matrix = sparse.eye(7, dtype=np.complex128, format="csr")
    matrix.indices = matrix.indices.astype(np.int64)
    matrix.indptr = matrix.indptr.astype(np.int64)
    facts = csr_audit(matrix, petsc_index_dtype=np.int32)
    assert facts["actual"]["indices_bits"] == 64
    assert facts["qualified_PETSc_IntType"]["indices_bits"] == 32


def test_sparse_graph_product_bound_includes_empty_rows_and_duplicate_paths():
    left = sparse.csr_matrix(np.asarray([[1, 1, 0], [0, 0, 0], [1, 0, 1]], complex))
    right = sparse.csr_matrix(np.asarray([[1, 0, 1, 0], [1, 0, 0, 1], [0, 1, 0, 0]], complex))
    assert _product_bound(left, right) >= (left @ right).nnz


def test_augmented_q_map_retains_separate_alias_columns_and_primal_dual_pairing():
    # A map-semantic unit fixture deliberately has nonunitary native moments.
    # This is not a substitute for the FFCx p2/p4 experiment.
    rt = sparse.diags([2, 3, 5, 7], dtype=np.complex128, format="csr")
    ft = sparse.kron(np.asarray([[1, 1], [1, -1]]) / np.sqrt(2), sparse.eye(2), format="csr")
    qt = (rt @ ft).tocsr()
    coordinates = AugmentedYCoordinates({"ny": 2, "trace_width": 2}, qt,
        (np.asarray([0]), np.asarray([1, 2])), np.ones(3, complex),
        (("top", 0, 0, "s"), ("top", 0, 1, "s"), ("top", 0, -1, "s")),
        3, np.dtype(np.int32), {})
    matrix = coordinates.q_map(1, allocation_gate=lambda *_: None)
    assert matrix.shape == (7, 4)
    np.testing.assert_array_equal(matrix[4:, 2:].toarray(), [[0, 0], [1, 0], [0, 1]])
    primal = np.asarray([1, 2j, 3, 4j])
    dual = np.asarray([1j, 2, 3j, 4, 5j, 6, 7j])
    np.testing.assert_allclose(np.vdot(dual, matrix @ primal), np.vdot(matrix.conj().T @ dual, primal))
    assert sparse.linalg.norm(matrix.conj().T @ matrix - sparse.eye(4)) > 1


def test_source_contract_does_not_copy_old_S2_hard_limits_or_factor_stats():
    root = Path(__file__).resolve().parents[1]
    source = (root / "solvers/y_orbit_sparse_reference.py").read_text()
    assert "factor.L" not in source.replace("# No access to factor.L/U: those properties materialize copies.", "")
    assert "max_factor_rows=1024" not in source and "extract_augmented_background_mode" not in source
    assert "q_trace.conj().T" in source
    assert "all-cross-q-audit then streamed per-q factors" in source


def test_partial_constructor_failure_clears_all_previously_retained_factors(monkeypatch):
    instance = SparseAllQFactor.__new__(SparseAllQFactor)
    def fail(self, *_args, **_kwargs):
        self.factors.append(object())
        raise RuntimeError("controlled partial setup failure")
    monkeypatch.setattr(SparseAllQFactor, "_setup", fail)
    coordinates = type("Coordinates", (), {"ny": 4})()
    with pytest.raises(RuntimeError, match="partial setup"):
        SparseAllQFactor.__init__(instance, None, coordinates,
            allocation_gate=lambda *_: None, event=lambda *_: None, save_array=lambda *_: None)
    assert instance.destroyed is True and instance.factors == []


def test_weaker_diagonal_block_leakage_cannot_hide_in_global_norm(monkeypatch):
    from src.solvers import y_orbit_sparse_reference as module
    calls = []
    monkeypatch.setattr(module, "splu", lambda *_: calls.append(True))
    coordinates = AugmentedYCoordinates(
        {"ny": 2, "trace_width": 1,
         "native_trace_translation": sparse.diags([1, -1], dtype=np.complex128, format="csr")},
        sparse.eye(2, dtype=np.complex128, format="csr"),
        (np.asarray([0], dtype=np.int32), np.asarray([1], dtype=np.int32)),
        np.asarray([1, -1], complex), (("top", 0, 0, "s"), ("top", 0, 1, "s")),
        2, np.dtype(np.int32), {})
    matrix = sparse.diags([1e9, 1, 1, 1], dtype=np.complex128, format="lil")
    matrix[0, 1] = 1e-9
    matrix = matrix.tocsr()
    with pytest.raises(ValueError, match="off-block gate"):
        SparseAllQFactor(matrix, coordinates, allocation_gate=lambda *_: None,
                         event=lambda *_: None, save_array=lambda *_: None)
    assert not calls  # no factor before the complete per-pair gate
