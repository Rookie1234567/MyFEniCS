"""Task40's narrow regression for the Task042 boundary component reuse."""

from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from src.solvers.directional_boundary import (
    BoundaryLayout,
    DirectionalBoundaryAction,
    FacetPolynomial,
)
from src.solvers.native_boundary_adapter import (
    NativeBoundaryAdapter,
    independent_trace_port_terms,
)
from src.solvers.task40_w1_local_probe import _direct_full_basis_integral


def _element():
    import basix.ufl

    return basix.ufl.element("N1curl", "hexahedron", 6).basix_element


def _modes():
    return [
        {
            "side": side,
            "k_vector": [0.2 + 0.13 * j, -0.17 + 0.09 * j, 0.31],
            "reference_plane_nm": 0.0 if side == "bottom" else 2.0,
            "e_vector": [1 + 0.2j, 0.3 - 0.1j, 0],
            "traction_vector": [0.7 - 0.8j, -0.9 + 0.2j, 0],
            "projection_denominator": 1.3 + j,
        }
        for side in ("bottom", "top")
        for j in range(2)
    ]


@pytest.mark.parametrize("q", [30, 60])
def test_directional_action_matches_explicit_complete_facet_sum(q):
    import basix

    polynomial = FacetPolynomial(_element())
    layout = BoundaryLayout(
        [0.0, 0.6, 1.5], [0.0, 0.8, 1.9], polynomial,
        (np.exp(0.3j), np.exp(-0.2j)),
    )
    modes = _modes()
    action = DirectionalBoundaryAction(layout, modes, q)
    trace = np.arange(1, layout.rows + 1, dtype=np.float64).astype(np.complex128)
    direct = np.zeros((len(modes), 2), dtype=np.complex128)
    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    for m, mode in enumerate(modes):
        side = mode["side"]
        zeta = 0.0 if side == "bottom" else 1.0
        tab = polynomial.element.tabulate(
            0, np.column_stack((rule, np.full(len(rule), zeta)))
        )[0][:, polynomial.active[side], :2]
        for i in range(layout.nx):
            for j in range(layout.ny):
                dx = layout.x[i + 1] - layout.x[i]
                dy = layout.y[j + 1] - layout.y[j]
                pts = np.column_stack((
                    layout.x[i] + dx * rule[:, 0],
                    layout.y[j] + dy * rule[:, 1],
                    np.full(len(rule), mode["reference_plane_nm"]),
                ))
                basis_integral = np.einsum(
                    "q,qjc->jc",
                    weights * np.exp(-1j * np.conj(pts @ mode["k_vector"])),
                    tab,
                ) * np.array([dy, dx])
                ids = layout.maps[side][i, j]
                local = trace[ids] * layout.weights[side][i, j]
                direct[m] += local @ basis_integral
    np.testing.assert_allclose(action.project_components(trace), direct, rtol=2e-11, atol=2e-11)


def test_native_adapter_adjoint_and_slave_storage_contract():
    matrix = csr_matrix(np.asarray([[1 + 0.3j, 2 - 0.2j, 0], [0, 0.5 - 0.7j, 0]], complex))
    adapter = NativeBoundaryAdapter(matrix, [1, 3], 3, 5, [2], identity="task40-fixture")
    x = np.asarray([0.2 + 1j, 3 - 0.1j, 0], dtype=np.complex128)
    y = np.asarray([1, 2 + 0.3j, -0.1j, 2 - 1j, 3], dtype=np.complex128)
    np.testing.assert_allclose(np.vdot(y, adapter.extract(x)), np.vdot(adapter.scatter(y), x))
    assert adapter.scatter(y)[2] == 0
    invalid = x.copy()
    invalid[2] = 1e-30
    with pytest.raises(ValueError, match="slave zero"):
        adapter.extract(invalid)


@pytest.mark.parametrize("degree", [4, 6])
@pytest.mark.parametrize("side", ["bottom", "top"])
def test_native_integral_retains_all_rows_against_direct_basix_quadrature(degree, side):
    import basix
    import basix.ufl

    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    polynomial = FacetPolynomial(element)
    J = np.diag([0.37, 0.21, 0.8])
    origin = np.asarray([-3.0, 1.25, 120.0 if side == "top" else -10.0])
    k = np.asarray([0.41 - 0.07j, -0.28 + 0.03j, 0.13], dtype=np.complex128)
    q = 30
    actual = polynomial.integral_native(side, k, J, origin, q)
    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    zref = 1.0 if side == "top" else 0.0
    points_ref = np.column_stack((rule, np.full(len(rule), zref)))
    tab = element.tabulate(0, points_ref)[0][:, :, :2]
    points_phys = origin + points_ref * np.diag(J)
    phase = np.exp(1j * (points_phys @ k))
    expected = np.einsum("q,qjc->jc", weights * phase, tab, optimize=True)
    expected *= np.asarray([J[1, 1], J[0, 0]])
    np.testing.assert_allclose(actual, expected, rtol=2e-11, atol=2e-11)
    assert actual.shape == (element.dim, 2)
    assert len(polynomial.active[side]) < element.dim


@pytest.mark.parametrize("degree", [4, 6])
@pytest.mark.parametrize("side", ["bottom", "top"])
def test_direct_q30_full_dof_oracle_matches_candidate_integral(degree, side):
    import basix
    import basix.ufl

    element = basix.ufl.element("N1curl", "hexahedron", degree).basix_element
    polynomial = FacetPolynomial(element)
    lower = np.asarray([-5.25, 1.5, -10.0 if side == "bottom" else 120.0])
    extent = np.asarray([0.19, 0.31, 10.0])
    reference_vertices = basix.cell.geometry(basix.CellType.hexahedron)
    coordinates = lower + reference_vertices * extent
    k = np.asarray([0.21 - 0.03j, -0.17 + 0.01j, 0.07 + 0.02j])
    direct, rule, weights = _direct_full_basis_integral(
        element, side, k, coordinates, 30
    )
    candidate = polynomial.integral_native(
        side, k, np.diag(extent), lower, 30
    )
    np.testing.assert_allclose(direct, candidate, rtol=2e-11, atol=2e-11)
    assert rule.shape[1] == 2 and weights.shape == (len(rule),)
    assert direct.shape == (element.dim, 2)


def test_direct_trace_carriers_use_owned_active_original_rows_only():
    # The slave row is exactly zero; the independent active rows survive with
    # their original ordering and are represented by the mainline P6 API.
    system = SimpleNamespace(
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=np.asarray([0, 2], dtype=np.int64),
            original_to_active={0: 0, 2: 1},
        )
    )
    C = np.asarray([[1 + 1j], [0], [2 - 1j]], dtype=np.complex128)
    D = np.asarray([[3 - 2j, 0, -0.5j]], dtype=np.complex128)
    terms = independent_trace_port_terms(system, C, D)
    assert len(terms) == 1
    np.testing.assert_array_equal(terms[0].B_original_rows, [0, 2])
    np.testing.assert_array_equal(terms[0].D_original_rows, [0, 2])
    with pytest.raises(ValueError, match="slave/interior support"):
        independent_trace_port_terms(system, C + np.asarray([[0], [1e-30], [0]]), D)
