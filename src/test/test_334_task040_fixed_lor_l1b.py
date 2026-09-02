"""Task040 L1b fixed x-y Bloch quotient reference checks."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.hcurl_fixed_lor_periodic import (
    FixedP6LORXYFloquetReferenceAction,
    build_fixed_p6_lor_xy_floquet_reference_action,
)

_FULL_VERTICES = 343
_REDUCED_VERTICES = 252
_FULL_EDGES = 882
_REDUCED_EDGES = 720
_N1 = 7
_N = 6
_TINY = np.finfo(np.float64).tiny


@pytest.fixture(scope="module")
def action() -> FixedP6LORXYFloquetReferenceAction:
    return build_fixed_p6_lor_xy_floquet_reference_action()


def _probe(size: int, offset: float) -> np.ndarray:
    indices = np.arange(size, dtype=np.float64)
    return np.sin(0.013 * (indices + 1.0) + offset) + 1j * np.cos(
        0.017 * (indices + 2.0) - offset
    )


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(actual) - np.asarray(expected))
        / max(float(np.linalg.norm(np.asarray(expected))), _TINY)
    )


def _adjoint_relative(actual_x, actual_y, x, y) -> float:
    return float(
        abs(np.vdot(actual_x, y) - np.vdot(x, actual_y))
        / max(
            float(np.linalg.norm(actual_x) * np.linalg.norm(y)),
            float(np.linalg.norm(x) * np.linalg.norm(actual_y)),
            _TINY,
        )
    )


def test_l1b_contract_and_independent_coordinate_phases(action) -> None:
    audit = action.audit
    assert audit["schema_version"] == "task040.fixed-lor.l1b.v1"
    assert audit["status"] == (
        "fixed_p6_xy_floquet_reference_mechanism_qualified"
    )
    assert audit["scope"] == (
        "research_local_only_periodic_reference_mechanism_not_lor_solver"
    )
    assert audit["periodic_axes"] == ("x", "y")
    assert audit["counts"] == {
        "full_vertices": _FULL_VERTICES,
        "reduced_vertices": _REDUCED_VERTICES,
        "full_edges": _FULL_EDGES,
        "reduced_edges": _REDUCED_EDGES,
        "reduced_edge_axes": {"x": 252, "y": 252, "z": 216},
    }
    assert action.Q0.shape == (_FULL_VERTICES, _REDUCED_VERTICES)
    assert action.Q1.shape == (_FULL_EDGES, _REDUCED_EDGES)
    assert action.G_reduced.shape == (_REDUCED_EDGES, _REDUCED_VERTICES)
    assert np.all(np.diff(action.Q0.indptr) == 1)
    assert np.all(np.diff(action.Q1.indptr) == 1)
    assert audit["coverage"]["Q0_reduced_columns"] == _REDUCED_VERTICES
    assert audit["coverage"]["Q1_reduced_columns"] == _REDUCED_EDGES
    assert audit["coverage"]["corner_phase_once"]

    for (i, j), expected in (
        ((0, 0), 1.0 + 0.0j),
        ((6, 0), np.exp(0.17j)),
        ((0, 6), np.exp(-0.09j)),
        ((6, 6), np.exp(0.17j - 0.09j)),
    ):
        row = i + _N1 * (j + _N1 * 0)
        actual = action.full_vertex_phase[row]
        assert abs(actual - expected) <= 2.0e-12
    edge_rows = {
        key: row
        for row, key in enumerate(action.l1a_action.transfer.reference.edge_keys)
    }
    for key, expected in (
        (("x", 0, 6, 0), np.exp(-0.09j)),
        (("y", 6, 0, 0), np.exp(0.17j)),
        (("z", 6, 6, 0), np.exp(0.17j - 0.09j)),
        (("x", 0, 0, 0), 1.0 + 0.0j),
    ):
        assert abs(action.full_edge_phase[edge_rows[key]] - expected) <= 2.0e-12
    assert audit["phase_max_absolute_error"] <= 2.0e-12
    assert audit["phase_magnitude_max_error"] <= 2.0e-12
    assert audit["phase_magnitude_max_error_by_map"]["Q0"] <= 2.0e-12
    assert audit["phase_magnitude_max_error_by_map"]["Q1"] <= 2.0e-12
    assert audit["orientation_max_absolute_error"] <= 2.0e-12
    assert audit["structure"]["full_side_factor_count"] == 0
    assert audit["structure"]["full_cross_section_factor_count"] == 0
    assert audit["structure"]["global_direct_factor_count"] == 0
    assert audit["structure"]["coarse_factor_count"] == 0
    assert audit["max_local_rows"] <= _REDUCED_EDGES
    assert audit["petsc"] is False
    assert audit["dolfinx"] is False
    assert audit["mpi"] is False
    assert audit["allgather"] is False
    assert audit["global_factor"] is False
    print(
        "TASK040_L1B "
        f"phase_x=0.17 phase_y=-0.09 "
        f"quotient_commuting_relative={audit['quotient_gradient_commuting']['relative']:.17g} "
        f"direct_vs_congruence={audit['action']['direct_vs_congruence_relative']:.17g} "
        f"direct_adjoint={audit['action']['adjoint_relative']:.17g} "
        f"galerkin_adjoint={audit['action']['galerkin_adjoint_relative']:.17g} "
        f"spectrum_min={audit['spectrum']['min']:.17g} "
        f"spectrum_max={audit['spectrum']['max']:.17g} "
        f"spectrum_ratio={audit['spectrum']['ratio']:.17g} "
        f"builder_wall={audit['wall_seconds']:.17g} "
        f"retained_periodic_bytes={audit['bytes']['retained_periodic_maps']} "
        f"dense_transient_bytes={audit['bytes']['dense_oracle_transient']} "
        f"reduced_lor_nnz={action.reduced_lor_operator.nnz}"
    )


def test_l1b_quotient_gradient_and_p6_commuting(action) -> None:
    probe = _probe(_REDUCED_VERTICES, 0.29)
    full_scalar = action.lift_vertices(probe)
    full_gradient = action.l1a_action.transfer.reference.gradient_incidence @ full_scalar
    reduced_gradient = np.asarray(action.G_reduced @ probe)
    lifted_gradient = action.lift_edges(reduced_gradient)
    assert _relative(full_gradient, lifted_gradient) <= 2.0e-10

    T0 = np.linalg.solve(
        action.l1a_action.transfer.R0,
        np.eye(_FULL_VERTICES, dtype=np.float64),
    )
    p6_from_lor = action.l1a_action.T1 @ lifted_gradient
    p6_from_scalar = action.l1a_action.transfer.p6_discrete_gradient @ (
        T0 @ full_scalar
    )
    assert _relative(p6_from_lor, p6_from_scalar) <= 2.0e-10
    commuting = action.audit["quotient_gradient_commuting"]
    assert all(np.isfinite(commuting[name]) for name in commuting)
    assert commuting["relative"] <= 2.0e-10


def test_l1b_direct_congruence_galerkin_and_complex_probes(action) -> None:
    x = _probe(_REDUCED_EDGES, 0.13)
    y = _probe(_REDUCED_EDGES, 0.37)
    direct_x = action.apply_lor_streamed(x)
    direct_y = action.apply_lor_streamed(y)
    congruence_x = np.asarray(action.reduced_lor_operator @ x)
    assert _relative(direct_x, congruence_x) <= 1.0e-10
    assert _relative(action.apply_lor_streamed(x), direct_x) <= 1.0e-10
    alpha, beta = 0.7 - 0.2j, -0.4 + 0.3j
    assert _relative(
        action.apply_lor_streamed(alpha * x + beta * y),
        alpha * direct_x + beta * direct_y,
    ) <= 1.0e-10
    assert _adjoint_relative(direct_x, direct_y, x, y) <= 2.0e-11

    galerkin_x = action.apply_galerkin(x)
    galerkin_y = action.apply_galerkin(y)
    full_x = action.lift_edges(x)
    independent_galerkin = action.restrict_edges(
        action.l1a_action.T1.conj().T
        @ (
            action.l1a_action.p6_operator
            @ (action.l1a_action.T1 @ full_x)
        )
    )
    assert _relative(galerkin_x, independent_galerkin) <= 1.0e-10
    assert _adjoint_relative(galerkin_x, galerkin_y, x, y) <= 2.0e-11
    energy = np.vdot(x, galerkin_x)
    assert np.isfinite(energy)
    assert energy.real > 0.0
    assert abs(energy.imag) / max(abs(energy), _TINY) <= 1.0e-10
    rayleigh = complex(np.vdot(x, galerkin_x)) / complex(
        np.vdot(x, action.reduced_lor_operator @ x)
    )
    assert np.isfinite(rayleigh.real)
    assert abs(rayleigh.imag) / max(abs(rayleigh), _TINY) <= 1.0e-10
    spectrum = action.audit["spectrum"]
    tolerance = action.audit["rayleigh_spectrum_range_tolerance"]
    assert spectrum["min"] - tolerance <= rayleigh.real <= spectrum["max"] + tolerance

    metrics = action.audit["action"]
    assert metrics["direct_vs_congruence_relative"] <= 1.0e-10
    assert metrics["repeat_relative"] <= 1.0e-10
    assert metrics["linearity_relative"] <= 1.0e-10
    assert metrics["adjoint_relative"] <= 2.0e-11
    assert metrics["galerkin_relative"] <= 1.0e-10
    assert metrics["galerkin_adjoint_relative"] <= 2.0e-11
    assert spectrum["finite"] and spectrum["positive"]
    assert spectrum["count"] == _REDUCED_EDGES
