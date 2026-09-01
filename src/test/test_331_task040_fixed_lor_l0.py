"""Task040 L0a: fixed p6 local refined de Rham complex tests."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.hcurl_fixed_lor import (
    FixedP6LORReferenceComplex,
    build_fixed_p6_lor_reference_complex,
)


@pytest.fixture(scope="module")
def complex_reference() -> FixedP6LORReferenceComplex:
    return build_fixed_p6_lor_reference_complex()


def test_l0a_canonical_counts_and_keys(complex_reference):
    reference = complex_reference
    assert reference.audit["scope"] == "research_local_only_reference_complex"
    assert reference.audit["degree"] == 6
    assert reference.audit["subdivision"] == (6, 6, 6)
    assert reference.audit["counts"] == {
        "vertices": 343,
        "edges": 882,
        "faces": 756,
        "cells": 216,
    }
    assert reference.vertex_keys[:3] == ((0, 0, 0), (1, 0, 0), (2, 0, 0))
    assert reference.vertex_keys[-1] == (6, 6, 6)
    assert reference.edge_keys[0] == ("x", 0, 0, 0)
    assert reference.edge_keys[294] == ("y", 0, 0, 0)
    assert reference.edge_keys[588] == ("z", 0, 0, 0)
    assert reference.face_keys[0] == ("x", 0, 0, 0)
    assert reference.face_keys[252] == ("y", 0, 0, 0)
    assert reference.face_keys[504] == ("z", 0, 0, 0)
    assert reference.cell_keys[0] == (0, 0, 0)
    assert reference.cell_keys[-1] == (5, 5, 5)
    assert reference.audit["unique_key_coverage"]
    assert reference.audit["local_incidence_coverage"]


def test_l0a_oriented_sparse_incidence(complex_reference):
    reference = complex_reference
    G = reference.gradient_incidence
    C = reference.curl_incidence
    D = reference.divergence_incidence
    assert G.shape == (882, 343)
    assert C.shape == (756, 882)
    assert D.shape == (216, 756)
    assert (G != 0).nnz == 2 * 882
    assert (C != 0).nnz == 4 * 756
    assert (D != 0).nnz == 6 * 216

    first_edge = dict(zip(G.getrow(0).indices, G.getrow(0).data, strict=True))
    assert first_edge == {0: -1.0, 1: 1.0}
    first_face = dict(zip(C.getrow(0).indices, C.getrow(0).data, strict=True))
    assert first_face == {294: 1.0, 336: -1.0, 588: -1.0, 595: 1.0}
    first_cell = dict(zip(D.getrow(0).indices, D.getrow(0).data, strict=True))
    assert first_cell == {0: -1.0, 1: 1.0, 252: -1.0, 258: 1.0, 504: -1.0, 540: 1.0}


def test_l0a_exact_complex_and_numeric_rank_audit(complex_reference):
    reference = complex_reference
    audit = reference.audit
    assert audit["incidence_products"]["CG"]["zero"]
    assert audit["incidence_products"]["DC"]["zero"]
    assert audit["incidence_products"]["CG"]["max_abs"] == 0.0
    assert audit["incidence_products"]["DC"]["max_abs"] == 0.0
    assert audit["numeric_ranks"] == {"G": 342, "C": 540, "D": 216}
    assert all(np.isfinite(value) for value in audit["rank_tolerances"].values())
    assert audit["pass"]
    assert audit["external_runtime"] == "numpy_scipy_only"
