"""Targeted independent checks for the V11 bounded full-882 boundary action."""
import numpy as np
import pytest

from src.solvers.directional_boundary import FacetPolynomial
from src.solvers.task40_v11_chunked_boundary_action import full882_chunked_boundary_action
from src.solvers.task40_w1_local_probe import analytic_full_basis_integral


class _ReverseDofOrientation:
    """Small exact permutation used to check primal/dual orientation pairing."""

    def T_apply(self, data, cell_info, block_size):
        assert np.asarray(cell_info).shape == (1,)
        assert block_size == 1
        data[:] = data[::-1].copy()


def _p6_element():
    import basix.ufl

    return basix.ufl.element("N1curl", "hexahedron", 6).basix_element


def _coordinates(bounds):
    (x0, x1), (y0, y1), (z0, z1) = bounds
    return np.asarray(
        [
            [x0, y0, z0], [x1, y0, z0], [x0, y1, z0], [x1, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x0, y1, z1], [x1, y1, z1],
        ],
        dtype=np.float64,
    )


def _modes(side):
    return [
        {
            "side": side,
            "k_vector": [0.34 + 0.015j, -0.21 + 0.01j, 0.42 - 0.008j],
            "e_vector": [0.7 + 0.1j, -0.2 + 0.3j, 0.0],
            "traction_vector": [-0.3 + 0.4j, 0.8 - 0.15j, 0.0],
            "projection_denominator": 1.7,
        },
        {
            "side": side,
            "k_vector": [-0.17 - 0.006j, 0.29 + 0.004j, -0.36 + 0.011j],
            "e_vector": [0.1 - 0.2j, 0.6 + 0.05j, 0.0],
            "traction_vector": [0.5 + 0.07j, -0.4 + 0.3j, 0.0],
            "projection_denominator": 2.3,
        },
    ]


@pytest.mark.parametrize("side", ["top", "bottom"])
@pytest.mark.parametrize("mode_batch_size", [1, 2])
def test_full882_chunked_action_matches_independent_full_row_moments(side, mode_batch_size):
    element = _p6_element()
    bounds = ((0.37, 1.81), (-0.52, 0.73), (2.25, 3.50))
    coords = _coordinates(bounds)
    modes = _modes(side)
    alpha = np.asarray([0.7 - 0.2j, -0.35 + 0.41j], dtype=np.complex128)
    coeff = np.linspace(-0.3, 0.8, 882) + 1j * np.linspace(0.4, -0.2, 882)
    coeff = np.asarray(coeff, dtype=np.complex128)
    cell_info = np.asarray([0], dtype=np.uint32)

    result = full882_chunked_boundary_action(
        element=element,
        dof_element=_ReverseDofOrientation(),
        cell_info=cell_info,
        coordinates=coords,
        side=side,
        modes=modes,
        selected_indices=[0, 1],
        mode_alpha=alpha,
        local_coefficients=coeff,
        quadrature_degree=30,
        point_chunk_size=37,
        mode_batch_size=mode_batch_size,
    )
    rotated_result = full882_chunked_boundary_action(
        element=element,
        dof_element=_ReverseDofOrientation(),
        cell_info=cell_info,
        coordinates=coords,
        side=side,
        modes=modes,
        selected_indices=[0, 1],
        mode_alpha=alpha,
        local_coefficients=1j * coeff,
        quadrature_degree=30,
        point_chunk_size=37,
        mode_batch_size=mode_batch_size,
    )

    polynomial = FacetPolynomial(element)
    lower = np.asarray([axis[0] for axis in bounds], dtype=np.float64)
    jacobian = np.diag([axis[1] - axis[0] for axis in bounds])
    expected_b = np.zeros(882, dtype=np.complex128)
    expected_d = np.zeros(2, dtype=np.complex128)
    for i, mode in enumerate(modes):
        k = np.asarray(mode["k_vector"], dtype=np.complex128)
        integrated = analytic_full_basis_integral(
            polynomial, side, k, jacobian, lower, dps=60
        )
        b_mode = integrated @ (-np.asarray(mode["traction_vector"][:2], dtype=np.complex128))
        d_mode = (integrated @ np.asarray(mode["e_vector"][:2], dtype=np.complex128)).conj()
        d_mode /= mode["projection_denominator"]
        expected_b += alpha[i] * b_mode[::-1]
        expected_d[i] = d_mode[::-1] @ coeff

    assert result["b_alpha"].shape == (882,)
    assert result["d_action"].shape == (2,)
    b_relative_error = np.linalg.norm(result["b_alpha"] - expected_b) / np.linalg.norm(expected_b)
    d_relative_error = np.linalg.norm(result["d_action"] - expected_d) / np.linalg.norm(expected_d)
    assert np.linalg.norm(expected_b) > 0.0
    assert np.linalg.norm(expected_d) > 0.0
    assert b_relative_error <= 1e-10
    assert d_relative_error <= 1e-10
    linearity_error = (
        np.linalg.norm(rotated_result["d_action"] - 1j * result["d_action"])
        / np.linalg.norm(result["d_action"])
    )
    assert linearity_error <= 1e-12
    work = result["work"]
    assert work["full_native_row_count"] == 882
    assert work["tangential_components"] == [0, 1]
    assert work["basis_tabulations"] == work["point_chunk_count"] > 1
    assert work["mode_batch_passes"] == work["point_chunk_count"] * (2 // mode_batch_size)
    assert work["full_mode_by_face_map_retained"] is False
    assert work["mode_square_matrix_allocated"] is False
    assert work["piola_tangential_area_factors"] == pytest.approx([1.25, 1.44])
    assert work["conservative_helper_owned_array_bytes_upper"] >= (
        work["fixed_helper_owned_array_bytes_upper"]
    )
    assert "process-tree RSS" in work["memory_scope"]


def test_full882_chunked_action_rejects_mixed_side_and_unbounded_batches():
    element = _p6_element()
    modes = _modes("top")
    modes[1] = dict(modes[1], side="bottom")
    args = {
        "element": element,
        "dof_element": _ReverseDofOrientation(),
        "cell_info": np.asarray([0], dtype=np.uint32),
        "coordinates": _coordinates(((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))),
        "side": "top",
        "modes": modes,
        "selected_indices": [0, 1],
        "mode_alpha": np.ones(2, dtype=np.complex128),
        "local_coefficients": np.ones(882, dtype=np.complex128),
    }
    with pytest.raises(ValueError, match="requested physical side"):
        full882_chunked_boundary_action(**args)

    args["modes"] = _modes("top")
    args["mode_batch_size"] = 65
    with pytest.raises(ValueError, match="mode_batch_size"):
        full882_chunked_boundary_action(**args)
