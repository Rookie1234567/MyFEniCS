"""Pure local S5-A1 interlevel transfer tests."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from src.solvers.fullspace_lor_memory_hierarchy import (
    ADJOINT_LIMIT,
    CURL_LIMIT,
    EDGE_QUADRATURE_LIMIT,
    GRADIENT_LIMIT,
    INTERLEVEL_BATCH_CELL_CAP,
    LINEARITY_LIMIT,
    REPEAT_LIMIT,
    audit_local_interlevel_transfer,
    build_local_interlevel_edge_transfer,
)


@pytest.fixture(scope="module", params=[(6, 3), (3, 1)])
def interlevel(request):
    fine_degree, coarse_degree = request.param
    return (
        fine_degree,
        coarse_degree,
        build_local_interlevel_edge_transfer(fine_degree, coarse_degree),
    )


def test_interlevel_shape_bytes_and_independent_audit(
    interlevel,
) -> None:
    fine_degree, coarse_degree, transfer = interlevel
    expected_shape = (
        3 * fine_degree * (fine_degree + 1) ** 2,
        3 * coarse_degree * (coarse_degree + 1) ** 2,
    )
    expected_node_shape = (
        (fine_degree + 1) ** 3,
        (coarse_degree + 1) ** 3,
    )
    assert transfer.edge_transfer.shape == expected_shape
    assert transfer.node_transfer.shape == expected_node_shape
    assert transfer.edge_transfer.dtype == np.complex128
    assert transfer.node_transfer.dtype == np.complex128
    assert transfer.edge_transfer.nbytes == expected_shape[0] * expected_shape[1] * 16
    assert transfer.node_transfer.nbytes == (
        expected_node_shape[0] * expected_node_shape[1] * 16
    )
    assert transfer.edge_transfer.flags.writeable is False
    assert transfer.node_transfer.flags.writeable is False
    assert transfer.audit["edge_line_integral_relative"] <= EDGE_QUADRATURE_LIMIT
    assert transfer.audit["curl_flux_relative"] <= CURL_LIMIT
    assert transfer.audit["gradient_commuting_relative"] <= GRADIENT_LIMIT
    assert transfer.audit["adjoint_work_relative"] <= ADJOINT_LIMIT
    assert transfer.audit["linearity_relative"] <= LINEARITY_LIMIT
    assert transfer.audit["repeat_relative"] <= REPEAT_LIMIT
    assert transfer.audit["simple_injection"] is False
    assert transfer.audit["line_integral_histopolation"] is True
    assert transfer.audit["oracle_workspace_retained"] is False
    assert transfer.audit["global_transfer_matrix"] is False


def test_interlevel_apply_and_hand_checked_adjoint(
    interlevel,
) -> None:
    fine_degree, _coarse_degree, transfer = interlevel
    rng = np.random.default_rng(3120 + fine_degree)
    coarse = rng.normal(size=transfer.edge_shape[1]) + 1j * rng.normal(
        size=transfer.edge_shape[1]
    )
    second = rng.normal(size=transfer.edge_shape[1]) + 1j * rng.normal(
        size=transfer.edge_shape[1]
    )
    fine = rng.normal(size=transfer.edge_shape[0]) + 1j * rng.normal(
        size=transfer.edge_shape[0]
    )
    before = coarse.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = transfer.apply_primal_many(coarse)
    repeated = transfer.apply_primal_many(coarse)
    combined = transfer.apply_primal_many(alpha * coarse + beta * second)
    expected = alpha * observed + beta * transfer.apply_primal_many(second)
    adjoint = transfer.apply_adjoint_many(fine)
    lhs = np.vdot(observed, fine)
    rhs = np.vdot(coarse, adjoint)
    assert abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny) <= ADJOINT_LIMIT
    assert np.linalg.norm(combined - expected) / max(
        np.linalg.norm(expected), np.finfo(float).tiny
    ) <= LINEARITY_LIMIT
    assert np.linalg.norm(repeated - observed) / max(
        np.linalg.norm(observed), np.finfo(float).tiny
    ) <= REPEAT_LIMIT
    np.testing.assert_array_equal(coarse, before)
    assert np.all(np.isfinite(observed))
    assert np.all(np.isfinite(adjoint))
    assert transfer.apply_primal_many(
        np.stack([coarse] * INTERLEVEL_BATCH_CELL_CAP)
    ).shape == (INTERLEVEL_BATCH_CELL_CAP, transfer.edge_shape[0])
    with pytest.raises(ValueError, match="fixed cap"):
        transfer.apply_primal_many(
            np.stack([coarse] * (INTERLEVEL_BATCH_CELL_CAP + 1))
        )


def test_mutated_map_fails_independent_audit(
    interlevel,
) -> None:
    fine_degree, coarse_degree, transfer = interlevel
    bad_edge = transfer.edge_transfer.copy()
    bad_edge[0, 0] += 0.125 + 0.25j
    with pytest.raises(ValueError):
        audit_local_interlevel_transfer(
            fine_degree,
            coarse_degree,
            bad_edge,
            transfer.node_transfer,
        )


def test_module_has_no_global_or_runtime_solver_dependencies() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_memory_hierarchy.py"
    source = path.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "allgather" not in lowered
    assert "petsc" not in lowered
    assert "mpi" not in lowered
    assert "solver" not in lowered
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name not in {"mpi4py", "petsc4py", "dolfinx"} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"mpi4py", "petsc4py", "dolfinx"}


def test_interlevel_object_is_immutable() -> None:
    transfer = build_local_interlevel_edge_transfer(3, 1)
    with pytest.raises(ValueError):
        transfer.edge_transfer[0, 0] = 1.0
    with pytest.raises(AttributeError):
        transfer.fine_degree = 1
    with pytest.raises(TypeError):
        transfer.audit["fine_degree"] = 1
