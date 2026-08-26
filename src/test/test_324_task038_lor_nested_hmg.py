"""Focused pure-local tests for the fixed C2 nested LOR geometry."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.fullspace_lor_nested_hmg import (
    ADJOINT_LIMIT,
    C2_PAIRS,
    CURL_LIMIT,
    EDGE_LIMIT,
    GRADIENT_LIMIT,
    H1STAR_GLL_INDICES,
    H3STAR_GLL_INDICES,
    H6_GLL_INDICES,
    LINEARITY_LIMIT,
    NestedHmgLocalTransfer,
    REPEAT_LIMIT,
    audit_nested_hmg_transfer,
    build_nested_lor_edge_hmg,
)
from src.solvers.fullspace_lor_transfer import _gll_nodes


@pytest.fixture(scope="module")
def nested_hmg():
    return build_nested_lor_edge_hmg()


def test_fixed_nested_nodes_are_exact_subsets_and_not_standard_level(nested_hmg):
    assert nested_hmg.audit["levels"] == (
        "h6", "h3star", "h1star"
    )
    assert nested_hmg.audit["pairs"] == C2_PAIRS
    assert nested_hmg.audit["fine_gll_indices"] == H6_GLL_INDICES
    assert nested_hmg.audit["h3star_gll_indices"] == H3STAR_GLL_INDICES
    assert nested_hmg.audit["h1star_gll_indices"] == H1STAR_GLL_INDICES
    assert np.array_equal(
        nested_hmg.h3star_nodes,
        nested_hmg.h6_nodes[list(H3STAR_GLL_INDICES)],
    )
    assert np.array_equal(
        nested_hmg.h1star_nodes,
        nested_hmg.h6_nodes[list(H1STAR_GLL_INDICES)],
    )
    standard_reference_level_nodes = np.asarray(_gll_nodes(3))
    assert not np.array_equal(
        nested_hmg.h3star_nodes, standard_reference_level_nodes
    )
    assert nested_hmg.audit["h3star_is_standard_polynomial_level"] is False
    assert nested_hmg.audit["node_subset_exact"] is True


@pytest.mark.parametrize(
    "attribute,edge_shape,node_shape,edge_nnz,node_nnz",
    (
        ("h6_to_h3star", (882, 144), (343, 64), 1800, 1000),
        ("h3star_to_h1star", (144, 12), (64, 8), 324, 216),
    ),
)
def test_pair_shapes_oracles_and_fixed_gates(
    nested_hmg, attribute, edge_shape, node_shape, edge_nnz, node_nnz
):
    transfer = getattr(nested_hmg, attribute)
    facts = transfer.audit
    assert facts["pair_fine_to_coarse"] in C2_PAIRS
    assert tuple(facts["edge_shape"]) == edge_shape
    assert tuple(facts["node_shape"]) == node_shape
    assert facts["edge_nnz"] == edge_nnz
    assert facts["node_nnz"] == node_nnz
    assert facts["line_integral_histopolation"] is True
    assert facts["simple_injection"] is False
    assert transfer.edge_transfer.shape == edge_shape
    assert transfer.node_transfer.shape == node_shape
    assert transfer.edge_transfer.dtype == np.complex128
    assert transfer.node_transfer.dtype == np.complex128
    assert facts["edge_columns_full_rank"] is True
    assert facts["gate_passed"] is True
    assert facts["gate_failures"] == ()
    assert facts["edge_line_integral_relative"] <= EDGE_LIMIT
    assert facts["curl_commuting_relative"] <= CURL_LIMIT
    assert facts["gradient_commuting_relative"] <= GRADIENT_LIMIT
    assert facts["adjoint_work_relative"] <= ADJOINT_LIMIT
    assert facts["linearity_relative"] <= LINEARITY_LIMIT
    assert facts["repeat_relative"] <= REPEAT_LIMIT
    assert facts["input_unchanged"] is True
    assert facts["finite"] is True
    assert audit_nested_hmg_transfer(transfer)["gate_passed"] is True


@pytest.mark.parametrize("attribute", ("h6_to_h3star", "h3star_to_h1star"))
def test_apply_is_linear_adjoint_repeatable_and_nonmutating(nested_hmg, attribute):
    transfer = getattr(nested_hmg, attribute)
    columns = transfer.edge_transfer.shape[1]
    rows = transfer.edge_transfer.shape[0]
    coarse = np.arange(1, columns + 1, dtype=np.float64).astype(np.complex128)
    coarse += 0.25j * np.arange(columns, 0, -1, dtype=np.float64)
    second = np.arange(columns, 2 * columns, dtype=np.float64).astype(np.complex128)
    fine = np.arange(1, rows + 1, dtype=np.float64).astype(np.complex128)
    coarse_before = coarse.copy()
    fine_before = fine.copy()
    primal = transfer.apply_primal_many(coarse)
    repeated = transfer.apply_primal_many(coarse)
    combo = transfer.apply_primal_many(0.31 * coarse - 0.17j * second)
    expected = 0.31 * primal - 0.17j * transfer.apply_primal_many(second)
    adjoint = transfer.apply_adjoint_many(fine)
    assert np.array_equal(coarse, coarse_before)
    assert np.array_equal(fine, fine_before)
    assert np.array_equal(primal, repeated)
    assert np.all(np.isfinite(primal))
    assert np.all(np.isfinite(adjoint))
    assert np.linalg.norm(combo - expected) / max(
        np.linalg.norm(expected), np.finfo(float).tiny
    ) <= LINEARITY_LIMIT
    lhs = np.vdot(primal, fine)
    rhs = np.vdot(coarse, adjoint)
    assert abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny) <= ADJOINT_LIMIT


def test_composition_and_immutability(nested_hmg):
    assert nested_hmg.audit["composition_direct_edge_relative"] <= EDGE_LIMIT
    assert nested_hmg.audit["composition_direct_node_relative"] <= EDGE_LIMIT
    assert nested_hmg.audit["composition_direct_is_independent_oracle"] is True
    for transfer in (nested_hmg.h6_to_h3star, nested_hmg.h3star_to_h1star):
        assert transfer.edge_transfer.flags.writeable is False
        assert transfer.node_transfer.flags.writeable is False
        with pytest.raises(AttributeError):
            transfer.edge_transfer = transfer.edge_transfer
        with pytest.raises(TypeError):
            transfer.audit["gate_passed"] = False


def test_mutated_pair_fails_independent_oracle(nested_hmg):
    source = nested_hmg.h6_to_h3star
    edge = source.edge_transfer.copy()
    edge[0, 0] += 0.125 + 0.25j
    mutated = NestedHmgLocalTransfer(
        source.fine_level,
        source.coarse_level,
        source.fine_nodes,
        source.coarse_nodes,
        edge,
        source.node_transfer,
        {},
    )
    with pytest.raises(ValueError, match="failed"):
        audit_nested_hmg_transfer(mutated)
