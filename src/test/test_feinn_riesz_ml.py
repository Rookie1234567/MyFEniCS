"""Small positive complex CHOLMOD witness and symbolic-before-numeric gate."""

import numpy as np
import pytest
from scipy import sparse

from src.solvers.feinn_riesz import SparseRiesz


def test_sparse_complex_positive_factor_and_release():
    off = np.full(19, -0.2 + 0.1j)
    G = sparse.diags(
        [off.conj(), np.full(20, 2.0), off], [-1, 0, 1], format="csr", dtype=complex
    )
    design = dict(riesz=dict(factor_payload_cap_bytes=2**28, planning_cap_bytes=2**30))
    gram = SparseRiesz(G, design)
    rng = np.random.default_rng(21)
    b = rng.standard_normal(20) + 1j * rng.standard_normal(20)
    q = gram.solve(b)
    assert np.linalg.norm(G @ q - b) / np.linalg.norm(b) < 1e-11
    assert np.vdot(b, q).real > 0
    assert gram.record["numeric"]["positive_pivots"] == 20
    gram.close()
    assert gram.handle is None and gram.record["solve_count"] == 1


def test_symbolic_capacity_prevents_numeric():
    events = []
    design = dict(riesz=dict(factor_payload_cap_bytes=1, planning_cap_bytes=2**30))
    with pytest.raises(RuntimeError, match="RIESZ_RESOURCE_BLOCKED"):
        SparseRiesz(
            sparse.eye(5, format="csr", dtype=complex),
            design,
            marker=lambda name, _: events.append(name),
        )
    assert events == ["riesz_symbolic"]
