"""Focused Task040 L1a fixed p6/LOR action checks."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from src.solvers.hcurl_fixed_lor_action import (
    FixedP6LORReferenceAction,
    build_fixed_p6_lor_reference_action,
)


@pytest.fixture(scope="module")
def action() -> FixedP6LORReferenceAction:
    return build_fixed_p6_lor_reference_action()


def _probe(size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(size=size) + 1j * rng.normal(size=size)


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    scale = max(float(np.linalg.norm(expected)), np.finfo(float).tiny)
    return float(np.linalg.norm(actual - expected) / scale)


def test_l1a_contract_and_provenance(action: FixedP6LORReferenceAction) -> None:
    audit = action.audit
    assert audit["schema_version"] == "task040.fixed-lor.l1a.v1"
    assert audit["status"] == "fixed_p6_reference_mechanism_qualified"
    assert audit["scope"] == "research_local_only_reference_mechanism_not_lor_solver"
    assert audit["tau"] == 1.0
    assert audit["operator"] == "curlcurl_plus_tau_mass"
    assert audit["counts"] == {
        "p6_dofs": 882,
        "lor_edges": 882,
        "lor_cells": 216,
        "local_p1_edges": 12,
        "lor_nnz": audit["counts"]["lor_nnz"],
    }
    assert audit["counts"]["lor_nnz"] > 0
    assert audit["operator_shapes"]["p6"] == (882, 882)
    assert audit["operator_shapes"]["lor"] == (882, 882)
    assert audit["operator_shapes"]["T1"] == (882, 882)
    assert audit["operator_shapes"]["cell_rows"] == (216, 12)
    assert audit["operator_shapes"]["cell_signs"] == (216, 12)
    assert audit["operator_shapes"]["cell_local_tensor"] == (12, 12)

    orientation = audit["orientation"]
    mapping = audit["cell_mapping"]
    assert orientation["pass"]
    assert orientation["constant_field_max_error"] <= 2e-12
    assert mapping["pass"] and mapping["constant_field_pass"]
    assert mapping["covered"] == 882
    assert mapping["missing"] == 0
    assert mapping["coverage_min"] == 1
    assert mapping["coverage_max"] == 4
    assert mapping["constant_field_max_error"] <= 2e-12

    for degree, name in ((12, "p6"), (2, "p1")):
        factory = audit["tensor_factory"][name]
        assert factory["quadrature_degree"] == degree
        assert factory["quadrature_point_count"] > 0
        assert len(factory["identity_sha256"]) == 64
        assert int(factory["identity_sha256"], 16) >= 0
        assert factory["reference_component_bytes"] > 0
        assert factory["total_build_seconds"] >= 0.0

    spectrum = audit["generalized_spectrum"]
    assert audit["checks"]["finite"]
    assert spectrum["count"] == 882
    assert np.isfinite([spectrum["min"], spectrum["max"], spectrum["ratio"]]).all()
    assert 0.0 < spectrum["min"] <= spectrum["max"]
    assert spectrum["ratio"] > 0.0
    assert audit["structure"]["max_local_rows"] == 882
    assert all(
        audit["structure"][key] == 0
        for key in (
            "full_side_factor_count",
            "full_cross_section_factor_count",
            "global_direct_factor_count",
            "coarse_factor_count",
        )
    )

    for array in (
        action.p6_operator,
        action.T1,
        action.cell_rows,
        action.cell_signs,
        action.cell_local_tensor,
    ):
        assert not array.flags.writeable
    assert isinstance(action.lor_operator, csr_matrix)
    assert not action.lor_operator.data.flags.writeable
    assert not action.lor_operator.indices.flags.writeable
    assert not action.lor_operator.indptr.flags.writeable
    print(
        "TASK040_L1A "
        f"spectrum={spectrum['min']:.6e}:{spectrum['max']:.6e} "
        f"action={audit['streamed_action']['vs_csr_relative']:.3e} "
        f"commuting={audit['T1']['inverse_commuting_relative']:.3e} "
        f"wall={audit['wall_seconds']:.3f} "
        f"bytes={audit['bytes']['dense_retained']} "
        f"nnz={audit['counts']['lor_nnz']}"
    )


def test_l1a_complex_actions(action: FixedP6LORReferenceAction) -> None:
    x = _probe(882, 3331)
    y = _probe(882, 3332)
    streamed_x = action.apply_lor_streamed(x)
    streamed_y = action.apply_lor_streamed(y)
    csr_x = np.asarray(action.lor_operator @ x)
    assert _relative(streamed_x, csr_x) <= 1e-10
    assert _relative(action.apply_lor_streamed(x), streamed_x) <= 1e-10
    alpha, beta = 0.7 - 0.2j, -0.4 + 0.3j
    linear = action.apply_lor_streamed(alpha * x + beta * y)
    assert _relative(linear, alpha * streamed_x + beta * streamed_y) <= 1e-10

    lhs = np.vdot(streamed_x, y)
    rhs = np.vdot(x, streamed_y)
    assert abs(lhs - rhs) / max(
        np.linalg.norm(streamed_x) * np.linalg.norm(y),
        np.linalg.norm(x) * np.linalg.norm(streamed_y),
        np.finfo(float).tiny,
    ) <= 2e-11
    np.testing.assert_allclose(
        action.apply_p6(x), action.p6_operator @ x, rtol=0.0, atol=1e-12
    )

    galerkin_x = action.apply_galerkin(x)
    galerkin_y = action.apply_galerkin(y)
    left = np.vdot(x, galerkin_y)
    right = np.vdot(galerkin_x, y)
    assert abs(left - right) / max(
        np.linalg.norm(x) * np.linalg.norm(galerkin_y),
        np.linalg.norm(galerkin_x) * np.linalg.norm(y),
        np.finfo(float).tiny,
    ) <= 1e-10
    energy = np.vdot(x, galerkin_x)
    assert energy.real > 0.0
    assert abs(energy.imag) / max(abs(energy), np.finfo(float).tiny) <= 1e-10


def test_l1a_transfer_and_energy(action: FixedP6LORReferenceAction) -> None:
    transfer = action.transfer
    vector = _probe(882, 3341)
    recovered = transfer.R1 @ (action.T1 @ vector)
    assert _relative(recovered, vector) <= 2e-10

    scalar_values = _probe(343, 3342)
    scalar_coefficients = np.linalg.solve(transfer.R0, scalar_values)
    lor_gradient = transfer.reference.gradient_incidence
    left = action.T1 @ (lor_gradient @ scalar_values)
    right = transfer.p6_discrete_gradient @ scalar_coefficients
    assert _relative(left, right) <= 2e-10

    p6_vector = action.T1 @ vector
    numerator = np.vdot(p6_vector, action.p6_operator @ p6_vector)
    denominator = np.vdot(vector, action.lor_operator @ vector)
    rayleigh = numerator / denominator
    assert rayleigh.real > 0.0
    assert abs(rayleigh.imag) / max(abs(rayleigh), np.finfo(float).tiny) <= 1e-10
    spectrum = action.audit["generalized_spectrum"]
    assert spectrum["min"] - 1e-10 <= rayleigh.real <= spectrum["max"] + 1e-10
